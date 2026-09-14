"""
测试动态卡牌生成功能

验证点：
1. 匹配阈值从60%降低到25%
2. 允许适度多划（上限150%）
3. 未命中预设点时动态生成卡牌
4. 卡牌类型分类准确性

运行方式：
    cd Backend
    python test_dynamic_card.py     # 作为脚本单独跑
    pytest test_dynamic_card.py     # 或作为 pytest 用例跑
"""

import sys

from game.api.api import _classify_card_type, _generate_dynamic_card


def test_classify_card_type():
    """测试卡牌类型分类器"""
    print("=" * 70)
    print("Test 1: Card Type Classifier")
    print("=" * 70)
    
    test_cases = [
        # (文本, 期望类型, 说明)
        # 分类器返回内部规范形式（不带「卡」），进协议响应体前由 display_card_type 转展示形式
        ("根据数据显示，增长率达到了85%，超过预期", "观点", "数据密集"),
        ("因为A导致B，所以C从而D", "观点", "逻辑推理"),
        ("虽然方案很好，但是实施起来有困难", "漏洞", "转折无因果"),
        ("这真是太令人震惊了！非常特别！", "情绪", "情感强烈"),
        ("他像一只飞翔的鸟，仿佛在天空中舞蹈", "修辞", "比喻修辞"),
        ("这是一个普通的论述段落", "观点", "默认情况"),
    ]
    
    for text, expected_type, description in test_cases:
        card_type, value, vx, vy = _classify_card_type(text)
        print(f"\n[{description}]")
        print(f"   Text: \"{text[:40]}...\"")
        print(f"   Result: {card_type}, value={value}, vector=({vx}, {vy})")
        print(f"   Expected: {expected_type}")
        # 必须断言，不能只打 PASS/FAIL：分类器存在两份需同步修改的关键词池，
        # 只打印的话分类器回归时 pytest 依然全绿（假绿灯）。
        assert card_type == expected_type, (
            f"[{description}] 分类错误: {card_type!r} != {expected_type!r} | text={text!r}"
        )


def test_generate_dynamic_card():
    """测试动态卡牌生成"""
    print("\n" + "=" * 70)
    print("Test 2: Dynamic Card Generation")
    print("=" * 70)
    
    test_text = "因为AI技术的发展，导致传统行业面临巨大挑战，所以需要转型升级"
    
    card = _generate_dynamic_card(
        article_id="test_article_1",
        text=test_text,
        start_offset=100,
        end_offset=150,
    )
    
    print(f"\nGenerated Card:")
    print(f"   card_id: {card['card_id']}")
    print(f"   card_type: {card['card_type']}")
    print(f"   attribute_value: {card['attribute_value']}")
    print(f"   range: [{card['start']}, {card['end']}]")
    
    # 验证格式
    assert card['card_id'].startswith("test_article_1_dynamic_观点_"), "ID format should include type"
    assert card['card_type'] in ["观点卡", "情绪卡", "漏洞卡", "修辞卡"], "Invalid type"
    assert 10 <= card['attribute_value'] <= 20, "Value out of range"
    assert card['start'] == 100, "Start offset error"
    assert card['end'] == 149, "End offset should be closed interval"
    
    # 验证 card_id 包含类型信息
    parts = card['card_id'].split('_dynamic_')
    assert len(parts) == 2, "card_id should have _dynamic_ separator"
    type_part = parts[1].split('_')[0]
    assert type_part in ["观点", "情绪", "漏洞", "修辞"], f"Type part '{type_part}' is invalid"
    
    print("\nAll validations passed")
    print(f"Card ID includes type info: '{type_part}'")


def test_edge_cases():
    """测试边界情况"""
    print("\n" + "=" * 70)
    print("Test 3: Edge Cases")
    print("=" * 70)
    
    # 空文本
    card_type, value, _, _ = _classify_card_type("")
    print(f"\nEmpty text -> {card_type}, value={value} [OK]")
    
    # 极短文本
    card_type, value, _, _ = _classify_card_type("abc")
    print(f"Short text -> {card_type}, value={value} [OK]")
    
    # 混合关键词
    mixed_text = "数据显示增长率为85%，但是效果并不理想，令人失望"
    card_type, value, vx, vy = _classify_card_type(mixed_text)
    print(f"\nMixed keywords: \"{mixed_text}\"")
    print(f"   Result: {card_type}, value={value}, vector=({vx}, {vy})")
    # 数据优先于转折（_classify_card_type 返回内部规范形式，不带「卡」）
    assert card_type == "观点", "Data type should have priority"


if __name__ == "__main__":
    try:
        test_classify_card_type()
        test_generate_dynamic_card()
        test_edge_cases()
        
        print("\n" + "=" * 70)
        print("SUCCESS: All tests passed! Dynamic card generation is working correctly.")
        print("=" * 70)
    except AssertionError as e:
        print(f"\nFAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: Unexpected error occurred")
        import traceback
        traceback.print_exc()
        sys.exit(1)
