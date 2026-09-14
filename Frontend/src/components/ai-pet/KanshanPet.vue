<script setup lang="ts">
/**
 * 看山桌宠 —— 点击交互模块 + 点评气泡模块
 *
 * 职责：
 * 1. 点击交互：点击看山 → 切换 GIF 动作 → 自动恢复待机
 * 2. 点评气泡：监听事件总线，划线/放卡/结算时弹出消息
 * 3. 聊天面板：委托给 KanshanChatPanel 组件
 *
 * 聊天模块（KanshanChatPanel）已拆分为独立组件。
 */
import { onBeforeUnmount, ref, computed, watch } from 'vue'
import AiPetAnalysisChart from './charts/AiPetAnalysisChart.vue'
import KanshanChatPanel from './KanshanChatPanel.vue'
import type { ChartData } from './charts/AiPetAnalysisChart.vue'
import { onKanshanBubble } from '../../services/kanshanEvents'

// [art-assets disabled]
const idleGif = ''
const greetGif = ''
const computerGif = ''
const wanderGif = ''
const sleepyGif = ''
const dribbleGif = ''


/* ===================== GIF 动作逻辑 ===================== */

/** 待机 GIF */
const IDLE_GIF: string = idleGif

/** 互动动作 GIF 列表 */
const ACTION_GIFS: string[] = [
  greetGif,
  computerGif,
  wanderGif,
  sleepyGif,
  dribbleGif,

]

/** 动作播放时长（毫秒），可通过 ref 调节 */
const actionDuration = ref<number>(5500)

/** 当前展示的 GIF 地址 */
const currentGif = ref<string>(IDLE_GIF)

/** 是否处于互动动作状态 */
const isActing = ref<boolean>(false)

/** 自动恢复待机定时器 */
let timer: ReturnType<typeof setTimeout> | null = null

/** 清理定时器 */
function clearTimer(): void {
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
}

/** 随机挑选一个动作 GIF */
function pickRandomAction(): string {
  const idx = Math.floor(Math.random() * ACTION_GIFS.length)
  return ACTION_GIFS[idx]
}

/** 播放一次互动动作（点击宠物本体 / 气泡消息时触发） */
function playAction(): void {
  clearTimer()
  currentGif.value = pickRandomAction()
  isActing.value = true

  timer = setTimeout(() => {
    currentGif.value = IDLE_GIF
    isActing.value = false
    timer = null
  }, actionDuration.value)
}

/* ===================== Props / Emits ===================== */

/** 当前向量数据（由父层通信层注入） */
const props = withDefaults(defineProps<{
  currentVector?: ChartData
  /** 是否默认显示知北针图表面板（背包内嵌时设为 true） */
  defaultShowChart?: boolean
}>(), {
  defaultShowChart: false,
})
const currentVector = computed(() => props.currentVector ?? { x: 0, y: 0 })

/* ===================== 知北针显示向量动效 ===================== */

/** 目标向量由宿主注入；显示向量独立插值，避免图表瞬间跳转。 */
const displayVector = ref<ChartData>({ ...currentVector.value })
// 角度单独保存：即使显示向量缩至零，也不能丢失上一帧的朝向。
const displayAngle = ref(Math.atan2(displayVector.value.y, displayVector.value.x))
const VECTOR_ANIMATION_DURATION = 300
const SETTLE_AMPLITUDE = 0.25
const SETTLE_DECAY = 4
const SETTLE_FREQUENCY = 14
const SETTLE_DURATION = 1200
const IDLE_AMPLITUDE = 0.08
const IDLE_DECAY = 6
const IDLE_FREQUENCY = 18
const IDLE_DURATION = 600
const IDLE_MIN_DELAY = 3000
const IDLE_MAX_DELAY = 5000
let vectorAnimationFrameId: number | null = null
let idleWobbleTimerId: ReturnType<typeof window.setTimeout> | null = null

function setDisplayVector(radius: number, angle: number): void {
  displayAngle.value = angle
  displayVector.value = {
    x: radius * Math.cos(angle),
    y: radius * Math.sin(angle),
  }
}

