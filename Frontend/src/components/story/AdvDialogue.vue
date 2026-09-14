<script setup lang="ts">
/**
 * ADV 对话框组件
 * 
 * 全屏底部对话框，用于剧情展示。
 * 支持打字机效果、点击继续、角色立绘。
 */

import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import type { StoryScript, DialogueLine } from '../../game/story/types'
import { getPortraitSrc } from '../../game/story/portraits'

const props = defineProps<{
  script: StoryScript | null
}>()

const emit = defineEmits<{
  complete: []
}>()

const currentLineIndex = ref(0)
const displayedText = ref('')
const isTyping = ref(false)
const typingTimer = ref<ReturnType<typeof setTimeout> | null>(null)

const currentLine = computed<DialogueLine | null>(() => {
  if (!props.script || currentLineIndex.value >= props.script.lines.length) return null
  return props.script.lines[currentLineIndex.value]
})

const isComplete = computed(() => {
  return !props.script || currentLineIndex.value >= props.script.lines.length
})

// 立绘随对话行切换；未配置立绘的角色（含旁白）返回 null，整个立绘区隐藏
const portraitSrc = computed(() => currentLine.value ? getPortraitSrc(currentLine.value.speaker) : null)

// 名字标签：直接使用后端返回的 speakerName
const speakerDisplayName = computed(() => currentLine.value?.speakerName ?? '')

const storySourceLabel = computed(() => {
  if (!props.script?.source) return ''
  if (props.script.source === 'ai') return 'AI 即兴剧情'
  if (props.script.source === 'fallback') return '本地保底剧情'
  return '本地剧情'
})



// 打字机效果
function startTyping(text: string) {
  if (typingTimer.value) clearTimeout(typingTimer.value)
  displayedText.value = ''
  isTyping.value = true

  let charIndex = 0
  const speed = 50 // 每字符毫秒

  function typeNext() {
    if (charIndex < text.length) {
      displayedText.value += text[charIndex]
      charIndex++
      typingTimer.value = setTimeout(typeNext, speed)
    } else {
      isTyping.value = false
    }
  }

  typeNext()
}

function handleNext() {
  if (isTyping.value) {
    // 跳过打字机，直接显示全文
    if (typingTimer.value) clearTimeout(typingTimer.value)
    if (currentLine.value) {
      displayedText.value = currentLine.value.text
    }
    isTyping.value = false
    return
  }

  if (!props.script) return

  currentLineIndex.value++
  if (currentLineIndex.value >= props.script.lines.length) {
    emit('complete')
  } else {
    const nextLine = props.script.lines[currentLineIndex.value]
    startTyping(nextLine.text)
  }
}

function handleKeyDown(e: KeyboardEvent) {
  if (e.key === ' ' || e.key === 'Enter') {
    e.preventDefault()
    handleNext()
  }
}

watch(() => props.script, (newScript) => {
  if (newScript && newScript.lines.length > 0) {
    currentLineIndex.value = 0
    startTyping(newScript.lines[0].text)
  }
}, { immediate: true })

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeyDown)
  if (typingTimer.value) clearTimeout(typingTimer.value)
})
</script>

<template>
  <div v-if="script" class="adv-dialogue-overlay" @click="handleNext">
    <!-- 背景遮罩 -->
    <div class="adv-backdrop"></div>

    <!-- 对话框主体 -->
    <div class="adv-dialogue-box">
      <!-- 角色立绘区：没有立绘的角色不占位，文本区自动占满 -->
      <div v-if="portraitSrc" class="adv-portrait-area">
        <div class="adv-portrait-frame">
          <!-- :key 绑定图片地址，换人时重建元素以重放 150ms 淡入 -->
          <img :key="portraitSrc" :src="portraitSrc" class="adv-portrait-img" alt="" />
        </div>
      </div>

      <!-- 文本区 -->
      <div class="adv-text-area">
        <div class="adv-dialogue-label">旅途小记</div>
        <div v-if="storySourceLabel" class="adv-story-source">
          {{ storySourceLabel }} · {{ script.title }}
        </div>

        <!-- 角色名 -->
        <div v-if="currentLine" class="adv-speaker-name">
          {{ currentLine.speakerName }}
        </div>

        <!-- 对话文本 -->
        <div class="adv-dialogue-text">
          {{ displayedText }}
          <span v-if="isTyping" class="typing-cursor">|</span>
        </div>

        <!-- 继续提示 -->
        <div v-if="!isTyping && !isComplete" class="adv-continue-hint">
          ▼ 点击继续
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.adv-dialogue-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 0 20px clamp(24px, 5vh, 48px);
  pointer-events: auto;
}

