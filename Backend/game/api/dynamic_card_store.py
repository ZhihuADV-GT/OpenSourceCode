"""动态卡牌持久化存储

动态卡（玩家划线生成）的**原文与向量无法从 card_id 反推**，而 session 内存缓存
（game/api/session.py 的 `_cards_cache`）是全局单例、重启即失，导致两个存量问题：

1. 局末文章生成时 `_reconstruct_dynamic_card` 的 `text` 恒为空 →
   `generate_paragraph` 直接返回 ""，动态卡段落静默消失（全动态卡矩阵 → 整篇空白）。
2. 后端重启后向量降级为档位默认值 → 同一副卡组的文章结构/基调随重启漂移
   （DevBox 每次 push 都重启，漂移是常态而非例外）。

本模块把动态卡落盘到 `article_lib/dynamic_cards.json`，作为 session 缓存之后、
ID 解析降级之前的**第二级数据源**。

【文件名约定 · 不可更改】
落盘文件名刻意不匹配 `article_*.json` / `ai_*.json`：这两个 glob 被
`article_store.discover_article_files` 扫描（matrix_vector_system 的 _load_card_by_id、
api 的 _get_raw_linespots、article_generator 的 _load_article_payload 全走它）。
若把动态卡写进这两类文件，动态卡会混进预设 linespot 池，污染
`/api/judge` 的 `_find_best_spot` 匹配——玩家随手一划反而"命中预设点"，
拿到劣化数值。新增任何落盘文件都必须避开这两个前缀。

【线程安全】
FastAPI 的同步端点跑在线程池里，`generate_article` 内部还有 ThreadPoolExecutor，
因此读写都过 `_LOCK`；写盘用临时文件 + `os.replace` 保证原子性，
避免并发写或写盘中途崩溃留下半截 JSON。
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Dict, Optional

# 复用 card_rules 的归一化，保证落盘的 card_type 是内部规范形式（不带「卡」）。
# card_rules 不 import 任何项目内模块，可安全顶层导入（无循环依赖风险）。
from game.numerics.card_rules import normalize_card_type
# article_lib 目录的唯一定义处，不再自己算 _BACKEND_DIR / "article_lib"
from game.article_store import ARTICLE_LIB_DIR

STORE_PATH = ARTICLE_LIB_DIR / "dynamic_cards.json"

# 记录上限：超出后按 created_at 淘汰最旧的。
# 动态卡是玩家划线的产物，单局配额 10 张，500 条足够覆盖数十局的排查需要；
# 不设上限会让文件无限增长，每次全量读写的开销线性上升。
_MAX_RECORDS = 500

SCHEMA_VERSION = 1

_LOCK = threading.Lock()

# 内存镜像：避免每次查询都读盘。None 表示尚未加载。
_cache: Optional[Dict[str, dict]] = None


# ══════════════════════════════════════════════════════════
#  读写底层
# ══════════════════════════════════════════════════════════

def _read_store() -> Dict[str, dict]:
    """从磁盘加载记录表（不带锁，调用方负责持锁）"""
    if not STORE_PATH.exists():
        return {}
    try:
        payload = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        # 文件损坏不应阻断游戏：退回空表，下次写入时覆盖重建
        return {}
    cards = payload.get("cards") if isinstance(payload, dict) else None
    if not isinstance(cards, dict):
        return {}
    return {str(k): v for k, v in cards.items() if isinstance(v, dict)}


def _write_store(cards: Dict[str, dict]) -> None:
    """原子写盘（不带锁，调用方负责持锁）"""
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": SCHEMA_VERSION, "cards": cards}
    tmp = STORE_PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, STORE_PATH)


def _get_cache() -> Dict[str, dict]:
    """取内存镜像，首次访问时加载（不带锁，调用方负责持锁）"""
    global _cache
    if _cache is None:
        _cache = _read_store()
    return _cache


def _evict_if_needed(cards: Dict[str, dict]) -> int:
    """超出上限时淘汰最旧记录，返回淘汰条数（不带锁）"""
    overflow = len(cards) - _MAX_RECORDS
    if overflow <= 0:
        return 0
    oldest = sorted(cards.items(), key=lambda kv: kv[1].get("created_at", 0))
    for key, _ in oldest[:overflow]:
        cards.pop(key, None)
    return overflow


# ══════════════════════════════════════════════════════════
#  对外接口
# ══════════════════════════════════════════════════════════

def save_dynamic_card(
    card_dict: dict,
    text: str,
    *,
    title: str = "",
    round_no: Optional[int] = None,
) -> bool:
    """落盘一张动态卡

    Args:
        card_dict: `_generate_dynamic_card` 的返回值（协议展示形式，含
            card_id / attribute_value / card_type / start / end / attribute_x / attribute_y）
        text: 卡牌原文（玩家选区经句边界扩展后的最终文本）
        title: 展示标题，原样回写以保证往返一致
        round_no: 局号，用于配额统计；/api/judge 当前不携带局号，可为 None

    Returns:
        是否写入成功。失败只记日志不抛异常——落盘是增强能力，
        不该因为磁盘问题让玩家划线直接失败。
    """
    card_id = str(card_dict.get("card_id") or "")
    # 空白字符也算无效：落一条空记录会让 _reconstruct_dynamic_card 的
    # text 非空判定通过、却给下游一段只有空白的原文
    if not card_id or not text.strip():
        return False

    # card_type 在响应体里是展示形式（带「卡」），落盘统一存规范形式，
    # 与 _load_card_by_id / _reconstruct_dynamic_card 的比较口径一致
    record = {
        "card_id": card_id,
        "article_id": card_id.split("_dynamic_")[0],
        "card_type": normalize_card_type(card_dict.get("card_type", "")),
        "text": text,
        "start": int(card_dict.get("start", 0)),
        "end": int(card_dict.get("end", 0)),
        "attribute_value": card_dict.get("attribute_value", 0),
        "attribute_x": float(card_dict.get("attribute_x", 0.0)),
        "attribute_y": float(card_dict.get("attribute_y", 0.0)),
        "rarity": "动态发现",
        "title": title,
        "round": round_no,
        "created_at": int(time.time() * 1000),
    }

    try:
        with _LOCK:
            cards = _get_cache()
            cards[card_id] = record
            evicted = _evict_if_needed(cards)
            _write_store(cards)
            if evicted:
                print(f"[dynamic-card-store] 超出上限 {_MAX_RECORDS}，淘汰最旧 {evicted} 条")
        return True
    except OSError as exc:
        print(f"[dynamic-card-store] 落盘失败 {card_id}: {exc}")
        return False


def load_dynamic_card(card_id: str) -> Optional[dict]:
    """按 card_id 读取落盘记录，未命中返回 None"""
    if not card_id:
        return None
    with _LOCK:
        record = _get_cache().get(card_id)
    # 返回副本，避免调用方就地修改污染内存镜像
    return dict(record) if record else None


def load_dynamic_text(card_id: str) -> str:
    """只取原文，未命中返回空串（供文章生成链路直接调用）"""
    record = load_dynamic_card(card_id)
    return str(record.get("text") or "") if record else ""


def find_card_id_by_hash(article_id: str, text_hash: str) -> Optional[str]:
    """按 (文章, 文本 hash) 反查已存在的 card_id，用于重复划线去重

    动态卡 ID 尾部的 timestamp 每次都不同，同一句话重复划会产生多张内容相同的卡，
    前端 isSourceCollected 按 cardId 判重看不出重复。此函数提供内容维度的去重入口。
    """
    if not article_id or not text_hash:
        return None
    suffix = f"_dynamic_"
    with _LOCK:
        cards = _get_cache()
        for card_id, record in cards.items():
            if record.get("article_id") != article_id:
                continue
            # ID 格式 {article}_dynamic_{type}_{hash}_{timestamp_ns}_{counter}
            parts = card_id.split(suffix, 1)
            if len(parts) != 2:
                continue
            sub = parts[1].rsplit("_", 2)  # 去掉尾部 timestamp_ns 与 counter
            # sub = ['{type}_{hash}', '{timestamp_ns}', '{counter}']
            if len(sub) == 3 and sub[1].isdigit() and sub[2].isdigit() and sub[0].endswith(f"_{text_hash}"):
                return card_id
    return None


def reset_cache() -> None:
    """丢弃内存镜像，下次访问重新读盘（测试与热更新用）"""
    global _cache
    with _LOCK:
        _cache = None
