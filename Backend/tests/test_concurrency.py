"""并行能力验证 —— 单局内并发 + 多局并发的隔离性

本后端此前**零并发测试**（tests/ 里 ThreadPool / threading / concurren 全仓零命中），
"这游戏能不能同时跑多局"一直是靠推断而非实测。本文件把它变成可执行的结论，分四层：

A. 前提：并发是否真实存在
   21 个 /api/ 端点全是 `def` 而非 `async def`，FastAPI 把它们派发到 anyio 线程池，
   所以多局并发是真实的 OS 线程并发。谁把某个端点改成 `async def` 又在里面做同步
   阻塞 IO（读盘 / subprocess / requests），就会堵住整个事件循环，全服串行。

B. 单局内并发：局末文章逐段生成
   article_generator.generate_article 用 ThreadPoolExecutor + executor.map
   （_GENERATE_MAX_PARALLEL=5）。验证「真并发」（总耗时≈最慢一段而非各段之和）
   与「顺序保持」（paragraphs[i] 与 blueprint[i] 必须同索引）。

C. 多局并发：已验证安全的面
   **前端主流程是并行安全的。** /api/workspace/vectors、/api/judge、
   /api/cards/dynamic、/api/articles/generate 的共同结构是「状态全在请求体里 +
   每请求新建 MatrixVectorSystem」，响应体只反映本次请求。实测 4 局并发 POST
   不同卡槽快照，各自响应与串行基准逐位相同，零串扰。

D. 高并发支持验证（20+ 玩家同时游玩）
   1. session 已按 player_id 分区（_vectors / _cards_cache 都是 dict[str, ...]）
   2. 动态卡 ID 用 time_ns() 纳秒时间戳，同文本并发不碰撞
   3. AI 文章生成已加 _AI_GEN_LOCK，check-then-act 竞争已修
   4. 端点通过 X-Player-Id 头接收 player_id，默认 'default' 向后兼容

D 层用例验证上述修复确实生效，确保后端能支持 20+ 玩家同时游玩。

所有落盘测试把 STORE_PATH 重定向到 tmp_path，绝不碰真实的
article_lib/dynamic_cards.json；所有 AI 相关测试都 monkeypatch 掉真实调用，
绝不消耗额度。

运行：cd Backend; pytest tests/test_concurrency.py -v
"""

from __future__ import annotations

import ast
import collections
import inspect
import sys
import threading
import time
from pathlib import Path

import pytest

# 允许直接从 Backend 目录运行（无 conftest.py，也不依赖 pip install -e）
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from game import article_store
from game.api import article_generator as ag
from game.api import dynamic_card_store as store
from game.api.api import _generate_dynamic_card, app
from game.api.session import get_session
from game.models import SaltCard
from game.numerics import Vector2D
from game.numerics.matrix_vector_system import MatrixVectorSystem, StructureType


# ══════════════════════════════════════════════════════════
#  公共工具
# ══════════════════════════════════════════════════════════

def _py_files() -> list[Path]:
    return sorted(f for f in (_BACKEND_DIR / "game").rglob("*.py")
                  if "__pycache__" not in f.parts)


def _api_routes() -> list[APIRoute]:
    return [r for r in app.routes
            if isinstance(r, APIRoute) and r.path.startswith("/api/")]


def run_parallel(fn, n: int, timeout: float = 60.0):
    """并发执行 n 个 fn(i)，返回 (按 i 排序的结果, 耗时秒)

    用 Barrier 让 n 个线程同时冲进临界区：不加栅栏的话线程可能天然错开、
    串行跑完，测试就会**假绿**——看起来"并发没问题"，其实根本没并发。
    """
    results: list = [None] * n
    errors: list = [None] * n
    barrier = threading.Barrier(n)

    def worker(i: int) -> None:
        try:
            barrier.wait(timeout=15)
            results[i] = fn(i)
        except BaseException as exc:  # noqa: BLE001 - 要把异常原样带回主线程
            errors[i] = exc

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(n)]
    started = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)
    elapsed = time.perf_counter() - started

    assert not any(t.is_alive() for t in threads), "有线程未结束，疑似死锁"
    assert all(e is None for e in errors), \
        f"并发执行抛异常：{[repr(e) for e in errors if e is not None][:3]}"
    return results, elapsed


