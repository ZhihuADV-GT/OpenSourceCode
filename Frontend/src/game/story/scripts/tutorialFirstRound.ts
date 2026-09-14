/**
 * 新手教程剧情脚本
 * 
 * 第一局开始时触发，看山为玩家介绍游戏基本规则。
 */

import type { StoryScript } from '../types'

export const tutorialFirstRound: StoryScript = {
  id: 'tutorial_first_round',
  title: '看山的指引',
  lines: [
    {
      speaker: 'kanshan',
      speakerName: '看山',
      text: '你好！我是看山，一只住在知乎世界的北极狐。',
      expression: 'idle',
    },
    {
      speaker: 'kanshan',
      speakerName: '看山',
      text: '欢迎来到这个由观点、情绪和知识构成的世界。',
      expression: 'idle',
    },
    {
      speaker: 'kanshan',
      speakerName: '看山',
      text: '你的任务是在文章中寻找有价值的信息，把它们变成盐选卡。',
      expression: 'idle',
    },
    {
      speaker: 'kanshan',
      speakerName: '看山',
      text: '然后用这些卡在工作台上合成，激活知北针。',
      expression: 'idle',
    },
    {
      speaker: 'kanshan',
      speakerName: '看山',
      text: '知北针会告诉我该往哪个方向旅行——这就是你的「答主之路」。',
      expression: 'idle',
    },
    {
      speaker: 'kanshan',
      speakerName: '看山',
      text: '我们有 6 次移动机会，最后会根据你走过的路线给出评语。',
      expression: 'idle',
    },
    {
      speaker: 'kanshan',
      speakerName: '看山',
      text: '准备好了吗？让我们开始第一段旅程吧！',
      expression: 'happy',
    },
  ],
}
