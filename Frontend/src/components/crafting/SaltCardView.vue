<script setup lang="ts">
import { computed } from 'vue'
import { getMaterialCardAsset } from '../../data/cardAssets'

const props = withDefaults(defineProps<{
  cardType?: string
  cardId?: string
  sourceText?: string
  compact?: boolean
}>(), {
  cardType: '信息点',
  cardId: 'unknown-card',
  sourceText: '暂无原文',
  compact: false,
})

const cardCover = computed(() => getMaterialCardAsset(props.cardType))
const cardTooltip = computed(() => [
  `类型：${props.cardType}`,
  `Card ID：${props.cardId}`,
  '',
  '原文：',
  props.sourceText,
].join('\n'))
</script>

<template>
  <div
    class="salt-card-view"
    :class="{ 'salt-card-view--compact': compact }"
    :data-card-type="cardType"
    :title="cardTooltip"
    :aria-label="`${cardType}，Card ID：${cardId}`"
  >
    <img
      v-if="cardCover"
      :src="cardCover"
      :alt="cardType"
      class="salt-card-cover"
      draggable="false"
    >
    <span v-else class="salt-card-cover-fallback">{{ cardType }}</span>
  </div>
</template>
