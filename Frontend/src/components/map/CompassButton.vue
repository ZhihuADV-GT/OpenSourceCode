<script setup lang="ts">
/**
 * 知北针（拟真指南针）— 地图右下角
 *
 * 交互逻辑：
 *   - 当 pendingMoveVector 非 null 时，知北针显示待出发状态
 *   - 由地图上的独立“出发”按钮调用 startJourney()
 *   - 指针旋转到结算向量的实际方向 → 看山移动 → 指针归零
 *   - 无待移动时，知北针为装饰态（不可点击）
 *
 * 方向语义由 mapTypes.ts 的 getJourneyDirectionByVector 统一提供。
 * 指针只消费该映射给出的 compassAngle，不再维护第二套投影公式。
 */
const compassImg = '' // [art-assets disabled] ../assets/compass-map.webp
import { getJourneyDirectionByVector } from '../../types/mapTypes'

const props = defineProps<{
  /** 待执行的移动向量 [vx, vy]，null 表示无待移动 */
  pendingMoveVector: [number, number] | null
}>()

const emit = defineEmits<{
  'animation-started': []
  'movement-start': []
  'movement-complete': []
}>()

import { ref, computed, onBeforeUnmount, watch } from 'vue'

/** 指针旋转角度（CSS deg） */
const needleRotation = ref(0)
/** 是否正在动画中 */
const isAnimating = ref(false)
const isNeedleVisible = ref(false)
let revealTimer: ReturnType<typeof window.setTimeout> | null = null
let completeTimer: ReturnType<typeof window.setTimeout> | null = null
let hideTimer: ReturnType<typeof window.setTimeout> | null = null

/** 是否有待执行的移动 */
const hasPendingMove = computed(() => props.pendingMoveVector !== null)

/** 根据统一旅途方向映射取得指针目标角度。 */
function computeTargetAngle(vec: [number, number]): number {
  return getJourneyDirectionByVector(vec).compassAngle
}

/** 找最短旋转路径的角度 */
function shortestAngleTo(from: number, to: number): number {
  const diff = ((to - from) % 360 + 540) % 360 - 180
  return from + diff
}

function startJourney(): boolean {
  if (!hasPendingMove.value || isAnimating.value) return false
  const vec = props.pendingMoveVector!

  isAnimating.value = true
  isNeedleVisible.value = true
  emit('animation-started')
  if (revealTimer !== null) window.clearTimeout(revealTimer)
  if (completeTimer !== null) window.clearTimeout(completeTimer)
  if (hideTimer !== null) window.clearTimeout(hideTimer)

  // 0–500ms：指针出现并转向。
  const targetAngle = computeTargetAngle(vec)
  needleRotation.value = shortestAngleTo(needleRotation.value, targetAngle)

  // 500–1500ms：保持指向，同时通知地图开始一次 tile 移动。
  revealTimer = window.setTimeout(() => {
    emit('movement-start')
  }, 500)

  // 1500ms：地图移动完成，进入本局结算。
  completeTimer = window.setTimeout(() => {
    emit('movement-complete')
  }, 1500)

  // 1500–2000ms：指针缩回并回到静待态。
  hideTimer = window.setTimeout(() => {
    needleRotation.value = 0
    isNeedleVisible.value = false
    isAnimating.value = false
  }, 2000)

  return true
}

defineExpose({ startJourney })

// 激活知北针后先在地图上展示待出发方向；只有独立的“出发”按钮
// 才会调用 startJourney 并触发移动。
watch(() => props.pendingMoveVector, (newVal) => {
  if (isAnimating.value) {
    return
  }

  if (newVal === null) {
    needleRotation.value = 0
    isNeedleVisible.value = false
    return
  }

  needleRotation.value = computeTargetAngle(newVal)
  isNeedleVisible.value = true
}, { immediate: true })

onBeforeUnmount(() => {
  if (revealTimer !== null) window.clearTimeout(revealTimer)
  if (completeTimer !== null) window.clearTimeout(completeTimer)
  if (hideTimer !== null) window.clearTimeout(hideTimer)
})
</script>

<template>
  <div
    class="compass-root"
    :class="{ 'compass--ready': hasPendingMove && !isAnimating }"
  >
    <img :src="compassImg" alt="知北针" class="compass-image" />
    <!-- SVG 指针叠加层 -->
    <svg class="compass-needle" viewBox="0 0 100 100">
      <polygon
        class="compass-needle-polygon"
        :class="{ 'compass-needle-polygon--hidden': !isNeedleVisible }"
        points="50,15 55,50 50,55 45,50"
        fill="#e74c3c"
        :style="{ transform: `rotate(${needleRotation}deg)` }"
      />
      <circle cx="50" cy="50" r="5" fill="#2c3e50" />
    </svg>
  </div>
</template>

<style scoped>
.compass-root {
  position: relative;
  width: 90px;
  height: 90px;
  cursor: default;
  user-select: none;
}

.compass--ready {
  animation: compass-pulse 2s ease-in-out infinite;
}
.compass--ready:hover {
  filter: brightness(1.15);
}

.compass-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  pointer-events: none;
}

.compass-needle {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.compass-needle-polygon {
  transform-origin: 50px 50px;
  opacity: 1;
  transition:
    transform 800ms cubic-bezier(0.34, 1.56, 0.64, 1),
    opacity 450ms cubic-bezier(0.22, 0.78, 0.28, 1);
  will-change: transform, opacity;
}

.compass-needle-polygon--hidden {
  opacity: 0;
}

@keyframes compass-pulse {
  0%, 100% { transform: scale(1); filter: brightness(1); }
  50% { transform: scale(1.06); filter: brightness(1.1); }
}
</style>
