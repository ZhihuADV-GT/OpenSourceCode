<script setup lang="ts">
import { ref, watch } from 'vue'
import type { CompositionHintItem } from '../types/compositionHint'

const props = defineProps<{
  visible: boolean
  message: string
  items: CompositionHintItem[]
  loading?: boolean
  analysis?: string
}>()

const emit = defineEmits<{
  close: []
  'deep-analysis': []
}>()

const selectedItem = ref<CompositionHintItem | null>(null)

function selectItem(item: CompositionHintItem) {
  selectedItem.value = item
}

function getTypeLabel(type: CompositionHintItem['type']) {
  const labels: Record<CompositionHintItem['type'], string> = {
    recipe: '阵型',
    adjacency: '相邻',
    risk: '风险',
    collection: '收集',
    compass: '罗盘',
  }
  return labels[type]
}

function handleDeepAnalysis() {
  emit('deep-analysis')
}

watch(() => props.visible, visible => {
  if (!visible) selectedItem.value = null
})
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="composition-hint-backdrop" @click="emit('close')">
      <div class="composition-hint-root" @click.stop>
        <header class="composition-hint-header">
          <span class="composition-hint-icon">💡</span>
          <h3>看山的合成建议</h3>
          <button class="composition-hint-close" type="button" aria-label="关闭合成建议" @click="emit('close')">✕</button>
        </header>

        <div class="composition-hint-message">
          <p>{{ message }}</p>
        </div>

        <div class="composition-hint-list">
          <article
            v-for="(item, index) in items"
            :key="`${item.type}-${item.title}`"
            class="composition-hint-item"
            :class="{ 'composition-hint-item--selected': selectedItem === item }"
            @click="selectItem(item)"
          >
            <div class="composition-hint-item-header">
              <span class="composition-hint-item-index">{{ index + 1 }}</span>
              <span class="composition-hint-item-type" :data-type="item.type">{{ getTypeLabel(item.type) }}</span>
              <strong>{{ item.title }}</strong>
            </div>
            <p class="composition-hint-item-reason">{{ item.reason }}</p>
            <div class="composition-hint-action">
              <span>建议操作</span>
              <p>{{ item.action }}</p>
            </div>
          </article>
        </div>

        <div v-if="analysis" class="composition-hint-analysis">
          <h4>看山的深度分析</h4>
          <p>{{ analysis }}</p>
        </div>

        <footer class="composition-hint-footer">
          <button
            class="composition-hint-deep-btn"
            type="button"
            :disabled="loading"
            @click="handleDeepAnalysis"
          >
            {{ loading ? '分析中…' : '深度分析（AI）' }}
          </button>
          <small>建议基于当前背包、创作流卡槽和玩家版配方书生成。</small>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.composition-hint-backdrop {
  position: fixed;
  inset: 0;
  z-index: 120;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.52);
  backdrop-filter: blur(2px);
}

.composition-hint-root {
  width: min(460px, 90vw);
  max-height: 82vh;
  overflow: auto;
  border: 2px solid rgba(157, 124, 77, 0.68);
  border-radius: 4px;
  background: linear-gradient(145deg, #f8efd8 0%, #f3e8bd 100%);
  box-shadow: 4px 6px 0 rgba(92, 66, 35, 0.25);
  color: #4f3b24;
  font-family: 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
}

.composition-hint-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(157, 124, 77, 0.3);
  background: rgba(248, 239, 216, 0.96);
}

.composition-hint-icon { font-size: 1.2rem; }

.composition-hint-header h3 {
  flex: 1;
  margin: 0;
  color: #6c5435;
  font-size: 0.95rem;
  font-weight: 800;
}

.composition-hint-close {
  width: 28px;
  height: 28px;
  border: 1px solid rgba(157, 124, 77, 0.4);
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.6);
  color: #6c5435;
  cursor: pointer;
}

.composition-hint-close:hover { background: rgba(255, 255, 255, 0.9); }

.composition-hint-message {
  padding: 12px 16px;
  border-bottom: 1px dashed rgba(157, 124, 77, 0.3);
  background: rgba(243, 232, 189, 0.5);
}

