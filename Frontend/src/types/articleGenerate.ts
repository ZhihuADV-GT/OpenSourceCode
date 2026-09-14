/**
 * 每局文章生成 —— 类型定义（协议链路7）
 *
 * 对齐后端 POST /api/articles/generate 的请求/响应格式。
 */

/** 段落蓝图中的单条记录 */
export interface BlueprintItem {
  /** 段序（0-based） */
  index: number
  /** 段落角色（破题段/驳斥段/…） */
  role: string
  /** 主卡牌 ID */
  card_id: string
  /** 主卡牌类型（观点/漏洞/情绪/修辞） */
  card_type: string
  /** 内容类型（原因类/机制类/…） */
  content_type: string
  /** 命中的模板 ID */
  template_id: string
  /** 织入填充卡数量 */
  weave_count: number
}

/** POST /api/articles/generate 请求体 */
export interface ArticleGenerateRequest {
  /** 工作台卡槽快照 [[slotId, cardId], ...] */
  slots: [string, string][]
  /** 是否调用 AI 逐段生成（默认 true）；false 则纯卡牌原文拼接兜底 */
  use_ai?: boolean
}

/** POST /api/articles/generate 响应体 */
export interface ArticleGenerateResponse {
  /** 文章标题 */
  title: string
  /** 拼装后的完整文章正文 */
  content: string
  /** 各段文本数组 */
  paragraphs: string[]
  /** 识别出的结构中文名（驳论/并列/递进/总-分-总/…） */
  structure: string
  /** 文章基调（rational/emotional/critical/…） */
  lean: string
  /** 段落蓝图 */
  blueprint: BlueprintItem[]
}
