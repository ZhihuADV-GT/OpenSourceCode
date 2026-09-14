/**
 * 新手引导 — 状态推导与双轨呈现
 *
 * 唯一事实来源是 currentContext：完全由游戏状态推导，不含任何计数器，
 * 因此不需要手动推进、不会因瞬时状态误判而卡死。
 *
 * 同一份 guide 数据驱动两种呈现，按生命周期互斥：
 * - 首次教学期（tutorialSeen === false）：TutorialSpotlight 遮罩聚光灯，强引导
 * - 毕业之后（tutorialSeen === true）：ContextualGuideCard 角落卡片，可跳过/可关闭
 */

import { computed, ref, watch, type Ref } from 'vue'
import { useCreationFlowStore } from '../../stores/creationFlow'
import { useGameStore } from '../../stores/game'
import { useMaterialStore } from '../../stores/material'
import { useWorkbenchStore } from '../../stores/workbench'
import { isNonZeroVector } from '../../types/mapTypes'

export type TutorialContext =
  | 'READING'
  | 'COLLECT_MATERIAL'
  | 'DRAG_TO_FLOW'
  | 'ACTIVATE_COMPASS'
  | 'DEPART'
  | 'ADJUST_ZERO_VECTOR'

export interface TutorialGuide {
  id: TutorialContext
  text: string
  suggestion: string
  speaker: string
  /**
   * 聚光灯高亮锚点候选，按优先级取第一个存在于 DOM 中的。
   * 用候选数组而非单一选择器，是为了让「背包开着就指工作台、没开就指背包图标」
   * 这类切换由 DOM 探测自然完成，无需额外的展开状态。
   */
  targets: readonly string[]
}

export const TUTORIAL_GUIDES: Readonly<Record<TutorialContext, TutorialGuide>> = {
  READING: {
    id: 'READING',
    text: '点击书本图标，看看看山拾到的旅行笔记，收集一些素材吧。',
    suggestion: '建议：阅读',
    speaker: '看山',
    targets: ['.article-system-btn'],
  },
  COLLECT_MATERIAL: {
    id: 'COLLECT_MATERIAL',
    text: '在文章中用鼠标选中一段文字，我会帮你判断它是否有价值。',
    suggestion: '建议：划线采集素材',
    speaker: '看山',
    targets: ['.book-stage'],
  },
  DRAG_TO_FLOW: {
    id: 'DRAG_TO_FLOW',
    text: '把背包中的素材拖进创作流，组合这次旅行的方向。',
    suggestion: '建议：拖卡进创作流',
    speaker: '看山',
    targets: ['[data-tutorial-workbench]', '[data-tutorial-backpack]'],
  },
  ACTIVATE_COMPASS: {
    id: 'ACTIVATE_COMPASS',
    text: '素材已经准备好了，试试“激活知北针”。',
    suggestion: '建议：激活知北针',
    speaker: '看山',
    targets: ['.creation-submit-button'],
  },
  DEPART: {
    id: 'DEPART',
    text: '方向已经确定，现在可以出发了。',
    suggestion: '建议：出发',
    speaker: '看山',
    targets: ['.map-bottom-bar'],
  },
  ADJUST_ZERO_VECTOR: {
    id: 'ADJUST_ZERO_VECTOR',
    text: '这次还没有形成明确方向，可以调整素材组合后再试一次。',
    suggestion: '建议：继续编辑创作流',
    speaker: '看山',
    targets: ['[data-tutorial-workbench]'],
  },
}

interface UseTutorialOptions {
  /** The same readiness computed by MapView that controls the real 出发 button. */
  departureReady: Readonly<Ref<boolean>>
}

const MAP_GUIDANCE_SCREENS = new Set([
  'map',
  'map-needs-vector',
  'map-ready',
])