/** 将两角度之差归一化到 [-π, π]，保证走视觉上的最小夹角。 */
function getShortestAngleDelta(from: number, to: number): number {
  let delta = to - from
  while (delta > Math.PI) delta -= 2 * Math.PI
  while (delta < -Math.PI) delta += 2 * Math.PI
  return delta
}

function cancelVectorMotion(): void {
  if (vectorAnimationFrameId !== null) {
    cancelAnimationFrame(vectorAnimationFrameId)
    vectorAnimationFrameId = null
  }
  if (idleWobbleTimerId !== null) {
    window.clearTimeout(idleWobbleTimerId)
    idleWobbleTimerId = null
  }
}

/** 到位后以衰减正弦摆动模拟指北针回正。 */
function startSettleWobble(baseAngle: number, radius: number): void {
  const startTime = performance.now()
  const tick = (now: number) => {
    const elapsed = (now - startTime) / 1000
    const decay = Math.exp(-SETTLE_DECAY * elapsed)
    if (elapsed > SETTLE_DURATION / 1000 || decay * SETTLE_AMPLITUDE < 0.001) {
      setDisplayVector(radius, baseAngle)
      vectorAnimationFrameId = null
      scheduleIdleWobble(baseAngle, radius)
      return
    }

    const wobble = SETTLE_AMPLITUDE * Math.sin(SETTLE_FREQUENCY * elapsed) * decay
    setDisplayVector(radius, baseAngle + wobble)
    vectorAnimationFrameId = requestAnimationFrame(tick)
  }
  vectorAnimationFrameId = requestAnimationFrame(tick)
}

/** 静置一段时间后触发一次较轻的回摆，令看山指北针保持生命感。 */
function scheduleIdleWobble(baseAngle: number, radius: number): void {
  idleWobbleTimerId = window.setTimeout(() => {
    idleWobbleTimerId = null
    const startTime = performance.now()
    const tick = (now: number) => {
      const elapsed = (now - startTime) / 1000
      const decay = Math.exp(-IDLE_DECAY * elapsed)
      if (elapsed > IDLE_DURATION / 1000 || decay * IDLE_AMPLITUDE < 0.0005) {
        setDisplayVector(radius, baseAngle)
        vectorAnimationFrameId = null
        scheduleIdleWobble(baseAngle, radius)
        return
      }

      const wobble = IDLE_AMPLITUDE * Math.sin(IDLE_FREQUENCY * elapsed) * decay
      setDisplayVector(radius, baseAngle + wobble)
      vectorAnimationFrameId = requestAnimationFrame(tick)
    }
    vectorAnimationFrameId = requestAnimationFrame(tick)
  }, IDLE_MIN_DELAY + Math.random() * (IDLE_MAX_DELAY - IDLE_MIN_DELAY))
}

/** 使用旧版相同的极坐标最短路径与三次缓动插值。 */
function animateVectorTo(target: ChartData): void {
  cancelVectorMotion()

  // 从当前显示向量直接插值到新向量，不经过零向量。
  const fromRadius = Math.hypot(displayVector.value.x, displayVector.value.y)
  const fromAngle = displayAngle.value
  const targetRadius = Math.hypot(target.x, target.y)
  const rawTargetAngle = Math.atan2(target.y, target.x)
  // 长度插值：始终从 fromRadius 过渡到 targetRadius，不经过 0。
  // 角度插值：目标为零时保持原角度，避免无意义的旋转。
  const angleDelta = targetRadius < 1e-10
    ? 0
    : getShortestAngleDelta(fromAngle, rawTargetAngle)
  const targetAngle = fromAngle + angleDelta

  const startTime = performance.now()
  const tick = (now: number) => {
    const elapsed = now - startTime
    const progress = Math.min(elapsed / VECTOR_ANIMATION_DURATION, 1)
    const eased = progress < 0.5
      ? 4 * progress ** 3
      : 1 - (-2 * progress + 2) ** 3 / 2
    const radius = fromRadius + (targetRadius - fromRadius) * eased
    setDisplayVector(radius, fromAngle + angleDelta * eased)

    if (elapsed < VECTOR_ANIMATION_DURATION) {
      vectorAnimationFrameId = requestAnimationFrame(tick)
      return
    }

    // 保留已展开的 targetAngle，下一次更新仍从本次最终朝向取最短路径。
    displayAngle.value = targetAngle
    displayVector.value = { ...target }
    vectorAnimationFrameId = null
    if (targetRadius > 1e-10) startSettleWobble(targetAngle, targetRadius)
  }
  vectorAnimationFrameId = requestAnimationFrame(tick)
}

