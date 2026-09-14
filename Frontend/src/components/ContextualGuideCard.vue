<script setup lang="ts">
/**
 * 上下文引导卡片（毕业后专用）
 *
 * 右上角的非强制提示卡，内容由 currentContext 实时推导。
 * 玩家可以关闭当前提示，之后仍可通过地图页的「旅行指南」按钮手动重开。
 *
 * 首次教学期（tutorialSeen === false）由 TutorialSpotlight 独占，本卡片不出现。
 */
import type { TutorialGuide } from '../game/tutorial/useTutorial'

defineProps<{
  guide: TutorialGuide | null
  visible: boolean
  persistent: boolean
}>()

const emit = defineEmits<{
  dismiss: []
}>()
</script>

<template>
  <aside
    v-if="visible && guide"
    class="contextual-guide"
    role="dialog"
    aria-label="旅行指南"
    aria-live="polite"
  >
    <div class="contextual-guide__header">
      <div class="contextual-guide__speaker">{{ guide.speaker }}</div>
      <button
        class="contextual-guide__close"
        type="button"
        aria-label="关闭当前引导"
        title="关闭当前引导"
        @click="emit('dismiss')"
      >
        ×
      </button>
    </div>
    <p class="contextual-guide__text">{{ guide.text }}</p>
    <p class="contextual-guide__suggestion">{{ guide.suggestion }}</p>
    <div v-if="!persistent" class="contextual-guide__actions">
      <button type="button" @click="emit('dismiss')">知道了</button>
    </div>
  </aside>
</template>

<style scoped>
.contextual-guide {
  position: fixed;
  z-index: 105;
  top: 94px;
  right: 18px;
  width: min(306px, calc(100vw - 36px));
  box-sizing: border-box;
  border: 1px solid rgba(188, 157, 111, 0.62);
  border-radius: 6px;
  padding: 15px 16px 12px;
  background:
    linear-gradient(rgba(121, 89, 57, 0.045) 1px, transparent 1px) 0 0 / 14px 14px,
    #f7efd9;
  box-shadow: 3px 4px 0 rgba(106, 77, 43, 0.12), 0 12px 28px rgba(82, 62, 39, 0.16), inset 0 0 0 1px rgba(255, 255, 255, 0.46);
  color: #4b3324;
}

.contextual-guide__header,
.contextual-guide__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.contextual-guide__speaker {
  color: #5f866d;
  font-size: 0.72rem;
  font-weight: 900;
  letter-spacing: 0.1em;
}

.contextual-guide__close {
  display: grid;
  width: 25px;
  height: 25px;
  place-items: center;
  border: 1px solid rgba(107, 62, 43, 0.34);
  border-radius: 3px;
  background: rgba(255, 250, 240, 0.65);
  color: #6b3e2b;
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
}

.contextual-guide__text {
  margin: 13px 0 8px;
  color: #442c1c;
  font-size: 0.92rem;
  font-weight: 700;
  line-height: 1.65;
}

.contextual-guide__suggestion {
  margin: 0;
  color: #6d886e;
  font-size: 0.7rem;
  font-weight: 900;
  letter-spacing: 0.04em;
}

.contextual-guide__actions {
  justify-content: flex-start;
  margin-top: 13px;
  border-top: 1px dashed rgba(107, 62, 43, 0.28);
  padding-top: 11px;
}

.contextual-guide__actions button {
  border: 1px solid #6f9279;
  border-radius: 7px 3px 7px 3px;
  padding: 7px 10px;
  background: #fffaf0;
  color: #4f705b;
  font-size: 0.68rem;
  font-weight: 800;
  cursor: pointer;
}

.contextual-guide__actions button:hover,
.contextual-guide__close:hover {
  filter: brightness(1.02);
  background: #fffdf5;
}

@media (max-width: 720px) {
  .contextual-guide {
    top: 82px;
    right: 10px;
    width: min(306px, calc(100vw - 20px));
  }
}
</style>