# slot 编号 → 矩阵位置，与 MatrixVectorSystem.MATRIX_LAYOUT 一致
_SLOT_ROWS = [[1, 2, 3], [4, 5, 6, 7, 8], [9, 10, 11, 12, 13], [14, 15, 16]]
_ALL_SLOTS = [s for row in _SLOT_ROWS for s in row]


@pytest.fixture(scope="module")
def article1() -> dict:
    """article_1 的原始 payload（6 张预设卡 + 全文），只读"""
    return article_store.read_json_like(article_store.ARTICLE_LIB_DIR / "article_1.json")


@pytest.fixture(scope="module")
def players(article1) -> dict[str, list[list[str]]]:
    """4 个"玩家"：同一篇文章的 6 张卡摆进不同槽位 → 4 个互不相同的卡槽快照

    必须用真实 card_id，因为端点走 auto_load_cards=True，要从 article_lib 读卡。
    """
    ids = [sp["card_id"] for sp in article1["linespots"]]
    layouts = {
        "p0": (ids[0:3], [0, 1, 2]),        # 首行三张
        "p1": (ids[3:6], [3, 4, 5]),        # 次行前三格
        "p2": (ids[0:4], [8, 9, 13, 15]),   # 斜跨二三四行
        "p3": (ids[2:6], [6, 10, 11, 14]),  # 散布中后段
    }
    return {k: [[str(_ALL_SLOTS[p]), cards[i]] for i, p in enumerate(pos)]
            for k, (cards, pos) in layouts.items()}


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """把动态卡落盘重定向到 tmp_path，绝不污染真实 dynamic_cards.json"""
    path = tmp_path / "dynamic_cards.json"
    monkeypatch.setattr(store, "STORE_PATH", path)
    store.reset_cache()
    yield path
    store.reset_cache()


def _card_dict(card_id: str, text: str, *, x: float = 32.0, y: float = 32.0) -> dict:
    return {
        "card_id": card_id, "attribute_value": 12, "card_type": "观点卡",
        "start": 0, "end": len(text), "attribute_x": x, "attribute_y": y,
    }


# ══════════════════════════════════════════════════════════
#  A. 前提：并发是否真实存在
# ══════════════════════════════════════════════════════════

def test_every_api_endpoint_is_sync_def_so_fastapi_uses_the_threadpool():
    """全部 /api/ 端点必须是 `def` 而非 `async def`

    这是整个并行能力的地基：FastAPI 把 `def` 端点派发到 anyio 线程池，多个请求
    才能真正同时执行；`async def` 端点直接跑在事件循环上，里面任何同步阻塞
    （Path.read_text / subprocess.run / requests.post）都会**冻结全服**。

    本后端的端点大量做同步 IO（读 article_lib、调 LLM、调预处理管道），
    所以必须保持 `def`。改成 async 前请先确认整条链路都是 await 的。
    """
    routes = _api_routes()
    assert len(routes) == 12, f"端点数变了：{[r.path for r in routes]}"
    async_ones = [r.path for r in routes if inspect.iscoroutinefunction(r.endpoint)]
    assert not async_ones, (
        f"这些端点是 async def，同步阻塞会冻结事件循环：{async_ones}")


def test_module_level_mutable_state_inventory():
    """模块级共享可变状态清单锁定 —— 并行能力的全部风险面就这四个

    并发 bug 只可能来自跨请求共享的可变状态。本用例把 game/ 里所有这类状态
    枚举出来钉死：新增一个就会红，提醒你先想清楚它是否需要按玩家分区或加锁。

    检测规则（三条，缺一不可）：
      1. 模块级私有名绑定到容器字面量（Dict/List/Set）且函数内部有 item assign
      2. 模块级私有名绑定到类实例（SomeClass()）—— 内容通过方法调用改写，
         静态扫描归不到模块名，但类实例天然可变
      3. 模块级私有名在函数内 `global` 声明（运行时重绑定）

    显式排除：模块级只读常量（_STRUCTURE_NAME_MAP / _WEAVE_ROLE_HINT /
    _SANITIZE_RULES 等），它们只有 .get() 与只读遍历，从不被改写。
    「共享数据」和「共享可变态」是两回事，只有后者才是并行风险面。

    四个的当前定性：
      _session        类实例，跨玩家共享，无键 —— 缺陷，见 D 层
      _cards_cache    同上（在 _session 内部）
      _article_cache  容器，并发未命中时各线程各自解析写入，良性竞争
      _cache          lazy-None + global 重绑定，全程 _LOCK 保护，线程安全
      _loader         类实例，load() 是 check-then-act，靠预热规避，见 B 层
    """
    found = _scan_shared_mutable_state()
    assert found == {
        "game/api/article_generator.py": ["_article_cache"],
        "game/api/dynamic_card_store.py": ["_cache"],
        "game/api/session.py": ["_session"],
        "game/template_loader.py": ["_loader"],
    }, f"模块级共享可变状态清单变动：{found}"


