import { http } from './http'
import type { HintResponse, HintRequest } from '../types/article'

/**
 * 获取文章阅读提示
 *
 * @param articleId - 文章 ID
 * @param mode - 模式：rule（规则引擎）| deep（AI 深度分析）
 * @returns 提示响应（含气泡文案 + 建议列表）
 */
export async function fetchArticleHint(
  articleId: string,
  mode: 'rule' | 'deep' = 'rule',
): Promise<HintResponse | null> {
  try {
    const request: HintRequest = {
      scene: 'article',
      article_id: articleId,
      mode,
    }
    const response = await http.post<HintResponse>('/ai/hint', request)
    return response.data
  } catch (error) {
    console.error('[hintService] 获取提示失败:', error)
    return null
  }
}
