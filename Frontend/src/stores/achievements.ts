import { defineStore } from 'pinia'
import {
  ACHIEVEMENT_DEFINITIONS,
  ACHIEVEMENT_IDS,
  ACHIEVEMENT_PRODUCT_VALUES,
} from '../data/achievementDefinitions'
import type { AchievementDefinition, AchievementState, AchievementStats } from '../types/achievement'
import type { Material } from '../types/material'

const STORAGE_KEY = 'game-achievements-v2'
const LEGACY_STORAGE_KEY = 'game-achievements-v1'
const CARD_TYPES = {
  RHETORIC: '修辞卡',
  EMOTION: '情绪卡',
  VIEWPOINT: '观点卡',
  LOOPHOLE: '漏洞卡',
} as const

interface PersistedAchievements {
  schemaVersion: 2
  stats: AchievementStats
  states: Record<string, AchievementState>
  countedMaterialIds: string[]
  usedMaterialInstanceIds: string[]
  countedKanshanInteractionIds: string[]
  migrated: boolean
}

function defaultStats(): AchievementStats {
  return {
    rhetoricCollectedTotal: 0,
    emotionCollectedTotal: 0,
    viewpointCollectedTotal: 0,
    loopholeCollectedTotal: 0,
    rhetoricUsedTotal: 0,
    emotionUsedTotal: 0,
    viewpointUsedTotal: 0,
    loopholeUsedTotal: 0,
    kanshanInteractionTotal: 0,
    completedRounds: 0,
    completedRoundNumbers: [],
    heatQualifiedRoundNumbers: [],
    saltQualifiedRoundNumbers: [],
    latestCompletedHeat: null,
    latestCompletedSalt: null,
    maxCompletedHeat: null,
    maxCompletedSalt: null,
  }
}

function defaultStates(): Record<string, AchievementState> {
  return Object.fromEntries(ACHIEVEMENT_DEFINITIONS.map(definition => [
    definition.id,
    {
      id: definition.id,
      status: definition.hidden ? 'HIDDEN' : 'LOCKED',
      progress: null,
      target: definition.target,
      unlockedAt: null,
      seen: false,
    },
  ]))
}

function finiteOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function nonNegativeInteger(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : fallback
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? [...new Set(value.filter((item): item is string => typeof item === 'string' && item.length > 0))]
    : []
}

function positiveRoundNumbers(value: unknown): number[] {
  return Array.isArray(value)
    ? [...new Set(value.filter(
        (round): round is number => typeof round === 'number' && Number.isInteger(round) && round > 0,
      ))].sort((a, b) => a - b)
    : []
}

function normalizeStats(rawStats: Partial<AchievementStats>): AchievementStats {
  const roundNumbers = positiveRoundNumbers(rawStats.completedRoundNumbers)
  const heatQualifiedRoundNumbers = positiveRoundNumbers(rawStats.heatQualifiedRoundNumbers)
    .filter(round => roundNumbers.includes(round))
  const saltQualifiedRoundNumbers = positiveRoundNumbers(rawStats.saltQualifiedRoundNumbers)
    .filter(round => roundNumbers.includes(round))

  return {
    rhetoricCollectedTotal: nonNegativeInteger(rawStats.rhetoricCollectedTotal, 0),
    emotionCollectedTotal: nonNegativeInteger(rawStats.emotionCollectedTotal, 0),
    viewpointCollectedTotal: nonNegativeInteger(rawStats.viewpointCollectedTotal, 0),
    loopholeCollectedTotal: nonNegativeInteger(rawStats.loopholeCollectedTotal, 0),
    rhetoricUsedTotal: nonNegativeInteger(rawStats.rhetoricUsedTotal, 0),
    emotionUsedTotal: nonNegativeInteger(rawStats.emotionUsedTotal, 0),
    viewpointUsedTotal: nonNegativeInteger(rawStats.viewpointUsedTotal, 0),
    loopholeUsedTotal: nonNegativeInteger(rawStats.loopholeUsedTotal, 0),
    kanshanInteractionTotal: nonNegativeInteger(rawStats.kanshanInteractionTotal, 0),
    completedRounds: roundNumbers.length,
    completedRoundNumbers: roundNumbers,
    heatQualifiedRoundNumbers,
    saltQualifiedRoundNumbers,
    latestCompletedHeat: finiteOrNull(rawStats.latestCompletedHeat),
    latestCompletedSalt: finiteOrNull(rawStats.latestCompletedSalt),
    maxCompletedHeat: finiteOrNull(rawStats.maxCompletedHeat),
    maxCompletedSalt: finiteOrNull(rawStats.maxCompletedSalt),
  }
}