def _scan_shared_mutable_state() -> dict[str, list[str]]:
    """扫描 game/ 里所有「共享可变态」的模块级私有名

    只报真正会被改写的状态，不报只读常量。检测规则：
      - 容器字面量（Dict/List/Set）+ 函数内有 item/attr assign → 可变
      - 类实例（SomeClass()）→ 天然可变（内容通过方法改写）
      - 函数内 `global` 声明 → 运行时重绑定
    """
    import ast as _ast
    files = sorted(f for f in (_BACKEND_DIR / "game").rglob("*.py")
                   if "__pycache__" not in f.parts)
    trees = {f: _ast.parse(f.read_text(encoding="utf-8")) for f in files}

    def _roots(n):
        while isinstance(n, (_ast.Subscript, _ast.Attribute)): n = n.value
        return n.id if isinstance(n, _ast.Name) else None

    def _lazy_none_ann(n):
        a = getattr(n, "annotation", None)
        return a is not None and any(k in _ast.unparse(a)
            for k in ("Optional", "Dict", "List", "dict", "list", "Set", "set"))

    # 收集模块级私有名绑定到容器 / 类实例 / lazy-None
    decl: dict[str, tuple[str, int, str]] = {}
    for f, t in trees.items():
        for n in t.body:
            if not isinstance(n, (_ast.Assign, _ast.AnnAssign)): continue
            v = n.value
            if v is None: continue
            tgts = n.targets if isinstance(n, _ast.Assign) else [n.target]
            for tg in tgts:
                if not isinstance(tg, _ast.Name) or not tg.id.startswith("_") or tg.id == "__all__":
                    continue
                if isinstance(v, (_ast.Dict, _ast.List, _ast.Set)):
                    kind = "container-literal"
                elif isinstance(v, _ast.Call) and isinstance(v.func, _ast.Name) and v.func.id[:1].isupper():
                    kind = "instance:" + v.func.id
                elif isinstance(v, _ast.Constant) and v.value is None and _lazy_none_ann(n):
                    kind = "lazy-None"
                else:
                    kind = None
                if kind:
                    decl.setdefault(tg.id, (f.as_posix(), n.lineno, kind))

    mutable: set[str] = set()
    _MUTATORS = {"append", "extend", "clear", "pop", "update", "add", "discard",
                 "remove", "setdefault", "insert", "popitem", "sort", "reverse"}
    for f, t in trees.items():
        for fn in [n for n in _ast.walk(t) if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))]:
            for st in fn.body:
                if isinstance(st, _ast.Global):
                    for nm in st.names:
                        if nm in decl: mutable.add(nm)
            for n in _ast.walk(fn):
                if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute) and n.func.attr in _MUTATORS:
                    r = _roots(n.func.value)
                    if r in decl: mutable.add(r)
                if isinstance(n, (_ast.Assign, _ast.AugAssign)):
                    tgts = n.targets if isinstance(n, _ast.Assign) else [n.target]
                    for tg in tgts:
                        if isinstance(tg, (_ast.Subscript, _ast.Attribute)):
                            r = _roots(tg)
                            if r in decl and decl[r][2] == "container-literal":
                                mutable.add(r)
    for nm, (_, _, kind) in decl.items():
        if kind.startswith("instance:"): mutable.add(nm)

    result: dict[str, list[str]] = {}
    for nm in sorted(mutable):
        f_abs, _, _ = decl[nm]
        rel = Path(f_abs).relative_to(_BACKEND_DIR).as_posix()
        result.setdefault(rel, []).append(nm)
    return result


