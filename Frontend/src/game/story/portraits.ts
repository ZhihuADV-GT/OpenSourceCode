/**
 * 剧情立绘与角色显示名映射
 *
 * 立绘资源统一存放目录：src/assets/portraits/
 * 看山沿用现有的 src/assets/kanshan/map-kanshan.png（LandingView / DiamondMap 已在用），
 * 不重复拷贝这份 1.3MB 文件。
 *
 * 新增角色立绘步骤：
 * 1. 把图片放进 src/assets/portraits/（建议透明背景 PNG，高度 400px 左右）
 * 2. 取消下方对应的 import 与映射行注释
 * 未配置立绘的角色在 AdvDialogue 中不占位，仅靠名字标签配色区分。
 */

const kanshanPortrait = '' // [art-assets disabled] ../../assets/kanshan/map-kanshan.webp
// import playerPortrait from '../../assets/portraits/player.png'
// import zhihuUserAPortrait from '../../assets/portraits/zhihu-user-a.png'
// import zhihuUserBPortrait from '../../assets/portraits/zhihu-user-b.png'
// import zhihuUserCPortrait from '../../assets/portraits/zhihu-user-c.png'

/** speaker ID → 立绘图片地址 */
export const STORY_PORTRAITS: Record<string, string> = {
  kanshan: kanshanPortrait,
  // player: playerPortrait,
  // zhihu_user_a: zhihuUserAPortrait,
  // zhihu_user_b: zhihuUserBPortrait,
  // zhihu_user_c: zhihuUserCPortrait,
}

/** speaker ID → 名字标签显示名（与后端 STORY_SPEAKER_PROFILES 的 name 保持一致） */
export const STORY_SPEAKER_NAMES: Record<string, string> = {
  kanshan: '看山',
  player: '旅行者',
  zhihu_user_a: '知乎用户A',
  zhihu_user_b: '知乎用户B',
  zhihu_user_c: '知乎用户C',
  narration: '旁白',
}

/** 旁白：不显示名字标签、不显示立绘 */
export const NARRATION_SPEAKER = 'narration'

/** 取角色立绘；未配置时返回 null（AdvDialogue 会隐藏立绘区） */
export function getPortraitSrc(speaker: string): string | null {
  return STORY_PORTRAITS[speaker] ?? null
}

/** 前端兜底：后端未给 speakerName 时按本地表补全 */
export function getSpeakerDisplayName(speaker: string, fallback?: string): string {
  return STORY_SPEAKER_NAMES[speaker] ?? fallback ?? speaker
}
