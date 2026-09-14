// 对齐协议 SubmitSignal（POST /api/submit 请求体）
export interface SubmitSignal {
  submit: true
}

// 对齐协议 Settlement（POST /api/submit 响应体）
export interface Settlement {
  passed: boolean
  rating: string
  answererDelta: number
  reward: {
    type: string
    value: number | string
  }
}

// 前端本地结算结果（由前端根据最终向量计算）
export interface LocalSettlementResult {
  passed: boolean
  rating: string
  projection: number
  answererDelta: number
}
