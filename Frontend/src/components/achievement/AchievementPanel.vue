<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
// [art-assets disabled]
const achievementBgm = ''
const mapBgm = ''
import AchievementTreeNode from './AchievementTreeNode.vue'
import { ACHIEVEMENT_DEFINITIONS } from '../../data/achievementDefinitions'
import { useAchievementStore as getAchievementStore } from '../../stores/achievements'
import type { AchievementDefinition, AchievementState } from '../../types/achievement'
import { achievementIconFor } from '../../data/achievementIcons'
import { AUDIO_VOLUME, playBgm, stopBgm } from '../../services/audioManager'

const props = defineProps<{
  newlyViewedIds?: string[]
}>()

const achievementStore = getAchievementStore()
const selectedId = ref<string | null>(null)

const nodeLayout: Record<string, { x: number; y: number }> = {
  FIRST_PATH: { x: 500, y: 38 },
  YELLOW_V: { x: 500, y: 125 },
  RHETORIC_BASIC: { x: 125, y: 220 },
  EMOTION_BASIC: { x: 375, y: 220 },
  VIEWPOINT_BASIC: { x: 625, y: 220 },
  LOOPHOLE_BASIC: { x: 875, y: 220 },
  RHETORIC_ADVANCED: { x: 125, y: 365 },
  HEAT_BASIC: { x: 500, y: 365 },
  SALT_BASIC: { x: 750, y: 365 },
  HEAT_ADVANCED: { x: 500, y: 475 },
  SALT_ADVANCED: { x: 750, y: 475 },
  FINAL_ACHIEVEMENT: { x: 250, y: 475 },
}

const obtainableDefinitions = computed(() => (
  ACHIEVEMENT_DEFINITIONS.filter(definition => !definition.hidden)
))
const unlockedCount = computed(() => obtainableDefinitions.value.filter(definition => (
  achievementStore.getAchievementState(definition.id)?.status === 'UNLOCKED'
)).length)
const selectedDefinition = computed(() => (
  ACHIEVEMENT_DEFINITIONS.find(definition => definition.id === selectedId.value) ?? null
))
const selectedState = computed(() => (
  selectedDefinition.value
    ? achievementStore.getAchievementState(selectedDefinition.value.id)
    : undefined
))
const edges = computed(() => ACHIEVEMENT_DEFINITIONS.flatMap(definition => (
  definition.prerequisites.flatMap(prerequisiteId => {
    const from = nodeLayout[prerequisiteId]
    const to = nodeLayout[definition.id]
    if (!from || !to) return []
    const sourceDefinition = ACHIEVEMENT_DEFINITIONS.find(item => item.id === prerequisiteId)!
    const sourceState = stateFor(sourceDefinition)
    const targetState = stateFor(definition)
    const routeState = targetState.status === 'HIDDEN' || sourceState.status === 'HIDDEN'
      ? 'hidden'
      : targetState.status === 'UNLOCKED' && sourceState.status === 'UNLOCKED'
        ? 'unlocked'
        : targetState.status === 'IN_PROGRESS' || sourceState.status === 'IN_PROGRESS'
          ? 'in-progress'
          : 'locked'
    return [{
      id: `${prerequisiteId}-${definition.id}`,
      x1: from.x,
      y1: from.y,
      x2: to.x,
      y2: to.y,
      routeState,
    }]
  })
)))

function stateFor(definition: AchievementDefinition): AchievementState {
  return achievementStore.getAchievementState(definition.id)!
}

function categoryFor(definition: AchievementDefinition) {
  if (definition.progressType === 'completed_rounds') return 'journey'
  if (definition.progressType === 'rhetoric_used') return 'rhetoric'
  if (definition.progressType === 'emotion_used') return 'emotion'
  if (definition.progressType === 'viewpoint_used') return 'viewpoint'
  if (definition.progressType === 'loophole_used') return 'loophole'
  return 'product'
}

function categoryMark(definition: AchievementDefinition) {
  switch (categoryFor(definition)) {
    case 'journey': return '行'
    case 'rhetoric': return '辞'
    case 'emotion': return '情'
    case 'viewpoint': return '观'
    case 'loophole': return '隙'
    case 'product': return '?'
  }
}

