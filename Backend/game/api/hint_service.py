"""
看山提示服务 - 规则引擎

职责：
- 分析文章内容，识别不同卡牌类型的特征段落
- 生成句子级阅读建议（带全文偏移坐标）
- 生成看山气泡文案（用 preview 定位）

坐标系说明：
- 所有偏移基于 article.content 全文连续序列（含 \n）
- 与 /api/judge 的 startOffset/endOffset 属于同一坐标系
- start 含，end 不含（遵循 JS Range convention）
"""

from __future__ import annotations

import re

# 卡型字面量的单一数据源：本模块内部全程用规范形式（不带「卡」），
# 仅在构造返回给前端的 hint["type"] 时用 display_card_type 转展示形式。
# classify_card 是本地关键词判型的唯一实现（看山提示与 /api/cards/dynamic 共用）。
from game.numerics.card_rules import (
    classify_card,
    display_card_type,
    normalize_card_type,
)


# ══════════════════════════════════════════════════════════
#  卡牌类型分类（判定本体在 card_rules.classify_card）
# ══════════════════════════════════════════════════════════


# 这里原本有一份 _classify_card_type_simple(text) -> str，与 api._classify_card_type
# 的关键词池、阈值与优先级瀑布逐字重复，只差返回值（本模块只要卡型，
# 那边还要属性值与向量）。两份共存时改一侧忘另一侧，就会出现「看山提示
# 这里藏着情绪卡，玩家划出来却是观点卡」的矛盾。现在判定本体只有
# game.numerics.card_rules.classify_card 一份，调用点取它的 .card_type 即可。
# 回归网见 tests/test_card_classifier.py（逐字对照两份旧实现的输出）。


# 卡型字面量的归一化/展示统一走 game.numerics.card_rules（见顶部 import）。
# 此处原有的 _normalize_card_type（加「卡」）与 card_rules.normalize_card_type（去「卡」）
# 方向相反，已删除。


# ══════════════════════════════════════════════════════════
#  文本切分工具
# ══════════════════════════════════════════════════════════


def split_into_paragraphs(content: str) -> list[tuple[int, str]]:
    """
    按 \n 拆分文章为逻辑段落，返回 [(start_offset, text), ...]
    
    注意：空段落会被跳过
    """
    paragraphs = []
    current_offset = 0
    
    for para in content.split('\n'):
        stripped = para.strip()
        if stripped:  # 跳过空段落
            paragraphs.append((current_offset, para))
        current_offset += len(para) + 1  # +1 for \n
    
    return paragraphs


def split_into_sentences(text: str) -> list[str]:
    """
    按 [。！？；] 切分句子
    
    返回的句子包含标点符号
    """
    # 按标点切分，保留标点
    sentences = re.split(r'(?<=[。！？；])', text)
    return [s for s in sentences if s.strip()]


# ══════════════════════════════════════════════════════════
#  核心：文章分析
# ══════════════════════════════════════════════════════════


def _hints_from_keywords(article_content: str) -> list[dict]:
    """
    关键词盲猜：扫描全文特征段落，生成推荐（覆盖动态卡牌特征区）
    """
    paragraphs = split_into_paragraphs(article_content)
    hints = []
    
    # 对每个段落采样分析
    for para_offset, para_text in paragraphs:
        # 取段落前100字采样
        sample = para_text[:100]
        card_type = classify_card(sample).card_type
        
        # 跳过默认观点（太泛）
        if card_type == "观点":
            continue
        
        # 提取特征句（按标点切分，取前2句）
        sentences = split_into_sentences(para_text)
        if not sentences:
            continue
        
        # 取特征句（前2句，或整段如果太短）
        feature_sentences = sentences[:2]
        feature_text = ''.join(feature_sentences)
        
        # 计算特征句的偏移区间
        feature_start = para_offset + para_text.find(feature_sentences[0])
        feature_end = feature_start + len(feature_text)
        
        # 生成 preview（前30字）
        preview = feature_text[:30]
        if len(feature_text) > 30:
            preview += "…"
        
        # 生成理由
        reason = _generate_reason(card_type)
        
        hints.append({
            "start": feature_start,
            "end": feature_end,
            "type": display_card_type(card_type),
            "preview": preview,
            "reason": reason,
        })
        
        # 关键词盲猜最多 3 条
        if len(hints) >= 3:
            break

    return hints


