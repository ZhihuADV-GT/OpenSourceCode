/** 剧情脚本注册表 */
import type { StoryScript } from '../types'
import { tutorialFirstRound } from './tutorialFirstRound'

const SCRIPTS: Record<string, StoryScript> = {
  [tutorialFirstRound.id]: tutorialFirstRound,
}

export function getStoryScript(id: string): StoryScript | undefined {
  return SCRIPTS[id]
}

export function getAllStoryScripts(): readonly StoryScript[] {
  return Object.values(SCRIPTS)
}

// A 版降级预设剧本不进注册表（避免与 AI 生成剧本的 id 空间混淆），
// 仅在此 re-export 供 stores/game.ts 在 AI 失败时取用。
export { AI_STORY_ID, FALLBACK_STORY_COUNT, getFallbackStory } from './fallbackStories'
