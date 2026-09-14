<script setup lang="ts">
/** 地图阶段：Map → 出发按钮 → Compass animation → movement → settlement。 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AchievementPanel from '../components/achievement/AchievementPanel.vue'
import ArticleOverlay from '../components/article/ArticleOverlay.vue'
import BackpackWindow from '../components/crafting/BackpackWindow.vue'
import CompassButton from '../components/map/CompassButton.vue'
import ContextualGuideCard from '../components/ContextualGuideCard.vue'
import DiamondMap from '../components/map/DiamondMap.vue'
import FinalEssayWindow from '../components/settlement/FinalEssayWindow.vue'
import RoundArticleWindow from '../components/RoundArticleWindow.vue'
import RecipeBookModal from '../components/RecipeBookModal.vue'
import SettlementModal from '../components/settlement/SettlementModal.vue'
import TravelNoteModal from '../components/settlement/TravelNoteModal.vue'
import AdvDialogue from '../components/story/AdvDialogue.vue'
import TutorialSpotlight from '../components/TutorialSpotlight.vue'
import { useCreationFlowStore } from '../stores/creationFlow'
import { useGameStore } from '../stores/game'
import { useGameRuntimeStore } from '../stores/gameRuntime'
import { useMaterialStore } from '../stores/material'
import { useWorkbenchStore } from '../stores/workbench'
import { useAchievementStore as getAchievementStore } from '../stores/achievements'
import { fetchRandomAIArticle } from '../services/articleService'
import { getQuadrantName, isNonZeroVector, VECTOR_EPSILON } from '../types/mapTypes'
import { getStoryScript } from '../game/story'
import { RANDOM_EVENT_TYPE_LABEL } from '../game/events'
import { useTutorial } from '../game/tutorial/useTutorial'
import { buildFinalJourneySummary } from '../game/write/summary'
import { useWriteEssay } from '../game/write/useWriteEssay'
import { fetchZhihuUserProfile, type ZhihuUserProfile } from '../services/zhihuAuthService'

import { achievementSystemIcon } from '../data/achievementIcons'
import { getKanshanRandomEventExpression } from '../data/kanshanExpressions'
// [art-assets disabled]
const articleSystemImg = ''
const backpackImg = ''
const desertArtwork = ''
const glacierArtwork = ''
const oceanArtwork = ''
const volcanoArtwork = ''
const mapBgm = ''
import { AUDIO_VOLUME, playBgm, stopBgm } from '../services/audioManager'

const gameStore = useGameStore()
const route = useRoute()
const router = useRouter()
const gameRuntimeStore = useGameRuntimeStore()
const creationFlowStore = useCreationFlowStore()
const materialStore = useMaterialStore()
const workbenchStore = useWorkbenchStore()
const achievementStore = getAchievementStore()

// 知乎用户资料（登录后显示昵称/头像）
const zhihuProfile = ref<ZhihuUserProfile | null>(null)
const zhihuProfileLoaded = ref(false)

async function loadZhihuProfile() {
  if (zhihuProfileLoaded.value) return
  try {
    zhihuProfile.value = await fetchZhihuUserProfile()
    zhihuProfileLoaded.value = true
  } catch {
    // 未登录或接口失败，静默降级为本地玩家
    zhihuProfileLoaded.value = true
  }
}

onMounted(() => {
  void loadZhihuProfile()
})

const displayName = computed(() => zhihuProfile.value?.fullname ?? '刘看山 · 本地玩家')
const displayAvatar = computed(() => zhihuProfile.value?.avatar_path ?? '')

const showBackpack = ref(false)
const showAchievement = ref(false)
const showFinalEssay = ref(false)
const showArticleOverlay = ref(false)
const isLoadingNewArticle = ref(false)
const compassRef = ref<InstanceType<typeof CompassButton> | null>(null)
const isStartingJourney = ref(false)
const achievementIconPulse = ref(false)
const newlyViewedAchievementIds = ref<string[]>([])
const writeEssay = useWriteEssay()
let achievementPulseTimer: ReturnType<typeof window.setTimeout> | undefined
let achievementFeedbackTimer: ReturnType<typeof window.setTimeout> | undefined

const hasUnseenAchievements = computed(() => achievementStore.hasUnseenUnlocks)

const showTravelNote = computed(() => gameStore.screen === 'round-intro')
const showRandomEvent = computed(() => gameStore.screen === 'random-event' && gameStore.currentRandomEventId !== null)
const showArticleGenBubble = computed(() => gameStore.screen === 'article-gen')
const showRoundArticleWindow = ref(false)
const showRecipeBook = ref(false)
/** v5: 结算弹窗关闭后自动触发知北针动画 */
const pendingCompassStart = ref(false)
const currentEvent = computed(() => gameStore.currentRandomEvent)
const randomEventExpression = computed(() => getKanshanRandomEventExpression(currentEvent.value))
// 剧情脚本由 stores/game.ts 在 continueJourney() 里解析（AI 生成 / A 版降级），
// 这里只读 activeStoryScript，不再依赖本地注册表能否查到 storyId。
const storyScript = computed(() => gameStore.activeStoryScript)
const isStoryEvent = computed(() => currentEvent.value?.type === 'D' && storyScript.value !== null)

