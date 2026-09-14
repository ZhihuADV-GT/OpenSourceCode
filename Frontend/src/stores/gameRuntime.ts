import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref } from 'vue'
import { storeToRefs } from 'pinia'
import type { Article } from '../types/article'
import { useMaterialStore } from './material'

const DEFAULT_ROUND_DURATION_SECONDS = 600

export const useGameRuntimeStore = defineStore('gameRuntime', () => {
  const materialStore = useMaterialStore()
  const { materials } = storeToRefs(materialStore)
  const activeArticle = ref<Article | null>(null)
  const answererValue = ref<number | null>(null)
  const roundDurationSeconds = ref(DEFAULT_ROUND_DURATION_SECONDS)
  const timeRemainingSeconds = ref(DEFAULT_ROUND_DURATION_SECONDS)
  let timer: ReturnType<typeof window.setInterval> | null = null

  const understandingTarget = computed(() => activeArticle.value?.targetValue ?? 0)
  const understandingCurrent = computed(() => {
    const articleId = activeArticle.value?.id
    if (!articleId) {
      return 0
    }

    const uniqueValues = new Map<string, number>()
    for (const material of materials.value) {
      if (material.articleId !== articleId) {
        continue
      }

      const materialKey = material.informationPointId || material.id
      if (!uniqueValues.has(materialKey)) {
        uniqueValues.set(materialKey, material.attributeValue ?? 0)
      }
    }

    return [...uniqueValues.values()].reduce((total, value) => total + value, 0)
  })

  function clearTimer() {
    if (timer !== null) {
      window.clearInterval(timer)
      timer = null
    }
  }

  function startRound(article: Article) {
    clearTimer()
    activeArticle.value = article
    timeRemainingSeconds.value = roundDurationSeconds.value

    timer = window.setInterval(() => {
      if (timeRemainingSeconds.value <= 1) {
        timeRemainingSeconds.value = 0
        clearTimer()
        return
      }

      timeRemainingSeconds.value -= 1
    }, 1000)
  }

  function stopRound() {
    clearTimer()
  }

  onScopeDispose(clearTimer)

  return {
    activeArticle,
    answererValue,
    roundDurationSeconds,
    timeRemainingSeconds,
    understandingCurrent,
    understandingTarget,
    startRound,
    stopRound,
  }
})