watch(currentVector, (target) => {
  animateVectorTo(target)
}, { deep: true })

const emit = defineEmits<{
  'character-click': []
  'expanded-change': [expanded: boolean]
  'module-a-click': []
}>()

/* ===================== 对话气泡（点评模块） ===================== */

/** 点击宠物时弹出的随机气泡文案 */
const CLICK_BUBBLES: string[] = [
  '嘿，有什么需要帮忙的吗？',
  '我正在观察这篇文章呢~',
  '加油，继续看下去！',
  '这里好像有些意思…',
]

/** 气泡显示文本，为空则隐藏 */
const bubbleText = ref<string>('')

let bubbleTimer: ReturnType<typeof setTimeout> | null = null

/** 点击宠物时弹出随机对话气泡，几秒后自动消失 */
function showBubble(): void {
  if (bubbleTimer !== null) {
    clearTimeout(bubbleTimer)
    bubbleTimer = null
  }
  const text = CLICK_BUBBLES[Math.floor(Math.random() * CLICK_BUBBLES.length)]
  showBubbleWithText(text, 3000)
}

/** 以指定文本显示气泡（供外部事件总线调用） */
function showBubbleWithText(text: string, duration = 3000): void {
  if (bubbleTimer !== null) {
    clearTimeout(bubbleTimer)
    bubbleTimer = null
  }
  bubbleText.value = text
  // 顺便让桌宠做个动作
  playAction()
  bubbleTimer = setTimeout(() => {
    bubbleText.value = ''
    bubbleTimer = null
  }, duration)
}

/** 保留原桌宠互动，同时通知宿主打开更完整的看山对话。 */
function handleCharacterClick(): void {
  playAction()
  showBubble()
  emit('character-click')
}

/* ===================== 聊天面板状态 ===================== */

const chatPanelRef = ref<InstanceType<typeof KanshanChatPanel> | null>(null)
const isChatExpanded = ref(false)

function handleChatExpandedChange(expanded: boolean): void {
  isChatExpanded.value = expanded
  emit('expanded-change', expanded)
}

function toggleChat(): void {
  chatPanelRef.value?.toggleExpanded()
}

/* ===================== 外置侧边工具栏回调 ===================== */

/** 预留绘图功能 A：阅读提示按钮 */
function onDrawModuleA(): void {
  emit('module-a-click')
}

/** 绘图功能 B - 指北针向量图窗口开关 */
const showChartPanel = ref(props.defaultShowChart)

function toggleChartPanel(): void {
  showChartPanel.value = !showChartPanel.value
}

/* ===================== 生命周期 ===================== */

onBeforeUnmount(() => {
  clearTimer()
  cancelVectorMotion()
  if (bubbleTimer !== null) {
    clearTimeout(bubbleTimer)
    bubbleTimer = null
  }
  unsubscribeBubble()
})

/* ===================== 事件总线：监听看山常时交互（点评模块） ===================== */

const unsubscribeBubble = onKanshanBubble((text: string) => {
  showBubbleWithText(text)
})
</script>