function normalizeStates(value: unknown): Record<string, AchievementState> {
  const savedStates = typeof value === 'object' && value !== null
    ? value as Record<string, Partial<AchievementState>>
    : {}
  const states = defaultStates()

  for (const definition of ACHIEVEMENT_DEFINITIONS) {
    const saved = savedStates[definition.id]
    if (!saved) continue
    const defaultState = states[definition.id]
    const savedStatus = saved.status
    const status = savedStatus === 'UNLOCKED' || savedStatus === 'IN_PROGRESS' || savedStatus === 'LOCKED'
      ? savedStatus
      : defaultState.status
    states[definition.id] = {
      id: definition.id,
      status: definition.hidden ? 'HIDDEN' : status,
      progress: finiteOrNull(saved.progress),
      target: definition.target,
      unlockedAt: finiteOrNull(saved.unlockedAt),
      seen: saved.seen === true,
    }
  }

  return states
}

function evaluateStateMap(
  stats: AchievementStats,
  currentStates: Record<string, AchievementState>,
  markHistoricalUnlocksSeen = false,
) {
  const states = { ...currentStates }
  const newlyUnlocked: string[] = []

  for (const definition of ACHIEVEMENT_DEFINITIONS) {
    const currentState = states[definition.id] ?? defaultStates()[definition.id]
    const wasUnlocked = currentState.status === 'UNLOCKED'
    const progress = progressFor(definition, stats)

    if (definition.hidden) {
      states[definition.id] = {
        ...currentState,
        status: 'HIDDEN',
        progress: null,
        target: definition.target,
      }
      continue
    }

    const prerequisitesMet = definition.prerequisites.every(id => (
      states[id]?.status === 'UNLOCKED'
    ))
    const targetMet = targetMetFor(definition, stats, progress)

    if (prerequisitesMet && targetMet) {
      // 前置条件满足 + 目标达成 → 解锁
      states[definition.id] = {
        ...currentState,
        status: 'UNLOCKED',
        progress,
        target: definition.target,
        unlockedAt: currentState.unlockedAt ?? Date.now(),
        seen: markHistoricalUnlocksSeen
          ? true
          : currentState.unlockedAt === null ? false : currentState.seen,
      }
      if (!wasUnlocked) newlyUnlocked.push(definition.id)
    } else if (prerequisitesMet) {
      // 前置条件满足但目标未达成 → 显示进度
      states[definition.id] = {
        ...currentState,
        status: 'IN_PROGRESS',
        progress,
        target: definition.target,
      }
    } else {
      // 前置条件未满足 → 锁定（但仍记录进度）
      states[definition.id] = {
        ...currentState,
        status: 'LOCKED',
        progress,  // ← 关键修复：即使锁定也记录进度
        target: definition.target,
      }
    }
  }

  return { states, newlyUnlocked }
}

