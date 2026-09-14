"""文章预处理管道

从知乎搜索文章 → 清洗 → AI 标注 → 入库 article_lib/。
原模块已整合至此，不再需要跨目录 sys.path hack。

入口函数
--------
- ``run_pipeline(keyword, count)`` —— 单次管道（供 api.py 在线调用）
- ``main()``                       —— CLI 入口
- ``batch_generate.main()``        —— 批量生成（遍历关键词池）
"""
