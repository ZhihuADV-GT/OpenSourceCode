"""真实 AI 联调：POST /api/cards/dynamic 的 AI 判定路径

默认跳过。跑一次要真实调用通义千问（消耗额度、单次 2-15s），显式开启：

    $env:LIVE_AI="1"; python -m pytest tests/test_dynamic_card_live.py -q -s

与 test_dynamic_card_service.py 的根本区别：那边把 call_tongyi 全部 monkeypatch 掉，
这边**不打桩**，就是要看 qwen-turbo 在 DYNAMIC_CARD_TEMPERATURE 下的真实输出。

观测四件单元测试覆盖不到的事：
1. selected_text 回查成功率 —— AI 是否真的逐字摘录（改一个字就降级到 L5）
2. JSON 格式稳定性 —— 三级净化 + strict=False 够不够
3. 单次耗时 —— 是否落在后端 15s 预算 / 前端 20s 超时之内
4. 判型区分度 —— 是否比本地关键词池（实测 13 种划法 12 种同解）更有信息量

本文件不断言 AI 的判定结果对不对：模型输出天然不确定，硬断言会让测试变成 flaky。
断言只覆盖两条确定性契约——AI 可达、耗时在预算内。成功率一律打印出来人工读。
"""

from __future__ import annotations

import os
import time

import pytest

from game.api import dynamic_card_service as service
from game.api import dynamic_card_store as store
from game.api.llm_config import (
    DYNAMIC_CARD_TEMPERATURE,
    TONGYI_MODEL_DYNAMIC_CARD,
    TONGYI_TIMEOUT_DYNAMIC_CARD,
)
from game.numerics.card_rules import normalize_card_type

pytestmark = pytest.mark.skipif(
    not os.environ.get("LIVE_AI"),
    reason="真实 AI 联调会消耗通义额度，需显式设置 LIVE_AI=1 才跑",
)


# ══════════════════════════════════════════════════════════
#  夹具：真调 AI，但把原始输出与耗时录下来
# ══════════════════════════════════════════════════════════

@pytest.fixture
def store_path(tmp_path, monkeypatch):
    """落盘重定向到 tmp，联调产生的卡不许污染真实 article_lib"""
    path = tmp_path / "dynamic_cards.json"
    monkeypatch.setattr(store, "STORE_PATH", path)
    store.reset_cache()
    yield path
    store.reset_cache()


@pytest.fixture
def ai_recorder(monkeypatch):
    """真调 call_tongyi，同时录下每次的原始输出、耗时、解析结果

    不打桩、不改行为，只是包一层观测。record["raw"] 是模型的原文，
    这是判断「JSON 净化够不够」「AI 有没有逐字摘录」的唯一依据。
    """
    records: list[dict] = []
    real_call = service.call_tongyi

    def _recording_call(*args, **kwargs):
        started = time.perf_counter()
        raw = real_call(*args, **kwargs)
        elapsed = time.perf_counter() - started
        records.append({
            "raw": raw,
            "elapsed": elapsed,
            "parsed": service.parse_card_json(raw) if raw else None,
            "prompt_chars": len(args[1]) if len(args) > 1 else kwargs.get("user_prompt", ""),
        })
        return raw

    monkeypatch.setattr(service, "call_tongyi", _recording_call)
    return records


@pytest.fixture
def classify():
    """用真实的本地关键词分类器，联调要走完整链路"""
    from game.api.api import _classify_card_type

    return _classify_card_type


def _load_content(article_id: str = "article_1") -> str:
    from game.api.article_generator import _load_article_payload

    payload = _load_article_payload(article_id)
    assert payload is not None, f"联调依赖的文章库缺失: {article_id}"
    return payload["content"]


# ══════════════════════════════════════════════════════════
#  选区构造：按句末标点切分
# ══════════════════════════════════════════════════════════

