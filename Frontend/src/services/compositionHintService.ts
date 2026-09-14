import type { CreationFlowSlot } from '../types/creationFlow'
import type {
  CompositionHintAnalysisRequest,
  CompositionHintAnalysisResponse,
  CompositionHintItem,
  CompositionHintResponse,
} from '../types/compositionHint'
import type { Material } from '../types/material'
import { http } from './http'

type CardTypeKey = 'viewpoint' | 'emotion' | 'loophole' | 'rhetoric'

const CARD_TYPE_LABELS: Record<CardTypeKey, string> = {
  viewpoint: '观点卡',
  emotion: '情绪卡',
  loophole: '漏洞卡',
  rhetoric: '修辞卡',
}

const SLOT_ROW: Record<number, number> = {
  1: 0, 2: 0, 3: 0,
  4: 1, 5: 1, 6: 1, 7: 1, 8: 1,
  9: 2, 10: 2, 11: 2, 12: 2, 13: 2,
  14: 3, 15: 3, 16: 3,
}

const SLOT_COL: Record<number, number> = {
  1: 1, 2: 2, 3: 3,
  4: 0, 5: 1, 6: 2, 7: 3, 8: 4,
  9: 0, 10: 1, 11: 2, 12: 3, 13: 4,
  14: 1, 15: 2, 16: 3,
}

const SLOT_LABELS: Record<number, string> = {
  1: '顶行位一', 2: '顶行位二', 3: '顶行位三',
  4: '中行一位一', 5: '中行一位二', 6: '中行一位三', 7: '中行一位四', 8: '中行一位五',
  9: '中行二位一', 10: '中行二位二', 11: '中行二位三', 12: '中行二位四', 13: '中行二位五',
  14: '底行位一', 15: '底行位二', 16: '底行位三',
}

function normalizeCardType(type: string | undefined): CardTypeKey | null {
  if (!type) return null
  if (type.includes('观点')) return 'viewpoint'
  if (type.includes('情绪')) return 'emotion'
  if (type.includes('漏洞')) return 'loophole'
  if (type.includes('修辞')) return 'rhetoric'
  return null
}

function countTypes(materials: readonly Material[]) {
  const counts: Record<CardTypeKey, number> = {
    viewpoint: 0,
    emotion: 0,
    loophole: 0,
    rhetoric: 0,
  }

  for (const material of materials) {
    const type = normalizeCardType(material.type)
    if (type) counts[type] += 1
  }

  return counts
}

function getSlotMaterial(slot: CreationFlowSlot, materials: readonly Material[]) {
  if (!slot.materialId) return null
  return materials.find(material => material.id === slot.materialId) ?? null
}

function getPlacedType(slot: CreationFlowSlot, materials: readonly Material[]) {
  return normalizeCardType(getSlotMaterial(slot, materials)?.type)
}

function areAdjacent(leftSlotIndex: number, rightSlotIndex: number) {
  const leftRow = SLOT_ROW[leftSlotIndex]
  const rightRow = SLOT_ROW[rightSlotIndex]
  const leftCol = SLOT_COL[leftSlotIndex]
  const rightCol = SLOT_COL[rightSlotIndex]
  if (leftRow === undefined || rightRow === undefined || leftCol === undefined || rightCol === undefined) return false

  const sameRowNeighbor = leftRow === rightRow && Math.abs(leftCol - rightCol) === 1
  const verticalMiddleNeighbor = (
    ((leftRow === 1 && rightRow === 2) || (leftRow === 2 && rightRow === 1))
    && leftCol === rightCol
  )
  return sameRowNeighbor || verticalMiddleNeighbor
}

function hasAdjacentType(
  slots: readonly CreationFlowSlot[],
  materials: readonly Material[],
  viewpointSlotIndex: number,
  targetType: CardTypeKey,
) {
  return slots.some(slot => (
    slot.index !== viewpointSlotIndex
    && areAdjacent(slot.index, viewpointSlotIndex)
    && getPlacedType(slot, materials) === targetType
  ))
}

function getEmptySlotLabels(slots: readonly CreationFlowSlot[], preferred: readonly number[]) {
  const empty = new Set<number>(slots.filter(slot => slot.materialId === null).map(slot => slot.index))
  return preferred.filter(index => empty.has(index)).map(index => SLOT_LABELS[index])
}

