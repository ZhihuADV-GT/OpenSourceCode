<script setup lang="ts">
/**
 * 文章阅读提示弹窗
 *
 * 显示看山的阅读建议：文章结构分析 + 句子级推荐区域
 * 点击"跳转"可滚动到对应位置并高亮闪烁
 */

import { ref } from 'vue'
import type { HintItem } from '../../types/article'

const props = defineProps<{
  visible: boolean
  message: string
  hints: HintItem[]
  loading?: boolean
  analysis?: string
}>()

const emit = defineEmits<{
  close: []
  'jump-to-hint': [hint: HintItem]
  'deep-analysis': []
}>()

/** 当前选中的 hint（用于高亮） */
const selectedHint = ref<HintItem | null>(null)

function handleJump(hint: HintItem) {
  selectedHint.value = hint
  emit('jump-to-hint', hint)
}

function handleDeepAnalysis() {
  emit('deep-analysis')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="hint-modal-backdrop" @click="emit('close')">
      <div class="hint-modal-root" @click.stop>
        <!-- 标题栏 -->
        <header class="hint-modal-header">
          <span class="hint-modal-icon">💡</span>
          <h3>看山的阅读建议</h3>
          <button class="hint-modal-close" type="button" @click="emit('close')">✕</button>
        </header>

        <!-- 气泡文案 -->
        <div class="hint-modal-message">
          <p>{{ message }}</p>
        </div>

        <!-- 推荐区域列表 -->
        <div class="hint-modal-list">
          <div
            v-for="(hint, index) in hints"
            :key="`${hint.start}-${hint.end}`"
            class="hint-modal-item"
            :class="{ 'hint-modal-item--selected': selectedHint === hint }"
          >
            <div class="hint-modal-item-header">
              <span class="hint-modal-item-index">{{ index + 1 }}</span>
              <span class="hint-modal-item-type" :data-type="hint.type">{{ hint.type }}</span>
            </div>
            <p class="hint-modal-item-preview">{{ hint.preview }}</p>
            <p class="hint-modal-item-reason">{{ hint.reason }}</p>
            <button
              class="hint-modal-item-jump"
              type="button"
              @click="handleJump(hint)"
            >
              跳转到此处
            </button>
          </div>
        </div>

        <!-- AI 深度分析结果 -->
        <div v-if="analysis" class="hint-modal-analysis">
          <h4>🔍 看山的深度分析</h4>
          <p>{{ analysis }}</p>
        </div>

        <!-- 深度分析按钮（预留） -->
        <div class="hint-modal-footer">
          <button
            class="hint-modal-deep-btn"
            type="button"
            :disabled="loading"
            @click="handleDeepAnalysis"
          >
            {{ loading ? '分析中…' : '🔍 深度分析（AI）' }}
          </button>
          <small class="hint-modal-footer-note">AI 分析需要 3-5 秒</small>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.hint-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(2px);
  display: grid;
  place-items: center;
}

.hint-modal-root {
  width: min(420px, 90vw);
  max-height: 80vh;
  overflow: auto;
  border: 2px solid rgba(157, 124, 77, 0.68);
  border-radius: 4px;
  background: linear-gradient(145deg, #f8efd8 0%, #f3e8bd 100%);
  box-shadow: 4px 6px 0 rgba(92, 66, 35, 0.25);
  font-family: 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
}

.hint-modal-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(157, 124, 77, 0.3);
  background: rgba(248, 239, 216, 0.96);
}

.hint-modal-icon {
  font-size: 1.2rem;
}

.hint-modal-header h3 {
  flex: 1;
  margin: 0;
  font-size: 0.95rem;
  font-weight: 800;
  color: #6c5435;
}

.hint-modal-close {
  width: 28px;
  height: 28px;
  border: 1px solid rgba(157, 124, 77, 0.4);
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.6);
  color: #6c5435;
  font-size: 0.9rem;
  cursor: pointer;
  transition: background 120ms ease;
}

.hint-modal-close:hover {
  background: rgba(255, 255, 255, 0.9);
}

