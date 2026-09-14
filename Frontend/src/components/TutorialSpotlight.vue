<script setup lang="ts">
/**
 * 新手教程聚光灯（首次教学期专用）
 *
 * 在目标元素周围绘制高亮遮罩 + 提示文本框。
 * 使用四个方向的暗色遮罩层拼出挖洞效果，露出目标元素；
 * 挖洞底边会在视口底部预留看山对话框的显示空间，避免对话框被挤出屏幕。
 *
 * 遮罩、脉冲环、tooltip 全部是 pointer-events: none，只做视觉聚焦不拦截操作；
 * 全流程唯一的功能性强制在 ArticleOverlay 的 lockClose 上。
 */

import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import type { TutorialGuide } from '../game/tutorial/useTutorial'

const props = defineProps<{
  guide: TutorialGuide | null
}>()

interface Rect {
  top: number
  left: number
  width: number
  height: number
}

/** 高亮挖洞与目标元素之间的间距 */
const PAD = 8
/** 视口底部为看山对话框（提示文本框）预留的高度，挖洞底边不会低于这条预留带 */
const BOTTOM_RESERVE = 150

const targetRect = ref<Rect | null>(null)
let rafId: number | null = null

/** 按优先级取第一个存在于 DOM 中的锚点 */
function resolveTarget(): Element | null {
  if (!props.guide) return null
  for (const selector of props.guide.targets) {
    const el = document.querySelector(selector)
    if (el) return el
  }
  return null
}

/** 查找目标元素并更新其位置 */
function updateTargetRect() {
  const el = resolveTarget()
  if (!el) {
    targetRect.value = null
    return
  }

  const rect = el.getBoundingClientRect()
  targetRect.value = {
    top: rect.top,
    left: rect.left,
    width: rect.width,
    height: rect.height,
  }
}

/** 持续追踪目标位置（每帧更新） */
function startTracking() {
  stopTracking()
  function tick() {
    updateTargetRect()
    rafId = requestAnimationFrame(tick)
  }
  tick()
}

function stopTracking() {
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
}

interface HoleRect {
  top: number
  left: number
  right: number
  bottom: number
}

/**
 * 高亮挖洞矩形
 * 默认紧贴目标元素；当目标位于屏幕上半部分（看山对话框将放在目标下方）时，
 * 把挖洞底边（即底部遮罩层顶部）上移到视口底部预留带之上，
 * 从而在目标元素下方腾出完整空间供看山对话框显示，不会被视口截断。
 */
const holeRect = computed<HoleRect | null>(() => {
  const r = targetRect.value
  if (!r) return null

  const top = Math.max(0, r.top - PAD)
  const left = Math.max(0, r.left - PAD)
  const right = Math.min(window.innerWidth, r.left + r.width + PAD)
  const rawBottom = Math.min(window.innerHeight, r.top + r.height + PAD)
  const minBottom = top + 80

  const dialogBelow = r.top <= window.innerHeight / 2
  const bottom = dialogBelow
    ? Math.max(minBottom, Math.min(rawBottom, window.innerHeight - BOTTOM_RESERVE))
    : Math.max(minBottom, rawBottom)

  return { top, left, right, bottom }
})

/** 看山对话框放在高亮挖洞的上方还是下方 */
const tooltipPosition = computed<'top' | 'bottom'>(() => {
  const h = holeRect.value
  if (!h) return 'bottom'
  return h.top > window.innerHeight / 2 ? 'top' : 'bottom'
})

/** tooltip 样式 */
const tooltipStyle = computed(() => {
  const h = holeRect.value
  if (!h) return { display: 'none' }

  const TOOLTIP_MAX_WIDTH = 360
  const MARGIN = 12
  const TOOLTIP_EST_HEIGHT = 120

  // 水平居中于高亮挖洞，但钳制在视口范围内
  let left = (h.left + h.right) / 2
  left = Math.max(TOOLTIP_MAX_WIDTH / 2 + MARGIN, Math.min(window.innerWidth - TOOLTIP_MAX_WIDTH / 2 - MARGIN, left))

  const style: Record<string, string> = {
    position: 'fixed',
    left: `${left}px`,
    transform: 'translateX(-50%)',
    maxWidth: `${TOOLTIP_MAX_WIDTH}px`,
  }

  if (tooltipPosition.value === 'top') {
    style.bottom = `${window.innerHeight - h.top + 16}px`
  } else {
    // 放在挖洞底边下方的预留带内，并钳制确保不超出视口底部
    style.top = `${Math.min(h.bottom + 16, window.innerHeight - TOOLTIP_EST_HEIGHT - MARGIN)}px`
  }

  return style
})

// 引导上下文变化时立刻重新定位（rAF 之外的即时补偿）
watch(() => props.guide?.id, async () => {
  await nextTick()
  updateTargetRect()
}, { immediate: true })

onMounted(() => {
  startTracking()
})

onBeforeUnmount(() => {
  stopTracking()
})
</script>

