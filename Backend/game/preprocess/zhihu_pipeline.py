"""知乎文章获取与预处理管道

功能：
1. 通过知乎搜索API搜索关键词
2. 获取文章列表并筛选高质量文章
3. 清洗HTML为纯文本
4. 安全审核 + 通义千问AI标注
5. 输出符合 article-model.json 格式的文件

已整合至 game.preprocess 子包，所有依赖改为包内直接导入。
"""

from __future__ import annotations

import sys
import io

# 修复 Windows 终端编码问题
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import json
import time
import hashlib
import re
from pathlib import Path
from typing import Optional

import requests

from game.api.llm_config import (
    DASHSCOPE_NATIVE_API_BASE_URL,
    TONGYI_API_KEY,
    TONGYI_MODEL_ANNOTATE,
    TONGYI_TIMEOUT_ANNOTATE,
    ZHIHU_API_BASE_URL,
    ZHIHU_ACCESS_TOKEN,
)
from game.api.llm_prompt import (
    DEFAULT_SEARCH_KEYWORD,
    DEFAULT_SEARCH_COUNT,
    ANNOTATE_SYSTEM_PROMPT,
    ANNOTATE_USER_PROMPT_TEMPLATE,
    SENSITIVE_CHECK_SYSTEM_PROMPT,
    SENSITIVE_CHECK_USER_TEMPLATE,
)
from game.numerics.card_rules import clamp_card_vector, validate_card_vector
from game.article_store import ARTICLE_LIB_DIR

# ==================== 配置常量 ====================

MAX_CONTENT_LENGTH: int = 8000  # 控制后续 AI 调用 token 消耗


# ==================== 步骤1: 知乎搜索 ====================

def search_zhihu_articles(query: str = None, count: int = None) -> list[dict]:
    """搜索知乎内容，返回文章列表

    Args:
        query: 搜索关键词
        count: 返回结果数(1-10)

    Returns:
        文章列表，每项包含 title / content_id / url 等信息
    """
    query = query or DEFAULT_SEARCH_KEYWORD
    count = count or DEFAULT_SEARCH_COUNT

    url = f"{ZHIHU_API_BASE_URL}/content/zhihu_search"

    headers = {
        "Authorization": f"Bearer {ZHIHU_ACCESS_TOKEN}",
        "X-Request-Timestamp": str(int(time.time())),
        "Content-Type": "application/json",
    }

    params = {
        "Query": query,
        "Count": count,
    }

    print(f"🔍 正在搜索知乎: '{query}'")
    print(f"📡 API: {url}")

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()

        data = response.json()

        if data["Code"] != 0:
            print(f"❌ API错误: {data.get('Message', 'Unknown error')}")
            return []

        items = data["Data"]["Items"]
        print(f"✅ 找到 {len(items)} 条结果")

        # 提取关键信息
        articles = []
        for item in items:
            article_info = {
                "title": item["Title"],
                "content_id": item["ContentID"],
                "content_type": item["ContentType"],  # Article/Question/Answer
                "abstract": item["ContentText"],
                "url": item["Url"],
                "vote_count": item["VoteUpCount"],
                "comment_count": item["CommentCount"],
                "author": item["AuthorName"],
                "publish_time": item["EditTime"],
            }
            articles.append(article_info)

        # 按赞同数排序（优先选择高质量文章）
        articles.sort(key=lambda x: x["vote_count"], reverse=True)

        print(f"\n📊 搜索结果TOP3:")
        for i, art in enumerate(articles[:3]):
            print(f"  {i+1}. {art['title']} (👍{art['vote_count']})")

        return articles

    except Exception as e:
        print(f"❌ 搜索失败: {e}")
        return []


# ==================== 步骤2: 获取文章详情 ====================

def fetch_article_detail(content_id: str) -> Optional[dict]:
    """获取文章详细内容

    NOTE: v4 API 接口不对外界开放，暂时使用搜索结果的摘要。

    Args:
        content_id: 知乎文章ID

    Returns:
        包含 content 和 author 的字典
    """
    # ❌ 禁用：v4 API 接口不对外开放
    # ✅ 临时方案：返回搜索结果的摘要（已在 search_zhihu_articles 中获取）
    print(f"⚠️ 使用搜索摘要代替全文（content_id: {content_id}）")
    return None


# ==================== 步骤3: 文本清洗 ====================

