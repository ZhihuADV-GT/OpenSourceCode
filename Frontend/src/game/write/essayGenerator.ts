/**
 * Final Write 模块 —— 最终旅程回答生成。
 *
 * 真实生成复用现有 /api/ai/chat 边界；网络或服务失败时返回本地保底文本，
 * 让最终旅程状态仍然可见、可重试。
 */

import type { FinalJourneySummary, WriteEssayRequest, WriteEssayResult } from './types'

const AI_CHAT_ENDPOINT = '/api/ai/chat'
const GENERATION_TIMEOUT_MS = 20_000

function preferenceLabel(summary: FinalJourneySummary): string {
  if (summary.preferredMaterial.kind === 'none') return '还没有形成单一的卡牌偏好'
  if (summary.preferredMaterial.kind === 'tie') {
    return `${summary.preferredMaterial.labels.join('与')}并列`
  }
  return summary.preferredMaterial.labels[0] ?? '暂无'
}

function achievementText(summary: FinalJourneySummary): string {
  if (summary.unlockedAchievements.length === 0) return '目前还没有解锁成就'
  return summary.unlockedAchievements.map(achievement => achievement.name).join('、')
}

function roundHistoryText(summary: FinalJourneySummary): string {
  if (summary.roundHistory.length === 0) return '暂无可用的移动记录'
  return summary.roundHistory
    .map(record => `第${record.round}局抵达(${record.toRow + 1},${record.toCol + 1})`)
    .join('；')
}

function buildPrompt(summary: FinalJourneySummary): string {
  const { collected, used } = summary
  return [
    '请为刚刚完成知乎世界六局旅程的玩家，写一篇最终的知乎风格回答兼旅行随笔。',
    '语气温暖、克制、略带文学感，像看山在旅途结束时替玩家整理一页手记。',
    '请写出约300到600字的中文正文，只输出正文，不要标题、Markdown、JSON、代码块或系统分析。',
    '不要机械罗列数据，也不要使用“恭喜”“作为AI”等套话；要把数据转化为对这次旅程的个人观察。',
    '',
    `旅程完成：${summary.roundsCompleted}局。`,
    `最终抵达：${summary.finalRegion}，位置(${summary.finalPosition.row + 1},${summary.finalPosition.col + 1})。`,
    `最终热度方向为${summary.finalHeat.toFixed(2)}，盐度方向为${summary.finalSalt.toFixed(2)}。`,
    `收集到的卡牌：修辞${collected.rhetoric}张、情绪${collected.emotion}张、观点${collected.viewpoint}张、漏洞${collected.loophole}张。`,
    `真正用于完成旅程的卡牌：修辞${used.rhetoric}张、情绪${used.emotion}张、观点${used.viewpoint}张、漏洞${used.loophole}张。`,
    `最常使用的卡牌倾向：${preferenceLabel(summary)}。`,
    `热度路线完成${summary.heatQualifiedRounds.length}局，盐度路线完成${summary.saltQualifiedRounds.length}局。`,
    `与看山成功交流${summary.kanshanInteractions}次。`,
    `已解锁的成就：${achievementText(summary)}。`,
    `移动痕迹：${roundHistoryText(summary)}。`,
    '',
    '请让正文同时回答：玩家如何选择、如何使用素材、如何与看山同行，以及这一路最终留下了怎样的方向感。',
  ].join('\n')
}

function titleForSummary(summary: FinalJourneySummary): string {
  return `${summary.finalRegion} · 这一程的回答`
}

function sanitizeGeneratedContent(value: unknown): string {
  if (typeof value !== 'string') return ''
  return value
    .replace(/^```(?:text|markdown)?\s*/i, '')
    .replace(/\s*```$/i, '')
    .trim()
}

/** 网络失败时的本地保底，保留收集与使用之间的差异。 */
export function buildFallbackEssay(summary: FinalJourneySummary): WriteEssayResult {
  const { collected, used } = summary
  const preference = preferenceLabel(summary)
  const interactionLine = summary.kanshanInteractions > 0
    ? `我也曾和看山交谈 ${summary.kanshanInteractions} 次。那些短短的问答没有替我决定方向，却让每一次犹豫都有了回应。`
    : '这一路我很少开口询问看山，更多时候是让脚下的选择自己回答。'

  const content = [
    `六局旅程走到${summary.finalRegion}，我才发现，方向从来不是地图替我准备好的答案。它藏在一次次取材、舍弃与再次出发之间。`,
    `我一共收集了修辞${collected.rhetoric}张、情绪${collected.emotion}张、观点${collected.viewpoint}张、漏洞${collected.loophole}张；但真正陪我走到终点的，是修辞${used.rhetoric}张、情绪${used.emotion}张、观点${used.viewpoint}张、漏洞${used.loophole}张。收集像把可能性放进背包，使用才是承认自己愿意沿哪一条路走下去。`,
    `这一路最常被我使用的是${preference}。热度路线走过${summary.heatQualifiedRounds.length}局，盐度路线走过${summary.saltQualifiedRounds.length}局。${interactionLine}`,
    `现在看山停在(${summary.finalPosition.row + 1},${summary.finalPosition.col + 1})，而我也终于明白，所谓完成并不是抵达某个完美答案，而是能说清楚自己为什么这样选择。旅程留下的不是一张终点照片，而是一篇仍愿意继续写下去的回答。`,
  ].join('\n\n')

  return {
    title: titleForSummary(summary),
    content,
    isAIGenerated: false,
  }
}

/** 调用已有 AI 聊天端点生成最终正文。 */
export async function generateEssay(req: WriteEssayRequest): Promise<WriteEssayResult> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), GENERATION_TIMEOUT_MS)

  try {
    const response = await fetch(AI_CHAT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: buildPrompt(req.summary),
        history: [],
      }),
      signal: controller.signal,
    })
    if (!response.ok) throw new Error(`Essay generation failed: ${response.status}`)

    const payload: unknown = await response.json()
    const reply = typeof payload === 'object' && payload !== null && 'reply' in payload
      ? sanitizeGeneratedContent(payload.reply)
      : ''
    if (!reply) throw new Error('Essay response was empty')

    return {
      title: titleForSummary(req.summary),
      content: reply,
      isAIGenerated: true,
      generatedAt: Date.now(),
    }
  } catch {
    return buildFallbackEssay(req.summary)
  } finally {
    clearTimeout(timeoutId)
  }
}
