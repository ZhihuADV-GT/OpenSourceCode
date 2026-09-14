"""动态卡牌落盘与文章生成链路的回归测试

覆盖「动态卡原文 100% 丢失」Bug 的第 0 步修复：

1. dynamic_card_store —— 读写往返、原子性、损坏文件容错、淘汰、去重、配额计数
2. _reconstruct_dynamic_card —— 优先读落盘（真实原文 + 真实向量），未命中才降级
3. article_generator._resolve_card_text —— 三级原文解析
4. build_blueprint —— 剔除无原文卡后段落角色重算（事后过滤会让末段角色错位）
5. generate_article —— paragraphs / blueprint 同步过滤与 index 重排

运行：cd Backend; pytest tests/test_dynamic_card_store.py -v
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

import pytest

# 允许直接从 Backend 目录运行（无 conftest.py，也不依赖 pip install -e）
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from game.api import dynamic_card_store as store
from game.api.article_generator import (
    _load_article_payload,
    _resolve_card_text,
    build_blueprint,
    generate_article,
    get_card_text,
)
from game.api.article_generator import ParagraphSpec
from game.models import SaltCard
from game.numerics.card_rules import display_card_type, normalize_card_type
from game.numerics.matrix_vector_system import (
    StructureType,
    _reconstruct_dynamic_card,
)


# ══════════════════════════════════════════════════════════
#  夹具与工具
# ══════════════════════════════════════════════════════════

@pytest.fixture
def store_path(tmp_path, monkeypatch):
    """把落盘文件重定向到临时目录，避免污染真实 article_lib"""
    path = tmp_path / "dynamic_cards.json"
    monkeypatch.setattr(store, "STORE_PATH", path)
    store.reset_cache()
    yield path
    store.reset_cache()


def make_card_dict(
    article_id: str = "article_1",
    card_type: str = "观点",
    text_hash: str = "abcd1234",
    timestamp_ns: int | None = None,
    counter: int = 0,
    x: float = 33.0,
    y: float = 34.0,
    *,
    timestamp: int | None = None,  # 向后兼容旧调用
) -> dict:
    """构造 _generate_dynamic_card 形态的响应字典（card_type 为协议展示形式）"""
    # timestamp 是旧参数名，兼容处理
    if timestamp is not None and timestamp_ns is None:
        timestamp_ns = timestamp
    if timestamp_ns is None:
        timestamp_ns = 1700000000000000000
    return {
        "card_id": f"{article_id}_dynamic_{normalize_card_type(card_type)}_{text_hash}_{timestamp_ns}_{counter}",
        "attribute_value": 12,
        "card_type": display_card_type(card_type),  # 出口带「卡」
        "start": 100,
        "end": 150,
        "attribute_x": x,
        "attribute_y": y,
    }


def make_salt_card(card_id: str, text: str = "", card_type: str = "观点") -> SaltCard:
    return SaltCard(
        id=card_id,
        articleId=card_id.split("_dynamic_")[0] if "_dynamic_" in card_id else "article_1",
        informationPointId="",
        text=text,
        type=normalize_card_type(card_type),
        rarity="动态发现",
        attribute_x=33.0,
        attribute_y=34.0,
        vector_array=[],
        title="",
    )


def empty_matrix() -> list:
    return [[None] * 5 for _ in range(4)]


# ══════════════════════════════════════════════════════════
#  1. 落盘读写
# ══════════════════════════════════════════════════════════

def test_save_load_roundtrip(store_path):
    cd = make_card_dict(card_type="情绪", x=25.0, y=-24.0)
    assert store.save_dynamic_card(cd, "玩家划出的原文", title="情绪卡-玩家划出的原...") is True

    record = store.load_dynamic_card(cd["card_id"])
    assert record is not None
    assert record["text"] == "玩家划出的原文"
    # 响应体里是展示形式（带「卡」），落盘必须归一化为规范形式，
    # 否则 _load_card_by_id 下游的类型比较会静默失效
    assert record["card_type"] == "情绪"
    assert record["attribute_x"] == 25.0
    assert record["attribute_y"] == -24.0
    assert record["title"] == "情绪卡-玩家划出的原..."
    assert record["article_id"] == "article_1"
    assert store_path.exists()


def test_load_returns_copy_not_reference(store_path):
    """返回副本：调用方就地修改不应污染内存镜像"""
    cd = make_card_dict()
    store.save_dynamic_card(cd, "原文")

    first = store.load_dynamic_card(cd["card_id"])
    first["text"] = "被篡改"

    assert store.load_dynamic_card(cd["card_id"])["text"] == "原文"
    assert store.load_dynamic_text(cd["card_id"]) == "原文"


@pytest.mark.parametrize("bad_dict,bad_text", [
    ({}, "有文本但无 card_id"),
    (make_card_dict(), ""),
    (make_card_dict(), "   "),
])
def test_save_rejects_invalid_input(store_path, bad_dict, bad_text):
    """空 card_id 或空原文都不该落盘——落一条空记录会让降级路径误判为命中"""
    if not bad_dict:
        bad_dict = {"card_id": ""}
    assert store.save_dynamic_card(bad_dict, bad_text) is False
    assert store.load_dynamic_card("anything") is None


def test_corrupt_store_file_does_not_break_game(store_path, monkeypatch):
    """落盘文件损坏时应退回空表，且后续写入能覆盖重建

    磁盘上的半截 JSON 不该让玩家划线或文章生成直接崩掉。
    """
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text('{"version": 1, "cards": {{{{ 半截', encoding="utf-8")
    store.reset_cache()

    assert store.load_dynamic_card("article_1_dynamic_观点_abcd1234_12345_0") is None

    cd = make_card_dict()
    assert store.save_dynamic_card(cd, "重建后的原文") is True
    assert store.load_dynamic_card(cd["card_id"])["text"] == "重建后的原文"


def test_store_filename_avoids_article_globs():
    """落盘文件名必须避开 article_*.json / ai_*.json

    这两个 glob 现在只有 article_store.discover_article_files 一份定义，
    三个消费方（matrix_vector_system._load_card_by_id、api._get_raw_linespots、
    article_generator._load_article_payload）全走它。若命中，动态卡会混进
    预设 linespot 池，污染 /api/judge 的 _find_best_spot —— 玩家随手一划
    反而"命中预设点"，拿到劣化数值。
    """
    name = store.STORE_PATH.name
    assert not fnmatch.fnmatch(name, "article_*.json")
    assert not fnmatch.fnmatch(name, "ai_*.json")

    # 不只看名字：直接问真身能不能扫到它
    from game.article_store import discover_article_files

    assert store.STORE_PATH not in discover_article_files(), (
        "dynamic_cards.json 被文章发现逻辑扫到了，它会混进预设 linespot 池"
    )

    payload = _load_article_payload(name.replace(".json", ""))
    assert payload is None


def test_eviction_keeps_newest(store_path, monkeypatch):
    monkeypatch.setattr(store, "_MAX_RECORDS", 5)
    ids = []
    for i in range(8):
        cd = make_card_dict(timestamp=10000 + i, text_hash=f"hash{i:04d}")
        store.save_dynamic_card(cd, f"原文{i}")
        ids.append(cd["card_id"])

    # 最旧的 3 条被淘汰，最新 5 条保留
    for gone in ids[:3]:
        assert store.load_dynamic_card(gone) is None
    for kept in ids[3:]:
        assert store.load_dynamic_card(kept) is not None


# ══════════════════════════════════════════════════════════
#  2. 去重
# ══════════════════════════════════════════════════════════
# 这里原本还有一个 test_count_by_round_and_article，验证
# store.count_dynamic_cards 的按局/按文章双口径计数。该函数已删除：
# 它是为后端配额检查预留的，但配额检查已整体移到前端
# （见 dynamic_card_service.resolve_dynamic_selection 的 round_no 说明：
# 「每局 10 张，resetGame 时清零」），生产代码零引用。


def test_find_card_id_by_hash(store_path):
    """重复划同一句话：ID 尾部 timestamp 不同，但内容 hash 相同"""
    first = make_card_dict(timestamp=11111)
    second = make_card_dict(timestamp=22222)  # 同 hash，不同 ts
    other_article = make_card_dict(article_id="article_2", timestamp=33333)

    store.save_dynamic_card(first, "同一句话")
    store.save_dynamic_card(second, "同一句话")
    store.save_dynamic_card(other_article, "同一句话")

    found = store.find_card_id_by_hash("article_1", "abcd1234")
    assert found in (first["card_id"], second["card_id"])
    # 跨文章不应串
    assert store.find_card_id_by_hash("article_3", "abcd1234") is None
    assert store.find_card_id_by_hash("article_1", "ffffffff") is None


# ══════════════════════════════════════════════════════════
#  3. 跨局重建：落盘优先，未命中才降级
# ══════════════════════════════════════════════════════════

def test_reconstruct_prefers_store_over_degradation(store_path):
    """落盘命中时必须拿回真实原文与真实向量，而不是档位默认值"""
    cd = make_card_dict(card_type="观点", x=35.0, y=32.0)
    store.save_dynamic_card(cd, "真实的玩家划线原文", title="观点卡-真实的玩家划线...")

    card = _reconstruct_dynamic_card(cd["card_id"])
    assert card is not None
    assert card.text == "真实的玩家划线原文"      # 降级路径这里恒为 ""
    assert card.attribute_x == 35.0               # 降级路径会给 32.0
    assert card.attribute_y == 32.0
    assert card.type == "观点"
    assert card.title == "观点卡-真实的玩家划线..."
    assert "已过期" not in card.title


def test_reconstruct_degrades_when_store_misses(store_path):
    """落盘未命中（历史卡 / 磁盘丢失）→ 原文为空 + 档位向量 + 过期标记"""
    card = _reconstruct_dynamic_card("article_1_dynamic_观点_abcd1234_1700000000000000000_0")
    assert card is not None
    assert card.text == ""
    assert (card.attribute_x, card.attribute_y) == (32.0, 32.0)
    assert "已过期" in card.title


@pytest.mark.parametrize("card_type,expected", [
    ("观点", (32.0, 32.0)),
    ("情绪", (25.0, -25.0)),
    ("漏洞", (-25.0, 25.0)),
    ("修辞", (1.30, 1.30)),
])
def test_reconstruct_degrade_vector_table(store_path, card_type, expected):
    """四种类型的降级向量都要能命中（ID 里是规范形式，不带「卡」）"""
    cd = make_card_dict(card_type=card_type)
    card = _reconstruct_dynamic_card(cd["card_id"])
    assert card is not None
    assert card.type == normalize_card_type(card_type)
    assert (card.attribute_x, card.attribute_y) == expected


def test_reconstruct_rejects_malformed_id(store_path):
    assert _reconstruct_dynamic_card("article_1_card_1") is None
    assert _reconstruct_dynamic_card("article_1_dynamic_观点") is None


# ══════════════════════════════════════════════════════════
#  4. 三级原文解析
# ══════════════════════════════════════════════════════════

def test_resolve_level1_uses_cards_data_text(store_path):
    """第 1 级：动态卡原文只在 cards_data 里，article_lib 中根本查不到"""
    cd = make_card_dict()
    card_id = cd["card_id"]
    assert get_card_text(card_id) == ""   # "_card_" 守卫会拒掉动态卡 ID

    cards_data = {card_id: make_salt_card(card_id, text="session 缓存里的原文")}
    assert _resolve_card_text(card_id, cards_data) == "session 缓存里的原文"


def test_resolve_level2_uses_article_lib_for_preset(store_path):
    """第 2 级：预设卡的 SaltCard.text 恒为空，必须走 article_lib linespots 反查"""
    payload = _load_article_payload("article_1")
    assert payload, "article_1.json 应存在"
    preset_id = payload["linespots"][0]["card_id"]

    expected = get_card_text(preset_id)
    assert expected, "预设卡应能从 article_lib 取到原文"

    cards_data = {preset_id: make_salt_card(preset_id, text="")}
    assert _resolve_card_text(preset_id, cards_data) == expected


def test_resolve_level3_falls_back_to_store(store_path):
    """第 3 级：cards_data 完全不含该卡（快照不完整）时直接查落盘"""
    cd = make_card_dict()
    store.save_dynamic_card(cd, "只有落盘里才有的原文")

    assert _resolve_card_text(cd["card_id"], {}) == "只有落盘里才有的原文"


def test_resolve_returns_empty_when_all_levels_miss(store_path):
    assert _resolve_card_text("nowhere_dynamic_观点_ffffffff_99999_0", {}) == ""
    assert _resolve_card_text("", {}) == ""


# ══════════════════════════════════════════════════════════
#  5. 蓝图构建：剔除无原文卡 + 角色重算
# ══════════════════════════════════════════════════════════

def test_build_blueprint_drops_empty_text_and_recomputes_roles(store_path):
    """无原文的卡必须在 build_blueprint 阶段剔除

    段落角色由 is_first / is_last 决定，依赖最终存活的卡序。
    若留到生成之后再过滤，本该是"结尾段"的会退化成"论述段"。
    """
    matrix = empty_matrix()
    good_first = "article_1_dynamic_观点_aaaa1111_10001_0"
    orphan = "nowhere_dynamic_观点_bbbb2222_10002_0"      # 三级都取不到原文
    good_last = "article_1_dynamic_观点_cccc3333_10003_0"

    matrix[0][0] = good_first
    matrix[1][0] = orphan
    matrix[2][0] = good_last

    store.save_dynamic_card(make_card_dict(text_hash="aaaa1111", timestamp=10001), "第一段原文")
    store.save_dynamic_card(make_card_dict(text_hash="cccc3333", timestamp=10003), "最后一段原文")

    cards_data = {
        good_first: make_salt_card(good_first, text="第一段原文"),
        orphan: make_salt_card(orphan, text=""),
        good_last: make_salt_card(good_last, text="最后一段原文"),
    }

    blueprint = build_blueprint(matrix, StructureType.OTHER, cards_data)

    assert [spec.card_id for spec in blueprint] == [good_first, good_last]
    assert orphan not in [spec.card_id for spec in blueprint]
    # 通用结构下首段=开头段、末段=结尾段（orphan 若未被剔除，good_last 会变成"论述段"）
    assert blueprint[0].role == "开头段"
    assert blueprint[-1].role == "结尾段"
    assert [spec.index for spec in blueprint] == [0, 1]
    assert blueprint[0].card_text == "第一段原文"


def test_build_blueprint_drops_refutation_target_without_text(store_path):
    """驳论结构的靶子段（row0 漏洞卡）若无原文，整段剔除而不是生成空破题段"""
    matrix = empty_matrix()
    empty_target = "nowhere_dynamic_漏洞_dddd4444_10004_0"
    viewpoint = "article_1_dynamic_观点_eeee5555_10005_0"

    matrix[0][0] = empty_target
    matrix[1][0] = viewpoint

    store.save_dynamic_card(make_card_dict(text_hash="eeee5555", timestamp=10005), "观点原文")
    cards_data = {
        empty_target: make_salt_card(empty_target, text="", card_type="漏洞"),
        viewpoint: make_salt_card(viewpoint, text="观点原文"),
    }

    blueprint = build_blueprint(matrix, StructureType.REFUTATION, cards_data)

    assert len(blueprint) == 1
    assert blueprint[0].card_id == viewpoint
    assert "破题段" not in [spec.role for spec in blueprint]


def test_build_blueprint_returns_empty_when_no_card_has_text(store_path):
    matrix = empty_matrix()
    orphan = "nowhere_dynamic_观点_ffff6666_10006_0"
    matrix[0][0] = orphan
    cards_data = {orphan: make_salt_card(orphan, text="")}

    assert build_blueprint(matrix, StructureType.OTHER, cards_data) == []


# ══════════════════════════════════════════════════════════
#  6. 文章生成：全动态卡矩阵不再产出空白
# ══════════════════════════════════════════════════════════

def test_generate_article_all_dynamic_cards_pure_concat(store_path):
    """全动态卡矩阵（use_ai=False）应产出非空文章 —— 修复前 content 恒为空

    这是该 Bug 最严重的后果：玩家看到一张白纸且没有任何错误提示。
    """
    matrix = empty_matrix()
    ids = []
    cards_data = {}
    for i, (row, col) in enumerate([(0, 0), (1, 0), (2, 0)]):
        cid = f"article_1_dynamic_观点_{i:04x}aaaa_{20000 + i}"
        matrix[row][col] = cid
        ids.append(cid)
        text = f"第{i}段玩家划线原文，包含数据 {i}0% 与因果推论。"
        store.save_dynamic_card(
            make_card_dict(text_hash=f"{i:04x}aaaa", timestamp=20000 + i), text
        )
        cards_data[cid] = make_salt_card(cid, text=text)

    snapshot = {
        "matrix": matrix,
        "structure": StructureType.OTHER,
        "structure_name": "通用",
        "vector": None,
        "cards_data": cards_data,
    }

    result = generate_article(snapshot, title="", use_ai=False)

    assert result["content"].strip(), "全动态卡矩阵不该产出空文章"
    for i in range(3):
        assert f"第{i}段玩家划线原文" in result["content"]
    assert len(result["paragraphs"]) == len(result["blueprint"]) == 3
    assert [item["index"] for item in result["blueprint"]] == [0, 1, 2]


def test_generate_article_filters_empty_paragraphs_and_reindexes(store_path, monkeypatch):
    """防御层：generate_paragraph 返回空串时，paragraphs 与 blueprint 必须同步剔除

    只过滤其中一个会让响应里两个字段段数对不上，排查时无从定位丢了哪一段。
    """
    import game.api.article_generator as ag

    matrix = empty_matrix()
    cards_data = {}
    for i, (row, col) in enumerate([(0, 0), (1, 0), (2, 0)]):
        cid = f"article_1_dynamic_观点_{i:04x}bbbb_{30000 + i}"
        matrix[row][col] = cid
        cards_data[cid] = make_salt_card(cid, text=f"第{i}段原文")

    real_generate = ag.generate_paragraph

    def flaky(spec, structure_name, lean, length_level=None):
        # 中间那段模拟 AI 与兜底同时失败
        return "" if spec.index == 1 else real_generate(spec, structure_name, lean, length_level)

    monkeypatch.setattr(ag, "generate_paragraph", flaky)
    # 不打真实网络：call_tongyi 返回 None 时 generate_paragraph 会走
    # FALLBACK_PARAGRAPH 降级，产出非空段落，测试因此确定且快速
    monkeypatch.setattr(ag, "call_tongyi", lambda *a, **kw: None)

    snapshot = {
        "matrix": matrix,
        "structure": StructureType.OTHER,
        "structure_name": "通用",
        "vector": None,
        "cards_data": cards_data,
    }
    result = generate_article(snapshot, title="", use_ai=True)

    assert len(result["paragraphs"]) == 2
    assert len(result["blueprint"]) == 2
    assert all(p.strip() for p in result["paragraphs"])
    # index 必须重排，否则前端看到的段序会跳号（0, 2）
    assert [item["index"] for item in result["blueprint"]] == [0, 1]
    assert "\n\n\n" not in result["content"]


def test_dynamic_filler_is_woven_into_viewpoint_paragraph(store_path):
    """相邻的动态情绪卡应被织入观点段

    修复前 _find_adjacent_fillers 调 get_card_text(nid)，而它的 "_card_" 守卫
    会拒掉含 "_dynamic_" 的 ID → weave_cards 永远为空，动态情绪/修辞卡
    根本无法织入相邻观点段，段落干瘪。

    注：情绪卡自己不成段（build_blueprint 只为观点卡与驳论靶子建段），
    它只能作为填充卡依附到相邻观点段上。
    """
    matrix = empty_matrix()
    viewpoint = "article_1_dynamic_观点_1234aaaa_40001_0"
    filler = "article_1_dynamic_情绪_1234bbbb_40002_0"
    matrix[0][0] = viewpoint
    matrix[0][1] = filler  # 水平相邻

    store.save_dynamic_card(
        make_card_dict(text_hash="1234aaaa", timestamp=40001), "观点原文"
    )
    store.save_dynamic_card(
        make_card_dict(card_type="情绪", text_hash="1234bbbb", timestamp=40002), "情绪原文"
    )
    cards_data = {
        viewpoint: make_salt_card(viewpoint, text="观点原文"),
        filler: make_salt_card(filler, text="情绪原文", card_type="情绪"),
    }

    blueprint = build_blueprint(matrix, StructureType.OTHER, cards_data)

    assert len(blueprint) == 1, "情绪卡不单独成段"
    spec = blueprint[0]
    assert isinstance(spec, ParagraphSpec)
    assert spec.card_id == viewpoint
    # ParagraphSpec.card_text 是织入提示词与降级拼接的唯一来源，必须非空
    assert spec.card_text == "观点原文"
    # 原文非空后 classify_content_type 才有区分度（空串恒返回“观点类”）
    assert spec.content_type != ""
    # 动态填充卡必须被织入，且类型是规范形式（不带「卡」）
    assert spec.weave_cards == [("情绪", "情绪原文")]


def test_refutation_target_survives_with_text(store_path):
    """靶子段有原文时仍应正常生成破题段（对照用例，防止降级逻辑过度生效）

    用 3 张卡覆盖驳论结构的全部三个角色：
    首段=破题段（靶子）、中段=驳斥段、末段=立论收束段。
    只有 2 张时观点卡同时是末段，会直接拿到立论收束段而跳过驳斥段。
    """
    matrix = empty_matrix()
    target = "article_1_dynamic_漏洞_aaaa7777_50001_0"
    mid = "article_1_dynamic_观点_aaaa8888_50002_0"
    last = "article_1_dynamic_观点_aaaa9999_50003_0"
    matrix[0][0] = target
    matrix[1][0] = mid
    matrix[2][0] = last

    store.save_dynamic_card(
        make_card_dict(card_type="漏洞", text_hash="aaaa7777", timestamp=50001), "靶子原文"
    )
    store.save_dynamic_card(
        make_card_dict(text_hash="aaaa8888", timestamp=50002), "中段观点原文"
    )
    store.save_dynamic_card(
        make_card_dict(text_hash="aaaa9999", timestamp=50003), "末段观点原文"
    )
    cards_data = {
        target: make_salt_card(target, text="靶子原文", card_type="漏洞"),
        mid: make_salt_card(mid, text="中段观点原文"),
        last: make_salt_card(last, text="末段观点原文"),
    }

    blueprint = build_blueprint(matrix, StructureType.REFUTATION, cards_data)

    assert [spec.role for spec in blueprint] == ["破题段", "驳斥段", "立论收束段"]
    assert blueprint[0].card_text == "靶子原文"
    assert blueprint[0].card_type == "漏洞"
    assert [spec.card_id for spec in blueprint] == [target, mid, last]


# ══════════════════════════════════════════════════════
#  7. 端到端：划线 → 落盘 → 模拟重启 → 文章生成
# ══════════════════════════════════════════════════════

def _iter_gap_slices(payload: dict, length: int = 40):
    """枚举 linespots 之间空隙里的候选选区（前端 convention：[start, end)）

    落在空隙里的选区与任何 linespot 重叠率都是 0，/api/judge 必然
    miss 预设点而走到动态生成分支。
    """
    content = payload["content"]
    spots = sorted((int(s["start"]), int(s["end"])) for s in payload["linespots"])
    gap_starts = [0] + [end + 1 for (_, end) in spots]
    gap_ends = [start for (start, _) in spots] + [len(content)]

    for gap_start, gap_end in zip(gap_starts, gap_ends):
        if gap_end - gap_start < length:
            continue
        mid = (gap_start + gap_end) // 2
        start = max(0, min(mid - length // 2, len(content) - length))
        yield start, start + length


def _find_viewpoint_gap(payload: dict, length: int = 40):
    """找一段能被判成观点卡的空隙选区

    只有观点卡（与驳论靶子）会单独成段，情绪/漏洞/修辞卡只能作为填充卡
    织入相邻观点段。若随机拿到一张修辞卡，单独放进矩阵会得到空蓝图，
    测试就测不到真正想验证的东西了。
    """
    from game.api.api import _classify_card_type

    for start, end in _iter_gap_slices(payload, length):
        text = payload["content"][start:end].strip()
        if not (5 <= len(text) <= 200):
            continue
        card_type = _classify_card_type(text)[0]
        if normalize_card_type(card_type) == "观点":
            return start, end, text
    return None


def test_e2e_dynamic_card_survives_restart_into_article(store_path):
    """端到端：玩家划线 → 动态卡 → 清 session（模拟后端重启）→ 文章仍拿到原文

    这条链路是第 0 步修复的核心目标。修复前：
      - get_card_text 的 "_card_" 守卫拒掉动态卡 → card_text 恒空
      - session 重启即失，_reconstruct_dynamic_card 的 text 也恒空
      → 全动态卡矩阵生成的 content 为空，前端只显示一张白纸且无任何提示
    """
    from fastapi.testclient import TestClient

    from game.api.api import app
    from game.api.session import get_session

    payload = _load_article_payload("article_1")
    assert payload is not None, "article_1.json 应存在"
    found = _find_viewpoint_gap(payload)
    if found is None:
        pytest.skip("article_1 的 linespot 空隙里没有能判成观点卡的片段")
    start, end, selected_text = found

    client = TestClient(app)

    # 1. 玩家划线 → 未命中预设点 → 动态生成
    resp = client.post("/api/judge", json={
        "articleId": "article_1",
        "paragraphIndex": 0,
        "startOffset": start,
        "endOffset": end,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hit"] is True, f"应走动态卡分支，实际: {body}"

    card = body["card"]
    card_id = card["card_id"]
    assert "_dynamic_" in card_id
    # 协议出口的 card_type 必须带「卡」（前端 CardType 联合类型与卡牌资源键依赖）
    assert card["card_type"].endswith("卡")
    # end 是闭区间，前端 adaptSaltCard 会 +1 转成 [start, end)
    assert card["end"] == end - 1

    # 2. 已落盘，且存的是规范形式类型
    record = store.load_dynamic_card(card_id)
    assert record is not None, "动态卡应已落盘"
    assert record["text"] == selected_text
    assert not record["card_type"].endswith("卡")

    # 3. 模拟后端重启：session 内存缓存清空
    get_session().clear_cards_cache()
    assert get_session().get_cached_card(card_id) is None

    # 4. 重启后重建仍能拿到真实原文与真实向量（不再降级）
    rebuilt = _reconstruct_dynamic_card(card_id)
    assert rebuilt is not None
    assert rebuilt.text == selected_text
    assert "已过期" not in rebuilt.title
    assert (rebuilt.attribute_x, rebuilt.attribute_y) == (
        card["attribute_x"], card["attribute_y"]
    )

    # 5. 用这张动态卡合成文章（use_ai=False 避免打真实网络）
    #    slot 9 → MATRIX_LAYOUT 第 3 行（row_index=2）的 col 0
    gen = client.post("/api/articles/generate", json={
        "slots": [["9", card_id]],
        "use_ai": False,
    })
    assert gen.status_code == 200, gen.text
    result = gen.json()

    assert result["content"].strip(), "全动态卡矩阵不该产出空文章"
    assert selected_text[:12] in result["content"], "文章应包含动态卡原文"
    assert len(result["paragraphs"]) == len(result["blueprint"]) == 1
    assert result["blueprint"][0]["card_id"] == card_id
    assert result["blueprint"][0]["index"] == 0


def test_e2e_preset_card_path_unchanged(store_path):
    """对照：命中预设点的链路不受落盘改动影响

    预设卡的 SaltCard.text 恒为空，必须仍靠 get_card_text 从 article_lib 反查。
    """
    from fastapi.testclient import TestClient

    from game.api.api import app

    payload = _load_article_payload("article_1")
    assert payload is not None
    spot = payload["linespots"][0]

    client = TestClient(app)
    resp = client.post("/api/judge", json={
        "articleId": "article_1",
        "paragraphIndex": 0,
        # linespot 是闭区间，前端 convention 为 [start, end) → end + 1
        "startOffset": int(spot["start"]),
        "endOffset": int(spot["end"]) + 1,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hit"] is True

    preset_id = body["card"]["card_id"]
    assert "_dynamic_" not in preset_id, "精确命中预设区间不应走动态分支"
    assert body["card"]["card_type"].endswith("卡")
    # 预设卡不落盘
    assert store.load_dynamic_card(preset_id) is None

    # 预设卡仍能正常进文章
    gen = client.post("/api/articles/generate", json={
        "slots": [["9", preset_id]],
        "use_ai": False,
    })
    assert gen.status_code == 200, gen.text
    result = gen.json()
    if normalize_card_type(body["card"]["card_type"]) == "观点":
        assert result["content"].strip()
        assert get_card_text(preset_id)[:12] in result["content"]
