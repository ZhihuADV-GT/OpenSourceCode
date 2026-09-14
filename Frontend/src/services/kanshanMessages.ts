/**
 * 看山常时交互 —— 消息字符串集中管理 + AI 点评接入
 *
 * 所有触发场景的消息池都在这里定义。
 * trigger 函数优先调用后端 AI 接口获取点评文本；
 * API 失败/超时时降级为从对应消息池随机选取。
 */

import { kanshanBubble } from './kanshanEvents'

/** 辅助函数：从数组中随机取一个元素 */
function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]
}

// ──────────────────────────────────────────────
// 划线判定相关
// ──────────────────────────────────────────────

/** 划线成功（命中有效信息点） */
export const JUDGE_SUCCESS: string[] = [
  '划对了！信息就在这儿',
  '好眼力！这条信息很有价值',
  '没错，这里藏着关键信息！',
]

/** 划线失败（未命中有效信息点） */
export const JUDGE_FAIL: string[] = [
  '不对，这里信息价值还不够',
  '嗯…这里好像不是重点',
  '再想想，关键信息可能在别处',
]

// ──────────────────────────────────────────────
// 放卡槽相关
// ──────────────────────────────────────────────

/** 放置盐选卡到卡槽时 */
export const CARD_PLACE: string[] = [
  '结构井井有条！',
  '离完美的创作更进一步！',
  '好卡配好位，继续！',
  '这张卡放得稳！',
]

// ──────────────────────────────────────────────
// 结算相关
// ──────────────────────────────────────────────

/** 结算通过（向量投影 > 0） */
export const SETTLE_PASS: string[] = [
  '盐热双高！社区关注！',
  '漂亮！这篇文章过关了！',
  '数据不错，读者会喜欢的！',
]

/** 结算失败（向量投影 ≤ 0） */
export const SETTLE_FAIL: string[] = [
  '还差一点，再调整下配置',
  '向量还没到位，继续加油',
  '别急，换个思路试试',
]

// ──────────────────────────────────────────────
// 内部：调用后端 AI 点评接口
// ──────────────────────────────────────────────

/** AI 点评请求上下文 */
export interface CommentContext {
  articleId?: string
  text?: string      // 划线文本片段
  cardType?: string  // 卡牌类型
  vector?: string    // 当前向量描述
}

/**
 * 调用后端 /api/ai/comment 获取 AI 点评
 * 失败时返回 null，由调用方降级
 */
async function fetchAiComment(eventType: string, context?: CommentContext): Promise<string | null> {
  try {
    const resp = await fetch('/api/ai/comment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event_type: eventType,
        article_id: context?.articleId ?? '',
        context: context ?? {},
      }),
    })
    if (!resp.ok) return null
    const data = await resp.json()
    return data.text ?? null
  } catch {
    return null
  }
}

// ──────────────────────────────────────────────
// 便捷触发函数（供各组件直接调用）
// ──────────────────────────────────────────────

/** 划线成功时触发 */
export async function triggerJudgeSuccess(context?: CommentContext): Promise<void> {
  const aiText = await fetchAiComment('judge_success', context)
  kanshanBubble(aiText ?? pick(JUDGE_SUCCESS), 'judge-success')
}

/** 划线失败时触发 */
export async function triggerJudgeFail(context?: CommentContext): Promise<void> {
  const aiText = await fetchAiComment('judge_fail', context)
  kanshanBubble(aiText ?? pick(JUDGE_FAIL), 'judge-fail')
}

/** 放卡时触发 */
export async function triggerCardPlace(context?: CommentContext): Promise<void> {
  const aiText = await fetchAiComment('card_place', context)
  kanshanBubble(aiText ?? pick(CARD_PLACE), 'card-place')
}

/** 结算通过时触发 */
export async function triggerSettlePass(context?: CommentContext): Promise<void> {
  const aiText = await fetchAiComment('settle_pass', context)
  kanshanBubble(aiText ?? pick(SETTLE_PASS), 'settle-pass')
}

/** 结算失败时触发 */
export async function triggerSettleFail(context?: CommentContext): Promise<void> {
  const aiText = await fetchAiComment('settle_fail', context)
  kanshanBubble(aiText ?? pick(SETTLE_FAIL), 'settle-fail')
}
