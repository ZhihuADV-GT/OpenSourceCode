/** game/events —— 随机事件系统 */
export type { RandomEvent, RandomEventType, EventEffect, DrawnEvent, CardType } from './types'
export { RANDOM_EVENT_TYPE_LABEL, ALL_CARD_TYPES } from './types'
export { drawRandomEvent, checkCondition, getEventById, getAllEvents } from './registry'
export type { ConditionContext } from './registry'
export { executeEventEffect } from './effects'
export type { EffectContext } from './effects'
export { setRoundTask, resetRoundTask, incrementTaskProgress, useRoundTask } from './taskTracker'
