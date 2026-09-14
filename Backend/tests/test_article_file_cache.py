"""ARTICLE_FILES 双缓存分歧的回归测试

Bug 现场（修复前）：
    api.py                     ARTICLE_FILES = _discover_article_files()   # L77
                               └─ AI 生成新文章后用 `global ARTICLE_FILES` 刷新（L546-547）
    matrix_vector_system.py    ARTICLE_FILES = _discover_article_files()   # L51
                               └─ 从不刷新

两份同名快照因此分歧：/api/articles/random 立刻能读到新生成的 AI 文章并把它发给前端，
但 MatrixVectorSystem._load_card_by_id 遍历的是自己那份陈旧快照，看不见这篇文章 ——
玩家在下一局用到新文章的预设卡时，卡牌数据静默加载失败（返回 None），
只能靠 session 缓存碰巧兜底，向量计算随之劣化且无任何报错。

修复分两轮：先让 matrix_vector_system 不再持有模块级快照（_load_card_by_id 改为
每次实时扫描），再把 api.py 那份快照连同 `global ARTICLE_FILES` 刷新一起删掉，
文章库的目录常量与发现逻辑收敛到叶子模块 game.article_store，三个消费方
（matrix_vector_system / api / article_generator）共用同一份实时扫描。
本文件锁定该行为，防止日后又被"优化"回快照。

运行：cd Backend; pytest tests/test_article_file_cache.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 允许直接从 Backend 目录运行（无 conftest.py，也不依赖 pip install -e）
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from game import article_store
from game.api import api as api_mod
from game.api.session import get_session
from game.numerics import matrix_vector_system as mvs


# ══════════════════════════════════════════════════════════
#  夹具与工具
# ══════════════════════════════════════════════════════════

@pytest.fixture
def article_lib(tmp_path, monkeypatch):
    """把 article_lib 重定向到临时目录，避免污染真实文章库

    discover_article_files() 在调用时才读模块全局 ARTICLE_LIB_DIR，
    所以 monkeypatch 生效，无需重启或重新 import。

    只需 patch 这一个点，matrix_vector_system / api / article_generator 三个
    消费方就全部跟着重定向——这正是把发现逻辑收敛到 article_store 换来的
    性质。收敛之前每个模块各有一份 _ARTICLE_LIB_DIR，patch 一处只能改一处，
    本文件根本盖不住 api.py 那条路径。
    """
    monkeypatch.setattr(article_store, "ARTICLE_LIB_DIR", tmp_path)
    session = get_session()
    session.clear_cards_cache()
    yield tmp_path
    session.clear_cards_cache()


def write_article(lib_dir: Path, article_id: str, linespots: list[dict]) -> Path:
    """按 article_lib 的真实格式落一篇文章"""
    payload = {
        "id": article_id,
        "title": f"标题-{article_id}",
        "content": "这是一段用于回归测试的正文，长度足够覆盖划线判定。" * 10,
        "linespots": linespots,
    }
    path = lib_dir / f"{article_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def make_linespot(card_id: str, card_type: str = "观点",
                  x: float = 32.0, y: float = 32.0) -> dict:
    """构造一条合规的 linespot（观点卡 x/y 落在 31~36，不触发钳制告警）"""
    return {
        "card_id": card_id,
        "card_type": card_type,
        "rarity": "common",
        "attribute_value": 15,
        "attribute_x": x,
        "attribute_y": y,
        "start": 0,
        "end": 19,
    }


# ══════════════════════════════════════════════════════════
#  发现层
# ══════════════════════════════════════════════════════════

def test_discover_sees_files_written_after_import(article_lib):
    """模块 import 之后才落盘的文章必须立刻可被发现"""
    assert article_store.discover_article_files() == []

    write_article(article_lib, "ai_deadbeef", [make_linespot("ai_deadbeef_card_1")])

    assert [p.name for p in article_store.discover_article_files()] == ["ai_deadbeef.json"]


def test_discover_only_matches_article_and_ai_globs(article_lib):
    """dynamic_cards.json 之类的落盘文件不得混进文章池"""
    write_article(article_lib, "article_1", [make_linespot("article_1_card_1")])
    write_article(article_lib, "ai_cafebabe", [make_linespot("ai_cafebabe_card_1")])
    (article_lib / "dynamic_cards.json").write_text("{}", encoding="utf-8")
    (article_lib / "notes.json").write_text("{}", encoding="utf-8")

    assert [p.name for p in article_store.discover_article_files()] == [
        "ai_cafebabe.json",
        "article_1.json",
    ]


def test_module_holds_no_stale_snapshot():
    """matrix_vector_system 与 api 都不得再有 ARTICLE_FILES 模块级快照

    快照本身就是 Bug 载体：它在 import 时定格，之后无论文章库怎么变都不会更新。
    api.py 那份曾经靠 `global ARTICLE_FILES` 手动刷新，但刷新只写在
    /api/articles/random 的 AI 生成分支里——任何新增的写入点忘写刷新就静默复发。
    """
    assert not hasattr(mvs, "ARTICLE_FILES"), (
        "matrix_vector_system 重新引入了 ARTICLE_FILES 模块级快照，"
        "会与 api.py 的刷新逻辑分歧，见本文件顶部说明"
    )
    assert not hasattr(api_mod, "ARTICLE_FILES"), (
        "api.py 重新引入了 ARTICLE_FILES 模块级快照；文章列表应每次调 "
        "article_store.discover_article_files() 实时扫描"
    )
    assert not hasattr(api_mod, "_discover_article_files"), (
        "api.py 重新定义了本地的 _discover_article_files，发现逻辑必须只有 "
        "game.article_store 一份"
    )


def test_discovery_has_single_definition():
    """发现逻辑只允许存在一份：消费方一律从 article_store 导入

    四份拷贝（api / matrix_vector_system / article_generator 内联 glob /
    根目录 test_ai_articles.py）是本轮合并掉的，这条防止它们长回来。
    """
    from game.api import article_generator as ag

    for mod in (mvs, api_mod, ag):
        assert not hasattr(mod, "_discover_article_files"), (
            f"{mod.__name__} 又自己定义了一份文章发现逻辑"
        )
        assert not hasattr(mod, "_ARTICLE_LIB_DIR"), (
            f"{mod.__name__} 又自己算了一份 article_lib 目录常量"
        )
    # 三个消费方用的是同一个函数对象，而不是同名副本
    assert mvs.discover_article_files is article_store.discover_article_files
    assert api_mod.discover_article_files is article_store.discover_article_files
    assert ag.discover_article_files is article_store.discover_article_files


# ══════════════════════════════════════════════════════════
#  卡牌加载层（Bug 的真实受害面）
# ══════════════════════════════════════════════════════════

def test_load_card_by_id_sees_newly_generated_article(article_lib):
    """核心回归：新生成 AI 文章的预设卡必须能加载出来

    修复前这里返回 None —— 文章是 import 之后才落盘的，陈旧快照里没有它。
    """
    write_article(
        article_lib,
        "ai_deadbeef",
        [make_linespot("ai_deadbeef_card_1", "观点", 32.0, 32.0)],
    )

    card = mvs._load_card_by_id("ai_deadbeef_card_1")

    assert card is not None, "新生成文章的预设卡加载失败（ARTICLE_FILES 快照未刷新）"
    assert card.id == "ai_deadbeef_card_1"
    assert card.articleId == "ai_deadbeef"
    assert card.type == "观点"
    assert card.attribute_x == 32.0
    assert card.attribute_y == 32.0


def test_load_card_by_id_tracks_article_lib_growth(article_lib):
    """文章库陆续增长时，每一次查找都要看到当时的最新状态"""
    write_article(article_lib, "ai_aaaaaaa1", [make_linespot("ai_aaaaaaa1_card_1")])
    assert mvs._load_card_by_id("ai_aaaaaaa1_card_1") is not None

    write_article(article_lib, "ai_bbbbbb2", [make_linespot("ai_bbbbbb2_card_1")])
    assert mvs._load_card_by_id("ai_bbbbbb2_card_1") is not None

    write_article(article_lib, "ai_cccccc3", [make_linespot("ai_cccccc3_card_1")])
    assert mvs._load_card_by_id("ai_cccccc3_card_1") is not None

    # 三篇都在，且早先那篇仍能找到
    assert mvs._load_card_by_id("ai_aaaaaaa1_card_1") is not None
    assert len(article_store.discover_article_files()) == 3


def test_load_cards_from_backend_covers_new_article(article_lib):
    """批量入口 load_cards_from_backend 同样要覆盖新文章

    这是 /api/workspace/vectors → process_snapshot 的真实调用路径。
    """
    write_article(article_lib, "ai_deadbeef", [
        make_linespot("ai_deadbeef_card_1", "观点", 32.0, 32.0),
        make_linespot("ai_deadbeef_card_2", "情绪", 25.0, -25.0),
    ])

    system = mvs.MatrixVectorSystem()
    cards = system.load_cards_from_backend(["ai_deadbeef_card_1", "ai_deadbeef_card_2"])

    assert len(cards) == 2
    assert {c.type for c in cards} == {"观点", "情绪"}


def test_load_card_by_id_returns_none_for_unknown_card(article_lib):
    """空文章库下查不到卡仍应安静返回 None，不得抛异常"""
    assert mvs._load_card_by_id("ai_nonexistent_card_9") is None


def test_load_card_by_id_applies_card_rules_clamp(article_lib, capsys):
    """实时扫描不得绕过加载层钳制：越界数值仍要被就近投影并打日志"""
    # 修辞卡的 x/y 是相邻乘数，合法区间 1.05~1.60；这里填成向量量纲 30
    write_article(article_lib, "ai_deadbeef", [
        make_linespot("ai_deadbeef_card_1", "修辞", 30.0, 30.0),
    ])

    card = mvs._load_card_by_id("ai_deadbeef_card_1")

    assert card is not None
    assert card.attribute_x < 30.0, "越界的修辞卡乘数未被钳制"
    assert "卡牌数值越界" in capsys.readouterr().out


# ══════════════════════════════════════════════════════
#  api.py 侧（删掉 ARTICLE_FILES 快照后新盖住的路径）
# ══════════════════════════════════════════════════════

def test_load_engine_articles_raises_on_empty_lib(article_lib):
    """空文章库下宁可报错，不得静默返回空列表让下游除零"""
    with pytest.raises(RuntimeError):
        api_mod._load_engine_articles()


def test_load_engine_articles_sees_newly_written_article(article_lib):
    """api._load_engine_articles 必须看到 import 之后才落盘的文章

    删掉 ARTICLE_FILES 快照之前，这里靠 /api/articles/random 里的
    `global ARTICLE_FILES` 刷新才碰巧正确，而刷新只写在那一个分支里。
    """
    write_article(article_lib, "ai_deadbeef", [make_linespot("ai_deadbeef_card_1")])
    assert [a.id for a in api_mod._load_engine_articles()] == ["ai_deadbeef"]

    # 同一进程内再落一篇，不靠任何刷新就立刻可见（快照时代做不到）
    write_article(article_lib, "article_9", [make_linespot("article_9_card_1")])
    assert {a.id for a in api_mod._load_engine_articles()} == {
        "ai_deadbeef", "article_9",
    }


def test_get_raw_linespots_sees_newly_written_article(article_lib):
    """/api/judge 取原始 linespots 的路径同样不能读陈旧快照

    这条路一旦读不到，JudgeResult.card 的 card_id 会退化到兼容分支，
    前端拿到的卡牌与文章预设点对不上号。
    """
    write_article(article_lib, "ai_deadbeef", [
        make_linespot("ai_deadbeef_card_1", "观点", 32.0, 32.0),
    ])

    article = api_mod._load_engine_articles()[0]
    raw = api_mod._get_raw_linespots(article)

    assert [s["card_id"] for s in raw] == ["ai_deadbeef_card_1"]
