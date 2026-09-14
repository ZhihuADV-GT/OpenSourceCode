// [art-assets disabled]
const opinionCard = ''
const emotionCard = ''
const flawCard = ''
const rhetoricCard = ''

export const materialCardAssets = {
  观点卡: opinionCard,
  情绪卡: emotionCard,
  漏洞卡: flawCard,
  修辞卡: rhetoricCard,
} as const

const frontendCardTypeToAssetType: Record<string, MaterialCardType | undefined> = {
  opinion: '观点卡',
  emotion: '情绪卡',
  flaw: '漏洞卡',
  rhetoric: '修辞卡',
}

export type MaterialCardType = keyof typeof materialCardAssets

export function getMaterialCardAsset(type: string | undefined) {
  const assetType = type && Object.prototype.hasOwnProperty.call(materialCardAssets, type)
    ? type as MaterialCardType
    : frontendCardTypeToAssetType[type ?? '']

  if (!assetType) {
    return undefined
  }

  return materialCardAssets[assetType]
}
