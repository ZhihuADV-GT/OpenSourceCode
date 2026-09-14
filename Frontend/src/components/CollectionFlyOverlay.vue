<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { getMaterialCardAsset } from '../data/cardAssets'
import type { CollectionFlight } from '../types/collectionMotion'

const props = defineProps<{
  flight: CollectionFlight | null
}>()

const emit = defineEmits<{
  (event: 'complete'): void
}>()

const isVisible = ref(false)
const flightStyle = ref<Record<string, string>>({})
const cardImageSrc = ref<string | undefined>()
const missingAssetLabel = import.meta.env.DEV ? 'CARD ASSET MISSING' : ''
const acquisitionCard = ref<HTMLElement | null>(null)
let currentAnimation: Animation | null = null
let showcaseTimer: number | null = null
let pulseTimer: number | null = null
let runId = 0

function clearAnimationState() {
  runId += 1
  currentAnimation?.cancel()
  currentAnimation = null

  if (showcaseTimer !== null) {
    window.clearTimeout(showcaseTimer)
    showcaseTimer = null
  }
}

function wait(duration: number) {
  return new Promise<void>((resolve) => {
    showcaseTimer = window.setTimeout(() => {
      showcaseTimer = null
      resolve()
    }, duration)
  })
}

function getBackpackTarget(materialId: string) {
  return [...document.querySelectorAll<HTMLElement>('[data-backpack-arrival-target]')]
    .find(element => element.dataset.materialId === materialId)
    ?? document.querySelector<HTMLElement>('[data-backpack-dock]')
}

function getArticleBounds() {
  const article = document.querySelector<HTMLElement>('.book-content--reading .article-card, .article-column .article-card')
  const rect = article?.getBoundingClientRect()
  const viewportPadding = 12

  return {
    left: Math.max(viewportPadding, rect?.left ?? viewportPadding),
    right: Math.min(window.innerWidth - viewportPadding, rect?.right ?? window.innerWidth - viewportPadding),
    top: Math.max(viewportPadding, rect?.top ?? viewportPadding),
    bottom: Math.min(window.innerHeight - viewportPadding, rect?.bottom ?? window.innerHeight - viewportPadding),
  }
}

function getCardSize() {
  const desktopWidth = Math.min(Math.max(window.innerWidth * 0.16, 180), 240)
  const preferredWidth = window.innerWidth <= 720
    ? Math.min(Math.max(window.innerWidth * 0.48, 160), 210)
    : desktopWidth
  const bounds = getArticleBounds()
  const availableWidth = Math.max(140, bounds.right - bounds.left - 24)
  const availableHeight = Math.max(180, bounds.bottom - bounds.top - 24)
  const cardRatio = 1279 / 1706

  return Math.max(140, Math.min(preferredWidth, availableWidth, availableHeight * cardRatio))
}

function clampPosition(x: number, y: number, width: number) {
  const bounds = getArticleBounds()
  const height = width / (1279 / 1706)

  return {
    x: Math.min(Math.max(x, bounds.left + width / 2), bounds.right - width / 2),
    y: Math.min(Math.max(y, bounds.top + height / 2), bounds.bottom - height / 2),
  }
}

function transformFor(deltaX: number, deltaY: number, scale: number, rotation: number) {
  return `translate3d(calc(-50% + ${deltaX}px), calc(-50% + ${deltaY}px), 0) scale(${scale}) rotate(${rotation}deg)`
}

function pulseBackpack(target: HTMLElement | null) {
  if (!target) {
    return
  }

  target.classList.remove('backpack-arrival-pulse')
  void target.offsetWidth
  target.classList.add('backpack-arrival-pulse')
  pulseTimer = window.setTimeout(() => {
    target.classList.remove('backpack-arrival-pulse')
    pulseTimer = null
  }, 240)
}

function finishFlight(target: HTMLElement | null) {
  clearAnimationState()
  pulseBackpack(target)
  isVisible.value = false
  emit('complete')
}