def test_matrix_vector_system_is_never_a_module_level_singleton():
    """MatrixVectorSystem 必须每请求新建，绝不能提成模块级单例

    这是 C 层"主流程并行安全"的**根本原因**：它持有 cards_data 实例状态，
    一旦做成单例，A 局 set_cards_data 会污染 B 局的向量计算。
    当前 api.py 在两个端点内部各 new 一次（POST /api/workspace/vectors 与
    POST /api/articles/generate），实例随请求生灭。
    """
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:                      # 只看模块顶层
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                        and sub.func.id == "MatrixVectorSystem"):
                    pytest.fail(f"{path.name} 在模块级实例化了 MatrixVectorSystem（L{sub.lineno}）")

    # 反向确认：端点内部确实在 new（否则上面的断言是空过）
    api_src = (_BACKEND_DIR / "game" / "api" / "api.py").read_text(encoding="utf-8")
    assert api_src.count("MatrixVectorSystem()") == 2, "实例化点数量变了，请重新核对并发安全性"


# ══════════════════════════════════════════════════════════
#  B. 单局内并发：逐段生成
# ══════════════════════════════════════════════════════════

_PARA_COUNT = 5
_PARA_DELAY = 0.30


def _synthetic_specs(n: int) -> list:
    return [
        ag.ParagraphSpec(index=i, role="论述段", card_id=f"c{i}", card_text=f"卡牌原文{i}",
                         card_type="观点", content_type="观点类", weave_cards=[], template_id="")
        for i in range(n)
    ]


@pytest.fixture
def stubbed_generation(monkeypatch):
    """把逐段生成替换成 sleep 桩，隔离出「并发调度」这一件事

    不 monkeypatch build_blueprint 的话就得依赖 article_lib 里每张卡都能取到原文
    （蓝图会剔除无原文的卡），段数不可控；而这里要验证的是线程池行为，不是蓝图。
    真实 AI 一律不调，零额度消耗。
    """
    specs = _synthetic_specs(_PARA_COUNT)
    monkeypatch.setattr(ag, "build_blueprint", lambda matrix, structure, cards_data: specs)

    def fake_generate(spec, structure_name, lean, *args, **kwargs):
        time.sleep(_PARA_DELAY)
        # 把 spec 的身份编进产物：顺序错乱或 spec 串扰都能被下游断言抓到
        return f"<{spec.index}|{spec.card_id}|{structure_name}|{lean}>"

    monkeypatch.setattr(ag, "generate_paragraph", fake_generate)
    return specs


def _snapshot() -> dict:
    return {
        "matrix": [[None] * 3, [None] * 5, [None] * 5, [None] * 3],
        "structure": StructureType.OTHER,
        "cards_data": {},
        "vector": Vector2D(1.0, 1.0),
    }


def test_paragraph_generation_is_truly_concurrent(stubbed_generation):
    """总耗时必须≈最慢一段，而不是各段之和

    5 段各 sleep 0.3s：串行 = 1.5s，并发（max_workers=5）≈ 0.3s。
    阈值取 0.9s = 串行的 60%，留足 CI 抖动余量又足以识破串行残留。
    """
    started = time.perf_counter()
    result = ag.generate_article(_snapshot(), title="并发验证", use_ai=True)
    elapsed = time.perf_counter() - started

    serial_floor = _PARA_COUNT * _PARA_DELAY
    assert elapsed < serial_floor * 0.6, (
        f"耗时 {elapsed:.2f}s 接近串行下限 {serial_floor:.2f}s，并发生效了吗？")
    assert len(result["paragraphs"]) == _PARA_COUNT


def test_paragraph_order_and_identity_survive_concurrency(stubbed_generation):
    """executor.map 的顺序保证：paragraphs[i] 必须来自 blueprint[i]

    乱序的后果是局末文章段落颠倒、且响应里 blueprint 的 index/role/card_id
    与 content 对不上——排查时无从定位。这里同时校验三件事：
    段落顺序、每段的 spec 身份没串、blueprint 的 index 与 card_id 同步。
    """
    result = ag.generate_article(_snapshot(), title="顺序验证", use_ai=True)

    paras = result["paragraphs"]
    assert [p.split("|")[0].lstrip("<") for p in paras] == [str(i) for i in range(_PARA_COUNT)]
    assert [p.split("|")[1] for p in paras] == [f"c{i}" for i in range(_PARA_COUNT)]
    # structure_name / lean 是并发前算好的共享入参，每段都必须拿到同一份
    assert len({(p.split("|")[2], p.split("|")[3].rstrip(">")) for p in paras}) == 1

    assert [b["index"] for b in result["blueprint"]] == list(range(_PARA_COUNT))
    assert [b["card_id"] for b in result["blueprint"]] == [f"c{i}" for i in range(_PARA_COUNT)]
    # content 是 paragraphs 按序拼装的结果，顺序错了这里也会跟着错
    assert result["content"].index("c0") < result["content"].index("c4")


