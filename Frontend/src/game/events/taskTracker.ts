/**
 * B 类事件 —— 任务追踪器
 * 
 * 追踪本局由 B 类事件设置的任务进度。
 * 在 collectCard / compose 时调用 checkTaskProgress 检查是否完成。
 */

import { ref, computed } from 'vue'
import type { EffectTask } from './types'

/** 当前局任务 */
const currentTask = ref<EffectTask | null>(null)
/** 当前进度 */
const currentProgress = ref(0)
/** 是否已完成 */
const isTaskCompleted = computed(() => {
  if (!currentTask.value) return false
  return currentProgress.value >= currentTask.value.count
})

/**
 * 设置本局任务（B 类事件触发时调用）
 */
export function setRoundTask(task: EffectTask) {
  currentTask.value = task
  currentProgress.value = 0
}

/**
 * 重置任务（新局开始时调用）
 */
export function resetRoundTask() {
  currentTask.value = null
  currentProgress.value = 0
}

/**
 * 增加进度（收集/合成卡牌时调用）
 * 
 * @param cardType 卡牌类型
 * @param count 增加数量
 * @returns 是否刚完成（本次增加后刚好达标）
 */
export function incrementTaskProgress(cardType: string, count: number = 1): boolean {
  if (!currentTask.value) return false
  if (currentTask.value.cardType !== cardType) return false

  const wasCompleted = isTaskCompleted.value
  currentProgress.value += count

  // 检查是否刚完成
  if (!wasCompleted && isTaskCompleted.value) {
    return true
  }
  return false
}

/**
 * 获取当前任务状态
 */
export function useRoundTask() {
  return {
    /** 当前任务 */
    task: currentTask,
    /** 当前进度 */
    progress: currentProgress,
    /** 是否已完成 */
    isCompleted: isTaskCompleted,
    /** 任务描述 */
    taskDescription: computed(() => {
      if (!currentTask.value) return ''
      const { task, cardType, count, message } = currentTask.value
      const progressText = `${currentProgress.value}/${count}`
      if (task === 'collect_cards') {
        return `收集 ${cardType}：${progressText}`
      }
      if (task === 'compose_with_card') {
        return `合成时包含 ${cardType}：${progressText}`
      }
      return message
    }),
  }
}