// 开场 ADV 介绍：只在第 1 局、且玩家还没看过时弹出。
// 不复用 tutorialSeen（那是聚光灯教学的毕业标记），两个语义独立持久化。
// 本来由事件 d_tutorial_first_round 承载，但 drawRandomEvent 只在局间结算后调用，
// 而它的守卫又要求 currentRound <= 1，两者永不同时成立，所以改回在这里直挂。
const showTutorialIntro = computed(() => gameStore.currentRound === 1 && gameStore.needsTutorialIntro)
const tutorialIntroScript = computed(() => getStoryScript('tutorial_first_round') ?? null)

function handleTutorialIntroComplete() {
  gameStore.markTutorialIntroSeen()
}

const isGameOver = computed(() => gameStore.isGameOver)
const currentVectorMatchesCommitted = computed(() => {
  const committed = gameStore.roundVector
  const preview = workbenchStore.currentVector
  if (!committed || !isNonZeroVector(preview)) return false
  return Math.hypot(preview[0] - committed[0], preview[1] - committed[1]) <= VECTOR_EPSILON
})
const compassPendingVector = computed<[number, number] | null>(() => (
  (gameStore.screen === 'map-ready' || gameStore.screen === 'map-moving')
    && currentVectorMatchesCommitted.value
    && gameStore.roundVector
    ? gameStore.roundVector
    : null
))
const canStartJourney = computed(() => (
  gameStore.isMapReady
    && currentVectorMatchesCommitted.value
    && !gameStore.mountainPosition.isMoving
    && !isStartingJourney.value
))
const {
  currentGuide,
  guideCardGuide,
  guideCardVisible,
  isGraduated,
  mandatoryTutorialActive,
  lockArticleClose,
  dismissCurrentHint,
  openManualGuide,
  persistentMapGuideVisible,
} = useTutorial({ departureReady: canStartJourney })
// 开场 ADV 播放期间不叠加聚光灯，避免两层引导同时压在屏幕上
const showTutorialSpotlight = computed(() => mandatoryTutorialActive.value && !showTutorialIntro.value)

const finalJourneySummary = computed(() => buildFinalJourneySummary({
  stats: achievementStore.stats,
  definitions: achievementStore.definitions,
  states: achievementStore.achievementStates,
  finalRegion: getQuadrantName(gameStore.finalQuadrant),
  finalPosition: {
    row: gameStore.mountainPosition.row,
    col: gameStore.mountainPosition.col,
  },
  finalHeat: gameStore.totalVector[0],
  finalSalt: gameStore.totalVector[1],
  roundHistory: gameStore.moveHistory,
}))

function clearRoundWorkspace() {
  creationFlowStore.clear()
  workbenchStore.clearWorkbench()
  workbenchStore.currentVector = [0, 0]
}

function clearWorkspace() {
  clearRoundWorkspace()
  materialStore.clearMaterials()
}

function handleCompassMovementStart() {
  // v5: 知北针动画开始时才清除工作区（此前知北针还需要 currentVector 匹配）
  clearRoundWorkspace()
  gameStore.beginCompassMovement()
}

function handleCompassMovementComplete() {
  gameStore.finalizeMovement()
  isStartingJourney.value = false
}

function handleJourneyAnimationStarted() {
  isStartingJourney.value = true
}

function resetFinalEssay() {
  showFinalEssay.value = false
  writeEssay.resetWriting()
}

function handleStartJourney() {
  if (!canStartJourney.value) return
  compassRef.value?.startJourney()
}

function handleDepart() {
  if (isGameOver.value) {
    resetFinalEssay()
    clearWorkspace()
    gameStore.resetGame()
  }
  gameStore.beginRoundIntro()
}

function handleWorkspaceSubmitted() {
  showBackpack.value = false
  // 步骤 3 完成由 showBackpack watch 处理（背包关闭后推进到步骤 4）
}

function openAchievementPanel() {
  newlyViewedAchievementIds.value = achievementStore.unseenAchievements.map(achievement => achievement.id)
  achievementStore.markAllAchievementsSeen()
  showAchievement.value = true
  if (achievementFeedbackTimer !== undefined) window.clearTimeout(achievementFeedbackTimer)
  achievementFeedbackTimer = window.setTimeout(() => {
    newlyViewedAchievementIds.value = []
    achievementFeedbackTimer = undefined
  }, 760)
}

function closeAchievementPanel() {
  showAchievement.value = false
  newlyViewedAchievementIds.value = []
  if (achievementFeedbackTimer !== undefined) {
    window.clearTimeout(achievementFeedbackTimer)
    achievementFeedbackTimer = undefined
  }
}

function handleTravelNoteContinue() {
  gameStore.openArticle()
  openArticleOverlay()
}

function handleTravelNoteSkip() {
  gameStore.screen = 'map'
  gameStore.persist()
}

