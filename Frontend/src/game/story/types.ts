/**
 * 剧情系统 —— 类型定义
 */

/** 对话行 */
export interface DialogueLine {
  /** 说话角色 ID */
  speaker: string
  /** 角色显示名 */
  speakerName: string
  /** 对话文本 */
  text: string
  /** 立绘表情/姿态（可选） */
  expression?: string
}

/** 剧情脚本 */
export interface StoryScript {
  /** 脚本 ID */
  id: string
  /** 脚本标题 */
  title: string
  /** 剧情来源：AI 实时生成或本地保底 */
  source?: 'ai' | 'fallback' | 'local'
  /** 开发期诊断信息 */
  debug?: Record<string, unknown>
  /** 对话序列 */
  lines: DialogueLine[]
}

/** 角色立绘配置 */
export interface CharacterPortrait {
  id: string
  name: string
  /** 立绘图片路径（相对 public/ 或 assets/） */
  portraitSrc: string
}
