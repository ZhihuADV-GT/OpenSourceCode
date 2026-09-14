/**
 * 划线判定通信服务：POST /api/cards/dynamic（主）+ POST /api/judge（异常兜底）
 *
 * 精简为纯 HTTP 转发：请求体即协议 SelectionPayload，响应体即协议 JudgeResult。
 * 后端返回的 card_type 已是中文类型名（观点卡/情绪卡/漏洞卡/修辞卡），前端直接使用。
 */
import { isAxiosError } from 'axios'
import { http } from './http'
import type { PendingSelection } from '../types/selection'
import type { SaltCard, SaltCardDto } from '../types/saltCard'
import type { JudgeResult, JudgeResultDto, SelectionPayload } from '../types/strokeJudge'
import type {
  DynamicCardPayload,
  DynamicCardResult,
  DynamicCardResultDto,
} from '../types/strokeJudge'

export const STROKE_JUDGE_API_STATUS = 'REAL_BACKEND_CONNECTED' as const
export const STROKE_JUDGE_ENDPOINT = '/judge' as const
export const DYNAMIC_CARD_ENDPOINT = '/cards/dynamic' as const

/**
 * 动态划线判定的单独超时，必须覆盖 http 实例的 5s 全局值。
 *
 * 后端给 AI 留的预算是 15s（TONGYI_TIMEOUT_DYNAMIC_CARD）。沿用全局 5s 会造成
 * 最坑的一种失败：后端建卡成功并已落盘，前端却报超时，玩家重划一次就多一张重复卡
 * （L2 去重只能拦下偏移量完全相同的重划，差一个字就是新 hash）。
 * 20s 比后端预算长，超时发生时后端一定已经结束，不会出现两边状态分岔。
 */
export const DYNAMIC_CARD_TIMEOUT_MS = 20000

export type StrokeJudgeErrorCode =
  | 'ARTICLE_NOT_FOUND'
  | 'STROKE_JUDGE_VALIDATION_ERROR'
  | 'STROKE_JUDGE_NETWORK_ERROR'
  | 'STROKE_JUDGE_TIMEOUT'
  | 'STROKE_JUDGE_HTTP_ERROR'
  | 'STROKE_JUDGE_RESPONSE_ERROR'

export class StrokeJudgeError extends Error {
  readonly code: StrokeJudgeErrorCode

  constructor(code: StrokeJudgeErrorCode, message: string) {
    super(message)
    this.name = 'StrokeJudgeError'
    this.code = code
  }
}

export function buildSelectionPayload(articleId: string, selection: PendingSelection): SelectionPayload {
  return {
    articleId,
    paragraphIndex: selection.paragraphIndex,
    startOffset: selection.startOffset,
    endOffset: selection.endOffset,
  }
}

/** 在划线 payload 上补上 round（后端按局计动态卡配额） */
export function buildDynamicCardPayload(
  articleId: string,
  selection: PendingSelection,
  round?: number,
): DynamicCardPayload {
  return {
    ...buildSelectionPayload(articleId, selection),
    round,
  }
}

function toStrokeJudgeError(error: unknown): StrokeJudgeError {
  if (error instanceof StrokeJudgeError) {
    return error
  }

  if (!isAxiosError(error)) {
    return new StrokeJudgeError(
      'STROKE_JUDGE_NETWORK_ERROR',
      'Stroke Judge 请求失败，请稍后重试。',
    )
  }

  if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
    return new StrokeJudgeError(
      'STROKE_JUDGE_TIMEOUT',
      'Stroke Judge 请求超时，请稍后重试。',
    )
  }

  if (!error.response) {
    return new StrokeJudgeError(
      'STROKE_JUDGE_NETWORK_ERROR',
      '无法连接 Stroke Judge 后端，请确认后端服务已启动。',
    )
  }

  if (error.response.status === 404) {
    return new StrokeJudgeError(
      'ARTICLE_NOT_FOUND',
      '后端找不到当前文章。',
    )
  }

  if (error.response.status === 422) {
    return new StrokeJudgeError(
      'STROKE_JUDGE_VALIDATION_ERROR',
      'Stroke Judge 请求字段未通过后端校验。',
    )
  }

  return new StrokeJudgeError(
    'STROKE_JUDGE_HTTP_ERROR',
    'Stroke Judge 后端返回了错误，请稍后重试。',
  )
}

export function getStrokeJudgeErrorMessage(error: unknown): string {
  return toStrokeJudgeError(error).message
}

