<script setup lang="ts">
import { computed, ref } from 'vue'
import { getMaterialCardAsset } from '../../data/cardAssets'
import { useWorkbenchStore } from '../../stores/workbench'
import type { Material } from '../../types/material'

const props = defineProps<{
  material: Material
}>()

const workbenchStore = useWorkbenchStore()
const isInWorkbench = computed(() => workbenchStore.hasMaterial(props.material.id))
const failedAsset = ref<string | undefined>()
const cardAsset = computed(() => getMaterialCardAsset(props.material.type))
const imageSource = computed(() => (
  cardAsset.value && cardAsset.value !== failedAsset.value ? cardAsset.value : undefined
))
const cardTypeLabel = computed(() => props.material.type ?? '未知类型素材')
const missingAssetLabel = import.meta.env.DEV ? 'CARD ASSET MISSING' : ''
const interactionLabel = computed(() => {
  if (isInWorkbench.value) {
    return `${cardTypeLabel.value}已加入工作台`
  }

  if (!imageSource.value) {
    return `${cardTypeLabel.value}卡牌美术缺失`
  }

  return `将${cardTypeLabel.value}加入工作台`
})
const interactionDisabled = computed(() => isInWorkbench.value || !imageSource.value)

function addToWorkbench() {
  workbenchStore.addMaterial(props.material.id)
}

function handleAssetError() {
  failedAsset.value = cardAsset.value

  if (import.meta.env.DEV) {
    console.warn(`[MaterialCard] Missing asset for type: ${props.material.type ?? 'undefined'}`)
  }
}
</script>

<template>
  <article
    class="material-card material-card__shell"
    :class="{
      'material-card--added': isInWorkbench,
      'material-card--missing': !imageSource,
    }"
  >
    <button
      class="material-card__interaction"
      type="button"
      :aria-label="interactionLabel"
      :disabled="interactionDisabled"
      :aria-pressed="isInWorkbench"
      @click="addToWorkbench"
    >
      <img
        v-if="imageSource"
        class="material-card__image"
        :src="imageSource"
        alt=""
        @error="handleAssetError"
      >
      <span v-else class="material-card__fallback" aria-hidden="true">{{ missingAssetLabel }}</span>
    </button>
  </article>
</template>
