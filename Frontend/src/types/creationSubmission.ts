import type { CreationFlowSlotIndex } from './creationFlow'

export interface CreationSubmissionSlot {
  index: CreationFlowSlotIndex
  cardId: string | null
}

export interface CreationSubmissionRequest {
  slots: CreationSubmissionSlot[]
}

/** Minimal response boundary until the backend result schema is finalized. */
export interface CreationResult {
  success: boolean
  message?: string
  resultId?: string
}
