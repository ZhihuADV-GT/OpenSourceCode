/**
 * C 类事件：直接给卡
 * 
 * 效果：直接发放素材卡给玩家。
 */

import type { RandomEvent } from '../types'

export const typeCEvents: RandomEvent[] = [
  {
    id: 'c_free_view',
    type: 'C',
    name: '意外发现',
    description: '看山在路边捡到了一张观点卡！',
    weight: 15,
    effect: {
      type: 'C',
      cardType: '观点卡',
      count: 1,
      message: '获得 1 张观点卡！',
    },
  },
  {
    id: 'c_free_emotion',
    type: 'C',
    name: '情绪共鸣',
    description: '看山感受到强烈的情绪波动，凝聚成了一张情绪卡。',
    weight: 12,
    effect: {
      type: 'C',
      cardType: '情绪卡',
      count: 1,
      message: '获得 1 张情绪卡！',
    },
  },
  {
    id: 'c_free_rhetoric',
    type: 'C',
    name: '文采飞扬',
    description: '看山被一段优美的文字打动，获得了一张修辞卡。',
    weight: 10,
    condition: { minRound: 2 },
    effect: {
      type: 'C',
      cardType: '修辞卡',
      count: 1,
      message: '获得 1 张修辞卡！',
    },
  },
]
