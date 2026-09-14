<script setup lang="ts">
import CardDragOverlay from './CardDragOverlay.vue'
import CardTransferOverlay from './CardTransferOverlay.vue'
import Backpack from './Backpack.vue'
import CreationFlow from './CreationFlow.vue'
import { useCardDragOrchestration } from '../../game/drag/useCardDragOrchestration'

const {
  pendingCreationArrivalIds,
  transferFlight,
  dragState,
  suppressClickMaterialId,
  activeDropTargetIndex,
  isDragging,
  draggingMaterialId,
  dragSourceType,
  handleCreationFlowTransfer,
  handleTransferComplete,
  handleDragStart,
  handleDragMove,
  handleDragEnd,
  handleDragSettled,
} = useCardDragOrchestration()

defineProps<{
  pendingArrivalMaterialIds: Set<string>
}>()

const emit = defineEmits<{
  submitted: []
  'submit-blocked-zero': []
  'open-recipe-book': []
}>()
</script>

<template>
  <aside class="right-primary-column" aria-label="Creation and backpack panel">
    <div class="side-panel-sticky">
      <div class="side-panel-content">
        <CreationFlow
          :pending-creation-arrival-ids="pendingCreationArrivalIds"
          :active-drop-target-index="activeDropTargetIndex"
          :is-dragging="isDragging"
          :dragging-material-id="draggingMaterialId"
          :drag-source-type="dragSourceType"
          @drag-start="handleDragStart"
          @drag-move="handleDragMove"
          @drag-end="handleDragEnd"
          @submitted="emit('submitted')"
          @submit-blocked-zero="emit('submit-blocked-zero')"
          @open-recipe-book="emit('open-recipe-book')"
        />
        <Backpack
          :pending-arrival-material-ids="pendingArrivalMaterialIds"
          :dragging-material-id="draggingMaterialId"
          :suppress-click-material-id="suppressClickMaterialId"
          @creation-flow-transfer-request="handleCreationFlowTransfer"
          @drag-start="handleDragStart"
          @drag-move="handleDragMove"
          @drag-end="handleDragEnd"
        />
        <slot name="after-backpack" />
      </div>
    </div>
    <CardDragOverlay :drag="dragState" @settled="handleDragSettled" />
    <CardTransferOverlay :flight="transferFlight" @complete="handleTransferComplete" />
  </aside>
</template>