async function playAnimation(
  keyframes: Keyframe[],
  options: KeyframeAnimationOptions,
  activeRunId: number,
) {
  const element = acquisitionCard.value

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

async function startFlight(flight: CollectionFlight | null) {
  clearAnimationState()
  isVisible.value = false
  cardImageSrc.value = flight ? getMaterialCardAsset(flight.materialType) : undefined

  if (!flight) {
    return
  }

  await nextTick()

  const target = getBackpackTarget(flight.materialId)
  const width = getCardSize()
  const sourceCenterX = flight.sourceRect.left + flight.sourceRect.width / 2
  const sourceCenterY = flight.sourceRect.top + flight.sourceRect.height / 2 - Math.min(72, width * 0.28)
  const spawn = clampPosition(sourceCenterX, sourceCenterY, width)
  const activeRunId = runId
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  flightStyle.value = {
    left: `${spawn.x}px`,
    top: `${spawn.y}px`,
    width: `${width}px`,
    opacity: '0',
    transform: transformFor(0, 18, 0.62, 0),
  }
  isVisible.value = true
  await nextTick()

  if (reducedMotion) {
    finishFlight(target)
    return
  }

  const popped = await playAnimation([
    { opacity: 0, transform: transformFor(0, 18, 0.62, 0) },
    { opacity: 1, transform: transformFor(0, 0, 1.08, 0), offset: 0.68 },
    { opacity: 1, transform: transformFor(0, 0, 1, 0) },
  ], {
    duration: 220,
    easing: 'cubic-bezier(0.22, 0.85, 0.28, 1)',
    fill: 'forwards',
  }, activeRunId)

  if (!popped || activeRunId !== runId) {
    return
  }

  await wait(420)

  if (activeRunId !== runId) {
    return
  }

  const targetRect = target?.getBoundingClientRect()
  const targetVisible = Boolean(
    targetRect
      && targetRect.right > 0
      && targetRect.left < window.innerWidth
      && targetRect.bottom > 0
      && targetRect.top < window.innerHeight,
  )

  if (!target || !targetVisible) {
    const faded = await playAnimation([
      { opacity: 1, transform: transformFor(0, 0, 1, 0) },
      { opacity: 0, transform: transformFor(0, -10, 0.3, 0) },
    ], {
      duration: 280,
      easing: 'ease-in',
      fill: 'forwards',
    }, activeRunId)

    if (faded && activeRunId === runId) {
      finishFlight(target)
    }
    return
  }

  const targetCenterX = targetRect.left + targetRect.width / 2
  const targetCenterY = targetRect.top + Math.min(targetRect.height / 2, 36)
  const deltaX = targetCenterX - spawn.x
  const deltaY = targetCenterY - spawn.y
  const flew = await playAnimation([
    { opacity: 1, transform: transformFor(0, 0, 1, 0) },
    { opacity: 0.98, transform: transformFor(deltaX * 0.45, deltaY * 0.45 - 34, 0.72, -2) },
    { opacity: 0.85, transform: transformFor(deltaX, deltaY, 0.28, 0) },
  ], {
    duration: 620,
    easing: 'cubic-bezier(0.22, 0.75, 0.22, 1)',
    fill: 'forwards',
  }, activeRunId)

  if (flew && activeRunId === runId) {
    finishFlight(target)
  }
}

watch(() => props.flight?.id ?? null, () => {
  void startFlight(props.flight)
}, { immediate: true })

onBeforeUnmount(() => {
  clearAnimationState()

  if (pulseTimer !== null) {
    window.clearTimeout(pulseTimer)
  }
})
</script>

<template>
  <div v-if="isVisible && flight" class="collection-flight-layer" aria-hidden="true">
    <div
      ref="acquisitionCard"
      class="collection-acquisition-card"
      :class="{ 'collection-acquisition-card--missing': !cardImageSrc }"
      :style="flightStyle"
    >
      <img v-if="cardImageSrc" :src="cardImageSrc" alt="">
      <span v-else class="collection-acquisition-card__fallback">{{ missingAssetLabel }}</span>
    </div>
  </div>
</template>