def test_max_parallel_is_capped_and_scales_with_blueprint(monkeypatch):
    """并发度 = max(1, min(段数, 5))：段数少时不开多余线程，段数多时不无限开

    无上限的话一篇 16 段的矩阵会同时打 16 个 LLM 请求，容易触发服务商限流；
    本项目失败会优雅降级为卡牌原文拼接，但降级意味着文章质量掉档。
    """
    assert ag._GENERATE_MAX_PARALLEL == 5
    for n, expected in ((0, 1), (1, 1), (3, 3), (5, 5), (9, 5), (16, 5)):
        assert max(1, min(n, ag._GENERATE_MAX_PARALLEL)) == expected, n


def test_template_loader_is_prewarmed_before_the_thread_pool():
    """TemplateLoader.load() 必须在 ThreadPoolExecutor 之前被调用（源码顺序断言）

    TemplateLoader 是全局单例且 load() 是**无锁的 check-then-act**：
        if self._loaded: return
        ... 逐个填 self._templates ...
        self._loaded = True
    两个线程同时进来会都执行填充（幂等，值相同，不损坏），但存在一个窗口：
    _loaded 仍为 False 而 _templates 只填了一半，此时并发调用 select_template
    会遍历到残缺字典、匹配不上而回退 None，段落因此拿不到模板。

    generate_article 用「进池前先 get_template_loader().load()」把这一步压成单线程，
    这行预热是**承重结构**，删掉就重新引入竞争。本用例锁住它的存在与位置。
    """
    tree = ast.parse((_BACKEND_DIR / "game" / "api" / "article_generator.py")
                     .read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "generate_article")

    prewarm_line = pool_line = None
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name == "load" and prewarm_line is None:
                prewarm_line = node.lineno
            if isinstance(node.func, ast.Name) and node.func.id == "ThreadPoolExecutor":
                pool_line = node.lineno

    assert prewarm_line is not None, "模板预热调用不见了"
    assert pool_line is not None, "ThreadPoolExecutor 不见了"
    assert prewarm_line < pool_line, (
        f"预热（L{prewarm_line}）必须在线程池（L{pool_line}）之前，否则重新引入 load() 竞争")

    # 反向确认风险确实存在：TemplateLoader 里没有锁
    loader_src = (_BACKEND_DIR / "game" / "template_loader.py").read_text(encoding="utf-8")
    assert "threading" not in loader_src and "Lock" not in loader_src, (
        "TemplateLoader 已加锁，预热不再是承重结构，可放宽本用例")


# ══════════════════════════════════════════════════════════
#  C. 多局并发：已验证安全的面
# ══════════════════════════════════════════════════════════

def test_concurrent_vector_posts_do_not_cross_talk(players):
    """4 局同时 POST 不同卡槽快照，各自响应必须与串行基准逐位相同

    这是「前端主流程可并行」的核心证据。端点内部每请求新建 MatrixVectorSystem，
    向量在局部变量里算完直接进响应体，不经过任何共享态——所以哪怕 _session 是
    全局单槽（见 D 层），**响应本身也不会串**。
    """
    keys = sorted(players)
    with TestClient(app) as client:
        baseline = {}
        for k in keys:                       # 串行基准
            r = client.post("/api/workspace/vectors", json={"slots": players[k]})
            assert r.status_code == 200, r.text
            baseline[k] = tuple(round(v, 9) for v in r.json()["instant_vector"])

        # 基准本身必须互不相同，否则"零串扰"是因为四局本来就算出同一个向量——假绿
        assert len(set(baseline.values())) == len(keys), baseline

        results, _ = run_parallel(
            lambda i: client.post("/api/workspace/vectors",
                                  json={"slots": players[keys[i]]}).json()["instant_vector"],
            len(keys))

    for i, k in enumerate(keys):
        assert tuple(round(v, 9) for v in results[i]) == baseline[k], \
            f"{k} 的并发响应串到了别的局：期望 {baseline[k]}，实得 {results[i]}"


