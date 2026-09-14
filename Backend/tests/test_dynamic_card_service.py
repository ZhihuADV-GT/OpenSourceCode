"""动态划线判定服务测试（POST /api/cards/dynamic）

覆盖四块：
1. JSON 净化 —— 该接口最常见的失败模式（比超时更频繁）
2. 句边界扩展 —— 确定性算法，三条成功路径强制经过
3. L1-L6 降级阶梯 —— 含「AI 挂了仍严格优于现状」的核心保证
4. HTTP 层 —— 响应体与 JudgeResultDto 同构，前端 adapter 可直接复用

所有 AI 调用都被 monkeypatch 掉，测试不打网络。
"""

from __future__ import annotations

import hashlib

import pytest

from game.api import dynamic_card_service as service
from game.api import dynamic_card_store as store
from game.numerics.card_rules import (
    normalize_card_type,
    validate_card_vector,
)


# ══════════════════════════════════════════════════════════
#  夹具与假件
# ══════════════════════════════════════════════════════════

@pytest.fixture
def store_path(tmp_path, monkeypatch):
    """把落盘重定向到 tmp，避免测试污染真实 article_lib"""
    path = tmp_path / "dynamic_cards.json"
    monkeypatch.setattr(store, "STORE_PATH", path)
    store.reset_cache()
    yield path
    store.reset_cache()


def fake_classifier(card_type: str = "观点", value: int = 12,
                     x: float = 32.0, y: float = 32.0):
    """造一个可控的本地分类器（签名与 api._classify_card_type 一致）"""
    def _classify(_text: str):
        return (card_type, value, x, y)
    return _classify


@pytest.fixture
def no_ai(monkeypatch):
    """让 AI 彻底失败（L6 路径）"""
    calls = []

    def _fail(*args, **kwargs):
        calls.append((args, kwargs))
        return None

    monkeypatch.setattr(service, "ai_judge_selection", _fail)
    return calls


@pytest.fixture
def article_text() -> str:
    """一段有多句、便于测句边界的中文文本"""
    return (
        "第一段的前置句。"
        "玩家划的这半句话还没有说完"
        "现在才说完。"
        "后面还有一句独立的内容。"
    )


# ══════════════════════════════════════════════════════════
#  1. JSON 净化
# ══════════════════════════════════════════════════════════

class TestParseCardJson:
    def test_plain_object(self):
        raw = '{"valid": true, "card_type": "观点", "selected_text": "原文摘录"}'
        parsed = service.parse_card_json(raw)
        assert parsed == {"valid": True, "card_type": "观点", "selected_text": "原文摘录"}

    def test_strips_markdown_fence(self):
        """最常见的跑偏：模型无视「不要 markdown 围栏」的指令"""
        raw = '```json\n{"valid": true, "card_type": "情绪"}\n```'
        assert service.parse_card_json(raw)["card_type"] == "情绪"

    def test_strips_bare_fence_without_language(self):
        raw = '```\n{"valid": false}\n```'
        assert service.parse_card_json(raw) == {"valid": False}

    def test_tolerates_trailing_comma(self):
        raw = '{"valid": true, "card_type": "漏洞", "selected_text": "x",}'
        assert service.parse_card_json(raw)["card_type"] == "漏洞"

    def test_extracts_object_from_surrounding_prose(self):
        """模型在 JSON 前后夹自然语言"""
        raw = '好的，我的判定如下：\n{"valid": true, "card_type": "修辞"}\n以上就是结果。'
        assert service.parse_card_json(raw)["card_type"] == "修辞"

    def test_single_quoted_keys_and_values(self):
        raw = "{'valid': true, 'card_type': '观点', 'selected_text': '摘录'}"
        parsed = service.parse_card_json(raw)
        assert parsed is not None
        assert parsed["card_type"] == "观点"

    def test_not_json_at_all(self):
        assert service.parse_card_json("这段话里根本没有 JSON") is None

    def test_empty_and_none(self):
        assert service.parse_card_json("") is None
        assert service.parse_card_json("   ") is None
        assert service.parse_card_json(None) is None

    def test_unbalanced_braces_from_token_cutoff(self):
        """被 max_tokens 截断 → 括号不平衡，必须返回 None 而不是抛异常"""
        raw = '{"valid": true, "card_type": "观点", "selected_text": "很长很长'
        assert service.parse_card_json(raw) is None

    def test_bare_control_characters_inside_string(self):
        """真实失败模式：AI 摘录原文时直接带上裸换行而不转义

        json.loads 默认 strict=True 会以 "Invalid control character" 判死，
        白白把一次本来可用的 AI 判定降级到 L6。必须用 strict=False 吃掉。
        """
        raw = '{"valid": true, "card_type": "观点", "selected_text": "前半句\n后半句"}'
        parsed = service.parse_card_json(raw)
        assert parsed is not None, "裸换行不得导致整条响应被丢弃"
        assert parsed["selected_text"] == "前半句\n后半句"

    def test_bare_tab_inside_string(self):
        raw = '{"valid": true, "selected_text": "包含\t制表符"}'
        assert service.parse_card_json(raw)["selected_text"] == "包含\t制表符"

    def test_array_wrapper_takes_first_object(self):
        """模型偶尔用数组包裹单个对象，取首元素是有意的宽容"""
        assert service.parse_card_json('[{"valid": true}]') == {"valid": True}

    def test_pure_array_without_object_returns_none(self):
        assert service.parse_card_json("[1, 2, 3]") is None
        assert service.parse_card_json('["观点", "情绪"]') is None

    def test_brace_inside_string_does_not_break_extraction(self):
        """字符串字面量里的花括号不能被当成结构括号"""
        raw = '{"selected_text": "这里有个 } 符号", "valid": true}'
        parsed = service.parse_card_json(raw)
        assert parsed["selected_text"] == "这里有个 } 符号"

    def test_escaped_quote_inside_string(self):
        raw = r'{"selected_text": "他说\"好\"", "valid": true}'
        parsed = service.parse_card_json(raw)
        assert parsed is not None
        assert parsed["valid"] is True

    def test_first_object_wins_when_several(self):
        raw = '{"valid": true, "card_type": "观点"} 另外还有 {"valid": false}'
        assert service.parse_card_json(raw)["card_type"] == "观点"

    # ── 字符串值内部的裸双引号（真机捕获的高频降级路径）──

    def test_unescaped_inner_quotes_from_real_capture(self):
        """真机捕获：AI 把原文里的英文双引号原样抄进 JSON 而没转义

        这是 article_3 上真实发生的（qwen-turbo, 0.98s）：原文「他们把精力
        都花在了"想"上，而不是"做"上」，AI 摘录时照抄了引号。
        json.loads 报 Expecting ',' delimiter: line 1 column 84，前三级净化
        全部失败 → 降级 L6，玩家这一划完全拿不到 AI 判型。

        后果不只是这一句：文章库里含英文引号的内容不少见，等于玩家划到
        这类段落就必然失去 AI 能力，是高频降级路径而不是边角情况。
        """
        raw = ('{"valid": true, "card_type": "观点", "selected_text": '
               '"这就是为什么很多聪明人反而行动力很差——他们把精力都花在了"想"上，'
               '而不是"做"上。", "reason": "表达可讨论的判断"}')
        parsed = service.parse_card_json(raw)
        assert parsed is not None, "内部裸引号不得导致整条响应被丢弃"
        assert parsed["card_type"] == "观点"
        assert parsed["reason"] == "表达可讨论的判断"

    def test_inner_quotes_are_restored_verbatim_for_lookup(self):
        """补转义后必须还原成逐字原文，否则回查会失败降级到 L5

        第四级的目的不是「让 JSON 能解析」就完事：解析出的 selected_text
        要拿去 content.find() 回查原文定位。多一个反斜杠或少一个引号都会
        查不到，等于把 L4（AI 定位）降成 L5（本地扩边），白修一场。
        """
        original = ('这就是为什么很多聪明人反而行动力很差——'
                    '他们把精力都花在了"想"上，而不是"做"上。')
        raw = '{"valid": true, "selected_text": "' + original + '", "reason": "x"}'
        parsed = service.parse_card_json(raw)
        assert parsed is not None
        assert parsed["selected_text"] == original, "必须与原文逐字相等"

        content = "前文。" + original + "后文。"
        assert content.find(parsed["selected_text"]) > 0, "回查必须命中"

    def test_inner_quotes_surrounded_by_hanzi(self):
        """引号两侧都是汉字时全部补转义，后面的字段不得错位

        这是启发式的正例：中文原文里引号外侧不可能是 , } ] : ，
        所以能稳定地与真正的字符串边界区分开。
        """
        raw = '{"selected_text": "他说"好"啊", "reason": "感叹", "valid": true}'
        parsed = service.parse_card_json(raw)
        assert parsed is not None
        assert parsed["selected_text"] == '他说"好"啊'
        assert parsed["reason"] == "感叹"
        assert parsed["valid"] is True

    def test_already_escaped_quotes_are_not_double_escaped(self):
        """已正确转义的 JSON 不能被第四级再改一次（幂等）

        第四级只在前三级都失败后才会被尝试，合规响应根本走不到这里。
        这条钉住 _escape_inner_quotes 对合规输入是幂等的——万一以后有人
        把它提到第一级，也不能把 \\" 变成 \\\\"。
        """
        raw = r'{"selected_text": "他说\"好\"，然后走了", "valid": true}'
        parsed = service.parse_card_json(raw)
        assert parsed["selected_text"] == '他说"好"，然后走了'
        assert service._escape_inner_quotes(raw) == raw, "对合规 JSON 必须幂等"

    def test_known_limitation_inner_quote_before_comma(self):
        """已知局限：内部引号紧跟英文逗号时会被当成边界，钉住这个退化行为

        启发式靠「结束引号后面是 , } ] :」判边界，所以原文里出现 `走",`
        这种序列时，那个内部引号会被误判为字符串结束。

        后果是**部分成功**而不是崩溃：JSON 能解析，但 selected_text 少了
        尾引号，回查原文失败 → 降级 L5（本地扩边），玩家仍能拿到一张卡。
        中文里引号后紧跟英文逗号的写法极少（原文用中文标点「，」），
        所以接受这个局限；写下来是为了以后看到 L5 日志时知道原因。
        """
        raw = '{"valid": true, "selected_text": "他说"走", "reason": "感叹"}'
        parsed = service.parse_card_json(raw)
        assert parsed is not None, "误判边界也必须能解析，不能整条丢弃"
        assert parsed["selected_text"] == '他说"走'
        assert parsed["reason"] == "感叹"