function makeItem(
  type: CompositionHintItem['type'],
  title: string,
  reason: string,
  action: string,
  priority: number,
): CompositionHintItem {
  return { type, title, reason, action, priority }
}

export function buildCompositionHints(
  materials: readonly Material[],
  slots: readonly CreationFlowSlot[],
  currentVector: readonly [number, number],
): CompositionHintResponse {
  const counts = countTypes(materials)
  const placed = slots.filter(slot => slot.materialId !== null)
  const placedCounts = countTypes(placed.flatMap(slot => {
    const material = getSlotMaterial(slot, materials)
    return material ? [material] : []
  }))
  const items: CompositionHintItem[] = []

  if (materials.length === 0) {
    return {
      message: '背包还没有素材。先回文章里划出观点、情绪、漏洞或修辞，看山才好帮你排阵。',
      items: [
        makeItem(
          'collection',
          '先收集观点卡',
          '配方书里大多数阵型都靠观点卡搭骨架，观点越稳定，知北针越容易靠近正北。',
          '回到文章页，优先划出核心论点、反常识结论或能支撑全文的句子。',
          100,
        ),
      ],
    }
  }

  if (counts.viewpoint === 0) {
    items.push(makeItem(
      'collection',
      '缺少观点卡',
      '观点卡是文章的主力。没有观点卡时，很难排出驳论、并列、递进或总分结构。',
      '先回文章页补充观点卡，再用情绪、漏洞和修辞做调味。',
      100,
    ))
  }

  if (counts.viewpoint >= 4) {
    items.push(makeItem(
      'recipe',
      '推荐阵型：递进论证',
      '你现在的观点卡数量足够，适合在中间两行错位摆开，做出层层推进的结构。',
      '把观点卡优先放在中行一和中行二，并避免上下对齐或左右紧挨。',
      92,
    ))
  } else if (counts.viewpoint >= 3 && counts.loophole >= 1) {
    items.push(makeItem(
      'recipe',
      '推荐阵型：驳论论证',
      '你同时有观点卡和漏洞卡，适合先立靶、再反驳，做一篇更犀利的文章。',
      '把漏洞卡放在顶行当靶子，观点卡放到中间两行承担反驳主力。',
      90,
    ))
  } else if (counts.viewpoint >= 3) {
    items.push(makeItem(
      'recipe',
      '推荐阵型：总-分-总',
      '观点卡数量已经够搭出首尾呼应的经典结构，风险比随手堆放低。',
      '顶行中间放一个观点，底行中间放一个观点，中间两行展开分论点。',
      86,
    ))
  } else if (counts.viewpoint >= 1) {
    items.push(makeItem(
      'recipe',
      '先做总-分雏形',
      '目前观点卡偏少，不必追求复杂阵型，可以先用一个观点点题，再慢慢补充分论点。',
      '把观点卡放在顶行中间或底行中间，后续再补观点卡扩展结构。',
      72,
    ))
  }

  const viewpointSlots = placed
    .filter(slot => getPlacedType(slot, materials) === 'viewpoint')
    .map(slot => slot.index)
  const hasRhetoric = counts.rhetoric > 0
  const hasPlacedRhetoric = placedCounts.rhetoric > 0
  const hasRhetoricAdjacency = viewpointSlots.some(slotIndex => hasAdjacentType(slots, materials, slotIndex, 'rhetoric'))

  if (hasRhetoric && !hasRhetoricAdjacency) {
    items.push(makeItem(
      'adjacency',
      hasPlacedRhetoric ? '修辞还没贴住观点' : '让修辞贴近观点',
      '配方书里修辞卡是催化剂，自己不直接出力，只有紧邻观点卡才会增色。',
      '把修辞卡放到观点卡左右相邻的位置；如果在中间两行，也可以放到观点卡正上或正下。',
      84,
    ))
  }

  const [heat, salt] = currentVector
  if (Math.abs(heat) > 0.1 || Math.abs(salt) > 0.1) {
    if (heat - salt > 0.8 && counts.loophole > 0) {
      items.push(makeItem(
        'compass',
        '当前偏热，可以加一点盐',
        '知北针已经偏向流量感。若想更靠近答主之路，可以用漏洞卡增强辨析。',
        '把漏洞卡贴到观点卡旁边，降低纯情绪表达的漂移感。',
        70,
      ))
    } else if (salt - heat > 0.8 && counts.emotion > 0) {
      items.push(makeItem(
        'compass',
        '当前偏盐，可以补一点热度',
        '知北针已经偏向找茬感。若想更容易被读者接住，可以用情绪卡增加共鸣。',
        '把情绪卡贴到观点卡旁边，让批判之外也有感染力。',
        70,
      ))
    }
  }

  if (placed.length > 0 && viewpointSlots.length === 0) {
    items.push(makeItem(
      'risk',
      '创作流缺少主心骨',
      '当前已经放入卡牌，但没有观点卡。这样容易变成纯情绪或纯找茬，文章骨架会散。',
      '先放入至少一张观点卡，再围绕它摆情绪、漏洞或修辞。',
      88,
    ))
  }

  if (placed.length >= 3 && counts.viewpoint > 0) {
    const centerOpenings = getEmptySlotLabels(slots, [6, 7, 10, 11, 12])
    if (centerOpenings.length > 0) {
      items.push(makeItem(
        'risk',
        '避免落到“其它”阵型',
        '配方书里“其它”代表随手堆放。当前已经有几张卡，可以开始收束成明确结构。',
        `优先把观点卡往中间两行移动，可考虑空位：${centerOpenings.slice(0, 3).join('、')}。`,
        62,
      ))
    }
  }

  if (counts.loophole > 0 && counts.viewpoint === 0) {
    items.push(makeItem(
      'collection',
      '漏洞需要观点来接住',
      '漏洞卡很适合驳论，但如果没有观点卡承接，就只剩找茬感。',
      '继续阅读，补一到两张观点卡后再尝试驳论论证。',
      80,
    ))
  }

  if (items.length === 0) {
    items.push(makeItem(
      'recipe',
      '先围绕观点卡排阵',
      '你的素材可以开始组合了。配方书的核心思路是先确定观点骨架，再用相邻卡调味。',
      '选一张观点卡放到中心附近，再把情绪、漏洞或修辞放到它旁边观察知北针变化。',
      50,
    ))
  }

  const sortedItems = items
    .sort((left, right) => right.priority - left.priority)
    .slice(0, 4)

  return {
    message: buildSummaryMessage(counts, placed.length, sortedItems[0]),
    items: sortedItems,
  }
}

