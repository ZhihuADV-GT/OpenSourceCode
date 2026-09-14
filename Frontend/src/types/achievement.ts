export type AchievementStatus = 'LOCKED' | 'IN_PROGRESS' | 'UNLOCKED' | 'HIDDEN'

export type AchievementProgressType =
  | 'completed_rounds'
  | 'rhetoric_used'
  | 'emotion_used'
  | 'viewpoint_used'
  | 'loophole_used'
  | 'completed_heat_threshold'
  | 'completed_salt_threshold'
  | 'qualified_heat_rounds'
  | 'qualified_salt_rounds'
  | 'product_value'

export interface AchievementStats {
  rhetoricCollectedTotal: number
  emotionCollectedTotal: number
  viewpointCollectedTotal: number
  loopholeCollectedTotal: number
  rhetoricUsedTotal: number
  emotionUsedTotal: number
  viewpointUsedTotal: number
  loopholeUsedTotal: number
  kanshanInteractionTotal: number
  completedRounds: number
  completedRoundNumbers: number[]
  heatQualifiedRoundNumbers: number[]
  saltQualifiedRoundNumbers: number[]
  latestCompletedHeat: number | null
  latestCompletedSalt: number | null
  maxCompletedHeat: number | null
  maxCompletedSalt: number | null
}

export interface AchievementDefinition {
  id: string
  name: string
  description: string
  prerequisites: string[]
  progressType: AchievementProgressType
  target: number | null
  productValue?: 'NEEDS_PRODUCT_VALUE'
  hidden?: boolean
}

export interface AchievementState {
  id: string
  status: AchievementStatus
  progress: number | null
  target: number | null
  unlockedAt: number | null
  seen: boolean
}
