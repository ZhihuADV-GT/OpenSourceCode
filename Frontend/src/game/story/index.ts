/** game/story —— 剧情系统 */
export type { StoryScript, DialogueLine, CharacterPortrait } from './types'
export {
  getStoryScript,
  getAllStoryScripts,
  AI_STORY_ID,
  FALLBACK_STORY_COUNT,
  getFallbackStory,
} from './scripts'
export {
  STORY_PORTRAITS,
  STORY_SPEAKER_NAMES,
  NARRATION_SPEAKER,
  getPortraitSrc,
  getSpeakerDisplayName,
} from './portraits'
