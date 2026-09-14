"""
动态划线判定服务 · POST /api/cards/dynamic 的纯逻辑层

玩家随手划的线经常没头没尾，本地关键词分类器对这类碎片几乎没有区分度
（实测 13 种真实划法里 12 种都判成「观点/value=12/(32,32)」）。本模块在此之上
叠一层 AI 判定，但**AI 不是关键路径，只是增益层**——所有 AI 可能失败的地方都有
本地兜底，且兜底结果严格优于引入 AI 之前的现状。

三条设计红线（改之前先读完）：

① AI 不报偏移量。LLM 数不准中文字符索引，且错得隐蔽：偏 3 个字肉眼看不出来，
   但 content[start:end] 已经残缺。改为让 AI 返 selected_text，后端用
   locate_in_content() 在限定窗口内回查真实偏移量。

② AI 不报数值。修辞卡那两个值是「相邻乘数」(1.05,1.60)，其余三类是「向量分量」
   （19~36 的整数），同一字段名承载两种量纲。历史上 AI 预处理把 13 张修辞卡填成
   10-30 量纲，相邻观点卡的行贡献从 (72,55) 被冲到 (576,1276)。数值一律由
   card_rules 派生 + clamp，AI 即使违规输出了数值字段也会被显式忽略。

③ 句边界扩展不交给 AI。expand_to_sentence_boundary() 是确定性字符串算法，
   本地 0ms、100% 准确、永不失败。三条成功路径（L4/L5/L6）全部强制经过它——
   不扩边的话卡牌文本会是半句话，进文章生成后段落读起来就是断的。

降级阶梯（L0 由 /api/judge 负责，本模块从 L1 开始）：
    L1  长度非法 / 纯标点 / 纯数字 / 灌水重复  → 拒，不调 AI
    L2  同一篇文章里同样的文本已经建过卡        → 拒，不调 AI（省成本）
    L3  本局配额已满                            → 拒，不调 AI
    L4  AI 成功 + 回查成功  → AI 选文 + 句边界扩展 + AI 判型
    L5  AI 成功 + 回查失败  → 原选区 + 句边界扩展 + AI 判型
    L6  AI 失败（超时/None/JSON 解析失败/未知卡型）→ 原选区 + 句边界扩展 + 本地判型
    AI 明确判 valid=false  → 拒（这是 AI 的正常产出，不算失败）
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from game.api.ai_service import call_tongyi
from game.api.dynamic_card_store import find_card_id_by_hash
from game.api.llm_config import (
    DYNAMIC_CARD_MAX_TOKENS,
    DYNAMIC_CARD_TEMPERATURE,
    TONGYI_MODEL_DYNAMIC_CARD,
    TONGYI_TIMEOUT_DYNAMIC_CARD,
)
from game.api.llm_prompt import (
    DYNAMIC_CARD_SYSTEM_PROMPT,
    DYNAMIC_CARD_USER_PROMPT_TEMPLATE,
)
from game.numerics.card_rules import (
    RHETORIC_FALLBACK,
    VECTOR_CARD_RULES,
    clamp_card_vector,
    is_known_card_type,
    normalize_card_type,
)

# 本地分类器的签名：text -> (card_type, attribute_value, vector_x, vector_y)
# 用注入而不是直接 import api._classify_card_type：api.py 顶层 import 本模块，
# 反向 import 会形成循环（同 matrix_vector_system 里延迟 import session 的处境）。
Classifier = Callable[[str], Tuple[str, int, float, float]]


# ══════════════════════════════════════════════════════════
#  拒绝文案 —— 全部复用现成字符串，本模块不自创文案
# ══════════════════════════════════════════════════════════
#
# 前端 ArticlePanel.vue 的 miss 分支已经是 `result.message || '未发现有效素材'`，
# 且无条件调 triggerJudgeFail() 弹看山气泡。所以后端填什么 message 前端就显示什么，
# 这条链路前端一行都不用改。以下三条与现有出处逐字一致，改这里等于改前端显示。

MSG_TOO_SHORT_OR_LONG = "选区过短或过长，请重新划线"   # = api.py /api/judge 的长度门槛
MSG_NO_MATERIAL = "未发现有效素材"                     # = ArticlePanel.vue 的兜底文案
MSG_DUPLICATED = "该素材已经收集"                      # = ArticlePanel.vue 的重复收集提示


# ══════════════════════════════════════════════════════════
#  门槛与窗口常量
# ══════════════════════════════════════════════════════════

MIN_CARD_TEXT = 5           # 与 /api/judge 现有的长度门槛一致

# 玩家能划多长（L1 入参门槛）。比 /api/judge 的 200 宽，这是本端点独有的：
# 新端点有 AI 能力，长选区交给 AI 收敛出 10-120 字的核心句，而不是直接拒掉。
# /api/judge 的 200（api.py 里的硬编码字面量）刻意不动：那边没有 AI，
# 放宽就等于允许直接拿整段当卡牌。
MAX_SELECTION_TEXT = 350

# 产出卡文本的硬上限，也是句边界扩展后的总长上限。
# 与 MAX_SELECTION_TEXT 刻意分开：放宽入参是为了让 AI 有机会收敛长选区，
# 而不是为了产出更长的卡。卡牌文本会直接进局末文章生成的段落，
# 一张 350 字的卡会把整个段落占满，所以产出上限继续卡在 200。
MAX_CARD_TEXT = 200

# 句边界扩展的单侧上限。不设限的话，选区落在一个没有句号的长段落中间时会一路
# 扩到段首，把 20 字的划线变成 300 字的整段，卡牌语义反而被稀释。
MAX_EXPAND_PER_SIDE = 80

# selected_text 回查窗口（选区 ± 此值）。比 MAX_EXPAND_PER_SIDE 宽，是给 AI
# 留的容错余量：prompt 里要求「单侧不要超出 80 字」，但模型不总听话。
# 落在窗口外的匹配一律不采信——AI 可能引到了文章另一处的同句，
# 错位标注（高亮跳到别处）比降级更难排查。
LOOKUP_WINDOW = 200

# 传给 AI 的上下文长度上限。短文传全文（判「反常识结论」这类判据需要主旨），
# 超长文以选区为中心截窗口，避免拖垮 15s 后端预算。
MAX_CONTEXT_CHARS = 6000

# 句末标点。中英文都收，\n 也算——段落边界天然是句边界。
_SENTENCE_ENDINGS = "。！？；!?;\n"

# 「有意义的字符」= 汉字或拉丁字母。纯数字/纯标点的选区没有任何语义，
# 但本地分类器的默认分支会给它一张观点卡，这类卡进文章生成只会产出空泛段落。
_MEANINGFUL_CHAR = re.compile(r"[\u4e00-\u9fffA-Za-z]")


# ══════════════════════════════════════════════════════════
#  JSON 净化
# ══════════════════════════════════════════════════════════
#
# 这是该接口**最常见**的失败模式（比超时更频繁）：模型包 ```json 围栏、
# 在 JSON 前后夹自然语言、留尾逗号、用单引号。所以净化必须做到位。
#
# ai_service._parse_story_json 已有围栏剥离，但它只认数组 [ ... ]（剧情是句子列表），
# 动态卡要的是单个对象。围栏剥离的思路沿用它，对象抽取与容错是本模块自己实现的。

_FENCE_HEAD = re.compile(r"^```[a-zA-Z]*\s*")
_FENCE_TAIL = re.compile(r"\s*```$")
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")
_SINGLE_QUOTED = re.compile(r"'([^']*)'")


def _dequote(candidate: str) -> str:
    """把单引号 JSON 转成双引号（最后一道，可能误伤英文撇号，故只在前面都失败后试）"""
    return _SINGLE_QUOTED.sub(
        lambda m: '"' + m.group(1).replace('"', '\\"') + '"',
        candidate,
    )


# 字符串边界引号的外侧必须是结构字符。真机实测：article_3 里有
# 「他们把精力都花在了"想"上，而不是"做"上」，AI 摘录时把英文双引号原样
# 抄进 JSON 而没转义，字符串在「花在了」后就提前结束。用这个启发式区分：
# 引号外侧是汉字的一律当字符串内容（中文原文里不会出现 `",` `":` 这种序列）。
#
# _extract_first_object 与 _escape_inner_quotes 共用这两个常量：两处必须对
# 「什么是字符串边界」给出同一个答案，否则提取阶段认为平衡、解析阶段又失败。
_STRUCT_BEFORE_OPEN = "{[:,"
_STRUCT_AFTER_CLOSE = ",}]:"


def _next_non_space(text: str, index: int) -> str:
    """index 之后第一个非空白字符，没有则返回空串

    不用 text[index + 1:].lstrip()：那是 O(n) 切片，放在逐字符循环里
    会把整个扫描变成 O(n²)。AI 返回的 JSON 可能几 KB，不值得。
    """
    for position in range(index + 1, len(text)):
        if not text[position].isspace():
            return text[position]
    return ""


def _extract_first_object(text: str) -> Optional[str]:
    """扫描出第一个括号平衡的 {...}，正确跳过字符串字面量内的括号与转义

    不能用 find("{") + rfind("}") 凑合：AI 常在 JSON 后面追一句
    「以上是判定结果}」这类自然语言，rfind 会把右边界吃到错误位置。

    字符串边界靠 _STRUCT_* 启发式判，不是见到 " 就翻转状态。这是实测逼出来的：
    AI 把原文里的裸引号抄进来时，内部引号个数为**奇数**会让朴素状态机错位
    ——`"他说"走", "reason": "感叹"}` 里最后的 } 被当成字符串内容跳过，
    depth 永远回不到 0，整条响应在**提取阶段**就被丢弃，后面四级净化根本没
    机会跑。偶数个引号时进出抵消，反而能侥幸提取成功（真机那次就是）。
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    prev_char = ""          # 上一个非空白字符，判断引号是不是字符串起始
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                # 后面不是结构字符 → 这是字符串内容里的裸引号，不结束字符串
                following = _next_non_space(text, index)
                if not following or following in _STRUCT_AFTER_CLOSE:
                    in_string = False
        elif char == '"':
            if not prev_char or prev_char in _STRUCT_BEFORE_OPEN:
                in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
        if not char.isspace():
            prev_char = char
    return None  # 括号不平衡，多半是被 max_tokens 截断了


