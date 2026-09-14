/**
 * @deprecated 前端本地配卡运算已废弃：协议要求向量运算必须在后端完成。
 * 真实链路请使用 workspaceApi.syncCombination()（POST /api/workspace/vectors）。
 * 本文件仅保留本地预估展示能力（工作台预览），后续阶段移除。
 */
import { DEMO_COMBINATION_RULES, type DemoCombinationRule } from '../data/demoCombinationRules'
import type { Material } from '../types/material'

export type CombinationResultStatus = 'success' | 'partial' | 'fail'

export interface CombinationResult {
  baseValue: number
  combinationBonus: number
  finalValue: number
  targetValue: number
  result: CombinationResultStatus
  ruleLabel?: string
}

function matchesRule(rule: DemoCombinationRule, materials: Material[]): boolean {
  const types = new Set(materials.map(material => material.type).filter(Boolean))

  if (rule.minDistinctTypes && types.size < rule.minDistinctTypes) {
    return false
  }

  return rule.requiredTypes.every(type => types.has(type))
}

function getBestRule(materials: Material[]): DemoCombinationRule | undefined {
  return DEMO_COMBINATION_RULES
    .filter(rule => matchesRule(rule, materials))
    .sort((left, right) => right.bonus - left.bonus)[0]
}

export function evaluateCombination(selectedMaterials: Material[], targetValue: number): CombinationResult {
  const baseValue = selectedMaterials.reduce(
    (total, material) => total + (material.attributeValue ?? 0),
    0,
  )
  const bestRule = getBestRule(selectedMaterials)
  const combinationBonus = bestRule?.bonus ?? 0
  const finalValue = baseValue + combinationBonus
  const result: CombinationResultStatus = finalValue >= targetValue
    ? 'success'
    : finalValue >= targetValue * 0.8
      ? 'partial'
      : 'fail'

  return {
    baseValue,
    combinationBonus,
    finalValue,
    targetValue,
    result,
    ruleLabel: bestRule?.label ?? '基础组合',
  }
}