function buildSummaryMessage(
  counts: Record<CardTypeKey, number>,
  placedCount: number,
  topItem: CompositionHintItem,
) {
  const cardSummary = (Object.keys(CARD_TYPE_LABELS) as CardTypeKey[])
    .filter(type => counts[type] > 0)
    .map(type => `${CARD_TYPE_LABELS[type]} ${counts[type]} 张`)
    .join('、')

  if (!cardSummary) return topItem.reason
  if (placedCount === 0) {
    return `你现在有 ${cardSummary}。${topItem.title}会是一个不错的起手方向。`
  }
  return `你已经摆上 ${placedCount} 张卡，背包里有 ${cardSummary}。看山建议先处理：${topItem.title}。`
}

export function buildCompositionHintAnalysisRequest(
  hint: CompositionHintResponse,
  materials: readonly Material[],
  slots: readonly CreationFlowSlot[],
  currentVector: readonly [number, number],
): CompositionHintAnalysisRequest {
  const counts = countTypes(materials)
  const cardSummary = (Object.keys(CARD_TYPE_LABELS) as CardTypeKey[])
    .map(type => `${CARD_TYPE_LABELS[type]} ${counts[type]} 张`)
    .join('、')
  const slotSummary = slots
    .filter(slot => slot.materialId !== null)
    .map(slot => {
      const material = getSlotMaterial(slot, materials)
      const type = normalizeCardType(material?.type)
      return `${SLOT_LABELS[slot.index]}：${type ? CARD_TYPE_LABELS[type] : '未知卡'}`
    })
    .join('；') || '创作流暂无卡牌'

  return {
    message: hint.message,
    items: hint.items,
    cardSummary,
    slotSummary,
    vector: [currentVector[0], currentVector[1]],
  }
}

export async function fetchCompositionHintAnalysis(
  request: CompositionHintAnalysisRequest,
): Promise<CompositionHintAnalysisResponse | null> {
  try {
    const response = await http.post<CompositionHintAnalysisResponse>('/ai/composition-hint', request, {
      timeout: 15000,
    })
    return response.data
  } catch (error) {
    console.error('[compositionHintService] 获取合成深度分析失败:', error)
    return null
  }
}