function progressPercent(definition: AchievementDefinition, state: AchievementState) {
  if (definition.progressType === 'completed_heat_threshold'
    || definition.progressType === 'completed_salt_threshold') return null
  if (state.target === null || state.progress === null) return null
  return Math.min(100, Math.max(0, (state.progress / state.target) * 100))
}

function selectNode(definition: AchievementDefinition) {
  if (definition.hidden) return
  selectedId.value = definition.id
}

function stateLabel(state: AchievementState) {
  switch (state.status) {
    case 'UNLOCKED': return '已解锁'
    case 'IN_PROGRESS': return '进行中'
    case 'LOCKED': return '未解锁'
    case 'HIDDEN': return '???'
  }
}

function progressLabel(definition: AchievementDefinition, state: AchievementState) {
  if (state.status === 'HIDDEN') return '???'
  if (definition.progressType === 'completed_heat_threshold') {
    return `热度达到 ${definition.target?.toFixed(2) ?? '目标值'}`
  }
  if (definition.progressType === 'completed_salt_threshold') {
    return `盐度达到 ${definition.target?.toFixed(2) ?? '目标值'}`
  }
  if (state.target !== null && state.progress !== null) {
    return `${Math.floor(state.progress)} / ${state.target}`
  }
  if (definition.productValue) return '条件尚未开放'
  return ''
}

function formatUnlockDate(timestamp: number | null) {
  if (timestamp === null) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(timestamp))
}

onMounted(() => {
  playBgm(achievementBgm, { loop: true, volume: AUDIO_VOLUME.achievementBgm })
})

onBeforeUnmount(() => stopBgm(achievementBgm))
onBeforeUnmount(() => playBgm(mapBgm, { loop: true, volume: AUDIO_VOLUME.mapBgm }))
</script>

<template>
  <section class="achievement-tree-panel achievement-panel" aria-label="看山的旅行见闻">
    <header class="achievement-tree-panel__header">
      <div class="achievement-tree-panel__title-group">
        <div>
          <p class="achievement-tree-panel__eyebrow">TRAVEL JOURNAL · ACHIEVEMENTS</p>
          <h2>看山的旅行见闻</h2>
          <p class="achievement-tree-panel__subtitle">旅途中获得的见闻与印记</p>
        </div>
      </div>
      <div class="achievement-tree-panel__summary" aria-label="成就完成度">
        <strong>已解锁 {{ unlockedCount }} / {{ obtainableDefinitions.length }}</strong>
        <span>旅途进度</span>
      </div>
    </header>

    <div class="achievement-tree-scroll" aria-label="成就树">
      <div class="achievement-tree-canvas">
        <svg class="achievement-tree-connectors" viewBox="0 0 1000 515" aria-hidden="true" focusable="false">
          <line
            v-for="edge in edges"
            :key="edge.id"
            :x1="edge.x1"
            :y1="edge.y1"
            :x2="edge.x2"
            :y2="edge.y2"
            :class="`achievement-tree-connector--${edge.routeState}`"
            class="achievement-tree-connector"
          />
        </svg>

        <AchievementTreeNode
          v-for="definition in ACHIEVEMENT_DEFINITIONS"
          :key="definition.id"
          :definition="definition"
          :state="stateFor(definition)"
          :progress-label="progressLabel(definition, stateFor(definition))"
          :category="categoryFor(definition)"
          :category-mark="categoryMark(definition)"
          :newly-unlocked="props.newlyViewedIds?.includes(definition.id) ?? false"
          :progress-percent="progressPercent(definition, stateFor(definition))"
          :style="{ left: `${nodeLayout[definition.id]?.x / 10}%`, top: `${nodeLayout[definition.id]?.y}px` }"
          @select="selectNode"
        />
      </div>
    </div>

    <div v-if="selectedDefinition && selectedState && selectedState.status !== 'HIDDEN'" class="achievement-tree-detail">
      <div class="achievement-tree-detail__title">
        <span class="achievement-tree-detail__badge" :class="`achievement-tree-detail__badge--${categoryFor(selectedDefinition)}`" aria-hidden="true">
          <img
            v-if="achievementIconFor(selectedDefinition.id, selectedState.status)"
            :src="achievementIconFor(selectedDefinition.id, selectedState.status) ?? undefined"
            alt=""
          />
          <span v-else>{{ categoryMark(selectedDefinition) }}</span>
        </span>
        <div>
          <p class="achievement-tree-detail__eyebrow">DETAIL</p>
          <strong>{{ selectedDefinition.name }}</strong>
        </div>
      </div>
      <p>{{ selectedDefinition.description }}</p>
      <div class="achievement-tree-detail__status">
        <span class="achievement-tree-detail__status-label">{{ stateLabel(selectedState) }}<template v-if="progressLabel(selectedDefinition, selectedState)"> · {{ progressLabel(selectedDefinition, selectedState) }}</template></span>
        <div v-if="progressPercent(selectedDefinition, selectedState) !== null" class="achievement-tree-detail__progress" aria-hidden="true">
          <span :style="{ width: `${progressPercent(selectedDefinition, selectedState)}%` }" />
        </div>
        <span v-if="selectedState.unlockedAt" class="achievement-tree-detail__date">{{ formatUnlockDate(selectedState.unlockedAt) }} 解锁</span>
      </div>
    </div>
    <p v-else class="achievement-tree-hint">点击一个已公开的见闻，查看它的旅途记录。</p>
  </section>
