"""快照流水线合并的等价性回归测试

合并前 MatrixVectorSystem 里有两个公开入口，各自逐字重复了同一条 4 步流水线：

    process_snapshot(slots) -> Vector2D   服务 POST /api/workspace/vectors
    export_snapshot(slots)  -> Dict       服务 POST /api/articles/generate

两者都跑「(可选)从后端加载卡牌 → snapshot_to_matrix → analyze_structure →
calculate_instant_vector」，唯一区别是 export_snapshot 把中间产物一并返回。
四行代码重复看起来无害，但流水线的**顺序本身就是语义**：analyze_structure
依赖 cards_data 已就位（否则 _count_viewpoint_cards 全数返回 0，结构恒为「其它」），
calculate_instant_vector 又依赖 structure 做后处理乘数。任何一侧改了顺序或漏了一步，
另一侧不会跟着改，两条 LIVE 端点就会静默给出不同的向量。

本文件在合并**之前**就把现有输出逐字钉死（8 块板覆盖 5 种结构分支），
合并后必须一个数字都不变。

运行：cd Backend; pytest tests/test_snapshot_pipeline.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 允许直接从 Backend 目录运行（无 conftest.py，也不依赖 pip install -e）
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from game.models import SaltCard
from game.numerics.card_rules import CARD_TYPES
from game.numerics.matrix_vector_system import (
    MatrixVectorSystem,
    StructureType,
    Vector2D,
)

# 卡型一律从 card_rules 取，不在测试里写字面量：判定口径变了这里会跟着变
GUANDIAN, QINGXU, LOUDONG, XIUCI = CARD_TYPES

# 各卡型的合规数值（见 Backend/article生成规则.md）：
# 观点第一象限 31~36、情绪第四象限 19~27、漏洞第二象限 19~27、修辞是相邻乘数
_CARD_VECTORS = {
    GUANDIAN: (33.0, 32.0),
    QINGXU: (24.0, -23.0),
    LOUDONG: (-22.0, 21.0),
    XIUCI: (1.20, 1.30),
}

# slot 编号 → 矩阵位置，与 MatrixVectorSystem.MATRIX_LAYOUT 一致
_SLOT_ROWS = [[1, 2, 3], [4, 5, 6, 7, 8], [9, 10, 11, 12, 13], [14, 15, 16]]

_N = None

# 8 块板 + 合并前实测的输出。G=观点 Q=情绪 L=漏洞 X=修辞
BOARDS: dict[str, tuple[list[list[str | None]], str, float, float]] = {
    # 驳论：首行 0 观点 + ≥1 漏洞，中间 ≥1 观点 → 走 ×1.15 后处理
    "refutation": (
        [[LOUDONG, QINGXU, LOUDONG],
         [GUANDIAN, _N, _N, _N, _N],
         [_N, _N, _N, _N, _N],
         [_N, _N, QINGXU, _N, _N]],
        StructureType.REFUTATION.name, 35.65, 36.57,
    ),
    # 总-分-总：首尾行各 1 张观点，中间 ≥1 张观点
    "total_sub_total": (
        [[_N, GUANDIAN, _N],
         [_N, _N, _N, _N, QINGXU],
         [GUANDIAN, _N, _N, _N, _N],
         [_N, GUANDIAN, _N]],
        StructureType.TOTAL_SUB_TOTAL.name, 123.0, 73.0,
    ),
    # 总-分：首行 1 张观点（总），尾行 2 张观点（分）
    "total_sub": (
        [[_N, GUANDIAN, _N],
         [_N, _N, GUANDIAN, _N, _N],
         [_N, _N, _N, _N, _N],
         [GUANDIAN, GUANDIAN, _N]],
        StructureType.TOTAL_SUB.name, 132.0, 128.0,
    ),
    # 分-总：首行 2 张观点（分），尾行 1 张观点（总）
    "sub_total": (
        [[GUANDIAN, GUANDIAN, _N],
         [_N, _N, _N, _N, _N],
         [_N, _N, QINGXU, _N, _N],
         [_N, GUANDIAN, _N]],
        StructureType.SUB_TOTAL.name, 123.0, 73.0,
    ),
    # 其它（分-分）：首尾行都 ≥2 张观点，走 ×0.75 后处理；满板含修辞卡相邻乘数
    # 刻意留一个空格子（slot_16），覆盖「矩阵有洞」时的相邻乘数取值
    "other_full_mixed": (
        [[GUANDIAN, GUANDIAN, GUANDIAN],
         [LOUDONG, QINGXU, QINGXU, XIUCI, GUANDIAN],
         [XIUCI, GUANDIAN, QINGXU, GUANDIAN, GUANDIAN],
         [GUANDIAN, GUANDIAN, _N]],
        StructureType.OTHER.name, 299.23, 180.15,
    ),
    # 其它（稀疏）：每行只 1 张卡，四行结构互不相邻
    "other_sparse": (
        [[GUANDIAN, _N, _N],
         [QINGXU, _N, _N, _N, _N],
         [LOUDONG, _N, _N, _N, _N],
         [XIUCI, _N, _N]],
        StructureType.OTHER.name, 26.25, 22.5,
    ),
    # 其它（全漏洞）：负向量堆叠，验证符号不被后处理乘数翻转
    "other_all_holes": (
        [[LOUDONG] * 3, [LOUDONG] * 5, [LOUDONG] * 5, [LOUDONG] * 3],
        StructureType.OTHER.name, -264.0, 252.0,
    ),
    # 其它（空板）：_find_non_empty_rows 返回 -1，短路成 OTHER
    "empty": (
        [[_N] * 3, [_N] * 5, [_N] * 5, [_N] * 3],
        StructureType.OTHER.name, 0.0, 0.0,
    ),
}


def _make_card(card_id: str, card_type: str) -> SaltCard:
    x, y = _CARD_VECTORS[card_type]
    return SaltCard(
        id=card_id,
        articleId="article_1",
        informationPointId="point_1",
        text=f"{card_type}测试文本",
        type=card_type,
        rarity="N",
        attribute_x=x,
        attribute_y=y,
    )


def _build_board(rows: list[list[str | None]]) -> tuple[list[SaltCard], list[list[str]]]:
    """把 4 行卡型布局摊成 (卡牌列表, 前端 SlotSnapshot)

    SlotSnapshot 是 [[slotId, cardId], ...]，空格子不进列表——
    这正是前端 POST 上来的形状，snapshot_to_matrix 会按 MATRIX_LAYOUT 填回去。
    """
    cards: list[SaltCard] = []
    slots: list[list[str]] = []
    for row_idx, row in enumerate(rows):
        for col_idx, card_type in enumerate(row):
            if card_type is None:
                continue
            slot_num = _SLOT_ROWS[row_idx][col_idx]
            card_id = f"c{slot_num}"
            cards.append(_make_card(card_id, card_type))
            slots.append([str(slot_num), card_id])
    return cards, slots


def _system_for(rows: list[list[str | None]]) -> tuple[MatrixVectorSystem, list[list[str]]]:
    """构造一个已装好卡牌数据、可直接跑流水线的系统（auto_load_cards=False 路径）"""
    cards, slots = _build_board(rows)
    system = MatrixVectorSystem()
    system.set_cards_data(cards)
    return system, slots


# ══════════════════════════════════════════════════════════
#  特征化：合并前的输出逐字锁定
# ══════════════════════════════════════════════════════════

@pytest.mark.parametrize("board_name", sorted(BOARDS))
def test_pipeline_output_is_locked(board_name):
    """两个入口的结构判定与向量数值必须与合并前实测值逐字相同

    这条是组 5 的主安全网：合并只允许把重复的 4 步抽成一处，
    任何数字变化都说明流水线被改了（顺序、漏步、或多跑了一步）。
    """
    rows, expected_structure, expected_x, expected_y = BOARDS[board_name]
    system, slots = _system_for(rows)

    exported = system.export_snapshot(slots, auto_load_cards=False)

    assert exported["structure"].name == expected_structure, board_name
    assert exported["structure_name"] == exported["structure"].value
    assert exported["vector"].x == pytest.approx(expected_x, abs=1e-9), board_name
    assert exported["vector"].y == pytest.approx(expected_y, abs=1e-9), board_name


@pytest.mark.parametrize("board_name", sorted(BOARDS))
def test_both_entry_points_agree_on_vector(board_name):
    """process_snapshot 的返回值必须等于 export_snapshot["vector"]

    /api/workspace/vectors 用前者、/api/articles/generate 用后者。
    两条端点算出的向量不一致，玩家看到的实时向量与局末文章里的向量就会打架。
    """
    rows, _, _, _ = BOARDS[board_name]
    cards, slots = _build_board(rows)

    left = MatrixVectorSystem()
    left.set_cards_data(cards)
    right = MatrixVectorSystem()
    right.set_cards_data(cards)

    instant = left.process_snapshot(slots, auto_load_cards=False)
    exported = right.export_snapshot(slots, auto_load_cards=False)

    assert isinstance(instant, Vector2D)
    assert (instant.x, instant.y) == (exported["vector"].x, exported["vector"].y), board_name


# ══════════════════════════════════════════════════════════
#  契约与内部一致性
# ══════════════════════════════════════════════════════════

def test_export_snapshot_shape_is_stable():
    """export_snapshot 的 5 个键与 article_generator 的消费契约不得变动

    article_generator.build_blueprint / generate_article 直接按这些键取值，
    少一个键就是局末文章生成整条链路 500。
    """
    rows, _, _, _ = BOARDS["other_full_mixed"]
    system, slots = _system_for(rows)

    exported = system.export_snapshot(slots, auto_load_cards=False)

    assert set(exported) == {"matrix", "structure", "structure_name", "vector", "cards_data"}
    # 中间产物必须与单独调用同一步的结果一致，否则「导出」名不副实
    matrix = system.snapshot_to_matrix(slots)
    assert exported["matrix"] == matrix
    assert exported["structure"] == system.analyze_structure(matrix)
    assert isinstance(exported["cards_data"], dict)
    assert exported["cards_data"] == dict(system.cards_data)
    assert len(exported["cards_data"]) == 15


def test_export_snapshot_does_not_alias_cards_data():
    """cards_data 必须是副本：调用方改它不能回写系统内部状态"""
    rows, _, _, _ = BOARDS["other_sparse"]
    system, slots = _system_for(rows)

    exported = system.export_snapshot(slots, auto_load_cards=False)
    exported["cards_data"].clear()

    assert len(system.cards_data) == 4


def test_auto_load_branch_also_agrees(monkeypatch):
    """auto_load_cards=True（两条端点的实际取值）下两个入口仍须一致

    加载卡牌那一步也在重复的流水线里，抽公共实现时最容易把它漏在一侧。
    """
    rows, _, _, _ = BOARDS["total_sub_total"]
    cards, slots = _build_board(rows)

    left = MatrixVectorSystem()
    right = MatrixVectorSystem()
    # 不打真实 article_lib：直接把加载结果替换成合成卡牌
    monkeypatch.setattr(left, "load_cards_from_backend", lambda card_ids: list(cards))
    monkeypatch.setattr(right, "load_cards_from_backend", lambda card_ids: list(cards))

    instant = left.process_snapshot(slots, auto_load_cards=True)
    exported = right.export_snapshot(slots, auto_load_cards=True)

    assert (instant.x, instant.y) == (exported["vector"].x, exported["vector"].y)
    # auto_load 分支必须真的把卡牌灌进 cards_data，否则结构判定会全数落空
    assert len(left.cards_data) == 4
    assert len(exported["cards_data"]) == 4
    assert exported["structure"].name == StructureType.TOTAL_SUB_TOTAL.name


def test_slots_accept_prefixed_slot_ids():
    """slot id 兼容 "slot_5" 写法（前端历史格式），两个入口都得认"""
    rows, _, _, _ = BOARDS["other_sparse"]
    cards, slots = _build_board(rows)
    prefixed = [[f"slot_{slot_id}", card_id] for slot_id, card_id in slots]

    system = MatrixVectorSystem()
    system.set_cards_data(cards)

    assert system.export_snapshot(prefixed, auto_load_cards=False)["matrix"] == \
        system.snapshot_to_matrix(slots)


# ══════════════════════════════════════════════════════════
#  单一实现
# ══════════════════════════════════════════════════════════

def test_pipeline_has_single_definition():
    """整条流水线只允许在源码里出现一次

    用 AST 数 calculate_instant_vector 的调用点：合并前 process_snapshot 与
    export_snapshot 各调一次（=2），合并后只应有抽出来的那一处（=1）。
    这条红了说明有人又把流水线抄了第二份。
    """
    import ast

    source = (_BACKEND_DIR / "game" / "numerics" / "matrix_vector_system.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)

    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "calculate_instant_vector"
    ]
    assert len(calls) == 1, (
        f"快照流水线在 {len(calls)} 处重复（行号 {[c.lineno for c in calls]}），"
        "process_snapshot 与 export_snapshot 必须共用同一条流水线"
    )