# ══════════════════════════════════════════════════════════
#  2. 句边界扩展（确定性算法，永不失败）
# ══════════════════════════════════════════════════════════

class TestExpandToSentenceBoundary:
    def test_mid_sentence_fragment_expands_both_ways(self, article_text):
        """核心用例：玩家划了半句，必须扩成完整句"""
        start = article_text.index("玩家划的这半句话")
        end = start + 6  # 只划了「玩家划的这」
        left, right = service.expand_to_sentence_boundary(article_text, start, end)
        assert article_text[left:right] == "玩家划的这半句话还没有说完现在才说完。"

    def test_already_at_boundaries_is_unchanged(self, article_text):
        start = article_text.index("玩家划的")
        end = article_text.index("。", start) + 1
        assert service.expand_to_sentence_boundary(article_text, start, end) == (start, end)

    def test_expansion_includes_the_ending_punctuation(self, article_text):
        start = article_text.index("后面还有一句")
        left, right = service.expand_to_sentence_boundary(article_text, start, start + 3)
        assert article_text[left:right].endswith("。")

    def test_left_expansion_stops_after_previous_ending(self, article_text):
        """向左扩到上一句句末标点之后，不会把上一句也吃进来"""
        start = article_text.index("后面还有一句") + 2
        left, _ = service.expand_to_sentence_boundary(article_text, start, start + 3)
        assert left == article_text.index("后面还有一句")

    def test_newline_counts_as_sentence_boundary(self):
        content = "上一段结尾\n这一段的句子还没说完"
        start = content.index("这一段") + 4
        left, right = service.expand_to_sentence_boundary(content, start, start + 3)
        assert left == content.index("这一段")
        assert right == len(content)

    def test_leading_and_trailing_whitespace_is_trimmed(self):
        content = "前句。\n   玩家划的句子在这里。   \n后句。"
        start = content.index("玩家划的") - 2
        end = content.index("。", start) + 4
        left, right = service.expand_to_sentence_boundary(content, start, end)
        result = content[left:right]
        assert result == result.strip()
        assert "玩家划的句子在这里。" in result

    def test_per_side_expansion_is_capped(self):
        """没有句末标点时不能一路扩到全文，单侧上限 80 字"""
        content = "无标点长句" * 60  # 300 字，一个标点都没有
        start, end = 150, 156
        left, right = service.expand_to_sentence_boundary(content, start, end)
        assert start - left <= service.MAX_EXPAND_PER_SIDE
        assert right - end <= service.MAX_EXPAND_PER_SIDE

    def test_total_length_never_exceeds_max(self):
        """扩完总长必须 ≤ MAX_CARD_TEXT（产出上限，与入参门槛 350 刻意不同）"""
        content = ("这是一句比较长的句子内容。" * 40)
        start, end = 100, 190  # 原选区 90 字
        left, right = service.expand_to_sentence_boundary(content, start, end)
        assert right - left <= service.MAX_CARD_TEXT

    # ── 原选区本身就超过产出上限：入参门槛放宽到 350 之后必然会出现 ──

    def test_overlong_selection_is_truncated_not_returned_as_is(self):
        """原选区 > MAX_CARD_TEXT 时必须截断，不能原样返回

        钳制逻辑原先在这种情况下 return start, end，350 字的选区就会原样变成
        一张 350 字的卡。卡牌文本直接进局末文章生成的段落，350 字会把整段占满。
        AI 降级（L5/L6）时走的正是这条路——它拿玩家原选区扩边，没有 AI 帮忙收敛。
        """
        content = "这是一个正常的句子片段。" * 40   # 480 字
        left, right = service.expand_to_sentence_boundary(content, 0, 350)
        assert right - left <= service.MAX_CARD_TEXT, f"产出 {right - left} 字，超出上限"
        assert left == 0, "保头弃尾：起点是玩家想强调的开头，也是 AI 收敛的倾向位置"

    def test_truncation_prefers_sentence_boundary(self):
        """截断优先在句末标点收口，不把句子拦腰砍断"""
        content = "这是一个正常的句子片段。" * 40
        left, right = service.expand_to_sentence_boundary(content, 0, 350)
        assert content[right - 1] == "。", f"应在句末标点收口，实际结尾 {content[right - 1]!r}"

    def test_truncation_hard_cuts_when_head_is_sentence_tail(self):
        """收口后不足下限时宁可硬截，也不要产出会被门槛拒掉的碎片

        构造：开头一个 2 字短句，其后 200 字内再无任何句末标点。
        句末收口只能收到 2 字（< MIN_CARD_TEXT），整张卡会被后面的门槛拒掉，
        玩家等于白划一次——比砍断句子更糟，所以这种情况硬截到上限。
        """
        content = "短。" + "这是一个正常的句子片段" * 20   # 后半段 220 字无标点
        left, right = service.expand_to_sentence_boundary(content, 0, 300)
        assert right - left >= service.MIN_CARD_TEXT, "不该因开头是残句尾就产出碎片"
        assert right - left <= service.MAX_CARD_TEXT

    def test_right_boundary_is_preserved_before_left_when_tight(self):
        """预算不够时先保句末（无尾比无头更伤可读性）"""
        head = "前面这一大段完全没有标点符号所以向左扩会吃掉很多字" * 3
        content = head + "玩家划的短句。"
        start = len(head) + 1
        end = start + 3
        left, right = service.expand_to_sentence_boundary(content, start, end)
        assert content[right - 1] == "。", "句末标点必须保住"

    def test_out_of_range_inputs_are_clamped(self):
        content = "只有一句。"
        assert service.expand_to_sentence_boundary(content, -50, 3) == (0, len(content))
        assert service.expand_to_sentence_boundary(content, 3, 9999)[1] <= len(content)

    def test_empty_range_returns_as_is(self):
        content = "一句话。"
        assert service.expand_to_sentence_boundary(content, 2, 2) == (2, 2)

    def test_empty_content(self):
        assert service.expand_to_sentence_boundary("", 0, 0) == (0, 0)

    def test_never_raises_on_arbitrary_input(self):
        """永不抛异常是硬要求：它在三条成功路径上，挂了就没有卡了"""
        content = "。\n！？；"
        for start in range(-2, len(content) + 3):
            for end in range(-2, len(content) + 3):
                left, right = service.expand_to_sentence_boundary(content, start, end)
                assert 0 <= left <= right <= len(content)


