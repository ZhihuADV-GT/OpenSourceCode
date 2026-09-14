/**
 * @deprecated 本地划线判定已废弃：协议要求所有判定逻辑必须在后端完成。
 * 请使用 strokeJudgeService.judgeSelection()（POST /api/judge）。
 * 本文件仅为历史参考保留，主流程不得再引用。
 */
import type { Article } from '../types/article'
import type { PendingSelection } from '../types/selection'
import type { Material } from '../types/material'

export type JudgeResult =
  | { status: 'success'; material: Material; informationPointId: string }
  | { status: 'invalid' }
  | { status: 'duplicate'; materialId: string; informationPointId: string }

export const MIN_OVERLAP_CHARS = 15
export const MIN_SELECTION_COVERAGE = 0.6

export function getRangeOverlap(
  selectionStart: number,
  selectionEnd: number,
  spotStart: number,
  spotEnd: number,
) {
  const overlapStart = Math.max(selectionStart, spotStart)
  const overlapEnd = Math.min(selectionEnd, spotEnd)

  return Math.max(0, overlapEnd - overlapStart)
}

export function judgeSelection(
  article: Article,
  selection: PendingSelection,
  existingMaterials: Material[] = [],
): JudgeResult {
  const selectionLength = selection.endOffset - selection.startOffset

  if (selectionLength <= 0) {
    return { status: 'invalid' }
  }

  const candidates = article.informationPoints
    .filter(point => (
      point.paragraphIndex === selection.paragraphIndex
      && typeof point.startOffset === 'number'
      && typeof point.endOffset === 'number'
    ))
    .map(point => {
      const overlapLength = getRangeOverlap(
        selection.startOffset,
        selection.endOffset,
        point.startOffset as number,
        point.endOffset as number,
      )

      return {
        point,
        overlapLength,
        selectionCoverage: overlapLength / selectionLength,
      }
    })
    .filter(candidate => (
      candidate.overlapLength >= MIN_OVERLAP_CHARS
      && candidate.selectionCoverage >= MIN_SELECTION_COVERAGE
    ))
    .sort((left, right) => (
      right.selectionCoverage - left.selectionCoverage
      || right.overlapLength - left.overlapLength
    ))

  const informationPoint = candidates[0]?.point

  if (!informationPoint) {
    return { status: 'invalid' }
  }

  const materialId = `${article.id}-${informationPoint.id}`
  const duplicate = existingMaterials.find(material => (
    material.articleId === article.id
    && material.informationPointId === informationPoint.id
  ))

  if (duplicate) {
    return {
      status: 'duplicate',
      materialId: duplicate.id,
      informationPointId: informationPoint.id,
    }
  }

  return {
    status: 'success',
    informationPointId: informationPoint.id,
    material: {
      id: materialId,
      articleId: article.id,
      informationPointId: informationPoint.id,
      text: informationPoint.text,
      type: informationPoint.type,
      rarity: informationPoint.rarity,
      attributeValue: informationPoint.attributeValue,
    },
  }
}
