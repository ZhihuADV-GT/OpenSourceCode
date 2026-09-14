import type { SaltCard, SaltCardDto } from './saltCard'

// 请求：对齐协议 SelectionPayload（POST /api/judge 请求体）
export interface SelectionPayload {
  articleId: string
  paragraphIndex: number
  startOffset: number
  endOffset: number
}

// 原始响应 DTO：card.start/end 是后端 linespot 的闭区间 [start, end]
export type JudgeResultDto =
  | { hit: true; matchRate: number; card: SaltCardDto }
  | { hit: false; matchRate: number; message: string }

// Adapter 后的前端 domain：card 使用 [start, end) canonical offsets
export type JudgeResult =
  | { hit: true; matchRate: number; card: SaltCard }
  | { hit: false; matchRate: number; message: string }

// ── 动态划线判定（POST /api/cards/dynamic，新端点） ──────────────
//
// 请求体前四个字段与 SelectionPayload 逐字一致，可直接复用 buildSelectionPayload
// 的产物；round 是新端点专属，后端用它按局计动态卡配额。
// round 可选是刻意的：后端该字段缺省就跳过配额检查，不因为少传一个字段把玩家挡在门外。
export interface DynamicCardPayload extends SelectionPayload {
  round?: number
}

// 判定来源。preset = 命中了预设要点（幂等保护分支），ai = AI 判定成功，
// local = AI 不可用时后端本地降级。
// 按已定决策，3 个来源对玩家完全一致，不做任何展示，仅供排查时对照后端日志的降级档位。
export type DynamicCardSource = 'preset' | 'ai' | 'local'

// 响应体与 JudgeResultDto 同构，只多一个 source。
// 同构是必须的：前端 adaptSaltCard / adaptJudgeResult / ArticlePanel 的 miss 文案链路
// 全部直接复用，后端换什么 message 前端就显示什么，这条链路一行都不用改。
export type DynamicCardResultDto = JudgeResultDto & { source?: DynamicCardSource }

export type DynamicCardResult = JudgeResult & { source?: DynamicCardSource }
