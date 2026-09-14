<script setup lang="ts">
/**
 * 文章全屏覆盖层
 *
 * 复刻 GameLayout 的完整文章阅读体验，作为地图页的子组件以全屏覆盖形式展示。
 * 使用明确的“返回地图”操作结束阅读并返回地图。
 */

import { storeToRefs } from 'pinia'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import type { Article, HintItem } from '../../types/article'
// [art-assets disabled]
const backpackImg = ''
const mapBgm = ''
const readingBgm = ''
const readingBookFrame = ''
const readingSceneBackground = ''
const kanshanStickerImg = ''
const starStickerImg = ''
import ArticlePanel from './ArticlePanel.vue'
import ArticleHintModal from './ArticleHintModal.vue'
import Backpack from '../crafting/Backpack.vue'
import CollectionFlyOverlay from '../CollectionFlyOverlay.vue'
import RightSecondaryColumn from '../RightSecondaryColumn.vue'
import SubWindow from '../SubWindow.vue'
import type { CollectionFlight } from '../../types/collectionMotion'
import { useGameStore } from '../../stores/game'
import { useGameRuntimeStore } from '../../stores/gameRuntime'
import { useMaterialStore } from '../../stores/material'
import { AUDIO_VOLUME, playBgm, stopBgm } from '../../services/audioManager'
import { fetchArticleHint } from '../../services/hintService'
import {
  KANSHAN_DECORATION_VARIANTS,
  takeNextKanshanDecorationVariant,
  type KanshanDecorationVariant,
} from '../kanshanDecorationVariants'

const props = defineProps<{
  article: Article
  isLoading?: boolean
  /** 首次教学期的素材采集阶段：锁住所有离开文章页的出口 */
  lockClose?: boolean
}>()

const emit = defineEmits<{
  close: []
  findMore: []
  openMapBackpack: []
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
const gameStore = useGameStore()
const runtimeStore = useGameRuntimeStore()
const materialStore = useMaterialStore()
const { materials } = storeToRefs(materialStore)
const pendingArrivalMaterialIds = reactive(new Set<string>())
const articleBackpackDecorationVariant = ref<KanshanDecorationVariant>(KANSHAN_DECORATION_VARIANTS[0])

onMounted(() => {
  playBgm(readingBgm, { loop: true, volume: AUDIO_VOLUME.readingBgm })
})

onBeforeUnmount(() => {
  stopBgm(readingBgm)
  playBgm(mapBgm, { loop: true, volume: AUDIO_VOLUME.mapBgm })
})

const understandingPercent = computed(() => {
  const target = runtimeStore.understandingTarget
  if (target <= 0) return 0
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
  // 保留原逻辑：打开文章页内置背包（只读）
  articleBackpackDecorationVariant.value = takeNextKanshanDecorationVariant(articleBackpackDecorationVariant.value)
  showBackpack.value = true
}

/** 跳转到地图页的背包/工作台（教程引导用） */
function goToMapWorkbench() {
  emit('openMapBackpack')
}

function handleClose() {
  // 全流程唯一的功能性强制：采到素材之前不允许离开文章页
  if (props.lockClose) return
  showBackpack.value = false
  gameStore.completeReading()
  emit('close')
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
  <Teleport to="body">
    <div class="article-overlay-root">
      <div class="article-overlay-backdrop" />

      <div class="article-overlay-panel game-page game-page--reading" data-round-scene="reading">
        <div class="reading-scene" :style="readingSceneStyle">
          <!-- 页面返回地图（首次教学期的采集阶段隐藏，防止未采到素材就离开） -->
          <button
            v-if="!lockClose"
            class="article-overlay-return-map-btn"
            type="button"
            title="返回地图"
            @click="handleClose"
          >
            返回地图
          </button>

          <!-- 理解度 HUD -->
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

          <!-- 文章阅读区 -->
          <section class="book-stage" aria-label="Article reading area">
            <img :src="readingBookFrame" alt="" aria-hidden="true" class="book-frame" />
            <div class="book-content book-content--reading">
              <ArticlePanel ref="articlePanelRef" :article="article" @material-collected="handleMaterialCollected" />
            </div>
          </section>

          <!-- 背包 dock（教程引导：跳转到地图页背包/工作台） -->
          <button
            v-if="!lockClose"
            class="backpack-dock"
            type="button"
            data-backpack-dock
            data-tutorial-backpack
            title="前往工作台"
            aria-label="前往工作台"
            :aria-expanded="showBackpack"
            @click="goToMapWorkbench"
          >
            <img :src="backpackImg" alt="背包" class="backpack-dock-icon" />
            <span v-if="materials.length" class="backpack-dock-count">{{ materials.length }}</span>
          </button>

          <!-- 继续寻找笔记 -->
          <button class="find-more-notes-button" type="button" :disabled="isLoading" @click="emit('findMore')">
            {{ isLoading ? '寻找中…' : '继续寻找笔记' }}
          </button>

          <!-- 右侧看山列 -->
          <RightSecondaryColumn @module-a-click="openHintModal" />
        </div>

        <!-- 背包子窗口 -->
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
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.article-overlay-root {
  position: fixed;
  inset: 0;
  z-index: 80;
}

.article-overlay-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(3px);
}

.article-overlay-panel {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  overflow: auto;
}

/* 覆盖 game-page 的 min-height:100vh，改为精确填满 */
.article-overlay-panel.game-page {
  min-height: 100%;
}

.article-overlay-return-map-btn {
  position: fixed;
  z-index: 99;
  top: 16px;
  right: 18px;
  display: grid;
  place-items: center;
  min-width: 108px;
  height: 44px;
  padding: 0 16px;
  border: 1px solid rgba(157, 124, 77, 0.68);
  border-radius: 9px 4px 9px 4px;
  background: rgba(248, 239, 216, 0.96);
  box-shadow: 3px 4px 0 rgba(92, 66, 35, 0.16);
  color: #6c5435;
  font: 800 clamp(0.88rem, 1vw, 1rem)/1.15 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
  font-weight: 800;
  cursor: pointer;
  transition: background 150ms ease, transform 120ms ease, box-shadow 120ms ease;
  backdrop-filter: blur(6px);
}

.article-overlay-return-map-btn:hover {
  background: #f5e5bf;
  transform: translateY(-2px);
  box-shadow: 4px 5px 0 rgba(92, 66, 35, 0.18);
}
</style>
