<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useCreationFlowStore } from '../../stores/creationFlow'
import { CREATION_FLOW_SLOT_INDICES } from '../../types/creationFlow'
import { useGameStore } from '../../stores/game'
import { useMaterialStore } from '../../stores/material'
import { useWorkbenchStore } from '../../stores/workbench'
import { isNonZeroVector } from '../../types/mapTypes'
import type { CardDragEndRequest, CardDragMoveRequest, CardDragStartRequest } from '../../types/cardDrag'
import type { Material } from '../../types/material'
import CardSlot from './CardSlot.vue'

type CreationSubmitState = 'idle' | 'submitting' | 'success' | 'error'

const props = defineProps<{
  pendingCreationArrivalIds: Set<string>
  activeDropTargetIndex?: number | null
  isDragging?: boolean
  draggingMaterialId?: string | null
  dragSourceType?: 'backpack' | 'creation' | null
}>()

const emit = defineEmits<{
  (event: 'drag-start', request: CardDragStartRequest): void
  (event: 'drag-move', request: CardDragMoveRequest): void
  (event: 'drag-end', request: CardDragEndRequest): void
  (event: 'submitted'): void
  (event: 'submit-blocked-zero'): void
  (event: 'open-recipe-book'): void
}>()

const creationFlowStore = useCreationFlowStore()
const materialStore = useMaterialStore()
const { slots } = storeToRefs(creationFlowStore)
const { materials } = storeToRefs(materialStore)
const revealedMaterialIds = reactive(new Set<string>())
const revealTimers = new Map<string, number>()
const submitState = ref<CreationSubmitState>('idle')
const submitFeedback = ref('')
const pointerSession = ref<{ materialId: string; slotIndex: number; pointerId: number } | null>(null)

const renderedSlots = computed(() => slots.value.map(slot => ({
  ...slot,
  material: materials.value.find(item => item.id === slot.materialId) ?? null,
})))

function isPending(material: Material | null) {
  return Boolean(material && props.pendingCreationArrivalIds.has(material.id))
}

function markRevealComplete(materialId: string) {
  revealedMaterialIds.add(materialId)
  const timer = window.setTimeout(() => {
    revealedMaterialIds.delete(materialId)
    revealTimers.delete(materialId)
  }, 190)
  revealTimers.set(materialId, timer)
}

function removeMaterial(slotIndex: typeof slots.value[number]['index']) {
  creationFlowStore.removeMaterial(slotIndex)
}

function formatSlotLabel(slotIndex: typeof slots.value[number]['index']) {
  return String(slotIndex).padStart(2, '0')
}

function removeWindowPointerListeners() {
  window.removeEventListener('pointermove', handleWindowPointerMove)
  window.removeEventListener('pointerup', handleWindowPointerUp)
  window.removeEventListener('pointercancel', handleWindowPointerCancel)
}

function handlePointerDown(slot: typeof renderedSlots.value[number], sourceEvent: PointerEvent) {
  if (!slot.material || isPending(slot.material) || props.isDragging) {
    return
  }

  const sourceElement = sourceEvent.currentTarget as HTMLElement | null
  if (!sourceElement) {
    return
  }

  const rect = sourceElement.getBoundingClientRect()
  pointerSession.value = {
    materialId: slot.material.id,
    slotIndex: slot.index,
    pointerId: sourceEvent.pointerId,
  }
  window.addEventListener('pointermove', handleWindowPointerMove)
  window.addEventListener('pointerup', handleWindowPointerUp)
  window.addEventListener('pointercancel', handleWindowPointerCancel)
  emit('drag-start', {
    sourceType: 'creation',
    sourceSlotIndex: slot.index,
    materialId: slot.material.id,
    materialType: slot.material.type ?? '素材',
    pointerId: sourceEvent.pointerId,
    sourceRect: {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    },
    startX: sourceEvent.clientX,
    startY: sourceEvent.clientY,
  })
}

function handleWindowPointerMove(sourceEvent: PointerEvent) {
  const session = pointerSession.value
  if (!session || session.pointerId !== sourceEvent.pointerId) {
    return
  }

  emit('drag-move', {
    materialId: session.materialId,
    pointerId: sourceEvent.pointerId,
    pointerX: sourceEvent.clientX,
    pointerY: sourceEvent.clientY,
  })
}

