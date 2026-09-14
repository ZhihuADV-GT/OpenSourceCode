"""
局末文章生成器（服务层）

职责：
- build_blueprint：矩阵位置 + 结构 → 段落蓝图（每张观点卡=一段，填充卡按相邻作用归段）
- classify_content_type：关键词规则分类（原因/机制/现象/对比/例子/数据/观点）
- generate_paragraph：选模板 + 调 AI 逐段生成（提取+填空+润色）
- assemble：按序拼装成篇

设计原则：
- 独立服务，输入为 matrix_vector_system.export_snapshot() 的结果 dict
- 不修改核心通信/IO
- AI 失败时降级为纯卡牌原文拼接（FALLBACK_PARAGRAPH）

卡牌原文的三级来源（见 _resolve_card_text）：
- 预设卡的 SaltCard.text 在 _load_card_by_id 里被写死为空，必须靠 get_card_text
  从 article_lib 的 linespots 反查；
- 动态卡的原文只存在于 session 缓存或落盘记录里，article_lib 中根本没有它，
  必须优先读 SaltCard.text。历史上这里只调 get_card_text，而它的
  "_card_" 守卫会把含 "_dynamic_" 的 ID 全部拒掉 → 动态卡原文 100% 丢失。
"""

from __future__ import annotations

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

from game.article_store import discover_article_files, read_json_like
from game.numerics.card_rules import display_card_type, normalize_card_type
from game.numerics.matrix_vector_system import StructureType
from game.template_loader import select_template, get_template_loader
from game.api.ai_service import call_tongyi
from game.api.llm_prompt import (
    GENERATE_PARAGRAPH_SYSTEM_PROMPT,
    GENERATE_PARAGRAPH_USER_TEMPLATE,
    CONTENT_TYPE_KEYWORDS,
    STRUCTURE_TONE_SNIPPETS,
    LEAN_MODIFIERS,
    FALLBACK_PARAGRAPH,
)
from game.api.llm_config import TONGYI_TIMEOUT_CHAT
from game.api.dynamic_card_store import load_dynamic_text


# ========== 常量 ==========

# 文章库目录与发现逻辑统一在 game.article_store（叶子模块），
# 本模块不再自己算 _BACKEND_DIR / _ARTICLE_LIB_DIR。

# StructureType.value → 模板库 structure 字段名
_STRUCTURE_NAME_MAP: dict[str, str] = {
    "驳论论证": "驳论",
    "并列论证": "并列",
    "递进论证": "递进",
    "总-分-总": "总-分-总",
    "总-分": "总-分",
    "分-总": "分-总",
    "其它": "通用",
}

# 填充卡织入角色提示
_WEAVE_ROLE_HINT: dict[str, str] = {
    "情绪": "共情渲染",
    "漏洞": "排雷提醒",
    "修辞": "金句点缀",
}

# 生成参数
_GENERATE_MAX_TOKENS: int = 400
_GENERATE_TEMPERATURE: float = 0.6
# 逐段生成的最大并发数：段落相互独立，可并发调 AI 把总耗时从「各段之和」压到「约最慢一段」
_GENERATE_MAX_PARALLEL: int = 5


# ========== 数据结构 ==========

@dataclass
class ParagraphSpec:
    """段落蓝图中的单个段落规格"""
    index: int                 # 段序（0-based）
    role: str                  # 段落角色（破题段/驳斥段/...）
    card_id: str               # 主卡牌 ID
    card_text: str             # 主卡牌原文
    card_type: str             # 主卡牌类型（观点/漏洞/...）
    content_type: str          # 内容类型（原因类/机制类/...）
    weave_cards: list = field(default_factory=list)  # 依附填充卡 [(type, text), ...]
    template_id: str = ""      # 命中的模板 ID


# ========== 卡牌原文加载（自给自足，不碰核心代码） ==========

# read_json_like 与 discover_article_files 统一从 game.article_store 导入。
# 这里原本各有一份：read_json_like 是第三份实现（写法更简但语义相同），
# _load_article_payload 里还内联了第四份文章 glob。四份各自演化早晚会对不上。


