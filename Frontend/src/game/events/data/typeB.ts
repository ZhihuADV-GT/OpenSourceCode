/**
 * B 类事件：任务型
 * 
 * 效果：给本局添加特殊目标，需要前端计数器跟踪进度。
 */

import type { RandomEvent } from '../types'

export const typeBEvents: RandomEvent[] = [
  {
    id: 'b_collect_views',
    type: 'B',
    name: '观点猎人',
    description: '看山发现这片区域观点密集，本局收集 3 张观点卡有额外奖励！',
    weight: 12,
    effect: {
      type: 'B',
      task: 'collect_cards',
      cardType: '观点卡',
      count: 3,
      message: '本局收集 3 张观点卡，完成任务！',
    },
  },
  {
    id: 'b_compose_emotion',
    type: 'B',
    name: '情绪共振',
    description: '空气中弥漫着强烈的情绪波动，合成时加入情绪卡效果更佳。',
    weight: 10,
    effect: {
      type: 'B',
      task: 'compose_with_card',
      cardType: '情绪卡',
      count: 1,
      message: '合成时包含至少 1 张情绪卡！',
    },
  },
  {
    id: 'b_collect_rhetoric',
    type: 'B',
    name: '修辞鉴赏',
    description: '看山对优美的文字特别敏感，本局收集 2 张修辞卡吧！',
    weight: 10,
    condition: { minRound: 2 },
    effect: {
      type: 'B',
      task: 'collect_cards',
      cardType: '修辞卡',
      count: 2,
      message: '本局收集 2 张修辞卡，完成任务！',
    },
  },
]
