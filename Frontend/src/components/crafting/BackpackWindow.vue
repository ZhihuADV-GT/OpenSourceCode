<script setup lang="ts">
/** 地图上的整合背包：本局唯一可编辑的 Creation Flow 工作区。 */
import { computed, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
// [art-assets disabled]
const kanshanStickerImg = ''
const planetStickerImg = ''
const starStickerImg = ''
const oceanEnvironmentImg = ''
const glacierEnvironmentImg = ''
const volcanoEnvironmentImg = ''
const desertEnvironmentImg = ''
import { useCreationFlowStore } from '../../stores/creationFlow'
import { useGameStore } from '../../stores/game'
import { useMaterialStore } from '../../stores/material'
import { useWorkbenchStore } from '../../stores/workbench'
import {
  buildCompositionHintAnalysisRequest,
  buildCompositionHints,
  fetchCompositionHintAnalysis,
} from '../../services/compositionHintService'
import type { CompositionHintResponse } from '../../types/compositionHint'
import {
  getQuadrantByMapPosition,
  getQuadrantName,
  isNonZeroVector,
  REGION_VISUAL_CONFIG,
  VECTOR_EPSILON,
  type BiomeType,
} from '../../types/mapTypes'
import SubWindow from '../SubWindow.vue'
import LeftPanel from './LeftPanel.vue'
import RightSecondaryColumn from '../RightSecondaryColumn.vue'
import CompositionHintModal from '../CompositionHintModal.vue'
import {
  KANSHAN_DECORATION_VARIANTS,
  takeNextKanshanDecorationVariant,
  type KanshanDecorationVariant,
} from '../kanshanDecorationVariants'

type KanshanGuidanceState =
  | 'EMPTY_BACKPACK'
  | 'BACKPACK_HAS_CARDS_FLOW_EMPTY'
  | 'FLOW_HAS_CARDS_ZERO_VECTOR'
  | 'FLOW_VALID_NOT_SUBMITTED'
  | 'SUBMITTED_READY'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{
  close: []
  submitted: []
  'open-recipe-book': []
}>()
const pendingArrivalMaterialIds = reactive(new Set<string>())
const showKanshanDialog = ref(false)
const showCompositionHint = ref(false)
const compositionHintLoading = ref(false)
const compositionHintAnalysis = ref('')
const compositionHint = ref<CompositionHintResponse>({
  message: '',
  items: [],
})
const workspaceDecorationVariant = ref<KanshanDecorationVariant>('orbit')
const kanshanDecorationVariant = ref<KanshanDecorationVariant>('orbit')
const creationFlowStore = useCreationFlowStore()
const gameStore = useGameStore()
const materialStore = useMaterialStore()
const workbenchStore = useWorkbenchStore()
const { materials } = storeToRefs(materialStore)

const environmentArtByBiome: Record<BiomeType, string> = {
  ocean: oceanEnvironmentImg,
  glacier: glacierEnvironmentImg,
  volcano: volcanoEnvironmentImg,
  desert: desertEnvironmentImg,
}

const environmentAccentByBiome: Record<BiomeType, string> = {
  ocean: '#63dbe7',
  glacier: '#b9dcff',
  volcano: '#ff8054',
  desert: '#edc56f',
}

const environmentLabelByBiome: Record<BiomeType, string> = {
  ocean: '海洋',
  glacier: '冰川',
  volcano: '火山',
  desert: '荒原 · 沙漠',
}

const currentMapRegion = computed(() => getQuadrantByMapPosition(
  gameStore.mountainPosition.row,
  gameStore.mountainPosition.col,
))
const currentRegionTheme = computed(() => {
  const region = REGION_VISUAL_CONFIG[currentMapRegion.value]
  return {
    biome: region.biome,
    image: environmentArtByBiome[region.biome],
    accent: environmentAccentByBiome[region.biome],
    label: `${environmentLabelByBiome[region.biome]} · ${getQuadrantName(currentMapRegion.value)}`,
  }
})
const kanshanDialogPanelStyle = computed<Record<string, string>>(() => ({
  '--kanshan-dialog-accent': currentRegionTheme.value.accent,
}))

const previewMatchesCommittedVector = computed(() => {
  const committed = gameStore.roundVector
  if (!gameStore.isMapReady || !committed) return false
  return Math.hypot(
    workbenchStore.currentVector[0] - committed[0],
    workbenchStore.currentVector[1] - committed[1],
  ) <= VECTOR_EPSILON
})

const kanshanGuidanceState = computed<KanshanGuidanceState>(() => {
  if (materials.value.length === 0) return 'EMPTY_BACKPACK'
  if (creationFlowStore.filledCount === 0) return 'BACKPACK_HAS_CARDS_FLOW_EMPTY'
  if (!isNonZeroVector(workbenchStore.currentVector)) return 'FLOW_HAS_CARDS_ZERO_VECTOR'
  if (previewMatchesCommittedVector.value) return 'SUBMITTED_READY'
  return 'FLOW_VALID_NOT_SUBMITTED'
})

const kanshanGuidance = computed(() => ({
  EMPTY_BACKPACK: '你还没有收集素材，可以先返回文章继续寻找。',
  BACKPACK_HAS_CARDS_FLOW_EMPTY: '把刚刚收集到的素材拖进创作流试试看。',
  FLOW_HAS_CARDS_ZERO_VECTOR: '现在还没有形成明确方向，可以调整素材组合。',
  FLOW_VALID_NOT_SUBMITTED: '已经形成方向了，可以提交这次选择。',
  SUBMITTED_READY: '方向已经确定，看看地图上的指南针，然后准备出发。',
})[kanshanGuidanceState.value])

const kanshanPlayerPrompt = computed(() => ({
  EMPTY_BACKPACK: '背包还是空的，我现在该从哪里开始？',
  BACKPACK_HAS_CARDS_FLOW_EMPTY: '我已经收集到素材，下一步要怎么组合？',
  FLOW_HAS_CARDS_ZERO_VECTOR: '这些素材还没有形成方向，我该怎样调整？',
  FLOW_VALID_NOT_SUBMITTED: '这组素材已经有方向了，可以出发了吗？',
  SUBMITTED_READY: '方向已经确定，接下来要看哪里？',
})[kanshanGuidanceState.value])

function openKanshanDialog() {
  kanshanDecorationVariant.value = takeNextKanshanDecorationVariant(kanshanDecorationVariant.value)
  showKanshanDialog.value = true
}

function openCompositionHint() {
  compositionHintAnalysis.value = ''
  compositionHint.value = buildCompositionHints(
    materialStore.materials,
    creationFlowStore.slots,
    workbenchStore.currentVector,
  )
  showCompositionHint.value = true
}

async function handleCompositionDeepAnalysis() {
  if (compositionHintLoading.value) return
  compositionHintLoading.value = true
  compositionHintAnalysis.value = ''

  const request = buildCompositionHintAnalysisRequest(
    compositionHint.value,
    materialStore.materials,
    creationFlowStore.slots,
    workbenchStore.currentVector,
  )
  const result = await fetchCompositionHintAnalysis(request)
  compositionHintLoading.value = false
  compositionHintAnalysis.value = result?.analysis || '深度分析暂时不可用，先按上面的合成建议试试看。'
}

function closeWorkspace() {
  showKanshanDialog.value = false
  emit('close')
}

function handleSubmitted() {
  showKanshanDialog.value = false
  emit('submitted')
}

function handleZeroVectorBlocked() {
  openKanshanDialog()
}

function pickWorkspaceDecorationVariant(current: KanshanDecorationVariant) {
  const candidates = KANSHAN_DECORATION_VARIANTS.filter(variant => variant !== current)
  return candidates[Math.floor(Math.random() * candidates.length)] ?? 'orbit'
}

watch(() => props.visible, visible => {
  if (visible) {
    workspaceDecorationVariant.value = pickWorkspaceDecorationVariant(workspaceDecorationVariant.value)
    return
  }

  showKanshanDialog.value = false
  showCompositionHint.value = false
}, { immediate: true })
</script>

<template>
  <SubWindow title="背包 & 创作流" icon="🎒" :visible="visible" wide theme="workspace" @close="closeWorkspace">
    <div
      class="integrated-backpack-window"
      :class="`integrated-backpack-window--${workspaceDecorationVariant}`"
      :data-decoration-variant="workspaceDecorationVariant"
      data-tutorial-workbench
    >
      <img class="workspace-window-sticker workspace-window-sticker--star" :src="starStickerImg" alt="" aria-hidden="true" />
      <img class="workspace-window-sticker workspace-window-sticker--character" :src="kanshanStickerImg" alt="" aria-hidden="true" />
      <LeftPanel
        :pending-arrival-material-ids="pendingArrivalMaterialIds"
        @submitted="handleSubmitted"
        @submit-blocked-zero="handleZeroVectorBlocked"
        @open-recipe-book="emit('open-recipe-book')"
      >
        <template #after-backpack>
          <RightSecondaryColumn
            embedded
            :directive="kanshanGuidance"
            :directive-state="kanshanGuidanceState"
            :region-decoration-src="currentRegionTheme.image"
            :region-label="currentRegionTheme.label"
            :region-biome="currentRegionTheme.biome"
            :show-region-decoration="!showKanshanDialog"
            @activate="openKanshanDialog"
            @module-a-click="openCompositionHint"
          />
        </template>
      </LeftPanel>
    </div>
  </SubWindow>

  <CompositionHintModal
    :visible="visible && showCompositionHint"
    :message="compositionHint.message"
    :items="compositionHint.items"
    :loading="compositionHintLoading"
    :analysis="compositionHintAnalysis"
    @close="showCompositionHint = false"
    @deep-analysis="handleCompositionDeepAnalysis"
  />

  <SubWindow
    title="看山的建议"
    icon="🧭"
    :visible="visible && showKanshanDialog"
    theme="kanshan"
    :panel-style="kanshanDialogPanelStyle"
    @close="showKanshanDialog = false"
  >
    <section
      class="workspace-kanshan-dialog"
      :data-kanshan-guidance-state="kanshanGuidanceState"
      :data-kanshan-region="currentMapRegion"
      :data-kanshan-biome="currentRegionTheme.biome"
      :data-decoration-variant="kanshanDecorationVariant"
      :class="`workspace-kanshan-dialog--${kanshanDecorationVariant}`"
    >
      <img class="workspace-kanshan-dialog__star-sticker" :src="starStickerImg" alt="" aria-hidden="true" />
      <img class="workspace-kanshan-dialog__star-sticker workspace-kanshan-dialog__star-sticker--secondary" :src="starStickerImg" alt="" aria-hidden="true" />
      <img class="workspace-kanshan-dialog__planet-sticker" :src="planetStickerImg" alt="" aria-hidden="true" />

      <img class="workspace-kanshan-dialog__character-sticker" :src="kanshanStickerImg" alt="看山" />

      <div class="workspace-kanshan-dialog__content">
        <div class="workspace-kanshan-dialog__identity">
          <div>
            <p>刘看山 · KANSHAN AI</p>
            <h4>旅途中的方向伙伴</h4>
          </div>
        </div>

        <p class="workspace-kanshan-dialog__region">
          <span>当前区域</span>
          <strong>{{ currentRegionTheme.label }}</strong>
        </p>

        <div class="workspace-kanshan-dialog__directive">
          <p class="workspace-kanshan-dialog__state">CURRENT DIRECTIVE · {{ kanshanGuidanceState }}</p>
          <p class="workspace-kanshan-dialog__message">{{ kanshanGuidance }}</p>
          <small>我会根据你在创作流中的素材组合，继续帮你辨认下一步方向。</small>
        </div>

        <div class="workspace-kanshan-dialog__conversation" aria-label="看山对话摘要">
          <div class="workspace-kanshan-dialog__bubble-row workspace-kanshan-dialog__bubble-row--player">
            <p class="workspace-kanshan-dialog__bubble workspace-kanshan-dialog__bubble--player">
              {{ kanshanPlayerPrompt }}
            </p>
          </div>
          <div class="workspace-kanshan-dialog__bubble-row workspace-kanshan-dialog__bubble-row--kanshan">
            <span class="workspace-kanshan-dialog__avatar" aria-hidden="true">山</span>
            <p class="workspace-kanshan-dialog__bubble workspace-kanshan-dialog__bubble--kanshan">
              {{ kanshanGuidance }}
            </p>
          </div>
        </div>

        <div class="workspace-kanshan-dialog__actions">
          <span>看山会继续根据创作流回应你</span>
          <button type="button" @click="showKanshanDialog = false">知道了</button>
        </div>
      </div>
    </section>
  </SubWindow>
</template>

<style scoped>
.integrated-backpack-window { width: 100%; min-width: 0; }
.workspace-kanshan-dialog {
  position: relative;
  display: flex;
  width: 100%;
  min-height: min(440px, calc(82vh - 60px));
  align-items: stretch;
  overflow: hidden;
  background:
    linear-gradient(rgba(120, 79, 43, 0.045) 1px, transparent 1px) 0 0 / 16px 16px,
    linear-gradient(90deg, rgba(120, 79, 43, 0.04) 1px, transparent 1px) 0 0 / 16px 16px,
    #f8efd8;
  color: #4b3324;
}
.workspace-kanshan-dialog__content {
  position: relative;
  z-index: 2;
  display: flex;
  box-sizing: border-box;
  width: calc(100% - 188px);
  max-width: 448px;
  flex-direction: column;
  justify-content: center;
  padding: 26px 18px 24px 34px;
}
.workspace-kanshan-dialog__identity {
  display: flex;
  align-items: center;
  gap: 16px;
}
.workspace-kanshan-dialog__identity p {
  margin: 0 0 6px;
  color: var(--kanshan-dialog-accent, #7dd5c8);
  font: 900 0.64rem/1 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.13em;
}
.workspace-kanshan-dialog__identity h4 {
  margin: 0;
  color: #4a3022;
  font-size: clamp(1.15rem, 2vw, 1.5rem);
  line-height: 1.2;
}
.workspace-kanshan-dialog__region {
  display: flex;
  align-items: center;
  gap: 9px;
  width: fit-content;
  margin: 14px 0 10px;
  border: 1px solid color-mix(in srgb, var(--kanshan-dialog-accent, #7dd5c8) 48%, transparent);
  border-radius: 999px;
  padding: 7px 11px;
  background: rgba(255, 250, 225, 0.84);
}
.workspace-kanshan-dialog__region span {
  color: #806149;
  font: 800 0.6rem/1 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.08em;
}
.workspace-kanshan-dialog__region strong {
  color: var(--kanshan-dialog-accent, #a8f0e5);
  font-size: 0.8rem;
}
.workspace-kanshan-dialog__directive {
  border-left: 3px solid var(--kanshan-dialog-accent, #67baae);
  padding: 12px 15px;
  background: rgba(255, 250, 226, 0.92);
  box-shadow: 3px 4px 0 rgba(86, 50, 34, 0.2);
}
.workspace-kanshan-dialog__state {
  margin: 0 0 9px;
  color: var(--kanshan-dialog-accent, #7dd5c8);
  font: 800 0.59rem/1.25 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.07em;
}
.workspace-kanshan-dialog__message { margin: 0; color: #442c1c; font-size: 0.96rem; font-weight: 700; line-height: 1.65; }
.workspace-kanshan-dialog__directive small { display: block; margin-top: 11px; color: #7b6552; font-size: 0.7rem; line-height: 1.5; }
.workspace-kanshan-dialog__conversation {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}
.workspace-kanshan-dialog__bubble-row { display: flex; align-items: flex-end; gap: 7px; }
.workspace-kanshan-dialog__bubble-row--player { justify-content: flex-end; }
.workspace-kanshan-dialog__bubble {
  max-width: 84%;
  margin: 0;
  border: 1px solid transparent;
  padding: 8px 11px;
  font-size: 0.74rem;
  font-weight: 700;
  line-height: 1.5;
  box-shadow: 2px 3px 0 rgba(79, 46, 30, 0.13);
}
.workspace-kanshan-dialog__bubble--player {
  border-color: #438d8a;
  border-radius: 13px 13px 3px 13px;
  background: #6bb6b1;
  color: #173f3e;
}
.workspace-kanshan-dialog__bubble--kanshan {
  border-color: #d2b889;
  border-radius: 13px 13px 13px 3px;
  background: #fffaf0;
  color: #4b3324;
}
.workspace-kanshan-dialog__avatar {
  display: grid;
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  place-items: center;
  border: 2px solid #6b3e2b;
  border-radius: 50%;
  background: #efd38d;
  color: #573724;
  font-size: 0.68rem;
  font-weight: 900;
}
.workspace-kanshan-dialog__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 14px;
  border-top: 1px dashed rgba(107, 62, 43, 0.3);
  padding-top: 11px;
}
.workspace-kanshan-dialog__actions span { color: #806149; font-size: 0.62rem; font-weight: 700; }
.workspace-kanshan-dialog__actions button {
  flex: 0 0 auto;
  border: 1px solid var(--kanshan-dialog-accent, #67baae);
  border-radius: 3px;
  padding: 8px 14px;
  background: #6b3e2b;
  color: #fff8df;
  font: 800 0.68rem/1 ui-monospace, SFMono-Regular, Consolas, monospace;
  cursor: pointer;
}
.workspace-kanshan-dialog__actions button:hover { filter: brightness(1.18); }
.workspace-kanshan-dialog__star-sticker,
.workspace-kanshan-dialog__planet-sticker,
.workspace-kanshan-dialog__character-sticker { position: absolute; z-index: 4; object-fit: contain; pointer-events: none; user-select: none; }
.workspace-kanshan-dialog__star-sticker { top: 24px; right: 26px; width: 50px; transform: rotate(-12deg); }
.workspace-kanshan-dialog__star-sticker--secondary { top: 78px; right: 137px; width: 28px; opacity: 0.7; transform: rotate(17deg); }
.workspace-kanshan-dialog__planet-sticker { top: 88px; right: 48px; width: 96px; transform: rotate(8deg); }
.workspace-kanshan-dialog__character-sticker { right: 5px; bottom: -15px; width: 178px; filter: drop-shadow(5px 7px 0 rgba(83, 47, 30, 0.22)); }
.workspace-kanshan-dialog--stargaze .workspace-kanshan-dialog__star-sticker { top: 25px; right: 125px; width: 46px; transform: rotate(14deg); }
.workspace-kanshan-dialog--stargaze .workspace-kanshan-dialog__star-sticker--secondary { top: 56px; right: 42px; width: 35px; opacity: 0.92; transform: rotate(-20deg); }
.workspace-kanshan-dialog--stargaze .workspace-kanshan-dialog__planet-sticker { top: 120px; right: 78px; width: 90px; transform: rotate(-8deg); }
.workspace-kanshan-dialog--explorer .workspace-kanshan-dialog__planet-sticker { top: 24px; right: 27px; width: 104px; transform: rotate(12deg); }
.workspace-kanshan-dialog--explorer .workspace-kanshan-dialog__star-sticker { top: 124px; right: 128px; width: 42px; transform: rotate(-8deg); }
.workspace-kanshan-dialog--explorer .workspace-kanshan-dialog__star-sticker--secondary { top: 172px; right: 42px; width: 25px; opacity: 0.78; }
.workspace-kanshan-dialog--signal .workspace-kanshan-dialog__star-sticker { top: 32px; right: 40px; width: 42px; transform: rotate(18deg); }
.workspace-kanshan-dialog--signal .workspace-kanshan-dialog__star-sticker--secondary { top: 92px; right: 122px; width: 38px; opacity: 0.88; transform: rotate(-14deg); }
.workspace-kanshan-dialog--signal .workspace-kanshan-dialog__planet-sticker { top: 148px; right: 44px; width: 85px; transform: rotate(16deg); }
@media (max-width: 680px) {
  .workspace-kanshan-dialog__content { width: 100%; max-width: none; padding: 28px; }
  .workspace-kanshan-dialog__planet-sticker,
  .workspace-kanshan-dialog__star-sticker--secondary,
  .workspace-kanshan-dialog__character-sticker { display: none; }
  .workspace-kanshan-dialog__star-sticker { top: 10px; right: 12px; width: 34px; opacity: 0.45; }
}
.integrated-backpack-window { height: 100%; }
.integrated-backpack-window :deep(.right-primary-column) { width: 100%; height: 100%; }
.integrated-backpack-window :deep(.right-primary-column .side-panel-sticky) { position: static; height: 100%; max-height: none; overflow: hidden; }
.integrated-backpack-window :deep(.right-primary-column .side-panel-content) { display: grid !important; grid-template-columns: minmax(540px, 1.55fr) minmax(300px, 0.8fr); grid-template-rows: minmax(0, 1fr) auto; align-items: start; gap: 12px; height: 100%; }
.integrated-backpack-window :deep(.right-primary-column .creation-flow-panel) { grid-row: 1 / span 2; grid-column: 1; overflow: visible; }
.integrated-backpack-window :deep(.right-primary-column .creation-flow-panel .workbench-slots) { width: min(100%, 450px); margin: 8px auto; column-gap: 7px; row-gap: 6px; }
.integrated-backpack-window :deep(.right-primary-column .creation-flow-panel .workbench-slot) { width: min(100%, 74px); justify-self: center; }
.integrated-backpack-window :deep(.right-primary-column .backpack-panel) { grid-row: 1; grid-column: 2; max-height: 100%; }
.integrated-backpack-window :deep(.right-primary-column .article-ai-dock--embedded) { grid-row: 2; grid-column: 2; min-height: 154px; }
.integrated-backpack-window :deep(.right-primary-column .backpack-panel) {
  --backpack-slot-width: 46px;
  --backpack-slot-gap: 7px;
  --backpack-grid-padding-x: 14px;
  --backpack-grid-padding-y: 16px;
}
.integrated-backpack-window :deep(.right-primary-column .backpack-slot-grid) {
  grid-template-columns: repeat(5, var(--backpack-slot-width));
}
.integrated-backpack-window :deep(.right-primary-column .backpack-scroll-area) { max-height: none; overflow: hidden; }
@media (max-width: 720px) {
  .integrated-backpack-window :deep(.right-primary-column .side-panel-content) { grid-template-columns: 1fr; }
  .integrated-backpack-window :deep(.right-primary-column .creation-flow-panel),
  .integrated-backpack-window :deep(.right-primary-column .backpack-panel) { grid-column: 1; grid-row: auto; }
}
</style>