<template>
  <div v-if="guide && holeRect" class="tutorial-spotlight-root">
    <!-- 暗色遮罩（四个 div 拼出挖洞效果，底边为看山对话框预留显示空间） -->
    <div
      class="tutorial-overlay-top"
      :style="{ height: `${holeRect.top}px` }"
    />
    <div
      class="tutorial-overlay-bottom"
      :style="{
        top: `${holeRect.bottom}px`,
        bottom: '0',
      }"
    />
    <div
      class="tutorial-overlay-left"
      :style="{
        top: `${holeRect.top}px`,
        height: `${holeRect.bottom - holeRect.top}px`,
        width: `${holeRect.left}px`,
      }"
    />
    <div
      class="tutorial-overlay-right"
      :style="{
        top: `${holeRect.top}px`,
        height: `${holeRect.bottom - holeRect.top}px`,
        left: `${holeRect.right}px`,
        right: '0',
      }"
    />

    <!-- 目标元素脉冲边框 -->
    <div
      class="tutorial-target-ring"
      :style="{
        top: `${holeRect.top}px`,
        left: `${holeRect.left}px`,
        width: `${holeRect.right - holeRect.left}px`,
        height: `${holeRect.bottom - holeRect.top}px`,
      }"
    />

    <!-- 提示文本框 -->
    <div class="tutorial-tooltip" :style="tooltipStyle">
      <div class="tutorial-tooltip__speaker">{{ guide.speaker }}</div>
      <p class="tutorial-tooltip__text">{{ guide.text }}</p>
    </div>
  </div>
</template>

<style scoped>
.tutorial-spotlight-root {
  position: fixed;
  inset: 0;
  z-index: 95;
  pointer-events: none;
}

/* 四个方向的遮罩层，共同覆盖除目标元素外的整个视口 */
.tutorial-overlay-top,
.tutorial-overlay-bottom,
.tutorial-overlay-left,
.tutorial-overlay-right {
  position: fixed;
  /* Warm-neutral focus dimming: keeps the map legible while separating the target. */
  background: rgba(20, 17, 14, 0.60);
  pointer-events: none;
  transition: all 300ms ease;
}

.tutorial-overlay-top {
  left: 0;
  right: 0;
  top: 0;
}

.tutorial-overlay-bottom {
  left: 0;
  right: 0;
}

.tutorial-overlay-left {
  left: 0;
}

.tutorial-overlay-right {
  /* right: 0 在 inline style 中设置 */
}

.tutorial-target-ring {
  position: fixed;
  border: 2px solid rgba(190, 151, 79, 0.84);
  border-radius: 9px 4px 9px 4px;
  box-shadow: 0 0 0 3px rgba(255, 247, 214, 0.38), 0 4px 12px rgba(133, 104, 54, 0.18), inset 0 0 0 1px rgba(255, 255, 255, 0.3);
  pointer-events: none;
  animation: tutorial-ring-pulse 2.8s ease-in-out infinite;
  transition: top 200ms ease, left 200ms ease, width 200ms ease, height 200ms ease;
}

@keyframes tutorial-ring-pulse {
  0%, 100% { border-color: rgba(190, 151, 79, 0.68); box-shadow: 0 0 0 3px rgba(255, 247, 214, 0.28), 0 4px 12px rgba(133, 104, 54, 0.14), inset 0 0 0 1px rgba(255, 255, 255, 0.24); }
  50% { border-color: rgba(110, 145, 116, 0.9); box-shadow: 0 0 0 4px rgba(233, 224, 183, 0.36), 0 5px 14px rgba(102, 126, 92, 0.2), inset 0 0 0 1px rgba(255, 255, 255, 0.34); }
}

.tutorial-tooltip {
  position: fixed;
  z-index: 96;
  max-width: 360px;
  min-width: 200px;
  padding: 14px 18px;
  background:
    linear-gradient(rgba(121, 89, 57, 0.035) 1px, transparent 1px) 0 0 / 14px 14px,
    #f7efd9;
  border: 1px solid rgba(188, 157, 111, 0.72);
  border-radius: 11px 5px 11px 5px;
  box-shadow: 3px 4px 0 rgba(106, 77, 43, 0.12), 0 12px 28px rgba(82, 62, 39, 0.16), inset 0 0 0 1px rgba(255, 255, 255, 0.46);
  pointer-events: none;
  animation: tooltip-fade-in 400ms ease;
}

@keyframes tooltip-fade-in {
  from { opacity: 0; transform: translateX(-50%) translateY(6px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}

.tutorial-tooltip__speaker {
  margin: 0 0 6px;
  color: #5f866d;
  font: 800 0.78rem/1.2 'Noto Serif SC', 'Songti SC', serif;
  letter-spacing: 0.06em;
}

.tutorial-tooltip__text {
  margin: 0;
  color: #4b3828;
  font: 600 0.84rem/1.6 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
  letter-spacing: 0.02em;
}

@media (prefers-reduced-motion: reduce) {
  .tutorial-target-ring,
  .tutorial-tooltip {
    animation: none;
  }
}
</style>
