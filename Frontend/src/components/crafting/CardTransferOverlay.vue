<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { getMaterialCardAsset } from '../../data/cardAssets'
import type { CreationFlowTransferFlight } from '../../types/collectionMotion'

const props = defineProps<{
  flight: CreationFlowTransferFlight | null
}>()

const emit = defineEmits<{
  (event: 'complete'): void
}>()

const isVisible = ref(false)
const transferStyle = ref<Record<string, string>>({})
const cardImageSrc = ref<string | undefined>()
const transferCard = ref<HTMLElement | null>(null)
let currentAnimation: Animation | null = null
let pulseTimer: number | null = null
let runId = 0

function clearAnimationState() {
  runId += 1
  currentAnimation?.cancel()
  currentAnimation = null
}

function getCreationFlowTarget(flight: CreationFlowTransferFlight) {
  return [...document.querySelectorAll<HTMLElement>('[data-creation-arrival-target]')]
    .find(element => (
      element.dataset.materialId === flight.materialId
      && element.dataset.creationSlotIndex === String(flight.targetSlotIndex)
    )) ?? null
}

function isInViewport(rect: DOMRect | undefined) {
  return Boolean(
    rect
      && rect.right > 0
      && rect.left < window.innerWidth
      && rect.bottom > 0
      && rect.top < window.innerHeight,
  )
}

function transformFor(deltaX: number, deltaY: number, scale: number, rotation: number) {
  return `translate3d(calc(-50% + ${deltaX}px), calc(-50% + ${deltaY}px), 0) scale(${scale}) rotate(${rotation}deg)`
}

function pulseCreationFlowSlot(target: HTMLElement | null) {
  if (!target) {
    return
  }

  if (pulseTimer !== null) {
    window.clearTimeout(pulseTimer)
  }

  target.classList.remove('creation-arrival-pulse')
  void target.offsetWidth
  target.classList.add('creation-arrival-pulse')
  pulseTimer = window.setTimeout(() => {
    target.classList.remove('creation-arrival-pulse')
    pulseTimer = null
  }, 220)
}

function finishTransfer(target: HTMLElement | null) {
  clearAnimationState()
  pulseCreationFlowSlot(target)
  isVisible.value = false
  emit('complete')
}

async function playAnimation(
  keyframes: Keyframe[],
  options: KeyframeAnimationOptions,
  activeRunId: number,
) {
  const element = transferCard.value

  if (!element || activeRunId !== runId) {
    return false
  }

  currentAnimation = element.animate(keyframes, options)

  try {
    await currentAnimation.finished
  } catch {
    return false
  }

  return activeRunId === runId
}

async function startTransfer(flight: CreationFlowTransferFlight | null) {
  clearAnimationState()
  isVisible.value = false
  cardImageSrc.value = flight ? getMaterialCardAsset(flight.materialType) : undefined

  if (!flight) {
    return
  }

  await nextTick()

  const target = getCreationFlowTarget(flight)
  const sourceWidth = Math.max(40, flight.sourceRect.width)
  const sourceHeight = Math.max(40, flight.sourceRect.height)
  const sourceCenterX = flight.sourceRect.left + flight.sourceRect.width / 2
  const sourceCenterY = flight.sourceRect.top + flight.sourceRect.height / 2
  const targetRect = target?.getBoundingClientRect()
  const activeRunId = runId
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  transferStyle.value = {
    left: `${sourceCenterX}px`,
    top: `${sourceCenterY}px`,
    width: `${sourceWidth}px`,
    height: `${sourceHeight}px`,
    opacity: '1',
    transform: transformFor(0, 0, 1, 0),
  }

  if (reducedMotion || !target || !isInViewport(targetRect)) {
    finishTransfer(target)
    return
  }

  isVisible.value = true
  await nextTick()

  const lifted = await playAnimation([
    { opacity: 1, transform: transformFor(0, 0, 1, 0) },
    { opacity: 1, transform: transformFor(0, -4, 1.06, 0) },
  ], {
    duration: 120,
    easing: 'cubic-bezier(0.22, 0.85, 0.28, 1)',
    fill: 'forwards',
  }, activeRunId)

  if (!lifted || activeRunId !== runId) {
    return
  }

  const refreshedTargetRect = target.getBoundingClientRect()
  const targetCenterX = refreshedTargetRect.left + refreshedTargetRect.width / 2
  const targetCenterY = refreshedTargetRect.top + refreshedTargetRect.height / 2
  const deltaX = targetCenterX - sourceCenterX
  const deltaY = targetCenterY - sourceCenterY
  const targetScale = Math.max(0.78, Math.min(1.08, refreshedTargetRect.width / sourceWidth))
  const flew = await playAnimation([
    { opacity: 1, transform: transformFor(0, -4, 1.06, 0) },
    { opacity: 1, transform: transformFor(deltaX * 0.5 + 12, deltaY * 0.5 + 10, 1.02, 2) },
    { opacity: 0.9, transform: transformFor(deltaX, deltaY, targetScale, 0) },
  ], {
    duration: 500,
    easing: 'cubic-bezier(0.22, 0.75, 0.22, 1)',
    fill: 'forwards',
  }, activeRunId)

  if (flew && activeRunId === runId) {
    finishTransfer(target)
  }
}

watch(() => props.flight?.id ?? null, () => {
  void startTransfer(props.flight)
}, { immediate: true })

onBeforeUnmount(() => {
  clearAnimationState()

  if (pulseTimer !== null) {
    window.clearTimeout(pulseTimer)
  }
})
</script>

<template>
  <div v-if="isVisible && flight" class="card-transfer-layer" aria-hidden="true">
    <div ref="transferCard" class="card-transfer-card" :style="transferStyle">
      <img v-if="cardImageSrc" :src="cardImageSrc" alt="">
    </div>
  </div>
</template>
