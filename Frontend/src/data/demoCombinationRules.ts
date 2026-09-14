export interface DemoCombinationRule {
  id: string
  requiredTypes: string[]
  bonus: number
  label: string
  minDistinctTypes?: number
}

/** Prototype-only Week 1 rules. These are not final game balance. */
export const DEMO_COMBINATION_RULES: DemoCombinationRule[] = [
  {
    id: 'multi-angle',
    requiredTypes: [],
    bonus: 20,
    label: '多角度组合',
    minDistinctTypes: 3,
  },
  {
    id: 'claim-verification',
    requiredTypes: ['观点卡', '漏洞卡'],
    bonus: 20,
    label: '观点核验',
  },
  {
    id: 'rhetorical-breakdown',
    requiredTypes: ['观点卡', '修辞卡'],
    bonus: 10,
    label: '表达拆解',
  },
  {
    id: 'emotion-recognition',
    requiredTypes: ['情绪卡', '修辞卡'],
    bonus: 15,
    label: '情绪识别',
  },
]