</template>

<style scoped>
.achievement-tree-panel {
  position: relative;
  width: 100%;
  box-sizing: border-box;
  padding: 22px 24px 14px;
  color: #4c3b27;
  background:
    radial-gradient(circle at 15% 18%, rgba(255, 255, 255, 0.35) 0 1px, transparent 1.5px),
    radial-gradient(circle at 78% 64%, rgba(130, 94, 46, 0.08) 0 1px, transparent 1.5px),
    linear-gradient(135deg, rgba(255, 251, 231, 0.99), rgba(239, 224, 181, 0.99)),
    #f5e9c5;
  background-size: 23px 23px, 31px 31px, auto, auto;
  border: 1px solid #a18359;
  border-radius: 13px;
  box-shadow: 0 14px 28px rgba(26, 18, 9, 0.2), 4px 5px 0 rgba(93, 65, 29, 0.14), inset 0 0 0 1px rgba(255, 255, 255, 0.7);
}
.achievement-tree-panel::before {
  position: absolute;
  inset: 8px;
  border: 1px solid rgba(154, 119, 69, 0.24);
  border-radius: 9px;
  pointer-events: none;
  content: '';
}
.achievement-tree-panel__header { position: relative; z-index: 1; display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; padding: 0 31px 14px 4px; border-bottom: 1px solid rgba(139, 103, 57, 0.28); }
.achievement-tree-panel__title-group { display: flex; align-items: center; }
.achievement-tree-panel__eyebrow, .achievement-tree-detail__eyebrow { margin: 0 0 5px; color: #92754c; font: 800 0.62rem ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: 0.1em; }
.achievement-tree-panel h2 { margin: 0; color: #45331e; font-family: 'Noto Serif SC', 'Songti SC', serif; font-size: clamp(1.15rem, 2vw, 1.55rem); line-height: 1.2; letter-spacing: 0.04em; }
.achievement-tree-panel__subtitle { margin: 5px 0 0; color: #856d4b; font-size: 0.72rem; }
.achievement-tree-panel__summary { display: grid; flex: 0 0 auto; gap: 3px; min-width: 106px; padding: 8px 10px; text-align: right; background: rgba(224, 197, 129, 0.32); border: 1px solid rgba(144, 108, 60, 0.3); border-radius: 7px; box-shadow: 2px 2px 0 rgba(103, 73, 33, 0.08); }
.achievement-tree-panel__summary strong { color: #5f492d; font-family: 'Noto Serif SC', 'Songti SC', serif; font-size: 0.78rem; }
.achievement-tree-panel__summary span { color: #927850; font-size: 0.63rem; letter-spacing: 0.08em; }
.achievement-tree-scroll { position: relative; z-index: 1; overflow-x: auto; overflow-y: hidden; margin-top: 10px; padding: 8px 0 10px; background: rgba(255, 251, 229, 0.3); border: 1px solid rgba(143, 105, 57, 0.18); border-radius: 10px; box-shadow: inset 0 1px 8px rgba(126, 90, 42, 0.06); }
.achievement-tree-canvas { position: relative; width: 100%; min-width: 900px; height: 515px; }
.achievement-tree-connectors { position: absolute; z-index: 0; inset: 0; width: 100%; height: 515px; overflow: visible; }
.achievement-tree-connector { stroke-width: 3; stroke-linecap: round; stroke-dasharray: 3 6; transition: stroke 180ms ease, opacity 180ms ease, stroke-width 180ms ease; }
.achievement-tree-connector--locked { stroke: rgba(147, 112, 65, 0.28); opacity: 0.7; }
.achievement-tree-connector--in-progress { stroke: #a9854d; opacity: 0.78; }
.achievement-tree-connector--unlocked { stroke: #728d62; stroke-width: 4; opacity: 0.92; }
.achievement-tree-connector--hidden { stroke: rgba(147, 130, 94, 0.25); opacity: 0.48; stroke-dasharray: 2 8; }
.achievement-tree-detail { position: relative; z-index: 1; display: grid; grid-template-columns: minmax(145px, 0.5fr) minmax(180px, 1fr) minmax(130px, 0.7fr); align-items: center; gap: 13px; min-height: 64px; margin-top: 24px; padding: 10px 13px; background: rgba(255, 251, 229, 0.76); border: 1px solid rgba(142, 105, 57, 0.32); border-radius: 9px; box-shadow: 3px 3px 0 rgba(103, 73, 33, 0.09), inset 0 0 0 1px rgba(255, 255, 255, 0.45); }
.achievement-tree-detail__title { display: flex; align-items: center; gap: 9px; min-width: 0; }
.achievement-tree-detail__badge { display: grid; place-items: center; width: 34px; height: 34px; flex: 0 0 auto; color: #756039; font-family: 'Noto Serif SC', 'Songti SC', serif; font-size: 0.95rem; background: rgba(221, 193, 119, 0.42); border: 1px solid rgba(139, 102, 52, 0.48); border-radius: 50%; box-shadow: inset 0 0 0 2px rgba(255, 248, 213, 0.5); }
.achievement-tree-detail__badge--rhetoric { color: #8b7447; }
.achievement-tree-detail__badge--emotion { color: #967051; }
.achievement-tree-detail__badge--viewpoint { color: #557b70; }
.achievement-tree-detail__badge--loophole { color: #70705a; }
.achievement-tree-detail__badge--product { color: #907653; }
.achievement-tree-detail__badge img { display: block; width: 40px; height: 40px; object-fit: contain; }
.achievement-tree-detail strong { color: #4c3820; font-family: 'Noto Serif SC', 'Songti SC', serif; font-size: 0.96rem; }
.achievement-tree-detail p:not(.achievement-tree-detail__eyebrow) { margin: 0; color: #6f5737; font-size: 0.86rem; line-height: 1.6; }
.achievement-tree-detail__status { display: grid; gap: 5px; min-width: 0; }
.achievement-tree-detail__status-label, .achievement-tree-detail__date { color: #88704d; font-size: 0.7rem; white-space: nowrap; }
.achievement-tree-detail__date { color: #72825e; }
.achievement-tree-detail__progress { width: 100%; height: 5px; overflow: hidden; background: rgba(132, 106, 68, 0.15); border-radius: 4px; }
.achievement-tree-detail__progress span { display: block; height: 100%; background: linear-gradient(90deg, #a9824c, #75916a); border-radius: inherit; }
.achievement-tree-hint { position: relative; z-index: 1; margin: 24px 0 0; color: #947b56; font-size: 0.78rem; font-weight: 600; line-height: 1.45; text-align: center; }
@media (max-width: 700px) {
  .achievement-tree-panel { padding: 18px 15px 14px; }
  .achievement-tree-panel__header { gap: 10px; padding-right: 4px; }
  .achievement-tree-panel__summary { min-width: 92px; }
  .achievement-tree-detail { grid-template-columns: 1fr; gap: 5px; }
  .achievement-tree-detail__status-label, .achievement-tree-detail__date { white-space: normal; }
}
</style>
