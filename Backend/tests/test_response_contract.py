"""响应体契约测试 —— 把「哪个字段谁在读」的审计结论固化成可执行的网

Step 3-B 的任务是清理「只写不读的响应字段」。审计跑完的结论是**一个都不该删**，
理由分散在协议文档、前端组件与后端内部消费三处，光写在报告里下一次还会被重新
审计一遍。本文件把那套结论钉进测试：

1. 每个响应模型的字段集逐字锁定（v4.0 协议的明文形状）；
2. 每条路由的 response_model 锁定，并把 3 个 `-> dict` 端点「无字段过滤」的
   事实显式记下来——那正是内部字段会漏到线上的机制；
3. ArticleGenerateResponse 那 4 个前端零消费的字段，用真实的前端源码扫描证明
   「确实没人读」，同时要求模型 docstring 里保留「为什么不删」的理由；
4. 预设卡响应刻意不含 attribute_x/y、动态卡响应必须含（内部持久化在读），
   这个不对称是设计而不是遗漏，两边都钉住。

任何一条红了都意味着协议形状或消费关系变了，改的人需要同步更新
游戏重点相关/收发数据json格式约定协议v4.0.md 与本文件的结论。

运行：cd Backend; pytest tests/test_response_contract.py -v
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# 允许直接从 Backend 目录运行（无 conftest.py，也不依赖 pip install -e）
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# 仓库根：Backend -> 仓库根。前端源码扫描要用，
# 后端单独 checkout 时目录不存在，相关用例 skip 而不是 fail。
_REPO_ROOT = _BACKEND_DIR.parent
_FRONTEND_SRC = _REPO_ROOT / "Frontend" / "src"

from fastapi.routing import APIRoute

from game.api.api import (
    ArticleGenerateResponse,
    ArticleResponse,
    BlueprintItem,
    ChatResponse,
    CommentResponse,
    CompositionHintResponse,
    HintItem,
    HintResponse,
    StoryLine,
    StoryResponse,
    VectorResult,
    _generate_dynamic_card,
    _load_engine_articles,
    _spot_to_card_response,
    app,
)


# ══════════════════════════════════════════════════════════
#  1. 响应模型字段集
# ══════════════════════════════════════════════════════════

# 值 = (模型, 字段集, 前端消费状况)
# 「消费状况」写在这里就是审计结论本身：LIVE = 有组件/store 在读；
# 只写 = 前端零消费，保留理由见对应模型的 docstring。
RESPONSE_MODELS: dict[str, tuple[type, set[str], str]] = {
    "ArticleResponse": (
        ArticleResponse,
        {"id", "title", "content", "target_value"},
        "全部 LIVE：articleService.toArticle 逐字段映射，target_value 进 "
        "gameRuntime.understandingTarget 与 Workbench 的合成判定",
    ),
    "VectorResult": (
        VectorResult,
        {"instant_vector"},
        "LIVE：前端指针图与 workspace 轮询都读它",
    ),
    "CommentResponse": (CommentResponse, {"text"}, "LIVE：看山气泡文案"),
    "ChatResponse": (
        ChatResponse,
        {"reply"},
        "LIVE：essayGenerator.ts 从 payload.reply 取正文",
    ),
    "StoryLine": (
        StoryLine,
        {"speaker", "speakerName", "text"},
        "LIVE：AdvDialogue.vue 渲染 speakerName 与 text，speaker 选立绘",
    ),
    "StoryResponse": (
        StoryResponse,
        {"generated", "id", "title", "lines", "source", "debug"},
        "generated/id/title/lines/debug LIVE（storyService.ts 与 stores/game.ts）；"
        "source 被前端 {...data, source:'ai'} 覆盖，属用户新增的诊断字段，保留",
    ),
    "HintItem": (
        HintItem,
        {"start", "end", "type", "preview", "reason"},
        "全部 LIVE：ArticleHintModal.vue 渲染 type/preview/reason，"
        "start/end 供 jump-to-hint 定位",
    ),
    "HintResponse": (
        HintResponse,
        {"mode", "message", "hints", "analysis"},
        "全部 LIVE：GameLayout.vue 与 ArticleOverlay.vue 读 mode/analysis",
    ),
    "CompositionHintResponse": (
        CompositionHintResponse,
        {"mode", "analysis"},
        "LIVE：BackpackWindow.vue 读 analysis 注入 CompositionHintModal",
    ),
    "BlueprintItem": (
        BlueprintItem,
        {"index", "role", "card_id", "card_type", "content_type",
         "template_id", "weave_count"},
        "只写：随 ArticleGenerateResponse.blueprint 一起发出，前端零消费，"
        "但是 v4.0 协议明文字段且是 AI 逐段生成唯一的可观测面",
    ),
    "ArticleGenerateResponse": (
        ArticleGenerateResponse,
        {"title", "content", "paragraphs", "structure", "lean", "blueprint"},
        "title/content LIVE（RoundArticleWindow.vue 打字机）；"
        "paragraphs/structure/lean/blueprint 只写，保留理由见模型 docstring",
    ),
}


@pytest.mark.parametrize("model_name", sorted(RESPONSE_MODELS))
def test_response_model_field_set_is_locked(model_name):
    """字段集逐字锁定：增删字段都会在这里红

    红了不等于「不许改」，而是「改之前先确认协议文档与前端消费方」。
    第三个元素记录的消费状况就是上次审计的结论，改动时一并更新。
    """
    model, expected_fields, _ = RESPONSE_MODELS[model_name]
    assert set(model.model_fields.keys()) == expected_fields, (
        f"{model_name} 字段集变动；上次审计的消费状况：{RESPONSE_MODELS[model_name][2]}"
    )


# ══════════════════════════════════════════════════════════
#  2. 路由与 response_model
# ══════════════════════════════════════════════════════════

# path -> response_model 名。dict 表示端点用 `-> dict` 注解，
# FastAPI 不做字段过滤：handler 往 dict 里塞什么就发什么。
ROUTE_RESPONSE_MODELS: dict[str, str] = {
    "/api/articles/random": "ArticleResponse",
    "/api/articles/generate": "ArticleGenerateResponse",
    "/api/judge": "dict",
    "/api/cards/dynamic": "dict",
    "/api/health": "dict",
    "/api/workspace/vectors": "VectorResult",
    "/api/ai/comment": "CommentResponse",
    "/api/ai/chat": "ChatResponse",
    "/api/ai/story": "StoryResponse",
    "/api/ai/hint": "HintResponse",
    "/api/ai/composition-hint": "CompositionHintResponse",
}


def _api_routes() -> dict[str, APIRoute]:
    """path -> route。/api/workspace/vectors 有 GET/POST 两条，键会合并，
    两条的 response_model 相同（都是 VectorResult），对本测试无影响。"""
    return {
        r.path: r for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith("/api/")
    }


def test_route_inventory_matches_protocol():
    """端点清单锁定：与 前后端通信协议v4.0.md 的 7 条链路一一对应

    少了说明端点被误删，多了说明有人加了新端点却没更新协议文档。
    """
    routes = _api_routes()
    assert set(routes) == set(ROUTE_RESPONSE_MODELS), (
        f"端点清单变动：新增 {set(routes) - set(ROUTE_RESPONSE_MODELS)}，"
        f"缺失 {set(ROUTE_RESPONSE_MODELS) - set(routes)}"
    )


@pytest.mark.parametrize("path", sorted(ROUTE_RESPONSE_MODELS))
def test_route_response_model_is_locked(path):
    routes = _api_routes()
    model = routes[path].response_model
    name = getattr(model, "__name__", None) if model is not None else None
    assert name == ROUTE_RESPONSE_MODELS[path], f"{path} 的 response_model 变了"


def test_dict_typed_endpoints_do_no_field_filtering():
    """显式记录：3 个 `-> dict` 端点没有 schema 过滤

    这是「内部字段漏到线上」的机制本身。/api/judge 与 /api/cards/dynamic 的
    card 子对象就是因此带出了 attribute_x/attribute_y（动态卡分支），
    而前端 SaltCardDto 并不声明它们。保留现状的理由见
    test_dynamic_card_response_carries_vectors_for_internal_consumers。

    哪天给这两个端点补上 Pydantic 模型，字段会被静默过滤掉——那是行为变更，
    本用例会红，提醒改的人重新核对前端适配层。
    """
    routes = _api_routes()
    untyped = {p for p, r in routes.items() if r.response_model is dict}
    assert untyped == {"/api/judge", "/api/cards/dynamic", "/api/health"}, untyped


# ══════════════════════════════════════════════════════════
#  3. ArticleGenerateResponse 的只写字段：审计结论可执行化
# ══════════════════════════════════════════════════════════

# RoundArticleWindow.vue 只读 title 与 content，这四个字段前端零消费
UNCONSUMED_GENERATE_FIELDS = ("paragraphs", "structure", "lean", "blueprint")


def _frontend_generate_consumers() -> list[Path]:
    """找出所有消费 /api/articles/generate 的前端文件"""
    if not _FRONTEND_SRC.exists():
        return []
    hits = []
    for path in sorted(_FRONTEND_SRC.rglob("*")):
        if path.suffix not in {".ts", ".vue"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "ArticleGenerateResponse" in text or "generateRoundArticle" in text:
            hits.append(path)
    return hits


def test_unconsumed_generate_fields_have_no_frontend_reader():
    """证明「前端确实一处都不读」——这是保留而非删除的前提，也是删的诱因

    扫描范围是真正消费该端点的前端文件（而不是整个 Frontend/src）：
    ArticlePanel.vue 里的 props.article.paragraphs 属于 Article 域类型，
    由 articleService.toArticle 用 [data.content] 就地构造，与本响应无关，
    扫全仓会产生假阳性。

    哪天前端真的接上了分段渲染，本用例会红——那时请把
    RESPONSE_MODELS["ArticleGenerateResponse"] 的消费状况从「只写」改成 LIVE，
    并同步删掉 ArticleGenerateResponse docstring 里的第 1 条理由。
    """
    consumers = _frontend_generate_consumers()
    if not consumers:
        pytest.skip(f"前端源码不在 {_FRONTEND_SRC}，无法核实消费方")

    # 消费方必须非空且包含那个窗口组件，否则「没人读」是因为根本没人调，
    # 那是另一个问题，不能当作本结论成立
    names = {p.name for p in consumers}
    assert "RoundArticleWindow.vue" in names, names
    assert "articleGenerateService.ts" in names, names

    pattern = re.compile(r"\.(" + "|".join(UNCONSUMED_GENERATE_FIELDS) + r")\b")
    for path in consumers:
        text = path.read_text(encoding="utf-8", errors="replace")
        found = sorted(set(pattern.findall(text)))
        assert not found, f"{path.name} 开始读取只写字段 {found}，请更新审计结论"


def test_generate_response_documents_why_unconsumed_fields_stay():
    """保留理由必须写在模型 docstring 里，不能只存在于某次对话或报告

    没有这条，下一个人看到四个没人读的字段就会直接删掉，连带撕掉
    v4.0 协议里预留的「按 paragraphs 分段渲染」入口。
    """
    doc = ArticleGenerateResponse.__doc__ or ""
    for field in UNCONSUMED_GENERATE_FIELDS:
        assert field in doc, f"docstring 未说明 {field} 为何保留"
    assert "收发数据json格式约定协议v4.0.md" in doc, "未指明协议出处"
    assert "BlueprintItem" in doc


def test_blueprint_item_documents_its_protocol_source():
    doc = BlueprintItem.__doc__ or ""
    assert "收发数据json格式约定协议v4.0.md" in doc


# ══════════════════════════════════════════════════════════
#  4. 预设卡 vs 动态卡的字段不对称（设计，不是遗漏）
# ══════════════════════════════════════════════════════════

def test_preset_card_response_omits_vector_components():
    """预设卡响应刻意不含 attribute_x/attribute_y

    _spot_to_card_response 的 docstring 写着「不返回 attribute_x/attribute_y
    (前端不需要知道)」——向量是后端算全局向量的内部数据，给了前端就等于
    把答案漏出去（玩家可以照着向量挑卡）。
    """
    try:
        articles = _load_engine_articles()
    except RuntimeError:
        pytest.skip("文章库为空")
    if not articles:
        pytest.skip("文章库为空")

    from game.api.api import _get_raw_linespots

    article = next((a for a in articles if _get_raw_linespots(a)), None)
    if article is None:
        pytest.skip("没有任何文章带 linespots")

    spots = article.linespots
    card = _spot_to_card_response(article, spots[0], 0)

    assert set(card) == {"card_id", "attribute_value", "card_type", "start", "end"}
    assert "attribute_x" not in card and "attribute_y" not in card


def test_dynamic_card_response_carries_vectors_for_internal_consumers():
    """动态卡响应带 attribute_x/attribute_y，且它们**不是死字段**

    同一个 dict 有两个消费方：
      - HTTP 响应的 card 字段（前端 SaltCardDto 不声明这两个键，读了也会丢）
      - _persist_dynamic_card：用 card_dict.get("attribute_x") 构造 SaltCard
        写进 session 缓存与 dynamic_cards.json，本局向量计算与跨局重建全靠它

    所以不能简单地「从响应里删掉」：要么把 dict 拆成内外两份（改动动态卡
    这条 LIVE 主路径），要么保留现状。选后者——多两个浮点数换一条核心链路
    不动，且与 /api/cards/dynamic 的 source、StoryResponse 的 debug 一样
    属于「顺带可观测」。这里钉住的是：值必须真实且合规，不能退化成 0。
    """
    card = _generate_dynamic_card(
        article_id="article_1",
        text="这项调查覆盖了十万个样本，因此结论具有代表性",
        start_offset=0,
        end_offset=20,
    )

    assert set(card) == {
        "card_id", "attribute_value", "card_type", "start", "end",
        "attribute_x", "attribute_y",
    }

    from game.numerics.card_rules import normalize_card_type, validate_card_vector

    internal_type = normalize_card_type(card["card_type"])
    assert validate_card_vector(
        internal_type, card["attribute_x"], card["attribute_y"]
    ) == [], "落盘用的向量必须合规，否则 _load_card_by_id 会在加载时钳制，玩家看到的数值与生成时不一致"
    assert (card["attribute_x"], card["attribute_y"]) != (0.0, 0.0), (
        "attribute_x/y 退化成 0 会让 _persist_dynamic_card 存进一张零向量卡"
    )
    # 响应体用展示形式（带「卡」），与预设卡分支同构，前端才能复用 adaptSaltCard
    assert card["card_type"].endswith("卡")


def test_judge_and_dynamic_card_responses_share_the_same_shape():
    """两个端点的响应体必须同构，前端 adaptJudgeResult 才能直接复用

    /api/cards/dynamic 是划线主路径、/api/judge 降为兜底，前端对两者调同一个
    适配器（adaptDynamicCardResult 内部就是 {...adaptJudgeResult(dto), source}）。
    形状一旦分叉，兜底路径会在适配层炸掉——而兜底路径平时不走，炸了也没人发现。

    用真实文章的第一条 linespot 做选区：两边都会命中预设分支，
    不打网络、不落盘动态卡（judge 只在 miss 分支才建卡）。
    """
    from fastapi.testclient import TestClient

    from game.api.api import _get_raw_linespots

    try:
        articles = _load_engine_articles()
    except RuntimeError:
        pytest.skip("文章库为空")
    article = next((a for a in articles if _get_raw_linespots(a)), None)
    if article is None:
        pytest.skip("没有任何文章带 linespots")

    spot = article.linespots[0]
    payload = {
        "articleId": article.id,
        "paragraphIndex": 0,
        "startOffset": spot.start,
        "endOffset": spot.end + 1,   # 前端 [start, end) 口径，后端内部是闭区间
    }

    client = TestClient(app)
    judge_resp = client.post("/api/judge", json=payload)
    dynamic_resp = client.post("/api/cards/dynamic", json=payload)
    assert judge_resp.status_code == 200, judge_resp.text
    assert dynamic_resp.status_code == 200, dynamic_resp.text

    judge_body = judge_resp.json()
    dynamic_body = dynamic_resp.json()

    # 前提：两边都得真的命中预设卡，否则比的是 miss 分支的键集
    assert judge_body["hit"] is True, judge_body
    assert dynamic_body["hit"] is True, dynamic_body
    assert dynamic_body["source"] == "preset"

    # 动态卡端点只允许比 judge 多一个 source（诊断字段），其余键逐字相同
    assert set(dynamic_body) - set(judge_body) == {"source"}
    assert set(judge_body) - set(dynamic_body) == set()
    # card 子对象也必须同构，否则 adaptSaltCard 会在兜底路径上炸
    assert set(dynamic_body["card"]) == set(judge_body["card"])
    assert set(judge_body["card"]) == {
        "card_id", "attribute_value", "card_type", "start", "end",
    }