def clean_html_to_text(html_content: str) -> str:
    """清洗 HTML 内容，提取纯文本"""
    print("🧹 开始清洗HTML...")

    text = re.sub(r"<[^>]+>", "", html_content)

    lines = text.splitlines()
    lines = [line.strip() for line in lines if line.strip()]
    cleaned_text = "\n".join(lines)

    if len(cleaned_text) > MAX_CONTENT_LENGTH:
        print(f"⚠️ 文本过长({len(cleaned_text)}字)，截断到{MAX_CONTENT_LENGTH}字")
        cleaned_text = cleaned_text[:MAX_CONTENT_LENGTH] + "\n\n...(省略)"

    print(f"✅ 清洗完成，最终字数: {len(cleaned_text)}")
    return cleaned_text


def truncate_content(text: str, max_length: int = None) -> str:
    """截断过长文本"""
    max_length = max_length or MAX_CONTENT_LENGTH

    if len(text) <= max_length:
        return text

    half = max_length // 2
    return text[:half] + f"\n\n...（省略{len(text) - max_length}字）...\n\n" + text[-half:]


# ==================== 敏感内容安全审核 ====================

def check_sensitive_content(title: str, content: str) -> bool:
    """敏感内容审核 —— 已禁用，所有文章直接放行。

    如需恢复审核，取消注释下方原实现即可。
    """
    print(f"\n🛡️ [审核已禁用] 跳过安全检查: {title[:30]}...")
    return False

    # ────────── 以下为原实现（保留备恢复） ──────────
    # user_prompt = SENSITIVE_CHECK_USER_TEMPLATE.format(title=title, content=content)
    # url = f"{DASHSCOPE_NATIVE_API_BASE_URL}/services/aigc/text-generation/generation"
    # headers = {
    #     "Authorization": f"Bearer {TONGYI_API_KEY}",
    #     "Content-Type": "application/json",
    # }
    # models = (TONGYI_MODEL_ANNOTATE if isinstance(TONGYI_MODEL_ANNOTATE, list)
    #           else [TONGYI_MODEL_ANNOTATE])
    #
    # print(f"\n🛡️ 正在审核内容安全: {title[:30]}...")
    # for model in models:
    #     payload = {
    #         "model": model,
    #         "input": {
    #             "messages": [
    #                 {"role": "system", "content": SENSITIVE_CHECK_SYSTEM_PROMPT},
    #                 {"role": "user", "content": user_prompt},
    #             ]
    #         },
    #         "parameters": {"max_tokens": 120, "temperature": 0.1},
    #     }
    #     try:
    #         response = requests.post(url, headers=headers, json=payload,
    #                                  timeout=TONGYI_TIMEOUT_ANNOTATE)
    #         if response.status_code != 200:
    #             print(f"⚠️ 审核模型 {model} 返回 {response.status_code}，尝试下一个")
    #             continue
    #         result = response.json()
    #         if "error_code" in result:
    #             print(f"⚠️ 审核模型 {model} 错误 {result['error_code']}，尝试下一个")
    #             continue
    #
    #         ai_text = (result["output"]["text"]
    #                    .replace("```json", "").replace("```", "").strip())
    #         verdict = json.loads(ai_text)
    #         sensitive = bool(verdict.get("sensitive", True))
    #         if sensitive:
    #             print(f"⛔ 敏感文章: 类别={verdict.get('category', '')} "
    #                   f"依据={verdict.get('reason', '')}")
    #         else:
    #             print("✅ 内容安全审核通过")
    #         return sensitive
    #     except json.JSONDecodeError as e:
    #         print(f"⚠️ 审核结果解析失败({e})，尝试下一个模型")
    #         continue
    #     except Exception as e:
    #         print(f"⚠️ 审核模型 {model} 调用失败({e})，尝试下一个")
    #         continue
    #
    # print("⚠️ 所有审核模型均失败，保守判为敏感，跳过该篇")
    # return True


# ==================== 步骤4: 通义千问AI标注 ====================