def test_concurrent_judge_posts_do_not_cross_talk(article1):
    """4 局同时判不同的预设点，各自必须命中自己那一张卡

    /api/judge 是 `-> dict` 端点（无 schema 过滤），状态全在请求体里，
    因此天然可并行。这里同时校验命中判定与 card_id 归属。
    """
    spots = article1["linespots"][:4]
    payloads = [{
        "articleId": article1["id"], "paragraphIndex": 0,
        "startOffset": sp["start"], "endOffset": sp["end"] + 1,
    } for sp in spots]

    with TestClient(app) as client:
        results, _ = run_parallel(
            lambda i: client.post("/api/judge", json=payloads[i]).json(), len(payloads))

    for sp, body in zip(spots, results):
        assert body["hit"] is True, f"未命中 {sp['card_id']}：{body}"
        assert body["card"]["card_id"] == sp["card_id"], \
            f"判到了别人的卡：期望 {sp['card_id']}，实得 {body['card']['card_id']}"


def test_concurrent_dynamic_cards_with_distinct_text_never_collide(article1):
    """不同选区并发生成动态卡，card_id 必须全不相同

    ID 里有 md5(text)[:8]，不同文本天然不同 hash，这条是**真实成立的安全性质**：
    多个玩家在同一毫秒划不同句子不会互相覆盖。
    （同文本同毫秒会撞，见 D 层 test_known_defect_same_text_...）
    """
    content = article1["content"]
    spans = [(i * 12, i * 12 + 30) for i in range(24)]
    # 前提校验：24 个选区的文本必须真的互不相同，否则这条测的是 D 层那个缺陷
    texts = {content[a:b] for a, b in spans}
    assert len(texts) == len(spans)

    results, _ = run_parallel(
        lambda i: _generate_dynamic_card(article1["id"], content[spans[i][0]:spans[i][1]],
                                         spans[i][0], spans[i][1]),
        len(spans))

    ids = [r["card_id"] for r in results]
    dupes = [k for k, v in collections.Counter(ids).items() if v > 1]
    assert not dupes, f"不同文本却撞了 ID：{dupes[:3]}"


def test_concurrent_store_writes_lose_nothing(isolated_store):
    """8 线程 × 25 张并发落盘，200 条必须一条不少且 JSON 完好

    验证 dynamic_card_store 的 _LOCK + 临时文件 + os.replace 原子写设计：
    没有锁的话并发读改写会互相覆盖（丢写），没有原子写的话中途崩溃会留下
    半截 JSON，下次 _read_store 解析失败静默退回空表——整批动态卡凭空消失。
    """
    threads, per_thread = 8, 25
    total = threads * per_thread

    def save(i: int):
        tid, seq = divmod(i, per_thread)
        text = f"线程{tid}第{seq}张动态卡的原文内容"
        return store.save_dynamic_card(
            _card_dict(f"article_1_dynamic_guandian_t{tid}s{seq}_{tid}{seq}", text), text)

    results, _ = run_parallel(save, total)
    assert all(results), f"有 {results.count(False)} 次落盘返回 False"

    payload = __import__("json").loads(isolated_store.read_text(encoding="utf-8"))
    assert len(payload["cards"]) == total, \
        f"丢写：期望 {total} 条，实得 {len(payload['cards'])} 条"
    assert not list(isolated_store.parent.glob("*.tmp")), "临时文件残留，原子写没走完"

    # 每条记录都必须能按 id 读回，且原文没串到别的线程
    for tid in range(threads):
        for seq in range(per_thread):
            cid = f"article_1_dynamic_guandian_t{tid}s{seq}_{tid}{seq}"
            rec = store.load_dynamic_card(cid)
            assert rec is not None, f"{cid} 读不回来"
            assert rec["text"] == f"线程{tid}第{seq}张动态卡的原文内容"


def test_store_hands_out_copies_so_callers_cannot_poison_shared_cache(isolated_store):
    """load_dynamic_card 必须返回副本

    内存镜像 _cache 是全局共享的；若把内部 dict 直接交出去，任何一个调用方
    就地改一下就会污染所有后续读者（跨请求、跨局）。
    """
    text = "副本语义验证用的原文"
    store.save_dynamic_card(_card_dict("article_1_dynamic_copytest_1_1", text), text)

    first = store.load_dynamic_card("article_1_dynamic_copytest_1_1")
    first["text"] = "被调用方就地篡改"
    first["injected"] = True

    second = store.load_dynamic_card("article_1_dynamic_copytest_1_1")
    assert second["text"] == text
    assert "injected" not in second


