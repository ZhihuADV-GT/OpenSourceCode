<script setup lang="ts">
/**
 * 应用根组件 — 路由容器
 * Landing 页面 (/) 和地图游戏页面 (/game) 通过 vue-router 切换
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import AchievementUnlockToast from './components/achievement/AchievementUnlockToast.vue'
import { ACHIEVEMENT_DEFINITIONS } from './data/achievementDefinitions'
import { useAchievementStore as getAchievementStore } from './stores/achievements'

const achievementStore = getAchievementStore()
const activeUnlockId = ref<string | null>(null)
const toastVisible = ref(false)
let hideTimer: ReturnType<typeof window.setTimeout> | undefined
let dequeueTimer: ReturnType<typeof window.setTimeout> | undefined

const activeAchievement = computed(() => (
  ACHIEVEMENT_DEFINITIONS.find(definition => definition.id === activeUnlockId.value) ?? null
))

function clearToastTimers() {
  if (hideTimer !== undefined) window.clearTimeout(hideTimer)
  if (dequeueTimer !== undefined) window.clearTimeout(dequeueTimer)
  hideTimer = undefined
  dequeueTimer = undefined
}

function showNextUnlock() {
  if (activeUnlockId.value !== null) return

  const nextUnlockId = achievementStore.unlockQueue[0]
  if (!nextUnlockId) return

  activeUnlockId.value = nextUnlockId
  toastVisible.value = true
  hideTimer = window.setTimeout(() => {
    toastVisible.value = false
    dequeueTimer = window.setTimeout(() => {
      achievementStore.dequeueUnlock(nextUnlockId)
      activeUnlockId.value = null
      showNextUnlock()
    }, 280)
  }, 3200)
}

watch(() => achievementStore.unlockQueue.length, showNextUnlock, { immediate: true })

onBeforeUnmount(() => {
  clearToastTimers()
})
</script>

<template>
  <RouterView />
  <AchievementUnlockToast
    :achievement="activeAchievement"
    :visible="toastVisible"
  />
</template>
