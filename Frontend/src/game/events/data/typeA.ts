/**
 * A 类事件：直接作用向量/位置
 * 
 * 效果：修改玩家位置或本局向量，立即生效。
 */

import type { RandomEvent } from '../types'

export const typeAEvents: RandomEvent[] = [
  {
    id: 'a_push_to_center',
    type: 'A',
    name: '迷雾骤起',
    description: '一阵迷雾将你带回了起点……',
    weight: 15,
    effect: {
      type: 'A',
      action: 'push_to_center',
      message: '迷雾散去，你发现自己回到了地图中央。',
    },
  },
  {
    id: 'a_invert_vector',
    type: 'A',
    name: '方向感紊乱',
    description: '你的指南针突然反转了方向！',
    weight: 10,
    condition: { minRound: 2 }, // 第2局后才可能触发
    effect: {
      type: 'A',
      action: 'invert_vector',
      message: '方向感恢复了，但本局向量被反转了。',
    },
  },
  {
    id: 'a_zero_vector',
    type: 'A',
    name: '记忆断层',
    description: '你忘记了刚才的合成方向……',
    weight: 8,
    condition: { minRound: 3 },
    effect: {
      type: 'A',
      action: 'zero_vector',
      message: '本局的向量被清零了，需要重新合成。',
    },
  },
]