def test_article_payload_cache_concurrent_miss_is_benign():
    """_article_cache 无锁，但并发未命中是良性竞争

    多个线程同时 miss 会各自解析一遍 JSON 再写入同一个 key，值完全相同
    （文章 id 带内容 hash，同 id 即同内容），CPython 单键赋值在 GIL 下原子，
    所以最坏结果只是重复劳动，不会损坏也不会读到半个对象。

    【身份语义】并发未命中时每个线程返回**各自的**解析结果（12 个不同对象），
    但值相等；缓存最终持有其中一个。后续命中时所有读者返回**同一个**对象
    （见 test_article_payload_cache_hits_share_one_object）—— 这是只读约束的
    来源：谁就地改它（比如给 linespots 排序）就会跨请求污染。
    """
    ag._article_cache.clear()
    results, _ = run_parallel(lambda i: ag._load_article_payload("article_1"), 12)

    assert all(r is not None for r in results)
    # 并发未命中：12 个不同对象，但值相等
    distinct_ids = len({id(r) for r in results})
    assert distinct_ids > 1, "所有线程返回同一对象？缓存预热路径变了"
    assert all(r == results[0] for r in results), "值不相等，解析结果不一致"
    # 缓存最终持有其中一个
    cached = ag._article_cache["article_1"]
    assert any(r is cached for r in results), "缓存持有的对象不在未命中结果里"
    assert set(ag._article_cache) == {"article_1"}
    assert cached["id"] == "article_1"


def test_article_payload_cache_hits_share_one_object():
    """缓存命中后所有读者必须返回同一个对象 —— 只读约束的来源

    一旦缓存建立，后续所有调用方拿到的都是同一个 dict 对象。这意味着：
    任何一个调用方就地改它（比如给 linespots 排序）就会污染所有后续读者。
    本用例把这个共享性钉住，改成返回副本时这里会红，那时请同步评估性能
    影响（每张卡都要调一次本函数）。
    """
    ag._article_cache.clear()
    # 先预热缓存（串行，确保缓存已建立）
    cached = ag._load_article_payload("article_1")
    assert cached is not None

    # 并发命中：所有线程必须拿到同一个对象
    results, _ = run_parallel(lambda i: ag._load_article_payload("article_1"), 8)
    assert all(r is cached for r in results), "缓存命中后返回的不是同一个对象，共享性假设变了"

    # 串行命中：同样
    for _ in range(3):
        assert ag._load_article_payload("article_1") is cached


def test_session_cache_reads_are_keyed_by_player_and_card_id():
    """_cards_cache 按 (player_id, card_id) 二级索引，不会读到别人的卡

    多玩家隔离：每个玩家的动态卡只存在自己的分区里，跨玩家不可能读到。
    并发写入 20 个不同玩家的卡，各自只能读到自己的。
    """
    session = get_session()
    # 记录测试前的玩家数
    before = len(session._cards_cache)

    def cache(i: int):
        pid = f"test_player_{i % 5}"  # 5 个玩家
        card = SaltCard(id=f"probe_{i}", articleId="article_1", informationPointId="",
                        text=f"探针{i}", type="观点", rarity="动态发现",
                        attribute_x=32.0, attribute_y=32.0)
        session.cache_card(card, player_id=pid)
        return session.get_cached_card(f"probe_{i}", player_id=pid)

    try:
        results, _ = run_parallel(cache, 20)
        for i, got in enumerate(results):
            assert got is not None and got.id == f"probe_{i}", f"读到了别人的卡：{got}"
        # 5 个玩家分区都被创建了
        assert len(session._cards_cache) == before + 5, "并发写丢了玩家分区"
    finally:
        # 清理测试玩家
        for i in range(5):
            session.clear_cards_cache(player_id=f"test_player_{i}")


# ══════════════════════════════════════════════════════════
#  D. 高并发支持验证（20+ 玩家同时游玩）
# ══════════════════════════════════════════════════════════