function loadPersistedAchievements(): PersistedAchievements {
  const fallback: PersistedAchievements = {
    schemaVersion: 2,
    stats: defaultStats(),
    states: defaultStates(),
    countedMaterialIds: [],
    usedMaterialInstanceIds: [],
    countedKanshanInteractionIds: [],
    migrated: false,
  }

  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const legacyRaw = raw ? null : localStorage.getItem(LEGACY_STORAGE_KEY)
    if (!raw && !legacyRaw) return fallback
    const parsed: unknown = JSON.parse(raw ?? legacyRaw!)
    if (typeof parsed !== 'object' || parsed === null) return fallback

    const record = parsed as Partial<PersistedAchievements>
    const rawStats = typeof record.stats === 'object' && record.stats !== null
      ? record.stats as Partial<AchievementStats>
      : {}
    const stats = normalizeStats(rawStats)
    const states = normalizeStates(record.states)
    const migrated = !raw
    const evaluated = migrated
      ? evaluateStateMap(stats, states, true).states
      : states
    return {
      schemaVersion: 2,
      stats,
      states: evaluated,
      countedMaterialIds: stringList(record.countedMaterialIds),
      usedMaterialInstanceIds: stringList(record.usedMaterialInstanceIds),
      countedKanshanInteractionIds: stringList(record.countedKanshanInteractionIds),
      migrated,
    }
  } catch {
    return fallback
  }
}

function persistAchievements(value: PersistedAchievements) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
  } catch {
    // Keep the in-memory achievement state usable if browser storage is unavailable.
  }

  if (import.meta.env.DEV) {
    document.documentElement.setAttribute('data-achievement-stats', JSON.stringify(value.stats))
    document.documentElement.setAttribute('data-achievement-states', JSON.stringify(value.states))
  }
}

function progressFor(definition: AchievementDefinition, stats: AchievementStats): number | null {
  switch (definition.progressType) {
    case 'completed_rounds': return stats.completedRounds
    case 'rhetoric_used': return stats.rhetoricUsedTotal
    case 'emotion_used': return stats.emotionUsedTotal
    case 'viewpoint_used': return stats.viewpointUsedTotal
    case 'loophole_used': return stats.loopholeUsedTotal
    case 'completed_heat_threshold': return stats.latestCompletedHeat
    case 'completed_salt_threshold': return stats.latestCompletedSalt
    case 'qualified_heat_rounds': return stats.heatQualifiedRoundNumbers.length
    case 'qualified_salt_rounds': return stats.saltQualifiedRoundNumbers.length
    case 'product_value': return null
  }
}

function targetMetFor(definition: AchievementDefinition, stats: AchievementStats, progress: number | null) {
  switch (definition.id) {
    case ACHIEVEMENT_IDS.HEAT_BASIC:
      return stats.heatQualifiedRoundNumbers.length > 0
    case ACHIEVEMENT_IDS.SALT_BASIC:
      return stats.saltQualifiedRoundNumbers.length > 0
    default:
      return definition.target !== null
        && progress !== null
        && progress >= definition.target
  }
}

