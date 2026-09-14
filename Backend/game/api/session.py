"""会话状态管理 - 按玩家分区，记录向量与动态卡缓存

前端每次 POST /api/workspace/vectors 同步卡槽快照后，
后端按 player_id 记录最后一次 instant_vector；GET /api/workspace/vectors 把它
回给前端的定时轮询（stores/workspace.ts 的 setInterval）。

多玩家隔离：
  _vectors[player_id]       每个玩家各自的最后一次向量
  _cards_cache[player_id]   每个玩家各自的动态卡缓存

player_id 默认 "default"（向后兼容单人单机），前端通过 X-Player-Id 头传入。
"""

from __future__ import annotations

from typing import Dict, Optional

from game.numerics import Vector2D
from game.models import SaltCard


_DEFAULT_PLAYER = "default"


class SessionManager:
    """按玩家分区的会话状态

    所有方法都接受 player_id 作为第一参数。不传则用 "default"（向后兼容）。
    """

    def __init__(self) -> None:
        self._vectors: Dict[str, Vector2D] = {}
        self._cards_cache: Dict[str, Dict[str, SaltCard]] = {}

    def update_vector(self, vector: Vector2D, player_id: str = _DEFAULT_PLAYER) -> None:
        self._vectors[player_id] = vector

    def last_vector(self, player_id: str = _DEFAULT_PLAYER) -> Vector2D:
        return self._vectors.get(player_id, Vector2D(0.0, 0.0))

    # ========== 卡牌缓存管理 ==========

    def cache_card(self, card: SaltCard, player_id: str = _DEFAULT_PLAYER) -> None:
        """将卡牌存入该玩家的缓存（用于动态生成的卡牌）"""
        self._cards_cache.setdefault(player_id, {})[card.id] = card

    def get_cached_card(self, card_id: str, player_id: str = _DEFAULT_PLAYER) -> Optional[SaltCard]:
        """从该玩家的缓存中获取卡牌"""
        return self._cards_cache.get(player_id, {}).get(card_id)

    def clear_cards_cache(self, player_id: Optional[str] = None) -> None:
        """清空卡牌缓存

        player_id=None 清空所有玩家；指定则只清该玩家。
        """
        if player_id is None:
            self._cards_cache.clear()
        else:
            self._cards_cache.pop(player_id, None)


# 全局会话单例（内存态，重启后重置）
_session = SessionManager()


def get_session() -> SessionManager:
    return _session
