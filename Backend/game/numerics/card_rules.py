"""
卡牌数值规则 · 单一数据源

规则原文见 Backend/article生成规则.md：
    观点卡的|x|&|y|大于30小于37，且两者之差小于5（必须为整数）
    漏洞卡和情绪卡的|x|&|y|大于18小于28，且两者差距小于7（必须为整数）
    修辞卡的x和y必须为正数且大于1.05小于1.60（必须为0.05的倍数，x和y可以不相等）

所有「生成卡牌数值」或「加载卡牌数值」的地方都必须复用本模块，
否则规则口径会在 prompt / 动态卡生成 / 文章加载 / AI 预处理四处各写一份并逐渐漂移
（历史上修辞卡就因此被填成 10-30 的向量量纲，冲垮过全局向量）。

本模块同时是「卡型字面量」的唯一定义处（见 normalize_card_type / display_card_type）：
内部规范形式不带「卡」后缀，协议出口与前端展示才带，两者禁止混用。

本模块不 import 任何项目内模块，可被 game.numerics 与 game.preprocess 安全共用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

# ══════════════════════════════════════════════════════════
#  向量类卡型（观点/漏洞/情绪）
# ══════════════════════════════════════════════════════════

# lo/hi 是 |x|,|y| 的闭区间，由规则的开区间换算成整数集合：
#   观点 >30 且 <37 → 31~36；漏洞/情绪 >18 且 <28 → 19~27
# max_gap 是「严格小于」的差值上限：||x|-|y|| < max_gap
# sign 是象限约定（规则文件未写，但游戏语义强依赖：观点第一象限、漏洞第二、情绪第四）
VECTOR_CARD_RULES: Dict[str, Dict] = {
    "观点": {"lo": 31, "hi": 36, "max_gap": 5, "sign": (+1.0, +1.0)},
    "漏洞": {"lo": 19, "hi": 27, "max_gap": 7, "sign": (-1.0, +1.0)},
    "情绪": {"lo": 19, "hi": 27, "max_gap": 7, "sign": (+1.0, -1.0)},
}


# ══════════════════════════════════════════════════════════
#  修辞卡（相邻乘数，不是向量分量）
# ══════════════════════════════════════════════════════════

RHETORIC_MIN = 1.05    # 开区间下界，1.05 本身不合法
RHETORIC_MAX = 1.60    # 开区间上界，1.60 本身不合法
RHETORIC_STEP = 0.05   # 必须是该值的整数倍
RHETORIC_FALLBACK = (1.30, 1.30)  # 量纲写错时退回的中性乘数（区间中间值）

# 轻微越界（取到端点 1.05/1.60、或 1.7 这类小偏差）→ 就近钳进区间；
# 超出此带宽（如 12、29、-15）→ 判定为量纲写错，直接退回中性值
RHETORIC_SLIGHT_BAND = (0.80, 2.00)


# ══════════════════════════════════════════════════════════
#  卡型字面量（内部规范形式 vs 协议展示形式）
# ══════════════════════════════════════════════════════════

# 四种卡型的内部规范字面量，一律不带「卡」后缀。
# 依据：article_lib/*.json 的 linespots.card_type、VECTOR_CARD_RULES 的键、
# 动态卡 ID 里持久化的 type_short（{article}_dynamic_{type}_{hash}_{ts}）、
# _reconstruct_dynamic_card 的降级向量表，全部用这一形式。
CARD_TYPES: Tuple[str, ...] = ("观点", "情绪", "漏洞", "修辞")


def normalize_card_type(card_type: str) -> str:
    """归一化卡型字面量 → 内部规范形式（不带「卡」后缀）

    任何卡型比较都必须先过本函数，禁止直接 == 原始字符串。
    历史上同一枚举在不同子系统期望相反：已删除的创作流模块
    （recipe_system / compose_engine）的 allowed_types 用带「卡」写法，
    而 matrix_vector_system / article_generator 的相邻增益与驳论判定用
    不带「卡」写法（仅观点卡做了双写容错），导致带后缀的数据静默丢失
    修辞增益、情绪/漏洞相邻反应与驳论结构判定。
    那套模块删掉后，带「卡」写法只剩协议出口（display_card_type）一个来源，
    但入口归一化仍然必须保留：前端请求体与历史文章 JSON 两种写法都还在传。
    """
    return str(card_type or "").replace("卡", "").strip()


def display_card_type(card_type: str) -> str:
    """转成协议 / 展示形式（带「卡」后缀）

    只用于 HTTP 响应体与前端展示。前端 CardType 联合类型、卡牌资源键
    （data/cardAssets.ts）、成就与事件文案、CSS [data-type] 选择器全部依赖
    带「卡」的写法，因此协议出口必须加回后缀。
    内部逻辑严禁拿本函数的返回值做比较——那会重新制造分裂。
    """
    t = normalize_card_type(card_type)
    return f"{t}卡" if t else ""


def is_known_card_type(card_type: str) -> bool:
    """是否四种已知卡型之一（归一化后判定）"""
    return normalize_card_type(card_type) in CARD_TYPES


# ══════════════════════════════════════════════════════════
#  校验
# ══════════════════════════════════════════════════════════

def validate_card_vector(card_type: str, x: float, y: float) -> List[str]:
    """按规则校验一张卡的数值，返回问题列表（空列表 = 合规）"""
    problems: List[str] = []
    t = normalize_card_type(card_type)

    if t == "修辞":
        for name, raw in (("x", x), ("y", y)):
            v = float(raw)
            if not (RHETORIC_MIN < v < RHETORIC_MAX):
                problems.append(f"{name}={v} 不在开区间 (1.05,1.60)")
                continue
            if abs(v / RHETORIC_STEP - round(v / RHETORIC_STEP)) > 1e-9:
                problems.append(f"{name}={v} 不是 {RHETORIC_STEP} 的整数倍")
        return problems

    rule = VECTOR_CARD_RULES.get(t)
    if rule is None:
        return [f"未知卡型 {card_type!r}"]

    lo, hi, max_gap = rule["lo"], rule["hi"], rule["max_gap"]
    if float(x) != int(x) or float(y) != int(y):
        problems.append(f"({x},{y}) 必须是整数")
    for name, raw in (("x", x), ("y", y)):
        if not (lo <= abs(float(raw)) <= hi):
            problems.append(f"|{name}|={abs(float(raw))} 不在 [{lo},{hi}]")
    if abs(abs(float(x)) - abs(float(y))) >= max_gap:
        problems.append(f"||x|-|y||={abs(abs(float(x)) - abs(float(y)))} 应 <{max_gap}")
    sx, sy = rule["sign"]
    if (float(x) > 0) != (sx > 0) or (float(y) > 0) != (sy > 0):
        problems.append(f"符号应为 ({'+' if sx > 0 else '-'},{'+' if sy > 0 else '-'})")
    return problems


# ══════════════════════════════════════════════════════════
#  钳制（就近投影，保留相对强弱）
# ══════════════════════════════════════════════════════════

def clamp_rhetoric_multiplier(x: float, y: float) -> Tuple[float, float]:
    """把修辞卡乘数收敛到合规区间

    - 轻微越界（落在 SLIGHT_BAND 内，如端点 1.05/1.60 或 1.7）→ 吸附到最近的合法网格值
    - 明显越界（量纲写错，如 12/29/-15）→ 退回中性乘数，而不是钳到边界
      （钳到 1.55 等于给脏数据最大增益）
    """
    lo_band, hi_band = RHETORIC_SLIGHT_BAND
    sanitized: List[float] = []
    for v in (float(x), float(y)):
        snapped = round(round(v / RHETORIC_STEP) * RHETORIC_STEP, 2)  # 就近吸附到网格
        if RHETORIC_MIN < snapped < RHETORIC_MAX:
            sanitized.append(snapped)
            continue
        if lo_band <= v <= hi_band:
            # 端点或小偏差：往区间内推一格
            snapped = (RHETORIC_MAX - RHETORIC_STEP) if snapped >= RHETORIC_MAX \
                else (RHETORIC_MIN + RHETORIC_STEP)
            sanitized.append(round(snapped, 2))
        else:
            return RHETORIC_FALLBACK
    return sanitized[0], sanitized[1]


def clamp_card_vector(card_type: str, x: float, y: float) -> Tuple[float, float]:
    """把任意卡型的数值就近钳到合规区间

    策略是「就近投影」而不是随机重配：原值越大钳完仍越大，
    卡牌之间的相对强弱与 AI 的标注意图得以保留。
    修辞卡走乘数逻辑，未知卡型原样返回（不做臆测）。
    """
    t = normalize_card_type(card_type)
    if t == "修辞":
        return clamp_rhetoric_multiplier(x, y)

    rule = VECTOR_CARD_RULES.get(t)
    if rule is None:
        return float(x), float(y)

    lo, hi, max_gap = rule["lo"], rule["hi"], rule["max_gap"]
    ax = min(max(abs(float(x)), lo), hi)
    ay = min(max(abs(float(y)), lo), hi)

    if abs(ax - ay) >= max_gap:
        # 差值超限：以较大者为基准，把较小者抬到 max_gap-1 以内
        if ax >= ay:
            ay = ax - (max_gap - 1)
        else:
            ax = ay - (max_gap - 1)
        # 抬完可能掉出下界，此时贴下界并把另一个压到允许的最近值
        if ax < lo:
            ax, ay = float(lo), float(min(lo + max_gap - 1, hi))
        elif ay < lo:
            ax, ay = float(min(lo + max_gap - 1, hi)), float(lo)

    sx, sy = rule["sign"]
    return sx * ax, sy * ay


# ══════════════════════════════════════════════════════════
#  本地关键词分类器（不调 AI）
# ══════════════════════════════════════════════════════════
#
# 这里原本有两份逐字重复的实现：api._classify_card_type（回卡型+属性+向量）
# 与 hint_service._classify_card_type_simple（只回卡型）。两者的关键词池与
# 优先级瀑布完全相同，只差返回值；任何一侧改了阈值就会出现「看山提示这里
# 藏着情绪卡，玩家划出来却是观点卡」的矛盾。现在只保留一份。
#
# 【已知缺陷，刻意未修】关键词池里的高频单字（个 / 比 / 度 / 太 / 真 /
# 像 / 如 / 般）在中文里命中率极高，实测 13 种玩家划法里 12 种落到同一个
# 默认分支（观点 / value=12 / (32,32)），几乎无区分度。修它要改阈值与池子，
# 属于行为变更，连带需重新标定动态卡数值与评级阈值，故本轮只做合并。
# 下面的用例把现有输出逐字锁定，将来真要修时能一眼看到改了哪些分支。


@dataclass(frozen=True)
class CardClassification:
    """一次本地判型的结果

    card_type 是内部规范形式（不带「卡」），进协议响应体前由调用方用
    display_card_type 转展示形式。vector_x/y 的量纲跟着卡型走：修辞卡是
    相邻乘数（1.05~1.60），其余三种是整数向量。
    """

    card_type: str
    attribute_value: int
    vector_x: float
    vector_y: float


# 关键词池。顺序与两份旧实现逐字一致（命中计数只看“是否包含”，不看顺序，
# 但保持原序才能跟旧实现逐字对照）。
CLASSIFY_KEYWORD_POOLS: Dict[str, Tuple[str, ...]] = {
    "data": ("%", "％", "万", "亿", "千", "百", "十", "个", "次", "率", "度", "比"),
    "logic": ("因为", "所以", "导致", "因此", "从而", "使得", "原因", "结果", "影响"),
    "contrast": ("但是", "然而", "不过", "可是", "却", "反而", "尽管", "虽然"),
    "emotion": ("！", "？", "太", "真", "非常", "特别", "简直", "令人", "让人"),
    "metaphor": ("像", "如", "仿佛", "犹如", "好似", "如同", "般", "似的"),
}

# 选区短于此长度就直接走默认分支（两份旧实现都是 5）
CLASSIFY_MIN_TEXT_LEN = 5


def _count_pool_hits(text: str, pool: Tuple[str, ...]) -> int:
    """统计一个关键词池里有多少个词出现在 text 中（每词最多计一次）"""
    return sum(1 for kw in pool if kw in text)


def classify_card(text: str) -> CardClassification:
    """根据文本内容分类卡牌类型并计算数值（本地规则，不调 AI）

    分类优先级（从高到低）：
        1. 数据类 → 观点卡（强证据）
        2. 逻辑词 → 观点卡（因果推理）
        3. 转折词且无因果词 → 漏洞卡（逻辑跳跃）
        4. 情感词 → 情绪卡（共鸣表达）
        5. 比喻词 → 修辞卡（文学性）
        6. 默认 → 观点卡（一般论述）

    【量纲约束】所有返回值必须符合本模块顶部的规则（即
    Backend/article生成规则.md）：观点 31~36 且差 <5；漏洞/情绪 19~27 且差 <7；
    修辞 x,y ∈ (1.05,1.60) 且为 0.05 的整数倍（相邻乘数，不是向量）。
    动态卡不得强于预设卡，否则玩家“乱划”比“精准命中”更划算。
    """
    if not text or len(text.strip()) < CLASSIFY_MIN_TEXT_LEN:
        return CardClassification("观点", 10, 31.0, 31.0)

    data_count = _count_pool_hits(text, CLASSIFY_KEYWORD_POOLS["data"])
    logic_count = _count_pool_hits(text, CLASSIFY_KEYWORD_POOLS["logic"])
    contrast_count = _count_pool_hits(text, CLASSIFY_KEYWORD_POOLS["contrast"])
    emotion_count = _count_pool_hits(text, CLASSIFY_KEYWORD_POOLS["emotion"])
    metaphor_count = _count_pool_hits(text, CLASSIFY_KEYWORD_POOLS["metaphor"])

    if data_count >= 2:
        # 数据密集 → 强观点（观点卡上限 36，差 1 < 5）
        return CardClassification("观点", min(20, 15 + data_count), 36.0, 35.0)

    if logic_count >= 2:
        # 逻辑推理 → 标准观点（中档，差 1 < 5）
        return CardClassification("观点", min(19, 14 + logic_count), 34.0, 33.0)

    if contrast_count >= 1 and logic_count == 0:
        # 有转折无因果 → 可能是漏洞
        return CardClassification("漏洞", min(17, 12 + contrast_count * 2), -25.0, 25.0)

    if emotion_count >= 2:
        # 情感强烈 → 情绪卡（|x|,|y| 必须落在 19~27，差 1 < 7）
        return CardClassification("情绪", min(18, 13 + emotion_count), 26.0, -25.0)

    if metaphor_count >= 1:
        # 有比喻 → 修辞卡
        return CardClassification("修辞", min(16, 11 + metaphor_count * 2), 1.25, 1.35)

    # 默认：一般观点
    return CardClassification("观点", 12, 32.0, 32.0)
