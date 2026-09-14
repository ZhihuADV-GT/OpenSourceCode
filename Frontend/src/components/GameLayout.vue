<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, nextTick, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { Article, HintItem } from '../types/article'
// [art-assets disabled]
const backpackImg = ''
const readingBookFrame = ''
const readingSceneBackground = ''
const kanshanStickerImg = ''
const starStickerImg = ''
import ArticlePanel from './article/ArticlePanel.vue'
import ArticleHintModal from './article/ArticleHintModal.vue'
import Backpack from './crafting/Backpack.vue'
import CollectionFlyOverlay from './CollectionFlyOverlay.vue'
import RightSecondaryColumn from './RightSecondaryColumn.vue'
import SubWindow from './SubWindow.vue'
import type { CollectionFlight } from '../types/collectionMotion'
import { useGameStore } from '../stores/game'
import { useGameRuntimeStore } from '../stores/gameRuntime'
import { useMaterialStore } from '../stores/material'
import { fetchArticleHint } from '../services/hintService'
import {
  KANSHAN_DECORATION_VARIANTS,
  takeNextKanshanDecorationVariant,
  type KanshanDecorationVariant,
} from './kanshanDecorationVariants'

const emit = defineEmits<{
  continue: []
}>()

const props = defineProps<{
  article: Article
  isLoading?: boolean
}>()

const collectionFlight = ref<CollectionFlight | null>(null)
const showBackpack = ref(false)
const queuedFlights: CollectionFlight[] = []
const articlePanelRef = ref<InstanceType<typeof ArticlePanel> | null>(null)
const showHintModal = ref(false)
const hintModalMessage = ref('')
const hintModalHints = ref<HintItem[]>([])
const hintModalLoading = ref(false)
const hintModalAnalysis = ref('')
const router = useRouter()
const gameStore = useGameStore()
const runtimeStore = useGameRuntimeStore()
const materialStore = useMaterialStore()
const { materials } = storeToRefs(materialStore)
const pendingArrivalMaterialIds = reactive(new Set<string>())
const articleBackpackDecorationVariant = ref<KanshanDecorationVariant>(KANSHAN_DECORATION_VARIANTS[0])
const understandingPercent = computed(() => {
  const target = runtimeStore.understandingTarget
  if (target <= 0) {
    return 0
  }

  return Math.min(100, Math.max(0, Math.round(
    runtimeStore.understandingCurrent / target * 100,
  )))
})
const readingSceneStyle = {
  '--reading-scene-bg': `url("${readingSceneBackground}")`,
}

function handleMaterialCollected(flight: CollectionFlight) {
  if (collectionFlight.value) {
    queuedFlights.push(flight)
    return
  }

  collectionFlight.value = flight
}

function handleFlightComplete() {
  collectionFlight.value = queuedFlights.shift() ?? null
}

function openBackpack() {
  articleBackpackDecorationVariant.value = takeNextKanshanDecorationVariant(articleBackpackDecorationVariant.value)
  showBackpack.value = true
}

function completeReading() {
  showBackpack.value = false
  if (gameStore.completeReading()) {
    void router.push('/game')
  }
}

/**
 * 打开阅读提示弹窗
 */
async function openHintModal() {
  if (!articlePanelRef.value) {
    return
  }

  hintModalLoading.value = true
  hintModalAnalysis.value = ''
  showHintModal.value = true

  const result = await articlePanelRef.value.fetchHintsForModal()
  hintModalLoading.value = false

  if (result) {
    hintModalMessage.value = result.message
    hintModalHints.value = result.hints
  } else {
    hintModalMessage.value = '暂时无法获取阅读建议，请稍后再试~'
    hintModalHints.value = []
  }
}

/**
 * 处理跳转到 hint 位置：关弹窗 → 高亮 → 滚动到可见
 */
