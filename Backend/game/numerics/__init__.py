"""数值计算模块

当前只有 matrix_vector_system 与 card_rules 两个在用实现：
- matrix_vector_system：POST /api/workspace/vectors 的配卡运算、
  动态卡跨局重建（_reconstruct_dynamic_card）
- card_rules：卡型字面量与数值区间的单一数据源，api / dynamic_card_store /
  dynamic_card_service 都从它取归一化规则

这里曾经再导出 ComposeEngine / CardSystem / JudgeSystem / RecipeSystem
四套「创作流」实现。它们唯一的生产入口是 /api/compose、/api/recipes 等
实验性端点，两个前端从未调用，已随端点一并删除（详见仓库根目录的
后端冗余清理报告）。Vector2D 的导出必须保留：game/api/session.py 走的是
`from game.numerics import Vector2D`。
"""

from .matrix_vector_system import Vector2D, MatrixVectorSystem, StructureType

__all__ = [
    "Vector2D",
    "MatrixVectorSystem",
    "StructureType",
]
