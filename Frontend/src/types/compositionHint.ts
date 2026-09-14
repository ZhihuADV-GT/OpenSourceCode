export type CompositionHintType = 'recipe' | 'adjacency' | 'risk' | 'collection' | 'compass'

export interface CompositionHintItem {
  type: CompositionHintType
  title: string
  reason: string
  action: string
  priority: number
}

export interface CompositionHintResponse {
  message: string
  items: CompositionHintItem[]
}

export interface CompositionHintAnalysisRequest {
  message: string
  items: CompositionHintItem[]
  cardSummary: string
  slotSummary: string
  vector: [number, number]
}

export interface CompositionHintAnalysisResponse {
  mode: 'deep' | 'fallback'
  analysis: string
}