_article_cache: dict[str, dict] = {}


def _load_article_payload(article_id: str) -> Optional[dict]:
    """按 article_id 加载文章 payload（带缓存）

    文章列表每次实时扫描（目录不存在时 discover_article_files 回空表），
    但解析好的 payload 进 _article_cache：本函数在生成一篇文章时会被
    每张卡调一次，不缓存就是 O(卡数 × 文章数) 次 JSON 解析。
    缓存不会陷进「陈旧快照」那个坑：文章 id 带内容 hash，同 id 即同内容。
    """
    if article_id in _article_cache:
        return _article_cache[article_id]

    for path in discover_article_files():
        try:
            payload = read_json_like(path)
        except Exception:
            continue
        if payload.get("id") == article_id:
            _article_cache[article_id] = payload
            return payload
    return None


def get_card_text(card_id: str) -> str:
    """
    从 article_lib 提取卡牌原文

    优先用 start_context/end_context 在正文中定位（数字索引常不准），
    定位失败时回退到 content[start:end]，再失败则拼接 context。
    card_id 形如 "article_6_card_2"，article_id = "article_6"
    """
    if not card_id or "_card_" not in card_id:
        return ""

    article_id = card_id.split("_card_")[0]
    payload = _load_article_payload(article_id)
    if not payload:
        return ""

    content = payload.get("content", "")
    for spot in payload.get("linespots", []):
        if spot.get("card_id") != card_id:
            continue

        start_ctx = (spot.get("start_context") or "").strip()
        end_ctx = (spot.get("end_context") or "").strip()

        # 策略1：用 context 在正文定位（最可靠）
        if start_ctx and end_ctx:
            s = content.find(start_ctx)
            if s != -1:
                e = content.find(end_ctx, s)
                if e != -1:
                    return content[s:e + len(end_ctx)].strip()

        # 策略2：回退到数字索引
        start = int(spot.get("start", 0))
        end = int(spot.get("end", 0))
        start = max(0, min(start, len(content)))
        end = max(start, min(end, len(content)))
        text = content[start:end].strip()
        if text:
            return text

        # 策略3：拼接 context 兜底
        return (start_ctx + end_ctx).strip()
    return ""


def _resolve_card_text(card_id: str, cards_data: dict) -> str:
    """三级取卡牌原文（预设卡与动态卡通吃）

    1. cards_data[card_id].text —— 动态卡的原文**只**存在于这里
       （session 内存缓存命中，或 _reconstruct_dynamic_card 从落盘读到）
    2. get_card_text(card_id) —— 预设卡走 article_lib linespots 反查
    3. load_dynamic_text(card_id) —— cards_data 未包含该卡时（快照不完整、
       卡牌加载失败）直接查落盘兜底

    顺序不能颠倒：预设卡的 text 恒为空，落到第 2 级；动态卡在 article_lib
    里查不到，第 2 级必然返回空，落到第 1/3 级。
    """
    card = cards_data.get(card_id)
    text = (getattr(card, "text", "") or "").strip()
    if text:
        return text

    text = get_card_text(card_id).strip()
    if text:
        return text

    return load_dynamic_text(card_id).strip()


# ========== 内容类型分类（关键词规则，不调 AI） ==========

def classify_content_type(card_text: str) -> str:
    """
    按关键词规则判断内容类型

    Returns: 原因类/机制类/现象类/对比类/例子类/数据类/观点类（默认）
    """
    if not card_text:
        return "观点类"

    # 按优先级匹配（数据类最具体，优先判断）
    priority = ["数据类", "例子类", "机制类", "对比类", "现象类", "原因类"]
    for ctype in priority:
        keywords = CONTENT_TYPE_KEYWORDS.get(ctype, [])
        for kw in keywords:
            if kw in card_text:
                return ctype
    return "观点类"


# ========== lean 基调计算 ==========

