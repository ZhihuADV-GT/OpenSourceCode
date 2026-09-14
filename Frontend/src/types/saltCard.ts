export type SaltCardType = '观点卡' | '情绪卡' | '漏洞卡' | '修辞卡'

/** 原始 JudgeResult.card DTO。后端 range 使用闭区间 [start, end]。 */
export interface SaltCardDto {
  card_id: string
  attribute_value: number
  card_type: string
  start: number
  end: number
}

/**
 * 前端 Judge card domain model。
 * canonical offsets 已由 Adapter 统一为 [start, end)：start 包含，end 不包含。
 */
export interface SaltCard {
  cardId: string
  attributeValue: number
  cardType: string
  canonicalStartOffset: number
  canonicalEndOffset: number
}
