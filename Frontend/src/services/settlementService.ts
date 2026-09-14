/**
 * 前端本地结算计算服务
 *
 * 根据最终向量在答主轴（45° 方向）上的投影长度，
 * 计算 pass/fail、评级、答主值增量。
 * 后端仅做 pass/fail 确认（投影 > 0），详细数值由本模块计算。
 */
import type { LocalSettlementResult } from '../types/settlement'

/** 评级阈值表（投影长度 → 评级）：向量为后端 ÷50 后量纲，p=1.0 ≈ 满强度正对答主轴 */
const RATING_THRESHOLDS: [number, string][] = [
  [1.8, 'SSS'],
  [1.3, 'SS'],
  [1.0, 'S'],
  [0.6, 'A'],
  [0.2, 'B'],
]

/**
 * 计算向量在答主轴（(1,1)/√2 方向）上的投影长度
 */
export function calcProjection(vector: [number, number]): number {
  return (vector[0] + vector[1]) / Math.SQRT2
}

/**
 * 根据投影长度返回评级
 */
export function calcRating(projection: number): string {
  for (const [threshold, rating] of RATING_THRESHOLDS) {
    if (projection >= threshold) return rating
  }
  return 'C'
}

/**
 * 根据投影长度和是否通过，计算答主值增量
 */
export function calcAnswererDelta(projection: number, passed: boolean): number {
  if (!passed) return 0
  const base = 10
  return base + Math.floor(projection * 10)
}

/**
 * 综合结算计算：输入最终向量，返回完整结算结果
 */
export function calculateLocalSettlement(vector: [number, number]): LocalSettlementResult {
  const projection = calcProjection(vector)
  const passed = projection > 0
  const rating = passed ? calcRating(projection) : 'C'
  const answererDelta = calcAnswererDelta(projection, passed)

  return { passed, rating, projection, answererDelta }
}

/** 终局评级阶梯表（总答主值 → 评级）：与终局结语文案档位对齐，≥100 为最高档 */
const FINAL_RATING_THRESHOLDS: [number, string][] = [
  [100, 'SSS'],
  [75, 'SS'],
  [50, 'A'],
  [25, 'B'],
]

/**
 * 终局评级：按总答主值划档（不复用单局向量投影阈值）
 */
export function calcFinalRating(answererValue: number): string {
  for (const [threshold, rating] of FINAL_RATING_THRESHOLDS) {
    if (answererValue >= threshold) return rating
  }
  return 'C'
}