<template>
  <!-- 整体容器：固定在右下角 -->
  <div class="kanshan-pet-root fixed bottom-4 right-4 z-50 flex items-end">
    <!-- 外置侧边工具栏（左侧，自下而上竖向排列） -->
    <div
      v-show="!isChatExpanded"
      class="kanshan-pet-tools flex flex-col items-center gap-2 mr-2 transition-all duration-300 ease-in-out"
    >
      <!-- 按钮 3（指北针向量图）：导航箭头 Icon -->
      <button
        type="button"
        class="w-8 h-8 flex items-center justify-center rounded-lg bg-sky-500 text-white shadow-md hover:scale-110 cursor-pointer transition-transform duration-200"
        :title="showChartPanel ? '关闭知北针' : '看山知北针'"
        @click="toggleChartPanel"
      >
        <svg
          xmlns="http://w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="currentColor"
          class="w-4 h-4"
        >
          <polygon points="12,2 22,22 12,17 2,22" />
        </svg>
      </button>

      <!-- 按钮 2（中间 - 预留绘图功能 A）：灯泡 Icon -->
      <button
        type="button"
        class="w-8 h-8 flex items-center justify-center rounded-lg bg-sky-500 text-white shadow-md hover:scale-110 cursor-pointer transition-transform duration-200"
        title="看山合成建议"
        aria-label="看山合成建议"
        @click="onDrawModuleA"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="w-4 h-4"
        >
          <path d="M9 18h6" />
          <path d="M10 22h4" />
          <path d="M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z" />
        </svg>
      </button>

      <!-- 按钮 1（最下方 - 消息对话）：消息 Icon -->
      <button
        type="button"
        class="w-8 h-8 flex items-center justify-center rounded-lg bg-sky-500 text-white shadow-md hover:scale-110 cursor-pointer transition-transform duration-200"
        title="和看山聊天"
        @click="toggleChat"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="currentColor"
          class="w-4 h-4"
        >
          <path
            d="M4 3h16a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H8l-4.8 3.2A.8.8 0 0 1 2 20.4V5a2 2 0 0 1 2-2z"
          />
        </svg>
      </button>
    </div>

    <!-- 主卡片区域（含上方气泡） -->
    <div class="kanshan-pet-stage relative">
      <!-- 点评气泡：点击宠物时或在常时交互时弹出，几秒后自动消失 -->
      <div
        v-show="bubbleText && !isChatExpanded && !showChartPanel"
        class="absolute bottom-full right-0 mb-2 z-20 pointer-events-none"
      >
        <div
          class="relative bg-white text-slate-700 text-sm px-3 py-1.5 rounded-xl shadow-md max-w-[200px] text-center animate-bubble-in"
        >
          {{ bubbleText }}
          <!-- 气泡小三角 -->
          <div
            class="absolute top-full right-4 w-0 h-0"
            style="border-left: 6px solid transparent; border-right: 6px solid transparent; border-top: 6px solid white;"
          ></div>
        </div>
      </div>

      <!-- 迷你模式宠物卡片 -->
      <div
        v-show="!isChatExpanded"
        class="kanshan-pet-card kanshan-pet-card--compact select-none w-[100px] h-[100px] transition-all duration-300 ease-in-out"
      >
        <div
          class="w-full h-full flex items-center justify-center cursor-pointer transition-transform duration-200 hover:scale-105 active:scale-95"
          @click="handleCharacterClick"
        >
          <img
            :src="currentGif"
            alt="知乎看山桌宠"
            class="w-full h-full object-contain select-none pointer-events-none"
            draggable="false"
          />
        </div>
      </div>

      <!-- 图表面板浮窗：在迷你卡片正上方叠加 200x200 窗口 -->
      <div
        v-if="showChartPanel && !isChatExpanded"
        class="absolute bottom-[calc(100%+48px)] right-0 w-[200px] h-[200px] z-30"
      >
        <div class="relative w-full h-full bg-white rounded-xl shadow-lg overflow-hidden">
          <div class="absolute top-1 left-1 z-10">
            <button
              type="button"
              class="w-5 h-5 flex items-center justify-center rounded-full bg-sky-500 text-white shadow hover:bg-sky-600 transition-colors cursor-pointer"
              title="关闭知北针"
              @click.stop="toggleChartPanel"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                class="w-3 h-3"
              >
                <path d="M18 6 6 18" />
                <path d="m6 6 12 12" />
              </svg>
            </button>
          </div>
          <AiPetAnalysisChart :data="displayVector" :width="200" :height="200" />
        </div>
      </div>

      <!-- 聊天面板（独立组件） -->
      <KanshanChatPanel
        v-show="isChatExpanded"
        ref="chatPanelRef"
        @expanded-change="handleChatExpandedChange"
      />
    </div>
  </div>
</template>

<style scoped>
/* 气泡弹出动画 */
@keyframes bubble-in {
  0% {
    opacity: 0;
    transform: scale(0.6) translateY(8px);
  }
  60% {
    opacity: 1;
    transform: scale(1.05) translateY(-2px);
  }
  100% {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}
.animate-bubble-in {
  animation: bubble-in 0.35s ease-out;
}
</style>