def _escape_inner_quotes(candidate: str) -> str:
    """给字符串值内部未转义的裸双引号补上转义

    实测缺陷（真机联调复现，不是推测）：
        "selected_text": "...他们把精力都花在了"想"上，而不是"做"上。"
    json.loads 报 Expecting ',' delimiter: line 1 column 84，前三级净化全部
    失败 → 降级 L6。后果是玩家只要划到含英文引号的段落就必然失去 AI 判型
    能力，而文章库里这类内容不少见，属于高频降级路径。

    通用做法无法区分「字符串内的引号」与「边界引号」，但这里有个可用的
    启发式：**真边界引号的外侧一定是结构字符**——起始引号前（跳过空白）
    是 { [ , : 之一，结束引号后是 , } ] : 之一。不满足的就是字符串内容，补转义。

    误判只会退回现状（解析失败降级），不会比现在更糟，所以这一级是安全的。
    """
    out: List[str] = []
    in_string = False
    escaped = False
    prev_char = ""          # 上一个非空白字符，避开 candidate[:index] 的 O(n²) 切片

    for index, char in enumerate(candidate):
        if not in_string:
            # 外侧不是结构字符的引号当普通字符，不开字符串
            if char == '"' and (not prev_char or prev_char in _STRUCT_BEFORE_OPEN):
                in_string = True
            out.append(char)
        elif escaped:
            escaped = False
            out.append(char)
        elif char == "\\":
            escaped = True
            out.append(char)
        elif char == '"':
            following = _next_non_space(candidate, index)
            if not following or following in _STRUCT_AFTER_CLOSE:
                in_string = False      # 真边界，或已到末尾
                out.append(char)
            else:
                out.append('\\"')      # 字符串内部的裸引号，补转义
        else:
            out.append(char)

        if not char.isspace():
            prev_char = char

    return "".join(out)


