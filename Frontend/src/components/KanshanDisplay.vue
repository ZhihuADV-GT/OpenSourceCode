<script setup lang="ts">
/**
 * 看山展示组件 — 背包窗口右下角
 * 显示看山待机 GIF，点击后通知父组件切换知北针显示
 */
const kanshanIdle = '' // [art-assets disabled]

defineProps<{
  /** 当前是否已展开知北针 */
  compassVisible: boolean
}>()

const emit = defineEmits<{
  toggleCompass: []
}>()

function handleClick() {
  emit('toggleCompass')
}
</script>

<template>
  <div
    class="kanshan-display"
    :class="{ 'kanshan--active': compassVisible }"
    @click="handleClick"
    :title="compassVisible ? '收起知北针' : '点击查看知北针'"
  >
    <img :src="kanshanIdle" alt="看山" class="kanshan-gif" draggable="false" />
  </div>
</template>

<style scoped>
.kanshan-display {
  width: 80px;
  height: 80px;
  cursor: pointer;
  transition: transform 150ms ease;
  user-select: none;
}
.kanshan-display:hover {
  transform: scale(1.08);
}
.kanshan--active {
  filter: drop-shadow(0 0 6px rgba(24, 144, 255, 0.4));
}
.kanshan-gif {
  width: 100%;
  height: 100%;
  object-fit: contain;
  pointer-events: none;
}
</style>
