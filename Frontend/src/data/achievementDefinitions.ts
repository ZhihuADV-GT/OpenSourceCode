import type { AchievementDefinition } from '../types/achievement'

export const NEEDS_PRODUCT_VALUE = 'NEEDS_PRODUCT_VALUE' as const

export const ACHIEVEMENT_IDS = {
  FIRST_PATH: 'FIRST_PATH',
  YELLOW_V: 'YELLOW_V',
  RHETORIC_BASIC: 'RHETORIC_BASIC',
  EMOTION_BASIC: 'EMOTION_BASIC',
  VIEWPOINT_BASIC: 'VIEWPOINT_BASIC',
  LOOPHOLE_BASIC: 'LOOPHOLE_BASIC',
  RHETORIC_ADVANCED: 'RHETORIC_ADVANCED',
  HEAT_BASIC: 'HEAT_BASIC',
  SALT_BASIC: 'SALT_BASIC',
  HEAT_ADVANCED: 'HEAT_ADVANCED',
  SALT_ADVANCED: 'SALT_ADVANCED',
  FINAL_ACHIEVEMENT: 'FINAL_ACHIEVEMENT',
} as const

export const ACHIEVEMENT_PRODUCT_VALUES = {
  HEAT_BASIC_THRESHOLD: 0.65,
  SALT_BASIC_THRESHOLD: 0.65,
  HEAT_ADVANCED_REQUIRED_ROUNDS: 3,
  SALT_ADVANCED_REQUIRED_ROUNDS: 3,
  FINAL_ACHIEVEMENT_CONDITION: null as string | null,
} as const

export const ACHIEVEMENT_DEFINITIONS: AchievementDefinition[] = [
  {
    id: ACHIEVEMENT_IDS.FIRST_PATH,
    name: '谢邀下机',
    description: '跟看山签订契约吧，成为知乎答主！',
    prerequisites: [],
    progressType: 'completed_rounds',
    target: 1,
  },
  {
    id: ACHIEVEMENT_IDS.YELLOW_V,
    name: '蓝V敕封',
    description: '收下这份认证吧，你已经是独当一面的答主了。',
    prerequisites: [ACHIEVEMENT_IDS.FIRST_PATH],
    progressType: 'completed_rounds',
    target: 3,
  },
  {
    id: ACHIEVEMENT_IDS.RHETORIC_BASIC,
    name: '知梗辨音',
    description: '使用修辞卡 5 次，通悉所有隐喻，你这句话的意思是——',
    prerequisites: [ACHIEVEMENT_IDS.YELLOW_V],
    progressType: 'rhetoric_used',
    target: 5,
  },
  {
    id: ACHIEVEMENT_IDS.EMOTION_BASIC,
    name: '言为心声',
    description: '使用情绪卡 5 次，愿你的文字也能这般炽热辉煌',
    prerequisites: [ACHIEVEMENT_IDS.YELLOW_V],
    progressType: 'emotion_used',
    target: 5,
  },
  {
    id: ACHIEVEMENT_IDS.VIEWPOINT_BASIC,
    name: '有理有据',
    description: '使用观点卡 5 次，即使遗风早已消散，也请您当上荣誉答主。',
    prerequisites: [ACHIEVEMENT_IDS.YELLOW_V],
    progressType: 'viewpoint_used',
    target: 5,
  },
  {
    id: ACHIEVEMENT_IDS.LOOPHOLE_BASIC,
    name: '洞若观火',
    description: '使用漏洞卡 5 次，看穿这点小把戏，连一眼都不需要！',
    prerequisites: [ACHIEVEMENT_IDS.YELLOW_V],
    progressType: 'loophole_used',
    target: 5,
  },
  {
    id: ACHIEVEMENT_IDS.RHETORIC_ADVANCED,
    name: '尽不言中',
    description: '使用修辞卡 10 次，有些共鸣，无需多言也能传达到。',
    prerequisites: [ACHIEVEMENT_IDS.RHETORIC_BASIC],
    progressType: 'rhetoric_used',
    target: 10,
  },
  {
    id: ACHIEVEMENT_IDS.HEAT_BASIC,
    name: '榜上名扬',
    description: '让热榜燃烧吧！',
    prerequisites: [ACHIEVEMENT_IDS.EMOTION_BASIC, ACHIEVEMENT_IDS.VIEWPOINT_BASIC],
    progressType: 'completed_heat_threshold',
    target: ACHIEVEMENT_PRODUCT_VALUES.HEAT_BASIC_THRESHOLD,
  },
  {
    id: ACHIEVEMENT_IDS.SALT_BASIC,
    name: '盐选臻入',
    description: '充满力量的思辨精神会永远流传下去',
    prerequisites: [ACHIEVEMENT_IDS.VIEWPOINT_BASIC, ACHIEVEMENT_IDS.LOOPHOLE_BASIC],
    progressType: 'completed_salt_threshold',
    target: ACHIEVEMENT_PRODUCT_VALUES.SALT_BASIC_THRESHOLD,
  },
  {
    id: ACHIEVEMENT_IDS.HEAT_ADVANCED,
    name: '续火传薪',
    description: '延续这簇余火吧，总有人如灰烬般渴求它的温度。',
    prerequisites: [ACHIEVEMENT_IDS.HEAT_BASIC],
    progressType: 'qualified_heat_rounds',
    target: ACHIEVEMENT_PRODUCT_VALUES.HEAT_ADVANCED_REQUIRED_ROUNDS,
  },
  {
    id: ACHIEVEMENT_IDS.SALT_ADVANCED,
    name: '无问西东',
    description: '向新世界进发吧。',
    prerequisites: [ACHIEVEMENT_IDS.SALT_BASIC],
    progressType: 'qualified_salt_rounds',
    target: ACHIEVEMENT_PRODUCT_VALUES.SALT_ADVANCED_REQUIRED_ROUNDS,
  },
  {
    id: ACHIEVEMENT_IDS.FINAL_ACHIEVEMENT,
    name: '后续成就(仮)',
    description: '开发团队没油菜花了(╥﹏╥)',
    prerequisites: [],
    progressType: 'product_value',
    target: null,
    productValue: NEEDS_PRODUCT_VALUE,
    hidden: false,  // 【修改】改为false，默认显示
  },
]