def parse_card_json(raw: str) -> Optional[dict]:
    """宽容解析 AI 返回的 JSON 对象；彻底失败返回 None（调用方降级到本地判定）"""
    if not raw or not raw.strip():
        return None

    text = raw.strip()
    if text.startswith("```"):
        text = _FENCE_TAIL.sub("", _FENCE_HEAD.sub("", text)).strip()

    candidate = _extract_first_object(text)
    if candidate is None:
        print(f"[dynamic-card] AI 输出里找不到 JSON 对象: {text[:80]!r}")
        return None

    # 四级递进：原文 → 去尾逗号 → 单引号转正 → 补转义字符串内部的裸引号。
    # 每级都只在上一级失败后才试，因为越往后的修正越激进（_dequote 会误伤
    # 文本里的撇号，_escape_inner_quotes 会改动字符串内容）。
    # 第四级用原始 candidate 而不是上一级的产物：两个修正目标互斥，
    # 叠加只会让误伤面变大。
    #
    # strict=False 不是可选的：AI 摘录中文原文时，selected_text 经常直接带上文章里的
    # 裸换行/制表符而没有转义成 \n，strict 模式会以 "Invalid control character"
    # 判死整条响应，白白把一次本来可用的 AI 判定降级到 L6。
    for attempt, payload in enumerate((
        candidate,
        _TRAILING_COMMA.sub(r"\1", candidate),
        _dequote(candidate),
        _escape_inner_quotes(candidate),
    )):
        try:
            parsed = json.loads(payload, strict=False)
        except (json.JSONDecodeError, ValueError) as exc:
            if attempt == 3:
                print(f"[dynamic-card] JSON 四级解析均失败: {exc}; 原文: {candidate[:120]!r}")
            continue
        if isinstance(parsed, dict):
            return parsed
        print(f"[dynamic-card] JSON 解析出的不是对象: {type(parsed).__name__}")
        return None
    return None


