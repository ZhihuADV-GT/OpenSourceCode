"""
矩阵向量运算系统 v3.0.0
负责将前端SlotSnapshot转换为16格矩阵，并根据文章结构进行向量运算
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple, Optional, Dict

from game.article_store import discover_article_files, read_json_like
from game.models import SaltCard


# ========== 后端数据加载辅助函数 ==========

# read_json_like 与 discover_article_files 统一从 game.article_store 导入。
# 这里原本各有一份拷贝（read_json_like 的 docstring 还直接写着「从data_loader.py
# 复制」），连同 api.py 与 article_generator.py 一共四份文章发现逻辑。
#
# 【不要在调用方做 ARTICLE_FILES 式的模块级快照】
# 本模块曾经写有 `ARTICLE_FILES = _discover_article_files()` 且从不刷新，而 api.py
# 那份同名快照会在 AI 生成新文章后用 `global ARTICLE_FILES` 刷新。两份缓存因此分歧：
# /api/articles/random 立刻能读到新文章，本模块的 _load_card_by_id 却看不见，
# 新局用到新文章的预设卡时卡牌数据静默加载失败（只能靠 session 缓存兜底）。
# 现在两边都改成「查找时实时扫描」：article_lib 只有几十个文件，两次 glob 的开销
# 远小于随后逐文件 read_json_like 的 JSON 解析，不值得为它牺牲正确性。
# 回归网见 tests/test_article_file_cache.py。


# ========== 卡牌数值加载层守卫 ==========
# 规则的唯一定义在 game/numerics/card_rules.py（对应 Backend/article生成规则.md），
# 本处只做「加载时兜底」。历史上 AI 文章把修辞卡的 attribute_x/y（相邻乘数）
# 误填成 10-30 的向量量纲，会让相邻观点卡被放大十几倍、负值还会翻转盐度符号，
# 直接冲垮 instant_vector（评级虚高、路径图飞出边界）；观点/情绪/漏洞卡也大量越界。
# 钳制策略是「就近投影」：保留卡牌之间的相对强弱，不改变 AI 的标注意图。
from .card_rules import (
    clamp_card_vector,
    display_card_type,
    normalize_card_type,
    validate_card_vector,
)


def _sanitize_card_vector(card_type: str, x: float, y: float,
                          card_id: str = '') -> Tuple[float, float]:
    """按规则钳制一张卡的数值，越界时打日志（合规则原样返回）

    修辞卡的 x/y 是相邻乘数、其余卡型是向量分量，两者规则不同，
    由 clamp_card_vector 内部按卡型分流，调用方无需判断。
    """
    problems = validate_card_vector(card_type, x, y)
    if not problems:
        return x, y
    fixed_x, fixed_y = clamp_card_vector(card_type, x, y)
    print(f'⚠️ [matrix_vector] 卡牌数值越界，已就近钳制: {card_id} [{card_type}] '
          f'({x}, {y}) -> ({fixed_x}, {fixed_y}) | {"; ".join(problems)}')
    return fixed_x, fixed_y


def _load_card_by_id(card_id: str) -> Optional[SaltCard]:
    """
    根据card_id从文章JSON中查询卡牌完整数据
    
    【优化】支持动态生成的卡牌（通过解析 card_id 重建数据）
    
    Args:
        card_id: 卡牌ID (如 "article_1_card_1" 或 "article_1_dynamic_xxxx")
    
    Returns:
        SaltCard | None: 匹配的卡牌，未找到返回None
    """
    # 1. 优先从 Session 缓存中查找（本局刚生成的动态卡牌）
    from game.api.session import get_session
    session = get_session()
    cached_card = session.get_cached_card(card_id)
    if cached_card:
        return cached_card
    
    # 2. 检查是否为动态卡牌（格式: article_x_dynamic_hash_timestamp）
    if '_dynamic_' in card_id:
        return _reconstruct_dynamic_card(card_id)
    
    # 3. 从文章 JSON 的 linespots 中查找（预设点卡牌）
    #    实时扫描而非读模块级快照，理由见文件顶部「后端数据加载辅助函数」节注释
    for path in discover_article_files():
        payload = read_json_like(path)
        article_id = payload.get('id')
        
        for linespot in payload.get('linespots', []):
            if linespot.get('card_id') == card_id:
                # 加载即归一化：card_type 收敛为不带「卡」的规范形式，
                # 下游相邻增益、驳论判定与 compose 校验全部按规范形式比较
                card_type = normalize_card_type(linespot.get('card_type', ''))
                attr_x = float(linespot.get('attribute_x', 0.0))
                attr_y = float(linespot.get('attribute_y', 0.0))
                # 加载即钳制：存量文章里大量卡牌数值越界（见 card_rules 注释）
                attr_x, attr_y = _sanitize_card_vector(card_type, attr_x, attr_y, card_id)
                return SaltCard(
                    id=card_id,
                    articleId=article_id,
                    informationPointId='',
                    text='',
                    type=card_type,
                    rarity=linespot.get('rarity', '未分类'),
                    attribute_x=attr_x,
                    attribute_y=attr_y,
                    vector_array=[],
                    title='',
                )
    return None


def _reconstruct_dynamic_card(card_id: str) -> Optional[SaltCard]:
    """
    从落盘记录 / card_id 重建动态卡牌数据

    card_id 格式: {article_id}_dynamic_{type}_{text_hash}_{timestamp}
    例如: ai_52a4dadd_dynamic_观点_68e816e1_70458

    两级重建策略：
    ① 落盘命中（dynamic_card_store）—— 拿回真实原文与真实向量，重启后依然准确。
       这是首选路径：原文为空会让局末文章生成整段丢掉这张卡，
       向量降级会让同一副卡组的文章结构/基调随后端重启漂移。
    ② 落盘未命中（历史卡、磁盘丢失）—— 只能解析 ID 里的 type 映射降级向量，
       原文无法恢复。

    降级向量策略（根据卡牌类型，均须符合 Backend/article生成规则.md）：
    - 观点卡: vector=(32, 32)      第一象限，|x|,|y| 必须落在 31~36
    - 情绪卡: vector=(25, -25)     第四象限，|x|,|y| 必须落在 19~27
    - 漏洞卡: vector=(-25, 25)     第二象限，|x|,|y| 必须落在 19~27
    - 修辞卡: vector=(1.30, 1.30)  相邻乘数（1.05-1.60 开区间的中间值）
    """
    try:
        # ── ① 落盘优先 ──────────────────────────────
        # 延迟 import：game/api/__init__.py 会连带加载 api.py，而 api.py 顶层
        # import 了本模块，顶层导入会形成循环（同 _load_card_by_id 里
        # from game.api.session import get_session 的处理方式）。
        from game.api.dynamic_card_store import load_dynamic_card

        record = load_dynamic_card(card_id)
        if record and str(record.get("text") or "").strip():
            stored_type = normalize_card_type(record.get("card_type", ""))
            stored_title = str(record.get("title") or "")
            return SaltCard(
                id=card_id,
                articleId=record.get("article_id") or card_id.split('_dynamic_')[0],
                informationPointId="",
                text=str(record["text"]),
                type=stored_type,
                rarity=record.get("rarity", "动态发现"),
                attribute_x=float(record.get("attribute_x", 0.0)),
                attribute_y=float(record.get("attribute_y", 0.0)),
                vector_array=[],
                title=stored_title or display_card_type(stored_type),
            )

        # ── ② 降级：解析 card_id ─────────────────────
        # 解析 card_id: article_x_dynamic_type_hash_timestamp
        parts = card_id.split('_dynamic_')
        if len(parts) != 2:
            return None
        
        article_id = parts[0]
        remainder = parts[1]  # type_hash_timestamp
        
        # 进一步拆分: type_hash_timestamp
        sub_parts = remainder.split('_')
        if len(sub_parts) < 3:
            return None
        
        # ID 里的 type_short 本就是规范形式，仍过一次 normalize 以防历史 ID 带后缀
        card_type = normalize_card_type(sub_parts[0])  # 观点/情绪/漏洞/修辞
        # hash 和 timestamp 不需要恢复，仅用于唯一性
        
        # 根据卡牌类型设置对应的降级向量
        # 观点卡取 32（而不是旧值 25）：规则要求观点卡 |x|,|y| 必须 >30，25 是非法值
        type_vectors = {
            "观点": (32.0, 32.0),
            "情绪": (25.0, -25.0),
            "漏洞": (-25.0, 25.0),
            "修辞": (1.30, 1.30),  # 1.05-1.60 开区间的中间值
        }
        
        vector_x, vector_y = type_vectors.get(card_type, (32.0, 32.0))  # 默认观点
        
        return SaltCard(
            id=card_id,
            articleId=article_id,
            informationPointId="",
            text="",  # 降级路径无法恢复原文（落盘未命中）
            type=card_type,
            rarity="动态发现",
            attribute_x=vector_x,
            attribute_y=vector_y,
            vector_array=[],
            # title 是展示字段，按协议形式带「卡」后缀
            title=f"{display_card_type(card_type)}（已过期）",
        )
    except Exception:
        return None


# ========== 向量基础类 ==========

@dataclass(slots=True)
class Vector2D:
    """二维向量类 - 统一的向量基础类"""
    x: float  # 热度
    y: float  # 盐度

    def __add__(self, other: "Vector2D") -> "Vector2D":
        return Vector2D(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vector2D") -> "Vector2D":
        return Vector2D(self.x - other.x, self.y - other.y)

    def magnitude(self) -> float:
        """向量模长"""
        return (self.x**2 + self.y**2)**0.5


class StructureType(str, Enum):
    """文章结构类型"""
    REFUTATION = "驳论论证"          # 首行0观点+≥1漏洞，中间≥1观点
    PARALLEL = "并列论证"            # 中间2/4张观点，对称列，不水平相邻，含总
    PROGRESSIVE = "递进论证"         # 中间>3张观点，错位，不相邻
    TOTAL_SUB_TOTAL = "总-分-总"     # 首行=总，尾行=总
    TOTAL_SUB = "总-分"              # 首行=总，尾行=分
    SUB_TOTAL = "分-总"              # 首行=分，尾行=总
    OTHER = "其它"                   # 其他所有情况


@dataclass
class MatrixRow:
    """矩阵行定义"""
    row_index: int  # 0-3
    slot_positions: List[int]  # 该行对应的slot位置（1-16）
    
    def __post_init__(self):
        """验证slot数量"""
        if self.row_index in [0, 3]:  # 第1、4行
            assert len(self.slot_positions) == 3, f"第{self.row_index+1}行应有3个slot"
        else:  # 第2、3行
            assert len(self.slot_positions) == 5, f"第{self.row_index+1}行应有5个slot"


class MatrixVectorSystem:
    """矩阵向量运算系统"""
    
    # 16格矩阵布局定义
    MATRIX_LAYOUT = [
        MatrixRow(row_index=0, slot_positions=[1, 2, 3]),      # 第1行：slot_1, slot_2, slot_3
        MatrixRow(row_index=1, slot_positions=[4, 5, 6, 7, 8]), # 第2行：slot_4-8
        MatrixRow(row_index=2, slot_positions=[9, 10, 11, 12, 13]), # 第3行：slot_9-13
        MatrixRow(row_index=3, slot_positions=[14, 15, 16]),    # 第4行：slot_14-16
    ]
    
    def __init__(self):
        self.cards_data: Dict[str, SaltCard] = {}  # card_id -> SaltCard
    
    def set_cards_data(self, cards: List[SaltCard]) -> None:
        """设置卡牌数据（从session获取）"""
        self.cards_data = {card.id: card for card in cards}
    
    def load_cards_from_backend(self, card_ids: List[str]) -> List[SaltCard]:
        """
        从后端获取卡牌完整数据
        
        Args:
            card_ids: 卡牌ID列表
        
        Returns:
            List[SaltCard]: 完整的卡牌对象列表
        """
        cards = []
        for card_id in card_ids:
            card = _load_card_by_id(card_id)
            if card:
                cards.append(card)
        return cards
    
    def snapshot_to_matrix(self, slots: List[List[str]]) -> List[List[Optional[str]]]:
        """
        将前端SlotSnapshot转换为16格矩阵
        
        Args:
            slots: [[slotId, cardId], ...] 格式，cardId可能为空
        
        Returns:
            4x5矩阵，四个角为None，中间16格为card_id或None
        """
        # 初始化4x5矩阵，四个角为None
        matrix = [
            [None, None, None, None, None],  # 第1行
            [None, None, None, None, None],  # 第2行
            [None, None, None, None, None],  # 第3行
            [None, None, None, None, None],  # 第4行
        ]
        
        # 构建slot_id到card_id的映射
        slot_to_card: Dict[int, Optional[str]] = {}
        for slot_pair in slots:
            if len(slot_pair) >= 2:
                slot_id_str = slot_pair[0]
                card_id = slot_pair[1] if slot_pair[1] else None
                # 提取slot编号：兼容纯数字 "2" 和带前缀 "slot_2" 两种格式
                if '_' in slot_id_str:
                    slot_num = int(slot_id_str.split('_')[1])
                else:
                    slot_num = int(slot_id_str)
                slot_to_card[slot_num] = card_id
        # 按矩阵布局填入卡牌
        for row_def in self.MATRIX_LAYOUT:
            row_idx = row_def.row_index
            for col_idx, slot_num in enumerate(row_def.slot_positions):
                card_id = slot_to_card.get(slot_num)
                
                # 第1、4行的有效位置在中间3列（索引1-3）
                if row_idx in [0, 3]:
                    matrix[row_idx][col_idx + 1] = card_id
                # 第2、3行的有效位置在所有5列（索引0-4）
                else:
                    matrix[row_idx][col_idx] = card_id
        
        return matrix
    
    # ========== 行级辅助方法 ==========
    
    def _count_type_cards(self, row: List[Optional[str]], card_type: str) -> int:
        """统计一行中指定类型卡牌的数量（两边归一化后比较）"""
        count = 0
        target = normalize_card_type(card_type)
        for card_id in row:
            if card_id and card_id in self.cards_data:
                if normalize_card_type(self.cards_data[card_id].type) == target:
                    count += 1
        return count

    def _count_viewpoint_cards(self, row: List[Optional[str]]) -> int:
        """统计一行中观点卡的数量

        这里原本是第二份独立实现，与 _count_type_cards 逐字等价（只是把
        card_type 硬编码成「观点」），两份都各自做了 normalize_card_type。
        现在收敛成 _count_type_cards 的特例：卡型比较的规则只剩一处定义，
        以后改归一化口径不会再漏掉观点卡这条路径。保留本方法名是因为
        结构判定里有 7 处调用点，_count_viewpoint_cards(row) 比
        _count_type_cards(row, "观点") 更能说明意图。
        """
        return self._count_type_cards(row, "观点")
    
    def _is_row_empty(self, row: List[Optional[str]]) -> bool:
        """判断一行是否全空"""
        return all(card_id is None for card_id in row)
    
    def _find_non_empty_rows(self, matrix: List[List[Optional[str]]]) -> Tuple[int, int]:
        """找到首个和末个非空行索引，返回 (first_idx, last_idx)，-1表示未找到"""
        first_idx = -1
        last_idx = -1
        for i, row in enumerate(matrix):
            if not self._is_row_empty(row):
                if first_idx == -1:
                    first_idx = i
                last_idx = i
        return first_idx, last_idx
    
    def _get_viewpoint_positions(self, row: List[Optional[str]]) -> List[int]:
        """获取一行中所有观点卡的列索引"""
        positions = []
        for col, card_id in enumerate(row):
            if card_id and card_id in self.cards_data:
                card = self.cards_data[card_id]
                if normalize_card_type(card.type) == "观点":
                    positions.append(col)
        return positions
    
    def _has_horizontal_adjacent(self, positions: List[int]) -> bool:
        """检查一组列索引中是否存在水平相邻"""
        sorted_pos = sorted(positions)
        for i in range(len(sorted_pos) - 1):
            if sorted_pos[i + 1] - sorted_pos[i] == 1:
                return True
        return False
    
    # ========== 结构检测辅助方法 ==========
    
    def _check_middle_row_conditions(self, matrix: List[List[Optional[str]]],
                                      min_count: int, max_count: int = 999,
                                      check_stagger: bool = False,
                                      check_no_adjacent: bool = False,
                                      allow_vertical_adjacent: bool = False) -> bool:
        """检查中间两行(row 1, row 2)是否满足指定条件"""
        r1_positions = self._get_viewpoint_positions(matrix[1])
        r2_positions = self._get_viewpoint_positions(matrix[2])
        total = len(r1_positions) + len(r2_positions)
        
        if total < min_count or total > max_count:
            return False
        
        # 错位检测：两行的观点卡列集合不完全相同
        if check_stagger:
            if set(r1_positions) == set(r2_positions) and len(r1_positions) > 0:
                return False
        
        # 水平相邻检测（两行各自检查）
        if check_no_adjacent:
            if self._has_horizontal_adjacent(r1_positions):
                return False
            if self._has_horizontal_adjacent(r2_positions):
                return False
        
        # 垂直相邻检测（仅row 1与row 2之间）
        if check_no_adjacent and not allow_vertical_adjacent:
            for col in r1_positions:
                if col in r2_positions:
                    return False
        
        return True
    
    def _is_symmetric_columns(self, positions: List[int]) -> bool:
        """
        检查列索引是否成对称列对（col 0↔4, col 1↔3）且数量一一对应
        
        行可上下错开（跨行匹配），但每个左列卡必须有数量相等的右列镜像卡
        """
        if len(positions) == 0:
            return True
        symmetric_pairs = {0: 4, 4: 0, 1: 3, 3: 1}
        # 统计各列出现次数
        counts: Dict[int, int] = {}
        for col in positions:
            counts[col] = counts.get(col, 0) + 1
        # 每列必须在对称映射中，且与其镜像列数量一一对应
        for col, cnt in counts.items():
            if col not in symmetric_pairs:
                return False  # col 2 是中轴线，不参与左右分配
            if counts.get(symmetric_pairs[col], 0) != cnt:
                return False
        return True
    
    def _detect_refutation(self, matrix: List[List[Optional[str]]]) -> bool:
        """检测驳论论证：首行0观点+≥1漏洞，中间两行≥1观点"""
        first_idx, _ = self._find_non_empty_rows(matrix)
        if first_idx == -1:
            return False
        
        first_row = matrix[first_idx]
        if self._count_viewpoint_cards(first_row) != 0:
            return False
        if self._count_type_cards(first_row, '漏洞') < 1:
            return False
        
        # 中间两行合计至少1张观点
        middle_viewpoints = (self._count_viewpoint_cards(matrix[1]) +
                             self._count_viewpoint_cards(matrix[2]))
        return middle_viewpoints >= 1
    
    def _detect_parallel(self, matrix: List[List[Optional[str]]]) -> bool:
        """检测并列论证：中间恰好2或4张观点，对称列，不水平相邻，含总行"""
        r1_pos = self._get_viewpoint_positions(matrix[1])
        r2_pos = self._get_viewpoint_positions(matrix[2])
        total = len(r1_pos) + len(r2_pos)
        
        # 观点卡必须恰好 2 或 4 张（不接受 3 张）
        if total not in (2, 4):
            return False
        
        # 不水平相邻（允许垂直相邻）
        if self._has_horizontal_adjacent(r1_pos) or self._has_horizontal_adjacent(r2_pos):
            return False
        
        all_positions = r1_pos + r2_pos
        
        # 对称列检测
        if not self._is_symmetric_columns(all_positions):
            return False
        
        # 必须存在一个"总"行（某行恰好1张观点卡）
        for row in matrix:
            if not self._is_row_empty(row) and self._count_viewpoint_cards(row) == 1:
                return True
        return False
    
    def _detect_progressive(self, matrix: List[List[Optional[str]]]) -> bool:
        """检测递进论证：中间>3张观点，错位，不相邻（含垂直）"""
        return self._check_middle_row_conditions(
            matrix, 4, check_stagger=True, check_no_adjacent=True,
            allow_vertical_adjacent=False
        )
    
    # ========== 结构分析 ==========
    
    def analyze_structure(self, matrix: List[List[Optional[str]]]) -> StructureType:
        """
        分析矩阵的文章结构（按优先级从高到低判断）
        
        优先级：驳论 > 并列 > 递进 > 总-分-总/总-分/分-总 > 其它
        
        Returns:
            StructureType
        """
        first_idx, last_idx = self._find_non_empty_rows(matrix)
        
        if first_idx == -1 or first_idx == last_idx:
            return StructureType.OTHER
        
        # --- 优先级1：驳论论证 ---
        if self._detect_refutation(matrix):
            return StructureType.REFUTATION
        
        # --- 优先级2：并列论证 ---
        if self._detect_parallel(matrix):
            return StructureType.PARALLEL
        
        # --- 优先级3：递进论证 ---
        if self._detect_progressive(matrix):
            return StructureType.PROGRESSIVE
        
        # --- 优先级4：总-分-总 / 总-分 / 分-总 ---
        first_viewpoint_count = self._count_viewpoint_cards(matrix[first_idx])
        
        if first_viewpoint_count == 1:
            first_row_type = "总"
        elif first_viewpoint_count >= 2:
            first_row_type = "分"
        else:
            return StructureType.OTHER
        
        last_viewpoint_count = self._count_viewpoint_cards(matrix[last_idx])
        
        if last_viewpoint_count == 1:
            last_row_type = "总"
        elif last_viewpoint_count >= 2:
            last_row_type = "分"
        else:
            return StructureType.OTHER
        
        if first_row_type == "总" and last_row_type == "总":
            middle_viewpoint_count = 0
            for i in range(first_idx + 1, last_idx):
                middle_viewpoint_count += self._count_viewpoint_cards(matrix[i])
            if middle_viewpoint_count >= 1:
                return StructureType.TOTAL_SUB_TOTAL
            return StructureType.OTHER
        elif first_row_type == "总" and last_row_type == "分":
            return StructureType.TOTAL_SUB
        elif first_row_type == "分" and last_row_type == "总":
            return StructureType.SUB_TOTAL
        else:  # 分-分
            return StructureType.OTHER
    
    # ========== 相邻乘数系统 ==========
    
    def _get_adjacency_multiplier(self, matrix: List[List[Optional[str]]],
                                   row: int, col: int) -> Tuple[float, float]:
        """
        计算单个观点卡基于相邻卡牌的乘数
        
        规则：
        - 第1、4行(row 0, 3)：仅水平相邻
        - 第2、3行(row 1, 2)：水平 + 垂直相邻（垂直仅限row 1与row 2之间）
        - 情绪相邻: x×1.3, y×0.8
        - 漏洞相邻: x×0.8, y×1.3
        - 修辞相邻: x×修辞.attribute_x, y×修辞.attribute_y
        - 观点相邻: 无增益
        """
        mult_x, mult_y = 1.0, 1.0
        
        # 水平相邻方向
        neighbors = [(row, col - 1), (row, col + 1)]
        
        # 垂直相邻：仅row 1和row 2之间互相计算，row 0和row 3不参与
        if row in (1, 2):
            other_row = 3 - row  # 1↔2
            neighbors.append((other_row, col))
        
        for nr, nc in neighbors:
            if 0 <= nr < 4 and 0 <= nc < 5:
                neighbor_id = matrix[nr][nc]
                if neighbor_id and neighbor_id in self.cards_data:
                    neighbor_card = self.cards_data[neighbor_id]
                    ntype = normalize_card_type(neighbor_card.type)
                    if ntype == '情绪':
                        mult_x *= 1.25
                        mult_y *= 0.75
                    elif ntype == '漏洞':
                        mult_x *= 0.75
                        mult_y *= 1.25
                    elif ntype == '修辞':
                        mult_x *= neighbor_card.attribute_x
                        mult_y *= neighbor_card.attribute_y
                    # 观点相邻无增益
        
        return mult_x, mult_y
    
    def _calculate_row_contribution(self, matrix: List[List[Optional[str]]],
                                     row_idx: int,
                                     excluded_positions: Optional[List[int]] = None
                                     ) -> Tuple[float, float]:
        """
        计算一行的向量贡献（修辞卡不参与求和，仅作为相邻增益）
        
        Args:
            matrix: 4x5矩阵
            row_idx: 行索引
            excluded_positions: 需要跳过的列索引（用于驳论row 0的特殊已处理位置）
        
        Returns:
            (x, y) 贡献值
        """
        total_x, total_y = 0.0, 0.0
        excluded = set(excluded_positions) if excluded_positions else set()
        
        for col, card_id in enumerate(matrix[row_idx]):
            if not card_id or card_id not in self.cards_data:
                continue
            if col in excluded:
                continue
            
            card = self.cards_data[card_id]
            ctype = normalize_card_type(card.type)
            
            # 修辞卡仅作为相邻增益，其自身x/y不带入最终求和
            if ctype == '修辞':
                continue
            
            # 观点卡应用相邻乘数
            if ctype == '观点':
                mult_x, mult_y = self._get_adjacency_multiplier(matrix, row_idx, col)
                total_x += card.attribute_x * mult_x
                total_y += card.attribute_y * mult_y
            else:
                # 非修辞、非观点卡（情绪、漏洞等）：直接加入
                total_x += card.attribute_x
                total_y += card.attribute_y
        
        return total_x, total_y
    
    def _calculate_refutation_row0(self, matrix: List[List[Optional[str]]],
                                    first_idx: int) -> Tuple[float, float, List[int]]:
        """
        驳论论证首行特殊处理
        
        注：驳论首行按定义不含观点卡（由 _detect_refutation 保证），
        故此处仅处理情绪/漏洞卡；修辞卡不入和；其余位置由
        _calculate_row_contribution 按 excluded_positions 跳过已处理卡。
        
        规则：
        1. 第一张情绪 + 所有漏洞先求和，后 x×1.4, y×1.3
        2. 第二张及以后的情绪卡，直接加原值（不做任何乘数处理）
        
        Returns:
            (result_x, result_y, special_positions) — special_positions 为已特殊处理的列索引
        """
        row = matrix[first_idx]
        emotion_cards = []
        loophole_cards = []
        
        for col, card_id in enumerate(row):
            if card_id and card_id in self.cards_data:
                card = self.cards_data[card_id]
                ctype = normalize_card_type(card.type)
                if ctype == '情绪':
                    emotion_cards.append((col, card))
                elif ctype == '漏洞':
                    loophole_cards.append((col, card))
        
        result_x, result_y = 0.0, 0.0
        special_positions = []
        
        # 步骤1：第一张情绪 + 所有漏洞先求和
        sum_x, sum_y = 0.0, 0.0
        for col, card in emotion_cards[:1] + loophole_cards:
            sum_x += card.attribute_x
            sum_y += card.attribute_y
            special_positions.append(col)
        
        # 后乘: x×1.4, y×1.3
        result_x += sum_x * 1.3
        result_y += sum_y * 1.2
        
        # 步骤2：第二张及以后的情绪卡，直接加原值
        for col, card in emotion_cards[1:]:
            result_x += card.attribute_x
            result_y += card.attribute_y
            special_positions.append(col)
        
        # 修辞卡不参与求和
        
        return result_x, result_y, special_positions
    
    # ========== 向量计算主入口 ==========
    
    def calculate_instant_vector(self, matrix: List[List[Optional[str]]],
                                  structure: StructureType) -> Vector2D:
        """
        根据文章结构计算instant_vector（基于相邻乘数系统）
        
        规则：
        - 修辞卡不参与最终求和，仅作为相邻增益
        - 观点卡受相邻卡牌类型影响乘数
        - 驳论论证首行特殊处理，全文×1.1
        - 其它分类所有非修辞卡直接求和×0.7
        """
        first_idx, last_idx = self._find_non_empty_rows(matrix)
        if first_idx == -1:
            return Vector2D(0.0, 0.0)
        
        total_x, total_y = 0.0, 0.0
        is_refutation = (structure == StructureType.REFUTATION)
        
        # --- 驳论首行特殊处理 ---
        refutation_row0_excluded = []
        if is_refutation:
            rx, ry, excluded = self._calculate_refutation_row0(matrix, first_idx)
            total_x += rx
            total_y += ry
            refutation_row0_excluded = excluded
        
        # --- 逐行计算贡献 ---
        for row_idx in range(4):
            if self._is_row_empty(matrix[row_idx]):
                continue
            
            if row_idx == first_idx and is_refutation:
                # 驳论首行：排除已特殊处理的情绪/漏洞位置
                rx, ry = self._calculate_row_contribution(
                    matrix, row_idx, refutation_row0_excluded)
            else:
                rx, ry = self._calculate_row_contribution(matrix, row_idx)
            
            total_x += rx
            total_y += ry
        
        # --- 结构后处理 ---
        if is_refutation:
            # 驳论：全文 x×1.1, y×1.1
            total_x *= 1.15
            total_y *= 1.15
        elif structure == StructureType.OTHER:
            # 其它分类：×0.7
            total_x *= 0.75
            total_y *= 0.75
        
        return Vector2D(round(total_x, 2), round(total_y, 2))
    
    def _run_pipeline(self, slots: List[List[str]], auto_load_cards: bool
                      ) -> Tuple[List[List[Optional[str]]], StructureType, Vector2D]:
        """快照流水线本体：(可选)加载卡牌 -> 矩阵 -> 结构分析 -> 向量计算

        这四步原本被 process_snapshot 与 export_snapshot 各抄了一份（逐字相同），
        而【顺序本身就是语义】：analyze_structure 依赖 cards_data 已就位（否则
        _count_type_cards 全数返回 0，结构恒判「其它」），calculate_instant_vector
        又依赖 structure 做后处理乘数（驳论 ×1.15 / 其它 ×0.75）。两份共存时
        改一侧忘另一侧，/api/workspace/vectors 与 /api/articles/generate 就会算出
        不同的向量，玩家看到的实时向量与局末文章里的向量对不上。

        返回三个中间产物，由调用方决定取用哪几个：process_snapshot 只要向量，
        export_snapshot 全都要（article_generator 按 matrix / structure /
        structure_name / vector / cards_data 五个键消费）。

        Args:
            slots: 前端发送的卡槽快照 [[slotId, cardId], ...]
            auto_load_cards: 是否先从后端加载卡牌数据并覆盖 cards_data

        Returns:
            (matrix, structure, instant_vector)
        """
        # 自动从后端获取卡牌数据
        if auto_load_cards:
            card_ids = [slot[1] for slot in slots if len(slot) >= 2 and slot[1]]
            cards = self.load_cards_from_backend(card_ids)
            self.set_cards_data(cards)

        # 转换为矩阵
        matrix = self.snapshot_to_matrix(slots)

        # 分析文章结构
        structure = self.analyze_structure(matrix)

        # 计算向量
        instant_vector = self.calculate_instant_vector(matrix, structure)

        return matrix, structure, instant_vector

    def process_snapshot(self, slots: List[List[str]], auto_load_cards: bool = True) -> Vector2D:
        """
        完整处理流程：SlotSnapshot -> 矩阵 -> 结构分析 -> 向量计算
        
        Args:
            slots: 前端发送的卡槽快照
            auto_load_cards: 是否自动从后端加载卡牌数据（默认True）
        
        Returns:
            Vector2D: 最终的instant_vector
        """
        # 整条流水线在 _run_pipeline，本入口只要最终的 instant_vector
        _, _, instant_vector = self._run_pipeline(slots, auto_load_cards)
        return instant_vector

    def export_snapshot(self, slots: List[List[str]], auto_load_cards: bool = True) -> Dict:
        """
        导出完整快照：矩阵 + 结构 + 向量（供文章生成模块使用）
        
        Args:
            slots: 前端发送的卡槽快照
            auto_load_cards: 是否自动从后端加载卡牌数据
        
        Returns:
            Dict: {
                "matrix": 4x5矩阵（card_id 或 None）,
                "structure": StructureType 枚举值,
                "structure_name": 结构中文名称,
                "vector": Vector2D,
                "cards_data": {card_id: SaltCard} 映射
            }
        """
        # 与 process_snapshot 共用 _run_pipeline，只是把中间产物一并交出去
        matrix, structure, instant_vector = self._run_pipeline(slots, auto_load_cards)

        return {
            "matrix": matrix,
            "structure": structure,
            "structure_name": structure.value,
            "vector": instant_vector,
            "cards_data": dict(self.cards_data),
        }