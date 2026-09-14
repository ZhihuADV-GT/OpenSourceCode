/**
 * 每局文章生成通信服务：协议链路7（POST /api/articles/generate）
 *
 * 创作台合成完成后，前端携带卡槽快照调用此服务，
 * 后端根据矩阵位置 + 结构 + 卡牌数据生成一篇结构化文章。
 *
 * 后端 AI 调用失败时会自动降级为卡牌原文拼接，不会返回错误。
 */
import { http } from './http'
import type { ArticleGenerateRequest, ArticleGenerateResponse } from '../types/articleGenerate'

/**
 * 文章生成超时（毫秒）：覆盖 http.ts 默认的 5 秒。
 * 后端需逐段调用 AI 生成整篇文章，耗时远高于普通请求，5 秒必然超时。
 */
const ARTICLE_GENERATE_TIMEOUT = 60000

/**
 * 请求后端生成每局文章
 *
 * @param slots  工作台卡槽快照，格式同配卡运算 `[[slotId, cardId], ...]`
 * @param useAi  是否调用 AI 逐段生成（默认 true）
 * @returns 生成的文章（含标题/正文/段落/结构/蓝图）
 */
export async function generateRoundArticle(
  slots: [string, string][],
  useAi = true,
): Promise<ArticleGenerateResponse> {
  const request: ArticleGenerateRequest = { slots, use_ai: useAi }
  const response = await http.post<ArticleGenerateResponse>('/articles/generate', request, {
    timeout: ARTICLE_GENERATE_TIMEOUT,
  })
  return response.data
}
