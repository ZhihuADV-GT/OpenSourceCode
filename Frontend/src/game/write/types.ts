/** Write 模块 —— 类型定义 */

import type { QuadrantType } from '../../types/mapTypes'

export interface CardCountSummary {
  rhetoric: number
  emotion: number
  viewpoint: number
  loophole: number
}

export interface MaterialPreference {
  kind: 'single' | 'tie' | 'none'
  labels: string[]
}

export interface UnlockedAchievementSummary {
  name: string
  description: string
}

export interface JourneyRoundSummary {
  round: number
  vector: [number, number]
  toRow: number
  toCol: number
}

/** 六局完成后的唯一随笔上下文。 */
export interface FinalJourneySummary {
  runId: string
  roundsCompleted: number
  collected: CardCountSummary
  used: CardCountSummary
  kanshanInteractions: number
  heatQualifiedRounds: number[]
  saltQualifiedRounds: number[]
  unlockedAchievements: UnlockedAchievementSummary[]
  achievementTotal: number
  finalRegion: string
  finalPosition: { row: number; col: number }
  finalHeat: number
  finalSalt: number
  preferredMaterial: MaterialPreference
  roundHistory: JourneyRoundSummary[]
}

/** 最终随笔生成请求。 */
export interface WriteEssayRequest {
  summary: FinalJourneySummary
}

/** 随笔生成结果 */
export interface WriteEssayResult {
  /** 随笔标题 */
  title: string
  /** 随笔正文 */
  content: string
  /** 是否由真 AI 生成（false = 降级保底） */
  isAIGenerated: boolean
  /** 生成完成时间；仅成功生成的结果会持久化。 */
  generatedAt?: number
}

/** 随笔模板（降级用） */
export interface EssayTemplate {
  quadrant: QuadrantType
  title: string
  content: string
}
