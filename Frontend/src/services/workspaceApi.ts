/**
 * 配卡运算通信服务：协议链路3（POST /api/workspace/vectors）
 */
import { http } from './http'
import type { SlotSnapshot, VectorResult } from '../types/workspace'

export async function syncCombination(snapshot: SlotSnapshot): Promise<VectorResult> {
  const response = await http.post<VectorResult>('/workspace/vectors', snapshot)
  return response.data
}
