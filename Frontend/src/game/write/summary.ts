import type { AchievementDefinition, AchievementState, AchievementStats } from '../../types/achievement'
import type {
  CardCountSummary,
  FinalJourneySummary,
  JourneyRoundSummary,
  MaterialPreference,
  UnlockedAchievementSummary,
} from './types'

export interface FinalJourneySummaryInput {
  stats: AchievementStats
  definitions: readonly AchievementDefinition[]
  states: readonly AchievementState[]
  finalRegion: string
  finalPosition: { row: number; col: number }
  finalHeat: number
  finalSalt: number
  roundHistory: readonly JourneyRoundSummary[]
}

const MATERIAL_LABELS: Array<keyof CardCountSummary> = ['rhetoric', 'emotion', 'viewpoint', 'loophole']
const MATERIAL_NAMES: Record<keyof CardCountSummary, string> = {
  rhetoric: '修辞卡',
  emotion: '情绪卡',
  viewpoint: '观点卡',
  loophole: '漏洞卡',
}

function cardCounts(stats: AchievementStats, suffix: 'CollectedTotal' | 'UsedTotal'): CardCountSummary {
  return {
    rhetoric: stats[`rhetoric${suffix}`],
    emotion: stats[`emotion${suffix}`],
    viewpoint: stats[`viewpoint${suffix}`],
    loophole: stats[`loophole${suffix}`],
  }
}

function preferredMaterial(used: CardCountSummary): MaterialPreference {
  const max = Math.max(...MATERIAL_LABELS.map(label => used[label]))
  if (max <= 0) return { kind: 'none', labels: [] }

  const labels = MATERIAL_LABELS
    .filter(label => used[label] === max)
    .map(label => MATERIAL_NAMES[label])
  return {
    kind: labels.length === 1 ? 'single' : 'tie',
    labels,
  }
}

function buildRunId(input: FinalJourneySummaryInput): string {
  const completed = input.stats.completedRoundNumbers.join(',')
  return [
    `rounds:${completed}`,
    `position:${input.finalPosition.row},${input.finalPosition.col}`,
    `vector:${input.finalHeat.toFixed(4)},${input.finalSalt.toFixed(4)}`,
  ].join('|')
}

function unlockedAchievements(
  definitions: readonly AchievementDefinition[],
  states: readonly AchievementState[],
): UnlockedAchievementSummary[] {
  const stateById = new Map(states.map(state => [state.id, state]))
  return definitions
    .filter(definition => !definition.hidden && stateById.get(definition.id)?.status === 'UNLOCKED')
    .map(definition => ({
      name: definition.name,
      description: definition.description,
    }))
}

export function buildFinalJourneySummary(input: FinalJourneySummaryInput): FinalJourneySummary {
  const collected = cardCounts(input.stats, 'CollectedTotal')
  const used = cardCounts(input.stats, 'UsedTotal')
  const unlocked = unlockedAchievements(input.definitions, input.states)

  return {
    runId: buildRunId(input),
    roundsCompleted: input.stats.completedRounds,
    collected,
    used,
    kanshanInteractions: input.stats.kanshanInteractionTotal,
    heatQualifiedRounds: [...input.stats.heatQualifiedRoundNumbers],
    saltQualifiedRounds: [...input.stats.saltQualifiedRoundNumbers],
    unlockedAchievements: unlocked,
    achievementTotal: input.definitions.filter(definition => !definition.hidden).length,
    finalRegion: input.finalRegion,
    finalPosition: { ...input.finalPosition },
    finalHeat: input.finalHeat,
    finalSalt: input.finalSalt,
    preferredMaterial: preferredMaterial(used),
    roundHistory: input.roundHistory.map(record => ({
      round: record.round,
      vector: [...record.vector] as [number, number],
      toRow: record.toRow,
      toCol: record.toCol,
    })),
  }
}
