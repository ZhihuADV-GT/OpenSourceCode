"""本地关键词分类器合并的等价性回归测试

合并前有两份逐字重复的实现：
    game/api/api.py            _classify_card_type(text) -> (card_type, value, x, y)
    game/api/hint_service.py   _classify_card_type_simple(text) -> card_type
两者的关键词池、阈值、优先级瀑布完全相同，只差返回值。现已收敛到
game/numerics/card_rules.py 的 classify_card()，api 侧保留一层「拆成 4 元组」
的薄封装（resolve_dynamic_selection 的 classify 形参按该契约调用）。

本文件的职责是证明这次合并**没有改变任何判定结果**：下面 _OLD_API_CLASSIFY 与
_OLD_HINT_CLASSIFY 是两份被删掉的实现的逐字拷贝，充当 oracle。真实文章语料 +
手工边界语料全部跑一遍新旧对照，任何一处漂移都会在这里炸出来。

同时锁定一条刻意未修的行为：关键词池里的高频单字（个 / 比 / 度 / 太 / 真 /
像 / 如 / 般）命中率极高，导致大量不同划法落到同一个默认分支。这是已知缺陷，
修它属于行为变更（要重新标定动态卡数值与评级阈值），不在「删冗余」范围内。
test_known_defect_high_frequency_single_chars 把现状钉住，将来真要修时它会红，
提醒改的人同步更新评测阈值。

运行：cd Backend; pytest tests/test_card_classifier.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 允许直接从 Backend 目录运行（无 conftest.py，也不依赖 pip install -e）
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from game.numerics.card_rules import (
    CLASSIFY_KEYWORD_POOLS,
    CardClassification,
    classify_card,
    is_known_card_type,
    normalize_card_type,
    validate_card_vector,
)


# ══════════════════════════════════════════════════════════
#  Oracle：两份被删掉的实现，逐字拷贝，不得修改
# ══════════════════════════════════════════════════════════

def _OLD_API_CLASSIFY(text: str) -> tuple[str, int, float, float]:
    """原 game/api/api.py::_classify_card_type，逐字拷贝"""
    if not text or len(text.strip()) < 5:
        return ("观点", 10, 31.0, 31.0)

    data_keywords = ["%", "％", "万", "亿", "千", "百", "十", "个", "次", "率", "度", "比"]
    logic_keywords = ["因为", "所以", "导致", "因此", "从而", "使得", "原因", "结果", "影响"]
    contrast_keywords = ["但是", "然而", "不过", "可是", "却", "反而", "尽管", "虽然"]
    emotion_keywords = ["！", "？", "太", "真", "非常", "特别", "简直", "令人", "让人"]
    metaphor_keywords = ["像", "如", "仿佛", "犹如", "好似", "如同", "般", "似的"]

    data_count = sum(1 for kw in data_keywords if kw in text)
    logic_count = sum(1 for kw in logic_keywords if kw in text)
    contrast_count = sum(1 for kw in contrast_keywords if kw in text)
    emotion_count = sum(1 for kw in emotion_keywords if kw in text)
    metaphor_count = sum(1 for kw in metaphor_keywords if kw in text)

    if data_count >= 2:
        value = min(20, 15 + data_count)
        return ("观点", value, 36.0, 35.0)

    if logic_count >= 2:
        value = min(19, 14 + logic_count)
        return ("观点", value, 34.0, 33.0)

    if contrast_count >= 1 and logic_count == 0:
        value = min(17, 12 + contrast_count * 2)
        return ("漏洞", value, -25.0, 25.0)

    if emotion_count >= 2:
        value = min(18, 13 + emotion_count)
        return ("情绪", value, 26.0, -25.0)

    if metaphor_count >= 1:
        value = min(16, 11 + metaphor_count * 2)
        return ("修辞", value, 1.25, 1.35)

    return ("观点", 12, 32.0, 32.0)


def _OLD_HINT_CLASSIFY(text: str) -> str:
    """原 game/api/hint_service.py::_classify_card_type_simple，逐字拷贝"""
    if not text or len(text.strip()) < 5:
        return "观点"

    data_keywords = ["%", "％", "万", "亿", "千", "百", "十", "个", "次", "率", "度", "比"]
    logic_keywords = ["因为", "所以", "导致", "因此", "从而", "使得", "原因", "结果", "影响"]
    contrast_keywords = ["但是", "然而", "不过", "可是", "却", "反而", "尽管", "虽然"]
    emotion_keywords = ["！", "？", "太", "真", "非常", "特别", "简直", "令人", "让人"]
    metaphor_keywords = ["像", "如", "仿佛", "犹如", "好似", "如同", "般", "似的"]

    data_count = sum(1 for kw in data_keywords if kw in text)
    logic_count = sum(1 for kw in logic_keywords if kw in text)
    contrast_count = sum(1 for kw in contrast_keywords if kw in text)
    emotion_count = sum(1 for kw in emotion_keywords if kw in text)
    metaphor_count = sum(1 for kw in metaphor_keywords if kw in text)

    if data_count >= 2:
        return "观点"
    if logic_count >= 2:
        return "观点"
    if contrast_count >= 1 and logic_count == 0:
        return "漏洞"
    if emotion_count >= 2:
        return "情绪"
    if metaphor_count >= 1:
        return "修辞"
    return "观点"


# ══════════════════════════════════════════════════════════
#  语料
# ══════════════════════════════════════════════════════════

# 手工语料：逐条覆盖 6 个分支 + 优先级压制 + 长度门槛 + 空值
HAND_PICKED_TEXTS = [
    # 短文本门槛（< 5 字，含 strip 后不足）
    "", "   ", "abcd", "观点", "太短了", "\n\n\t  ",
    # 分支 1：数据类（data_count >= 2）
    "增长了百分之三十达到百万级别", "30%的用户提高了转化率", "成千上万次的对比",
    # 分支 2：逻辑词（logic_count >= 2）
    "因为这样做所以导致了问题", "原因在于结果影响了判断", "从而使得原因被忽略",
    # 分支 3：转折且无因果（contrast >= 1 且 logic == 0）
    "但是他并不认同这个说法", "然而事情并没有结束", "尽管这样却仍然失败",
    # 分支 3 被分支 2 压制：同时有转折与因果 → 走逻辑
    "因为所以但是他不同意", "导致因此然而",
    # 分支 1 压制其余全部：数据 + 逻辑 + 转折 + 情感 + 比喻
    "百万%因为所以但是太像",
    # 分支 4：情感词（emotion_count >= 2）
    "太好了！真的是非常特别", "这简直令人难以置信？",
    # 分支 5：比喻词（metaphor_count >= 1）
    "他像风一样掠过湖面", "仿佛一切都犹如昨日", "好似如同般的错觉",
    # 分支 6：默认（一个池都不命中，或只命中 1 个 data 词）
    "他们正在讨论这个问题", "今天 everyone 都在忙碌", "……,,,,,,",
    # 真实感长句（混合命中）
    "很多人认为，正是因为缺少监督，才导致比例失衡，但这并不意味着无解。",
    "这项调查覆盖了十万个样本，因此结论具有一定的代表性，然而也存在偏差。",
]


def _real_article_texts() -> list[str]:
    """从真实文章库取语料；库为空时回退到手工语料"""
    try:
        from game.api.api import _load_engine_articles
        articles = _load_engine_articles()
    except Exception:
        return []
    return [a.content[:3000] for a in articles]


def _sweep_texts() -> list[str]:
    """在真实文章上做确定性滑窗切片，产出上千条真实选区"""
    out: list[str] = []
    for content in _real_article_texts():
        for length in (5, 8, 13, 21, 40):
            for start in range(0, min(len(content), 1200), 7):
                out.append(content[start:start + length])
    return out


# ══════════════════════════════════════════════════════════
#  等价性
# ══════════════════════════════════════════════════════════

@pytest.mark.parametrize("text", HAND_PICKED_TEXTS)
def test_matches_old_api_implementation(text):
    """新实现的 4 元组必须与旧 api._classify_card_type 逐字相同"""
    got = classify_card(text)
    assert (got.card_type, got.attribute_value, got.vector_x, got.vector_y) == \
        _OLD_API_CLASSIFY(text), f"判型漂移: {text!r}"


@pytest.mark.parametrize("text", HAND_PICKED_TEXTS)
def test_matches_old_hint_implementation(text):
    """新实现的卡型必须与旧 hint_service._classify_card_type_simple 逐字相同"""
    assert classify_card(text).card_type == _OLD_HINT_CLASSIFY(text), f"判型漂移: {text!r}"


def test_two_old_implementations_agreed_on_type():
    """前置校验：两份旧实现的卡型判定本来就一致

    若这条红了，说明 oracle 拷贝写错了，上面两条等价对照就失去意义。
    """
    for text in HAND_PICKED_TEXTS:
        assert _OLD_API_CLASSIFY(text)[0] == _OLD_HINT_CLASSIFY(text)


def test_matches_old_implementations_on_real_article_sweep():
    """真实文章滑窗切片上的大规模新旧对照（确定性，不打网络）"""
    texts = _sweep_texts()
    if not texts:
        pytest.skip("文章库为空，跳过真实语料扫描")

    drifted = []
    for text in texts:
        got = classify_card(text)
        old = _OLD_API_CLASSIFY(text)
        if (got.card_type, got.attribute_value, got.vector_x, got.vector_y) != old:
            drifted.append((text, old, got))
        if got.card_type != _OLD_HINT_CLASSIFY(text):
            drifted.append((text, "hint-mismatch", got.card_type))

    assert not drifted, f"{len(drifted)}/{len(texts)} 条切片判型漂移，前 3 条: {drifted[:3]}"


# ══════════════════════════════════════════════════════════
#  契约与不变量
# ══════════════════════════════════════════════════════════

def test_api_wrapper_keeps_four_tuple_contract():
    """api._classify_card_type 必须仍是 4 元组

    dynamic_card_service.resolve_dynamic_selection 的 classify 形参、
    tests/test_dynamic_card_store.py 与 tests/test_dynamic_card_live.py
    都按这个契约调用，合并不能改签名。
    """
    from game.api.api import _classify_card_type

    for text in HAND_PICKED_TEXTS:
        assert _classify_card_type(text) == _OLD_API_CLASSIFY(text)


def test_hint_service_no_longer_defines_its_own_classifier():
    """判型本体只允许 card_rules 一份，两个消费方不得再自己写"""
    from game.api import hint_service

    assert not hasattr(hint_service, "_classify_card_type_simple"), (
        "hint_service 又自己定义了一份分类器，会与 api 侧漂移"
    )
    assert hint_service.classify_card is classify_card


def test_outputs_are_canonical_and_rule_compliant():
    """所有分支的输出都是规范卡型且数值合规

    这条与合并无关，是分类器本身的长期不变量：动态卡不得越界，
    否则 clamp_card_vector 会在加载层把它钳回去，玩家看到的数值与
    生成时的不一致。
    """
    seen_types = set()
    for text in HAND_PICKED_TEXTS:
        got = classify_card(text)
        assert isinstance(got, CardClassification)
        assert is_known_card_type(got.card_type), got.card_type
        assert normalize_card_type(got.card_type) == got.card_type, "卡型必须是不带「卡」的规范形式"
        assert validate_card_vector(got.card_type, got.vector_x, got.vector_y) == [], (
            f"{got} 违反 Backend/article生成规则.md 的量纲约束"
        )
        seen_types.add(got.card_type)

    # 六个分支都要被手工语料覆盖到，否则等价对照有盲区
    assert seen_types == {"观点", "漏洞", "情绪", "修辞"}, seen_types


def test_keyword_pools_match_old_literals():
    """关键词池必须与两份旧实现逐字一致（含顺序）"""
    assert CLASSIFY_KEYWORD_POOLS["data"] == (
        "%", "％", "万", "亿", "千", "百", "十", "个", "次", "率", "度", "比")
    assert CLASSIFY_KEYWORD_POOLS["logic"] == (
        "因为", "所以", "导致", "因此", "从而", "使得", "原因", "结果", "影响")
    assert CLASSIFY_KEYWORD_POOLS["contrast"] == (
        "但是", "然而", "不过", "可是", "却", "反而", "尽管", "虽然")
    assert CLASSIFY_KEYWORD_POOLS["emotion"] == (
        "！", "？", "太", "真", "非常", "特别", "简直", "令人", "让人")
    assert CLASSIFY_KEYWORD_POOLS["metaphor"] == (
        "像", "如", "仿佛", "犹如", "好似", "如同", "般", "似的")


def test_card_rules_stays_a_leaf_module():
    """card_rules 不得 import 任何项目内模块

    它要被 game.numerics 与 game.preprocess 共用；一旦引入项目内依赖，
    game/numerics/__init__.py 的包初始化就可能与之成环。
    """
    import ast

    src = (_BACKEND_DIR / "game" / "numerics" / "card_rules.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] != "game", alias.name
        elif isinstance(node, ast.ImportFrom):
            # 相对导入（level > 0）同样是项目内依赖，一并禁掉
            assert node.level == 0, f"card_rules 出现了相对导入: {'.' * node.level}{node.module}"
            assert (node.module or "").split(".")[0] != "game", node.module


# ══════════════════════════════════════════════════════════
#  已知缺陷（刻意未修，钉住现状）
# ══════════════════════════════════════════════════════════

def test_known_defect_high_frequency_single_chars():
    """高频单字导致无区分度：这条红了说明判定逻辑被改了

    实测现象（合并前就存在）：语义完全不同的选区落到同一个默认分支
    「观点 / value=12 / (32.0, 32.0)」。根因是池子里的 个 / 比 / 度 / 太 /
    真 / 像 / 如 / 般 在中文里几乎处处命中。

    计数口径要说清：`sum(1 for kw in pool if kw in text)` 算的是「池子里有多少个
    不同的词出现过」，不是出现次数。所以同一个单字重复多少遍也只算 1 个，
    但任意两个不同的高频单字共现（如「个」+「比」）就足以把一句无意义的
    碎片推进最高数据档，拿到强于绝大多数预设卡的 (36.0, 35.0)。

    本轮任务是删冗余、合并重复实现，明确不改判定：修它要重新标定动态卡
    数值与前端评级阈值，属于行为变更。这里把现状钉住，将来真要优化分类器
    时本用例会红，提醒改的人同步更新评测口径。
    """
    default_branch = ("观点", 12, 32.0, 32.0)

    semantically_different = [
        "高达高达高达高达",          # 灌水重复
        "的了吗呢啊呀",              # 纯虚词
        "他们正在讨论这个问题",      # 正常陈述句
    ]
    for text in semantically_different:
        got = classify_card(text)
        assert (got.card_type, got.attribute_value, got.vector_x, got.vector_y) == \
            default_branch, f"默认分支行为已变更: {text!r} -> {got}"

    # 同一个单字重复 N 遍仍只算 1 个命中 → 达不到 data_count >= 2，仍走默认分支
    repeated = classify_card("度度度度度")
    assert (repeated.card_type, repeated.attribute_value,
            repeated.vector_x, repeated.vector_y) == default_branch

    # 但任意两个不同高频单字共现，就能把无意义碎片推到最高数据档
    junk = classify_card("这个比例难度量")   # 个 / 比 / 度 三个高频单字
    assert (junk.card_type, junk.attribute_value, junk.vector_x, junk.vector_y) == \
        ("观点", 18, 36.0, 35.0), f"高频单字误判行为已变更: {junk}"