def compute_lean(vector) -> str:
    """
    θ = atan2(盐度 y, 热度 x)，答主之路 = 45°

    Returns: emotional(θ<35°) / rational(35°~55°) / critical(θ>55°)
    """
    x = getattr(vector, "x", 0.0)
    y = getattr(vector, "y", 0.0)
    if x == 0 and y == 0:
        return "rational"
    theta = math.degrees(math.atan2(y, x))
    if theta < 0:
        theta += 360  # 归一到 [0, 360)
    # 只关心第一象限附近的角度带
    if theta < 35:
        return "emotional"
    elif theta > 55 and theta < 180:
        return "critical"
    return "rational"


# ========== 篇幅档位 ==========

def _determine_length_level(card_text: str) -> str:
    """按卡牌原文长度定档位（默认精简，省 token）"""
    n = len(card_text)
    if n >= 60:
        return "标准"
    return "精简"


# ========== 角色映射 ==========

def _role_for_position(structure_name: str, is_first: bool, is_last: bool) -> str:
    """根据结构 + 段落位置确定角色"""
    if structure_name == "驳论":
        if is_first:
            return "破题段"
        if is_last:
            return "立论收束段"
        return "驳斥段"
    if structure_name == "并列":
        if is_first:
            return "并列总起段"
        if is_last:
            return "并列汇总段"
        return "并列论述段"
    if structure_name == "递进":
        if is_first:
            return "递进起始段"
        if is_last:
            return "递进到顶段"
        return "递进推进段"
    if structure_name in ("总-分-总", "总-分"):
        if is_first:
            return "总起段"
        if is_last and structure_name == "总-分-总":
            return "回扣段"
        return "论述段"
    if structure_name == "分-总":
        if is_last:
            return "回扣段"
        return "论述段"
    # 其它/通用
    if is_first:
        return "开头段"
    if is_last:
        return "结尾段"
    return "论述段"


# ========== 相邻填充卡查找 ==========

def _find_adjacent_fillers(matrix, cards_data, row: int, col: int) -> list:
    """找到 (row,col) 观点卡相邻的填充卡，返回 [(type, text), ...]"""
    neighbors = [(row, col - 1), (row, col + 1)]
    if row in (1, 2):
        neighbors.append((3 - row, col))  # row1 ↔ row2 垂直相邻

    fillers = []
    for nr, nc in neighbors:
        if 0 <= nr < 4 and 0 <= nc < 5:
            nid = matrix[nr][nc]
            if nid and nid in cards_data:
                # 归一化后比较：填充卡类型会直接进织入提示词，统一用规范形式
                ntype = normalize_card_type(cards_data[nid].type)
                if ntype in ("情绪", "漏洞", "修辞"):
                    # 动态填充卡的原文不在 article_lib，必须走三级解析
                    ftext = _resolve_card_text(nid, cards_data)
                    if ftext:
                        fillers.append((ntype, ftext))
    return fillers


# ========== 段落蓝图 ==========

