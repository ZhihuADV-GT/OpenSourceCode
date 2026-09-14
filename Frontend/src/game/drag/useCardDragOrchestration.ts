import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useCreationFlowStore } from '../../stores/creationFlow'
import type { CreationFlowTransferFlight, CreationFlowTransferRequest } from '../../types/collectionMotion'
import type { CardDragEndRequest, CardDragMoveRequest, CardDragStartRequest, CardDragState } from '../../types/cardDrag'
import { isCreationFlowSlotIndex } from '../../types/creationFlow'

const DRAG_THRESHOLD = 7

/**
 * 卡牌拖拽与飞行动画的编排层。
 * 落点通过全局 `[data-creation-drop-target]` 解析，因此 CreationFlow 可以挂在任意位置。
 */
export function useCardDragOrchestration() {
  const creationFlowStore = useCreationFlowStore()

  const pendingCreationArrivalIds = reactive(new Set<string>())
  const transferFlight = ref<CreationFlowTransferFlight | null>(null)
  const transferQueue: CreationFlowTransferRequest[] = []
  const dragState = ref<CardDragState | null>(null)
  const suppressClickMaterialId = ref<string | null>(null)
  let queuedDragMove: CardDragMoveRequest | null = null
  let dragMoveFrame: number | null = null
  let suppressClickTimer: number | null = null

  function startNextTransfer() {
    const nextRequest = transferQueue.shift()

    if (!nextRequest) {
      transferFlight.value = null
      return
    }

    if (creationFlowStore.getMaterialAt(nextRequest.targetSlotIndex) !== nextRequest.materialId) {
      pendingCreationArrivalIds.delete(nextRequest.materialId)
      startNextTransfer()
      return
    }

    transferFlight.value = {
      ...nextRequest,
      targetSlotIndex: nextRequest.targetSlotIndex,
    }
  }

  function handleCreationFlowTransfer(request: CreationFlowTransferRequest) {
    pendingCreationArrivalIds.add(request.materialId)

    if (transferFlight.value) {
      transferQueue.push(request)
      return
    }

    transferQueue.unshift(request)
    startNextTransfer()
  }

  function handleTransferComplete() {
    if (transferFlight.value) {
      pendingCreationArrivalIds.delete(transferFlight.value.materialId)
    }

    transferFlight.value = null
    startNextTransfer()
  }

  function toCardRect(rect: DOMRect): CardDragState['sourceRect'] {
    return {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    }
  }

  function getTargetAtPointer(pointerX: number, pointerY: number) {
    const targets = [...document.querySelectorAll<HTMLElement>('[data-creation-drop-target]')]

    return targets
      .map(element => ({
        element,
        index: Number(element.dataset.creationSlotIndex),
        rect: element.getBoundingClientRect(),
      }))
      .find(({ rect }) => (
        pointerX >= rect.left
        && pointerX <= rect.right
        && pointerY >= rect.top
        && pointerY <= rect.bottom
      )) ?? null
  }

  function updateDragFromPointer(request: CardDragMoveRequest) {
    const state = dragState.value
    if (!state || state.materialId !== request.materialId || state.pointerId !== request.pointerId) {
      return
    }

    const distance = Math.hypot(request.pointerX - state.startX, request.pointerY - state.startY)
    if (state.phase === 'pressing' && distance < DRAG_THRESHOLD) {
      return
    }

    if (state.phase === 'pressing') {
      state.phase = 'dragging'
      suppressClickMaterialId.value = state.materialId
      if (suppressClickTimer !== null) {
        window.clearTimeout(suppressClickTimer)
        suppressClickTimer = null
      }
    }

    if (state.phase !== 'dragging') {
      return
    }

    const target = getTargetAtPointer(request.pointerX, request.pointerY)
    state.pointerX = request.pointerX
    state.pointerY = request.pointerY
    state.displayX = request.pointerX
    state.displayY = request.pointerY - 8
    state.activeTargetIndex = target?.index ?? null
  }

  function flushDragMove() {
    dragMoveFrame = null
    const request = queuedDragMove
    queuedDragMove = null
    if (request) {
      updateDragFromPointer(request)
    }
  }

  function handleDragStart(request: CardDragStartRequest) {
    if (dragState.value) {
      return
    }

    dragState.value = {
      ...request,
      pointerX: request.startX,
      pointerY: request.startY,
      displayX: request.sourceRect.left + request.sourceRect.width / 2,
      displayY: request.sourceRect.top + request.sourceRect.height / 2,
      activeTargetIndex: null,
      phase: 'pressing',
    }
  }

  function handleDragMove(request: CardDragMoveRequest) {
    const state = dragState.value
    if (!state || state.materialId !== request.materialId || state.pointerId !== request.pointerId) {
      return
    }

    queuedDragMove = request
    if (dragMoveFrame === null) {
      dragMoveFrame = window.requestAnimationFrame(flushDragMove)
    }
  }

  function getTargetRect(index: number) {
    return [...document.querySelectorAll<HTMLElement>('[data-creation-drop-target]')]
      .find(element => Number(element.dataset.creationSlotIndex) === index)
      ?.getBoundingClientRect() ?? null
  }

  function refreshCreationSourceRect(state: CardDragState) {
    if (state.sourceType !== 'creation' || state.sourceSlotIndex === null) {
      return
    }

    const sourceElement = document.querySelector<HTMLElement>(
      `[data-creation-slot-index="${state.sourceSlotIndex}"]`,
    )
    const sourceRect = sourceElement?.getBoundingClientRect()
    if (sourceRect) {
      state.sourceRect = toCardRect(sourceRect)
    }
  }

  function setSnapBack() {
    const state = dragState.value
    if (!state || state.phase !== 'dragging') {
      return
    }

    refreshCreationSourceRect(state)
    state.phase = 'snap-back'
    state.activeTargetIndex = null
    state.targetRect = undefined
  }

  function scheduleSuppressClickClear(materialId: string) {
    if (suppressClickTimer !== null) {
      window.clearTimeout(suppressClickTimer)
    }

    suppressClickTimer = window.setTimeout(() => {
      if (suppressClickMaterialId.value === materialId) {
        suppressClickMaterialId.value = null
      }
      suppressClickTimer = null
    }, 0)
  }

  function handleDragEnd(request: CardDragEndRequest) {
    if (dragMoveFrame !== null) {
      window.cancelAnimationFrame(dragMoveFrame)
      dragMoveFrame = null
    }
    queuedDragMove = null

    const state = dragState.value
    if (!state || state.materialId !== request.materialId || state.pointerId !== request.pointerId) {
      return
    }

    if (state.phase === 'pressing') {
      dragState.value = null
      return
    }

    if (state.phase !== 'dragging') {
      return
    }

    updateDragFromPointer({
      materialId: request.materialId,
      pointerId: request.pointerId,
      pointerX: request.pointerX,
      pointerY: request.pointerY,
    })
    scheduleSuppressClickClear(state.materialId)

    const targetIndex = state.activeTargetIndex
    const targetRect = targetIndex === null ? null : getTargetRect(targetIndex)
    const canDrop = !request.cancelled && targetIndex !== null && targetRect !== null

    if (canDrop) {
      if (isCreationFlowSlotIndex(targetIndex)) {
        const sourceSlotIndex = state.sourceType === 'creation' ? state.sourceSlotIndex : null
        if (sourceSlotIndex === targetIndex) {
          dragState.value = null
          return
        }

        const updated = sourceSlotIndex === null
          ? creationFlowStore.placeMaterial(state.materialId, targetIndex)
          : isCreationFlowSlotIndex(sourceSlotIndex)
            ? creationFlowStore.moveMaterial(sourceSlotIndex, targetIndex)
            : false
        if (updated) {
          pendingCreationArrivalIds.add(state.materialId)
          state.phase = 'snapping'
          state.targetRect = toCardRect(targetRect)
          return
        }
      }
    }

    setSnapBack()
  }

  function pulseCreationFlowSlot(slotIndex: number) {
    const target = document.querySelector<HTMLElement>(`[data-creation-slot-index="${slotIndex}"]`)
    if (!target) {
      return
    }

    target.classList.remove('creation-arrival-pulse')
    void target.offsetWidth
    target.classList.add('creation-arrival-pulse')
    window.setTimeout(() => target.classList.remove('creation-arrival-pulse'), 220)
  }

  function handleDragSettled(materialId: string) {
    const state = dragState.value
    if (!state || state.materialId !== materialId) {
      return
    }

    if (state.phase === 'snapping' && state.activeTargetIndex !== null) {
      pendingCreationArrivalIds.delete(materialId)
      pulseCreationFlowSlot(state.activeTargetIndex)
    }

    dragState.value = null
  }

  function cancelDrag() {
    const state = dragState.value
    if (state?.phase === 'dragging') {
      scheduleSuppressClickClear(state.materialId)
      setSnapBack()
    }
  }

  function handleKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      cancelDrag()
    }
  }

  const activeDropTargetIndex = computed(() => (
    dragState.value?.phase === 'dragging' ? dragState.value.activeTargetIndex : null
  ))
  const isDragging = computed(() => dragState.value?.phase === 'dragging')
  const draggingMaterialId = computed(() => (
    dragState.value && dragState.value.phase !== 'pressing' ? dragState.value.materialId : null
  ))
  const dragSourceType = computed(() => (
    dragState.value && dragState.value.phase !== 'pressing' ? dragState.value.sourceType : null
  ))

  onMounted(() => window.addEventListener('keydown', handleKeyDown))

  onBeforeUnmount(() => {
    window.removeEventListener('keydown', handleKeyDown)
    if (dragMoveFrame !== null) {
      window.cancelAnimationFrame(dragMoveFrame)
    }
    if (suppressClickTimer !== null) {
      window.clearTimeout(suppressClickTimer)
    }
  })

  return {
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
  }
}