function handleJumpToHint(hint: HintItem) {
  if (!articlePanelRef.value) {
    return
  }

  // 关闭弹窗，让文章可见
  showHintModal.value = false

  // 设置 hint 高亮
  articlePanelRef.value.showHintHighlight([{
    start: hint.start,
    end: hint.end,
    type: hint.type,
  }])

  // 等待渲染后滚动到高亮位置
  nextTick(() => {
    const el = document.querySelector('.article-highlight-hint')
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  })

  // 5 秒后清除高亮
  setTimeout(() => {
    if (articlePanelRef.value) {
      articlePanelRef.value.showHintHighlight([])
    }
  }, 5000)
}

/**
 * 处理深度分析：调用 AI deep 模式
 */
async function handleDeepAnalysis() {
  hintModalLoading.value = true
  const result = await fetchArticleHint(props.article.id, 'deep')
  hintModalLoading.value = false

  if (result && result.mode === 'deep' && result.analysis) {
    hintModalAnalysis.value = result.analysis
  } else {
    hintModalAnalysis.value = '深度分析暂时不可用，先看看上面的基础建议吧~'
  }
}
</script>

<template>
  <main class="game-page game-page--reading" data-round-scene="reading">
    <div class="reading-scene" :style="readingSceneStyle">
      <aside class="reading-understanding-hud" aria-label="理解度">
        <div class="reading-understanding-hud__heading">
          <span>理解度</span>
          <strong>{{ understandingPercent }}%</strong>
        </div>
        <div
          class="reading-understanding-hud__progress"
          role="progressbar"
          aria-label="理解度"
          :aria-valuenow="understandingPercent"
          aria-valuemin="0"
          aria-valuemax="100"
        >
          <span :style="{ width: `${understandingPercent}%` }"></span>
        </div>
      </aside>

      <section class="book-stage" aria-label="Article reading area">
        <img :src="readingBookFrame" alt="" aria-hidden="true" class="book-frame" />
        <div class="book-content book-content--reading">
          <ArticlePanel ref="articlePanelRef" :article="article" @material-collected="handleMaterialCollected" />
        </div>
      </section>

      <button
        class="backpack-dock"
        type="button"
        data-backpack-dock
        title="打开卡牌背包"
        aria-label="打开卡牌背包"
        :aria-expanded="showBackpack"
        @click="openBackpack"
      >
        <img :src="backpackImg" alt="背包" class="backpack-dock-icon" />
        <span v-if="materials.length" class="backpack-dock-count">{{ materials.length }}</span>
      </button>

      <button class="reading-complete-button" type="button" @click="completeReading">
        返回地图
      </button>

      <button class="find-more-notes-button" type="button" :disabled="isLoading" @click="emit('continue')">
        {{ isLoading ? '寻找中…' : '继续寻找笔记' }}
      </button>

      <RightSecondaryColumn @module-a-click="openHintModal" />
    </div>

    <!-- 阅读提示弹窗 -->
    <ArticleHintModal
      :visible="showHintModal"
      :message="hintModalMessage"
      :hints="hintModalHints"
      :loading="hintModalLoading"
      :analysis="hintModalAnalysis"
      @close="showHintModal = false"
      @jump-to-hint="handleJumpToHint"
      @deep-analysis="handleDeepAnalysis"
    />

    <SubWindow
      title="卡牌背包"
      icon="🎒"
      theme="article-backpack"
      :visible="showBackpack"
      @close="showBackpack = false"
    >
      <div
        class="backpack-window-body article-backpack-window"
        :class="`article-backpack-window--${articleBackpackDecorationVariant}`"
        :data-decoration-variant="articleBackpackDecorationVariant"
      >
        <img class="article-backpack-decoration article-backpack-decoration--star" :src="starStickerImg" alt="" aria-hidden="true" />
        <img class="article-backpack-decoration article-backpack-decoration--character" :src="kanshanStickerImg" alt="" aria-hidden="true" />
        <Backpack
          :pending-arrival-material-ids="pendingArrivalMaterialIds"
          read-only
        />
      </div>
    </SubWindow>

    <CollectionFlyOverlay :flight="collectionFlight" @complete="handleFlightComplete" />
  </main>
</template>
