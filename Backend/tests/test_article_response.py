"""
测试 ArticleResponse 数据格式
验证 /api/articles/random 接口只返回符合协议的4个字段，不包含敏感信息

运行方式：
    cd Backend
    python test_article_response.py      # 作为脚本单独跑
    pytest test_article_response.py      # 或作为 pytest 用例跑

【既是脚本也是 pytest 用例】失败一律用 assert 抛出，不要写成「return False」——
return 值在 pytest 下不会让用例失败，只会得到 PytestReturnNotNoneWarning，
表现为永远通过的假绿灯。也不要用 except Exception 兜住断言错误。
sys.stdout 编码劫持只放在 __main__ 守卫内：pytest 收集时会 import 本文件，
顶层替换 sys.stdout 会包住 pytest 的 capture 对象，卸载时抛
ValueError: I/O operation on closed file，导致整个 pytest 崩溃。
"""
import json
import sys
import io

from game.api.api import _load_engine_articles, _article_to_response

# 协议要求 ArticleResponse 只暴露这 4 个字段
EXPECTED_FIELDS = {"id", "title", "content", "target_value"}
# 这些字段带答案/结构信息，泄露给前端等于直接送答案
SENSITIVE_FIELDS = ["linespots", "informationPoints", "paragraphs", "author", "question"]


def test_article_response():
    print("=" * 60)
    print("🔍 测试 ArticleResponse 数据格式")
    print("=" * 60)

    # 加载文章引擎数据
    articles = _load_engine_articles()
    assert articles, "没有找到文章数据"
    print(f"\n✅ 成功加载 {len(articles)} 篇文章\n")

    # 测试第一篇文章
    article = articles[0]
    response = _article_to_response(article)

    print("📦 ArticleResponse 对象:")
    print(f"  - id: {response.id}")
    print(f"  - title: {response.title}")
    print(f"  - content长度: {len(response.content)} 字符")
    print(f"  - target_value: {response.target_value}")

    # 转换为 JSON 查看实际发送的格式
    response_json = response.model_dump()
    print("\n📤 实际发送的 JSON 格式:")
    print(json.dumps(response_json, ensure_ascii=False, indent=2))

    # 🔒 安全检查
    print("\n" + "=" * 60)
    print("🔒 安全检查: 验证敏感数据是否被剔除")
    print("=" * 60)

    for field in SENSITIVE_FIELDS:
        assert field not in response_json, f"[危险] 发现敏感字段: {field}"
        print(f"✅ [安全] 已剔除: {field}")

    # 验证内容中的换行符
    newline_count = response.content.count('\n')
    print("\n📝 内容验证:")
    print(f"  - 包含换行符数量: {newline_count}")
    print(f"  - 换行符保留状态: {'✅ 已正确保留 \\n' if newline_count > 0 else '⚠️ 无换行符'}")

    # 统计返回的字段数
    print("\n📊 统计:")
    print(f"  - 返回字段数量: {len(response_json)} (预期: {len(EXPECTED_FIELDS)})")
    print(f"  - 字段列表: {list(response_json.keys())}")

    assert set(response_json) == EXPECTED_FIELDS, (
        f"字段与协议不符: 多出 {sorted(set(response_json) - EXPECTED_FIELDS)}, "
        f"缺少 {sorted(EXPECTED_FIELDS - set(response_json))}"
    )

    print("\n" + "=" * 60)
    print("🎉 测试通过! ArticleResponse 格式完全符合协议要求")
    print("=" * 60)


if __name__ == "__main__":
    # 设置标准输出编码为 UTF-8（仅限直接运行，见文件头说明）
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    test_article_response()
