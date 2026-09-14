import { http } from './http'
import type { Article, ArticleResponse } from '../types/article'

/**
 * 游戏初始化：协议链路1（GET /api/articles）
 *
 * 【安全要点】前端不再从本地 mock 加载 linespots，
 * 文章数据一律来自后端（后端已剔除 linespots / attribute_x / attribute_y）。
 */
function toArticle(data: ArticleResponse): Article {
  return {
    id: data.id,
    title: data.title,
    content: data.content,
    canonicalContent: data.content,
    // 后端 linespot 偏移基于全文连续序列，保持单段落渲染以保证前端偏移与后端一致
    paragraphs: [data.content],
    informationPoints: [], // 协议要求：前端不得持有 linespots
    targetValue: data.target_value ?? undefined,
  }
}

/** 获取全部文章列表 */
export async function fetchArticles(): Promise<Article[]> {
  const response = await http.get<ArticleResponse[]>('/articles')
  return response.data.map(toArticle)
}

/** 按 ID 获取单篇文章（协议可选 articleId 查询参数） */
export async function fetchArticleById(articleId: string): Promise<Article> {
  const response = await http.get<ArticleResponse>('/articles', {
    params: { articleId },
  })
  return toArticle(response.data)
}

/**
 * 获取AI生成的文章列表
 * 
 * AI生成的文章ID格式为 "ai_{hash}"，存储在后端 article_lib 目录
 */
export async function fetchAIArticles(): Promise<Article[]> {
  const response = await http.get<ArticleResponse[]>('/articles')
  // 过滤出AI生成的文章（ID以 'ai_' 开头）
  return response.data
    .filter(data => data.id.startsWith('ai_'))
    .map(toArticle)
}

/**
 * 随机获取一篇文章（优先AI文章，AI文章全部读完后降级到本地文章）
 * 
 * @param excludeIds - 已读文章ID列表，后端会排除这些文章
 * 调用后端 /api/articles/random?category=ai&exclude=id1,id2
 * 
 * 后端 fallback 策略：
 * 1. 从未读AI文章中随机选择
 * 2. AI文章全部读完且总数<100 → 自动调用后端生成新文章
 * 3. AI文章达100篇上限或生成失败 → 降级到本地手动文章
 */
export async function fetchRandomAIArticle(excludeIds?: string[]): Promise<Article | null> {
  try {
    const params: Record<string, string> = { category: 'ai' }
    if (excludeIds && excludeIds.length > 0) {
      params.exclude = excludeIds.join(',')
    }
    const response = await http.get<ArticleResponse>('/articles/random', { params })
    const article = toArticle(response.data)
    console.log(`✅ [fetchRandomAIArticle] 成功获取: ${article.id} - ${article.title}`)
    return article
  } catch (error) {
    console.error('❌ [fetchRandomAIArticle] 获取失败:', error)
    console.warn('💡 备用方案：使用默认文章')
    return null
  }
}
