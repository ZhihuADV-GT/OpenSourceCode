<script setup lang="ts">
import type { AchievementDefinition, AchievementState } from '../../types/achievement'
import { achievementIconFor } from '../../data/achievementIcons'

const props = defineProps<{
  definition: AchievementDefinition
  state: AchievementState
  progressLabel: string
  category: string
  categoryMark: string
  newlyUnlocked: boolean
  progressPercent: number | null
}>()

const emit = defineEmits<{
  select: [definition: AchievementDefinition]
}>()

function handleSelect() {
  if (props.state.status !== 'HIDDEN') emit('select', props.definition)
}

function stateLabel(status: AchievementState['status']) {
  switch (status) {
    case 'UNLOCKED': return '已解锁'
    case 'IN_PROGRESS': return '进行中'
    case 'LOCKED': return '未解锁'
    case 'HIDDEN': return '???'
  }
}
</script>

<template>
  <button
    class="achievement-tree-node"
    :class="[
      `achievement-tree-node--${state.status.toLowerCase()}`,
      `achievement-tree-node--${category}`,
      { 'achievement-tree-node--newly-unlocked': newlyUnlocked },
    ]"
    :data-achievement-id="definition.id"
    type="button"
    :disabled="state.status === 'HIDDEN'"
    :aria-label="state.status === 'HIDDEN' ? '隐藏成就' : `${definition.name}，${stateLabel(state.status)}`"
    @click="handleSelect"
  >
    <span class="achievement-tree-node__badge" aria-hidden="true">
      <img
        v-if="achievementIconFor(definition.id, state.status)"
        :src="achievementIconFor(definition.id, state.status) ?? undefined"
        alt=""
        class="achievement-tree-node__badge-image"
      />
      <span v-else>{{ state.status === 'UNLOCKED' ? '✓' : categoryMark }}</span>
    </span>
    <span class="achievement-tree-node__copy">
      <strong>{{ state.status === 'HIDDEN' ? '???' : definition.name }}</strong>
      <small>{{ stateLabel(state.status) }}</small>
      <em v-if="progressLabel">{{ progressLabel }}</em>
    </span>
    <span v-if="newlyUnlocked && state.status === 'UNLOCKED'" class="achievement-tree-node__new-tag">新见闻</span>
    <span
      v-if="progressPercent !== null && state.status !== 'HIDDEN'"
      class="achievement-tree-node__progress"
      aria-hidden="true"
    >
      <span :style="{ width: `${progressPercent}%` }" />
    </span>
  </button>
</template>

