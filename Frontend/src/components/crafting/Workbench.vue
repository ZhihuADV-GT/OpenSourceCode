<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { onBeforeUnmount, reactive, watch } from 'vue'
import { getMaterialCardAsset } from '../../data/cardAssets'
import { evaluateCombination } from '../../services/combinationService'
import { useMaterialStore } from '../../stores/material'
import { useWorkbenchStore } from '../../stores/workbench'
import type { Article } from '../../types/article'
import { CREATION_FLOW_SLOT_INDICES } from '../../types/creationFlow'
import type { CreationFlowSlot } from '../../types/creationFlow'
import type { Material } from '../../types/material'
import CardSlot from './CardSlot.vue'

const props = defineProps<{
  article: Article
  pendingWorkbenchArrivalIds: Set<string>
  activeDropTargetIndex?: number | null
  isDragging?: boolean
  creationFlow?: boolean
}>()

const materialStore = useMaterialStore()
const workbenchStore = useWorkbenchStore()
const { materials } = storeToRefs(materialStore)
const { selectedMaterialIds, feedback, lastResult } = storeToRefs(workbenchStore)
const revealedMaterialIds = reactive(new Set<string>())
const revealTimers = new Map<string, number>()

const selectedMaterials = computed(() => selectedMaterialIds.value
  .map(id => materials.value.find(material => material.id === id))
  .filter((material): material is Material => Boolean(material)))
const pendingArrivalCount = computed(() => props.pendingWorkbenchArrivalIds.size)
const slotCount = computed(() => props.creationFlow ? CREATION_FLOW_SLOT_INDICES.length : workbenchStore.maxMaterials)
const creationFlowSlotIndices = CREATION_FLOW_SLOT_INDICES

const creationFlowSlots = computed<CreationFlowSlot[]>(() => creationFlowSlotIndices.map(index => ({
  index,
  materialId: selectedMaterials.value[index - 1]?.id ?? null,
})))

const slots = computed(() => Array.from({ length: slotCount.value }, (_, index) => (
  selectedMaterials.value[index] ?? null
)))

function isGameplaySlot(index: number) {
  return index < workbenchStore.maxMaterials
}

function isDropTarget(index: number, material: Material | null) {
  return isGameplaySlot(index) && !material
}

function isCreationDropTarget(index: number, material: Material | null) {
  return Boolean(props.creationFlow && !material && creationFlowSlots.value[index]?.index)
}

function isPending(material: Material | null) {
  return Boolean(material && props.pendingWorkbenchArrivalIds.has(material.id))
}

function markRevealComplete(materialId: string) {
  revealedMaterialIds.add(materialId)
  const timer = window.setTimeout(() => {
    revealedMaterialIds.delete(materialId)
    revealTimers.delete(materialId)
  }, 190)
  revealTimers.set(materialId, timer)
}

watch(() => [...props.pendingWorkbenchArrivalIds], (pendingIds, previousIds = []) => {
  const pending = new Set(pendingIds)

  for (const materialId of previousIds) {
    if (!pending.has(materialId)) {
      const previousTimer = revealTimers.get(materialId)
      if (previousTimer !== undefined) {
        window.clearTimeout(previousTimer)
      }
      markRevealComplete(materialId)
    }
  }
})

onBeforeUnmount(() => {
  for (const timer of revealTimers.values()) {
    window.clearTimeout(timer)
  }
})

const playHint = computed(() => {
  if (workbenchStore.selectedCount === 0) {
    return '请选择至少 2 张素材'
  }

  if (workbenchStore.selectedCount === 1) {
    return '还需要至少 1 张素材'
  }

  return ''
})

function removeMaterial(materialId: string) {
  workbenchStore.removeMaterial(materialId)
}

function formatSlotLabel(slotIndex: number) {
  return String(slotIndex).padStart(2, '0')
}

function playCombination() {
  if (!workbenchStore.canPlay) {
    workbenchStore.setFeedback(playHint.value)
    return
  }

  workbenchStore.setLastResult(
    evaluateCombination(selectedMaterials.value, props.article.targetValue ?? 0),
  )
}

function resultLabel(result: NonNullable<typeof lastResult.value>['result']) {
  return {
    success: '判定成功',
    partial: '接近成功',
    fail: '判定失败',
  }[result]
}
</script>