# ══════════════════════════════════════════════════════════
#  句边界扩展（确定性算法，三条成功路径强制经过）
# ══════════════════════════════════════════════════════════

def expand_to_sentence_boundary(content: str, start: int, end: int) -> Tuple[int, int]:
    """把 [start, end) 向两侧扩到完整句边界，返回新的 [start, end)

    预算分配是「先向右吃到句末标点，再向左退到句首标点之后」，顺序刻意如此：
    「无尾」（半句话被切断）比「无头」更伤可读性，选区本身已接近产出上限时，
    剩余预算优先保证句末完整。

    永不抛异常：入参会先钳进 [0, len(content)]，扩不动就原样返回。
    """
    total = len(content)
    start = max(0, min(start, total))
    end = max(start, min(end, total))
    if start == end:
        return start, end

    # ── 向右：吃到本句的句末标点（含标点本身） ──
    right_limit = min(total, end + MAX_EXPAND_PER_SIDE)
    right = end
    # end 已经含句末标点（玩家正好划到句号）时本句已完整，不能再向右扫——
    # 否则扫描会从下一句的首字开始，一路吃到下个句号，卡牌文本变成两句话。
    if not (end > 0 and content[end - 1] in _SENTENCE_ENDINGS):
        while right < right_limit and content[right] not in _SENTENCE_ENDINGS:
            right += 1
        if right < right_limit:
            right += 1

    # ── 向左：退到上一句句末标点之后（start 本就在句首则不动） ──
    left_limit = max(0, start - MAX_EXPAND_PER_SIDE)
    left = start
    while left > left_limit and content[left - 1] not in _SENTENCE_ENDINGS:
        left -= 1

    # ── 缩掉扩进来的首尾空白（段落换行、缩进） ──
    span = content[left:right]
    lead = len(span) - len(span.lstrip())
    trail = len(span.rstrip())
    left, right = left + lead, left + trail
    if left >= right:
        return start, end

    # ── 总长钳制：先弃左扩展，再弃右扩展，都保不住就截断原选区 ──
    if right - left > MAX_CARD_TEXT:
        if right - start <= MAX_CARD_TEXT:
            left = start
        elif end - left <= MAX_CARD_TEXT:
            right = end
        else:
            # 原选区本身就超过产出上限。入参门槛放宽到 MAX_SELECTION_TEXT(350)
            # 之后这条路必然会走到：AI 降级（L5/L6）时拿玩家原选区扩边，
            # 而原选区可能长达 350 字。原样返回会让一张 350 字的卡进文章生成。
            return _truncate_to_card_limit(content, start)
    return left, right


