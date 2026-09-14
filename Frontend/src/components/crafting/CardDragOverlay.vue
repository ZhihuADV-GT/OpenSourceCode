<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { getMaterialCardAsset } from '../../data/cardAssets'
import type { CardDragState } from '../../types/cardDrag'

const props = defineProps<{
  drag: CardDragState | null
}>()

const emit = defineEmits<{
  (event: 'settled', materialId: string): void
}>()

const dragCard = ref<HTMLElement | null>(null)
let currentAnimation: Animation | null = null
let runId = 0

const isVisible = computed(() => Boolean(props.drag && props.drag.phase !== 'pressing'))
const cardImageSrc = computed(() => props.drag ? getMaterialCardAsset(props.drag.materialType) : undefined)

function clearAnimation() {
  runId += 1
  currentAnimation?.cancel()
  currentAnimation = null
}

function transformFor(scale: number, rotation: number) {
  return `translate3d(-50%, -50%, 0) scale(${scale}) rotate(${rotation}deg)`
}

const overlayStyle = computed(() => {
  const drag = props.drag
  if (!drag) {
    return {}
  }

  return {
    left: `${drag.displayX}px`,
    top: `${drag.displayY}px`,
    width: `${Math.max(40, drag.sourceRect.width)}px`,
    height: `${Math.max(40, drag.sourceRect.height)}px`,
    transform: transformFor(drag.phase === 'dragging' ? 1.04 : 1, drag.phase === 'dragging' ? -1 : 0),
  }
})

async function animateToTarget(drag: CardDragState) {
  await nextTick()
  const element = dragCard.value
  const targetRect = drag.phase === 'snapping' ? drag.targetRect : drag.sourceRect
  if (!element || !targetRect) {
    emit('settled', drag.materialId)
    return
  }

  const activeRunId = runId
  const startX = drag.displayX
  const startY = drag.displayY
  const targetX = targetRect.left + targetRect.width / 2
  const targetY = targetRect.top + targetRect.height / 2
  const targetScale = drag.phase === 'snapping'
    ? Math.max(0.78, Math.min(1, targetRect.width / Math.max(40, drag.sourceRect.width)))
    : 1

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    emit('settled', drag.materialId)
    return
  }

  currentAnimation = element.animate([
    {
      left: `${startX}px`,
      top: `${startY}px`,
      transform: transformFor(1.04, -1),
      opacity: 1,
    },
    {
      left: `${targetX}px`,
      top: `${targetY}px`,
      transform: transformFor(drag.phase === 'snapping' ? 0.98 : 1.02, 0),
      opacity: 1,
      offset: 0.72,
    },
    {
      left: `${targetX}px`,
      top: `${targetY}px`,
      transform: transformFor(targetScale, 0),
      opacity: drag.phase === 'snap-back' ? 0.92 : 1,
    },
  ], {
    duration: drag.phase === 'snapping' ? 160 : 220,
    easing: 'cubic-bezier(0.22, 0.82, 0.28, 1)',
    fill: 'forwards',
  })

  try {
    await currentAnimation.finished
  } catch {
    return
  }

  if (activeRunId === runId && props.drag?.materialId === drag.materialId) {
    emit('settled', drag.materialId)
  }
}

watch(() => `${props.drag?.materialId ?? ''}:${props.drag?.phase ?? ''}`, () => {
  clearAnimation()
  const drag = props.drag
  if (drag?.phase === 'snapping' || drag?.phase === 'snap-back') {
    void animateToTarget(drag)
  }
})

onBeforeUnmount(clearAnimation)
</script>

<template>
  <div v-if="isVisible && drag" class="card-drag-overlay-layer" aria-hidden="true">
    <div ref="dragCard" class="card-drag-overlay" :class="{ 'card-drag-overlay--snapping': drag.phase === 'snapping' }" :style="overlayStyle">
      <img v-if="cardImageSrc" :src="cardImageSrc" alt="">
    </div>
  </div>
</template>