def build_blueprint(matrix, structure, cards_data) -> list:
    """
    矩阵位置 + 结构 → 段落蓝图（ParagraphSpec 列表）

    规则：
    - 阅读序：row0 → row1(左→右) → row2(左→右) → row3
    - 每张观点卡 = 一段；首段=开头角色，末段=结尾角色
    - 驳论：row0 的漏洞卡=靶子，单独成开头段
    - 填充卡（情绪/漏洞/修辞）不单独成段，按相邻作用注入观点段
    """
    structure_name = _STRUCTURE_NAME_MAP.get(
        structure.value if isinstance(structure, StructureType) else str(structure),
        "通用",
    )

    # 1. 按阅读序收集观点卡位置
    viewpoint_positions = []  # [(row, col, card_id), ...]
    for row in range(4):
        for col in range(5):
            cid = matrix[row][col]
            if cid and cid in cards_data:
                if normalize_card_type(cards_data[cid].type) == "观点":
                    viewpoint_positions.append((row, col, cid))

    # 2. 驳论特殊处理：row0 漏洞卡作靶子，插到最前
    target_card = None  # (card_id, text)
    if structure_name == "驳论":
        for col in range(5):
            cid = matrix[0][col]
            if cid and cid in cards_data and normalize_card_type(cards_data[cid].type) == "漏洞":
                target_card = (cid, _resolve_card_text(cid, cards_data))
                break

    # 3. 组装段落主卡序列
    #    原文为空的卡在这里就剔除，不留到生成之后再过滤：
    #    ① 段落角色（开头段/结尾段/回扣段）由 is_first/is_last 决定，依赖最终
    #       存活的卡序。事后过滤会让末段角色错位（本该"结尾段"的变成"论述段"）。
    #    ② 空原文的段落 generate_paragraph 必然返回 ""，白耗一次 AI 调用与超时预算。
    main_cards = []  # [(card_id, card_type, card_text, is_target), ...]
    dropped: list = []

    if target_card:
        if target_card[1]:
            main_cards.append((target_card[0], "漏洞", target_card[1], True))
        else:
            dropped.append(target_card[0])

    for (row, col, cid) in viewpoint_positions:
        card_text = _resolve_card_text(cid, cards_data)
        if card_text:
            main_cards.append((cid, "观点", card_text, False))
        else:
            dropped.append(cid)

    if dropped:
        print(f'[article-generator] 剔除 {len(dropped)} 张取不到原文的卡牌: {dropped}')

    if not main_cards:
        return []

    # 驳论的靶子段被剔除后，剩下的观点卡不能再套“破题段”角色。
    # _role_for_position 对驳论结构无条件把首段当破题段，而破题段模板的语义是
    # “先立靶再反驳”——拿观点卡原文去填会语义错位。此时降级按通用结构分角色。
    role_structure = structure_name
    if structure_name == "驳论" and not any(is_t for (*_, is_t) in main_cards):
        role_structure = "通用"
        print('[article-generator] 驳论靶子段缺失，段落角色降级按通用结构分配')

    # 4. 逐段构建 ParagraphSpec
    blueprint = []
    total = len(main_cards)
    for i, (cid, ctype, card_text, is_target) in enumerate(main_cards):
        is_first = (i == 0)
        is_last = (i == total - 1)

        # 靶子段固定用破题段角色
        if is_target:
            role = "破题段"
        else:
            role = _role_for_position(role_structure, is_first, is_last)

        content_type = classify_content_type(card_text)

        # 填充卡依附：靶子段不织入，观点段查相邻
        weave_cards = []
        if not is_target:
            # 找到该观点卡在矩阵中的位置
            pos = next(((r, c) for (r, c, x) in viewpoint_positions if x == cid), None)
            if pos:
                weave_cards = _find_adjacent_fillers(matrix, cards_data, pos[0], pos[1])

        blueprint.append(ParagraphSpec(
            index=i,
            role=role,
            card_id=cid,
            card_text=card_text,
            card_type=ctype,
            content_type=content_type,
            weave_cards=weave_cards,
        ))

    return blueprint


# ========== 输出净化（确定性兜底） ==========

# 模型偶尔会把骨架里的写作指令/占位符/内部术语照抄进成品（如"从卡牌提取核心反驳观点："
# "所以{小结}，""卡牌中提到"），仅靠 prompt 约束压不住随机泄漏，这里用正则做确定性清除。
_SANITIZE_RULES: list = [
    # 骨架指令泄漏：如"从卡牌提取核心反驳观点：" / "从卡牌提取核心反驳观点，"
    (re.compile(r"从?(?:卡牌|卡片|原文|素材)提取[^。！？\n]{0,20}?[：:，,]"), ""),
    # 内部术语元引用：如"卡牌中提到，" / "卡牌里提到" / "卡片显示"
    (re.compile(r"(?:卡牌|卡片|牌面)[里中]?(?:提到|写到|说到|显示|表明|指出|告诉我们)[，,]?"), ""),
    # closing 占位符未填充：如"所以{小结}，" / "所以小结，"
    (re.compile(r"所以\s*\{?小结\}?[，,]"), "所以，"),
    # 任何残留的花括号占位符及其内容
    (re.compile(r"\{[^{}\n]{0,24}\}"), ""),
    # 残留的孤立花括号
    (re.compile(r"[{}]"), ""),
]