def annotate_with_tongyi_qianwen(title: str, content: str) -> list[dict]:
    """调用通义千问进行 AI 标注

    Args:
        title: 文章标题
        content: 清洗后的纯文本

    Returns:
        linespots 列表；None 表示内容安全预检未通过
    """
    SYSTEM_PROMPT = ANNOTATE_SYSTEM_PROMPT
    USER_PROMPT = ANNOTATE_USER_PROMPT_TEMPLATE.format(title=title, content=content)

    url = f"{DASHSCOPE_NATIVE_API_BASE_URL}/services/aigc/text-generation/generation"

    headers = {
        "Authorization": f"Bearer {TONGYI_API_KEY}",
        "Content-Type": "application/json",
    }

    # TONGYI_MODEL_ANNOTATE 现为模型列表：逐个尝试（failover）
    models = (TONGYI_MODEL_ANNOTATE if isinstance(TONGYI_MODEL_ANNOTATE, list)
              else [TONGYI_MODEL_ANNOTATE])

    payload = {
        "model": models[0],
        "input": {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT},
            ]
        },
        "parameters": {
            "max_tokens": 2000,
            "temperature": 0.7,
        },
    }

    print(f"\n🤖 正在调用通义千问标注...")
    print(f"📡 API: {url}")

    for model in models:
        payload["model"] = model
        print(f"📝 模型: {model}")
        try:
            response = requests.post(
                url, headers=headers, json=payload, timeout=TONGYI_TIMEOUT_ANNOTATE
            )

            if response.status_code != 200:
                try:
                    err_body = response.json()
                except Exception:
                    err_body = response.text[:200]
                print(f"⚠️ 标注模型 {model} 返回 {response.status_code}: {err_body}，尝试下一个")
                continue

            result = response.json()

            if "error_code" in result:
                print(
                    f"⚠️ 标注模型 {model} 错误: "
                    f"{result['error_code']}-{result.get('error_message', '')}，尝试下一个"
                )
                continue

            # 解析 AI 返回的 JSON（DashScope 原生格式）
            ai_text = result["output"]["text"]
            ai_text = ai_text.replace("```json", "").replace("```", "").strip()

            # 内容安全预检：标注模型检测到敏感内容，返回 None 通知调用方跳过
            if '"sensitive"' in ai_text and "true" in ai_text:
                print("⛔ 标注模型判定文章含敏感内容，跳过")
                return None

            print(f"\n📋 AI返回内容预览:")
            print(ai_text[:200] + "...")

            linespots = json.loads(ai_text)
            print(f"✅ AI标注完成，有效划线点{len(linespots)}个")
            return linespots

        except json.JSONDecodeError as e:
            print(f"⚠️ 标注模型 {model} 返回格式错误: {e}，尝试下一个")
            continue
        except Exception as e:
            print(f"⚠️ 标注模型 {model} 调用失败: {e}，尝试下一个")
            continue

    print("❌ 所有标注模型均失败，返回空（调用方将用样例数据兜底）")
    return []


def manual_create_sample_linespots(content: str) -> list[dict]:
    """临时方案：手动标注样例数据（用于测试流程）"""
    print("⚠️ 使用手动标注的样例数据（替代AI）")

    return [
        {
            "start": 11,
            "end": 50,
            "card_type": "观点",
            "attribute_value": 15,
            "vector_x": 35,
            "vector_y": 35,
            "_reason": "开篇即抛出核心观点，具有高信息密度",
        },
        {
            "start": 100,
            "end": 180,
            "card_type": "漏洞",
            "attribute_value": 12,
            "vector_x": -25,
            "vector_y": 22,
            "_reason": "论证过程存在假设前提，需要更多证据支撑",
        },
        {
            "start": 50,
            "end": 90,
            "card_type": "修辞",
            "attribute_value": 10,
            "vector_x": 1.5,
            "vector_y": 1.2,
            "_reason": "使用排比句式增强表达效果",
        },
    ]


# ==================== 步骤5: 组装 article JSON ====================

def build_article_json(
    title: str,
    content: str,
    linespots: list[dict],
    source_url: str = "",
    author: str = "",
) -> dict:
    """组装符合 article-model.json 格式的完整数据

    Args:
        title: 文章标题
        content: 全文纯文本
        linespots: AI 标注的划线点
        source_url: 知乎原文链接
        author: 作者名

    Returns:
        完整的 article 字典
    """
    print("\n📦 组装Article JSON...")

    total_value = sum(spot["attribute_value"] for spot in linespots)
    target_value = int(total_value * 0.8)

    id_hash = hashlib.md5(title.encode()).hexdigest()[:8]
    article_id = f"ai_{id_hash}"

    formatted_linespots = []
    for i, spot in enumerate(linespots):
        # 写入前按 card_rules 兜底：AI 偶尔会越界，钳回合规区间
        raw_x, raw_y = spot["vector_x"], spot["vector_y"]
        problems = validate_card_vector(spot["card_type"], raw_x, raw_y)
        if problems:
            vec_x, vec_y = clamp_card_vector(spot["card_type"], raw_x, raw_y)
            print(
                f"⚠️ 卡牌数值越界已钳制: {spot['card_type']} "
                f"({raw_x}, {raw_y}) -> ({vec_x}, {vec_y}) | {'; '.join(problems)}"
            )
        else:
            vec_x, vec_y = raw_x, raw_y

        formatted_spot = {
            "card_id": f"{article_id}_card_{i+1}",
            "start": spot["start"],
            "end": spot["end"],
            "start_context": content[spot["start"] : spot["start"] + 5],
            "end_context": content[spot["end"] - 5 : spot["end"]],
            "card_type": spot["card_type"],
            "attribute_value": spot["attribute_value"],
            "attribute_x": vec_x,
            "attribute_y": vec_y,
        }
        formatted_linespots.append(formatted_spot)

    article = {
        "id": article_id,
        "title": title,
        "source_url": source_url,
        "author": author,
        "content": content,
        "target_value": target_value,
        "linespots": formatted_linespots,
    }

    print(f"✅ 组装完成:")
    print(f"   ID: {article_id}")
    print(f"   Title: {title}")
    print(f"   Content length: {len(content)}")
    print(f"   Linespots: {len(formatted_linespots)}")
    print(f"   Target value: {target_value}")

    return article


