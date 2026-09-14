"""游戏核心数据模型

只保留三个在用的 dataclass：

- LineSpot：文章 JSON 里的预设理解点，/api/judge 命中判定的比对目标
- SaltCard：卡牌（文章预设点卡 + 玩家划线生成的动态卡），贯穿配卡运算、
  会话缓存、落盘与局末文章生成
- Article：一篇文章（id / title / content / target_value / linespots）

这里曾经还有 10 个 dataclass：RouteType、SlotDef、LinkDef、RecipeTemplate、
Item、RewardOption、Achievement、Inventory、PlayerState，以及被完整定义了
两次的 GameResult（两份字段一模一样，后一份覆盖前一份）。它们的引用方全部
来自已删除的创作流与局外成长模块（compose_engine / recipe_system /
card_system / judge_system / reward_system / achievement_system /
highlight_system / route_system），那些模块删掉后这 10 个在本仓零引用。
其中 GameResult 与 Inventory 在删模块之前就已经是零引用的孤儿。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(slots=True)
class LineSpot:
    start: int
    end: int
    card_type: str
    rarity: str
    attribute_value: int = 0  # 文章 JSON 定义的理解点贡献值
    vector_x: float = 0.0  # 热度属性
    vector_y: float = 0.0  # 盐度属性

    def normalized(self) -> "LineSpot":
        if self.start <= self.end:
            return self
        return LineSpot(
            start=self.end,
            end=self.start,
            card_type=self.card_type,
            rarity=self.rarity,
            attribute_value=self.attribute_value,
            vector_x=self.vector_x,
            vector_y=self.vector_y,
        )
    
    @property
    def magnitude(self) -> float:
        """向量模长，用于兼容性"""
        return (self.vector_x**2 + self.vector_y**2)**0.5


@dataclass(slots=True)
class SaltCard:
    id: str
    articleId: str
    informationPointId: str
    text: str
    type: str
    rarity: str
    attribute_x: float = 0.0  # 热度属性
    attribute_y: float = 0.0  # 盐度属性
    vector_array: List[List[float]] = field(default_factory=list)  # 向量数组 [[x1,y1], [x2,y2], ...]
    title: str = ""
    description: str = ""
    source: str = ""
    sourceRange: tuple[int, int] = (0, 0)
    obtainedInRound: int = 0

    @property
    def name(self) -> str:
        return self.title or self.text

    @property
    def card_type(self) -> str:
        return self.type

    @card_type.setter
    def card_type(self, value: str) -> None:
        self.type = value
    
    @property
    def magnitude(self) -> float:
        """向量模长，用于评级计算"""
        return (self.attribute_x**2 + self.attribute_y**2)**0.5

    @property
    def base_value(self) -> int:
        """向后兼容：返回向量模长的整数值"""
        return int(self.magnitude)

    @base_value.setter
    def base_value(self, value: int) -> None:
        """向后兼容：将标量值均匀分配到 x 和 y"""
        scale = value / (2**0.5)
        self.attribute_x = scale
        self.attribute_y = scale

    @property
    def source_text(self) -> str:
        return self.source

    @source_text.setter
    def source_text(self, value: str) -> None:
        self.source = value

    @property
    def source_range(self) -> tuple[int, int]:
        return self.sourceRange

    @source_range.setter
    def source_range(self, value: tuple[int, int]) -> None:
        self.sourceRange = value

    @property
    def obtained_in_round(self) -> int:
        return self.obtainedInRound

    @obtained_in_round.setter
    def obtained_in_round(self, value: int) -> None:
        self.obtainedInRound = value


@dataclass(slots=True)
class Article:
    id: str
    title: str
    content: str
    target_value: int
    linespots: List[LineSpot]
