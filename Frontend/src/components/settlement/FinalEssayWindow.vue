<script setup lang="ts">
import { computed, watch } from 'vue'
import { useWriteEssay } from '../../game/write/useWriteEssay'
import type { FinalJourneySummary } from '../../game/write/types'

const props = defineProps<{
  visible: boolean
  summary: FinalJourneySummary
}>()

const emit = defineEmits<{
  close: []
}>()

const writeEssay = useWriteEssay()

const preferredMaterialLabel = computed(() => {
  if (props.summary.preferredMaterial.kind === 'none') return '暂无单一偏好'
  if (props.summary.preferredMaterial.kind === 'tie') {
    return props.summary.preferredMaterial.labels.join(' / ') + '并列'
  }
  return props.summary.preferredMaterial.labels[0] ?? '暂无'
})

watch(
  [() => props.visible, () => props.summary.runId],
  ([visible]) => {
    if (visible) void writeEssay.ensureWriting(props.summary)
  },
  { immediate: true },
)

function retryGeneration() {
  void writeEssay.startWriting({ summary: props.summary }, true)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="final-essay-overlay" @click.self="emit('close')">
      <article class="final-essay-window" aria-labelledby="final-essay-title">
        <button class="final-essay-close" type="button" aria-label="关闭最终回答" @click="emit('close')">×</button>

        <header class="final-essay-header">
          <p class="final-essay-eyebrow">TRAVEL ANSWER · FINAL NOTE</p>
          <h1 id="final-essay-title">看山与你共同写下的回答</h1>
          <p>一段旅程，最终落成了一篇回答。</p>
        </header>

        <div v-if="writeEssay.isGenerating" class="final-essay-loading" aria-live="polite">
          <span class="final-essay-loading-mark" aria-hidden="true">✦</span>
          <strong>看山正在整理这一路的见闻……</strong>
          <span>请让记忆在纸面上慢慢归位。</span>
        </div>

        <template v-else>
          <section class="final-essay-paper" aria-label="最终旅程回答">
            <div class="final-essay-paper-rule" aria-hidden="true" />
            <h2>{{ writeEssay.title || '这一程的回答' }}</h2>
            <p class="final-essay-content">{{ writeEssay.displayedText }}</p>
            <button
              v-if="writeEssay.isWriting"
              class="final-essay-read-all"
              type="button"
              @click="writeEssay.skipWriting"
            >
              查看全文
            </button>
          </section>

          <div v-if="writeEssay.generationError" class="final-essay-error" role="status">
            <p>{{ writeEssay.generationError }}</p>
            <button type="button" @click="retryGeneration">再试一次</button>
          </div>
        </template>

        <section class="final-essay-summary" aria-label="本次旅程摘要">
          <p class="final-essay-summary-title">本次旅程</p>
          <div class="final-essay-summary-grid">
            <span><small>完成</small><strong>{{ summary.roundsCompleted }} 局旅程</strong></span>
            <span><small>使用最多</small><strong>{{ preferredMaterialLabel }}</strong></span>
            <span><small>与看山交流</small><strong>{{ summary.kanshanInteractions }} 次</strong></span>
            <span><small>成就</small><strong>{{ summary.unlockedAchievements.length }} / {{ summary.achievementTotal }}</strong></span>
          </div>
          <p class="final-essay-region">最后抵达 · {{ summary.finalRegion }}</p>
        </section>

        <footer class="final-essay-actions">
          <button type="button" class="final-essay-secondary-action" @click="emit('close')">再次查看旅程</button>
          <button type="button" class="final-essay-primary-action" @click="emit('close')">完成</button>
        </footer>
      </article>
    </div>
  </Teleport>
</template>

<style scoped>
.final-essay-overlay {
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
.final-essay-window {
  position: relative;
  width: min(720px, calc(100vw - 32px));
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
.final-essay-close {
  position: absolute;
  top: 11px;
  right: 14px;
  width: 30px;
  height: 30px;
  border: 1px solid #b09a83;
  border-radius: 50%;
  background: rgba(255, 252, 239, 0.74);
  color: #786552;
  font-size: 1.35rem;
  line-height: 1;
  cursor: pointer;
}
.final-essay-close:hover { background: #e9dfc5; }
.final-essay-header { text-align: center; }
.final-essay-eyebrow {
  margin: 0 0 8px;
  color: #648692;
  font: 800 0.62rem ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.14em;
}
.final-essay-header h1 {
  margin: 0;
  color: #4d3d32;
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: clamp(1.25rem, 3vw, 1.75rem);
  letter-spacing: 0.08em;
}
.final-essay-header p:last-child { margin: 9px 0 0; color: #8c7867; font-size: 0.78rem; }
.final-essay-loading {
  display: grid;
  justify-items: center;
  gap: 9px;
  min-height: 245px;
  align-content: center;
  margin-top: 24px;
  border: 1px dashed #b7a58c;
  background: rgba(255, 252, 239, 0.62);
  color: #756554;
}
.final-essay-loading-mark { color: #648e9a; font-size: 1.5rem; animation: essay-mark-breathe 1.3s ease-in-out infinite; }
.final-essay-loading strong { font-family: 'Noto Serif SC', 'Songti SC', serif; font-size: 0.95rem; }
.final-essay-loading span:last-child { color: #a18d7a; font-size: 0.7rem; }
.final-essay-paper {
  position: relative;
  min-height: 245px;
  margin-top: 24px;
  border: 1px solid #d0bea0;
  border-radius: 3px;
  padding: 22px 22px 18px;
  background: rgba(255, 253, 244, 0.72);
  box-shadow: inset 0 0 0 3px rgba(232, 220, 193, 0.42);
}
.final-essay-paper-rule { width: 44px; height: 3px; margin-bottom: 13px; background: #6f99a3; }
.final-essay-paper h2 { margin: 0 0 14px; color: #5d4939; font: 800 1rem/1.3 'Noto Serif SC', 'Songti SC', serif; }
.final-essay-content { margin: 0; color: #594c43; font: 0.9rem/2 'Noto Serif SC', 'Songti SC', serif; white-space: pre-line; }
.final-essay-read-all { margin-top: 12px; border: 0; background: transparent; color: #648692; font-size: 0.7rem; cursor: pointer; }
.final-essay-error { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 10px; padding: 9px 11px; border-left: 3px solid #b17a61; background: rgba(239, 219, 201, 0.56); color: #795848; font-size: 0.71rem; }
.final-essay-error p { margin: 0; line-height: 1.5; }
.final-essay-error button { flex: 0 0 auto; border: 1px solid #9c725f; border-radius: 4px; padding: 5px 9px; background: #fff8e9; color: #795848; cursor: pointer; }
.final-essay-summary { margin-top: 22px; }
.final-essay-summary-title { margin: 0 0 8px; color: #6b8490; font: 800 0.66rem ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: 0.12em; }
.final-essay-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.final-essay-summary-grid span { display: grid; gap: 4px; border-top: 1px solid #cbb99d; padding-top: 8px; }
.final-essay-summary-grid small { color: #9a8775; font-size: 0.62rem; }
.final-essay-summary-grid strong { color: #5d4e42; font: 700 0.75rem 'Noto Serif SC', 'Songti SC', serif; }
.final-essay-region { margin: 10px 0 0; color: #8d7967; font-size: 0.68rem; }
.final-essay-actions { display: flex; justify-content: flex-end; gap: 9px; margin-top: 22px; }
.final-essay-actions button { border-radius: 4px; padding: 9px 15px; font-size: 0.72rem; font-weight: 800; cursor: pointer; }
.final-essay-secondary-action { border: 1px solid #a99a87; background: transparent; color: #786756; }
.final-essay-primary-action { border: 1px solid #577f8b; background: #668f9a; color: #fffdf1; box-shadow: 2px 2px 0 rgba(68, 93, 100, 0.24); }
@keyframes essay-mark-breathe { 0%, 100% { opacity: 0.45; transform: scale(0.86); } 50% { opacity: 1; transform: scale(1.12); } }
@media (max-width: 620px) {
  .final-essay-overlay { padding: 12px; }
  .final-essay-window { max-height: calc(100vh - 24px); padding: 27px 16px 18px; }
  .final-essay-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .final-essay-content { font-size: 0.83rem; line-height: 1.85; }
}
</style>
