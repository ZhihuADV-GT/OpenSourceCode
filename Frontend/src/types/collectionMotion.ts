import type { CreationFlowSlotIndex } from './creationFlow'

export interface CardRect {
  left: number
  top: number
  width: number
  height: number
}

export interface SelectionAnchorRect {
  top: number
  bottom: number
  left: number
  right: number
  width: number
  height: number
}

export interface CollectionFlight {
  id: string
  materialId: string
  materialType: string
  sourceRect: SelectionAnchorRect
}

export interface CreationFlowTransferRequest {
  id: string
  materialId: string
  materialType: string
  sourceRect: CardRect
  targetSlotIndex: CreationFlowSlotIndex
}

export interface CreationFlowTransferFlight extends CreationFlowTransferRequest {}

export type WorkbenchTransferRequest = CreationFlowTransferRequest
export type WorkbenchTransferFlight = CreationFlowTransferFlight