export function useTutorial({ departureReady }: UseTutorialOptions) {
  const gameStore = useGameStore()
  const materialStore = useMaterialStore()
  const creationFlowStore = useCreationFlowStore()
  const workbenchStore = useWorkbenchStore()
  const manualGuideOpen = ref(false)
  const persistentMapGuideDismissed = ref(false)

  /** 首次教学期：聚光灯强引导生效，角落卡片与「旅行指南」按钮不出现 */
  const isFirstRunTutorial = computed(() => !gameStore.tutorialSeen)
  /** 已毕业：只剩非强制的角落卡片 */
  const isGraduated = computed(() => gameStore.tutorialSeen)

  const currentContext = computed<TutorialContext | null>(() => {
    const screen = gameStore.screen

    // 文章阅读页是流程中的一站而非旁支：还没采到素材时就地提示划线，
    // 采到之后返回 null，等玩家回到地图再由下面的链路接管。
    if (screen === 'article') {
      return materialStore.materials.length === 0 ? 'COLLECT_MATERIAL' : null
    }

    if (!MAP_GUIDANCE_SCREENS.has(screen)) return null
    if (materialStore.materials.length === 0) return 'READING'
    if (creationFlowStore.filledCount === 0) return 'DRAG_TO_FLOW'

    // The departure control and this branch share the same readiness value.
    // This prevents the guide from saying “可以出发” while the button is disabled.
    if (departureReady.value) return 'DEPART'
    if (isNonZeroVector(workbenchStore.currentVector)) {
      return 'ACTIVATE_COMPASS'
    }
    return 'ADJUST_ZERO_VECTOR'
  })

  const currentGuide = computed<TutorialGuide | null>(() => {
    const context = currentContext.value
    return context ? TUTORIAL_GUIDES[context] : null
  })

  /**
   * 首次教学期的硬门禁：采集素材之前不允许离开文章页。
   * 这是全流程唯一一处功能性强制，聚光灯遮罩本身是 pointer-events: none 的纯视觉引导。
   */
  const lockArticleClose = computed(() => (
    isFirstRunTutorial.value && currentContext.value === 'COLLECT_MATERIAL'
  ))

  const dismissedForCurrentRound = computed(() => {
    const context = currentContext.value
    if (!context) return false
    return (gameStore.tutorialDismissedContextByRound[String(gameStore.currentRound)] ?? [])
      .includes(context)
  })

  const skippedForCurrentRound = computed(() => (
    gameStore.tutorialSkippedRoundNumbers.includes(gameStore.currentRound)
  ))

  const automaticGuideVisible = computed(() => (
    gameStore.currentRound === 1
      && currentGuide.value !== null
      && gameStore.tutorialAutoGuideEnabled
      && !skippedForCurrentRound.value
      && !dismissedForCurrentRound.value
  ))

  const isMapGuideScreen = computed(() => (
    MAP_GUIDANCE_SCREENS.has(gameStore.screen) || gameStore.screen === 'map-moving'
  ))
  /**
   * 毕业后保留一张地图入口引导卡，直到玩家明确点击右上角 X。
   * 本地 ref 负责阻止同一页面内的自动回显，不引入新的存档字段，
   * 也不让历史上的「知道了」记录影响这张新的持久卡片。
   */
  const persistentMapGuideVisible = computed(() => (
    isGraduated.value
      && isMapGuideScreen.value
      && !persistentMapGuideDismissed.value
  ))
  const mandatoryTutorialActive = computed(() => (
    gameStore.currentRound === 1
      && isFirstRunTutorial.value
      && currentGuide.value !== null
  ))
  const manualMapGuideVisible = computed(() => (
    isGraduated.value && isMapGuideScreen.value && manualGuideOpen.value
  ))
  const guideCardGuide = computed(() => (
    mandatoryTutorialActive.value
      ? currentGuide.value
      : persistentMapGuideVisible.value || manualMapGuideVisible.value
      ? TUTORIAL_GUIDES.READING
      : currentGuide.value
  ))
  // 强制教程优先于手动/持久卡片；教程完成后才进入地图引导卡逻辑。
  const guideCardVisible = computed(() => (
    mandatoryTutorialActive.value
      || (
        isGraduated.value
        && (
          persistentMapGuideVisible.value
          || manualMapGuideVisible.value
          || (
            !persistentMapGuideDismissed.value
            && currentGuide.value !== null
            && (manualGuideOpen.value || automaticGuideVisible.value)
          )
        )
      )
  ))
  // 保留旧返回值名称，避免其他调用方依赖变化；MapView 使用更明确的 guideCardVisible。
  const guideVisible = guideCardVisible

  function dismissCurrentHint() {
    if (mandatoryTutorialActive.value) {
      // 强制教程不使用持久卡片的 dismissal 状态；步骤仍由真实游戏状态推进。
      manualGuideOpen.value = false
      return
    }
    if (persistentMapGuideVisible.value || manualMapGuideVisible.value) {
      persistentMapGuideDismissed.value = true
      manualGuideOpen.value = false
      return
    }
    const context = currentContext.value
    if (!context) return
    gameStore.dismissTutorialContext(context)
    manualGuideOpen.value = false
  }

  function skipCurrentRound() {
    if (gameStore.currentRound === 1) gameStore.skipTutorialRound()
    manualGuideOpen.value = false
  }

  function disableAutoGuide() {
    gameStore.setTutorialAutoGuideEnabled(false)
    manualGuideOpen.value = false
  }

  function openManualGuide() {
    if (isGraduated.value && isMapGuideScreen.value) {
      persistentMapGuideDismissed.value = false
      manualGuideOpen.value = true
      return
    }
    if (currentGuide.value) manualGuideOpen.value = true
  }

  function closeManualGuide() {
    manualGuideOpen.value = false
  }

  // A guide card is contextual, not a progress counter. If the player takes
  // an unrelated action, the same dismissed context remains dismissed. When
  // a real state transition produces a new context, the new card can appear.
  watch(currentContext, context => {
    if (!context) manualGuideOpen.value = false
  })

  return {
    currentContext,
    currentGuide,
    isFirstRunTutorial,
    isGraduated,
    mandatoryTutorialActive,
    lockArticleClose,
    guideCardGuide,
    guideCardVisible,
    guideVisible,
    persistentMapGuideVisible,
    automaticGuideVisible,
    skippedForCurrentRound,
    dismissCurrentHint,
    skipCurrentRound,
    disableAutoGuide,
    openManualGuide,
    closeManualGuide,
  }
}