def _truncate_to_card_limit(content: str, start: int) -> Tuple[int, int]:
    """原选区超过 MAX_CARD_TEXT 时，从选区起点截取并在句末标点处收口

    保头弃尾是刻意的：玩家划线的起点通常是他真正想强调的开头，
    AI 收敛核心句时也倾向选区前部，两边口径一致。

    收口优先落在句末标点上，避免把句子拦腰砍断；但收口后不足
    MIN_CARD_TEXT 时宁可硬截保住长度——降级路径本就是尽力而为，
    若因选区开头正好是个残句尾而让整张卡被后面的门槛拒掉，
    玩家等于白划一次，比砍断句子更糟。
    """
    cut = min(len(content), start + MAX_CARD_TEXT)
    for index in range(cut - 1, start, -1):
        if content[index] in _SENTENCE_ENDINGS:
            if index + 1 - start >= MIN_CARD_TEXT:
                return start, index + 1
            break
    return start, cut


def _strip_whitespace(text: str) -> Tuple[str, list[int]]:
    """去掉所有空白字符，并记下每个保留字符在原串里的下标

    返回 (compressed, mapping)，mapping[i] 是 compressed[i] 在 text 里的原始下标。
    """
    chars: list[str] = []
    mapping: list[int] = []
    for index, char in enumerate(text):
        if char.isspace():
            continue
        chars.append(char)
        mapping.append(index)
    return "".join(chars), mapping


def locate_in_content(
    content: str,
    selected_text: str,
    start: int,
    end: int,
) -> Optional[Tuple[int, int]]:
    """把 AI 返回的 selected_text 回查成原文的 [起, 止) 区间；查不到返回 None

    两级匹配：先精确 find（绝大多数情况），失败再做空白不敏感匹配。

    第二级不是宽容，是必需：真机联调实测 AI 摘录跨行句子时会把 \n 丢掉
    （原文「正相关。\n和成本无关」被摘成「正相关。和成本无关」），精确匹配
    必然失败，白白把一次完全可用的 AI 判定降级到 L5。提示词里写「一个字都不能改」
    拦不住这件事：换行是不可见字符，模型没有遵守它的动机，只能后端做确定性归一。

    返回区间而不是单个起始偏移，也是因为空白不敏感匹配下
    len(selected_text) != 原文跨度（原文多出被丢掉的空白），
    调用方拿 len() 自己算结束位置会偏短。

    只在选区 ± LOOKUP_WINDOW 的窗口内找。窗口外即使能找到也不采信：
    AI 可能引到了文章另一处的相同句子，那样标注会跳到错误位置，
    而错位高亮比降级到本地扩边更难排查。
    """
    needle = (selected_text or "").strip()
    if not needle:
        return None

    window_start = max(0, start - LOOKUP_WINDOW)
    window_end = min(len(content), end + LOOKUP_WINDOW)

    found = content.find(needle, window_start, window_end)
    if found != -1:
        return found, found + len(needle)

    # ── 第二级：空白不敏感匹配 ──
    compressed_window, mapping = _strip_whitespace(content[window_start:window_end])
    compressed_needle, _ = _strip_whitespace(needle)
    if compressed_needle:
        hit = compressed_window.find(compressed_needle)
        if hit != -1:
            # mapping 把压缩下标翻回窗口内下标，再加 window_start 翻回全文下标。
            # 止偏移取最后一个非空白字符的下标 +1：句末标点本身被包含在内，
            # expand_to_sentence_boundary 看到 content[end-1] 是句号就不会再向右扩。
            located_start = window_start + mapping[hit]
            located_end = window_start + mapping[hit + len(compressed_needle) - 1] + 1
            print(f"[dynamic-card] selected_text 精确匹配失败，空白不敏感匹配命中 "
                  f"[{located_start},{located_end})（AI 丢了空白字符）")
            return located_start, located_end

    print(f"[dynamic-card] selected_text 未落在窗口 [{window_start},{window_end}) 内，"
          f"降级本地扩边: {needle[:40]!r}")
    return None