# ══════════════════════════════════════════════════════════
#  3. selected_text 回查
# ══════════════════════════════════════════════════════════

class TestLocateInContent:
    def test_finds_text_inside_window(self, article_text):
        needle = "玩家划的这半句话"
        start = article_text.index(needle)
        assert service.locate_in_content(article_text, needle, start, start + 3) == (
            start, start + len(needle))

    def test_rejects_match_far_outside_window(self):
        """AI 引到文章另一处的同句 → 不采信，否则高亮会跳到错误位置"""
        content = ("重复出现的句子。" + "中间填充内容。" * 60
                   + "重复出现的句子。")
        first = content.index("重复出现的句子")
        last = content.rindex("重复出现的句子")
        # 玩家划的是后面那处，AI 却摘了前面那处的文本
        result = service.locate_in_content(content, "重复出现的句子", last, last + 5)
        assert result is None or result[0] >= last - service.LOOKUP_WINDOW

    def test_empty_needle(self, article_text):
        assert service.locate_in_content(article_text, "", 0, 5) is None
        assert service.locate_in_content(article_text, "   ", 0, 5) is None
        assert service.locate_in_content(article_text, None, 0, 5) is None

    def test_needle_is_stripped_before_lookup(self, article_text):
        needle = "  玩家划的这半句话  "
        bare = "玩家划的这半句话"
        start = article_text.index(bare)
        assert service.locate_in_content(article_text, needle, start, start + 3) == (
            start, start + len(bare))

    def test_absent_text_returns_none(self, article_text):
        assert service.locate_in_content(article_text, "文章里根本没有这句话", 0, 5) is None

    def test_newline_dropped_by_ai_still_matches(self):
        """真机联调实测的失败模式：AI 摘录跨行句子时把 \n 丢掉

        原文是「…正相关。\n和成本无关…」，qwen-turbo 返的 selected_text 是
        「…正相关。和成本无关…」。精确 find 必然失败，以前白白降级到 L5。
        """
        content = "第一句话在这里。\n第二句话紧接着。第三句结束。"
        needle = "第一句话在这里。第二句话紧接着。"  # 少了那个 \n

        result = service.locate_in_content(content, needle, 0, len(content))

        assert result is not None, "空白不敏感回查没生效，会降级到 L5"
        expected_end = content.index("第二句话紧接着。") + len("第二句话紧接着。")
        assert result == (0, expected_end)

    def test_whitespace_match_returns_exact_original_span(self):
        """回查出来的区间必须是原文真实跨度，而不是 len(selected_text)

        AI 丢了 1 个 \n，len() 就比原文短 1。拿 len() 算止偏移会少括一个字，
        而句末标点一旦被切掉，expand_to_sentence_boundary 就会继续向右扩到下一句。
        """
        content = "前导句。\n目标句子在这里。\n后续句子。"
        needle = "目标句子在这里。后续句子。"  # AI 把中间的 \n 丢了

        result = service.locate_in_content(content, needle, 4, 20)

        assert result is not None
        assert content[result[0]:result[1]] == "目标句子在这里。\n后续句子。"
        assert len(content[result[0]:result[1]]) == len(needle) + 1, \
            "止偏移没把被丢掉的空白算回去"

    def test_whitespace_match_still_respects_window(self):
        """空白不敏感匹配同样受窗口约束：宁可降级也不得错位高亮"""
        content = "开头的句子。\n" + "中间填充。" * 200 + "开头的句子。"
        tail = content.rindex("开头的句子。")

        # AI 摘的版本多了个空格：精确匹配两处都失败，空白不敏感匹配两处都能命中，
        # 但只有文末那处落在 tail ± LOOKUP_WINDOW 内
        result = service.locate_in_content(content, "开头 的句子。", tail, tail + 6)

        assert result is not None
        assert result[0] == tail, "匹配到了窗口外的文首同句，会造成错位高亮"


class TestBuildContext:
    def test_short_content_is_passed_whole(self, article_text):
        assert service.build_context(article_text, 0, 5) == article_text

    def test_long_content_is_windowed_with_ellipsis(self):
        content = "很长的文章。" * 3000  # 18000 字，远超 MAX_CONTEXT_CHARS
        middle = len(content) // 2
        context = service.build_context(content, middle, middle + 10)
        assert len(context) <= service.MAX_CONTEXT_CHARS + 4  # 允许两个省略号
        assert context.startswith("……") and context.endswith("……")
        assert content[middle:middle + 10] in context, "选区本身必须在窗口里"

    def test_window_near_start_has_no_leading_ellipsis(self):
        content = "很长的文章。" * 3000
        context = service.build_context(content, 0, 10)
        assert not context.startswith("……")
        assert context.endswith("……")


# ══════════════════════════════════════════════════════════
#  4. 数值派生（红线②：数值绝不采信 AI）
# ══════════════════════════════════════════════════════════

class TestMidVectorForType:
    @pytest.mark.parametrize("card_type", ["观点", "情绪", "漏洞", "修辞"])
    def test_derived_vector_is_always_valid(self, card_type):
        """派生出的数值必须直接通过 card_rules 校验，不能再靠 clamp 抢救"""
        x, y = service.mid_vector_for_type(card_type)
        assert validate_card_vector(card_type, x, y) == []

    @pytest.mark.parametrize("card_type", ["观点卡", "情绪卡", "漏洞卡", "修辞卡"])
    def test_accepts_display_form_too(self, card_type):
        x, y = service.mid_vector_for_type(card_type)
        assert validate_card_vector(card_type, x, y) == []

    def test_rhetoric_uses_multiplier_not_vector(self):
        """修辞是乘数量纲，绝不能派生出 19-36 的整数"""
        x, y = service.mid_vector_for_type("修辞")
        assert 1.05 < x < 1.60 and 1.05 < y < 1.60

    def test_vector_types_are_integers(self):
        for card_type in ("观点", "情绪", "漏洞"):
            x, y = service.mid_vector_for_type(card_type)
            assert float(x) == int(x) and float(y) == int(y)

    def test_quadrant_signs_follow_rules(self):
        assert service.mid_vector_for_type("观点") == (33.0, 33.0)    # 第一象限
        assert service.mid_vector_for_type("漏洞") == (-23.0, 23.0)   # 第二象限
        assert service.mid_vector_for_type("情绪") == (23.0, -23.0)   # 第四象限

    def test_unknown_type_does_not_crash(self):
        assert service.mid_vector_for_type("不存在的类型") == (0.0, 0.0)

    def test_no_hardcoded_vector_table_in_service(self):
        """防漂移：service 里不许出现第二份向量表，必须从 card_rules 派生"""
        source = open(service.__file__, encoding="utf-8").read()
        body = source.split("def mid_vector_for_type")[1].split("\ndef ")[0]
        for forbidden in ("33.0, 33.0", "(32", "(25", "1.25"):
            assert forbidden not in body, f"mid_vector_for_type 里出现了硬编码 {forbidden}"