function handleSettlementContinue() {
  // v5: 不立即清除工作区，设置标记等结算弹窗关闭后自动触发知北针
  
  // 【关键修复】无论是否有知北针动画，都要先记录成就
  // 因为知北针动画可能被跳过或失败
  
  // 【重要】使用 gameStore 中保存的卡牌快照，而不是从 materialStore 或 localStorage 查找
  // 因为 materialStore 会在每局开始时被 clearMaterials() 清空
  const committedMaterials = gameStore.committedMaterialsSnapshot
  
  if (import.meta.env.DEV) {
    console.log('[handleSettlementContinue] 准备记录成就')
    console.log('  currentRound:', gameStore.currentRound)
    console.log('  committedMaterialIds:', gameStore.committedMaterialIds)
    console.log('  committedMaterialIds数量:', gameStore.committedMaterialIds.length)
    console.log('  committedMaterialsSnapshot:', committedMaterials.length, '张')
    
    // 检查每个卡牌
    committedMaterials.forEach((material: any) => {
      console.log('  - ID:', material.id)
      console.log('    type:', material.type)
    })
  }
  
  const achievementStore = getAchievementStore()
  achievementStore.recordCommittedMaterialUsage(committedMaterials)
  achievementStore.recordRoundCompleted(gameStore.currentRound, gameStore.roundVector ?? [0, 0])
  
  pendingCompassStart.value = true
}

function handleRoundArticleDone() {
  showRoundArticleWindow.value = false
  gameStore.completeArticleGeneration()
}

function handleRoundArticleSkip() {
  showRoundArticleWindow.value = false
  gameStore.skipArticleGeneration()
}

function handleResolveRandomEvent() {
  gameStore.resolveRandomEvent()
}

function handleStoryComplete() {
  gameStore.currentStoryId = null
  gameStore.currentStoryScript = null
  gameStore.resolveRandomEvent()
}

function handleForceInit() {
  resetFinalEssay()
  gameStore.forceInitGame()
  materialStore.clearMaterials()
  workbenchStore.clearWorkbench()
  creationFlowStore.clear()
  showBackpack.value = false
  showAchievement.value = false
  showArticleOverlay.value = false
}

// ── 文章覆盖层 ──
async function openArticleOverlay() {
  // 安全守卫：确保卡槽监听已安装（onMounted 已调用，此处为幂等重入保护）。
  // setupSlotSync 内部有防重复守卫，多次调用安全。
  workbenchStore.setupSlotSync()

  // 如果还没有文章，先加载一篇
  if (!gameStore.article) {
    try {
      const loadedArticle = await fetchRandomAIArticle()
      if (loadedArticle) {
        gameStore.setArticle(loadedArticle)
        gameStore.recordSeenArticle(loadedArticle.id)
        gameRuntimeStore.startRound(loadedArticle)
      }
    } catch (error) {
      console.error('[MapView] 文章加载失败:', error)
      return
    }
  }
  gameStore.openArticle()
  showArticleOverlay.value = true
}

function handleArticleOverlayClose() {
  // 首次教学期的采集门禁由 ArticleOverlay 的 lockClose 从源头挡住，
  // 这里不需要再判断教程步骤；引导内容会随 currentContext 自动跟随。
  showArticleOverlay.value = false
  gameRuntimeStore.stopRound()
  // 故意不调用 workbenchStore.stopSlotSync()：卡槽监听需要跨文章页保持安装，
  // 关闭时卸载会导致回到合成页后知北针不再转动。
}

/** 文章页背包按钮 → 关闭文章，打开地图页背包/工作台 */
function handleArticleBackpackToWorkbench() {
  showArticleOverlay.value = false
  gameRuntimeStore.stopRound()
  gameStore.completeReading()
  // 打开地图页背包
  showBackpack.value = true
}

async function handleFindMoreNotes() {
  if (isLoadingNewArticle.value) return
  isLoadingNewArticle.value = true
  try {
    const newArticle = await fetchRandomAIArticle(gameStore.seenArticleIds)
    if (!newArticle) throw new Error('没有可用的AI文章')
    gameStore.setArticle(newArticle)
    gameStore.recordSeenArticle(newArticle.id)
    gameRuntimeStore.startRound(newArticle)
  } catch (error) {
    console.error('[MapView] 刷新文章失败:', error)
  } finally {
    isLoadingNewArticle.value = false
  }
}

function ensureArticleLoaded() {
  if (gameStore.article) return
  void (async () => {
    try {
      const loadedArticle = await fetchRandomAIArticle()
      if (loadedArticle) {
        gameStore.setArticle(loadedArticle)
        gameStore.recordSeenArticle(loadedArticle.id)
        gameRuntimeStore.startRound(loadedArticle)
        workbenchStore.setupSlotSync()
      }
    } catch (error) {
      console.error('[MapView] 文章加载失败:', error)
    }
  })()
}

onMounted(() => {
  playBgm(mapBgm, { loop: true, volume: AUDIO_VOLUME.mapBgm })

  if (route.query.start === 'new') {
    handleForceInit()
    void router.replace({ name: 'game' })
  }

  workbenchStore.setupSlotSync()
  if (gameStore.screen === 'article') {
    ensureArticleLoaded()
    openArticleOverlay()
    return
  }

  gameStore.restoreAfterRefresh()
})