.composition-hint-message p {
  margin: 0;
  color: #5a4428;
  font-size: 0.85rem;
  font-weight: 700;
  line-height: 1.6;
}

.composition-hint-list {
  display: grid;
  gap: 10px;
  padding: 12px 16px;
}

.composition-hint-item {
  border: 1px solid rgba(157, 124, 77, 0.3);
  border-radius: 3px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.4);
  cursor: pointer;
  transition: border-color 150ms ease, background 150ms ease;
}

.composition-hint-item:hover {
  border-color: rgba(157, 124, 77, 0.52);
  background: rgba(255, 255, 255, 0.62);
}

.composition-hint-item--selected {
  border-color: #9d7c4d;
  background: rgba(248, 239, 216, 0.84);
  box-shadow: inset 0 0 0 1px rgba(157, 124, 77, 0.28);
}

.composition-hint-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 7px;
}

.composition-hint-item-header strong {
  min-width: 0;
  color: #49361f;
  font-size: 0.84rem;
  line-height: 1.3;
}

.composition-hint-item-index {
  display: grid;
  width: 20px;
  height: 20px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 50%;
  background: #9d7c4d;
  color: #fff;
  font-size: 0.75rem;
  font-weight: 800;
}

.composition-hint-item-type {
  flex: 0 0 auto;
  border-radius: 2px;
  padding: 2px 8px;
  color: #fff;
  font-size: 0.72rem;
  font-weight: 800;
}

.composition-hint-item-type[data-type="recipe"] { background: #5b8c6f; }
.composition-hint-item-type[data-type="adjacency"] { background: #6b8fa8; }
.composition-hint-item-type[data-type="risk"] { background: #9a6a58; }
.composition-hint-item-type[data-type="collection"] { background: #8b6b9e; }
.composition-hint-item-type[data-type="compass"] { background: #c77d5a; }

.composition-hint-item-reason {
  margin: 0 0 9px;
  color: #5b4930;
  font-size: 0.78rem;
  font-weight: 650;
  line-height: 1.55;
}

.composition-hint-action {
  border: 1px solid rgba(107, 143, 168, 0.34);
  border-radius: 3px;
  padding: 8px 10px;
  background: rgba(107, 143, 168, 0.08);
}

.composition-hint-action span {
  display: block;
  margin-bottom: 4px;
  color: #4a6b80;
  font-size: 0.68rem;
  font-weight: 800;
}

.composition-hint-action p {
  margin: 0;
  color: #4a5a68;
  font-size: 0.76rem;
  line-height: 1.55;
}

.composition-hint-footer {
  padding: 11px 16px 12px;
  border-top: 1px solid rgba(157, 124, 77, 0.3);
  background: rgba(243, 232, 189, 0.5);
  text-align: center;
}

.composition-hint-analysis {
  margin: 0 16px 12px;
  border: 1px solid rgba(107, 143, 168, 0.4);
  border-radius: 3px;
  padding: 10px 12px;
  background: rgba(107, 143, 168, 0.08);
}

.composition-hint-analysis h4 {
  margin: 0 0 6px;
  color: #4a6b80;
  font-size: 0.8rem;
  font-weight: 800;
}

.composition-hint-analysis p {
  margin: 0;
  color: #4a5a68;
  font-size: 0.8rem;
  line-height: 1.7;
  white-space: pre-wrap;
}

.composition-hint-deep-btn {
  width: 100%;
  margin-bottom: 7px;
  border: 1px solid rgba(107, 143, 168, 0.5);
  border-radius: 3px;
  padding: 8px 16px;
  background: linear-gradient(145deg, #6b8fa8 0%, #5a7d94 100%);
  color: #fff;
  font-size: 0.82rem;
  font-weight: 800;
  cursor: pointer;
  transition: background 150ms ease, transform 100ms ease;
}

.composition-hint-deep-btn:hover:not(:disabled) {
  background: linear-gradient(145deg, #7a9eb7 0%, #6b8fa8 100%);
  transform: translateY(-1px);
}

.composition-hint-deep-btn:disabled {
  opacity: 0.62;
  cursor: not-allowed;
}

.composition-hint-footer small {
  display: block;
  color: #8a7558;
  font-size: 0.7rem;
}
</style>