def test_text_hash_matches_generate_dynamic_card():
    """hash 算法必须与 api._generate_dynamic_card 内联的逐字一致

    两处实现是重复的：那边内联 hashlib，这边为了做 L2 去重也要算。
    一旦漂移，L2 去重就永远不命中，同一段文字可以无限刷卡。
    """
    from game.api.api import _generate_dynamic_card

    text = "这是一段用于校验 hash 一致性的文本"
    card = _generate_dynamic_card("article_1", text, 0, len(text))
    # card_id 格式: {article_id}_dynamic_{type}_{hash}_{timestamp_ns}_{counter}
    # hash 是倒数第 3 段（timestamp_ns 倒数第 2，counter 倒数第 1）
    id_hash = card["card_id"].rsplit("_", 3)[-3]
    assert id_hash == service.compute_text_hash(text)
    assert id_hash == hashlib.md5(text.encode("utf-8")).hexdigest()[:8]


# ══════════════════════════════════════════════════════════
#  5. L1 门槛
# ══════════════════════════════════════════════════════════

class TestCheckSelectionQuality:
    def test_normal_text_passes(self):
        assert service.check_selection_quality("这是一个正常的句子片段") is None

    @pytest.mark.parametrize("text", ["", "   ", "短句", "四个字"])
    def test_too_short(self, text):
        assert service.check_selection_quality(text) == service.MSG_TOO_SHORT_OR_LONG

    def test_too_long(self):
        # 必须用真有变化的文本：重复字符会先撞灌水检查，测的就不是长度门槛了。
        # 放宽到 350 之后「字」*201 正是这样从 MSG_TOO_SHORT_OR_LONG 变成了
        # MSG_NO_MATERIAL（见下面那条行为变更记录）。
        long_text = ("这是一个正常的句子片段。" * 40)[:351]
        assert len(long_text) == 351
        assert service.check_selection_quality(long_text) == service.MSG_TOO_SHORT_OR_LONG
    
    def test_exactly_at_bounds_passes(self):
        # 边界用例必须是真有变化的文本：“字"*N 会被灌水重复检查拦下（那是正确行为）
        assert service.check_selection_quality("字" * 5) is None
        long_text = ("这是一个正常的句子片段。" * 40)[:350]
        assert len(long_text) == 350
        assert service.check_selection_quality(long_text) is None
    
    def test_selection_between_judge_limit_and_own_limit_passes(self):
        """201-350 字是本端点独有的放行区间，放宽的全部意义就在这里
    
        实测 260 字选区原先撞 200 被 L1 直接拒，玩家白划一次；现在它能进 AI，
        由 AI 摘出 10-120 字的核心句。/api/judge 没有 AI，它的 200 不能跟着放宽。
        """
        for length in (201, 260, 350):
            text = ("这是一个正常的句子片段。" * 40)[:length]
            assert len(text) == length
            assert service.check_selection_quality(text) is None, f"{length} 字应放行"
    
    def test_overlong_repetition_falls_to_flood_check_not_length(self):
        """行为变更记录：201 个重复字放宽后不再撞长度门槛，而是撞灌水检查
    
        两个门槛都拒它，但文案不同（MSG_NO_MATERIAL vs MSG_TOO_SHORT_OR_LONG）。
        钉住这条是为了以后有人动灌水检查时，立刻看出超长重复选区的归属会变。
        """
        assert service.check_selection_quality("字" * 201) == service.MSG_NO_MATERIAL

    @pytest.mark.parametrize("text", ["。。。。。。", "！？！？！？", "——————"])
    def test_punctuation_only(self, text):
        assert service.check_selection_quality(text) == service.MSG_NO_MATERIAL

    @pytest.mark.parametrize("text", ["1234567890", "2024-09-11", "3.1415926"])
    def test_digits_only(self, text):
        assert service.check_selection_quality(text) == service.MSG_NO_MATERIAL

    @pytest.mark.parametrize("text", ["哈哈哈哈哈哈", "高达高达高达", "好好好好好好"])
    def test_flooded_repetition(self, text):
        """本地分类器对这些一律给观点卡，实测与完整因果段判定结果完全相同"""
        assert service.check_selection_quality(text) == service.MSG_NO_MATERIAL

    def test_repetition_check_does_not_hit_normal_short_text(self):
        assert service.check_selection_quality("数字增长了") is None
        assert service.check_selection_quality("2024年增长率") is None

    def test_reuse_of_existing_wording(self):
        """文案必须与现有出处逐字一致，前端直接显示后端给的 message"""
        assert service.MSG_TOO_SHORT_OR_LONG == "选区过短或过长，请重新划线"
        assert service.MSG_NO_MATERIAL == "未发现有效素材"
        assert service.MSG_DUPLICATED == "该素材已经收集"


# ══════════════════════════════════════════════════════════
#  6. L1-L6 降级阶梯
# ══════════════════════════════════════════════════════════

def _resolve(content, start, end, *, monkeypatch=None, verdict=None,
             round_no=None, classify=None, article_id="article_1"):
    """跑一次判定；verdict='fail' 表示 AI 返回 None"""
    if verdict == "fail":
        monkeypatch.setattr(service, "ai_judge_selection", lambda *a, **k: None)
    elif verdict is not None:
        monkeypatch.setattr(service, "ai_judge_selection", lambda *a, **k: verdict)
    return service.resolve_dynamic_selection(
        article_id=article_id,
        content=content,
        start=start,
        end=end,
        round_no=round_no,
        classify=classify or fake_classifier(),
    )


class TestRejectLadder:
    def test_l1_too_short_never_calls_ai(self, monkeypatch, store_path):
        """L1 不调 AI：省钱，也避免为垃圾选区付 15s 延迟"""
        calls = monkeypatch.setattr(service, "ai_judge_selection",
                                    lambda *a, **k: pytest.fail("L1 不该调 AI"))
        content = "这是一段正常文章。短句。"
        start = content.index("短句")
        outcome = _resolve(content, start, start + 2, monkeypatch=monkeypatch)
        assert outcome.hit is False
        assert outcome.response["message"] == service.MSG_TOO_SHORT_OR_LONG
        assert outcome.response["source"] == "local"

    def test_l1_punctuation_only_never_calls_ai(self, monkeypatch, store_path):
        monkeypatch.setattr(service, "ai_judge_selection",
                            lambda *a, **k: pytest.fail("L1 不该调 AI"))
        content = "前文。。。。。。后文"
        start = content.index("。。。")
        outcome = _resolve(content, start, start + 6, monkeypatch=monkeypatch)
        assert outcome.response["message"] == service.MSG_NO_MATERIAL

    def test_l2_duplicate_never_calls_ai(self, monkeypatch, store_path):
        """同文章同文本已建过卡 → 拒，且不调 AI"""
        content = "这是一段可以被划的正常句子内容。后面还有。"
        start = content.index("这是一段")
        end = content.index("。") + 1

        first = _resolve(content, start, end, verdict=service.AiVerdict(
            valid=True, card_type="观点", selected_text=content[start:end]),
            monkeypatch=monkeypatch)
        assert first.hit is True
        store.save_dynamic_card(
            {"card_id": "article_1_dynamic_观点_"
                        + service.compute_text_hash(content[start:end]) + "_1700000000000000000_0",
             "card_type": "观点卡", "start": start, "end": end - 1,
             "attribute_value": 12, "attribute_x": 32.0, "attribute_y": 32.0},
            content[start:end],
        )

        monkeypatch.setattr(service, "ai_judge_selection",
                            lambda *a, **k: pytest.fail("L2 不该调 AI"))
        second = _resolve(content, start, end, monkeypatch=monkeypatch)
        assert second.hit is False
        assert second.response["message"] == service.MSG_DUPLICATED

    def test_no_quota_check_on_backend(self, monkeypatch, store_path):
        """配额检查已移至前端：后端不再强制配额，即使落盘已满也继续处理"""
        content = "这是一段可以被划的正常句子内容。"
        start, end = 0, content.index("。") + 1

        # 落盘 20 张卡（远超旧配额的 10 张）
        for index in range(20):
            store.save_dynamic_card(
                {"card_id": f"article_1_dynamic_观点_abcd{index:04d}_{index}",
                 "card_type": "观点卡", "start": start, "end": end - 1,
                 "attribute_value": 12, "attribute_x": 32.0, "attribute_y": 32.0,
                 "round": 3},
                f"占位文本 {index}", round_no=3,
            )

        # 后端应继续处理，不因配额拒绝
        outcome = _resolve(
            content, start, end, monkeypatch=monkeypatch, round_no=3,
            verdict=service.AiVerdict(valid=True, card_type="观点",
                                      selected_text=content[start:end]),
        )
        assert outcome.hit is True

    def test_ai_says_no_material_is_a_rejection_not_a_failure(self, monkeypatch, store_path):
        """AI 正常判定为无要点 → 拒（source=ai），与 AI 挂掉（source=local）语义不同"""
        content = "这是一段日常寒暄的句子啊。"
        start, end = 0, content.index("。") + 1
        outcome = _resolve(content, start, end, monkeypatch=monkeypatch,
                           verdict=service.AiVerdict(valid=False, reason="日常寒暄"))
        assert outcome.hit is False
        assert outcome.response["message"] == service.MSG_NO_MATERIAL
        assert outcome.response["source"] == "ai"


