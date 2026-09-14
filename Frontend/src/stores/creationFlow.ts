import { defineStore } from 'pinia'
const cardFlowDropSfx = '' // [art-assets disabled]
import {
  CREATION_FLOW_SLOT_INDICES,
  isCreationFlowSlotIndex,
} from '../types/creationFlow'
import type { CreationFlowSlot, CreationFlowSlotIndex } from '../types/creationFlow'
import type { CreationSubmissionRequest } from '../types/creationSubmission'
import { AUDIO_VOLUME, playSfx } from '../services/audioManager'
import { triggerCardPlace } from '../services/kanshanMessages'
import { useMaterialStore as getMaterialStore } from './material'

const STORAGE_KEY = 'game-creation-flow'

function createSlots(): CreationFlowSlot[] {
  return CREATION_FLOW_SLOT_INDICES.map(index => ({ index, materialId: null }))
}

function loadSlots(): CreationFlowSlot[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return createSlots()
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return createSlots()

    const ids = new Map<number, string | null>()
    for (const item of parsed) {
      if (typeof item !== 'object' || item === null) continue
      const record = item as { index?: unknown; materialId?: unknown }
      const index = Number(record.index)
      if (!isCreationFlowSlotIndex(index)) continue
      ids.set(index, typeof record.materialId === 'string' ? record.materialId : null)
    }

    return createSlots().map(slot => ({
      ...slot,
      materialId: ids.get(slot.index) ?? null,
    }))
  } catch {
    return createSlots()
  }
}

function persistSlots(slots: CreationFlowSlot[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(slots))
  } catch {
    // The card flow remains available in memory when storage is blocked.
  }
}

export const useCreationFlowStore = defineStore('creationFlow', {
  state: () => ({
    slots: loadSlots(),
    feedback: '',
  }),
  getters: {
    filledCount: state => state.slots.filter(slot => slot.materialId !== null).length,
    isFull: state => state.slots.every(slot => slot.materialId !== null),
    firstEmptySlotIndex: state => state.slots.find(slot => slot.materialId === null)?.index ?? null,
    getMaterialAt: state => (slotIndex: CreationFlowSlotIndex) => (
      state.slots.find(slot => slot.index === slotIndex)?.materialId ?? null
    ),
    hasMaterial: state => (materialId: string) => state.slots.some(slot => slot.materialId === materialId),
    serializeSlots: (state): CreationSubmissionRequest => ({
      slots: state.slots.map(slot => ({
        index: slot.index,
        // Compatibility boundary: the legacy internal Material ID is the
        // backend-facing Salt Card ID until the store is safely renamed.
        cardId: slot.materialId,
      })),
    }),
  },
  actions: {
    placeMaterial(materialId: string, slotIndex: CreationFlowSlotIndex) {
      if (!isCreationFlowSlotIndex(slotIndex)) {
        this.feedback = '无效的创作槽位'
        return false
      }

      if (this.hasMaterial(materialId)) {
        this.feedback = '该素材已在创作流'
        return false
      }

      const targetSlot = this.slots.find(slot => slot.index === slotIndex)
      if (this.isFull) {
        this.feedback = 'Creation Flow 已满'
        return false
      }

      if (!targetSlot || targetSlot.materialId !== null) {
        this.feedback = '目标槽位已有素材'
        return false
      }

      targetSlot.materialId = materialId
      this.feedback = ''
      persistSlots(this.slots)
      // 查找素材类型作为上下文
      const matStore = getMaterialStore()
      const mat = matStore.materials.find(m => m.id === materialId)
      triggerCardPlace({ cardType: mat?.type })
      playSfx(cardFlowDropSfx, { volume: AUDIO_VOLUME.cardFlowDrop })
      return true
    },
    placeCard(cardId: string, slotIndex: CreationFlowSlotIndex) {
      return this.placeMaterial(cardId, slotIndex)
    },
    moveMaterial(sourceSlotIndex: CreationFlowSlotIndex, targetSlotIndex: CreationFlowSlotIndex) {
      if (!isCreationFlowSlotIndex(sourceSlotIndex) || !isCreationFlowSlotIndex(targetSlotIndex)) {
        this.feedback = '无效的创作槽位'
        return false
      }

      if (sourceSlotIndex === targetSlotIndex) {
        return true
      }

      const sourceSlot = this.slots.find(slot => slot.index === sourceSlotIndex)
      const targetSlot = this.slots.find(slot => slot.index === targetSlotIndex)
      if (!sourceSlot || !targetSlot || sourceSlot.materialId === null) {
        this.feedback = '来源槽位没有素材'
        return false
      }

      const sourceMaterialId = sourceSlot.materialId
      sourceSlot.materialId = targetSlot.materialId
      targetSlot.materialId = sourceMaterialId
      this.feedback = ''
      persistSlots(this.slots)
      return true
    },
    removeMaterial(slotIndex: CreationFlowSlotIndex) {
      const targetSlot = this.slots.find(slot => slot.index === slotIndex)
      if (!targetSlot) {
        return false
      }

      targetSlot.materialId = null
      this.feedback = ''
      persistSlots(this.slots)
      return true
    },
    removeCard(slotIndex: CreationFlowSlotIndex) {
      return this.removeMaterial(slotIndex)
    },
    clear() {
      this.slots = createSlots()
      this.feedback = ''
      persistSlots(this.slots)
    },
    setFeedback(message: string) {
      this.feedback = message
    },
  },
})
