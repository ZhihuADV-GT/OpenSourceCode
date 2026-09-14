// 严格对齐协议 ArticleResponse（GET /api/articles 响应）
export interface ArticleResponse {
  id: string
  title: string
  content: string
  target_value: number | null
}

/**
 * 信息点（原 linespot 的前端映射）。
 * 协议要求后端绝不向前端下发 linespots，因此在真实后端模式下此列表恒为空，
 * 仅保留类型供前端内部逻辑（ArticlePanel / judgeService 等）引用。
 */
export interface InformationPoint {
  id: string
  text: string
  type?: string
  rarity?: string
  attributeValue?: number
  paragraphIndex?: number
  sourceStartOffset?: number
  sourceEndOffset?: number
  startOffset?: number
  endOffset?: number
}

// 前端内部使用的 Article（从 ArticleResponse 转换）
export interface Article {
  id: string
  title: string
  author?: string
  question?: string
  content: string
  canonicalContent: string
  paragraphs: string[]
  informationPoints: InformationPoint[]
  targetValue?: number
}

// ══════════════════════════════════════════════════════════
//  提示系统类型（POST /api/ai/hint）
// ══════════════════════════════════════════════════════════

/** 单条阅读建议 */
export interface HintItem {
  start: number           // 全文偏移（含）
  end: number             // 全文偏移（不含）
  type: string            // 卡牌类型：观点卡/情绪卡/漏洞卡/修辞卡
  preview: string         // 预览文本（前30字）
  reason: string          // 理由
}

/** 提示响应 */
export interface HintResponse {
  mode: 'rule' | 'deep'   // 规则引擎 | AI 深度
  message: string         // 看山气泡文案
  hints: HintItem[]       // 建议列表
  analysis?: string       // AI 深度分析文本（仅 deep 模式有值）
}

/** 提示请求 */
export interface HintRequest {
  scene: 'article'        // 场景（未来可扩展 backpack）
  article_id: string      // 文章 ID
  mode: 'rule' | 'deep'   // 模式
}

/** 前端使用的 hint 范围（用于高亮闪烁） */
export interface HintRange {
  start: number
  end: number
  type: string
}