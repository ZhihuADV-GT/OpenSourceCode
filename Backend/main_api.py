"""FastAPI 应用启动入口"""
from __future__ import annotations

# 加载项目根目录的环境变量文件
from dotenv import load_dotenv
from pathlib import Path

# 用 cwd 的父目录定位项目根（兼容 python -m 和直接运行）
CWD = Path.cwd().resolve()
# 尝试查找项目根目录的 .env 文件
if (CWD / ".env").exists():
    load_dotenv(CWD / ".env", override=True)
    print(f"[dotenv] Loaded: {CWD / '.env'}")
elif (CWD.parent / ".env").exists():
    load_dotenv(CWD.parent / ".env", override=True)
    print(f"[dotenv] Loaded: {CWD.parent / '.env'}")
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)
        print(f"[dotenv] Loaded: {env_file}")
    else:
        print("[dotenv] No .env file found, using system environment variables")

# 将 backend 目录加入 sys.path
import sys

# 确保可以导入 game 模块
BACKEND_DIR = Path(__file__).parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 导入 FastAPI app
from game.api import app

# 如果是直接运行此文件
if __name__ == "__main__":
    import uvicorn

    # sys.path 已在文件顶部插入，app 也已在上方导入，此处无需重复
    uvicorn.run(
        "game.api:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