def _split_sentences(content: str, min_chars: int = 12):
    """切出 (start, end) 句子列表，end 含句末标点本身

    刻意复用 service._SENTENCE_ENDINGS：这样「我构造的完整句」与
    「后端句边界扩展认的句边界」是同一个口径，不然观测结果会自相矛盾
    （我以为给了完整句，后端却觉得还差半句）。
    """
    spans = []
    start = 0
    for index, char in enumerate(content):
        if char not in service._SENTENCE_ENDINGS:
            continue
        span = content[start:index + 1]
        # 过滤掉换行/短标题/纯标点碎片，只留真正有内容的句子
        if len(span.strip()) >= min_chars and service._MEANINGFUL_CHAR.search(span):
            spans.append((start, index + 1))
        start = index + 1
    return spans


def _pick_probes(content: str) -> list[tuple[str, int, int]]:
    """挑 6 种典型划法，返回 (标签, start, end)

    全部从真实文章里切，不手写字面量：手写文本会让 AI 面对「文章里不存在的句子」，
    观测到的行为与线上不一致。
    """
    sentences = _split_sentences(content)
    assert len(sentences) >= 4, f"article_1 只切出 {len(sentences)} 句，样本不足"

    # 完整句：挑一个中等长度的，太短没信息量、太长超 MAX_CARD_TEXT
    full = next(
        (s for s in sentences if 20 <= s[1] - s[0] <= 60),
        sentences[len(sentences) // 2],
    )
    head_start, head_end = full
    middle = (head_start + head_end) // 2

    probes = [
        # 玩家划得很准 —— 期望 AI 原样返回，path=L4
        ("完整句", head_start, head_end),
        # 没头：从句中划到句末 —— 期望 AI 向左补出主语
        ("没头半句", middle, head_end),
        # 没尾：从句首划到句中 —— 期望 AI 向右补到句末
        ("没尾半句", head_start, middle),
    ]

    # 跨两句：期望 AI 挑核心句而不是照抄两段
    index = sentences.index(full)
    if index + 1 < len(sentences):
        next_start, next_end = sentences[index + 1]
        probes.append(("跨两句", head_start, next_end))

    # 长段（超 MAX_CARD_TEXT=200）：期望 AI 收敛到 10-120 字的核心句
    long_start = head_start
    long_end = min(len(content), head_start + 260)
    if long_end - long_start > service.MAX_CARD_TEXT:
        probes.append(("超长选区", long_start, long_end))

    # linespot 空隙：预设要点之外的过渡句，最可能被 AI 判 valid=false
    gap = _find_gap(content, 24)
    if gap is not None:
        probes.append(("要点空隙", gap[0], gap[1]))

    return probes


def _find_gap(content: str, length: int = 24):
    """找一段不与任何 linespot 重叠的选区（低价值文本的候选）"""
    from game.api.article_generator import _load_article_payload

    payload = _load_article_payload("article_1")
    if payload is None:
        return None
    spots = sorted((int(s["start"]), int(s["end"])) for s in payload.get("linespots", []))
    gap_starts = [0] + [end + 1 for (_, end) in spots]
    gap_ends = [start for (start, _) in spots] + [len(content)]
    for gap_start, gap_end in zip(gap_starts, gap_ends):
        if gap_end - gap_start < length:
            continue
        middle = (gap_start + gap_end) // 2
        start = max(0, min(middle - length // 2, len(content) - length))
        candidate = content[start:start + length]
        if service._MEANINGFUL_CHAR.search(candidate):
            return start, start + length
    return None


# ══════════════════════════════════════════════════════════
#  联调
# ══════════════════════════════════════════════════════════

def test_ai_reachable_and_within_budget(ai_recorder, store_path, classify):
    """门槛测试：key/网络可用，且单次耗时落在后端预算内

    单独一个测试而不是并进矩阵里：key 失效或端点不通时这里就快速失败，
    不必白等 6 次超时（6 × 15s = 90s）。
    """
    content = _load_content()
    start, end = _split_sentences(content)[0]

    started = time.perf_counter()
    outcome = service.resolve_dynamic_selection(
        article_id="article_1", content=content,
        start=start, end=end, classify=classify,
    )
    total = time.perf_counter() - started

    assert ai_recorder, "根本没有发起 AI 调用，说明被 L1/L2/L3 提前拒了，联调无效"
    record = ai_recorder[0]
    assert record["raw"] is not None, (
        "call_tongyi 返回 None：API key 失效、端点不通或额度耗尽，"
        "看上面 [ai_service] 的日志行"
    )
    assert record["elapsed"] < TONGYI_TIMEOUT_DYNAMIC_CARD, (
        f"单次 AI 耗时 {record['elapsed']:.2f}s 已超后端预算 "
        f"{TONGYI_TIMEOUT_DYNAMIC_CARD}s，前端 20s 超时会跟着穿透"
    )

    print(f"\n{'=' * 66}")
    print(f"模型={TONGYI_MODEL_DYNAMIC_CARD}  temperature={DYNAMIC_CARD_TEMPERATURE}")
    print(f"单次 AI 耗时={record['elapsed']:.2f}s  端到端={total:.2f}s  "
          f"后端预算={TONGYI_TIMEOUT_DYNAMIC_CARD}s")
    print(f"AI 原文: {record['raw']}")
    print(f"净化后:  {record['parsed']}")
    print(f"判定:    hit={outcome.hit} "
          f"path={(outcome.resolved or {}).get('path')} "
          f"source={outcome.response.get('source')}")
    print(f"{'=' * 66}")


def test_probe_matrix(ai_recorder, store_path, classify):
    """6 种典型划法的真实表现，末尾打汇总统计

    不传 round_no：本轮只观测 AI 路径，不想让 L3 配额把用例挡掉。
    """
    content = _load_content()
    probes = _pick_probes(content)
    rows = []

    for label, start, end in probes:
        before = len(ai_recorder)
        try:
            outcome = service.resolve_dynamic_selection(
                article_id="article_1", content=content,
                start=start, end=end, classify=classify,
            )
        except Exception as exc:  # 联调要的是观测，不是让一个用例炸掉整轮
            rows.append((label, "EXC", "-", 0.0, str(exc)[:60]))
            print(f"\n[{label}] 抛异常: {type(exc).__name__}: {exc}")
            continue

        called = len(ai_recorder) > before
        record = ai_recorder[-1] if called else None
        resolved = outcome.resolved or {}
        path = resolved.get("path", "-")
        elapsed = record["elapsed"] if record else 0.0

        print(f"\n{'─' * 66}")
        print(f"[{label}] 选区[{start}:{end}] ({end - start}字)")
        print(f"  玩家划的: 「{content[start:end][:70]}」")
        if record:
            print(f"  AI 原文({elapsed:.2f}s): {record['raw']}")
            print(f"  净化后: {record['parsed']}")
        else:
            print("  未调 AI（被 L1/L2/L3 提前拒）")
        print(f"  → hit={outcome.hit} path={path} "
              f"source={outcome.response.get('source') or outcome.response.get('message')}")
        if outcome.hit:
            print(f"  卡型={resolved.get('type')} 向量=({resolved.get('x')}, {resolved.get('y')})")
            print(f"  最终区间[{resolved.get('start')}:{resolved.get('end')}] "
                  f"「{outcome.text[:80]}」")
            # 回查是否成功 = AI 摘的文本有没有真的落在最终区间里
            located = "是" if path == "L4" else "否(降级用玩家原选区)"
            print(f"  selected_text 回查成功: {located}")
        rows.append((label, path, outcome.response.get("source", "-"), elapsed,
                     resolved.get("type", outcome.response.get("message", ""))[:20]))

    # ── 汇总 ──
    total = len(rows)
    l4 = sum(1 for r in rows if r[1] == "L4")
    parsed_ok = sum(1 for r in ai_recorder if r["parsed"] is not None)
    slowest = max((r["elapsed"] for r in ai_recorder), default=0.0)
    types = {r[4] for r in rows if r[1] in ("L4", "L5", "L6")}

    print(f"\n{'=' * 66}")
    print(f"汇总：{total} 种划法，AI 调用 {len(ai_recorder)} 次")
    print(f"  JSON 解析成功:  {parsed_ok}/{len(ai_recorder)}")
    print(f"  回查成功(L4):   {l4}/{total}   ← 核心指标，低了说明 AI 没逐字摘录")
    print(f"  最慢单次:       {slowest:.2f}s / 预算 {TONGYI_TIMEOUT_DYNAMIC_CARD}s")
    print(f"  判型种类:       {sorted(types)}   ← 只有 1 种说明区分度不足")
    for label, path, source, elapsed, extra in rows:
        print(f"    {label:<8} path={path:<4} source={source:<6} "
              f"{elapsed:>5.2f}s  {extra}")
    print(f"{'=' * 66}")

    # 唯一的硬断言：AI 至少 reachable，且没有一次超预算
    assert ai_recorder, "6 种划法一次 AI 都没调到，联调无效"
    assert all(r["elapsed"] < TONGYI_TIMEOUT_DYNAMIC_CARD for r in ai_recorder), (
        f"有 AI 调用超出后端预算 {TONGYI_TIMEOUT_DYNAMIC_CARD}s，最慢 {slowest:.2f}s"
    )


# ══════════════════════════════════════════════════════
#  判型区分度（单独一个 test，方便只跑它省额度）
# ══════════════════════════════════════════════════════

# 从全文按语言特征分散采样，而不是全落在同一段论述里。
# 上一轮 6 个 probe 全部切自 sentences[0] 邻近区域，5 次调用全判「观点」——
# 那是样本同质导致的，不能据此判断模型区分度。
#
# 线索词刻意比本地关键词池宽，但必须**标记强度够高**：
# - 情绪只用「！」与反问词，不用单独的「？」：议论文里的设问句带问号但该判观点，
#   用它采样必然采到错样本（上一轮就是这么采到一个设问句的）
# - 漏洞只用绝对化表述（以偏概全的最强信号），不用「但是/然而」：
#   转折词在议论文里绝大多数时候只是正常论证节奏，不代表逻辑漏洞
_TYPE_CUES = {
    # 修辞不用单词「一样」与「像」：它们在中文里绝大多数时候表示「相同」
    # 而不是比喻（「也一样」「不一样」「看起来像」），真正的比喻结构是「像…一样」。
    # 零额度预跑实测：用「一样」采到的两句（「性质完全不一样」「个人层面也一样」）
    # 主体都是定义性区分与做法建议，AI 判观点完全正确，验不到修辞判据。
    "修辞": ("似的", "如同", "仿佛", "犹如", "好比", "像是", "像一场",
             "像一种", "像个", "像只", "像一道", "像一台"),
    "情绪": ("！", "难道", "凭什么", "何必", "岂不是", "说白了"),
    "漏洞": ("所有人都", "一定是", "必然会", "从来不", "绝不", "统统", "无非是"),
}

# 每类线索句的句长上限。哨兵踩坑后加的：情绪类必须短，因为长句一旦塞进
# 论证结构，主体就变成论点，判观点反而是正确判定（实测 48 字带「！」的
# 复合句 AI 判观点，AI 是对的）。修辞与漏洞放宽到 60：比喻句与以偏概全的
# 结论句本身需要一定长度才成立，卡得太紧会采不到样本。
_TYPE_MAX_CHARS = {"修辞": 60, "情绪": 25, "漏洞": 60}

# 否定式比喻标记，必须从修辞样本里排除。
#
# 「一样」「像」这类线索词的否定形式不构成比喻。零额度预跑实测采到过
# 「同一件事，性质完全不一样，差别只在你有没有主动开口。」（26 字）——
# 这句主体是定义性区分，AI 判观点是**正确**的，拿它验修辞判据只会得到
# 一个无法归因的结果，白白烧掉一次额度。与「含！不等于情绪」同一类陷阱：
# 字符线索只是必要条件，必须再排除它的反义用法。
_CUE_NEGATIONS = ("不一样", "不像", "不如", "不似", "不相同", "没两样", "也一样")

# 提示词里已经用作反例的句子，必须从测试样本里排除。
#
# 上一轮就踩了这个坑：三个反例全部取自测试样本，改完提示词再测同样三句，
# 3/3「命中」——但 AI 只是认出了我写进去的原句，这个结果没有任何检验力。
# 提示词里保留真实反例（它们确实是最有说服力的边界案例），
# 但测试必须用提示词没见过的句子，才能验到泛化能力。
_PROMPT_EXAMPLES = (
    "听起来像日报",
    "说得越多，别人对你越放心",
    "如何避免认知偏差给自己挖的坑",
    "难道我们只能眼睁睁",
    "X 的衰落不是",
)


def _find_cued_sentence(content: str, sentences, cues, taken, max_chars: int):
    """挑含指定线索、长度合规、没被用过、也不是提示词例句的**最短**句子

    取最短而不是遇到的第一句：长句更容易混进论证结构，一旦主体变成论点，
    判观点就是正确判定，观测结果无法归因。
    """
    best = None
    for span in sentences:
        if span in taken:
            continue
        text = content[span[0]:span[1]]
        if not (8 <= len(text) <= max_chars):
            continue
        if any(frag in text for frag in _PROMPT_EXAMPLES):
            continue
        if not any(cue in text for cue in cues):
            continue
        if any(neg in text for neg in _CUE_NEGATIONS):
            continue
        if best is None or len(text) < best[0]:
            best = (len(text), span)
    return best[1] if best else None


def _collect_cued_probes(limit_articles: int = 10):
    """跨文章按线索采样，每类取一个样本

    单篇文章的文体太窄：实测 article_1 是议论文，全文找不到任何比喻句与
    转折句，只在一篇里采样会直接因样本不足而跑不起来。

    返回 (线索型, article_id, content, start, end) 列表。
    """
    from game.api.api import _load_engine_articles

    articles = _load_engine_articles()
    probes = []
    found: set = set()
    # 每篇的命中情况记下来，找不到时能直接看出是「词不在全文」还是「被句长过滤掉」
    diagnostics: dict = {}
    for article in articles[:limit_articles]:
        if len(found) == len(_TYPE_CUES):
            break
        sentences = _split_sentences(article.content, min_chars=8)
        taken: set = set()
        for expected_type, cues in _TYPE_CUES.items():
            if expected_type in found:
                continue
            max_chars = _TYPE_MAX_CHARS[expected_type]
            span = _find_cued_sentence(article.content, sentences, cues, taken,
                                       max_chars)
            if span is None:
                raw_hits = sum(article.content.count(cue) for cue in cues)
                diagnostics[expected_type] = (
                    f"{article.id} 全文含线索词 {raw_hits} 次，"
                    f"但都不在 8-{max_chars} 字的句子里"
                )
                continue
            taken.add(span)
            found.add(expected_type)
            probes.append((expected_type, article.id, article.content,
                           span[0], span[1]))
    return probes, diagnostics


def test_card_type_discrimination(ai_recorder, store_path, classify):
    """修辞/情绪/漏洞三类线索句，AI 能不能分开判

    本地关键词池的历史实测是「13 种划法 12 种同解」，几乎全判观点。
    引入 AI 判型的全部理由就是要打破这个，所以这条必须单独验。

    不断言 AI 判得「对」：线索句本身可能兼具多种特征（带「！」的比喻句
    判情绪还是修辞都说得通），硬断言只会让测试变成 flaky。
    观测指标是**判型种类数**——三类线索句如果还是全判同一个型，
    说明提示词的四类判据没起作用，需要改 llm_prompt.py。
    """
    probes, diagnostics = _collect_cued_probes()
    for expected_type, note in diagnostics.items():
        if expected_type not in {p[0] for p in probes}:
            print(f"\n[{expected_type}] 没采到样本：{note}")

    assert len(probes) >= 2, (
        f"只找到 {len(probes)} 类线索句（{[p[0] for p in probes]}），"
        f"样本不足以判断区分度；诊断：{diagnostics}"
    )

    judged = []
    for expected_type, article_id, content, start, end in probes:
        before = len(ai_recorder)
        outcome = service.resolve_dynamic_selection(
            article_id=article_id, content=content,
            start=start, end=end, classify=classify,
        )
        record = ai_recorder[-1] if len(ai_recorder) > before else None
        resolved = outcome.resolved or {}
        got = resolved.get("type", "-")
        local_type = normalize_card_type(classify(content[start:end])[0])
        judged.append(got)

        print(f"\n{'─' * 66}")
        print(f"[线索={expected_type}] {article_id} 选区[{start}:{end}] ({end - start}字)")
        print(f"  原文: 「{content[start:end][:70]}」")
        if record:
            print(f"  AI({record['elapsed']:.2f}s): {record['raw']}")
        print(f"  本地关键词池判: {local_type}   AI 判: {got}   "
              f"最终采用: {resolved.get('type', '-')}")
        print(f"  → path={resolved.get('path', '-')} "
              f"source={outcome.response.get('source') or outcome.response.get('message')}")
        if outcome.hit:
            print(f"  向量=({resolved.get('x')}, {resolved.get('y')}) "
                  f"最终文本「{outcome.text[:60]}」")

    distinct = len({t for t in judged if t != "-"})
    # probe 是 5 元组 (线索型, article_id, content, start, end)，只取首元素比
    agreed = sum(1 for probe, got in zip(probes, judged) if got == probe[0])
    print(f"\n{'=' * 66}")
    print(f"判型区分度：{len(probes)} 类线索句 → AI 给出 {distinct} 种不同判型")
    print(f"  与线索期望一致: {agreed}/{len(probes)}（仅作参考，线索本身不权威）")
    print(f"  对比基准：本地关键词池在同样样本上历史实测 13 种划法 12 种同解")
    print(f"{'=' * 66}")

    assert ai_recorder, "一次 AI 都没调到，无法评估判型区分度"
    assert all(r["elapsed"] < TONGYI_TIMEOUT_DYNAMIC_CARD for r in ai_recorder), (
        "有 AI 调用超出后端预算"
    )


# ══════════════════════════════════════════════════════════
#  提示词回归哨兵（单次调用，额度紧张时用这个）
# ══════════════════════════════════════════════════════════

def _find_exclamation_probe(limit_articles: int = 10, max_chars: int = 25):
    """找全库**最短**的一句纯感叹句

    句长上限是这条哨兵的关键，踩过坑才加的。实测采到过：
    「容易失败的模式是先想个项目出来—开公司—再做业务，不是说这个模式
    不行，是容易失败，创业九死一生！」（48 字），AI 判观点、reason「表达
    可讨论判断」。这次 AI 是对的：句子主体是「不是 A，是 B」的定义性区分
    ——恰好就是提示词第 4 条自己举的观点正例句式，末尾那个「！」只是语气
    点缀。拿这种样本去指控提示词有偏置，等于要求 AI 把一个该判观点的句子
    判成情绪。

    「含！」是情绪的必要条件而不是充分条件。真正的感叹句靠语气而不是论据
    说服人，所以它短；一旦句子里塞进了论证结构，主体就变成观点了。
    因此这里按句长升序取最短候选，而不是遇到的第一句。

    同时排除带比喻词与绝对化表述的句子：那样判成修辞或漏洞都说得通，
    观测结果无法归因。要的是只可能判情绪或观点的干净样本。

    返回 (article_id, content, start, end) 或 None。
    """
    from game.api.api import _load_engine_articles

    rhetoric_cues = _TYPE_CUES["修辞"]
    loophole_cues = _TYPE_CUES["漏洞"]
    candidates = []
    for article in _load_engine_articles()[:limit_articles]:
        for start, end in _split_sentences(article.content, min_chars=8):
            text = article.content[start:end]
            if not (8 <= len(text) <= max_chars) or "！" not in text:
                continue
            if any(frag in text for frag in _PROMPT_EXAMPLES):
                continue
            # 只留纯感叹：不带比喻词、不带绝对化表述
            if any(cue in text for cue in rhetoric_cues + loophole_cues):
                continue
            candidates.append((len(text), article.id, article.content, start, end))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1:]


def test_exclamation_sentinel(ai_recorder, store_path, classify):
    """单次哨兵：感叹句还会不会被吞进「观点」

    为什么单独留一条只花 1 次额度的测试：判型区分度的完整验证要 3 次调用，
    额度不够时无法评估提示词改动。这条挑偏置最确凿的一类做最小验证——
    旧提示词明写「情绪：如反问、感叹」，带「！」的句子仍被 8/8 判成观点。
    改完 llm_prompt.py 跑这一条：若仍判观点，说明改动无效，不必再烧额度；
    若改判情绪，方向就对了，值得申请额度做三类完整验证。

    不断言 AI 必须判情绪（模型输出不确定，硬断言会变 flaky），
    只断言确定性契约：AI 可达、未超预算、reason 非空。判型打印出来人工读。

    读输出时先看句长：超过 30 字的「感叹句」很可能主体是论证，
    判观点属于正确判定，不能当成提示词偏置的证据。
    """
    probe = _find_exclamation_probe()
    assert probe is not None, (
        "前 10 篇里找不到 ≤25 字、只带！、不带比喻词与绝对化表述的句子，"
        "无法构造干净样本；把 _find_exclamation_probe 的 limit_articles 调大，"
        "或适当放宽 max_chars（但超过 40 字就会重现「！只是语气点缀」的坑）"
    )
    article_id, content, start, end = probe

    outcome = service.resolve_dynamic_selection(
        article_id=article_id, content=content,
        start=start, end=end, classify=classify,
    )

    assert len(ai_recorder) == 1, (
        f"哨兵必须恰好消耗 1 次 AI 调用，实际 {len(ai_recorder)} 次"
        f"（被 L1/L2/L3 提前拒就没意义了）"
    )
    record = ai_recorder[0]
    resolved = outcome.resolved or {}
    got = resolved.get("type", "-")
    parsed = record["parsed"] or {}
    local_type = normalize_card_type(classify(content[start:end])[0])

    print(f"\n{'=' * 66}")
    print(f"感叹句哨兵  {article_id} 选区[{start}:{end}] ({end - start}字)")
    print(f"  原文: 「{content[start:end]}」")
    print(f"  AI 原文({record['elapsed']:.2f}s): {record['raw']}")
    print(f"  AI 判型: {parsed.get('card_type')}   reason: {parsed.get('reason')}")
    print(f"  本地关键词池判: {local_type}   最终采用: {got}   "
          f"path={resolved.get('path', '-')}")
    print(f"  → 判成情绪 = 提示词改动生效；仍判观点 = 改动无效")
    print(f"{'=' * 66}")

    assert record["elapsed"] < TONGYI_TIMEOUT_DYNAMIC_CARD, (
        f"单次 {record['elapsed']:.2f}s 超出后端预算 {TONGYI_TIMEOUT_DYNAMIC_CARD}s"
    )
    assert parsed, f"JSON 没解析出来，净化链失效：{record['raw'][:200]!r}"
    assert str(parsed.get("reason", "")).strip(), "AI 没给 reason，无法归因判型依据"


# ══════════════════════════════════════════════════════════
#  定向验证：主体不是论断的句子
# ══════════════════════════════════════════════════════════
#
# 为什么不用 _TYPE_CUES 的字符线索扫描挑样本：字符线索只是必要条件，不是
# 充分条件。真机实测三次采到的都是语义完全不同的句子——
#   「…如同考试提前持有解答答案一样，应对沟通将易如反掌」（37字）
#     比喻只是状语修饰，主干是做法建议，AI 判观点是**对的**；
#   「好的创业项目一定是轻资产就可以运作起来的…」（46字）
#     「一定是」只是修饰，主体是评判标准，AI 判观点也是**对的**。
# 两次都验不到修辞/漏洞的判据，各白烧一次额度。
#
# 所以下面的样本是人工通读全库后挑的，判据是「与提示词里该类正例同构」。
# 定位用子串而不是硬编码偏移量：文章库会增删，偏移量必然漂移。
#
# 已归档的前两批样本（各烧过额度，结论已得出，不再重跑）：
#   「跟耗材似的」21字 → AI 判**情绪**，reason「比喻+情绪冲击」。
#     AI 看见了比喻，但认为它不是句子主体（去掉「跟耗材似的」后
#     「他家常备三根，打断一根换一根」语法仍成立），于是往下走到第 2 条。
#     关键是它**没跳到第 4 条兜底**——顺序契约是守住的。
#   「U客直谈一定是最好…的软件」25字 → AI 判**观点**，reason「可讨论的判断」。
#     也判对了：第 3 条三条判据全预设句内有论证结构，而这是个孤立断言，
#     没有前提→结论的过程，按字面定义不算漏洞。
# 两批都不是提示词偏置，都是样本挑错，故换成下面两条同构样本。
_CURATED_PROBES = (
    # 暗喻对举，与第 1 条正例「通勤像一场每天重播的默剧」同类：
    # 去掉比喻（同情心=奢侈品、分数=硬通货）整句就不成立。
    ("修辞", "ai_e70ec330", "优绩主义养蛊"),
    # 把复杂现象归因到单一因素，与第 3 条正例「一定是因为吃不了苦」几乎同构。
    # 额外价值：原文含 4 个英文双引号（0x22），AI 摘录时必须转义成 \"，
    # 否则 JSON 解析失败 —— 顺带验回查链对引号的鲁棒性。
    ("漏洞", "article_3", "很多聪明人反而行动力很差"),
)


def _find_curated_probe(article_id: str, fragment: str):
    """在指定文章里定位含 fragment 的完整句，返回 (content, start, end)"""
    from game.api.api import _load_engine_articles

    for article in _load_engine_articles():
        if article.id != article_id:
            continue
        for start, end in _split_sentences(article.content, min_chars=6):
            if fragment in article.content[start:end]:
                return article.content, start, end
        return None
    return None


def test_curated_non_opinion_probes(ai_recorder, store_path, classify):
    """修辞/漏洞定向验证：主体不是论断时，AI 会不会倒进「观点」这个兜底类

    要验的契约是「观点判断最后进行」：一句话的主体确实是比喻、或确实是
    绝对化断言时，AI 要能判出修辞/漏洞。不要求四类卡按比例出现——只要
    这种情况真出现时判得出来就够了。

    情绪类已由 test_exclamation_sentinel 连续两次验证（12 字与 15 字纯感叹句
    都判情绪，本地关键词池都误判观点并被 AI 纠正），这里补修辞与漏洞两类。

    不硬断言判型：模型输出不确定，硬断言会变 flaky。断言只覆盖确定性契约
    ——每条恰好 1 次调用、未超预算、reason 非空。判型与 reason 打印出来人工读。
    """
    located = []
    for expected_type, article_id, fragment in _CURATED_PROBES:
        found = _find_curated_probe(article_id, fragment)
        assert found is not None, (
            f"{article_id} 里找不到含「{fragment}」的完整句：文章库变了。"
            f"重新扫一遍全库，把 _CURATED_PROBES 换成新的干净样本"
        )
        located.append((expected_type, article_id, fragment) + found)

    judged = []
    for expected_type, article_id, fragment, content, start, end in located:
        before = len(ai_recorder)
        outcome = service.resolve_dynamic_selection(
            article_id=article_id, content=content,
            start=start, end=end, classify=classify,
        )
        assert len(ai_recorder) == before + 1, (
            f"[{expected_type}] 这条样本必须恰好消耗 1 次 AI 调用，实际 "
            f"{len(ai_recorder) - before} 次——被 L1/L2/L3 提前拦下就没验到判型"
        )
        record = ai_recorder[-1]
        parsed = record["parsed"] or {}
        resolved = outcome.resolved or {}
        got = resolved.get("type", "-")
        local_type = normalize_card_type(classify(content[start:end])[0])
        judged.append(got)

        print(f"\n{'=' * 66}")
        print(f"[人工样本 线索={expected_type}] {article_id} "
              f"选区[{start}:{end}] ({end - start}字)")
        print(f"  原文: 「{content[start:end]}」")
        print(f"  AI({record['elapsed']:.2f}s): {record['raw']}")
        print(f"  本地关键词池判: {local_type}   最终采用: {got}   "
              f"path={resolved.get('path', '-')}")
        if outcome.hit:
            print(f"  向量=({resolved.get('x')}, {resolved.get('y')})")

        assert record["elapsed"] < TONGYI_TIMEOUT_DYNAMIC_CARD, (
            f"[{expected_type}] 单次 {record['elapsed']:.2f}s 超出后端预算"
        )
        assert parsed, f"[{expected_type}] JSON 没解析出来：{record['raw'][:200]!r}"
        assert str(parsed.get("reason", "")).strip(), (
            f"[{expected_type}] AI 没给 reason，判错也无法归因"
        )

    print(f"\n{'=' * 66}")
    print(f"定向验证：{[p[0] for p in located]} → AI 判 {judged}")
    print(f"  判出非观点 = 该类判据生效；仍判观点 = 先读上面的 reason 归因。")
    print(f"  若 reason 仍是「可讨论的判断」，说明该句主体确实是论断，是样本挑错了")
    print(f"  ——换样本，不要改提示词（前三次都是这个原因，不是偏置）。")
    print(f"{'=' * 66}")
