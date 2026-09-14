/**
 * 看山常时交互 —— 事件总线
 *
 * 任何组件均可 import 后 emit 事件，KanshanPet 监听并弹出气泡。
 * 消息字符串统一维护在 kanshanMessages.ts 中。
 */

export type KanshanBubbleSemantic =
  | 'judge-success'
  | 'judge-fail'
  | 'card-place'
  | 'settle-pass'
  | 'settle-fail'

type Listener = (text: string, semantic?: KanshanBubbleSemantic) => void

const listeners = new Set<Listener>()

/** 订阅看山气泡事件，返回取消订阅函数 */
export function onKanshanBubble(fn: Listener): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/** 触发看山气泡（自动从消息池随机选取文本） */
export function kanshanBubble(text: string, semantic?: KanshanBubbleSemantic): void {
  listeners.forEach(fn => fn(text, semantic))
}