<style scoped>
.achievement-tree-node { position: absolute; z-index: 1; display: grid; grid-template-columns: 60px minmax(0, 1fr); align-items: center; gap: 10px; width: 188px; min-height: 84px; padding: 9px 10px 12px; overflow: hidden; transform: translate(-50%, -50%); color: #59432a; text-align: left; background: rgba(249, 238, 201, 0.96); border: 1px solid rgba(142, 105, 57, 0.52); border-radius: 9px 4px 9px 4px; box-shadow: 3px 4px 0 rgba(94, 65, 29, 0.14), inset 0 0 0 1px rgba(255, 255, 255, 0.52); cursor: pointer; transition: transform 140ms ease, filter 140ms ease, border-color 140ms ease, box-shadow 180ms ease; }
.achievement-tree-node:hover:not(:disabled), .achievement-tree-node:focus-visible:not(:disabled) { transform: translate(-50%, -50%) translateY(-3px); filter: brightness(1.04); border-color: #ad7e3f; outline: none; }
.achievement-tree-node__badge { display: grid; place-items: center; width: 60px; height: 60px; color: #8b6a3f; font-family: 'Noto Serif SC', 'Songti SC', serif; font-size: 0.95rem; background: transparent; border: 0; border-radius: 0; box-shadow: none; }
.achievement-tree-node__badge-image { display: block; width: 60px; height: 60px; object-fit: contain; pointer-events: none; }
.achievement-tree-node__copy { display: grid; min-width: 0; gap: 2px; }
.achievement-tree-node strong { overflow: hidden; color: #543c20; font-size: 0.92rem; text-overflow: ellipsis; white-space: nowrap; }
.achievement-tree-node small { color: #8d704b; font-size: 0.68rem; }
.achievement-tree-node em { color: #795d38; font-size: 0.69rem; font-style: normal; }
.achievement-tree-node--journey .achievement-tree-node__badge { color: #7b6a3e; }
.achievement-tree-node--rhetoric .achievement-tree-node__badge { color: #8d7145; }
.achievement-tree-node--emotion .achievement-tree-node__badge { color: #966d4e; }
.achievement-tree-node--viewpoint .achievement-tree-node__badge { color: #5a7d72; }
.achievement-tree-node--loophole .achievement-tree-node__badge { color: #70715b; }
.achievement-tree-node--product .achievement-tree-node__badge { color: #8f7550; }
.achievement-tree-node--unlocked { background: linear-gradient(135deg, rgba(255, 249, 217, 0.99), rgba(235, 226, 181, 0.98)); border-color: #ae8a50; box-shadow: 3px 4px 0 rgba(94, 65, 29, 0.16), inset 0 0 0 1px rgba(255, 255, 255, 0.62); }
.achievement-tree-node--unlocked .achievement-tree-node__badge { color: #6d744f; background: transparent; box-shadow: none; }
.achievement-tree-node--in_progress { background: rgba(249, 239, 207, 0.98); border-color: rgba(169, 132, 73, 0.82); }
.achievement-tree-node--locked { filter: saturate(0.45); opacity: 0.72; }
.achievement-tree-node--hidden { opacity: 0.72; background: rgba(224, 211, 174, 0.62); border-style: dashed; cursor: default; }
.achievement-tree-node--hidden .achievement-tree-node__badge { color: #98815e; background: transparent; box-shadow: none; }
.achievement-tree-node__new-tag { position: absolute; top: 5px; right: 6px; padding: 1px 4px; color: #786137; font: 800 0.52rem ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: 0.04em; background: rgba(232, 202, 115, 0.72); border: 1px solid rgba(145, 108, 55, 0.34); border-radius: 3px; }
.achievement-tree-node__progress { position: absolute; right: 10px; bottom: 5px; left: 10px; height: 3px; overflow: hidden; background: rgba(132, 106, 68, 0.14); border-radius: 4px; }
.achievement-tree-node__progress span { display: block; height: 100%; background: linear-gradient(90deg, #b2854c, #779371); border-radius: inherit; }
.achievement-tree-node--newly-unlocked { animation: achievement-node-stamp 680ms cubic-bezier(0.2, 0.85, 0.35, 1.1) both; }
.achievement-tree-node--newly-unlocked .achievement-tree-node__badge { animation: achievement-badge-stamp 680ms cubic-bezier(0.2, 0.85, 0.35, 1.1) both; }
@keyframes achievement-node-stamp {
  0% { opacity: 0; transform: translate(-50%, -50%) scale(0.88) rotate(-1deg); }
  58% { opacity: 1; transform: translate(-50%, -50%) scale(1.025) rotate(0.5deg); }
  100% { opacity: 1; transform: translate(-50%, -50%) scale(1) rotate(0); }
}
@keyframes achievement-badge-stamp {
  0% { transform: scale(0.72) rotate(-12deg); }
  60% { transform: scale(1.08) rotate(3deg); }
  100% { transform: scale(1) rotate(0); }
}
@media (max-width: 700px) {
  .achievement-tree-node { grid-template-columns: 54px minmax(0, 1fr); width: 176px; min-height: 80px; gap: 8px; }
  .achievement-tree-node__badge, .achievement-tree-node__badge-image { width: 54px; height: 54px; }
}
</style>
