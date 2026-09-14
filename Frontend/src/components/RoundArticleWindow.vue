<script setup lang="ts">
/**
 * 每局文章生成窗口 —— 全屏覆盖层
 *
 * 在结算前弹出，看山为这一程写下的随笔。
 * 风格与 FinalEssayWindow 一致：淡黄纸张质感 + 打字机效果。
 */
import { computed, ref, watch, onUnmounted } from 'vue'
import { generateRoundArticle } from '../services/articleGenerateService'
import type { ArticleGenerateResponse } from '../types/articleGenerate'
import { useCreationFlowStore } from '../stores/creationFlow'
import { useMaterialStore } from '../stores/material'

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  done: []
  skip: []
}>()

const creationStore = useCreationFlowStore()
const materialStore = useMaterialStore()

// ── 状态 ──
const isGenerating = ref(false)
const generationError = ref('')
const articleResult = ref<ArticleGenerateResponse | null>(null)

// ── 打字机效果 ──
const displayedText = ref('')
const isTyping = ref(false)
let typingTimer: ReturnType<typeof setTimeout> | null = null

function clearTypingTimer() {
  if (typingTimer) {
    clearTimeout(typingTimer)
    typingTimer = null
  }
}

onUnmounted(() => clearTypingTimer())

// ── 构建卡槽快照 ──
function buildSlotSnapshot(): [string, string][] {
  const snapshot: [string, string][] = []
  for (const slot of creationStore.slots) {
    if (slot.materialId === null) continue
    const material = materialStore.getMaterialById(slot.materialId)
    if (!material) continue
    const cardId = material.informationPointId?.trim()
    if (!cardId) continue
    snapshot.push([String(slot.index), cardId])
  }
  return snapshot
}

// ── 生成文章 ──
async function startGeneration() {
  if (isGenerating.value || articleResult.value) return

  clearTypingTimer()
  displayedText.value = ''
  isTyping.value = false
  generationError.value = ''
  isGenerating.value = true

  const slots = buildSlotSnapshot()
  if (slots.length === 0) {
    isGenerating.value = false
    generationError.value = '没有可用的卡牌素材'
    return
  }

  try {
    const result = await generateRoundArticle(slots)
    // 后端可能返回空 content（例如所有卡牌都取不到原文），此时若直接进打字机，
    // typeNextChar 会因 0 < 0 不成立而立即结束，玩家只看到一张白纸，
    // 且 generationError 仍为空 → 没有任何提示，看起来像卡死
    if (!result.content || !result.content.trim()) {
      console.warn('[RoundArticleWindow] 后端返回空文章内容:', result)
      isGenerating.value = false
      generationError.value = '看山盯着这些素材，却没能写出一个字（原因：缺乏观点卡）'
      return
    }
    articleResult.value = result
    isGenerating.value = false
    startTyping(result.content)
  } catch (error) {
    console.error('[RoundArticleWindow] 文章生成失败:', error)
    isGenerating.value = false
    generationError.value = '看山暂时没能写下这篇随笔'
  }
}

// ── 打字机 ──
const currentCharIndex = ref(0)

function startTyping(content: string) {
  clearTypingTimer()
  displayedText.value = ''
  currentCharIndex.value = 0
  isTyping.value = true
  typeNextChar(content)
}

function typeNextChar(content: string) {
  if (!isTyping.value) return
  if (currentCharIndex.value < content.length) {
    displayedText.value = content.slice(0, currentCharIndex.value + 1)
    currentCharIndex.value++
    typingTimer = setTimeout(() => typeNextChar(content), 32)
  } else {
    isTyping.value = false
    typingTimer = null
  }
}

function skipTyping() {
  clearTypingTimer()
  if (articleResult.value) {
    displayedText.value = articleResult.value.content
    currentCharIndex.value = articleResult.value.content.length
  }
  isTyping.value = false
}

// ── 监听 visible ──
watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      // 重置状态，开始生成
      articleResult.value = null
      generationError.value = ''
      startGeneration()
    } else {
      clearTypingTimer()
      isTyping.value = false
    }
  },
)

const articleTitle = computed(() => articleResult.value?.title ?? '这一程的随笔')
const hasArticle = computed(() => articleResult.value !== null)
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="round-article-overlay" @click.self="emit('skip')">
      <article class="round-article-window" aria-labelledby="round-article-title">

        <header class="round-article-header">
          <p class="round-article-eyebrow">TRAVEL NOTE · ROUND</p>
          <h1 id="round-article-title">看山记下的这一程</h1>
        </header>

        <!-- 加载中 -->
        <div v-if="isGenerating" class="round-article-loading" aria-live="polite">
          <span class="round-article-loading-mark" aria-hidden="true">✦</span>
          <strong>看山正在落笔……</strong>
          <span>让记忆在纸面上慢慢归位</span>
        </div>

        <!-- 错误状态 -->
        <div v-else-if="generationError && !hasArticle" class="round-article-fallback">
          <p>{{ generationError }}</p>
          <p class="round-article-fallback-hint">旅途仍在继续，下一站还有新的故事。</p>
          <div class="round-article-actions">
            <button type="button" class="round-article-primary-action" @click="emit('skip')">
              继续出发
            </button>
          </div>
        </div>

        <!-- 文章内容 -->
        <template v-else-if="hasArticle">
          <section class="round-article-paper" aria-label="本局随笔">
            <div class="round-article-paper-rule" aria-hidden="true" />
            <h2>{{ articleTitle }}</h2>
            <p class="round-article-content">{{ displayedText }}<span v-if="isTyping" class="round-article-cursor" aria-hidden="true">|</span></p>
            <button
              v-if="isTyping"
              class="round-article-skip-typing"
              type="button"
              @click="skipTyping"
            >
              查看全文
            </button>
          </section>

          <footer class="round-article-actions">
            <button type="button" class="round-article-secondary-action" @click="emit('skip')">
              跳过
            </button>
            <button type="button" class="round-article-primary-action" @click="emit('done')">
              完成
            </button>
          </footer>
        </template>

      </article>
    </div>
  </Teleport>
