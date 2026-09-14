"""
测试 Judge API - 划线判定接口
验证 POST /api/judge 返回符合协议的 JudgeResult 格式

运行方式：
    cd Backend
    python test_judge_api.py      # 作为脚本单独跑
    pytest test_judge_api.py      # 或作为 pytest 用例跑

【既是脚本也是 pytest 用例】/api/judge 是在用端点，本文件的断言是它唯一的
回归网。因此失败一律用 assert 抛出：原来的「except Exception 兜底 + return False」
写法在 pytest 下永远显示通过（假绿灯），断言失败会被自己吞掉。
sys.stdout 编码劫持只放在 __main__ 守卫内：pytest 收集时会 import 本文件，
顶层替换 sys.stdout 会包住 pytest 的 capture 对象，卸载时抛
ValueError: I/O operation on closed file，导致整个 pytest 崩溃。
"""
import json
import sys
import io

from game.api.api import _find_best_spot, _load_engine_articles, _spot_to_card_response

# article_1.json 里六条 linespot 的 attribute_value（来自 JSON，不是向量模长）
EXPECTED_ATTRIBUTE_VALUES = [15, 15, 10, 10, 10, 5]
# 命中率阈值，与 /api/judge 端点保持一致
HIT_THRESHOLD = 60
# 本用例的断言（card_id 命名、linespot 数量与数值）全部针对 article_1，
# 因此必须显式钉住它。不能写 articles[0]：article_lib 下 sorted() 时
# ai_*.json 排在 article_*.json 之前（'i' < 'r'），AI 文章上线后
# articles[0] 已经变成 ai_09961d81（8 条 linespot）。
TARGET_ARTICLE_ID = "article_1"


