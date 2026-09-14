/**
 * A 版本地预设剧情（降级保底）
 *
 * 当后端 /api/ai/story 生成失败、超时或不可用时，播放这里的静态剧本。
 *
 * 覆盖范围：第 1-5 局结算后触发的 5 段剧情（分别在第 2-6 局开场播放）。
 * 第 1 局开场的新手教程 ADV 由 tutorialFirstRound.ts 承担，不在此文件范围内。
 *
 * 索引口径：key = 触发序号 = 结算时的局号 previousRound（1-5），
 * 与 stores/game.ts 中 getFallbackStory(previousRound) 的调用一致。
 */

import type { StoryScript } from '../types'

/** AI 生成剧情的占位 storyId（与 events/data/typeD.ts 中 d_ai_story 的 effect.storyId 一致） */
export const AI_STORY_ID = 'ai_generated'

/** A 版预设剧本总段数 */
export const FALLBACK_STORY_COUNT = 5

export const FALLBACK_STORIES: Record<number, StoryScript> = {
  // 第 1 段：观点海洋 · 知乎用户A（热情话痨型）出场
  1: {
    id: 'fallback_story_1',
    title: '观点海洋的回音',
    source: 'fallback',
    lines: [
      {
        speaker: 'narration',
        speakerName: '旁白',
        text: '海风把提问瓶推上沙滩，瓶里的字条已经被浪打湿了。',
      },
      {
        speaker: 'kanshan',
        speakerName: '看山',
        text: '快看！那是观点海洋的回音鲸，它又在唱上周的高赞回答啦。',
      },
      {
        speaker: 'player',
        speakerName: '旅行者',
        text: '同一句话，唱一整周不腻吗？',
      },
      {
        speaker: 'zhihu_user_a',
        speakerName: '知乎用户A',
        text: '不腻！我之前也在这儿听过，越听越有味道！',
      },
      {
        speaker: 'zhihu_user_a',
        speakerName: '知乎用户A',
        text: '好观点就是这样，经得起反复咀嚼，你放心大胆地划！',
      },
      {
        speaker: 'kanshan',
        speakerName: '看山',
        text: '听见没？这片海喜欢肯反复琢磨的人呢。',
      },
      {
        speaker: 'player',
        speakerName: '旅行者',
        text: '那我多带几句走。',
      },
    ],
  },

  // 第 2 段：盐度冰川 · 知乎用户B（冷静考据型）出场
  2: {
    id: 'fallback_story_2',
    title: '冰川下的反光',
    source: 'fallback',
    lines: [
      {
        speaker: 'narration',
        speakerName: '旁白',
        text: '冰面下冻着许多尖锐的评论，隔着蓝幽幽的光，看得清楚却碰不到。',
      },
      {
        speaker: 'kanshan',
        speakerName: '看山',
        text: '小心脚下哦，盐度冰川的冰面会把说法里的漏洞照出来。',
      },
      {
        speaker: 'player',
        speakerName: '旅行者',
        text: '照出来了会怎么样？',
      },
      {
        speaker: 'zhihu_user_b',
        speakerName: '知乎用户B',
        text: '严格来说，被照出来的漏洞不该被藏起来，而应该被标清楚。',
      },
      {
        speaker: 'zhihu_user_b',
        speakerName: '知乎用户B',
        text: '实际上，能指出漏洞的人比能输出观点的人更稀缺。',
      },
      {
        speaker: 'kanshan',
        speakerName: '看山',
        text: '他就是这个脾气，冷冰冰的，但说的在理呢。',
      },
      {
        speaker: 'player',
        speakerName: '旅行者',
        text: '那我把漏洞也一起带走。',
      },
    ],
  },

  // 第 3 段：情绪火山 · 知乎用户C（丧系吐槽型）出场
  3: {
    id: 'fallback_story_3',
    title: '共鸣喷泉的回声',
    source: 'fallback',
    lines: [
      {
        speaker: 'narration',
        speakerName: '旁白',
        text: '共鸣喷泉又喷发了，滚烫的回声贴着地面一路滚过来。',
      },
      {
        speaker: 'kanshan',
        speakerName: '看山',
        text: '情绪火山的喷泉每隔一阵就炸一次，声音会直接钻进心里哦。',
      },
      {
        speaker: 'zhihu_user_c',
        speakerName: '知乎用户C',
        text: '啊这……我上次被溅了一身，缓了三天。',
      },
      {
        speaker: 'zhihu_user_c',
        speakerName: '知乎用户C',
        text: '你说得对，情绪是有价值，但我选择躺平。',
      },
      {
        speaker: 'player',
        speakerName: '旅行者',
        text: '那你还站在这儿？',
      },
      {
        speaker: 'zhihu_user_c',
        speakerName: '知乎用户C',
        text: '因为躺在这儿更烫。',
      },
      {
        speaker: 'kanshan',
        speakerName: '看山',
        text: '别理他啦，岩浆冷下来的情绪结晶可是很好的素材呢。',
      },
    ],
  },

  // 第 4 段：知识荒原 · 不出场 NPC，只留看山与旅行者的二人戏
  4: {
    id: 'fallback_story_4',
    title: '荒原上的灯塔',
    source: 'fallback',
    lines: [
      {
        speaker: 'narration',
        speakerName: '旁白',
        text: '沙丘后面露出半座图书馆的屋顶，风翻动着谁也没在读的书页。',
      },
      {
        speaker: 'kanshan',
        speakerName: '看山',
        text: '这里是知识荒原……安静得连回声都不愿意留下来呢。',
      },
      {
        speaker: 'player',
        speakerName: '旅行者',
        text: '远处那点光是什么？',
      },
      {
        speaker: 'kanshan',
        speakerName: '看山',
        text: '是灯塔。它一直亮着，只是很少有人走到能看清它的地方。',
      },
      {
        speaker: 'player',
        speakerName: '旅行者',
        text: '那我们算走到了吗？',
      },
      {
        speaker: 'kanshan',
        speakerName: '看山',
        text: '走到能听见风的地方，就已经算很远啦。',
      },
    ],
  },

  // 第 5 段：旅途将尽的氛围段落，不提主线、不做总结陈词，留给终局随笔
  5: {
    id: 'fallback_story_5',
    title: '最后一段路',
    source: 'fallback',
    lines: [
      {
        speaker: 'narration',
        speakerName: '旁白',
        text: '走过的路在身后连成一条浅浅的痕迹，风一吹就淡了半分。',
      },
      {
        speaker: 'kanshan',
        speakerName: '看山',
        text: '只剩最后一段路了呢……你还记得第一次划下句子时的感觉吗？',
      },
      {
        speaker: 'player',
        speakerName: '旅行者',
        text: '有点紧张，也有点上瘾。',
      },
      {
        speaker: 'kanshan',
        speakerName: '看山',
        text: '那些卡片、那些向量，其实都是你一路留下的脚印哦。',
      },
      {
        speaker: 'player',
        speakerName: '旅行者',
        text: '那终点会是什么？',
      },
      {
        speaker: 'kanshan',
        speakerName: '看山',
        text: '终点嘛，就是你自己写下来的那段话呀。',
      },
    ],
  },
}

/**
 * 取第 index 段 A 版预设剧本
 *
 * @param index 触发序号（= 结算时的局号，1-5）；越界时按 5 取模回绕
 */
export function getFallbackStory(index: number): StoryScript {
  const safeIndex = Number.isFinite(index) ? Math.trunc(index) : 1
  const normalized = ((safeIndex - 1) % FALLBACK_STORY_COUNT + FALLBACK_STORY_COUNT) % FALLBACK_STORY_COUNT + 1
  return FALLBACK_STORIES[normalized]
}
