from __future__ import annotations

from pathlib import Path

from game.article_store import read_json_like
from game.models import Article, LineSpot
from game.numerics.card_rules import normalize_card_type


def load_article(path: str | Path) -> Article:
    article_path = Path(path)
    payload = read_json_like(article_path)
    spots = [
        LineSpot(
            start=int(item["start"]),
            end=int(item["end"]),
            # 数据入口归一化：card_type 一律收敛为不带「卡」的规范形式，
            # 避免带后缀的历史数据在下游相邻增益 / 驳论判定处静默失效
            card_type=normalize_card_type(item["card_type"]),
            rarity=str(item.get("rarity", "未分类")),  # [FIX] 如果缺少 rarity 字段，使用默认值
            attribute_value=int(item.get("attribute_value", 0)),
            vector_x=float(item.get("attribute_x", 0.0)),
            vector_y=float(item.get("attribute_y", 0.0)),
        )
        for item in payload.get("linespots", [])
    ]
    return Article(
        id=str(payload["id"]),
        title=str(payload["title"]),
        content=str(payload["content"]),
        target_value=int(payload.get("target_value", 100)),
        linespots=spots,
    )


def get_source_text(article: Article, start: int, end: int) -> str:
    """从文章内容中提取指定范围的文本"""
    content = article.content
    # 确保索引在有效范围内
    start = max(0, min(start, len(content)))
    end = max(start, min(end, len(content)))
    return content[start:end]