watch(() => achievementStore.unlockQueue.length, (queueLength, previousLength) => {
  if (queueLength <= previousLength) return
  achievementIconPulse.value = false
  if (achievementPulseTimer !== undefined) window.clearTimeout(achievementPulseTimer)
  requestAnimationFrame(() => {
    achievementIconPulse.value = true
    achievementPulseTimer = window.setTimeout(() => {
      achievementIconPulse.value = false
    }, 900)
  })
})

// v5: 结算弹窗关闭后自动触发知北针动画
watch(
  () => pendingCompassStart.value,
  (shouldStart) => {
    if (!shouldStart) return
    pendingCompassStart.value = false
    // 延迟一帧确保结算弹窗已关闭、DOM 已更新
    window.setTimeout(() => {
      if (canStartJourney.value) {
        compassRef.value?.startJourney()
      }
    }, 100)
  },
)

onBeforeUnmount(() => {
  stopBgm(mapBgm)
  workbenchStore.stopSlotSync()
  if (achievementPulseTimer !== undefined) window.clearTimeout(achievementPulseTimer)
  if (achievementFeedbackTimer !== undefined) window.clearTimeout(achievementFeedbackTimer)
})
</script>

<template>
  <div class="map-view-root">
    <div class="map-environment" aria-hidden="true">
      <div class="map-environment__region map-environment__region--ocean">
        <img :src="oceanArtwork" alt="" />
      </div>
      <div class="map-environment__region map-environment__region--glacier">
        <img :src="glacierArtwork" alt="" />
      </div>
      <div class="map-environment__region map-environment__region--volcano">
        <img :src="volcanoArtwork" alt="" />
      </div>
      <div class="map-environment__region map-environment__region--desert">
        <img :src="desertArtwork" alt="" />
      </div>
      <div class="map-environment__center-blend" />
    </div>

    <DiamondMap
      class="map-grid-stage"
      :mountain-position="gameStore.mountainPosition"
      :visited-quadrants="gameStore.visitedQuadrants"
      :show-article-bubble="showArticleGenBubble"
      @article-bubble-click="showRoundArticleWindow = true"
    />

    <div class="corner-top-left hud-map-card">
      <div class="player-profile" v-if="displayAvatar">
        <img :src="displayAvatar" alt="" class="player-avatar" />
        <span class="player-name">{{ displayName }}</span>
      </div>
      <span v-else class="player-name">{{ displayName }}</span>
      <div class="answerer-bar-wrap">
        <span class="answerer-label">答主值</span>
        <div class="answerer-bar" role="progressbar" aria-label="答主值" :aria-valuenow="gameStore.answererValue">
          <div class="answerer-bar-fill" :style="{ width: `${Math.min(gameStore.answererValue, 100)}%` }" />
        </div>
        <span class="answerer-value">{{ gameStore.answererValue }}</span>
      </div>
      <button class="init-reset-btn" type="button" title="强制初始化游戏" @click="handleForceInit">↻</button>
    </div>

    <div class="corner-top-right">
      <button
        class="hud-map-icon achievement-entry-btn"
        :class="{ 'hud-map-icon--achievement-pulse': achievementIconPulse }"
        type="button"
        title="成就系统"
        :aria-label="hasUnseenAchievements ? '打开成就系统，有新的未读成就' : '打开成就系统'"
        @click="openAchievementPanel"
      >
        <img :src="achievementSystemIcon" alt="成就" class="corner-icon" />
        <span v-if="hasUnseenAchievements" class="achievement-unseen-indicator" aria-label="有新的未读成就">✦</span>
      </button>
      <!-- 首次教学期隐藏，避免玩家一键绕过聚光灯教程 -->
      <button
        v-if="isGraduated"
        class="guide-help-btn"
        type="button"
        title="打开旅行指南"
        aria-label="打开旅行指南"
        @click="openManualGuide"
      >
        <span aria-hidden="true">?</span>
        <small>指南</small>
      </button>
    </div>

    <div class="corner-bottom-left-stack">
      <button class="hud-map-icon article-system-btn" type="button" title="阅读笔记" aria-label="打开文章阅读" @click="openArticleOverlay">
        <img :src="articleSystemImg" alt="文章" class="corner-icon" />
      </button>
      <button class="hud-map-icon" type="button" title="背包与创作流" aria-label="打开背包与创作流" data-tutorial-backpack @click="showBackpack = true">
        <img :src="backpackImg" alt="背包" class="corner-icon" />
      </button>
    </div>

    <div class="corner-bottom-right">
      <CompassButton
        ref="compassRef"
        :pending-move-vector="compassPendingVector"
        @animation-started="handleJourneyAnimationStarted"
        @movement-start="handleCompassMovementStart"
        @movement-complete="handleCompassMovementComplete"
      />
      <span class="compass-status" :class="`compass-status--${gameStore.screen}`" aria-live="polite">
        <template v-if="gameStore.screen === 'map-ready' && currentVectorMatchesCommitted">知北针已就绪 · 等待出发</template>
        <template v-else-if="gameStore.screen === 'map-ready'">素材组合已变化 · 请重新激活知北针</template>
        <template v-else-if="gameStore.screen === 'map-moving'">看山正在移动…</template>
        <template v-else-if="gameStore.screen === 'map-needs-vector'">知北针等待激活方向...</template>
        <template v-else>知北针静待</template>
      </span>
    </div>

    <div class="map-bottom-bar">
      <button
        v-if="gameStore.screen === 'map-ready' || gameStore.screen === 'map-moving' || gameStore.screen === 'article-gen'"
        class="depart-btn"
        type="button"
        :disabled="gameStore.screen === 'article-gen' ? false : !canStartJourney"
        @click.stop="gameStore.screen === 'article-gen' ? (showRoundArticleWindow = true) : handleStartJourney()"
      >
        {{ gameStore.screen === 'article-gen' ? '出发' : '出发' }}
      </button>
      <button v-else-if="gameStore.screen === 'map' || isGameOver" class="depart-btn" type="button" @click.stop="handleDepart">
        {{ isGameOver ? '重新开始' : '准备出发' }}
      </button>
      <button v-else-if="gameStore.screen === 'map-needs-vector'" class="depart-btn" type="button" disabled>
        出发
      </button>
    </div>

    <TravelNoteModal
      :visible="showTravelNote"
      :round="gameStore.currentRound"
      :total-rounds="gameStore.totalRounds"
      @continue="handleTravelNoteContinue"
      @skip="handleTravelNoteSkip"
    />

    <BackpackWindow
      :visible="showBackpack"
      @close="showBackpack = false"
      @submitted="handleWorkspaceSubmitted"
      @open-recipe-book="showRecipeBook = true"
    />

    <SettlementModal
      @continue-journey="handleSettlementContinue"
      @show-achievements="openAchievementPanel"
    />

    <FinalEssayWindow
      :visible="showFinalEssay"
      :summary="finalJourneySummary"
      @close="showFinalEssay = false"
    />

    <RoundArticleWindow
      :visible="showRoundArticleWindow"
      @done="handleRoundArticleDone"
      @skip="handleRoundArticleSkip"
    />

    <RecipeBookModal
      :visible="showRecipeBook"
      @close="showRecipeBook = false"
    />

    <!-- 随机事件弹窗（非剧情类） -->
    <Teleport to="body">
      <div v-if="showRandomEvent && !isStoryEvent" class="random-event-overlay">
        <div class="random-event-panel">
          <div class="random-event-eyebrow">旅途小插曲</div>
          <div class="random-event-type-badge">
            {{ currentEvent ? RANDOM_EVENT_TYPE_LABEL[currentEvent.type] : '事件' }}
          </div>
          <h2 class="random-event-name">{{ currentEvent?.name ?? '未知事件' }}</h2>
          <p class="random-event-desc">{{ currentEvent?.description ?? '' }}</p>
          <p v-if="gameStore.currentEventMessage" class="random-event-result">
            {{ gameStore.currentEventMessage }}
          </p>
          <div class="random-event-reaction" aria-hidden="true">
            <img :src="randomEventExpression" alt="" draggable="false" />
          </div>
          <button class="random-event-continue-btn" type="button" @click="handleResolveRandomEvent">
            继续旅行 →
          </button>
        </div>
      </div>
    </Teleport>

    <!-- 开场 ADV 介绍：首次进入游戏时看山的自我介绍 -->
    <Teleport to="body">
      <div v-if="showTutorialIntro && tutorialIntroScript" class="story-overlay">
        <AdvDialogue :script="tutorialIntroScript" @complete="handleTutorialIntroComplete" />
      </div>
    </Teleport>

    <!-- 剧情事件：ADV 对话框 -->
    <Teleport to="body">
      <div v-if="showRandomEvent && isStoryEvent" class="story-overlay">
        <AdvDialogue :script="storyScript" @complete="handleStoryComplete" />
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showAchievement" class="achievement-overlay" @click.self="closeAchievementPanel">
        <div class="achievement-dialog">
          <button class="achievement-dialog-close" type="button" aria-label="关闭成就系统" @click="closeAchievementPanel">×</button>
          <AchievementPanel :newly-viewed-ids="newlyViewedAchievementIds" />
        </div>
      </div>
    </Teleport>

    <!-- 文章全屏覆盖层 -->
    <ArticleOverlay
      v-if="showArticleOverlay && gameStore.article"
      :article="gameStore.article"
      :is-loading="isLoadingNewArticle"
      :lock-close="lockArticleClose"
      @close="handleArticleOverlayClose"
      @find-more="handleFindMoreNotes"
      @open-map-backpack="handleArticleBackpackToWorkbench"
    />

    <!-- 首次教学期：遮罩聚光灯（Teleport 到 body 确保在所有覆盖层之上） -->
    <Teleport to="body">
      <TutorialSpotlight v-if="showTutorialSpotlight" :guide="currentGuide" />
    </Teleport>

    <!-- 毕业后：右上角非强制引导卡 -->
    <ContextualGuideCard
      :guide="guideCardGuide"
      :visible="guideCardVisible"
      :persistent="persistentMapGuideVisible"
      @dismiss="dismissCurrentHint"
    />
  </div>