def build_context(content: str, start: int, end: int) -> str:
    """给 AI 的上下文：短文传全文，超长文以选区为中心截窗口并加省略标记"""
    if len(content) <= MAX_CONTEXT_CHARS:
        return content

    half = MAX_CONTEXT_CHARS // 2
    middle = (start + end) // 2
    high = min(len(content), max(0, middle - half) + MAX_CONTEXT_CHARS)
    low = max(0, high - MAX_CONTEXT_CHARS)
    prefix = "……" if low > 0 else ""
    suffix = "……" if high < len(content) else ""
    return f"{prefix}{content[low:high]}{suffix}"


# ══════════════════════════════════════════════════════════
#  AI 判定
# ══════════════════════════════════════════════════════════

@dataclass
class AiVerdict:
    """AI 的判定结果——只有判型与选文，没有任何数值"""
    valid: bool
    card_type: str = ""       # 内部规范形式（不带「卡」）
    selected_text: str = ""
    reason: str = ""


def ai_judge_selection(
    content: str,
    selection: str,
    start: int,
    end: int,
) -> Optional[AiVerdict]:
    """调 AI 判型与选文

    返回 None 表示「AI 这条路走不通」（超时 / 返回 None / JSON 解析失败 /
    未知卡型 / valid 却没给 selected_text），调用方应降级到 L6 本地判定。
    返回 valid=False 的 AiVerdict 表示「AI 正常判定为无要点」，这不是失败，
    应当直接拒绝建卡。两者语义不同，调用方必须分开处理。
    """
    prompt = DYNAMIC_CARD_USER_PROMPT_TEMPLATE.format(
        context=build_context(content, start, end),
        selection=selection,
        start=start,
        end=end,
    )
    raw = call_tongyi(
        DYNAMIC_CARD_SYSTEM_PROMPT,
        prompt,
        model=TONGYI_MODEL_DYNAMIC_CARD,
        max_tokens=DYNAMIC_CARD_MAX_TOKENS,
        temperature=DYNAMIC_CARD_TEMPERATURE,
        timeout=TONGYI_TIMEOUT_DYNAMIC_CARD,
    )
    if raw is None:
        print("[dynamic-card] call_tongyi 返回 None（超时/网络/额度），降级本地判定")
        return None

    parsed = parse_card_json(raw)
    if parsed is None:
        return None

    reason = str(parsed.get("reason") or "")
    if not parsed.get("valid"):
        return AiVerdict(valid=False, reason=reason)

    card_type = normalize_card_type(parsed.get("card_type", ""))
    if not is_known_card_type(card_type):
        print(f"[dynamic-card] AI 返回未知卡型 {parsed.get('card_type')!r}，降级本地判定")
        return None

    selected_text = str(parsed.get("selected_text") or "").strip()
    if not selected_text:
        print("[dynamic-card] AI 判 valid 但 selected_text 为空，降级本地判定")
        return None

    # 显式忽略 AI 可能违规输出的数值字段（红线②）
    ignored = [k for k in ("vector_x", "vector_y", "attribute_value", "start", "end")
               if k in parsed]
    if ignored:
        print(f"[dynamic-card] 已忽略 AI 输出的数值字段: {ignored}")

    return AiVerdict(valid=True, card_type=card_type,
                     selected_text=selected_text, reason=reason)


def mid_vector_for_type(card_type: str) -> Tuple[float, float]:
    """按 card_rules 的单一数据源派生该型别的中性数值

    只在「AI 判型与本地分类器不一致」时用：此时本地算出的向量属于另一个型别，
    量纲可能完全不同（修辞是乘数、其余是整数向量），必须整个换掉。
    取该型区间的中值再过一次 clamp 兜底。

    刻意不在这里硬编码向量表——那会是 card_rules 之外的第五份规则口径
    （历史上规则口径在四处各写一份，直接导致过 96 张卡量纲违规）。
    matrix_vector_system._reconstruct_dynamic_card 里那张降级表语义不同：
    它是「落盘丢失的过期卡」的保守值，已被测试锁定，不要合并过来。
    """
    normalized = normalize_card_type(card_type)
    if normalized == "修辞":
        return RHETORIC_FALLBACK

    rule = VECTOR_CARD_RULES.get(normalized)
    if rule is None:
        return (0.0, 0.0)
    # 整除取中值：VECTOR_CARD_RULES 要求整数分量，(31+36)/2=33.5 会违规
    middle = (rule["lo"] + rule["hi"]) // 2
    return clamp_card_vector(
        normalized,
        rule["sign"][0] * middle,
        rule["sign"][1] * middle,
    )