def _sanitize_paragraph(text: str) -> str:
    """确定性清除模型照抄的指令文字/占位符/内部术语，保证成品干净"""
    for pattern, repl in _SANITIZE_RULES:
        text = pattern.sub(repl, text)
    # 压缩清除后可能产生的重复标点（如"，，"）
    text = re.sub(r"([，,。；;：:])\1+", r"\1", text)
    return text.strip()


# ========== 单段生成 ==========

def generate_paragraph(spec: ParagraphSpec, structure_name: str, lean: str,
                       length_level: Optional[str] = None) -> str:
    """
    选模板 + 调 AI 生成单段；失败降级为卡牌原文

    Args:
        spec: 段落规格
        structure_name: 模板库结构名（驳论/并列/...）
        lean: emotional/rational/critical
        length_level: 精简/标准/饱满（None 则自动判定）
    """
    if not spec.card_text:
        return ""

    if length_level is None:
        length_level = _determine_length_level(spec.card_text)

    # 1. 选模板
    tpl = select_template(
        role=spec.role,
        structure=structure_name,
        content_type=spec.content_type,
        tone=(lean if lean in ("emotional", "critical") else None),
    )
    if tpl is None:
        return FALLBACK_PARAGRAPH.format(card_text=spec.card_text)
    spec.template_id = tpl.template_id

    # 2. 构建织入文本
    weave_text = "（无）"
    if spec.weave_cards:
        lines = []
        for (ftype, ftext) in spec.weave_cards:
            hint = _WEAVE_ROLE_HINT.get(ftype, "补充")
            # ftype 是规范形式（不带「卡」），提示词里用展示形式拼成「情绪卡」等
            lines.append(f"- {display_card_type(ftype)}（{hint}）：{ftext}")
        weave_text = "\n".join(lines)

    # 3. 构建基调提示
    tone_parts = [STRUCTURE_TONE_SNIPPETS.get(structure_name, "")]
    if lean in LEAN_MODIFIERS:
        tone_parts.append(LEAN_MODIFIERS[lean])
    tone_hint = "；".join(p for p in tone_parts if p)

    # 4. 按档位 + 模板实际槽位动态裁剪骨架（未定义的槽位不注入，避免占位符泄漏）
    sk = tpl.skeleton
    has_evidence = bool(sk.get("evidence"))
    has_mechanism = bool(sk.get("mechanism"))
    use_evidence = has_evidence and length_level in ("标准", "饱满")
    use_mechanism = has_mechanism and length_level == "饱满"

    # 字数档位按实际可用槽位取：无 evidence 的模板（open/close 类）按精简档
    eff_level = length_level if use_evidence else "精简"
    word_range = tpl.word_range.get(eff_level, [40, 120])

    lead_options = json.dumps(sk.get("lead", []), ensure_ascii=False)
    closing_options = json.dumps(sk.get("closing", []), ensure_ascii=False)

    # 动态拼接骨架块：只渲染模板真实拥有且本档启用的槽位
    sk_lines = []
    if lead_options and lead_options != "[]":
        sk_lines.append(f"lead 候选：{lead_options}")
    sk_lines.append(f"claim：{sk.get('claim', '{核心观点}')}")
    if use_evidence:
        sk_lines.append(f"evidence：{sk['evidence']}")
    if use_mechanism:
        sk_lines.append(f"mechanism：{sk['mechanism']}")
    if closing_options and closing_options != "[]":
        sk_lines.append(f"closing 候选：{closing_options}")
    skeleton_block = "\n".join(sk_lines)

    # 5. 填充 user prompt
    user_prompt = GENERATE_PARAGRAPH_USER_TEMPLATE.format(
        skeleton_block=skeleton_block,
        card_text=spec.card_text,
        weave_text=weave_text,
        length_level=eff_level,
        word_min=word_range[0],
        word_max=word_range[1],
        tone_hint=tone_hint,
    )

    # 6. 调 AI
    result = call_tongyi(
        GENERATE_PARAGRAPH_SYSTEM_PROMPT,
        user_prompt,
        max_tokens=_GENERATE_MAX_TOKENS,
        temperature=_GENERATE_TEMPERATURE,
        timeout=TONGYI_TIMEOUT_CHAT,
    )

    # 7. 降级
    if not result or not result.strip():
        return FALLBACK_PARAGRAPH.format(card_text=spec.card_text)
    # 8. 净化：确定性清除模型可能照抄的指令/占位符/内部术语
    return _sanitize_paragraph(result)


