/**
 * 地图页向量服务：GET /api/workspace/vectors
 * 与 Map-page/src/services/vectorService.ts 保持一致
 */
import { http } from './http'

/** 后端 VectorResult 响应结构 */
export interface VectorResultResponse {
  instant_vector: [number, number]
  submitted: boolean  // 本局是否已 submit（消费型，读一次后重置）
}

/**
 * GET /api/workspace/vectors
 * 读取会话中最后一次的即时二维向量 + submitted 标记
 */
export async function fetchVector(): Promise<VectorResultResponse> {
  const { data } = await http.get<VectorResultResponse>('/workspace/vectors')
  return data
}