.adv-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(58, 45, 34, 0.5);
  backdrop-filter: blur(3px);
  pointer-events: none;
}

.adv-dialogue-box {
  position: relative;
  z-index: 1;
  display: flex;
  gap: 26px;
  width: 100%;
  max-width: 980px;
  padding: 22px 26px 24px;
  background:
    radial-gradient(circle at 12% 12%, rgba(255, 255, 255, 0.52), transparent 28%),
    linear-gradient(135deg, #f7efd9 0%, #eee0c2 100%);
  border: 2px solid rgba(155, 119, 76, 0.72);
  border-radius: 16px 8px 16px 8px;
  box-shadow: 0 16px 34px rgba(60, 45, 32, 0.22), 4px 5px 0 rgba(118, 82, 45, 0.12), inset 0 0 0 1px rgba(255, 255, 255, 0.5);
  color: #5c4734;
  pointer-events: auto;
}

.adv-portrait-area {
  flex-shrink: 0;
  width: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.adv-portrait-frame {
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(220, 197, 155, 0.72);
  border-radius: 50%;
  border: 2px solid rgba(145, 105, 63, 0.48);
  box-shadow: inset 0 0 0 5px rgba(255, 248, 220, 0.34), 2px 3px 0 rgba(110, 78, 45, 0.12);
}

.adv-portrait-img {
  max-height: 160px;
  max-width: 120px;
  object-fit: contain;
  animation: portrait-fade-in 150ms ease-out;
}

@keyframes portrait-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

.adv-text-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 9px;
  min-height: 108px;
}

.adv-dialogue-label {
  align-self: flex-start;
  margin-bottom: 1px;
  color: #92744d;
  font: 800 0.62rem/1 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.14em;
}

.adv-story-source {
  align-self: flex-start;
  margin-top: -5px;
  border: 1px solid rgba(146, 116, 77, 0.38);
  border-radius: 999px;
  padding: 4px 9px;
  background: rgba(255, 250, 236, 0.72);
  color: #8a704e;
  font: 800 0.58rem/1 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.07em;
}

.adv-speaker-name {
  font-size: 18px;
  font-weight: 700;
  color: #68462f;
  font-family: 'Noto Serif SC', 'Songti SC', serif;
}

/* 角色配色：看山青 / 旅行者暖白 / A 珊瑚红 / B 冰蓝 / C 灰紫 */
.adv-speaker-name.speaker-kanshan {
  color: #7fdbca;
  text-shadow: 0 0 8px rgba(127, 219, 202, 0.5);
}

.adv-speaker-name.speaker-player {
  color: #f0d9a8;
  text-shadow: 0 0 8px rgba(240, 217, 168, 0.45);
}

.adv-speaker-name.speaker-zhihu_user_a {
  color: #e88a7d;
  text-shadow: 0 0 8px rgba(232, 138, 125, 0.45);
}

.adv-speaker-name.speaker-zhihu_user_b {
  color: #7fa8d9;
  text-shadow: 0 0 8px rgba(127, 168, 217, 0.45);
}

.adv-speaker-name.speaker-zhihu_user_c {
  color: #a79bc4;
  text-shadow: 0 0 8px rgba(167, 155, 196, 0.45);
}

.adv-dialogue-text {
  font-size: 16px;
  line-height: 1.6;
  color: #5e4c3a;
  white-space: pre-wrap;
  word-break: break-word;
}

.typing-cursor {
  display: inline-block;
  animation: blink 0.8s infinite;
  color: #6d9a7b;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.adv-continue-hint {
  align-self: flex-end;
  font-size: 13px;
  color: #9b7d55;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}

@media (max-width: 640px) {
  .adv-dialogue-overlay { padding: 0 12px 18px; }
  .adv-dialogue-box { gap: 14px; padding: 16px 15px 17px; }
  .adv-portrait-area { width: 72px; }
  .adv-portrait-placeholder { width: 66px; height: 66px; }
  .portrait-emoji { font-size: 34px; }
  .adv-speaker-name { font-size: 16px; }
  .adv-dialogue-text { font-size: 14px; }
}
</style>
