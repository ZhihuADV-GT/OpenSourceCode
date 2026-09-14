/**
 * D 类事件：触发剧情
 * 
 * 效果：弹出 ADV 对话框，播放剧情脚本。
 * 剧情脚本在 game/story/scripts/ 中定义；storyId 为 'ai_generated'（即
 * fallbackStories.ts 导出的 AI_STORY_ID）时，剧本由后端 /api/ai/story 实时生成，
 * 失败时降级到本地 A 版预设剧本。
 */

import type { RandomEvent } from '../types'

export const typeDEvents: RandomEvent[] = [
  {
    // 当前唯一生效的 D 类事件：每局结算后触发一段 AI 即兴剧情。
    // weight = 1 且无 condition，配合 registry.ts 的 DEV_FORCE_STORY_EVENT
    // 做到开发期每局必定触发；关闭该开关后与 A/B/C 按权重混合抽取。
    id: 'd_ai_story',
    type: 'D',
    name: '旅途插曲',
    description: '看山想和你说说这片地方的事。',
    weight: 1,
    effect: {
      type: 'D',
      storyId: 'ai_generated',
      message: '看山想和你说说这片地方的事',
    },
  },
  {
    id: 'd_tutorial_first_round',
    type: 'D',
    name: '看山的指引',
    description: '第一局开始，看山会为你介绍这个世界的基本规则。',
    // weight = 0 → 已从抽取池中停用，定义保留仅作历史记录。
    // 停用原因：drawRandomEvent 只在 continueJourney()（一局结算之后）被调用，
    // 彼时 currentRound 已自增，而 game.ts 里的 legacy 守卫又要求 currentRound <= 1，
    // 两个条件永不同时成立，本事件实际上永远不可能触发。
    // 开场介绍改由 MapView 直挂（门控为 gameStore.needsTutorialIntro）。
    weight: 0,
    condition: {
      maxRound: 1, // 仅第一局触发
    },
    effect: {
      type: 'D',
      storyId: 'tutorial_first_round',
      message: '触发剧情：看山的指引（新手教程）',
    },
  },
  // ── 以下三个「初访象限」事件已停用（weight = 0），定义保留作历史记录 ──
  // 停用原因：1) 它们的 storyId（first_visit_view / critique / emotion）从未在
  // scripts/index.ts 注册，isStoryEvent 判定会失败并退化成普通事件面板；
  // 2) visitedQuadrants 在 finalizeMovement() 里就已写入，而事件抽取发生在其后的
  // continueJourney()，firstVisitQuadrant 条件必然为 false，事件永远不可能触发。
  // 象限风物现已改由 d_ai_story 的 AI 生成剧情承载。
  {
    id: 'd_first_quadrant_view',
    type: 'D',
    name: '初访观点海洋',
    description: '看山第一次来到观点海洋，有什么想说的？',
    weight: 0,
    condition: {
      firstVisitQuadrant: 'view',
    },
    effect: {
      type: 'D',
      storyId: 'first_visit_view',
      message: '触发剧情：初访观点海洋',
    },
  },
  {
    id: 'd_first_quadrant_critique',
    type: 'D',
    name: '初访盐度冰川',
    description: '看山第一次来到盐度冰川，有什么想说的？',
    weight: 0,
    condition: {
      firstVisitQuadrant: 'critique',
    },
    effect: {
      type: 'D',
      storyId: 'first_visit_critique',
      message: '触发剧情：初访盐度冰川',
    },
  },
  {
    id: 'd_first_quadrant_emotion',
    type: 'D',
    name: '初访情绪火山',
    description: '看山第一次来到情绪火山，有什么想说的？',
    weight: 0,
    condition: {
      firstVisitQuadrant: 'emotion',
    },
    effect: {
      type: 'D',
      storyId: 'first_visit_emotion',
      message: '触发剧情：初访情绪火山',
    },
  },
]
