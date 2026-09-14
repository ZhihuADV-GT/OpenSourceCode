// 对齐协议 SlotSnapshot（POST /api/workspace/vectors 请求体）
export interface SlotSnapshot {
  slots: [string, string][]
}

// 对齐协议 VectorResult（POST /api/workspace/vectors 响应体）
export interface VectorResult {
  instant_vector: [number, number]
}
