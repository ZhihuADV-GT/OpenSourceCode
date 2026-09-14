"""批量生成 AI 文章脚本

遍历 llm_prompt.SEARCH_KEYWORDS_POOL 关键词池，逐个调用管道生成文章。

已整合至 game.preprocess 子包，不再需要 subprocess 调用外部脚本。

使用方式：
    cd Backend
    python -m game.preprocess.batch_generate
"""

from __future__ import annotations

import time

from game.api.llm_prompt import SEARCH_KEYWORDS_POOL
from game.preprocess.zhihu_pipeline import run_pipeline


def main():
    """批量遍历关键词池，逐篇调用预处理管道"""
    keywords = SEARCH_KEYWORDS_POOL

    print("=" * 60)
    print("📦 批量生成AI文章")
    print(f"   关键词数量: {len(keywords)}")
    print("=" * 60)

    success_count = 0
    fail_count = 0

    for i, keyword in enumerate(keywords, 1):
        print(f"\n{'─' * 60}")
        print(f"📝 [{i}/{len(keywords)}] 关键词: {keyword}")
        print(f"{'─' * 60}")

        try:
            success = run_pipeline(keyword=keyword, count=3)
            if success:
                print(f"✅ [{keyword}] 生成成功")
                success_count += 1
            else:
                print(f"⚠️ [{keyword}] 管道返回失败")
                fail_count += 1

        except Exception as e:
            print(f"💥 [{keyword}] 异常: {e}")
            fail_count += 1

        # 每次生成后等待几秒，避免 API 限流
        if i < len(keywords):
            time.sleep(3)

    print(f"\n{'=' * 60}")
    print(f"📊 批量生成完成: 成功 {success_count}, 失败 {fail_count}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
