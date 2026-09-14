<script setup lang="ts">
/** 文章阶段：只负责阅读与收集，正式创作流由地图页 overlay 承载。 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import GameLayout from '../components/GameLayout.vue'
import { fetchRandomAIArticle } from '../services/articleService'
import { useGameStore } from '../stores/game'
import { useGameRuntimeStore } from '../stores/gameRuntime'
import { useWorkbenchStore } from '../stores/workbench'
import type { Article } from '../types/article'

const article = ref<Article | null>(null)
const loadError = ref('')
const isLoadingNewArticle = ref(false)
const gameStore = useGameStore()
const gameRuntimeStore = useGameRuntimeStore()
const workbenchStore = useWorkbenchStore()

async function loadArticle() {
  try {
    if (gameStore.screen !== 'article') {
      gameStore.openArticle()
    }
    
    const loadedArticle = gameStore.article ?? await fetchRandomAIArticle()
    
    if (!loadedArticle) {
      throw new Error('没有可用的AI文章')
    }
    
    article.value = loadedArticle
    gameStore.setArticle(loadedArticle)
    gameStore.recordSeenArticle(loadedArticle.id)
    gameRuntimeStore.startRound(loadedArticle)
    workbenchStore.setupSlotSync()
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error)
    console.error('[GameView] 文章加载失败，请确认后端服务已启动:', error)
  }
}

async function handleFindMoreNotes() {
  if (isLoadingNewArticle.value) return
  isLoadingNewArticle.value = true
  loadError.value = ''
  try {
    const newArticle = await fetchRandomAIArticle(gameStore.seenArticleIds)
    if (!newArticle) {
      throw new Error('没有可用的AI文章')
    }
    // 保留背包中已有的卡牌，只更新文章和计时器
    article.value = newArticle
    gameStore.setArticle(newArticle)
    gameStore.recordSeenArticle(newArticle.id)
    gameRuntimeStore.startRound(newArticle)
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error)
    console.error('[GameView] 刷新文章失败:', error)
  } finally {
    isLoadingNewArticle.value = false
  }
}

onMounted(loadArticle)

onBeforeUnmount(() => {
  gameRuntimeStore.stopRound()
  workbenchStore.stopSlotSync()
})
</script>

<template>
  <GameLayout v-if="article" :article="article" :is-loading="isLoadingNewArticle" @continue="handleFindMoreNotes" />
  <main v-else class="empty-state">
    <p v-if="loadError">文章加载失败：{{ loadError }}</p>
    <p v-else>{{ isLoadingNewArticle ? '正在寻找新的笔记…' : '正在从后端加载文章…' }}</p>
  </main>
</template>
