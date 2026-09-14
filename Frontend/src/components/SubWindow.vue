<script setup lang="ts">
/**
 * 通用子窗口容器 — 地图上的弹出式子窗口
 * 用于阅读页、背包页、看山对话等功能的占位容器
 */
defineProps<{
  title: string
  icon: string
  visible: boolean
  wide?: boolean
  theme?: 'kanshan' | 'workspace' | 'article-backpack'
  panelStyle?: Record<string, string>
}>()

const emit = defineEmits<{
  close: []
}>()
</script>

<template>
  <Teleport to="body">
    <Transition name="sub-window">
      <div v-if="visible" class="sub-window-overlay" @click.self="emit('close')">
        <div
          class="sub-window-panel"
          :class="{
            'sub-window-panel--wide': wide,
            'sub-window-panel--kanshan': theme === 'kanshan',
            'sub-window-panel--workspace': theme === 'workspace',
            'sub-window-panel--article-backpack': theme === 'article-backpack',
          }"
          :style="panelStyle"
          role="dialog"
          aria-modal="true"
          :aria-label="title"
        >
          <!-- 标题栏 -->
          <div class="sub-window-header">
            <span class="sub-window-icon">{{ icon }}</span>
            <h3 class="sub-window-title">{{ title }}</h3>
            <div v-if="$slots['header-actions']" class="sub-window-header-actions">
              <slot name="header-actions" />
            </div>
            <button class="sub-window-close" @click="emit('close')" title="关闭">
              ✕
            </button>
          </div>
          <!-- 内容区 -->
          <div class="sub-window-content">
            <slot>
              <p class="sub-window-placeholder">功能开发中…</p>
            </slot>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.sub-window-overlay {
  position: fixed;
  inset: 0;
  z-index: 90;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(3px);
}

.sub-window-panel {
  background: linear-gradient(145deg, #2a2a2e, #1e1e22);
  border: 2px solid #444;
  border-radius: 12px;
  width: 90%;
  max-width: 640px;
  max-height: 80vh;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.sub-window-panel--wide {
  max-width: 1040px;
  max-height: 88vh;
}

.sub-window-panel--workspace {
  width: min(1180px, calc(100vw - 24px));
  height: min(696px, calc(100vh - 24px));
  max-width: none;
  max-height: none;
  border: 1px solid #aab7c4;
  border-radius: 8px;
  background: #f3f0eb;
  box-shadow: 0 12px 30px rgba(60, 55, 50, 0.24);
}

.sub-window-panel--workspace .sub-window-header {
  flex: 0 0 46px;
  height: 46px;
  border-top: 6px solid #aab7c4;
  border-bottom: 1px solid #bcb2a6;
  padding: 0 12px;
  background: linear-gradient(180deg, #e2d9cf, #d8cec2);
}

.sub-window-panel--workspace .sub-window-title {
  color: #594f44;
  font-family: "Noto Sans SC", "Microsoft YaHei", sans-serif;
  font-size: 15px;
  font-weight: 600;
}

.sub-window-panel--workspace .sub-window-close {
  width: 24px;
  height: 24px;
  border: 1px solid #bcb2a6;
  border-radius: 4px;
  background: #ece4da;
  color: #6b6054;
  font-size: 14px;
}

.sub-window-panel--workspace .sub-window-content {
  min-height: 0;
  padding: 12px 14px 14px;
  overflow: hidden;
  background: #f3f0eb;
}

.sub-window-panel--article-backpack {
  width: min(760px, calc(100vw - 40px));
  max-width: none;
  max-height: min(620px, calc(100vh - 40px));
  border: 1px solid #b99a73;
  border-radius: 10px;
  background: #f3f0eb;
  box-shadow: 0 14px 34px rgba(82, 62, 39, 0.22), 3px 4px 0 rgba(82, 70, 58, 0.12);
}

.sub-window-panel--article-backpack .sub-window-header {
  flex: 0 0 46px;
  height: 46px;
  border-top: 5px solid #b99a73;
  border-bottom: 1px solid #bcb2a6;
  padding: 0 14px;
  background: linear-gradient(180deg, #eadfc8, #dfd0b7);
}

.sub-window-panel--article-backpack .sub-window-title {
  color: #5a4733;
  font-family: "Noto Sans SC", "Microsoft YaHei", sans-serif;
  font-size: 15px;
  font-weight: 600;
}

.sub-window-panel--article-backpack .sub-window-close {
  width: 26px;
  height: 26px;
  border: 1px solid #bea583;
  border-radius: 5px;
  background: #f1e7d4;
  color: #6b5540;
  font-size: 14px;
}

.sub-window-panel--article-backpack .sub-window-content {
  min-height: 0;
  padding: 12px 14px 14px;
  overflow: hidden;
  background: #f5eddd;
}

.sub-window-panel--kanshan {
  width: min(92%, 720px);
  min-height: min(520px, 82vh);
  overflow: visible;
  border: 8px solid #6b3e2b;
  border-radius: 16px;
  background: #f8efd8;
  box-shadow:
    0 18px 58px rgba(0, 0, 0, 0.58),
    inset 0 0 0 2px rgba(255, 251, 220, 0.82),
    inset 0 -7px 0 rgba(98, 55, 37, 0.13);
}

.sub-window-panel--kanshan .sub-window-header {
  border-bottom: 2px solid rgba(107, 62, 43, 0.45);
  background: rgba(237, 219, 178, 0.94);
}

.sub-window-panel--kanshan .sub-window-title {
  color: #4c3022;
}

.sub-window-panel--kanshan .sub-window-close {
  border: 1px solid rgba(107, 62, 43, 0.35);
  background: rgba(255, 249, 220, 0.7);
  color: #6b3e2b;
}

.sub-window-panel--kanshan .sub-window-content {
  min-height: 0;
  padding: 0;
  overflow: hidden;
}

.sub-window-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  background: rgba(255, 255, 255, 0.06);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.sub-window-icon {
  font-size: 22px;
}

.sub-window-title {
  flex: 1;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 16px;
  font-weight: 700;
  color: #e0e0e0;
  margin: 0;
  letter-spacing: 0.04em;
}

.sub-window-close {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.08);
  color: #aaa;
  font-size: 16px;
  cursor: pointer;
  transition: background 150ms, color 150ms;
}
.sub-window-close:hover {
  background: rgba(255, 80, 80, 0.2);
  color: #ff6b6b;
}

.sub-window-content {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
  min-height: 200px;
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
}

.sub-window-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sub-window-placeholder {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 14px;
  color: #888;
  letter-spacing: 0.06em;
}

/* 过渡动画 */
.sub-window-enter-active,
.sub-window-leave-active {
  transition: opacity 200ms ease, transform 200ms ease;
}
.sub-window-enter-from {
  opacity: 0;
  transform: scale(0.92) translateY(12px);
}
.sub-window-leave-to {
  opacity: 0;
  transform: scale(0.92) translateY(12px);
}
</style>
