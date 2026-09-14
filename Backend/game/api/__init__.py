"""API 模块 - FastAPI 应用与会话状态

对外必须保留 `app`：main_api.py 的 `from game.api import app` 和
uvicorn.run("game.api:app") 都依赖它，这是后端的启动入口。

这里曾经再导出 communication.FrontendBridge / GameEvent（事件广播桥）。
它的唯一消费者是 POST /api/compose 的结算广播与 GET /api/events 的轮询出口，
两个端点在两个前端里都零调用，已随端点与 communication 模块一并删除。
"""

from .session import SessionManager, get_session
from .api import app

__all__ = [
    "SessionManager",
    "get_session",
    "app",
]
