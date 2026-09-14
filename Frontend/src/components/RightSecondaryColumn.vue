<script setup lang="ts">
import { computed, ref } from 'vue'
import KanshanPet from './ai-pet/KanshanPet.vue'
import { useWorkbenchStore } from '../stores/workbench'

const props = withDefaults(defineProps<{
  embedded?: boolean
  directive?: string
  directiveState?: string
  regionDecorationSrc?: string
  regionLabel?: string
  regionBiome?: string
  showRegionDecoration?: boolean
}>(), {
  embedded: false,
  directive: '',
  directiveState: '',
  regionDecorationSrc: '',
  regionLabel: '',
  regionBiome: '',
  showRegionDecoration: true,
})

const emit = defineEmits<{
  activate: []
  'module-a-click': []
}>()

const workbenchStore = useWorkbenchStore()
const isChatExpanded = ref(false)
const kanshanVector = computed(() => ({
  x: workbenchStore.currentVector[0],
  y: workbenchStore.currentVector[1],
}))
const regionDecorationVisible = computed(() => (
  props.showRegionDecoration
  && !isChatExpanded.value
  && Boolean(props.regionDecorationSrc)
))
</script>

<template>
  <aside
    class="article-ai-dock"
    :class="{ 'article-ai-dock--embedded': embedded }"
    aria-label="AI 看山"
  >
    <div
      v-if="embedded"
      class="article-ai-dock__embedded-shell"
      :data-kanshan-guidance-state="directiveState"
      :data-kanshan-biome="regionBiome"
    >
      <div
        class="article-ai-dock__directive"
        :class="{ 'article-ai-dock__directive--themed': regionDecorationVisible }"
      >
        <figure v-if="regionDecorationVisible" class="article-ai-dock__region-sticker" aria-hidden="true">
          <span class="article-ai-dock__region-pin"></span>
          <img :src="regionDecorationSrc" alt="" />
          <figcaption>{{ regionLabel }}</figcaption>
        </figure>
        <span>当前看山提示</span>
        <p>{{ directive }}</p>
        <small>点击看山打开完整对话</small>
      </div>
      <div class="article-ai-dock__pet">
          <KanshanPet
            :current-vector="kanshanVector"
            :default-show-chart="embedded"
            @character-click="emit('activate')"
            @module-a-click="emit('module-a-click')"
            @expanded-change="isChatExpanded = $event"
          />
      </div>
    </div>
    <KanshanPet v-else :current-vector="kanshanVector" @module-a-click="emit('module-a-click')" />
  </aside>
</template>

