export const CREATION_FLOW_SLOT_INDICES = [
  1, 2, 3, 4,
  5, 6, 7, 8,
  9, 10, 11, 12,
  13, 14, 15, 16,
] as const

export type CreationFlowSlotIndex = typeof CREATION_FLOW_SLOT_INDICES[number]

export function isCreationFlowSlotIndex(value: number): value is CreationFlowSlotIndex {
  return CREATION_FLOW_SLOT_INDICES.includes(value as CreationFlowSlotIndex)
}

export interface CreationFlowSlot {
  index: CreationFlowSlotIndex
  materialId: string | null
}