function handleWindowPointerUp(sourceEvent: PointerEvent) {
  const session = pointerSession.value
  if (!session || session.pointerId !== sourceEvent.pointerId) {
    return
  }

  emit('drag-end', {
    materialId: session.materialId,
    pointerId: sourceEvent.pointerId,
    pointerX: sourceEvent.clientX,
    pointerY: sourceEvent.clientY,
  })
  pointerSession.value = null
  removeWindowPointerListeners()
}

function handleWindowPointerCancel(sourceEvent: PointerEvent) {
  const session = pointerSession.value
  if (!session || session.pointerId !== sourceEvent.pointerId) {
    return
  }

  emit('drag-end', {
    materialId: session.materialId,
    pointerId: sourceEvent.pointerId,
    pointerX: sourceEvent.clientX,
    pointerY: sourceEvent.clientY,
    cancelled: true,
  })
  pointerSession.value = null
  removeWindowPointerListeners()
}

function getSubmitErrorMessage(error: unknown) {
  const errorMessage = error instanceof Error
    ? error.message
    : typeof error === 'object' && error !== null && 'message' in error
      ? String(error.message)
      : ''

  if (errorMessage.includes('Network Error') || errorMessage.includes('timeout')) {
    return '无法连接后端，请确认后端服务已启动'
  }

  return '提交失败，请稍后重试'
}

async function submitCreationFlow() {
  if (submitState.value === 'submitting') {
    return
  }

  const gameStore = useGameStore()
  const workbenchStore = useWorkbenchStore()

  submitState.value = 'submitting'
  submitFeedback.value = 'Submitting...'

  try {
    // Step 1: 最终向量同步 —— 确保前端持有最新的 instant_vector
    const synced = await workbenchStore.syncSlotsToBackend()
    if (!synced) {
      throw new Error('Vector sync failed')
    }

    const finalVector = [...workbenchStore.currentVector] as [number, number]
    if (!isNonZeroVector(finalVector)) {
      // 已提交待出发（map-ready）时绝不能作废本局方向：invalidateRoundVector 会连带清掉
      // roundVector / pendingKanshanMove / localSettlement，知北针将永久无法出发。
      // 卡槽被自愈清空后再点提交，正好会落到这个零向量分支。
      const alreadyCommitted = gameStore.isMapReady
      if (!alreadyCommitted) {
        gameStore.invalidateRoundVector()
      }
      submitState.value = 'error'
      submitFeedback.value = alreadyCommitted
        ? '本局方向已提交 · 若出发按钮不可用，请重新配卡后再提交'
        : '当前组合尚未形成有效方向，请调整素材后再提交'
      emit('submit-blocked-zero')
      return
    }

    // v5: 不再调用 submitOutcome() 和本地结算,直接进入文章生成流程
    const committedMaterialIds = [...new Set(
      creationFlowStore.slots
        .map(slot => slot.materialId)
        .filter((materialId): materialId is string => materialId !== null),
    )]
        
    // 【调试】记录提交的卡牌ID
    if (import.meta.env.DEV) {
      console.log('[CreationFlow] 准备提交卡牌:', committedMaterialIds.length, '张')
      console.log('  slots数量:', creationFlowStore.slots.length)
      console.log('  slots内容:', creationFlowStore.slots.map(s => ({ slot: s.index, materialId: s.materialId })))
      console.log('  提取的卡牌ID:', committedMaterialIds)
    }
        
    if (!gameStore.commitRoundVector(null, finalVector, committedMaterialIds)) {
      submitState.value = 'error'
      submitFeedback.value = '当前组合尚未形成有效方向，请调整素材后再提交'
      emit('submit-blocked-zero')
      return
    }
    submitState.value = 'success'
    submitFeedback.value = '已提交 · 点击看山旁的感叹号查看本局随笔'
    emit('submitted')
  } catch (error) {
    console.error('[CreationFlow] 创作流提交失败:', error)
    submitState.value = 'error'
    submitFeedback.value = getSubmitErrorMessage(error)
  }
}

watch(() => [...props.pendingCreationArrivalIds], (pendingIds, previousIds = []) => {
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
  removeWindowPointerListeners()
  for (const timer of revealTimers.values()) {
    window.clearTimeout(timer)
  }
})
</script>

