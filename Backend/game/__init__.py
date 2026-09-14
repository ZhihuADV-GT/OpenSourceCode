"""游戏主模块

刻意不再做任何再导出。全仓扫描（AST，含 tests 与根目录脚本）确认
`from game import X` 与 `import game` 的使用次数为 0：业务代码一律按子模块
导入——game.api（app）、game.models（Article / LineSpot / SaltCard）、
game.numerics.matrix_vector_system、game.numerics.card_rules、
game.data_loader、game.template_loader。

这里曾经再导出 9 个数据模型、12 个数值计算符号以及 FrontendBridge /
GameEvent / app。那条链有两个代价：一是 `import game` 会连带把 FastAPI
应用和整套创作流模块全部加载进来（哪怕只想读一个 dataclass），二是每删一个
死模块都要同步改三处 `__init__`，漏改就 ImportError。再导出链已随死模块移除。
"""
