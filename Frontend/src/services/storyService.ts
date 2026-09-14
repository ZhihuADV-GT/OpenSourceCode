import { http } from './http'
import type { QuadrantType } from '../types/mapTypes'

/**
 * 局间 ADV 剧情：AI 实时生成（POST /api/ai/story）
 *
 * 后端全程无状态：不落盘、不读 session、不做缓存，只把生成结果回传前端。
 * 生成失败（generated=false / 超时 / 网络异常）时返回 null，
 * 由 stores/game.ts 降级到 game/story/scripts/fallbackStories.ts 的本地 A 版剧本。
 */

/** 剧情生成上下文（字段与后端 StoryRequest 对齐） */
export interface StoryContext {
  /** 刚结束的局号（1-5） */
  round: number
  /** 看山当前所在象限 */
  quadrant: QuadrantType
  /** 本局结算是否通过 */
  passed: boolean
  /** 结算评价文本 */
  rating: string
  /** 本局向量热度 */
  heat: number
  /** 本局向量盐度 */
  salt: number
  /** 四类卡牌计数 */
  cards: Record<string, number>
  /** 最近移动方向 */
  history: string[]
}

/** 单句 ADV 对话（字段与前端 DialogueLine 一致） */
export interface AIStoryLine {
  speaker: string
  speakerName: string
  text: string
}

/** 后端 /api/ai/story 响应 */
export interface AIStoryResult {
  generated: boolean
  id: string
  title: string
  lines: AIStoryLine[]
  source?: 'ai'
  debug?: Record<string, unknown>
}

/** AI 剧情生成超时（毫秒）；覆盖 http.ts 默认的 5 秒，生成 5-8 句需要更久 */
const STORY_REQUEST_TIMEOUT = 20000

/**
 * 请求一段 AI 生成的剧情
 *
 * @returns 生成结果；失败时返回 null（调用方负责降级）
 */
export async function fetchAIStory(context: StoryContext): Promise<AIStoryResult | null> {
  const startedAt = performance.now()
  try {
    console.log(
      `🎬 [fetchAIStory] 请求 AI 剧情：第${context.round}局 quadrant=${context.quadrant} ` +
      `rating=${context.rating || '无'} vector=(${context.heat.toFixed(2)}, ${context.salt.toFixed(2)})`,
    )
    const response = await http.post<AIStoryResult>('/ai/story', context, {
      timeout: STORY_REQUEST_TIMEOUT,
    })
    const data = response.data
    const elapsedMs = Math.round(performance.now() - startedAt)

    if (!data || data.generated !== true || !Array.isArray(data.lines) || data.lines.length === 0) {
      console.warn(`⚠️ [fetchAIStory] 后端未生成剧情，耗时 ${elapsedMs}ms，降级到本地预设剧本`, data?.debug)
      return null
    }

    console.log(
      `✅ [fetchAIStory] AI 剧情生成成功: ${data.id} - ${data.title}` +
      `（${data.lines.length} 句，${elapsedMs}ms）`,
      data.debug,
    )
    return { ...data, source: 'ai', debug: { ...data.debug, clientElapsedMs: elapsedMs } }
  } catch (error) {
    console.error('❌ [fetchAIStory] AI 剧情生成失败:', error)
    console.warn('💡 备用方案：使用本地预设剧情')
    return null
  }
}