# ========== 拼装 ==========

def assemble(paragraphs: list, title: str = "") -> str:
    """按序拼装段落成篇（段落间空行分隔）"""
    valid = [p for p in paragraphs if p and p.strip()]
    body = "\n\n".join(valid)
    if title:
        return f"{title}\n\n{body}"
    return body


# ========== 主入口 ==========

def generate_article(snapshot: dict, title: str = "", use_ai: bool = True) -> dict:
    """
    完整流程：export_snapshot 结果 → 本局文章

    Args:
        snapshot: matrix_vector_system.export_snapshot() 的返回值
                  {matrix, structure, structure_name, vector, cards_data}
        title: 文章标题（可选）
        use_ai: 是否调用 AI（False 时纯拼接，用于 P2 链路测试）

    Returns:
        {
            "title": str,
            "content": str,             # 拼装后的完整文章
            "paragraphs": [str, ...],   # 各段文本
            "structure": str,           # 结构中文名
            "lean": str,                # 基调
            "blueprint": [dict, ...],   # 段落蓝图（含 template_id）
        }
    """
    matrix = snapshot.get("matrix")
    structure = snapshot.get("structure")
    cards_data = snapshot.get("cards_data", {})
    vector = snapshot.get("vector")

    structure_name = _STRUCTURE_NAME_MAP.get(
        structure.value if isinstance(structure, StructureType) else str(structure),
        "通用",
    )
    lean = compute_lean(vector) if vector else "rational"

    # 1. 段落蓝图
    blueprint = build_blueprint(matrix, structure, cards_data)

    # 2. 逐段生成
    if use_ai:
        # 段落之间相互独立，并发生成以缩短总耗时（串行时 = 各段耗时之和，
        # 加长提示词后容易触发前端等待超时）；executor.map 保证结果按 blueprint 原序返回。
        # 预热模板加载器，规避多线程首次并发 load() 的竞争。
        get_template_loader().load()
        max_workers = max(1, min(len(blueprint), _GENERATE_MAX_PARALLEL))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            paragraphs = list(executor.map(
                lambda spec: generate_paragraph(spec, structure_name, lean),
                blueprint,
            ))
    else:
        # P2 纯拼接兜底：卡牌原文 + 织入
        paragraphs = []
        for spec in blueprint:
            spec.template_id = "(pure_concat)"
            paragraphs.append(spec.card_text)

    # 3. 防御性过滤 + 拼装
    #    build_blueprint 已剔除无原文的卡，正常到不了这里；再兜一层是防止
    #    generate_paragraph 被改动后重新引入空段落。
    #    必须 paragraphs 与 blueprint 按同一索引一起剔除——只过滤其中一个会让
    #    响应里两个字段段数对不上，排查时根本无从定位是哪一段丢了。
    valid_pairs = [
        (para, spec) for para, spec in zip(paragraphs, blueprint)
        if para and para.strip()
    ]
    if len(valid_pairs) != len(paragraphs):
        print(f'[article-generator] 过滤空段落: {len(paragraphs)} → {len(valid_pairs)}')
        paragraphs = [para for para, _ in valid_pairs]
        blueprint = [spec for _, spec in valid_pairs]
        # index 是响应字段，剔除后必须重排，否则前端看到的段序会跳号
        for new_index, spec in enumerate(blueprint):
            spec.index = new_index

    content = assemble(paragraphs, title)

    if not content.strip():
        print(f'[article-generator] 警告：文章内容为空（蓝图 {len(blueprint)} 段）')

    return {
        "title": title,
        "content": content,
        "paragraphs": paragraphs,
        "structure": structure_name,
        "lean": lean,
        "blueprint": [
            {
                "index": s.index,
                "role": s.role,
                "card_id": s.card_id,
                "card_type": s.card_type,
                "content_type": s.content_type,
                "template_id": s.template_id,
                "weave_count": len(s.weave_cards),
            }
            for s in blueprint
        ],
    }