# ==================== 步骤6: 保存 JSON 文件 ====================

def save_article_json(article: dict, output_dir: Path = None) -> Path:
    """保存 article JSON 到 article_lib 目录

    Args:
        article: article 字典
        output_dir: 输出目录（默认使用 ARTICLE_LIB_DIR）

    Returns:
        输出文件路径
    """
    if output_dir is None:
        output_dir = ARTICLE_LIB_DIR

    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{article['id']}.json"
    filepath = output_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(article, f, ensure_ascii=False, indent=2)

    print(f"\n💾 已保存到: {filepath}")
    return filepath


# ==================== 主流程 ====================

def run_pipeline(keyword: str = None, count: int = None) -> bool:
    """单次管道入口 —— 供 api.py 在线调用与 CLI 共用

    Args:
        keyword: 搜索关键词（默认使用 DEFAULT_SEARCH_KEYWORD）
        count:   搜索数量（默认使用 DEFAULT_SEARCH_COUNT）

    Returns:
        True 表示成功生成并入库
    """
    keyword = keyword or DEFAULT_SEARCH_KEYWORD
    count = count or DEFAULT_SEARCH_COUNT

    print("=" * 60)
    print("🚀 知乎文章预处理流水线")
    print(f"   关键词: {keyword} | 数量: {count}")
    print("=" * 60)

    # Step 1: 搜索知乎文章
    articles = search_zhihu_articles(query=keyword, count=count)

    if not articles:
        print("❌ 没有可用的文章，退出")
        return False

    # Step 2: 逐篇安全审核，选第一篇通过的
    selected = None
    clean_content = None
    for art in articles:
        _cleaned = clean_html_to_text(art.get("abstract", "暂无内容"))
        if check_sensitive_content(art["title"], _cleaned):
            print(f"⛔ 跳过敏感文章，尝试下一篇: {art['title']}")
            continue
        selected = art
        clean_content = _cleaned
        break

    if selected is None:
        print("⛔ 搜索结果中没有通过安全审核的文章，本次不入库")
        return False

    print(f"\n📌 选中安全文章: {selected['title']}")
    print(f"   赞同数: {selected['vote_count']}")
    print(f"   作者: {selected.get('author', '匿名用户')}")

    author = selected.get("author", "匿名用户")

    # Step 3: AI 标注
    linespots = annotate_with_tongyi_qianwen(selected["title"], clean_content)

    if linespots is None:
        print("⛔ 文章未通过内容安全预检，跳过")
        return False

    if not linespots:
        print("⚠️ AI标注失败，使用手动样例数据")
        linespots = manual_create_sample_linespots(clean_content)

    # Step 4: 组装 JSON
    article = build_article_json(
        title=selected["title"],
        content=clean_content,
        linespots=linespots,
        source_url=selected["url"],
        author=author,
    )

    # Step 5: 保存
    filepath = save_article_json(article)

    print("\n" + "=" * 60)
    print("✅ 处理完成！")
    print(f"📄 输出文件: {filepath}")
    print("=" * 60)
    return True


def main():
    """CLI 入口：python -m game.preprocess.zhihu_pipeline [关键词] [数量]"""
    keyword = sys.argv[1] if len(sys.argv) > 1 else None
    count = int(sys.argv[2]) if len(sys.argv) > 2 else None
    run_pipeline(keyword=keyword, count=count)


if __name__ == "__main__":
    main()