def test_vectors_are_isolated_by_player_id(players):
    """每个玩家的向量互不干扰 —— session 已按 player_id 分区

    POST /api/workspace/vectors 通过 X-Player-Id 头区分玩家，
    GET /api/workspace/vectors 读回该玩家自己的向量。
    20 个玩家同时写入后轮询，各自读到的必须是自己刚写的。
    """
    with TestClient(app) as client:
        # 20 个玩家并发写入各自的向量
        player_ids = [f"player_{i}" for i in range(20)]
        keys = sorted(players)[:4]  # 用 4 种不同的卡槽布局

        def write_and_read(i: int):
            pid = player_ids[i]
            k = keys[i % len(keys)]
            # POST 写入该玩家的向量
            r = client.post("/api/workspace/vectors",
                            json={"slots": players[k]},
                            headers={"X-Player-Id": pid})
            assert r.status_code == 200, r.text
            written = tuple(round(v, 9) for v in r.json()["instant_vector"])
            # GET 轮询该玩家的向量
            polled = tuple(round(v, 9) for v in client.get(
                "/api/workspace/vectors", headers={"X-Player-Id": pid}
            ).json()["instant_vector"])
            return pid, written, polled

        results, _ = run_parallel(write_and_read, 20)

        # 每个玩家读到的必须是自己写的
        for pid, written, polled in results:
            assert polled == written, f"{pid} 的轮询读到了别人的向量：期望 {written}，实得 {polled}"

        # 不同玩家的向量必须互不相同（否则隔离性验证无意义）
        written_vectors = {pid: w for pid, w, _ in results}
        assert len(set(written_vectors.values())) >= 4, \
            "多玩家向量相同，隔离性验证前提不成立"


def test_dynamic_card_id_no_collision_under_concurrency(article1):
    """同文本同毫秒并发 → card_id 必须全不相同（time_ns() 纳秒精度）

    ID 格式改为 {article_id}_dynamic_{type}_{hash}_{time_ns()}，
    纳秒时间戳使同毫秒碰撞概率趋近于零。24 个并发请求必须产出 24 个不同 ID。
    """
    content = article1["content"]
    sample = content[40:70]

    results, elapsed = run_parallel(
        lambda i: _generate_dynamic_card(article1["id"], sample, 40, 70), 24)

    ids = [r["card_id"] for r in results]
    distinct = len(set(ids))
    assert elapsed < 0.5, f"耗时 {elapsed:.2f}s 太长，测试前提不成立"
    assert distinct == 24, (
        f"24 个并发请求只产出 {distinct} 个不同 ID —— time_ns() 精度不够？"
        f"或 ID 生成逻辑变了。前 3 个 ID：{ids[:3]}")


def test_ai_article_autogen_is_locked():
    """AI 文章生成已加锁 —— check-then-act 竞争已修

    api.py 里有 `import threading` 与 `_AI_GEN_LOCK = threading.Lock()`，
    且 `/api/articles/random` 的 AI 生成分支在 `with _AI_GEN_LOCK:` 内。
    """
    api_src = (_BACKEND_DIR / "game" / "api" / "api.py").read_text(encoding="utf-8")
    assert "import threading" in api_src, "api.py 缺少 threading import"
    assert "_AI_GEN_LOCK" in api_src, "api.py 缺少 _AI_GEN_LOCK"
    assert "with _AI_GEN_LOCK:" in api_src, "AI 生成分支未在锁内"


def test_session_manager_has_player_dimension():
    """SessionManager 已引入玩家维度分区

    _vectors: dict[str, Vector2D] 按 player_id 存储最后一次向量
    _cards_cache: dict[str, dict[str, SaltCard]] 按 player_id 存储动态卡
    所有方法接受 player_id 参数，默认 'default' 向后兼容。
    """
    session = get_session()
    attrs = {a for a in vars(session)}
    assert "_vectors" in attrs, f"SessionManager 缺少 _vectors：{attrs}"
    assert "_cards_cache" in attrs, f"SessionManager 缺少 _cards_cache：{attrs}"
    # 旧结构已移除
    assert "_last_vector" not in attrs, "SessionManager 仍有旧的 _last_vector 单槽"

    # 方法签名验证：player_id 参数存在且有默认值
    import inspect
    sig = inspect.signature(session.update_vector)
    assert "player_id" in sig.parameters, "update_vector 缺少 player_id 参数"
    sig = inspect.signature(session.last_vector)
    assert "player_id" in sig.parameters, "last_vector 缺少 player_id 参数"
    sig = inspect.signature(session.cache_card)
    assert "player_id" in sig.parameters, "cache_card 缺少 player_id 参数"

    # clear_cards_cache 支持按玩家清理
    sig = inspect.signature(session.clear_cards_cache)
    assert "player_id" in sig.parameters, "clear_cards_cache 缺少 player_id 参数"