</template>

<style scoped>
.round-article-overlay {
  position: fixed;
  z-index: 150;
  inset: 0;
  display: grid;
  place-items: center;
  overflow: auto;
  padding: 24px;
  background: rgba(29, 40, 48, 0.66);
  backdrop-filter: blur(7px);
}

.round-article-window {
  position: relative;
  width: min(680px, calc(100vw - 32px));
  max-height: calc(100vh - 48px);
  overflow: auto;
  border: 1px solid #9a8068;
  border-radius: 8px;
  padding: 32px clamp(22px, 5vw, 54px) 24px;
  background:
    linear-gradient(rgba(255, 252, 239, 0.9), rgba(248, 241, 220, 0.96)),
    #f8f1dc;
  box-shadow: 7px 8px 0 rgba(45, 38, 32, 0.2), 0 20px 42px rgba(21, 30, 34, 0.3);
  color: #4c4038;
}

/* ── 标题栏 ── */
.round-article-header { text-align: center; }
.round-article-eyebrow {
  margin: 0 0 8px;
  color: #648692;
  font: 800 0.62rem ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.14em;
}
.round-article-header h1 {
  margin: 0;
  color: #4d3d32;
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: clamp(1.15rem, 2.8vw, 1.6rem);
  letter-spacing: 0.08em;
}

/* ── 加载中 ── */
.round-article-loading {
  display: grid;
  justify-items: center;
  gap: 9px;
  min-height: 220px;
  align-content: center;
  margin-top: 24px;
  border: 1px dashed #b7a58c;
  background: rgba(255, 252, 239, 0.62);
  color: #756554;
}
.round-article-loading-mark {
  color: #648e9a;
  font-size: 1.5rem;
  animation: round-article-breathe 1.3s ease-in-out infinite;
}
.round-article-loading strong {
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: 0.95rem;
}
.round-article-loading span:last-child {
  color: #a18d7a;
  font-size: 0.7rem;
}

/* ── 降级提示 ── */
.round-article-fallback {
  margin-top: 24px;
  padding: 24px;
  text-align: center;
  border: 1px dashed #b7a58c;
  background: rgba(255, 252, 239, 0.62);
  color: #756554;
}
.round-article-fallback p { margin: 0 0 8px; font-size: 0.85rem; }
.round-article-fallback-hint { color: #a18d7a; font-size: 0.72rem; }

/* ── 文章纸面 ── */
.round-article-paper {
  position: relative;
  min-height: 200px;
  margin-top: 24px;
  border: 1px solid #d0bea0;
  border-radius: 3px;
  padding: 22px 22px 18px;
  background: rgba(255, 253, 244, 0.72);
  box-shadow: inset 0 0 0 3px rgba(232, 220, 193, 0.42);
}
.round-article-paper-rule {
  width: 44px;
  height: 3px;
  margin-bottom: 13px;
  background: #6f99a3;
}
.round-article-paper h2 {
  margin: 0 0 14px;
  color: #5d4939;
  font: 800 1rem/1.3 'Noto Serif SC', 'Songti SC', serif;
}
.round-article-content {
  margin: 0;
  color: #594c43;
  font: 0.9rem/2 'Noto Serif SC', 'Songti SC', serif;
  white-space: pre-line;
}
.round-article-cursor {
  color: #648e9a;
  font-weight: 300;
  animation: round-article-blink 0.8s step-end infinite;
}
.round-article-skip-typing {
  margin-top: 12px;
  border: 0;
  background: transparent;
  color: #648692;
  font-size: 0.7rem;
  cursor: pointer;
}

/* ── 操作按钮 ── */
.round-article-actions {
  display: flex;
  justify-content: flex-end;
  gap: 9px;
  margin-top: 22px;
}
.round-article-actions button {
  border-radius: 4px;
  padding: 9px 15px;
  font-size: 0.72rem;
  font-weight: 800;
  cursor: pointer;
}
.round-article-secondary-action {
  border: 1px solid #a99a87;
  background: transparent;
  color: #786756;
}
.round-article-secondary-action:hover { background: rgba(169, 154, 135, 0.12); }
.round-article-primary-action {
  border: 1px solid #577f8b;
  background: #668f9a;
  color: #fffdf1;
  box-shadow: 2px 2px 0 rgba(68, 93, 100, 0.24);
}
.round-article-primary-action:hover { background: #5a828c; }

/* ── 动画 ── */
@keyframes round-article-breathe {
  0%, 100% { opacity: 0.45; transform: scale(0.86); }
  50% { opacity: 1; transform: scale(1.12); }
}
@keyframes round-article-blink {
  50% { opacity: 0; }
}

/* ── 响应式 ── */
@media (max-width: 620px) {
  .round-article-overlay { padding: 12px; }
  .round-article-window { max-height: calc(100vh - 24px); padding: 27px 16px 18px; }
  .round-article-content { font-size: 0.83rem; line-height: 1.85; }
}
</style>