def test_judge_api():
    print("=" * 70)
    print("🔍 测试 Judge API - 玩家划线判定")
    print("=" * 70)

    articles = _load_engine_articles()
    assert articles, "没有找到文章数据"

    matches = [a for a in articles if a.id == TARGET_ARTICLE_ID]
    assert matches, f"没有找到 {TARGET_ARTICLE_ID}，实际文章：{[a.id for a in articles]}"
    article = matches[0]
    print(f"\n✅ 使用文章: {article.title}")
    print(f"   内容长度: {len(article.content)} 字符")
    print(f"   预设划线点数量: {len(article.linespots)}")

    assert [spot.attribute_value for spot in article.linespots] == EXPECTED_ATTRIBUTE_VALUES
    print(f"   attribute_value: {EXPECTED_ATTRIBUTE_VALUES}（来自 JSON，不是向量模长）")

    for index, expected_value in enumerate(EXPECTED_ATTRIBUTE_VALUES):
        card_data = _spot_to_card_response(article, article.linespots[index], index)
        assert card_data["card_id"] == f"article_1_card_{index + 1}"
        assert card_data["attribute_value"] == expected_value
        assert card_data["start"] == article.linespots[index].start
        assert card_data["end"] == article.linespots[index].end
    print("   六张 Judge card attribute_value 均与 JSON 一致")

    # 显示所有预设的划线点
    print("\n📍 预设划线点 (linespots):")
    for i, spot in enumerate(article.linespots):
        text = article.content[spot.start:spot.end + 1]
        print(f"   [{i}] {spot.card_type}-{spot.rarity}: [{spot.start}-{spot.end}] \"{text[:30]}\"")

    print("\n" + "=" * 70)
    print("🧪 测试用例 1: 精确命中第一个划线点")
    print("=" * 70)

    # 测试1: 精确命中
    spot1 = article.linespots[0]
    best_index, best_spot, best_rate = _find_best_spot(
        article, spot1.start, spot1.end + 1
    )

    print(f"请求: startOffset={spot1.start}, endOffset={spot1.end + 1}")
    print(f"结果: matchRate={best_rate}%, hit={'✅ YES' if best_rate >= HIT_THRESHOLD else '❌ NO'}")

    assert best_spot is not None and best_rate >= HIT_THRESHOLD, "应该命中但未命中"
    card_data = _spot_to_card_response(article, best_spot, best_index)
    print("\n📦 JudgeResult (命中):")
    print(json.dumps({
        "hit": True,
        "matchRate": best_rate,
        "card": card_data
    }, ensure_ascii=False, indent=2))

    # 验证卡数据结构
    assert "card_id" in card_data, "缺少 card_id"
    assert "attribute_value" in card_data, "缺少 attribute_value"
    assert card_data["attribute_value"] == EXPECTED_ATTRIBUTE_VALUES[0], "attribute_value 不来自 JSON"
    assert "card_type" in card_data, "缺少 card_type"
    assert card_data["start"] == spot1.start, "canonical start 不来自命中 linespot"
    assert card_data["end"] == spot1.end, "canonical end 不来自命中 linespot"
    assert "attribute_x" not in card_data, "❌ 泄露敏感字段: attribute_x"
    assert "attribute_y" not in card_data, "❌ 泄露敏感字段: attribute_y"
    print("✅ 卡丹数据格式正确，无敏感信息泄露")

    wide_start = max(0, spot1.start - 3)
    wide_end = min(len(article.content), spot1.end + 1 + 3)
    wide_index, wide_spot, wide_rate = _find_best_spot(article, wide_start, wide_end)
    assert wide_spot is not None and wide_rate >= HIT_THRESHOLD, "宽选区应命中第一个 linespot"
    wide_card = _spot_to_card_response(article, wide_spot, wide_index)
    assert wide_card["start"] == spot1.start, "宽选区命中后 start 被错误替换为 request offset"
    assert wide_card["end"] == spot1.end, "宽选区命中后 end 被错误替换为 request offset"
    print("✅ 宽选区命中后仍返回 canonical linespot range")

    partial_start = spot1.start + 5
    partial_end = spot1.end - 4 + 1
    partial_index, partial_spot, partial_rate = _find_best_spot(
        article, partial_start, partial_end
    )
    assert partial_spot is not None and partial_rate >= HIT_THRESHOLD, "标准范围内的部分选区应命中"
    partial_card = _spot_to_card_response(article, partial_spot, partial_index)
    assert partial_card["start"] == spot1.start, "部分选区命中后 start 未恢复 canonical range"
    assert partial_card["end"] == spot1.end, "部分选区命中后 end 未恢复 canonical range"
    print("✅ 部分选区命中后恢复完整 canonical linespot range")

    print("\n" + "=" * 70)
    print("🧪 测试用例 2: 未命中（偏移范围太小）")
    print("=" * 70)

    # 测试2: 未命中（选择一段空白区域）
    fake_start = 100
    fake_end = 102  # 只有2个字符，太短
    best_index, best_spot, best_rate = _find_best_spot(article, fake_start, fake_end)

    print(f"请求: startOffset={fake_start}, endOffset={fake_end}")
    print(f"结果: matchRate={best_rate}%, hit={'✅ YES' if best_rate >= HIT_THRESHOLD else '❌ NO'}")

    assert not best_spot or best_rate < HIT_THRESHOLD, f"意外命中: rate={best_rate}%"
    print("\n📦 JudgeResult (未命中):")
    print(json.dumps({
        "hit": False,
        "message": "这里信息价值过低",
        "matchRate": best_rate
    }, ensure_ascii=False, indent=2))
    print("✅ 未命中结果正确")

    print("\n" + "=" * 70)
    print("🧪 测试用例 3: 部分命中（重叠率 > 60%）")
    print("=" * 70)

    # 测试3: 部分命中（稍微超出范围）
    spot2 = article.linespots[1]
    extended_start = max(0, spot2.start - 5)
    extended_end = min(len(article.content), spot2.end + 1 + 5)
    best_index, best_spot, best_rate = _find_best_spot(article, extended_start, extended_end)

    print(f"原区间: [{spot2.start}-{spot2.end}]")
    print(f"请求: startOffset={extended_start}, endOffset={extended_end}")
    print(f"结果: matchRate={best_rate}%, hit={'✅ YES' if best_rate >= HIT_THRESHOLD else '❌ NO'}")

    assert best_rate <= 100, f"错误: 重叠率超过100% ({best_rate}%)"
    print(f"✅ 重叠率在合理范围内: {best_rate}%")

    print("\n" + "=" * 70)
    print("🧪 测试用例 4: 超出100%（防止多划整篇文章）")
    print("=" * 70)

    # 测试4: 远超实际范围（应该被判定为多划，rate=0）
    huge_start = 0
    huge_end = 501
    best_index, best_spot, best_rate = _find_best_spot(article, huge_start, huge_end)

    print(f"请求: startOffset={huge_start}, endOffset={huge_end}")
    print(f"结果: matchRate={best_rate}%")

    assert best_rate == 0 or best_rate > 100, f"错误: 允许了多划 (rate={best_rate}%)"
    print(f"✅ 正确拒绝多划: rate={best_rate}% (应为0或>100)")

    print("\n" + "=" * 70)
    print("🎉 所有测试通过! Judge API 符合协议要求")
    print("=" * 70)


if __name__ == "__main__":
    # 设置标准输出编码为 UTF-8（仅限直接运行，见文件头说明）
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    test_judge_api()
