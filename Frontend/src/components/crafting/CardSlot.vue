<script setup lang="ts">
import SaltCardView from './SaltCardView.vue'

withDefaults(defineProps<{
  imageSrc?: string
  cardType?: string
  cardId?: string
  sourceText?: string
  compact?: boolean
  occupied: boolean
  selected?: boolean
  interactive?: boolean
  variant?: 'backpack' | 'workbench'
  ariaLabel?: string
  dragging?: boolean
}>(), {
  imageSrc: undefined,
  cardType: undefined,
  cardId: undefined,
  sourceText: undefined,
  compact: false,
  selected: false,
  interactive: false,
  variant: 'backpack',
  ariaLabel: undefined,
  dragging: false,
})

const emit = defineEmits<{
  (event: 'activate', sourceEvent: MouseEvent): void
  (event: 'pointer-down', sourceEvent: PointerEvent): void
  (event: 'pointer-move', sourceEvent: PointerEvent): void
  (event: 'pointer-up', sourceEvent: PointerEvent): void
  (event: 'pointer-cancel', sourceEvent: PointerEvent): void
}>()

function handlePointerDown(sourceEvent: PointerEvent) {
  const sourceElement = sourceEvent.currentTarget as HTMLElement | null
  sourceElement?.setPointerCapture(sourceEvent.pointerId)
  emit('pointer-down', sourceEvent)
}

function handlePointerUp(sourceEvent: PointerEvent) {
  const sourceElement = sourceEvent.currentTarget as HTMLElement | null
  if (sourceElement?.hasPointerCapture(sourceEvent.pointerId)) {
    sourceElement.releasePointerCapture(sourceEvent.pointerId)
  }
  emit('pointer-up', sourceEvent)
}

function handlePointerCancel(sourceEvent: PointerEvent) {
  const sourceElement = sourceEvent.currentTarget as HTMLElement | null
  if (sourceElement?.hasPointerCapture(sourceEvent.pointerId)) {
    sourceElement.releasePointerCapture(sourceEvent.pointerId)
  }
  emit('pointer-cancel', sourceEvent)
}
</script>

<template>
  <button
    v-if="interactive"
    class="inventory-slot"
    :class="[
      `inventory-slot--${variant}`,
      {
        'inventory-slot--occupied': occupied,
        'inventory-slot--selected': selected,
        'inventory-slot--dragging-source': dragging,
      },
    ]"
    type="button"
    :aria-label="ariaLabel"
    :aria-pressed="selected"
    @pointerdown="handlePointerDown"
    @pointermove="$emit('pointer-move', $event)"
    @pointerup="handlePointerUp"
    @pointercancel="handlePointerCancel"
    @click="$emit('activate', $event)"
  >
    <SaltCardView
      v-if="occupied && cardType"
      :card-type="cardType"
      :card-id="cardId"
      :source-text="sourceText"
      :compact="compact"
    />
    <img v-else-if="occupied && imageSrc" class="inventory-slot__image" :src="imageSrc" alt="" draggable="false">
    <span v-if="!occupied && variant === 'workbench'" class="inventory-slot__empty-marker" aria-hidden="true">+</span>
  </button>
  <div
    v-else
    class="inventory-slot"
    :class="[
      `inventory-slot--${variant}`,
      {
        'inventory-slot--occupied': occupied,
        'inventory-slot--selected': selected,
        'inventory-slot--dragging-source': dragging,
      },
    ]"
  >
    <SaltCardView
      v-if="occupied && cardType"
      :card-type="cardType"
      :card-id="cardId"
      :source-text="sourceText"
      :compact="compact"
    />
    <img v-else-if="occupied && imageSrc" class="inventory-slot__image" :src="imageSrc" alt="" draggable="false">
    <span v-if="!occupied && variant === 'workbench'" class="inventory-slot__empty-marker" aria-hidden="true">+</span>
  </div>
</template>
