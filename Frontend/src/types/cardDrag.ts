import type { CardRect } from './collectionMotion'

export type CardDragPhase = 'pressing' | 'dragging' | 'snapping' | 'snap-back'
export type CardDragSourceType = 'backpack' | 'creation'

export interface CardDragStartRequest {
  sourceType: CardDragSourceType
  sourceSlotIndex: number | null
  materialId: string
  materialType: string
  pointerId: number
  sourceRect: CardRect
  startX: number
  startY: number
}

export interface CardDragMoveRequest {
  materialId: string
  pointerId: number
  pointerX: number
  pointerY: number
}

export interface CardDragEndRequest {
  materialId: string
  pointerId: number
  pointerX: number
  pointerY: number
  cancelled?: boolean
}

export interface CardDragState {
  sourceType: CardDragSourceType
  sourceSlotIndex: number | null
  materialId: string
  materialType: string
  pointerId: number
  sourceRect: CardRect
  startX: number
  startY: number
  pointerX: number
  pointerY: number
  displayX: number
  displayY: number
  activeTargetIndex: number | null
  targetRect?: CardRect
  phase: CardDragPhase
}
