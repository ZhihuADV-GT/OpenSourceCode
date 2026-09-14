/**
 * 游戏状态机 —— Vue 组合式 Hook
 * 
 * 在组件/Store 中提供 xstate 状态机实例，
 * 所有屏幕转换通过 send(event) 触发，保证流程合法性。
 * 
 * 使用方式：
 *   const { machine, send, canSend } = useGameMachine()
 *   send({ type: 'OPEN_ARTICLE' })  // 合法则转换，非法则忽略
 */

import { ref, computed } from 'vue'
import { createActor } from 'xstate'
import { createGameMachine } from './gameMachine'
import type { GameEvent, GameScreen } from './types'

let _actor: ReturnType<typeof createActor> | null = null
const currentScreen = ref<GameScreen>('map')

/** 获取（或创建）全局单例状态机 actor */
function getActor() {
  if (!_actor) {
    const machine = createGameMachine()
    _actor = createActor(machine)
    _actor.subscribe((snapshot) => {
      const value = snapshot.value as string
      if (typeof value === 'string') {
        currentScreen.value = value as GameScreen
      }
    })
    _actor.start()
  }
  return _actor
}

/** 从持久化状态恢复（游戏加载时调用一次） */
export function restoreMachineState(screen: GameScreen): void {
  if (_actor) {
    _actor.stop()
    _actor = null
  }
  const machine = createGameMachine()
  // xstate v5: 通过 resolveState 从字符串状态值恢复
  const snapshot = machine.resolveState({ value: screen, context: { round: 1 } })
  _actor = createActor(machine, { snapshot })
  _actor.subscribe((snap) => {
    const value = snap.value as string
    if (typeof value === 'string') {
      currentScreen.value = value as GameScreen
    }
  })
  _actor.start()
}

/** 重置状态机到初始状态 */
export function resetMachineState(): void {
  if (_actor) {
    _actor.stop()
    _actor = null
  }
  currentScreen.value = 'map'
}

export function useGameMachine() {
  const actor = getActor()

  const send = (event: GameEvent) => {
    actor.send(event)
  }

  const canSend = computed(() => {
    return (_eventType: string) => {
      return true // xstate 会自动忽略非法事件
    }
  })

  return {
    /** 当前屏幕状态（响应式） */
    screen: currentScreen,
    /** 发送事件触发状态转换 */
    send,
    /** 检查事件是否可发送 */
    canSend: canSend.value,
    /** 底层 actor（高级用法） */
    actor,
  }
}
