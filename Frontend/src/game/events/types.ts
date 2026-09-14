/**
 * 随机事件 —— 类型定义
 * 
 * 四种事件类型：
 * - A: 直接作用向量/位置（如把玩家抛回荒原中心）
 * - B: 任务型（本局需要 N 张观点卡 / 合成需特定卡）
 * - C: 直接给卡
 * - D: 触发剧情（弹出 ADV 对话框）
 */

import type { QuadrantType } from '../../types/mapTypes'

/** 卡牌类型（与素材卡的 type 字段对应） */
export type CardType = '观点卡' | '情绪卡' | '漏洞卡' | '修辞卡'

export const ALL_CARD_TYPES: readonly CardType[] = ['观点卡', '情绪卡', '漏洞卡', '修辞卡']

// ══════════════════════════════════════════════════════════
//  事件类型枚举
// ══════════════════════════════════════════════════════════

export type RandomEventType = 'A' | 'B' | 'C' | 'D'

export const RANDOM_EVENT_TYPE_LABEL: Record<RandomEventType, string> = {
  A: '环境变化',
  B: '特殊任务',
  C: '意外收获',
  D: '剧情触发',
}

// ══════════════════════════════════════════════════════════
//  事件数据结构
// ══════════════════════════════════════════════════════════

export interface RandomEvent {
  /** 唯一 ID */
  id: string
  /** 事件类型 */
  type: RandomEventType
  /** 显示名称 */
  name: string
  /** 描述文本（展示给玩家） */
  description: string
  /** 触发权重（越大越容易抽中，0 = 不主动抽取） */
  weight: number
  /** 触发条件（不满足则跳过） */
  condition?: EventCondition
  /** 事件效果 */
  effect: EventEffect
}

/** 触发条件：所有条件都必须满足 */
export interface EventCondition {
  /** 最低局数（currentRound >= minRound） */
  minRound?: number
  /** 最高局数 */
  maxRound?: number
  /** 必须已访问的象限 */
  visitedQuadrants?: QuadrantType[]
  /** 必须未访问的象限（首次进入时触发） */
  firstVisitQuadrant?: QuadrantType
  /** 答主值范围 */
  answererValueMin?: number
  answererValueMax?: number
}

// ══════════════════════════════════════════════════════════
//  事件效果
// ══════════════════════════════════════════════════════════

/** A 类效果：直接修改向量/位置 */
export interface EffectVectorModify {
  type: 'A'
  /** 效果子类型 */
  action:
    | 'push_to_center'      // 抛回地图中心
    | 'push_to_quadrant'    // 抛到指定象限中心
    | 'invert_vector'       // 反转本局向量
    | 'zero_vector'         // 清零本局向量
  /** 目标象限（action = push_to_quadrant 时使用） */
  targetQuadrant?: QuadrantType
  /** 附加消息（展示给玩家） */
  message: string
}

/** B 类效果：任务型 */
export interface EffectTask {
  type: 'B'
  /** 任务子类型 */
  task:
    | 'collect_cards'       // 本局收集 N 张指定类型卡
    | 'compose_with_card'   // 合成时必须包含指定类型卡
  /** 目标卡牌类型 */
  cardType: CardType
  /** 目标数量 */
  count: number
  /** 任务描述 */
  message: string
}

/** C 类效果：直接给卡 */
export interface EffectGiveCard {
  type: 'C'
  /** 卡牌类型 */
  cardType: CardType
  /** 数量 */
  count: number
  /** 附加消息 */
  message: string
}

/** D 类效果：触发剧情 */
export interface EffectStory {
  type: 'D'
  /** 剧情脚本 ID */
  storyId: string
  /** 附加消息（事件标题） */
  message: string
}

export type EventEffect = EffectVectorModify | EffectTask | EffectGiveCard | EffectStory

// ══════════════════════════════════════════════════════════
//  抽取结果
// ═════════════════════════════════════════════════════════

export interface DrawnEvent {
  event: RandomEvent
  /** 是否满足触发条件 */
  conditionMet: boolean
}
