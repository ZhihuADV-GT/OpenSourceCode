"""文章库（article_lib）读取层 —— 叶子模块，不 import 任何 game.* 模块

这里只定义一次、别处一律 import 的三件事：

- ``ARTICLE_LIB_DIR``：文章库目录。此前 api.py / matrix_vector_system.py /
  article_generator.py / dynamic_card_store.py 各自算了一份
  ``Path(__file__).resolve().parent.parent.parent / "article_lib"``，
  层数还得跟着文件所在深度数一遍，挪一次目录就要改四处。
- ``read_json_like``：读 JSON 并过滤 ``//`` 注释行。此前有三份实现，其中
  matrix_vector_system 那份的 docstring 直接写着「从data_loader.py复制」。
- ``discover_article_files``：扫描 ``article_*.json``（手写）与 ``ai_*.json``
  （AI 生成）。此前有两份同名函数，外加 article_generator._load_article_payload
  与根目录 test_ai_articles.py 里各一处内联 glob，共四份。

为什么必须是叶子模块，而不是塞进已有的 data_loader：
matrix_vector_system 由 ``game/numerics/__init__.py`` 在包初始化途中加载，而
data_loader 反向 ``from game.numerics.card_rules import normalize_card_type``。
若把本模块的内容放进 data_loader，那么「先 import data_loader」的一方会在
game.numerics 尚未初始化完时回头 import 还没执行到函数定义的 data_loader，
抛 ``cannot import name 'read_json_like' from partially initialized module``。
本模块只依赖标准库，从任何方向 import 都不会成环。

【不要在调用方做 ARTICLE_FILES 式的模块级快照】
``ARTICLE_FILES = discover_article_files()`` 这种 import 时定格的快照是已经修过
一次的 Bug 载体：api.py 那份会在 AI 生成新文章后用 ``global ARTICLE_FILES``
刷新，matrix_vector_system 那份从不刷新，两份同名快照分歧，导致新生成文章的
预设卡静默加载失败（_load_card_by_id 返回 None，向量计算劣化且无任何报错）。
快照还要求「每个写文章的地方都记得刷新」，漏一处就复发。article_lib 只有几十个
文件，两次 glob 的开销远小于随后逐文件的 JSON 解析，不值得为它牺牲正确性。
回归网见 tests/test_article_file_cache.py。
"""

from __future__ import annotations

import json
from pathlib import Path

# 本文件在 Backend/game/ 下，向上一级即 Backend/
_BACKEND_DIR = Path(__file__).resolve().parent.parent

ARTICLE_LIB_DIR = _BACKEND_DIR / "article_lib"


def read_json_like(path: Path) -> dict:
    """读取 JSON 文件，自动过滤整行 ``//`` 注释

    article_lib 里的手写文章带 ``//`` 注释，标准 json 解析会直接报错，
    所以所有文章读取都必须走这里。只剔除「整行以 // 开头」的行，
    不做行尾注释剥离——正文里出现 ``//``（如 URL）不能被误删。
    """
    raw_text = Path(path).read_text(encoding="utf-8")
    lines = [ln for ln in raw_text.splitlines() if not ln.lstrip().startswith("//")]
    return json.loads("\n".join(lines).strip())


def discover_article_files() -> list[Path]:
    """发现所有文章文件：``article_*.json``（手写）+ ``ai_*.json``（AI 生成）

    每次调用都实时扫描目录，不缓存结果（理由见模块 docstring）。
    返回按路径排序，保证 /api/articles/random 的候选顺序稳定。

    落盘的动态卡（dynamic_cards.json）刻意不匹配这两个 glob，
    否则会混进预设 linespot 池污染 /api/judge 的命中判定，
    详见 dynamic_card_store.py 顶部的「文件名约定 · 不可更改」。
    """
    # 读模块全局而非默认参数，这样测试可以 monkeypatch ARTICLE_LIB_DIR
    # 把文章库重定向到 tmp_path，无需重启或重新 import
    if not ARTICLE_LIB_DIR.exists():
        print(f"⚠️ [article_store] article_lib目录不存在: {ARTICLE_LIB_DIR}")
        return []

    _SKIP_STEMS = {"_template", "-model"}
    files = [
        p for p in ARTICLE_LIB_DIR.glob("article_*.json")
        if not any(skip in p.stem for skip in _SKIP_STEMS)
    ]
    files.extend(ARTICLE_LIB_DIR.glob("ai_*.json"))
    return sorted(files)
