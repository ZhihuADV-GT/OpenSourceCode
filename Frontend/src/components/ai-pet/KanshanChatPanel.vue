<script setup lang="ts">
/**
 * 看山聊天面板模块
 *
 * 职责：
 * - 展开/收起聊天界面
 * - 聊天记录管理（玩家消息 + AI回复）
 * - 当前阶段使用固定对话库，后续接入大模型 API
 */
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
const kanshanStickerImg = '' // [art-assets disabled] ../../assets/kanshan-dialog/kanshan-sticker.webp
const planetStickerImg = '' // [art-assets disabled] ../../assets/kanshan-dialog/planet-sticker.webp
const starStickerImg = '' // [art-assets disabled] ../../assets/kanshan-dialog/star-sticker.webp
import {
  getKanshanExpression,
  type KanshanExpressionName,
} from '../../data/kanshanExpressions'
import { useAchievementStore as getAchievementStore } from '../../stores/achievements'
import { onKanshanBubble, type KanshanBubbleSemantic } from '../../services/kanshanEvents'
import {
  takeNextKanshanDecorationVariant,
  type KanshanDecorationVariant,
} from '../kanshanDecorationVariants'

/* ===================== 降级对话库（API 失败时使用） ===================== */

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]
}

const aiReplies: string[] = [
  '你好呀，我是看山！',
  '我在知乎解答问题呢~',
  '今天有什么有趣的事吗？',
  '有什么想聊的，尽管说吧！',
  '旅途辛苦了，歇一歇吧。',
]

/* ===================== 数据结构 ===================== */

interface ChatMessage {
  id: number
  sender: 'player' | 'ai'
  text: string
}

/* ===================== 状态 ===================== */

const isExpanded = ref(false)
const decorationVariant = ref<KanshanDecorationVariant>('orbit')
const messages = ref<ChatMessage[]>([])
const isAiTyping = ref(false)
const currentAvatarExpression = ref<KanshanExpressionName>('neutral')
const chatListRef = ref<HTMLDivElement | null>(null)
const playerInput = ref('')
const currentAvatarImage = computed(() => getKanshanExpression(currentAvatarExpression.value))

const avatarExpressionByBubbleSemantic: Record<KanshanBubbleSemantic, KanshanExpressionName> = {
  'judge-success': 'happy',
  'judge-fail': 'confused',
  'card-place': 'okay',
  'settle-pass': 'cheer',
  'settle-fail': 'confused',
}

let messageId = 0
let interactionSequence = 0

const emit = defineEmits<{
  'expanded-change': [expanded: boolean]
}>()

/* ===================== 方法 ===================== */

function toggleExpanded(): void {
  if (!isExpanded.value) {
    decorationVariant.value = takeNextKanshanDecorationVariant(decorationVariant.value)
  }
  isExpanded.value = !isExpanded.value
  emit('expanded-change', isExpanded.value)
}

async function pushMessage(sender: ChatMessage['sender'], text: string): Promise<void> {
  messages.value.push({ id: ++messageId, sender, text })
  await nextTick()
  if (chatListRef.value) {
    chatListRef.value.scrollTop = chatListRef.value.scrollHeight
  }
}

async function sendMessage(): Promise<void> {
  const text = playerInput.value.trim()
  if (isAiTyping.value) return
  if (!text) {
    currentAvatarExpression.value = 'confused'
    return
  }
  playerInput.value = ''

  const interactionId = createInteractionId()
  void pushMessage('player', text)
  getAchievementStore().recordKanshanInteraction(interactionId)
  isAiTyping.value = true
  currentAvatarExpression.value = 'thinking'

  try {
    const resp = await fetch('/api/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history: messages.value.slice(-10).map(m => ({ sender: m.sender, text: m.text })),
      }),
    })
    if (resp.ok) {
      const data = await resp.json()
      const reply = typeof data.reply === 'string' ? data.reply : pick(aiReplies)
      await pushMessage('ai', reply)
      currentAvatarExpression.value = 'happy'
    } else {
      await pushMessage('ai', pick(aiReplies))
      currentAvatarExpression.value = 'confused'
    }
  } catch {
    await pushMessage('ai', pick(aiReplies))
    currentAvatarExpression.value = 'confused'
  } finally {
    isAiTyping.value = false
  }
}

function createInteractionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  interactionSequence += 1
  return `kanshan-${Date.now()}-${interactionSequence}-${Math.random().toString(36).slice(2)}`
}

function handleInputKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    void sendMessage()
  }
}

function cleanup(): void {
  unsubscribeBubble()
}

const unsubscribeBubble = onKanshanBubble((text, semantic) => {
  if (!semantic) return
  currentAvatarExpression.value = avatarExpressionByBubbleSemantic[semantic]
  void pushMessage('ai', text)
})

defineExpose({ isExpanded, toggleExpanded })

onBeforeUnmount(cleanup)
</script>

<template>
  <div
    class="kanshan-chat-root"
    :class="[
      isExpanded ? 'kanshan-chat-root--expanded' : 'kanshan-chat-root--compact',
      `kanshan-chat-root--${decorationVariant}`,
    ]"
  >
    <!-- 展开模式：右上角关闭按钮 -->
    <div v-if="isExpanded" class="kanshan-chat-close-wrap">
      <button
        type="button"
        class="kanshan-chat-close"
        title="收起"
        @click.stop="toggleExpanded"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          class="w-4 h-4"
        >
          <path d="M18 6 6 18" />
          <path d="m6 6 12 12" />
        </svg>
      </button>
    </div>

    <!-- 聊天面板 -->
    <div v-if="isExpanded" class="kanshan-chat-panel">
      <header class="kanshan-chat-header">
        <div>
          <strong>看山通信记录</strong>
          <span>KANSHAN AI COMPANION</span>
        </div>
        <div class="kanshan-chat-header__avatar" aria-live="polite">
          <Transition name="kanshan-expression-fade" mode="out-in">
            <img
              :key="currentAvatarExpression"
              :src="currentAvatarImage"
              class="kanshan-chat-header__avatar-image"
              alt="看山当前表情"
              draggable="false"
            />
          </Transition>
        </div>
      </header>

      <!-- 装饰贴纸 -->
      <img class="kanshan-chat-decoration kanshan-chat-decoration--star" :src="starStickerImg" alt="" aria-hidden="true" />
      <img class="kanshan-chat-decoration kanshan-chat-decoration--star-secondary" :src="starStickerImg" alt="" aria-hidden="true" />
      <img class="kanshan-chat-decoration kanshan-chat-decoration--planet" :src="planetStickerImg" alt="" aria-hidden="true" />
      <img class="kanshan-chat-decoration kanshan-chat-decoration--explorer" :src="kanshanStickerImg" alt="" aria-hidden="true" />

      <!-- 聊天记录列表 -->
      <div ref="chatListRef" class="kanshan-chat-list">
        <div v-if="messages.length === 0 && !isAiTyping" class="kanshan-chat-empty">
          <span class="kanshan-chat-empty__avatar" aria-hidden="true">山</span>
          <p>旅途中想聊点什么？我会陪你一起辨认方向。</p>
        </div>

        <div
          v-for="msg in messages"
          :key="msg.id"
          class="kanshan-chat-message"
          :class="`kanshan-chat-message--${msg.sender}`"
        >
          <span v-if="msg.sender === 'ai'" class="kanshan-chat-avatar" aria-hidden="true">山</span>
          <div
            class="kanshan-chat-bubble"
            :class="`kanshan-chat-bubble--${msg.sender}`"
          >
            {{ msg.text }}
          </div>
        </div>

        <!-- 看山正在输入 -->
        <div v-if="isAiTyping" class="kanshan-chat-message kanshan-chat-message--ai">
          <span class="kanshan-chat-avatar" aria-hidden="true">山</span>
          <div class="kanshan-chat-bubble kanshan-chat-bubble--ai kanshan-chat-bubble--typing">
            看山正在输入…
          </div>
        </div>
      </div>

      <!-- 底部：输入框 + 发送按钮 -->
      <div class="kanshan-chat-composer">
        <input
          v-model="playerInput"
          type="text"
          class="kanshan-chat-input"
          placeholder="和看山说点什么…"
          :disabled="isAiTyping"
          maxlength="200"
          @keydown="handleInputKeydown"
        />
        <button
          type="button"
          class="kanshan-chat-send"
          :disabled="isAiTyping || !playerInput.trim()"
          @click="void sendMessage()"
        >
          {{ isAiTyping ? '思考中' : '发送' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.kanshan-chat-root--compact {
  display: none;
}
.kanshan-chat-root--expanded {
  position: relative;
  width: 300px;
  height: 300px;
  border: 5px solid #68402d;
  border-radius: 14px;
  background: #f7ecd2;
  box-shadow: 7px 8px 0 rgba(65, 38, 27, 0.3), 0 16px 28px rgba(44, 27, 22, 0.24);
  color: #4c3425;
}

.kanshan-chat-close-wrap {
  position: absolute;
  z-index: 20;
  top: 8px;
  right: 8px;
}
.kanshan-chat-close {
  display: grid;
  width: 27px;
  height: 27px;
  place-items: center;
  border: 2px solid #68402d;
  border-radius: 50%;
  background: #fff8e6;
  color: #68402d;
  box-shadow: 2px 2px 0 rgba(91, 53, 36, 0.26);
  cursor: pointer;
}
.kanshan-chat-close:hover { background: #f4ddb0; }

.kanshan-chat-panel {
  position: relative;
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  flex-direction: column;
}
.kanshan-chat-header {
  position: relative;
  z-index: 2;
  display: flex;
  min-height: 43px;
  flex: 0 0 43px;
  align-items: center;
  border-bottom: 2px solid #8e6248;
  padding: 6px 48px 5px 54px;
  background: #e8cf9f;
  box-shadow: inset 0 -3px 0 rgba(107, 62, 43, 0.12);
}
.kanshan-chat-header__avatar {
  position: absolute;
  top: 3px;
  left: 10px;
  width: 36px;
  height: 36px;
  overflow: hidden;
  border-radius: 50%;
  background: rgba(255, 250, 238, 0.52);
}
.kanshan-chat-header__avatar-image { display: block; width: 100%; height: 100%; object-fit: contain; }
.kanshan-expression-fade-enter-active,
.kanshan-expression-fade-leave-active { transition: opacity 180ms ease, transform 180ms ease; }
.kanshan-expression-fade-enter-from,
.kanshan-expression-fade-leave-to { opacity: 0; transform: scale(0.96); }
.kanshan-chat-header strong { display: block; font-size: 0.75rem; line-height: 1.15; }
.kanshan-chat-header span { display: block; margin-top: 3px; color: #87644d; font: 800 0.43rem/1 ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: 0.09em; }

.kanshan-chat-list {
  position: relative;
  z-index: 2;
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  padding: 12px 10px;
  background:
    linear-gradient(rgba(126, 89, 59, 0.04) 1px, transparent 1px) 0 0 / 14px 14px,
    #f8efd9;
  scrollbar-color: #b38964 #ead7b5;
  scrollbar-width: thin;
}
.kanshan-chat-empty {
  display: flex;
  width: 86%;
  align-items: center;
  gap: 8px;
  margin: auto;
  border: 1px dashed #c6a77a;
  border-radius: 10px;
  padding: 10px;
  background: rgba(255, 250, 238, 0.82);
  color: #7b604c;
}
.kanshan-chat-empty p { margin: 0; font-size: 0.68rem; line-height: 1.45; }
.kanshan-chat-empty__avatar,
.kanshan-chat-avatar {
  display: grid;
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
  place-items: center;
  border: 2px solid #68402d;
  border-radius: 50%;
  background: #efd38d;
  color: #573724;
  font-size: 0.58rem;
  font-weight: 900;
}
.kanshan-chat-message { display: flex; align-items: flex-end; gap: 6px; }
.kanshan-chat-message--player { justify-content: flex-end; }
.kanshan-chat-message--ai { justify-content: flex-start; }
.kanshan-chat-bubble {
  max-width: 76%;
  overflow-wrap: anywhere;
  border: 1px solid transparent;
  padding: 7px 10px;
  font-size: 0.73rem;
  font-weight: 650;
  line-height: 1.45;
  box-shadow: 2px 3px 0 rgba(83, 48, 32, 0.12);
}
.kanshan-chat-bubble--player {
  border-color: #3d8784;
  border-radius: 13px 13px 3px 13px;
  background: #69b5b0;
  color: #153c3a;
}
.kanshan-chat-bubble--ai {
  border-color: #d0b487;
  border-radius: 13px 13px 13px 3px;
  background: #fffaf0;
  color: #4b3324;
}
.kanshan-chat-bubble--typing { color: #8c7766; font-weight: 600; }
.kanshan-chat-composer {
  position: relative;
  z-index: 3;
  display: flex;
  min-height: 50px;
  flex: 0 0 50px;
  align-items: center;
  gap: 8px;
  border-top: 2px solid #8e6248;
  padding: 6px 9px;
  background: #ead6ae;
}
.kanshan-chat-input {
  flex: 1 1 auto;
  min-width: 0;
  border: 2px solid #b38964;
  border-radius: 8px;
  padding: 8px 10px;
  background: #fffaf0;
  color: #4b3324;
  font-size: 0.72rem;
  font-weight: 600;
  outline: none;
  transition: border-color 120ms ease;
}
.kanshan-chat-input:focus { border-color: #5c9f9b; }
.kanshan-chat-input:disabled { opacity: 0.48; cursor: not-allowed; }
.kanshan-chat-input::placeholder { color: #a08870; font-weight: 500; }
.kanshan-chat-send {
  flex: 1 1 auto;
  border: 2px solid #4c716d;
  border-radius: 8px;
  padding: 9px 10px;
  background: #5c9f9b;
  color: #fffbea;
  box-shadow: 0 3px 0 #365b59;
  font-size: 0.72rem;
  font-weight: 800;
  cursor: pointer;
  transition: filter 120ms ease, transform 120ms ease, box-shadow 120ms ease;
}
.kanshan-chat-send:hover { filter: brightness(1.08); }
.kanshan-chat-send:active { transform: translateY(2px); box-shadow: 0 1px 0 #365b59; }
.kanshan-chat-send:disabled { opacity: 0.48; cursor: not-allowed; filter: grayscale(0.35); }

.kanshan-chat-decoration { position: absolute; z-index: 5; object-fit: contain; pointer-events: none; user-select: none; }
.kanshan-chat-decoration--star { top: 6px; left: 150px; width: 24px; transform: rotate(-10deg); }
.kanshan-chat-decoration--star-secondary { display: none; top: 18px; left: 180px; width: 15px; opacity: 0.76; }
.kanshan-chat-decoration--planet { top: 5px; left: 188px; width: 32px; transform: rotate(8deg); }
.kanshan-chat-decoration--explorer { display: none; top: 1px; left: 172px; width: 42px; }
.kanshan-chat-root--stargaze .kanshan-chat-decoration--star { left: 156px; width: 22px; transform: rotate(14deg); }
.kanshan-chat-root--stargaze .kanshan-chat-decoration--star-secondary { display: block; left: 195px; }
.kanshan-chat-root--stargaze .kanshan-chat-decoration--planet { display: none; }
.kanshan-chat-root--explorer .kanshan-chat-decoration--star { left: 147px; width: 18px; }
.kanshan-chat-root--explorer .kanshan-chat-decoration--planet { display: none; }
.kanshan-chat-root--explorer .kanshan-chat-decoration--explorer { display: block; left: 180px; }
.kanshan-chat-root--signal .kanshan-chat-decoration--star { left: 162px; width: 18px; transform: rotate(22deg); }
.kanshan-chat-root--signal .kanshan-chat-decoration--star-secondary { display: block; top: 5px; left: 192px; width: 19px; }
.kanshan-chat-root--signal .kanshan-chat-decoration--planet { display: none; }
@media (prefers-reduced-motion: reduce) {
  .kanshan-expression-fade-enter-active,
  .kanshan-expression-fade-leave-active { transition: none; }
}
</style>