class TestSuccessLadder:
    """三条成功路径都必须有句边界扩展（用户明确要求，不只是降级时才扩）"""

    def test_l4_uses_ai_text_expanded_to_sentence(self, monkeypatch, store_path):
        content = "前置句子。玩家划的这半句话还没有说完现在才说完。后续句子。"
        raw_start = content.index("玩家划的这半句话")
        raw_end = raw_start + 6                      # 玩家只划了「玩家划的这」
        ai_text = "玩家划的这半句话还没有说完"        # AI 摘了更长但仍未到句末的片段

        outcome = _resolve(content, raw_start, raw_end, monkeypatch=monkeypatch,
                           verdict=service.AiVerdict(valid=True, card_type="观点",
                                                     selected_text=ai_text))
        assert outcome.hit is True
        assert outcome.resolved["path"] == "L4"
        assert outcome.response["source"] == "ai"
        # 句边界扩展：AI 摘的片段被补到完整句
        assert outcome.text == "玩家划的这半句话还没有说完现在才说完。"
        assert outcome.resolved["start"] == raw_start
        assert outcome.resolved["end"] == content.index("。", raw_start) + 1

    def test_l5_falls_back_to_raw_selection_when_lookup_fails(self, monkeypatch, store_path):
        """AI 判型可用但 selected_text 回查失败 → 原选区扩边 + AI 判型"""
        content = "前置句子。玩家划的这半句话还没有说完现在才说完。后续句子。"
        raw_start = content.index("玩家划的这半句话")
        raw_end = raw_start + 6

        outcome = _resolve(content, raw_start, raw_end, monkeypatch=monkeypatch,
                           verdict=service.AiVerdict(valid=True, card_type="情绪",
                                                     selected_text="文章里没有这句话"))
        assert outcome.hit is True
        assert outcome.resolved["path"] == "L5"
        assert outcome.response["source"] == "ai"
        assert outcome.resolved["type"] == "情绪", "判型仍采信 AI"
        assert outcome.text == "玩家划的这半句话还没有说完现在才说完。", "仍必须扩到句边界"

    def test_l6_falls_back_to_local_when_ai_dies(self, monkeypatch, store_path):
        """AI 挂掉 → 本地判型 + 本地句边界扩展，结果仍严格优于引入 AI 之前"""
        content = "前置句子。玩家划的这半句话还没有说完现在才说完。后续句子。"
        raw_start = content.index("玩家划的这半句话")
        raw_end = raw_start + 6

        outcome = _resolve(content, raw_start, raw_end, monkeypatch=monkeypatch,
                           verdict="fail", classify=fake_classifier("观点", 12, 32.0, 32.0))
        assert outcome.hit is True
        assert outcome.resolved["path"] == "L6"
        assert outcome.response["source"] == "local"
        assert outcome.text == "玩家划的这半句话还没有说完现在才说完。"
        assert outcome.resolved["type"] == "观点"
        assert (outcome.resolved["x"], outcome.resolved["y"]) == (32.0, 32.0)

    @pytest.mark.parametrize("path_verdict", [
        service.AiVerdict(valid=True, card_type="观点", selected_text="SENT"),
        service.AiVerdict(valid=True, card_type="情绪", selected_text="文章里没有"),
        "fail",
    ], ids=["L4", "L5", "L6"])
    def test_all_success_paths_expand_to_sentence_boundary(
            self, monkeypatch, store_path, path_verdict):
        """用户要求：任何动态划线，成功的话，都应该有句边界扩展"""
        content = "前置句子。玩家划的这半句话还没有说完现在才说完。后续句子。"
        raw_start = content.index("玩家划的这半句话")
        raw_end = raw_start + 6

        verdict = path_verdict
        if isinstance(verdict, service.AiVerdict) and verdict.selected_text == "SENT":
            verdict = service.AiVerdict(
                valid=True, card_type=verdict.card_type,
                selected_text="玩家划的这半句话还没有说完",
            )

        outcome = _resolve(content, raw_start, raw_end, monkeypatch=monkeypatch,
                           verdict=verdict)
        assert outcome.hit is True
        assert outcome.text.endswith("。"), f"{outcome.resolved['path']} 没有扩到句末"
        assert outcome.text.startswith("玩家"), f"{outcome.resolved['path']} 没有扩到句首"

    def test_ai_type_override_replaces_vector_with_valid_one(self, monkeypatch, store_path):
        """AI 改判型别时数值必须整个换掉：修辞是乘数，其余是整数向量，量纲不同"""
        content = "前置句子。这段文字像一个比喻一样展开说明问题。后续。"
        start = content.index("这段文字")
        end = start + 8

        outcome = _resolve(content, start, end, monkeypatch=monkeypatch,
                           verdict=service.AiVerdict(valid=True, card_type="修辞",
                                                     selected_text=content[start:end]),
                           classify=fake_classifier("观点", 15, 34.0, 33.0))
        assert outcome.resolved["type"] == "修辞"
        x, y = outcome.resolved["x"], outcome.resolved["y"]
        assert validate_card_vector("修辞", x, y) == [], f"修辞卡数值违规: {(x, y)}"
        assert 1.05 < x < 1.60, "绝不能沿用观点卡的 34.0"

    def test_ai_type_same_as_local_keeps_local_vector(self, monkeypatch, store_path):
        """判型一致时沿用本地分类器的数值（保留卡牌相对强弱）"""
        content = "前置句子。这段文字是一个完整的观点句子。后续。"
        start = content.index("这段文字")
        end = content.index("。", start) + 1

        outcome = _resolve(content, start, end, monkeypatch=monkeypatch,
                           verdict=service.AiVerdict(valid=True, card_type="观点",
                                                     selected_text=content[start:end]),
                           classify=fake_classifier("观点", 18, 35.0, 34.0))
        assert (outcome.resolved["x"], outcome.resolved["y"]) == (35.0, 34.0)
        assert outcome.resolved["value"] == 18

    @pytest.mark.parametrize("ai_type", ["观点", "情绪", "漏洞", "修辞"])
    def test_any_ai_type_yields_valid_vector(self, monkeypatch, store_path, ai_type):
        content = "前置句子。这段文字是一个完整的句子内容。后续。"
        start = content.index("这段文字")
        end = content.index("。", start) + 1
        outcome = _resolve(content, start, end, monkeypatch=monkeypatch,
                           verdict=service.AiVerdict(valid=True, card_type=ai_type,
                                                     selected_text=content[start:end]),
                           classify=fake_classifier("观点", 12, 32.0, 32.0))
        assert validate_card_vector(ai_type, outcome.resolved["x"],
                                    outcome.resolved["y"]) == []

    def test_ai_card_type_with_suffix_is_normalized(self, monkeypatch, store_path):
        """prompt 明令禁止带「卡」后缀，但模型不总听话，必须归一化而不是拒绝"""
        content = "前置句子。这段文字是一个完整的句子内容。后续。"
        start = content.index("这段文字")
        end = content.index("。", start) + 1
        outcome = _resolve(content, start, end, monkeypatch=monkeypatch,
                           verdict=service.AiVerdict(valid=True, card_type="观点卡",
                                                     selected_text=content[start:end]))
        assert outcome.hit is True
        assert outcome.resolved["type"] == "观点"

    def test_unknown_ai_type_degrades_to_local(self, monkeypatch, store_path):
        """AI 返回未知卡型 → 判型退回本地，数值绝不能变成 (0,0)

        回归用例：mid_vector_for_type 对未知型别返回 (0.0, 0.0)，而零向量会直接
        污染矩阵合成结果。ai_judge_selection 虽然拦了未知卡型，但消费点必须再防一道：
        本用例直接构造 verdict 绕过了那一层，就是为了钉住这个防御。
        """
        content = "前置句子。这段文字是一个完整的句子内容。后续。"
        start = content.index("这段文字")
        end = content.index("。", start) + 1
        outcome = _resolve(content, start, end, monkeypatch=monkeypatch,
                           verdict=service.AiVerdict(valid=True, card_type="数据",
                                                     selected_text=content[start:end]),
                           classify=fake_classifier("情绪", 14, 26.0, -25.0))
        assert outcome.hit is True
        assert outcome.resolved["type"] == "情绪", "未知卡型必须退回本地判型"
        assert outcome.resolved["path"] == "L4", "选文回查仍成功，只是判型被忽略"
        assert (outcome.resolved["x"], outcome.resolved["y"]) == (26.0, -25.0)
        assert validate_card_vector("情绪", outcome.resolved["x"],
                                    outcome.resolved["y"]) == []

    def test_ai_short_fragment_falls_back_to_l5(self, monkeypatch, store_path):
        """AI 摘了个过短碎片，扩边后仍不足 5 字 → 退回原选区（L5）"""
        content = "前置句子。玩家划的这半句话还没有说完。后续。"
        start = content.index("玩家划的")
        end = start + 8
        outcome = _resolve(content, start, end, monkeypatch=monkeypatch,
                           verdict=service.AiVerdict(valid=True, card_type="观点",
                                                     selected_text="嗯"))
        assert outcome.hit is True
        assert outcome.resolved["path"] == "L5"
        assert len(outcome.text.strip()) >= service.MIN_CARD_TEXT

    def test_outcome_text_is_not_leaked_into_response(self, monkeypatch, store_path):
        """text 只供后端落盘，不进响应体（前端自己按 canonical range 切）"""
        content = "前置句子。这段文字是一个完整的句子内容。后续。"
        start = content.index("这段文字")
        end = content.index("。", start) + 1
        outcome = _resolve(content, start, end, monkeypatch=monkeypatch, verdict="fail")
        assert outcome.text
        assert "text" not in outcome.response
        assert "_resolved" not in outcome.response
        assert set(outcome.response) == {"hit", "matchRate", "source"}


