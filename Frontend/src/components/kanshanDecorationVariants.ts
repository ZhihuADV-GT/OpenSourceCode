export const KANSHAN_DECORATION_VARIANTS = [
  'orbit',
  'stargaze',
  'explorer',
  'signal',
] as const

export type KanshanDecorationVariant = typeof KANSHAN_DECORATION_VARIANTS[number]

let nextVariantIndex = 0

/**
 * Pick a decoration arrangement only when a chat opens. Cycling through a
 * small curated set keeps every layout safe and makes browser QA repeatable.
 */
export function takeNextKanshanDecorationVariant(
  current?: KanshanDecorationVariant,
): KanshanDecorationVariant {
  let variant = KANSHAN_DECORATION_VARIANTS[nextVariantIndex]
  nextVariantIndex = (nextVariantIndex + 1) % KANSHAN_DECORATION_VARIANTS.length

  if (variant === current) {
    variant = KANSHAN_DECORATION_VARIANTS[nextVariantIndex]
    nextVariantIndex = (nextVariantIndex + 1) % KANSHAN_DECORATION_VARIANTS.length
  }

  return variant
}