<style scoped>
.article-ai-dock {
  position: fixed;
  right: clamp(18px, 3vw, 46px);
  /* 上移到教程底部预留带（150px）之上，保证对话框完整可见且不被遮罩压暗 */
  bottom: clamp(160px, 18vh, 220px);
  z-index: 7;
  width: 156px;
  min-height: 118px;
  pointer-events: none;
}
.article-ai-dock :deep(.fixed.bottom-4.right-4) {
  position: absolute !important;
  top: auto !important;
  right: 0 !important;
  bottom: 0 !important;
  left: auto !important;
  z-index: 4;
  pointer-events: auto;
}
.article-ai-dock :deep(.fixed.bottom-4.right-4 > .relative),
.article-ai-dock :deep(.fixed.bottom-4.right-4 > .relative > .select-none),
.article-ai-dock :deep(.fixed.bottom-4.right-4 > .relative > .select-none > .bg-white) {
  border: 0;
  border-radius: 0;
  background: transparent !important;
  box-shadow: none;
}
.article-ai-dock :deep(.fixed.bottom-4.right-4 > .relative > .select-none > .bg-white > div:last-child) {
  background: transparent !important;
  border-top-color: rgba(101, 126, 123, 0.32) !important;
}
.article-ai-dock :deep(.fixed.bottom-4.right-4 .bg-sky-500) {
  background: #789b82 !important;
}
.article-ai-dock :deep(.fixed.bottom-4.right-4 .bg-sky-50) {
  background: rgba(248, 239, 216, 0.92) !important;
}
.article-ai-dock :deep(.fixed.bottom-4.right-4 .text-slate-700) {
  color: #655240 !important;
}
.article-ai-dock :deep(.fixed.bottom-4.right-4 .absolute.bottom-full .bg-white) {
  border: 1px solid rgba(112, 91, 55, 0.32);
  background: #f3e8bd !important;
  color: #4a4d42 !important;
}
.article-ai-dock :deep(.fixed.bottom-4.right-4 .absolute.bottom-full .border-top) {
  border-top-color: #f3e8bd !important;
}
.article-ai-dock--embedded {
  position: relative;
  right: auto;
  bottom: auto;
  z-index: 1;
  width: 100%;
  min-height: 144px;
  border: 1px solid rgba(126, 218, 204, 0.4);
  border-radius: 3px;
  padding: 7px 8px;
  background: linear-gradient(145deg, rgba(9, 39, 48, 0.94), rgba(5, 24, 32, 0.96));
  box-shadow: inset 1px 1px 0 rgba(149, 239, 225, 0.16), 3px 3px 0 rgba(0, 0, 0, 0.25);
  pointer-events: auto;
}
.article-ai-dock__embedded-shell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 160px;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 128px;
  color: #e5f8f3;
}
.article-ai-dock__pet {
  position: relative;
  z-index: 2;
  display: flex;
  width: 160px;
  min-height: 124px;
  align-items: end;
  justify-content: end;
  overflow: visible;
}
.article-ai-dock__directive {
  position: relative;
  min-width: 0;
  border: 1px solid rgba(130, 220, 205, 0.24);
  border-radius: 3px;
  padding: 10px 9px;
  background: rgba(5, 26, 34, 0.68);
}
.article-ai-dock__directive--themed { padding-top: 48px; }
.article-ai-dock__region-sticker {
  position: absolute;
  z-index: 3;
  top: -10px;
  right: -7px;
  width: 92px;
  margin: 0;
  border: 3px solid #f8efd8;
  padding: 3px 3px 2px;
  background: #f8efd8;
  box-shadow: 2px 3px 0 #593626, 0 7px 12px rgba(0, 0, 0, 0.28);
  color: #4a3022;
  transform: rotate(2.5deg);
}
.article-ai-dock__region-sticker img {
  display: block;
  width: 100%;
  aspect-ratio: 4 / 2.55;
  object-fit: cover;
}
.article-ai-dock__region-sticker figcaption {
  overflow: hidden;
  padding-top: 3px;
  font: 900 0.47rem/1 ui-monospace, SFMono-Regular, Consolas, monospace;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.article-ai-dock__region-pin {
  position: absolute;
  z-index: 2;
  top: -7px;
  left: 50%;
  width: 21px;
  height: 9px;
  background: rgba(242, 213, 141, 0.86);
  box-shadow: 0 1px 2px rgba(58, 33, 21, 0.32);
  transform: translateX(-50%) rotate(-5deg);
}
.article-ai-dock__directive > span {
  display: block;
  margin-bottom: 6px;
  color: #76d9cb;
  font: 900 0.58rem/1 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.1em;
}
.article-ai-dock__directive > p {
  margin: 0;
  color: #effbf7;
  font-size: 0.78rem;
  font-weight: 700;
  line-height: 1.52;
}
.article-ai-dock__directive > small {
  display: block;
  margin-top: 7px;
  color: #8fb8b8;
  font: 700 0.56rem/1.25 ui-monospace, SFMono-Regular, Consolas, monospace;
}
.article-ai-dock--embedded :deep(.kanshan-pet-root) {
  position: relative !important;
  inset: auto !important;
  z-index: 1;
  display: flex;
  width: auto;
  height: auto;
  align-items: end;
}
.article-ai-dock--embedded :deep(.kanshan-pet-tools) {
  display: flex !important;
  flex-direction: column;
  flex: 0 0 auto;
}
.article-ai-dock--embedded :deep(.kanshan-pet-stage) {
  width: auto;
  height: auto;
}
.article-ai-dock--embedded :deep(.kanshan-pet-card--compact) {
  width: 120px !important;
  height: 120px !important;
}
.article-ai-dock__embedded-shell:has(.kanshan-pet-card--expanded) {
  grid-template-columns: 1fr;
}
.article-ai-dock__embedded-shell:has(.kanshan-pet-card--expanded) .article-ai-dock__pet {
  width: 100%;
  justify-content: center;
}
@media (max-width: 720px) {
  .article-ai-dock { right: 10px; bottom: 160px; min-height: 112px; }
  .article-ai-dock--embedded { right: auto; bottom: auto; min-height: 142px; }
  .article-ai-dock__embedded-shell { grid-template-columns: minmax(0, 1fr) 152px; }
  .article-ai-dock__pet { width: 152px; }
  .article-ai-dock :deep(.fixed.bottom-4.right-4) {
    position: relative !important;
    top: auto !important;
    right: auto !important;
    display: flex;
    justify-content: flex-end;
  }
}
</style>
