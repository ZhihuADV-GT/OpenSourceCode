/**
 * 随机事件 —— 效果处理器
 * 
 * 职责：执行事件效果，修改游戏状态。
 * 每种事件类型有对应的处理函数。
 */

import type { RandomEvent, EventEffect } from './types'
import type { ConditionContext } from './registry'

// ══════════════════════════════════════════════════════════
//  效果执行上下文（由调用方传入）
// ═════════════════════════════════════════════════════════

export interface EffectContext {
  /** 当前游戏状态上下文 */
  conditionCtx: ConditionContext
  /** 应用 A 类效果：修改位置/向量 */
  applyVectorEffect: (action: string, targetQuadrant?: string) => void
  /** 应用 C 类效果：发放卡牌 */
  giveCard: (cardType: string, count: number) => void
  /** 应用 B 类效果：设置本局任务 */
  setRoundTask: (task: string, cardType: string, count: number) => void
  /** 应用 D 类效果：触发剧情 */
  triggerStory: (storyId: string) => void
}

// ══════════════════════════════════════════════════════════
//  效果执行
// ══════════════════════════════════════════════════════════

/**
 * 执行事件效果
 * 
 * @param event 抽中的事件
 * @param ctx 效果执行上下文
 * @returns 执行结果消息
 */
export function executeEventEffect(event: RandomEvent, ctx: EffectContext): string {
  const effect = event.effect

  switch (effect.type) {
    case 'A':
      return handleVectorEffect(effect, ctx)
    case 'B':
      return handleTaskEffect(effect, ctx)
    case 'C':
      return handleGiveCardEffect(effect, ctx)
    case 'D':
      return handleStoryEffect(effect, ctx)
    default:
      return '未知事件类型'
  }
}

function handleVectorEffect(
  effect: Extract<EventEffect, { type: 'A' }>,
  ctx: EffectContext,
): string {
  ctx.applyVectorEffect(effect.action, effect.targetQuadrant)
  return effect.message
}

function handleTaskEffect(
  effect: Extract<EventEffect, { type: 'B' }>,
  ctx: EffectContext,
): string {
  ctx.setRoundTask(effect.task, effect.cardType, effect.count)
  return effect.message
}

function handleGiveCardEffect(
  effect: Extract<EventEffect, { type: 'C' }>,
  ctx: EffectContext,
): string {
  ctx.giveCard(effect.cardType, effect.count)
  return effect.message
}

function handleStoryEffect(
  effect: Extract<EventEffect, { type: 'D' }>,
  ctx: EffectContext,
): string {
  ctx.triggerStory(effect.storyId)
  return effect.message
}
