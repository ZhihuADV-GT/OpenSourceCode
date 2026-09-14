<script setup lang="ts">
/**
 * 旅行笔记弹窗 — 每局开始时弹出
 * 点击"继续旅行"后进入游戏页面
 */
const props = defineProps<{
  visible: boolean
  round: number
  totalRounds: number
}>()

const emit = defineEmits<{
  continue: []
  skip: []
}>()
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="visible" class="travel-note-overlay" @click.self="emit('continue')">
        <div class="travel-note-modal">
          <div class="travel-note-icon">📜</div>
          <h2 class="travel-note-title">看山获得了旅行笔记</h2>
          <p class="travel-note-round">
            第 {{ round }} / {{ totalRounds }} 局
          </p>
          <p class="travel-note-desc">
            新的旅程即将开始，准备好你的卡牌了吗？
          </p>
          <button class="travel-note-btn" @click="emit('continue')">
            继续旅行 →
          </button>
          <button class="travel-note-skip-btn" @click="emit('skip')">
            返回地图
          </button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.travel-note-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(4px);
}

.travel-note-modal {
  background: linear-gradient(145deg, #fdf6e3, #f5e6c8);
  border: 3px solid #8b7355;
  border-radius: 16px;
  padding: 40px 48px;
  text-align: center;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.5);
  max-width: 420px;
  width: 90%;
}

.travel-note-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.travel-note-title {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 22px;
  font-weight: 800;
  color: #3d2b1f;
  margin: 0 0 8px;
  letter-spacing: 0.04em;
}

.travel-note-round {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 13px;
  color: #8b7355;
  margin: 0 0 16px;
  font-weight: 600;
}

.travel-note-desc {
  font-size: 14px;
  color: #6b5b4f;
  margin: 0 0 28px;
  line-height: 1.6;
}

.travel-note-btn {
  padding: 12px 36px;
  border: 2px solid #8b7355;
  border-radius: 8px;
  background: #3d2b1f;
  color: #fdf6e3;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.06em;
  cursor: pointer;
  transition: background 150ms, transform 90ms;
}
.travel-note-btn:hover {
  background: #5a3e2b;
  transform: translateY(-1px);
}
.travel-note-btn:active {
  transform: translateY(1px);
}

.travel-note-skip-btn {
  display: block;
  margin: 12px auto 0;
  padding: 8px 24px;
  border: 1px solid rgba(139, 115, 85, 0.4);
  border-radius: 6px;
  background: transparent;
  color: #8b7355;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: background 150ms, color 150ms;
}
.travel-note-skip-btn:hover {
  background: rgba(139, 115, 85, 0.1);
  color: #5a3e2b;
}

/* 过渡动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 250ms ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