</template>

<style scoped>
.map-view-root {
  position: relative;
  width: 100%;
  height: 100vh;
  min-height: 560px;
  overflow: hidden;
  isolation: isolate;
  background:
    radial-gradient(circle at 50% 50%, rgba(10, 39, 48, 0.12) 0 27%, rgba(4, 16, 23, 0.7) 78%),
    #071820;
}
.map-environment { position: absolute; z-index: 0; inset: 0; overflow: hidden; pointer-events: none; }
.map-environment__region { position: absolute; overflow: hidden; opacity: 0.94; }
.map-environment__region img { width: 100%; height: 100%; object-fit: cover; filter: saturate(1.05) contrast(1.03); }
.map-environment__region--ocean {
  top: -28%; left: -6%; width: 112%; height: 78%;
  -webkit-mask-image: radial-gradient(ellipse 78% 104% at 50% 0, #000 0 38%, rgba(0, 0, 0, 0.82) 56%, rgba(0, 0, 0, 0.32) 74%, transparent 92%);
  mask-image: radial-gradient(ellipse 78% 104% at 50% 0, #000 0 38%, rgba(0, 0, 0, 0.82) 56%, rgba(0, 0, 0, 0.32) 74%, transparent 92%);
}
.map-environment__region--glacier {
  top: -10%; bottom: -10%; left: -20%; width: 66%;
  -webkit-mask-image: radial-gradient(ellipse 104% 78% at 0 50%, #000 0 38%, rgba(0, 0, 0, 0.82) 56%, rgba(0, 0, 0, 0.32) 74%, transparent 92%);
  mask-image: radial-gradient(ellipse 104% 78% at 0 50%, #000 0 38%, rgba(0, 0, 0, 0.82) 56%, rgba(0, 0, 0, 0.32) 74%, transparent 92%);
}
.map-environment__region--volcano {
  top: -10%; right: -20%; bottom: -10%; width: 66%;
  -webkit-mask-image: radial-gradient(ellipse 104% 78% at 100% 50%, #000 0 38%, rgba(0, 0, 0, 0.82) 56%, rgba(0, 0, 0, 0.32) 74%, transparent 92%);
  mask-image: radial-gradient(ellipse 104% 78% at 100% 50%, #000 0 38%, rgba(0, 0, 0, 0.82) 56%, rgba(0, 0, 0, 0.32) 74%, transparent 92%);
}
.map-environment__region--desert {
  bottom: -28%; left: -6%; width: 112%; height: 78%;
  -webkit-mask-image: radial-gradient(ellipse 78% 104% at 50% 100%, #000 0 38%, rgba(0, 0, 0, 0.82) 56%, rgba(0, 0, 0, 0.32) 74%, transparent 92%);
  mask-image: radial-gradient(ellipse 78% 104% at 50% 100%, #000 0 38%, rgba(0, 0, 0, 0.82) 56%, rgba(0, 0, 0, 0.32) 74%, transparent 92%);
}
.map-environment__center-blend {
  position: absolute;
  inset: 0;
  background: none;
}
.map-grid-stage { position: relative; z-index: 2; }
.corner-top-left { transform: scale(1.1); transform-origin: top left; }
.hud-map-card {
  position: absolute;
  z-index: 10;
  top: 18px;
  left: 18px;
  min-width: 220px;
  border: 1px solid rgba(170, 133, 83, 0.62);
  border-radius: 9px;
  padding: 11px 14px;
  background: rgba(255, 248, 228, 0.93);
  box-shadow: 3px 4px 0 rgba(92, 66, 35, 0.15), 0 9px 20px rgba(72, 57, 37, 0.12);
  color: #5b4630;
  backdrop-filter: blur(3px);
}
.player-profile { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.player-avatar { width: 32px; height: 32px; border-radius: 50%; object-fit: cover; border: 2px solid rgba(170, 133, 83, 0.5); }
.player-name { display: block; margin-bottom: 8px; color: #4e3827; font: 800 0.76rem ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: 0.06em; }
.answerer-bar-wrap { display: flex; align-items: center; gap: 8px; }
.answerer-label { color: #806a4e; font: 700 0.65rem ui-monospace, SFMono-Regular, Consolas, monospace; white-space: nowrap; }
.answerer-bar { flex: 1; height: 8px; overflow: hidden; border: 1px solid rgba(166, 142, 98, 0.55); border-radius: 999px; background: #e9e0c9; }
.answerer-bar-fill { height: 100%; border-radius: inherit; background: linear-gradient(90deg, #91aa79, #d3b56b); transition: width 400ms ease; }
.answerer-value { min-width: 32px; color: #6f8b6b; font: 800 0.7rem ui-monospace, SFMono-Regular, Consolas, monospace; text-align: right; }
.init-reset-btn {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  margin-top: 8px;
  border: 1px solid rgba(170, 133, 83, 0.58);
  border-radius: 5px;
  background: #f1e4c5;
  color: #806149;
  font-size: 0.82rem;
  line-height: 1;
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease;
}
.init-reset-btn:hover { background: #e6d3a8; color: #547466; }
.corner-top-right, .corner-bottom-left-stack, .corner-bottom-right { position: absolute; z-index: 10; }
.corner-top-right { top: 18px; right: 18px; display: flex; align-items: flex-start; gap: 10px; transform: scale(1.1); transform-origin: top right; }
.corner-bottom-left-stack { bottom: 22px; left: 18px; display: flex; flex-direction: column; gap: 6px; transform: scale(1.1); transform-origin: bottom left; }
.corner-bottom-right { right: 18px; bottom: 19px; display: grid; justify-items: end; gap: 4px; transform: scale(1.1); transform-origin: bottom right; }
.hud-map-icon { display: grid; place-items: center; border: 1px solid rgba(170, 133, 83, 0.58); border-radius: 8px; padding: 4px; background: rgba(255, 248, 228, 0.92); box-shadow: 2px 3px 0 rgba(92, 66, 35, 0.14); cursor: pointer; transition: transform 150ms ease, filter 150ms ease, box-shadow 150ms ease; }
.hud-map-icon:hover { transform: translateY(-2px) scale(1.05); filter: sepia(0.08) saturate(1.06) brightness(1.04); box-shadow: 3px 4px 0 rgba(92, 66, 35, 0.18); }
.achievement-entry-btn { position: relative; width: 76px; height: 76px; padding: 1px; border: 0; background: transparent; box-shadow: none; }
.achievement-entry-btn .corner-icon { width: 84px; height: 84px; transform: translate(-4px, -4px); }
.achievement-entry-btn:hover { background: transparent; box-shadow: none; filter: brightness(1.04); }
.guide-help-btn { display: grid; min-width: 42px; min-height: 42px; place-items: center; border: 1px solid rgba(170, 133, 83, 0.62); border-radius: 8px 5px 8px 5px; padding: 4px 6px; background: rgba(255, 248, 228, 0.93); box-shadow: 2px 3px 0 rgba(92, 66, 35, 0.12); color: #6b5038; cursor: pointer; transition: transform 150ms ease, filter 150ms ease, box-shadow 150ms ease; }
.guide-help-btn:hover { transform: translateY(-2px); filter: brightness(1.04); box-shadow: 3px 4px 0 rgba(92, 66, 35, 0.16); }
.guide-help-btn span { font: 900 1.15rem/1 Georgia, serif; }
.guide-help-btn small { color: #806149; font-size: 0.52rem; font-weight: 800; letter-spacing: 0.06em; }
.hud-map-icon--achievement-pulse { animation: achievement-entry-pulse 900ms ease both; }
.corner-icon { width: 62px; height: 62px; object-fit: contain; pointer-events: none; }
.achievement-unseen-indicator { position: absolute; top: -7px; right: -7px; display: grid; place-items: center; width: 19px; height: 19px; border: 1px solid rgba(253, 221, 134, 0.9); border-radius: 50%; background: #315e60; box-shadow: 0 0 0 2px rgba(7, 24, 32, 0.78), 0 0 12px rgba(255, 210, 106, 0.52); color: #ffe39a; font-size: 0.75rem; line-height: 1; }
.compass-status { display: inline-block; border: 1px solid rgba(170, 133, 83, 0.48); border-radius: 999px; padding: 5px 8px; background: rgba(255, 248, 228, 0.84); box-shadow: 1px 2px 0 rgba(92, 66, 35, 0.1); color: #806a50; font: 700 0.62rem ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: 0.04em; text-shadow: none; }
.compass-status--map-ready { color: #527c6c; }
.compass-status--map-moving { color: #9b7443; }
.map-bottom-bar { position: absolute; z-index: 9; right: 0; bottom: 0; left: 0; display: flex; align-items: end; justify-content: flex-end; gap: 18px; padding: 0 150px 20px 0; pointer-events: none; transform: scale(1.1); transform-origin: bottom right; }
.depart-btn { pointer-events: auto; border: 2px solid #c39b61; border-radius: 8px 4px 8px 4px; padding: 10px 25px; background: #6e9b8c; box-shadow: 3px 4px 0 rgba(77, 67, 45, 0.2); color: #fff9e9; font: 800 0.76rem ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: 0.08em; cursor: pointer; transition: transform 90ms ease, background 150ms ease, box-shadow 150ms ease; }
.depart-btn:hover { transform: translate(-1px, -2px); background: #83aa99; box-shadow: 4px 5px 0 rgba(77, 67, 45, 0.2); }
.depart-btn:disabled { border-color: #b9af9c; background: #e2dccd; box-shadow: 2px 2px 0 rgba(77, 67, 45, 0.12); color: #8b8377; cursor: not-allowed; transform: none; }
.achievement-overlay { position: fixed; z-index: 120; inset: 0; display: grid; place-items: center; padding: 20px; background: rgba(3, 12, 18, 0.76); backdrop-filter: blur(5px); }
.achievement-dialog { position: relative; width: min(980px, calc(100vw - 40px)); max-height: calc(100vh - 40px); }
.achievement-dialog :deep(.achievement-tree-panel) { max-height: calc(100vh - 40px); overflow: auto; }
.achievement-dialog :deep(.achievement-panel) { width: 100%; margin: 0; }
.achievement-dialog-close { position: absolute; z-index: 2; top: 8px; right: 8px; width: 30px; height: 30px; border: 1px solid rgba(224, 255, 249, 0.4); background: rgba(4, 20, 28, 0.7); color: #d8f6ef; cursor: pointer; }
@keyframes achievement-entry-pulse {
  0% { filter: brightness(1); }
  35% { filter: brightness(1.35) drop-shadow(0 0 8px rgba(255, 214, 111, 0.75)); }
  100% { filter: brightness(1); }
}

/* ── 随机事件弹窗 ── */
.random-event-overlay {
  position: fixed;
  z-index: 110;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(65, 49, 36, 0.48);
  backdrop-filter: blur(5px);
}
.random-event-panel {
  max-width: 420px;
  width: 100%;
  padding: 26px 24px 22px;
  border: 1px solid rgba(158, 120, 75, 0.72);
  border-radius: 15px 8px 15px 8px;
  background: radial-gradient(circle at 14% 12%, rgba(255, 255, 255, 0.56), transparent 28%), linear-gradient(145deg, #f8f0dc, #eee0c1);
  box-shadow: 0 16px 34px rgba(65, 48, 31, 0.22), 4px 5px 0 rgba(111, 79, 42, 0.14), inset 0 0 0 1px rgba(255, 255, 255, 0.5);
  color: #5d4834;
  text-align: center;
}
.random-event-eyebrow {
  margin-bottom: 7px;
  color: #96764b;
  font: 800 0.61rem/1 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.16em;
}
.random-event-type-badge {
  display: inline-block;
  padding: 5px 12px;
  margin-bottom: 10px;
  border: 1px solid rgba(151, 112, 66, 0.52);
  border-radius: 999px;
  background: rgba(232, 207, 157, 0.58);
  color: #795a36;
  font: 800 0.64rem/1 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.08em;
}
.random-event-name {
  margin: 0 0 10px;
  color: #523b27;
  font: 800 clamp(1.25rem, 3vw, 1.55rem)/1.25 'Noto Serif SC', 'Songti SC', serif;
  letter-spacing: 0.05em;
}
.random-event-desc {
  margin: 0 0 8px;
  color: #735e48;
  font: 0.82rem/1.7 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
}
.random-event-result {
  margin: 12px 0 16px;
  padding: 9px 11px;
  border: 1px solid rgba(113, 143, 101, 0.38);
  border-radius: 8px;
  background: rgba(207, 224, 183, 0.42);
  color: #55725b;
  font: 700 0.75rem/1.45 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
}
.random-event-reaction {
  display: flex;
  min-height: 62px;
  align-items: center;
  justify-content: flex-end;
  margin: -3px 2px 1px;
  pointer-events: none;
}
.random-event-reaction img { display: block; width: 68px; height: 68px; object-fit: contain; }
.random-event-continue-btn {
  margin-top: 5px;
  border: 1px solid #5f836c;
  border-radius: 9px 4px 9px 4px;
  padding: 10px 22px;
  background: #789b82;
  box-shadow: 3px 4px 0 rgba(79, 92, 65, 0.2);
  color: #fff8e5;
  font: 800 0.76rem/1 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
  letter-spacing: 0.06em;
  cursor: pointer;
  transition: transform 120ms ease, background 150ms ease, box-shadow 120ms ease;
}
.random-event-continue-btn:hover {
  transform: translateY(-2px);
  background: #6b9076;
  box-shadow: 4px 5px 0 rgba(79, 92, 65, 0.22);
}
.random-event-continue-btn:focus-visible {
  outline: 2px solid #c59d61;
  outline-offset: 3px;
}

/* ── 剧情事件全屏遮罩 ── */
.story-overlay {
  position: fixed;
  z-index: 115;
  inset: 0;
}

@media (max-width: 720px) {
  .map-view-root { min-height: 480px; }
  .hud-map-card { top: 10px; left: 10px; min-width: 184px; padding: 8px 10px; }
  .corner-top-right { top: 10px; right: 10px; gap: 8px; }
  .corner-bottom-left-stack { bottom: 12px; left: 10px; }
  .corner-bottom-right { right: 10px; bottom: 10px; }
  .corner-icon { width: 50px; height: 50px; }
  .achievement-entry-btn { width: 62px; height: 62px; }
  .achievement-entry-btn .corner-icon { width: 70px; height: 70px; transform: translate(-4px, -4px); }
  .map-bottom-bar { padding: 0 112px 12px 0; }
  .depart-btn { padding: 8px 13px; }
  .map-environment__region--ocean, .map-environment__region--desert { left: -10%; width: 120%; }
  .map-environment__region--glacier, .map-environment__region--volcano { width: 78%; }
}
</style>
