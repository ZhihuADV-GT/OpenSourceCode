/**
 * 游戏主状态机 —— xstate 定义
 * 
 * 职责：管理屏幕状态转换，保证流程合法性。
 * 不管理游戏数据（向量、答主值等由 Pinia store 负责）。
 * 
 * v5 状态流转图：
 * 
 *   map ─BEGIN_ROUND──→ round-intro ─SKIP_INTRO──→ map
 *                              │                        │
 *                         OPEN_ARTICLE            OPEN_ARTICLE
 *                              │                        │
 *                              ▼                        ▼
 *                          article ──COMPLETE_READING──→ map-needs-vector
 *                              ▲         │                    │
 *                              │    RETURN_TO_MAP        SUBMIT_VECTOR
 *                              │         │                    │
 *                              ─────────┘                    ▼
 *                                                         map-ready
 *                                                           │  │
 *                                                    START_WRITE │ SUBMIT
 *                                                       │       │
 *                                                       ▼       ▼
 *                                                      write  article-gen
 *                                                       │       │
 *                                                 SKIP_WRITE  ARTICLE_DONE / SKIP_ARTICLE
 *                                                 FINISH_WRITE   │
 *                                                       │        ▼
 *                                                       └──→ round-settlement
 *                                                              │
 *                                                         ACTIVATE_COMPASS
 *                                                              │
 *                                                              ▼
 *                                                          map-moving
 *                                                              │
 *                                                         MOVEMENT_COMPLETE
 *                                                              │
 *                                                              ▼
 *                                                         round-settlement
 *                                                              │
 *                                                         SETTLEMENT_DONE
 *                                                              │
 *                                                              ▼
 *                                                         random-event
 *                                                              │
 *                                                         EVENT_RESOLVED
 *                                                              │
 *                                                              ▼
 *                                                          round-intro（下一局）
 */

import { setup } from 'xstate'
import type { GameScreen, GameEvent } from './types'

const gameMachine = setup({
  types: {
    context: {} as { round: number },
    events: {} as GameEvent,
  },
}).createMachine({
  id: 'game',
  initial: 'map',
  context: { round: 1 },

  states: {
    map: {
      on: {
        BEGIN_ROUND: 'round-intro',
        OPEN_ARTICLE: 'article',
        RESET_GAME: 'map',
      },
    },

    'round-intro': {
      on: {
        SKIP_INTRO: 'map',
        OPEN_ARTICLE: 'article',
        RESET_GAME: 'map',
      },
    },

    article: {
      on: {
        COMPLETE_READING: {
          target: 'map-needs-vector',
          // guard: 如果有 pendingKanshanMove 则去 map-ready（在 action 中处理）
        },
        RETURN_TO_MAP: 'map',
        RESET_GAME: 'map',
      },
    },

    'map-needs-vector': {
      on: {
        SUBMIT_VECTOR: 'map-ready',
        OPEN_ARTICLE: 'article',
        RESET_GAME: 'map',
      },
    },

    'map-ready': {
      on: {
        SUBMIT: 'article-gen',           // v5: 提交配卡 → 文章生成
        START_WRITE: 'write',
        ACTIVATE_COMPASS: 'map-moving',  // 保留：兼容旧流程直接出发
        OPEN_ARTICLE: 'article',
        RESET_GAME: 'map',
      },
    },

    'article-gen': {
      on: {
        ARTICLE_DONE: 'round-settlement',
        SKIP_ARTICLE: 'round-settlement',
        RESET_GAME: 'map',
      },
    },

    write: {
      on: {
        SKIP_WRITE: 'map-ready',
        FINISH_WRITE: 'map-ready',
        RETURN_TO_MAP: 'map',
        RESET_GAME: 'map',
      },
    },

    'map-moving': {
      on: {
        MOVEMENT_COMPLETE: 'round-settlement',
        RESET_GAME: 'map',
      },
    },

    'round-settlement': {
      on: {
        ACTIVATE_COMPASS: 'map-moving',  // v5: 结算完成后点击出发
        SETTLEMENT_DONE: 'random-event',
        CONTINUE_JOURNEY: 'round-intro', // 旧流程兼容（跳过随机事件）
        RESET_GAME: 'map',
      },
    },

    'random-event': {
      on: {
        EVENT_RESOLVED: 'round-intro',
        RESET_GAME: 'map',
      },
    },

    'final-settlement': {
      type: 'final',
    },
  },
})

/** 创建状态机实例 */
export function createGameMachine() {
  return gameMachine
}

/** 从持久化屏幕状态获取 xstate 初始状态值 */
export function getInitialStateValue(screen: GameScreen): string {
  return screen
}

export type GameMachine = ReturnType<typeof createGameMachine>