.hint-modal-message {
  padding: 12px 16px;
  border-bottom: 1px dashed rgba(157, 124, 77, 0.3);
  background: rgba(243, 232, 189, 0.5);
}

.hint-modal-message p {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 600;
  color: #5a4428;
  line-height: 1.6;
}

.hint-modal-list {
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hint-modal-item {
  border: 1px solid rgba(157, 124, 77, 0.3);
  border-radius: 3px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.4);
  transition: border-color 150ms ease, background 150ms ease;
}

.hint-modal-item:hover {
  border-color: rgba(157, 124, 77, 0.5);
  background: rgba(255, 255, 255, 0.6);
}

.hint-modal-item--selected {
  border-color: #9d7c4d;
  background: rgba(248, 239, 216, 0.8);
  box-shadow: inset 0 0 0 1px rgba(157, 124, 77, 0.3);
}

.hint-modal-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.hint-modal-item-index {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #9d7c4d;
  color: #fff;
  font-size: 0.75rem;
  font-weight: 800;
  display: grid;
  place-items: center;
}

.hint-modal-item-type {
  padding: 2px 8px;
  border-radius: 2px;
  font-size: 0.72rem;
  font-weight: 700;
  color: #fff;
}

.hint-modal-item-type[data-type="观点卡"] {
  background: #5b8c6f;
}

.hint-modal-item-type[data-type="情绪卡"] {
  background: #c77d5a;
}

.hint-modal-item-type[data-type="漏洞卡"] {
  background: #8b6b9e;
}

.hint-modal-item-type[data-type="修辞卡"] {
  background: #6b8fa8;
}

.hint-modal-item-preview {
  margin: 0 0 4px;
  font-size: 0.82rem;
  font-weight: 600;
  color: #4a3a22;
  line-height: 1.5;
}

.hint-modal-item-reason {
  margin: 0 0 8px;
  font-size: 0.75rem;
  color: #7a6548;
  line-height: 1.4;
}

.hint-modal-item-jump {
  width: 100%;
  padding: 6px 12px;
  border: 1px solid rgba(157, 124, 77, 0.4);
  border-radius: 2px;
  background: rgba(248, 239, 216, 0.9);
  color: #6c5435;
  font-size: 0.78rem;
  font-weight: 700;
  cursor: pointer;
  transition: background 120ms ease, transform 100ms ease;
}

.hint-modal-item-jump:hover {
  background: #f5e5bf;
  transform: translateY(-1px);
}

.hint-modal-analysis {
  margin: 0 16px 12px;
  padding: 10px 12px;
  border: 1px solid rgba(107, 143, 168, 0.4);
  border-radius: 3px;
  background: rgba(107, 143, 168, 0.08);
}

.hint-modal-analysis h4 {
  margin: 0 0 6px;
  font-size: 0.8rem;
  font-weight: 800;
  color: #4a6b80;
}

.hint-modal-analysis p {
  margin: 0;
  font-size: 0.8rem;
  color: #4a5a68;
  line-height: 1.7;
  white-space: pre-wrap;
}

.hint-modal-footer {
  padding: 12px 16px;
  border-top: 1px solid rgba(157, 124, 77, 0.3);
  background: rgba(243, 232, 189, 0.5);
  text-align: center;
}

.hint-modal-deep-btn {
  width: 100%;
  padding: 8px 16px;
  border: 1px solid rgba(107, 143, 168, 0.5);
  border-radius: 3px;
  background: linear-gradient(145deg, #6b8fa8 0%, #5a7d94 100%);
  color: #fff;
  font-size: 0.82rem;
  font-weight: 700;
  cursor: pointer;
  transition: background 150ms ease, transform 100ms ease;
}

.hint-modal-deep-btn:hover:not(:disabled) {
  background: linear-gradient(145deg, #7a9eb7 0%, #6b8fa8 100%);
  transform: translateY(-1px);
}

.hint-modal-deep-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.hint-modal-footer-note {
  display: block;
  margin-top: 6px;
  font-size: 0.7rem;
  color: #8a7558;
}
</style>