def compute_text_hash(text: str) -> str:
    """卡牌文本 hash，必须与 api._generate_dynamic_card 内联的算法逐字一致

    两处实现是重复的（那边内联 hashlib，这边为了做 L2 去重也要算），
    已有测试锁定两者产出相同。后续若重构，应让 api.py 改为调本函数。
    """
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:8]


# ══════════════════════════════════════════════════════════
#  L1 门槛
# ══════════════════════════════════════════════════════════

def check_selection_quality(text: str) -> Optional[str]:
    """L1 有效性门槛：返回拒绝文案，None 表示通过

    长度门槛 5-350 字（MIN_CARD_TEXT / MAX_SELECTION_TEXT）。下限与 /api/judge
    一致，上限比它宽 150 字——本端点会把长选区交给 AI 收敛出核心句，
    /api/judge 没有 AI，放宽就等于允许拿整段当卡。

    另加三条纯字符检查。本地分类器对这些垃圾选区一律走默认分支给一张观点卡
    （实测「高达高达高达」与完整因果段判定结果完全相同），
    这类卡进文章生成只会产出空泛段落，还会白占一格配额。
    """
    stripped = (text or "").strip()

    if len(stripped) < MIN_CARD_TEXT or len(stripped) > MAX_SELECTION_TEXT:
        return MSG_TOO_SHORT_OR_LONG

    if not _MEANINGFUL_CHAR.search(stripped):
        # 纯标点 / 纯数字 / 纯符号
        return MSG_NO_MATERIAL

    # 灌水重复：长度不短但字符种类极少（「哈哈哈哈哈哈」「高达高达高达」）
    if len(stripped) >= 6 and len(set(stripped)) <= 2:
        return MSG_NO_MATERIAL

    return None


# ══════════════════════════════════════════════════════════
#  主判定（L1-L6 编排）
# ══════════════════════════════════════════════════════════

@dataclass
class DynamicCardOutcome:
    """判定结果

    response 直接作为 HTTP 响应体（与 JudgeResultDto 同构，额外带 source 字段）。
    text 是最终卡牌原文，**仅供后端 session 缓存与落盘使用**，不进响应体——
    前端拿 canonical range 自己从文章里切，多返一份文本只会让两侧有漂移的可能。
    resolved 是内部交接用的判型结果，同样不进响应体。
    """
    response: Dict = field(default_factory=dict)
    text: str = ""
    resolved: Optional[Dict] = None

    @property
    def hit(self) -> bool:
        return bool(self.response.get("hit"))


def _reject(message: str, source: str, path: str) -> DynamicCardOutcome:
    print(f"[dynamic-card] {path} 拒绝建卡: {message}")
    return DynamicCardOutcome(response={
        "hit": False,
        "matchRate": 0,
        "message": message,
        "source": source,
    })


