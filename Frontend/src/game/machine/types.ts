/**
 * 游戏主状态机 —— 类型定义
 * 
 * v5 屏幕状态流转（xstate 管理）：
 * map → round-intro → article → map-needs-vector → map-ready
 *       → article-gen → round-settlement → map-moving → random-event → (循环)
 * 
 * v5 变化（vs v4）：
 * - 新增 article-gen 状态（每局文章生成，在结算前触发）
 * - 提交后流程：map-ready →SUBMIT→ article-gen →ARTICLE_DONE→ round-settlement
 * - write 状态保留给六局结束的最终随笔
 */

export type GameScreen =
  | 'map'                // 地图页（默认/自由探索态）
  | 'round-intro'        // 本局开场（旅行笔记弹窗，可跳过）
  | 'article'            // 文章阅读 + 划线得卡
  | 'map-needs-vector'   // 地图页，等待提交向量
  | 'map-ready'          // 地图页，向量已提交，等待激活知北针
  | 'article-gen'        // 每局文章生成（感叹号气泡 + 全屏覆盖层）
  | 'write'              // AI 生成随笔（六局最终，可跳过）
  | 'map-moving'         // 看山移动动画中
  | 'round-settlement'   // 本局结算弹窗（前端本地计算）
  | 'random-event'       // 随机事件 / 剧情触发
  | 'final-settlement'   // 6局结束，最终结算

/** 状态机事件类型 */
export type GameEvent =
  | { type: 'BEGIN_ROUND' }           // map → round-intro
  | { type: 'SKIP_INTRO' }            // round-intro → map（跳过开场）
  | { type: 'OPEN_ARTICLE' }          // round-intro / map → article
  | { type: 'COMPLETE_READING' }      // article → map-needs-vector / map-ready
  | { type: 'SUBMIT_VECTOR' }         // map-needs-vector → map-ready
  | { type: 'SUBMIT' }                // map-ready → article-gen（提交配卡，触发文章生成）
  | { type: 'SHOW_ARTICLE' }          // article-gen 内部：感叹号气泡已点击，显示文章窗口
  | { type: 'SKIP_ARTICLE' }          // article-gen → round-settlement（跳过文章）
  | { type: 'ARTICLE_DONE' }          // article-gen → round-settlement（文章阅读完成）
  | { type: 'START_WRITE' }           // （保留）map-ready → write（最终随笔）
  | { type: 'SKIP_WRITE' }            // （保留）write → map-ready
  | { type: 'FINISH_WRITE' }          // （保留）write → map-ready
  | { type: 'ACTIVATE_COMPASS' }      // round-settlement → map-moving
  | { type: 'MOVEMENT_COMPLETE' }     // map-moving → round-settlement
  | { type: 'SETTLEMENT_DONE' }       // round-settlement → random-event
  | { type: 'EVENT_RESOLVED' }        // random-event → round-intro
  | { type: 'CONTINUE_JOURNEY' }      // round-settlement → round-intro（旧流程兼容）
  | { type: 'RESET_GAME' }            // 任意 → map（重置）
  | { type: 'RETURN_TO_MAP' }         // article / write → map（随时返回）

/** 从字符串反推 GameScreen（用于持久化恢复） */
export function isGameScreen(value: unknown): value is GameScreen {
  const screens: readonly GameScreen[] = [
    'map', 'round-intro', 'article', 'map-needs-vector', 'map-ready',
    'article-gen', 'write', 'map-moving', 'round-settlement', 'random-event', 'final-settlement',
  ]
  return typeof value === 'string' && screens.includes(value as GameScreen)
}