# ══════════════════════════════════════════════════════════
#  7. HTTP 层：POST /api/cards/dynamic
# ══════════════════════════════════════════════════════════

def _load_payload(article_id: str = "article_1") -> dict:
    from game.api.article_generator import _load_article_payload

    payload = _load_article_payload(article_id)
    assert payload is not None, f"测试依赖的文章库缺失: {article_id}"
    return payload


def _find_gap_selection(payload: dict, length: int = 40):
    """找一段不与任何 linespot 重叠的选区（前端 convention：[start, end)）

    与 test_dynamic_card_store._iter_gap_slices 思路一致，但这里只需要一个可用选区，
    不需要枚举全部。两份而不抽公用：测试之间不引入导入耦合，且各自只需十行。
    """
    content = payload["content"]
    spots = sorted((int(s["start"]), int(s["end"])) for s in payload["linespots"])
    gap_starts = [0] + [end + 1 for (_, end) in spots]
    gap_ends = [start for (start, _) in spots] + [len(content)]
    for gap_start, gap_end in zip(gap_starts, gap_ends):
        if gap_end - gap_start < length:
            continue
        middle = (gap_start + gap_end) // 2
        start = max(0, min(middle - length // 2, len(content) - length))
        return start, start + length
    return None


def _find_long_gap_selection(min_length: int):
    """跨文章找一段 ≥min_length 字、不与任何 linespot 重叠的选区

    跨文章是必须的：单篇的空隙长度是内容的偶然属性，article_1 里未必有 201 字的
    连续空隙，只在一篇里找会让测试因样本不足而 skip（skip 不算失败，
    等于长期零覆盖）。返回 (payload, start, end)，全库都找不到才返回 None。
    """
    from game.api.api import _load_engine_articles
    from game.api.article_generator import _load_article_payload

    for article in _load_engine_articles():
        payload = _load_article_payload(article.id)
        if payload is None:
            continue
        found = _find_gap_selection(payload, length=min_length)
        if found is not None:
            return payload, found[0], found[1]
    return None


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from game.api.api import app

    return TestClient(app)


class TestHttpEndpoint:
    def test_new_endpoint_registered_without_touching_existing_ones(self, client):
        """硬约束：新端点注册后，其余在用端点一个不能少

        下面这份是删过一轮死端点之后的在用集合（共 12 个业务端点，
        /api/cards/dynamic 单独断言，/api/workspace/vectors 的 GET 与 POST
        共用一个 path）。已删除的 5 个在两个前端里零调用：
        GET /api/articles、GET /api/recipes、POST /api/compose、
        GET /api/events、POST /api/submit。
        删它们时同步改过本清单，所以这里少一个就意味着真的被误删了。
        """
        from game.api.api import app

        paths = {route.path for route in app.routes}
        assert "/api/cards/dynamic" in paths, "新端点未注册"
        existing = {
            "/api/articles/random", "/api/articles/generate",
            "/api/judge", "/api/health",
            "/api/workspace/vectors",
            "/api/ai/comment", "/api/ai/chat", "/api/ai/story", "/api/ai/hint",
            "/api/ai/composition-hint",
        }
        missing = existing - paths
        assert not missing, f"现有端点丢失: {missing}"

    def test_app_object_and_metadata_intact(self, client):
        """启动面：app 可从包顶层导入，且与模块里的是同一个对象

        这条原本是根目录 test_refactor.py 的 test_api_app。那个脚本的
        其余用例全在导入已删除的创作流模块（VectorSystem / ComposeEngine /
        RecipeSystem），已随模块一并移除；只有这条仍然有效，迁到这里保住覆盖。
        main_api.py 走的是 `from game.api import app` 与
        uvicorn.run("game.api:app")，靠的就是 game/api/__init__.py 的再导出；
        两边不是同一对象的话，启动的和测试的就不是同一个应用。
        """
        from game.api import app as pkg_app
        from game.api.api import app as mod_app

        assert pkg_app is mod_app, "game.api 再导出的 app 与 game.api.api.app 不是同一对象"
        assert pkg_app.title == "Zhihu Article Game API"

    def test_404_for_unknown_article(self, client, store_path):
        resp = client.post("/api/cards/dynamic", json={
            "articleId": "不存在的文章", "startOffset": 0, "endOffset": 40,
        })
        assert resp.status_code == 404

    def test_round_field_is_optional(self, client, store_path, monkeypatch):
        """round 不传也能跑（跳过配额检查），不因为缺字段把玩家挡在门外"""
        monkeypatch.setattr(service, "call_tongyi", lambda *a, **k: None)
        payload = _load_payload()
        start, end = _find_gap_selection(payload)
        resp = client.post("/api/cards/dynamic", json={
            "articleId": payload["id"], "startOffset": start, "endOffset": end,
        })
        assert resp.status_code == 200, resp.text

    def test_idempotent_guard_returns_preset_card(self, client, store_path):
        """直接调新端点但选区其实命中预设点 → 给预设卡，不重复建动态卡"""
        payload = _load_payload()
        spot = payload["linespots"][0]
        resp = client.post("/api/cards/dynamic", json={
            "articleId": payload["id"],
            "startOffset": int(spot["start"]),
            # linespot 是闭区间，前端 convention 为 [start, end) → end + 1
            "endOffset": int(spot["end"]) + 1,
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["hit"] is True
        assert body["source"] == "preset"
        assert "_dynamic_" not in body["card"]["card_id"]
        assert store.load_dynamic_card(body["card"]["card_id"]) is None, "预设卡不应落盘"

    def test_preset_branch_is_equivalent_to_judge(self, client, store_path):
        """两个端点的预设点分支必须逐字等价（除 source）

        前端已改成「先调 /api/cards/dynamic，它整体不可用才回落 /api/judge」。
        改调用顺序的原因是：judge 的 miss 分支自己就会建卡并落盘，先 judge
        再补调新端点会让同一次划线产生两张卡（文本不同 → L2 去重的 hash
        不命中 → 拦不住），而那张 judge 建的孤儿卡还会让玩家下次划同一句时
        被误判「该素材已经收集」。

        这个改法成立的前提是：**命中预设点时两个端点给出同一张卡**。
        等价性一旦被破坏（比如只改了其中一边的 25% 阈值、或 _spot_to_card_response
        的调用方式），预设卡行为就会静默漂移，而前端没有测试设施能发现。
        所以在这里钉死，让两个端点必须同步改。
        """
        payload = _load_payload()
        spot = payload["linespots"][0]
        request = {
            "articleId": payload["id"],
            # paragraphIndex 必须显式传：JudgeRequest 里它是**必填**（无默认值），
            # 而 DynamicCardRequest 给了 `= 0`。不传的话 judge 直接返 422，
            # 本测试就变成在比「422 vs 200」而不是比两个预设分支。
            "paragraphIndex": 0,
            "startOffset": int(spot["start"]),
            # linespot 是闭区间，前端 convention 为 [start, end) → end + 1
            "endOffset": int(spot["end"]) + 1,
        }
        judge_resp = client.post("/api/judge", json=request)
        dynamic_resp = client.post("/api/cards/dynamic", json=request)
        assert judge_resp.status_code == 200, judge_resp.text
        assert dynamic_resp.status_code == 200, dynamic_resp.text

        judge_body = judge_resp.json()
        dynamic_body = dynamic_resp.json()
        assert judge_body["hit"] is True, "样本选区应当命中预设点，否则本测试没验到东西"
        assert dynamic_body.pop("source") == "preset"
        assert dynamic_body == judge_body, (
            "两个端点的预设点分支不再等价：前端的调用顺序改造会直接改变预设卡行为。"
            f" judge={judge_body!r} dynamic={dynamic_body!r}"
        )

    def test_normal_length_selection_is_accepted(self, client, store_path, monkeypatch):
        """5-200 字的普通选区必须能建成卡

        这个长度带是前端改造后新增的主路径（以前只有 201-350 字能走到本端点，
        因为 judge 只在选区长度非法时才返 hit:false）。它占真实划线的绝大多数，
        一旦被门槛误挡，玩家几乎所有划线都会失败。
        """
        monkeypatch.setattr(service, "call_tongyi", lambda *a, **k: None)
        for length in (5, 40, 120, 200):
            # 跨文章找：单篇的空隙长度是内容的偶然属性，article_1 里没有
            # 200 字的连续空隙，只在一篇里找会让上限边界永远没被验到。
            found = _find_long_gap_selection(length)
            assert found is not None, f"全库找不到 {length} 字的空隙，换个长度"
            payload, start, end = found
            resp = client.post("/api/cards/dynamic", json={
                "articleId": payload["id"], "startOffset": start, "endOffset": end,
            })
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["hit"] is True, f"{length} 字选区被拒：{body.get('message')}"
            assert body["source"] == "local", "call_tongyi 已打桩成 None，应走 L6 本地降级"

    def test_ai_down_still_creates_card(self, client, store_path, monkeypatch):
        """L6 全链路：call_tongyi 返回 None 仍能建卡、扩到句边界、落盘

        这是整个方案的核心保证：AI 是纯增益层，不是关键路径。
        """
        monkeypatch.setattr(service, "call_tongyi", lambda *a, **k: None)
        payload = _load_payload()
        start, end = _find_gap_selection(payload)
        content = payload["content"]

        resp = client.post("/api/cards/dynamic", json={
            "articleId": payload["id"], "startOffset": start, "endOffset": end, "round": 1,
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()

        if body["hit"] is False:
            # 选区本身质量不够（L1）也是合理结果，但不能是报错
            assert body["message"] in (service.MSG_NO_MATERIAL,
                                       service.MSG_TOO_SHORT_OR_LONG)
            assert body["source"] == "local"
            return

        assert body["source"] == "local"
        card = body["card"]
        assert "_dynamic_" in card["card_id"]
        # 句边界扩展已生效：canonical range 比玩家原选区宽（或正好已在句边界）
        assert card["start"] <= start
        assert card["end"] + 1 >= end
        final_text = content[card["start"]:card["end"] + 1]
        assert len(final_text.strip()) >= service.MIN_CARD_TEXT
        assert validate_card_vector(normalize_card_type(card["card_type"]),
                                    card["attribute_x"], card["attribute_y"]) == []

        # 落盘带 round，配额能按局分区计数
        record = store.load_dynamic_card(card["card_id"])
        assert record is not None
        assert record["round"] == 1
        assert record["text"] == final_text

    def test_response_is_judge_dto_isomorphic(self, client, store_path, monkeypatch):
        """前端 adaptJudgeResult / adaptSaltCard 能直接吃这个响应体

        关键：card.end 必须是闭区间，adaptSaltCard 会做 canonicalEndOffset = dto.end + 1。
        这是唯一允许发生 inclusive/exclusive 转换的协议边界，搞错就会整段偏移一位。
        """
        monkeypatch.setattr(service, "call_tongyi", lambda *a, **k: None)
        payload = _load_payload()
        start, end = _find_gap_selection(payload)

        resp = client.post("/api/cards/dynamic", json={
            "articleId": payload["id"], "startOffset": start, "endOffset": end,
        })
        body = resp.json()
        assert set(body) >= {"hit", "matchRate"}, "缺 JudgeResultDto 必需字段"
        if body["hit"]:
            assert set(body["card"]) >= {"card_id", "attribute_value", "card_type",
                                         "start", "end"}
            assert body["card"]["card_type"].endswith("卡"), "协议出口必须带「卡」后缀"
            assert body["card"]["end"] >= body["card"]["start"]
            # 与 /api/judge 动态卡分支逐字段对齐（多一个 source 是有意为之）
            judge = client.post("/api/judge", json={
                "articleId": payload["id"], "paragraphIndex": 0,
                "startOffset": start, "endOffset": end,
            }).json()
            if judge["hit"] and "_dynamic_" in judge["card"]["card_id"]:
                assert set(judge["card"]) == set(body["card"])
        else:
            assert isinstance(body["message"], str) and body["message"]

    def test_over_judge_limit_passes_here_but_not_in_judge(self, client, store_path,
                                                           monkeypatch):
        """同一段 201+ 字选区：/api/judge 拒、本端点放行——两个门槛刻意不同

        /api/judge 的 200 是 api.py 里的硬编码字面量，那边没有 AI，放宽就等于
        允许直接拿整段当卡牌。本端点会把长选区交给 AI 收敛出核心句。
        这条钉住两边不被「顺手统一」成同一个常量，并同时验证产出仍 ≤200。
        """
        monkeypatch.setattr(service, "call_tongyi", lambda *a, **k: None)  # 不烧额度
        found = _find_long_gap_selection(201)
        assert found is not None, "全库找不到 201 字的 linespot 空隙，无法构造对比用例"
        payload, start, end = found

        judge = client.post("/api/judge", json={
            "articleId": payload["id"], "paragraphIndex": 0,
            "startOffset": start, "endOffset": end,
        }).json()
        assert judge["hit"] is False
        assert judge["message"] == "选区过短或过长，请重新划线", (
            f"/api/judge 的 200 上限被改动了？实际 message={judge['message']!r}"
        )

        dynamic = client.post("/api/cards/dynamic", json={
            "articleId": payload["id"], "startOffset": start, "endOffset": end,
        }).json()
        if dynamic["hit"]:
            # AI 被打桩成失败，走 L6 截断路径：放行但产出必须钳在上限内
            card = dynamic["card"]
            final_len = card["end"] + 1 - card["start"]
            assert final_len <= service.MAX_CARD_TEXT, (
                f"放行后产出 {final_len} 字的卡，超出产出上限 {service.MAX_CARD_TEXT}"
            )
        else:
            assert dynamic["message"] != "选区过短或过长，请重新划线", (
                "本端点不该再用 200 拒长选区，否则放宽入参门槛的改动失效"
            )

    def test_l1_rejection_never_calls_ai(self, client, store_path, monkeypatch):
        """L1 拒绝走 HTTP 也不得调 AI（省钱，也避免白耗 15s 延迟）

        触发条件用「过短」而不是「纯标点」：过短在任何文章里都必然可构造
        （从已知空隙里切 2 个字），而「连续 6 字纯标点」是文章内容的偶然属性——
        原先按纯标点找，article_1 里找不到就 pytest.skip，等于这条 HTTP 层断言
        长期零覆盖（skip 不算失败，没人会发现）。纯标点分支由
        TestCheckSelectionQuality 的单元测试覆盖，两边不重叠。
        """
        def _boom(*args, **kwargs):
            raise AssertionError("L1 拒绝不该调 AI")

        monkeypatch.setattr(service, "call_tongyi", _boom)
        payload = _load_payload()
        gap = _find_gap_selection(payload, length=2)
        assert gap is not None, "article_1 里找不到任何 linespot 空隙，无法构造 L1 选区"
        start, _ = gap
        # 2 字 < MIN_CARD_TEXT(5)，且落在已知空隙里（与所有 linespot 零重叠），
        # 因此不会被端点开头的预设点幂等分支截走，必然走到 resolve_dynamic_selection。
        resp = client.post("/api/cards/dynamic", json={
            "articleId": payload["id"], "startOffset": start, "endOffset": start + 2,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["hit"] is False
        assert body["message"] == service.MSG_TOO_SHORT_OR_LONG
        assert body["source"] == "local"
        # matchRate 必须在：前端 DynamicCardResultDto 的 hit:false 分支把它定为必填
        assert body["matchRate"] == 0

    def test_no_quota_enforcement_on_backend(self, client, store_path, monkeypatch):
        """配额检查已移至前端：后端不再因配额拒绝请求"""
        payload = _load_payload()
        start, end = _find_gap_selection(payload)
        # 落盘 20 张卡（远超旧配额的 10 张）
        for index in range(20):
            store.save_dynamic_card(
                {"card_id": f"article_1_dynamic_观点_abcd{index:04d}_{index}",
                 "card_type": "观点卡", "start": start, "end": end - 1,
                 "attribute_value": 12, "attribute_x": 32.0, "attribute_y": 32.0,
                 "round": 7},
                f"配额占位文本 {index}", round_no=7,
            )

        # 后端应继续处理（会调 AI），不因配额拒绝
        resp = client.post("/api/cards/dynamic", json={
            "articleId": payload["id"], "startOffset": start, "endOffset": end, "round": 7,
        })
        assert resp.status_code == 200
        body = resp.json()
        # 不应返回配额满的错误
        assert "上限" not in body.get("message", "")

    def test_ai_success_path_end_to_end(self, client, store_path, monkeypatch):
        """L4 全链路：伪造一个带 markdown 围栏的 AI 响应，验证净化+回查+扩边+落盘"""
        payload = _load_payload()
        content = payload["content"]
        start, end = _find_gap_selection(payload)
        # AI 只摘选区前半段且未含句末标点，后端应把它扩到完整句。
        # 去掉双引号（会破坏手拼的 JSON 结构），但**刻意保留裸换行**——
        # 那是 AI 摘录中文原文时的真实失败模式，正好一并钉住 strict=False。
        ai_text = content[start:start + 12].replace('"', "")
        fence = ('```json\n{"valid": true, "card_type": "情绪", '
                 f'"selected_text": "{ai_text}", "reason": "共鸣金句", '
                 '"vector_x": 99, "attribute_value": 42}\n```')
        monkeypatch.setattr(service, "call_tongyi", lambda *a, **k: fence)

        resp = client.post("/api/cards/dynamic", json={
            "articleId": payload["id"], "startOffset": start, "endOffset": end, "round": 2,
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["hit"] is True, body
        assert body["source"] == "ai", f"JSON 净化或回查失败导致降级: {body}"
        card = body["card"]
        assert normalize_card_type(card["card_type"]) == "情绪"
        # AI 违规输出的数值必须被忽略（红线②），改用 card_rules 派生的合规值
        assert validate_card_vector("情绪", card["attribute_x"], card["attribute_y"]) == []
        assert card["attribute_x"] != 99
        assert card["attribute_value"] != 42, "attribute_value 也不得采信 AI"
        # 句边界扩展：AI 摘的片段被补到完整句（只会变长，不会变短）
        final_text = content[card["start"]:card["end"] + 1]
        assert ai_text.strip() in final_text or final_text.startswith(ai_text.strip()[:6])
        assert len(final_text) >= len(ai_text.strip())
        assert store.load_dynamic_card(card["card_id"])["text"] == final_text

    def test_created_card_flows_into_article_generation(self, client, store_path, monkeypatch):
        """端到端：新端点建的卡能直接进局末文章生成（第0步链路的验收）"""
        monkeypatch.setattr(service, "call_tongyi", lambda *a, **k: None)
        payload = _load_payload()
        start, end = _find_gap_selection(payload)

        body = client.post("/api/cards/dynamic", json={
            "articleId": payload["id"], "startOffset": start, "endOffset": end, "round": 4,
        }).json()
        if body["hit"] is False:
            pytest.skip("选区被 L1 门槛拦下，换一个空隙即可（不影响本用例意图）")

        card_id = body["card"]["card_id"]
        # 模拟后端重启：session 缓存清空，只能靠落盘恢复
        from game.api.session import get_session

        get_session().clear_cards_cache()

        gen = client.post("/api/articles/generate", json={
            "slots": [["9", card_id]], "use_ai": False,
        })
        assert gen.status_code == 200, gen.text
        result = gen.json()
        assert len(result["paragraphs"]) == len(result["blueprint"])
        stored_text = store.load_dynamic_card(card_id)["text"]
        if normalize_card_type(body["card"]["card_type"]) == "观点":
            assert result["content"].strip(), "全动态卡矩阵不得产出空文章"
            assert stored_text[:12] in result["content"]
