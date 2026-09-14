// [art-assets disabled]
const achievementIcon = ''
const firstPathInactive = ''
const firstPathActive = ''
const yellowVInactive = ''
const yellowVActive = ''
const rhetoricBasicInactive = ''
const rhetoricBasicActive = ''
const emotionBasicInactive = ''
const emotionBasicActive = ''
const viewpointBasicInactive = ''
const viewpointBasicActive = ''
const loopholeBasicInactive = ''
const loopholeBasicActive = ''
const rhetoricAdvancedInactive = ''
const rhetoricAdvancedActive = ''
const heatBasicInactive = ''
const heatBasicActive = ''
const saltBasicInactive = ''
const saltBasicActive = ''
const heatAdvancedInactive = ''
const heatAdvancedActive = ''
const saltAdvancedActive = ''
const saltAdvancedInactive = ''
import { ACHIEVEMENT_IDS } from './achievementDefinitions'
import type { AchievementStatus } from '../types/achievement'

interface AchievementIconPair {
  inactive: string
  active: string
}

const individualAchievementIcons: Partial<Record<string, AchievementIconPair>> = {
  [ACHIEVEMENT_IDS.FIRST_PATH]: {
    inactive: firstPathInactive,
    active: firstPathActive,
  },
  [ACHIEVEMENT_IDS.YELLOW_V]: {
    inactive: yellowVInactive,
    active: yellowVActive,
  },
  [ACHIEVEMENT_IDS.RHETORIC_BASIC]: {
    inactive: rhetoricBasicInactive,
    active: rhetoricBasicActive,
  },
  [ACHIEVEMENT_IDS.EMOTION_BASIC]: {
    inactive: emotionBasicInactive,
    active: emotionBasicActive,
  },
  [ACHIEVEMENT_IDS.VIEWPOINT_BASIC]: {
    inactive: viewpointBasicInactive,
    active: viewpointBasicActive,
  },
  [ACHIEVEMENT_IDS.LOOPHOLE_BASIC]: {
    inactive: loopholeBasicInactive,
    active: loopholeBasicActive,
  },
  [ACHIEVEMENT_IDS.RHETORIC_ADVANCED]: {
    inactive: rhetoricAdvancedInactive,
    active: rhetoricAdvancedActive,
  },
  [ACHIEVEMENT_IDS.HEAT_BASIC]: {
    inactive: heatBasicInactive,
    active: heatBasicActive,
  },
  [ACHIEVEMENT_IDS.SALT_BASIC]: {
    inactive: saltBasicInactive,
    active: saltBasicActive,
  },
  [ACHIEVEMENT_IDS.HEAT_ADVANCED]: {
    inactive: heatAdvancedInactive,
    active: heatAdvancedActive,
  },
  [ACHIEVEMENT_IDS.SALT_ADVANCED]: {
    inactive: saltAdvancedInactive,
    active: saltAdvancedActive,
  },
}

/** The Map entry artwork is reserved for the Map achievement button only. */
export const achievementSystemIcon = achievementIcon

export function achievementIconFor(id: string, status: AchievementStatus): string | null {
  if (status === 'HIDDEN') return null

  const pair = individualAchievementIcons[id]
  if (!pair) return null

  return status === 'UNLOCKED' ? pair.active : pair.inactive
}
