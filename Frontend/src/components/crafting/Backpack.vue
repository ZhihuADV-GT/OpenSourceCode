<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useCreationFlowStore } from '../../stores/creationFlow'
import { BACKPACK_CAPACITY, useMaterialStore } from '../../stores/material'
import type { CreationFlowTransferRequest } from '../../types/collectionMotion'
import type { CardDragEndRequest, CardDragMoveRequest, CardDragStartRequest } from '../../types/cardDrag'
import type { Material } from '../../types/material'
import CardSlot from './CardSlot.vue'

const BACKPACK_SLOT_COUNT = BACKPACK_CAPACITY

const materialStore = useMaterialStore()
const creationFlowStore = useCreationFlowStore()
const { materials } = storeToRefs(materialStore)
const props = withDefaults(defineProps<{
  pendingArrivalMaterialIds: Set<string>
  draggingMaterialId?: string | null
  suppressClickMaterialId?: string | null
  readOnly?: boolean
}>(), {
  readOnly: false,
})
const emit = defineEmits<{
  (event: 'creation-flow-transfer-request', request: CreationFlowTransferRequest): void
  (event: 'drag-start', request: CardDragStartRequest): void
  (event: 'drag-move', request: CardDragMoveRequest): void
  (event: 'drag-end', request: CardDragEndRequest): void
}>()

const revealedMaterialIds = reactive(new Set<string>())
const revealTimers = new Map<string, number>()
let transferSequence = 0
const pointerSession = ref<{ materialId: string; pointerId: number } | null>(null)

function removeWindowPointerListeners() {
  window.removeEventListener('pointermove', handleWindowPointerMove)
  window.removeEventListener('pointerup', handleWindowPointerUp)
  window.removeEventListener('pointercancel', handleWindowPointerCancel)
}

const slots = computed(() => Array.from({ length: BACKPACK_SLOT_COUNT }, (_, index) => ({
  index,
  material: materials.value[index] ?? null,
})))

function isPending(material: Material | null) {
  return Boolean(material && props.pendingArrivalMaterialIds.has(material.id))
}

function canActivate(material: Material | null) {
  return Boolean(material && !props.readOnly && !isPending(material))
}

function canDrag(material: Material | null) {
  return Boolean(material && canActivate(material) && !isSelected(material))
}

function isSelected(material: Material | null) {
  return Boolean(material && creationFlowStore.hasMaterial(material.id))
}

function activateMaterial(material: Material, sourceEvent: MouseEvent) {
  if (props.suppressClickMaterialId === material.id) {
    return
  }

  const sourceElement = sourceEvent.currentTarget as HTMLElement | null

  if (!sourceElement) {
    return
  }

  const rect = sourceElement.getBoundingClientRect()
  const targetSlotIndex = creationFlowStore.firstEmptySlotIndex

  if (targetSlotIndex === null) {
    creationFlowStore.setFeedback('Creation Flow 已满')
    return
  }

  if (!creationFlowStore.placeMaterial(material.id, targetSlotIndex)) {
    return
  }

  transferSequence += 1
  emit('creation-flow-transfer-request', {
    id: `${material.id}-creation-${Date.now()}-${transferSequence}`,
    materialId: material.id,
    materialType: material.type ?? '素材',
    targetSlotIndex,
    sourceRect: {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    },
  })
}

function handlePointerDown(material: Material, sourceEvent: PointerEvent) {
  if (!canDrag(material)) {
    return
  }

  const sourceElement = sourceEvent.currentTarget as HTMLElement | null
  if (!sourceElement) {
    return
  }

  const rect = sourceElement.getBoundingClientRect()
  pointerSession.value = {
    materialId: material.id,
    pointerId: sourceEvent.pointerId,
  }
  window.addEventListener('pointermove', handleWindowPointerMove)
  window.addEventListener('pointerup', handleWindowPointerUp)
  window.addEventListener('pointercancel', handleWindowPointerCancel)
  emit('drag-start', {
    sourceType: 'backpack',
    sourceSlotIndex: null,
    materialId: material.id,
    materialType: material.type ?? '素材',
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

function markRevealComplete(materialId: string) {
  revealedMaterialIds.add(materialId)
  const timer = window.setTimeout(() => {
    revealedMaterialIds.delete(materialId)
    revealTimers.delete(materialId)
  }, 190)
  revealTimers.set(materialId, timer)
}

watch(() => [...props.pendingArrivalMaterialIds], (pendingIds, previousIds = []) => {
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
  <section class="hud-card backpack-panel hud-pixel-panel">
    <div class="panel-heading">
      <div>
        <p class="panel-eyebrow hud-terminal-label">BACKPACK</p>
      </div>
      <span class="count-badge">{{ materials.length }} / {{ BACKPACK_CAPACITY }}</span>
    </div>

    <div class="backpack-scroll-area">
      <div class="backpack-slot-grid" role="list" aria-label="Backpack inventory slots">
        <div
          v-for="slot in slots"
          :key="`backpack-slot-${slot.index}`"
          class="backpack-slot-cell"
          :class="{
            'backpack-slot-cell--pending': isPending(slot.material),
            'backpack-slot-cell--revealing': slot.material && revealedMaterialIds.has(slot.material.id),
            'backpack-slot-cell--used': isSelected(slot.material),
          }"
          role="listitem"
          :data-backpack-slot-index="slot.index"
          :data-backpack-arrival-target="isPending(slot.material) ? '' : undefined"
          :data-material-id="slot.material?.id"
        >
          <CardSlot
            :card-type="isPending(slot.material) ? undefined : slot.material?.type"
            :card-id="isPending(slot.material) ? undefined : slot.material?.id"
            :source-text="isPending(slot.material) ? undefined : slot.material?.text"
            :occupied="Boolean(slot.material) && !isPending(slot.material)"
            :selected="isSelected(slot.material)"
            :interactive="canActivate(slot.material)"
            :dragging="draggingMaterialId === slot.material?.id"
            variant="backpack"
            :aria-label="slot.material
              ? isSelected(slot.material)
                ? `${slot.material.type ?? '信息点'}当前位于创作流`
                : `将${slot.material.type ?? '信息点'}加入创作流`
              : undefined"
            @activate="slot.material && activateMaterial(slot.material, $event)"
            @pointer-down="slot.material && handlePointerDown(slot.material, $event)"
          />
        </div>
      </div>
    </div>
  </section>
</template>