def _generate_reason(card_type: str) -> str:
    """根据卡牌类型生成理由文案"""
    reasons = {
        "观点": "包含具体数据或逻辑推理，适合收集",
        "漏洞": "有转折或逻辑跳跃，可能揭示漏洞",
        "情绪": "情感表达强烈，容易引起共鸣",
        "修辞": "使用比喻或修辞手法，富有文学性",
    }
    return reasons.get(card_type, "值得关注")


def _generate_hint_message(hints: list[dict]) -> str:
    """
    生成看山气泡文案
    
    用 preview 定位（不用段落号，因为前端没有段概念）
    """
    if not hints:
        return "这篇文章似乎比较平淡，再仔细看看有没有特别的表达~"
    
    # 用第一个 hint 的 preview
    first_hint = hints[0]
    preview = first_hint["preview"]
    # hint["type"] 已是展示形式（带「卡」），判定前先归一化
    card_type = normalize_card_type(first_hint["type"])
    
    # 根据类型生成不同文案（文案里的「情绪卡」等是自然语言，不是字面量判定）
    if card_type == "漏洞":
        return f"『{preview}』附近似乎有逻辑漏洞，去看看吧~"
    elif card_type == "情绪":
        return f"『{preview}』附近情感很强烈，可能藏着情绪卡~"
    elif card_type == "修辞":
        return f"『{preview}』用了巧妙的修辞，值得留意~"
    else:
        return f"『{preview}』附近藏着有价值的信息，去看看吧~"


# ══════════════════════════════════════════════════════════
#  便捷函数
# ══════════════════════════════════════════════════════════


def _hints_from_linespots(content: str, linespots: list[dict]) -> list[dict]:
    """从预设划线点生成推荐（设计者标注的高价值点，精确）"""
    hints = []
    # 按 attribute_value 降序（高价值优先）
    sorted_spots = sorted(linespots, key=lambda s: s.get("attribute_value", 0), reverse=True)
    for spot in sorted_spots:
        start = spot.get("start", 0)
        end = spot.get("end", 0)
        if end <= start:
            continue
        # linespot 的 card_type 是内部规范形式，出口转展示形式
        card_type = normalize_card_type(spot.get("card_type", "观点"))
        text = content[start:end]
        preview = text[:30] + ("…" if len(text) > 30 else "")
        hints.append({
            "start": start,
            "end": end,
            "type": display_card_type(card_type),
            "preview": preview,
            "reason": "看山标注的重点内容",
        })
    return hints


def _overlaps_any(hint: dict, existing: list[dict]) -> bool:
    """判断 hint 区间是否与已有推荐重叠"""
    for e in existing:
        if hint["start"] < e["end"] and hint["end"] > e["start"]:
            return True
    return False


def _merge_hints(linespot_hints: list[dict], keyword_hints: list[dict], limit: int = 5, linespot_quota: int = 3) -> list[dict]:
    """合并（配额制）：linespots 最多占 linespot_quota 席，留位置给关键词（动态卡牌特征区）；
    任一方不足时另一方补位；关键词与 linespots 重叠的跳过"""
    merged: list[dict] = []
    # 1. linespots 优先，但最多占配额（避免挤掉关键词）
    for h in linespot_hints[:linespot_quota]:
        merged.append(h)
    # 2. 关键词补充，跳过与已有重叠的
    for h in keyword_hints:
        if len(merged) >= limit:
            break
        if _overlaps_any(h, merged):
            continue
        merged.append(h)
    # 3. 关键词不足（重叠太多或无特征段）时，用剩余 linespots 补位
    if len(merged) < limit:
        for h in linespot_hints[linespot_quota:]:
            if len(merged) >= limit:
                break
            if _overlaps_any(h, merged):
                continue
            merged.append(h)
    return merged


def get_rule_based_hints(article_content: str, linespots: list[dict] | None = None) -> dict:
    """
    获取规则引擎的提示结果（混合模式）

    linespots 覆盖预设高价值点；关键词覆盖动态卡牌特征区。
    """
    linespot_hints = _hints_from_linespots(article_content, linespots or [])
    keyword_hints = _hints_from_keywords(article_content)
    hints = _merge_hints(linespot_hints, keyword_hints)
    message = _generate_hint_message(hints)

    return {
        "mode": "rule",
        "message": message,
        "hints": hints,
    }
