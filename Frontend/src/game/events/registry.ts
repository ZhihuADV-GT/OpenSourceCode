/**
 * 随机事件 —— 注册表与抽取逻辑
 * 
 * 职责：
 * - 汇总所有事件数据
 * - 根据权重随机抽取事件
 * - 检查触发条件
 */

import type { RandomEvent, EventCondition, DrawnEvent } from './types'
import { typeAEvents } from './data/typeA'
import { typeBEvents } from './data/typeB'
import { typeCEvents } from './data/typeC'
import { typeDEvents } from './data/typeD'

// ══════════════════════════════════════════════════════════
//  事件注册表
// ══════════════════════════════════════════════════════════

/**
 * 开发期强制每局触发剧情（D 类）事件，方便调试剧情系统。
 * 为 true 时抽取池只保留 D 类；上线前需置 false 恢复 A/B/C/D 混合加权。
 */
export const DEV_FORCE_STORY_EVENT = true

/** 全部事件（按类型分组） */
const ALL_EVENTS: RandomEvent[] = [
  ...typeAEvents,
  ...typeBEvents,
  ...typeCEvents,
  ...typeDEvents,
]

/** 按 ID 索引 */
const EVENT_BY_ID = new Map<string, RandomEvent>(
  ALL_EVENTS.map(e => [e.id, e]),
)

export function getEventById(id: string): RandomEvent | undefined {
  return EVENT_BY_ID.get(id)
}

export function getAllEvents(): readonly RandomEvent[] {
  return ALL_EVENTS
}

// ══════════════════════════════════════════════════════════
//  条件检查
// ══════════════════════════════════════════════════════════

export interface ConditionContext {
  currentRound: number
  answererValue: number
  visitedQuadrants: readonly string[]
}

export function checkCondition(
  condition: EventCondition | undefined,
  ctx: ConditionContext,
): boolean {
  if (!condition) return true

  if (condition.minRound !== undefined && ctx.currentRound < condition.minRound) return false
  if (condition.maxRound !== undefined && ctx.currentRound > condition.maxRound) return false

  if (condition.answererValueMin !== undefined && ctx.answererValue < condition.answererValueMin) return false
  if (condition.answererValueMax !== undefined && ctx.answererValue > condition.answererValueMax) return false

  if (condition.visitedQuadrants) {
    for (const q of condition.visitedQuadrants) {
      if (!ctx.visitedQuadrants.includes(q)) return false
    }
  }

  if (condition.firstVisitQuadrant) {
    // 首次访问：当前局刚进入该象限（visitedQuadrants 不包含）
    if (ctx.visitedQuadrants.includes(condition.firstVisitQuadrant)) return false
  }

  return true
}

// ══════════════════════════════════════════════════════════
//  权重抽取
// ══════════════════════════════════════════════════════════

/**
 * 从事件池中按权重随机抽取一个事件。
 * 每局必触发（v4 设计），抽中后检查条件，不满足则返回 null。
 */
export function drawRandomEvent(ctx: ConditionContext): DrawnEvent | null {
  // 过滤掉 weight = 0 的事件；开发期强制模式下只保留 D 类
  const pool = ALL_EVENTS.filter(e => (
    e.weight > 0 && (!DEV_FORCE_STORY_EVENT || e.type === 'D')
  ))
  if (pool.length === 0) return null

  // 计算总权重
  const totalWeight = pool.reduce((sum, e) => sum + e.weight, 0)
  if (totalWeight <= 0) return null

  // 加权随机
  let roll = Math.random() * totalWeight
  let drawn: RandomEvent = pool[0]
  for (const event of pool) {
    roll -= event.weight
    if (roll <= 0) {
      drawn = event
      break
    }
  }

  // 检查条件
  const conditionMet = checkCondition(drawn.condition, ctx)

  return { event: drawn, conditionMet }
}