<template>
  <section
    class="hud-card workbench-panel creation-flow-panel hud-pixel-panel"
    :class="{
      'workbench-panel--loading': props.pendingCreationArrivalIds.size > 0,
      'workbench-panel--has-cards': creationFlowStore.filledCount > 0,
      'workbench-panel--dragging': props.isDragging,
    }"
    aria-label="Creation Flow"
  >
    <div class="panel-heading">
      <div>
        <p class="panel-eyebrow hud-terminal-label">CREATION_FLOW</p>
      </div>
      <button
        class="status-chip creation-clear-button"
        type="button"
        :disabled="creationFlowStore.filledCount === 0"
        aria-label="清空创作流"
        @click="creationFlowStore.clear"
      >清空</button>
    </div>

    <div class="creation-flow-body">
      <!-- 配方书按钮：absolute 悬浮于面板右下角，不占卡槽行内空间 -->
      <button
        class="recipe-book-slot"
        type="button"
        aria-label="创作流配方书"
        title="创作流配方书"
        @click="emit('open-recipe-book')"
      >
        <span class="recipe-book-slot__emoji">📕</span>
      </button>

      <div class="workbench-slots" role="list" aria-label="Creation Flow material slots">
      <div
        v-for="slot in renderedSlots"
        :key="`creation-slot-${slot.index}`"
        class="workbench-slot"
        :class="{
          'workbench-slot--pending': isPending(slot.material),
          'workbench-slot--revealing': slot.material && revealedMaterialIds.has(slot.material.id),
          'workbench-slot--drop-ready': props.activeDropTargetIndex === slot.index
            && (!slot.material || props.dragSourceType === 'creation')
            && props.pendingCreationArrivalIds.size === 0,
        }"
        role="listitem"
        :aria-label="`创作流第 ${formatSlotLabel(slot.index)} 个卡槽`"
        :data-creation-slot-index="slot.index"
        :data-creation-slot-material-id="slot.materialId ?? undefined"
        :data-creation-slot-state="slot.material
          ? isPending(slot.material) ? 'pending' : 'occupied'
          : props.activeDropTargetIndex === slot.index ? 'drop-ready' : 'empty'"
        :data-creation-drop-target="isPending(slot.material) ? undefined : ''"
        :data-creation-arrival-target="isPending(slot.material) ? '' : undefined"
        :data-material-id="slot.materialId ?? undefined"
      >
        <span class="creation-flow-slot-number" aria-hidden="true">{{ formatSlotLabel(slot.index) }}</span>
        <CardSlot
          :card-type="isPending(slot.material) ? undefined : slot.material?.type"
          :card-id="isPending(slot.material) ? undefined : slot.material?.id"
          :source-text="isPending(slot.material) ? undefined : slot.material?.text"
          compact
          :occupied="Boolean(slot.material) && !isPending(slot.material)"
          :interactive="Boolean(slot.material) && !isPending(slot.material)"
          :dragging="props.draggingMaterialId === slot.material?.id"
          :aria-label="slot.material ? `从创作流第 ${formatSlotLabel(slot.index)} 个槽位拖动卡牌` : undefined"
          variant="workbench"
          @pointer-down="slot.material && handlePointerDown(slot, $event)"
        />
        <button
          v-if="slot.material && !isPending(slot.material)"
          class="workbench-remove-button"
          type="button"
          :aria-label="`从创作流第 ${slot.index} 个槽位移除素材`"
          @click="removeMaterial(slot.index)"
        >×</button>
      </div>
      </div>
    </div>

    <div class="creation-submit-area">
      <button
        class="workbench-play-button creation-submit-button"
        type="button"
        :disabled="submitState === 'submitting'"
        :aria-busy="submitState === 'submitting'"
        :aria-label="submitState === 'submitting' ? '正在激活知北针' : '激活知北针'"
        :title="submitState === 'submitting' ? '正在激活知北针' : '激活知北针'"
        @click="submitCreationFlow"
      >{{ submitState === 'submitting' ? '正在激活…' : '激活知北针' }}</button>
      <p
        v-if="submitFeedback"
        class="creation-submit-feedback"
        :class="`creation-submit-feedback--${submitState}`"
        :data-creation-submit-state="submitState"
        role="status"
      >{{ submitFeedback }}</p>
    </div>

    <p v-if="creationFlowStore.feedback" class="workbench-feedback" role="status">
      {{ creationFlowStore.feedback }}
    </p>
  </section>
</template>