def resolve_dynamic_selection(
    *,
    article_id: str,
    content: str,
    start: int,
    end: int,
    round_no: Optional[int] = None,
    classify: Classifier,
) -> DynamicCardOutcome:
    """按 L1-L6 阶梯判定一段玩家选区，产出与 JudgeResultDto 同构的响应

    Args:
        article_id: 文章 ID，用于 card_id 前缀与 L2 去重的分区键
        content: 文章全文（偏移量坐标系与 /api/judge 一致：全文连续序列含 \\n）
        start/end: 玩家选区，前端 convention 为 [start, end)
        round_no: 局号，落盘时记录；配额检查已移至前端（每局 10 张，resetGame 时清零）
        classify: 本地分类器（api._classify_card_type），注入以避免循环 import
    """
    selection = content[start:end].strip()

    # ── L1：本地门槛（不调 AI） ──────────────────────────
    reject_reason = check_selection_quality(selection)
    if reject_reason:
        return _reject(reject_reason, "local", "L1")

    # ── L2：同文章同文本已建过卡（不调 AI，省成本） ────────
    # 动态卡 ID 尾部的 timestamp 每次都不同，同一句话重复划会产生多张内容相同的卡，
    # 而前端 isSourceCollected 按 cardId 判重看不出这种重复。
    duplicated_id = find_card_id_by_hash(article_id, compute_text_hash(selection))
    if duplicated_id:
        return _reject(MSG_DUPLICATED, "local", f"L2(已存在 {duplicated_id})")

    # ── 调 AI ────────────────────────────────────────────
    verdict = ai_judge_selection(content, selection, start, end)

    if verdict is not None and not verdict.valid:
        # AI 正常判定为无要点，这不是失败，直接拒
        return _reject(MSG_NO_MATERIAL, "ai", f"L4(AI 判无要点: {verdict.reason})")

    # AI 判型（L4/L5 用），空字串表示 AI 这条路走不通
    ai_type = ""
    if verdict is not None and verdict.valid:
        candidate_type = normalize_card_type(verdict.card_type)
        # 防御：ai_judge_selection 已经拦过未知卡型，但本函数不该信任调用方传进来的
        # verdict（测试与以后的其它调用点都可能绕过那一层）。未知型别会让
        # mid_vector_for_type 返回 (0.0, 0.0)，而零向量会直接污染矩阵合成结果。
        if is_known_card_type(candidate_type):
            ai_type = candidate_type
        else:
            print(f"[dynamic-card] verdict 带未知卡型 {verdict.card_type!r}，忽略 AI 判型")

    # ── 确定最终区间：三条成功路径都强制过句边界扩展（红线③） ──
    final_start, final_end = start, end
    path = "L6"
    if verdict is not None and verdict.valid:
        located = locate_in_content(content, verdict.selected_text, start, end)
        if located is not None:
            candidate = expand_to_sentence_boundary(content, located[0], located[1])
            # AI 可能摘了个过短的碎片，扩边后仍不达门槛就退回原选区（L5）
            if len(content[candidate[0]:candidate[1]].strip()) >= MIN_CARD_TEXT:
                final_start, final_end = candidate
                path = "L4"
            else:
                path = "L5"
        else:
            path = "L5"

    if path != "L4":
        # L5：AI 判型可用但选文回查失败；L6：AI 完全失败。两者都用原选区扩边。
        final_start, final_end = expand_to_sentence_boundary(content, start, end)

    final_text = content[final_start:final_end]
    if len(final_text.strip()) < MIN_CARD_TEXT:
        return _reject(MSG_NO_MATERIAL, "local", f"{path}(扩边后仍不足 {MIN_CARD_TEXT} 字)")

    # ── 数值：一律本地派生，AI 只影响型别（红线②） ──────────
    local_type, local_value, local_x, local_y = classify(final_text)
    local_type = normalize_card_type(local_type)
    if ai_type and ai_type != local_type:
        # AI 看过上下文，判型优先；但量纲跟着型别走，必须整个换掉
        final_type = ai_type
        final_x, final_y = mid_vector_for_type(ai_type)
        print(f"[dynamic-card] AI 改判型别: 本地={local_type} → AI={ai_type}，"
              f"数值改用该型中值 ({final_x}, {final_y})")
    else:
        final_type = local_type
        final_x, final_y = local_x, local_y
    # clamp 兜底：分类器的硬编码向量必须始终符合 article生成规则.md
    final_x, final_y = clamp_card_vector(final_type, final_x, final_y)

    source = "ai" if path in ("L4", "L5") else "local"
    print(f"[dynamic-card] {path} 建卡成功: type={final_type}, source={source}, "
          f"range=[{final_start},{final_end}), 原文={final_text[:30]!r}")

    return DynamicCardOutcome(
        text=final_text,
        resolved={
            "type": final_type,
            "value": local_value,
            "x": final_x,
            "y": final_y,
            "start": final_start,
            "end": final_end,
            "path": path,
        },
        response={
            "hit": True,
            "matchRate": 0,
            "source": source,
            # card 字段由端点补齐：复用 _generate_dynamic_card 以保证 card_id 格式
            # 与响应结构的单一来源，本模块不重写一份 ID 拼接逻辑。
        },
    )
