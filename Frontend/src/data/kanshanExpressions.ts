import type { RandomEvent } from '../game/events/types'
// [art-assets disabled]
const kanshanCelebrate = ''
const kanshanConfused = ''
const kanshanEncourage = ''
const kanshanHappy = ''
const kanshanNeutral = ''
const kanshanThinking = ''
const kanshanOkay = ''
const kanshanCheer = ''

export type KanshanExpressionName =
  | 'neutral'
  | 'thinking'
  | 'happy'
  | 'confused'
  | 'encourage'
  | 'celebrate'
  | 'okay'
  | 'cheer'

export const kanshanExpressions: Record<KanshanExpressionName, string> = {
  neutral: kanshanNeutral,
  thinking: kanshanThinking,
  happy: kanshanHappy,
  confused: kanshanConfused,
  encourage: kanshanEncourage,
  celebrate: kanshanCelebrate,
  okay: kanshanOkay,
  cheer: kanshanCheer,
}

const randomEventExpressionById: Partial<Record<RandomEvent['id'], KanshanExpressionName>> = {
  a_push_to_center: 'confused',
  a_invert_vector: 'confused',
  a_zero_vector: 'confused',
  b_collect_views: 'encourage',
  b_compose_emotion: 'thinking',
  b_collect_rhetoric: 'encourage',
  c_free_view: 'celebrate',
  c_free_emotion: 'happy',
  c_free_rhetoric: 'happy',
  d_tutorial_first_round: 'neutral',
  d_first_quadrant_view: 'thinking',
  d_first_quadrant_critique: 'thinking',
  d_first_quadrant_emotion: 'thinking',
}

export function getKanshanExpression(name: string | undefined): string {
  if (!name || !(name in kanshanExpressions)) return kanshanExpressions.neutral
  return kanshanExpressions[name as KanshanExpressionName]
}

export function getKanshanRandomEventExpression(event: Pick<RandomEvent, 'id'> | null | undefined): string {
  return getKanshanExpression(event ? randomEventExpressionById[event.id] : undefined)
}