<template>
  <section
    class="hud-card workbench-panel hud-pixel-panel"
    :class="{
      'creation-flow-panel': props.creationFlow,
      'workbench-panel--loading': pendingArrivalCount > 0,
      'workbench-panel--ready': workbenchStore.canPlay && pendingArrivalCount === 0,
      'workbench-panel--full': workbenchStore.selectedCount === workbenchStore.maxMaterials
        && pendingArrivalCount === 0,
    }"
  >
    <div class="panel-heading">
      <div>
        <p class="panel-eyebrow hud-terminal-label">{{ props.creationFlow ? 'CREATION_FLOW' : 'WORKBENCH' }}</p>
        <h2>{{ props.creationFlow ? 'Creation Flow' : 'Workbench' }}</h2>
      </div>
      <span
        class="status-chip"
        :class="workbenchStore.canPlay ? '' : 'status-chip-muted'"
        aria-live="polite"
      >
        <template v-if="pendingArrivalCount > 0">
          <span class="pixel-loading-indicator" aria-hidden="true">□□■</span>
          <span>LOADING {{ pendingArrivalCount }}</span>
        </template>
        <template v-else-if="workbenchStore.canPlay">
          <span class="pixel-state-marker" aria-hidden="true">■</span>
          <span>READY</span>
        </template>
        <template v-else-if="props.creationFlow">{{ CREATION_FLOW_SLOT_INDICES.length }} SLOTS</template>
        <template v-else>{{ selectedMaterialIds.length }}/{{ workbenchStore.maxMaterials }}</template>
      </span>
    </div>

    <div class="workbench-slots" role="list" aria-label="Workbench material slots">
      <div
        v-for="(material, index) in slots"
        :key="`slot-${index}`"
        class="workbench-slot"
        :class="{
        'workbench-slot--pending': isPending(material),
        'workbench-slot--revealing': material && revealedMaterialIds.has(material.id),
        'workbench-slot--drop-ready': props.activeDropTargetIndex === index
          && !material
          && pendingArrivalCount === 0,
        'workbench-slot--locked': props.isDragging
          && !material
          && props.activeDropTargetIndex !== index,
      }"
        role="listitem"
        :aria-label="props.creationFlow
          ? `创作流第 ${formatSlotLabel(index + 1)} 个卡槽`
          : `工作台第 ${index + 1} 个卡槽`"
        :data-workbench-slot-index="index"
        :data-workbench-slot-state="material
          ? isPending(material) ? 'pending' : 'occupied'
          : props.activeDropTargetIndex === index ? 'drop-ready' : props.isDragging ? 'locked' : 'empty'"
        :data-workbench-drop-target="isDropTarget(index, material) ? '' : undefined"
        :data-creation-slot-index="props.creationFlow ? index + 1 : undefined"
        :data-creation-slot-material-id="props.creationFlow ? creationFlowSlots[index]?.materialId ?? undefined : undefined"
        :data-creation-drop-target="isCreationDropTarget(index, material) ? '' : undefined"
        :data-workbench-arrival-target="isPending(material) ? '' : undefined"
        :data-material-id="material?.id"
      >
        <span v-if="props.creationFlow" class="creation-flow-slot-number" aria-hidden="true">{{ formatSlotLabel(index + 1) }}</span>
        <CardSlot
          :image-src="isPending(material) ? undefined : material ? getMaterialCardAsset(material.type) : undefined"
          :occupied="Boolean(material) && !isPending(material)"
          variant="workbench"
        />
        <button
          v-if="material && !isPending(material)"
          class="workbench-remove-button"
          type="button"
          :aria-label="`从工作台移除${material.type ?? '信息点'}`"
          @click="removeMaterial(material.id)"
        >×</button>
      </div>
    </div>

    <template v-if="!props.creationFlow">
      <p v-if="feedback || playHint" class="workbench-feedback" role="status">
        {{ feedback || playHint }}
      </p>
      <button
        class="secondary-button workbench-play-button"
        :class="{ 'workbench-play-button--ready': workbenchStore.canPlay && pendingArrivalCount === 0 }"
        type="button"
        :disabled="!workbenchStore.canPlay"
        @click="playCombination"
        aria-label="组合出牌"
      ><span aria-hidden="true">&gt;</span> COMBINE</button>

      <section
        v-if="lastResult"
        class="combination-result"
        :class="`combination-result-${lastResult.result}`"
        aria-label="Combination result"
      >
        <div class="combination-result-heading">
          <div>
            <p class="panel-eyebrow">Local numeric judge</p>
            <h3>回应判定</h3>
          </div>
          <strong :class="`result-${lastResult.result}`">{{ resultLabel(lastResult.result) }}</strong>
        </div>
        <div class="combination-score" aria-label="Final value and target value">
          <strong>{{ lastResult.finalValue }}</strong>
          <span>/ {{ lastResult.targetValue }}</span>
        </div>
        <p class="combination-result-materials">
          使用素材：{{ selectedMaterials.map(material => material.type ?? '信息点').join('、') }}
        </p>
        <dl class="combination-result-values">
          <div><dt>基础值</dt><dd>{{ lastResult.baseValue }}</dd></div>
          <div><dt>组合</dt><dd>{{ lastResult.ruleLabel }}</dd></div>
          <div><dt>组合加成</dt><dd>+{{ lastResult.combinationBonus }}</dd></div>
          <div><dt>最终值</dt><dd>{{ lastResult.finalValue }}</dd></div>
          <div><dt>目标值</dt><dd>{{ lastResult.targetValue }}</dd></div>
        </dl>
      </section>
      <section v-else class="combination-empty-state" aria-label="Combination result pending">
        <span class="combination-empty-icon" aria-hidden="true">◌</span>
        <span>等待组合出牌</span>
      </section>
    </template>
  </section>
</template>