export const useAchievementStore = defineStore('achievements', {
  state: () => {
    const persisted = loadPersistedAchievements()
    const state = {
      stats: persisted.stats,
      states: persisted.states,
      countedMaterialIds: persisted.countedMaterialIds,
      usedMaterialInstanceIds: persisted.usedMaterialInstanceIds,
      countedKanshanInteractionIds: persisted.countedKanshanInteractionIds,
      unlockQueue: [] as string[],
    }
    if (persisted.migrated) {
      persistAchievements({
        schemaVersion: 2,
        stats: state.stats,
        states: state.states,
        countedMaterialIds: state.countedMaterialIds,
        usedMaterialInstanceIds: state.usedMaterialInstanceIds,
        countedKanshanInteractionIds: state.countedKanshanInteractionIds,
        migrated: false,
      })
    }
    return state
  },
  getters: {
    definitions: () => ACHIEVEMENT_DEFINITIONS,
    achievementStates: state => ACHIEVEMENT_DEFINITIONS.map(definition => state.states[definition.id]),
    unlockedAchievements: state => ACHIEVEMENT_DEFINITIONS
      .filter(definition => state.states[definition.id]?.status === 'UNLOCKED'),
    unseenAchievements: state => ACHIEVEMENT_DEFINITIONS
      .filter(definition => {
        const achievementState = state.states[definition.id]
        return achievementState?.status === 'UNLOCKED' && !achievementState.seen
      }),
    hasUnseenUnlocks: state => Object.values(state.states).some(achievementState => (
      achievementState.status === 'UNLOCKED' && !achievementState.seen
    )),
    getAchievementState: state => (id: string) => state.states[id],
    heatQualifiedRounds: state => state.stats.heatQualifiedRoundNumbers.length,
    saltQualifiedRounds: state => state.stats.saltQualifiedRoundNumbers.length,
  },
  actions: {
    persist() {
      persistAchievements({
        schemaVersion: 2,
        stats: this.stats,
        states: this.states,
        countedMaterialIds: this.countedMaterialIds,
        usedMaterialInstanceIds: this.usedMaterialInstanceIds,
        countedKanshanInteractionIds: this.countedKanshanInteractionIds,
        migrated: false,
      })
    },
    evaluateAchievements() {
      const evaluated = evaluateStateMap(this.stats, this.states)
      this.states = evaluated.states
      this.persist()
      const newlyUnlocked = evaluated.newlyUnlocked
      this.unlockQueue.push(...newlyUnlocked)
      return newlyUnlocked
    },
    recordSuccessfulCollection(material: Material) {
      if (this.countedMaterialIds.includes(material.id)) return [] as string[]

      this.countedMaterialIds.push(material.id)
      switch (material.type) {
        case CARD_TYPES.RHETORIC: this.stats.rhetoricCollectedTotal += 1; break
        case CARD_TYPES.EMOTION: this.stats.emotionCollectedTotal += 1; break
        case CARD_TYPES.VIEWPOINT: this.stats.viewpointCollectedTotal += 1; break
        case CARD_TYPES.LOOPHOLE: this.stats.loopholeCollectedTotal += 1; break
        default: break
      }
      return this.evaluateAchievements()
    },
    recordCommittedMaterialUsage(materials: readonly Material[]) {
      let changed = false

      // 【调试】记录卡牌使用情况
      if (import.meta.env.DEV && materials.length > 0) {
        console.log('[成就系统] 开始记录卡牌使用:', materials.length, '张卡牌')
        materials.forEach(m => {
          console.log('  -', m.id, '| type:', m.type, '| infoId:', m.informationPointId)
        })
      }

      for (const material of materials) {
        if (!material.id || this.usedMaterialInstanceIds.includes(material.id)) {
          if (import.meta.env.DEV) {
            console.log('[成就系统] 跳过已计数的卡牌:', material.id)
          }
          continue
        }

        this.usedMaterialInstanceIds.push(material.id)
        switch (material.type) {
          case CARD_TYPES.RHETORIC: 
            this.stats.rhetoricUsedTotal += 1
            if (import.meta.env.DEV) {
              console.log('[成就系统] ✅ 修辞卡 +1, 当前:', this.stats.rhetoricUsedTotal)
            }
            break
          case CARD_TYPES.EMOTION: 
            this.stats.emotionUsedTotal += 1
            if (import.meta.env.DEV) {
              console.log('[成就系统] ✅ 情绪卡 +1, 当前:', this.stats.emotionUsedTotal)
            }
            break
          case CARD_TYPES.VIEWPOINT: 
            this.stats.viewpointUsedTotal += 1
            if (import.meta.env.DEV) {
              console.log('[成就系统] ✅ 观点卡 +1, 当前:', this.stats.viewpointUsedTotal)
            }
            break
          case CARD_TYPES.LOOPHOLE: 
            this.stats.loopholeUsedTotal += 1
            if (import.meta.env.DEV) {
              console.log('[成就系统] ✅ 漏洞卡 +1, 当前:', this.stats.loopholeUsedTotal)
            }
            break
          default:
            if (import.meta.env.DEV) {
              console.warn('[成就系统] ⚠️ 未知卡牌类型:', material.type, '(ID:', material.id, ')')
            }
            break
        }
        changed = true
      }

      if (changed && import.meta.env.DEV) {
        console.log('[成就系统] 统计更新:', {
          viewpoint: this.stats.viewpointUsedTotal,
          emotion: this.stats.emotionUsedTotal,
          loophole: this.stats.loopholeUsedTotal,
          rhetoric: this.stats.rhetoricUsedTotal,
        })
      }

      return changed ? this.evaluateAchievements() : [] as string[]
    },
    recordKanshanInteraction(interactionId: string) {
      if (!interactionId || this.countedKanshanInteractionIds.includes(interactionId)) {
        return [] as string[]
      }

      this.countedKanshanInteractionIds.push(interactionId)
      this.stats.kanshanInteractionTotal += 1
      return this.evaluateAchievements()
    },
    recordRoundCompleted(round: number, vector: [number, number]) {
      if (!Number.isInteger(round) || round <= 0 || this.stats.completedRoundNumbers.includes(round)) {
        return [] as string[]
      }

      const [heat, salt] = vector
      this.stats.completedRoundNumbers = [...this.stats.completedRoundNumbers, round].sort((a, b) => a - b)
      this.stats.completedRounds = this.stats.completedRoundNumbers.length
      if (Number.isFinite(heat) && heat >= ACHIEVEMENT_PRODUCT_VALUES.HEAT_BASIC_THRESHOLD
        && !this.stats.heatQualifiedRoundNumbers.includes(round)) {
        this.stats.heatQualifiedRoundNumbers = [...this.stats.heatQualifiedRoundNumbers, round].sort((a, b) => a - b)
      }
      if (Number.isFinite(salt) && salt >= ACHIEVEMENT_PRODUCT_VALUES.SALT_BASIC_THRESHOLD
        && !this.stats.saltQualifiedRoundNumbers.includes(round)) {
        this.stats.saltQualifiedRoundNumbers = [...this.stats.saltQualifiedRoundNumbers, round].sort((a, b) => a - b)
      }
      this.stats.latestCompletedHeat = Number.isFinite(heat) ? heat : null
      this.stats.latestCompletedSalt = Number.isFinite(salt) ? salt : null
      this.stats.maxCompletedHeat = this.stats.maxCompletedHeat === null || !Number.isFinite(heat)
        ? this.stats.maxCompletedHeat ?? (Number.isFinite(heat) ? heat : null)
        : Math.max(this.stats.maxCompletedHeat, heat)
      this.stats.maxCompletedSalt = this.stats.maxCompletedSalt === null || !Number.isFinite(salt)
        ? this.stats.maxCompletedSalt ?? (Number.isFinite(salt) ? salt : null)
        : Math.max(this.stats.maxCompletedSalt, salt)
      return this.evaluateAchievements()
    },
    markAchievementSeen(id: string) {
      const achievementState = this.states[id]
      if (!achievementState || achievementState.status !== 'UNLOCKED' || achievementState.seen) return false
      achievementState.seen = true
      this.persist()
      return true
    },
    markAllAchievementsSeen() {
      let markedCount = 0
      for (const achievementState of Object.values(this.states) as AchievementState[]) {
        if (achievementState.status === 'UNLOCKED' && !achievementState.seen) {
          achievementState.seen = true
          markedCount += 1
        }
      }
      if (markedCount > 0) this.persist()
      return markedCount
    },
    dequeueUnlock(id: string) {
      if (this.unlockQueue[0] !== id) return false
      this.unlockQueue.shift()
      return true
    },
    resetAchievements() {
      this.stats = defaultStats()
      this.states = defaultStates()
      this.countedMaterialIds = []
      this.usedMaterialInstanceIds = []
      this.countedKanshanInteractionIds = []
      this.unlockQueue = []
      this.persist()
    },
  },
})
