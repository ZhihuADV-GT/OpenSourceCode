export interface Material {
  id: string
  articleId: string
  informationPointId: string
  /** 新素材所属回合；旧 localStorage 素材可能缺失此字段。 */
  collectedRound?: number
  text: string
  type?: string
  rarity?: string
  attributeValue?: number
  title?: string
  description?: string
  strength?: number
  source?: string
  /** 玩家实际划线范围，仅用于 Judge 请求和调试，不用于永久高亮。 */
  paragraphIndex?: number
  startOffset?: number
  endOffset?: number
  /** Judge 命中后由后端 linespot 返回的 canonical 范围，统一为 [start, end)。 */
  canonicalStartOffset?: number
  canonicalEndOffset?: number
}