/**
 * 将后端 linespot 闭区间 [start, end] 转成前端统一的 [start, end) range。
 * 这是唯一允许发生 inclusive/exclusive 转换的协议边界。
 */
export function adaptSaltCard(dto: SaltCardDto): SaltCard {
  if (
    !Number.isInteger(dto.start)
    || !Number.isInteger(dto.end)
    || dto.start < 0
    || dto.end < dto.start
  ) {
    throw new StrokeJudgeError(
      'STROKE_JUDGE_RESPONSE_ERROR',
      'Stroke Judge 返回了无效的 canonical range。',
    )
  }

  return {
    cardId: dto.card_id,
    attributeValue: dto.attribute_value,
    cardType: dto.card_type,
    canonicalStartOffset: dto.start,
    canonicalEndOffset: dto.end + 1,
  }
}

/** Raw DTO → 前端 domain。Vue component 不直接读取后端 snake_case response。 */
export function adaptJudgeResult(dto: JudgeResultDto): JudgeResult {
  // 用 'card' in dto 判别分支，不要改回 dto.hit。
  //
  // JudgeResultDto 是 hit:true/false 的可辨识联合，按常规写法该用布尔判别式，
  // 但实测这条路在本项目里不稳：tsc 6.0.3 下 if (!dto.hit) 的窄化正常
  // （strict 与非 strict 两种配置均 EXIT=0，vite build 也过），编辑器语言
  // 服务器却在 then 分支里认为 dto 仍是整个联合，报「JudgeResultDto 上不存在
  // 属性 message」——一个编译器查不出、只在编辑器里长红的幽灵错误。
  // 改回 return dto 也一样报，只是换成 SaltCardDto 缺少 SaltCard 的 camelCase 字段。
  // 注意它只坏在 then 分支：if 之后访问 dto.card 从来不报错。
  //
  // in 窄化走的是另一条实现路径，不依赖 strictNullChecks、也不依赖布尔字面量
  // 判别式，两边都成立。card / message 恰好是两分支各自的独有字段，判别无歧义。
  if ('card' in dto) {
    return {
      hit: true,
      matchRate: dto.matchRate,
      card: adaptSaltCard(dto.card),
    }
  }

  return {
    hit: false,
    matchRate: dto.matchRate,
    message: dto.message,
  }
}

/** 发送 SelectionPayload，返回 Adapter 后的 JudgeResult domain */
export async function judgeSelection(payload: SelectionPayload): Promise<JudgeResult> {
  try {
    const response = await http.post<JudgeResultDto>(STROKE_JUDGE_ENDPOINT, payload)
    return adaptJudgeResult(response.data)
  } catch (error) {
    throw toStrokeJudgeError(error)
  }
}

/** 动态卡 DTO → domain。card 的 canonical range 转换全部交给已有的 adaptJudgeResult。 */
export function adaptDynamicCardResult(dto: DynamicCardResultDto): DynamicCardResult {
  // 后端返的 card.start/end 是句边界扩展后的区间，而不是玩家原始选区。
  // 经 adaptSaltCard 后 canonicalEndOffset = end + 1，与预设卡同一口径，
  // ArticlePanel.toMaterial 拿它 slice canonicalContent 就能得到完整句子的原文与高亮。
  return { ...adaptJudgeResult(dto), source: dto.source }
}

/**
 * AI 辅助的动态划线判定（POST /api/cards/dynamic）——划线的**主路径**
 *
 * 覆盖全部选区长度：端点内部第一步就是与 /api/judge 同一套 linespot 比对，
 * 命中预设点时返回的 card 与 judge 逐字一致（只多一个 source 字段），未命中
 * 才走 AI 判型 + 句边界扩展。
 *
 * /api/judge 降为异常兜底，只在本请求整体失败（后端未起 / 网络断 / 超时）时调。
 * 顺序不能反过来：judge 的 miss 分支自己就会建卡并落盘，先 judge 再调这里会让
 * 同一次划线产生两张卡。详见 ArticlePanel.judgeSelectionWithAi 的注释，
 * 以及后端 test_preset_branch_is_equivalent_to_judge（钉住两边预设分支的等价性）。
 */
export async function createDynamicCard(payload: DynamicCardPayload): Promise<DynamicCardResult> {
  try {
    const response = await http.post<DynamicCardResultDto>(
      DYNAMIC_CARD_ENDPOINT,
      payload,
      { timeout: DYNAMIC_CARD_TIMEOUT_MS },
    )
    return adaptDynamicCardResult(response.data)
  } catch (error) {
    throw toStrokeJudgeError(error)
  }
}
