<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
// [art-assets disabled]
const mapBgm = ''
const settlementBgm = ''
import { useCreationFlowStore } from '../../stores/creationFlow'
import { useGameStore } from '../../stores/game'
import { useMaterialStore } from '../../stores/material'
import { useWorkbenchStore } from '../../stores/workbench'
import { useAchievementStore } from '../../stores/achievements'
import { useWriteEssay } from '../../game/write/useWriteEssay'
import { AUDIO_VOLUME, playBgm, stopBgm } from '../../services/audioManager'
import { achievementIconFor } from '../../data/achievementIcons'
import { calcFinalRating } from '../../services/settlementService'
import { getQuadrantName, getQuadrantByMapPosition, getTargetPosition, MAP_SIZE, MAP_CENTER, QUADRANT_CONFIGS } from '../../types/mapTypes'

const emit = defineEmits<{
  'continue-journey': []
  'show-achievements': []
  restart: []
}>()

const gameStore = useGameStore()
const creationFlowStore = useCreationFlowStore()
const workbenchStore = useWorkbenchStore()
const materialStore = useMaterialStore()
const achievementStore = useAchievementStore()
const writeEssay = useWriteEssay()

const result = computed(() => gameStore.localSettlement)
const isVisible = computed(() => (
  gameStore.screen === 'round-settlement' || gameStore.screen === 'final-settlement'
))
const isSettlementOpen = computed(() => isVisible.value && result.value !== null)
const isFinal = computed(() => gameStore.screen === 'final-settlement')
const isPassed = computed(() => result.value?.passed ?? false)
// 终局屏不代表单局成败：旅程完成恒为完成态（✓），仅局结算沿用单局 passed
const showPassed = computed(() => isFinal.value || isPassed.value)
const rating = computed(() => result.value?.rating || '待定')
const answererDelta = computed(() => result.value?.answererDelta ?? 0)
const projection = computed(() => result.value?.projection ?? 0)
const vector = computed(() => gameStore.roundVector ?? [0, 0] as [number, number])
const vectorLength = computed(() => Math.hypot(gameStore.totalVector[0], gameStore.totalVector[1]))
// 结算时位置：局结算时移动尚未发生（点继续旅行→知北针动画后才落子），
// 故读“当前位置 + 本局向量”的预推落点（与实际移动同一 getTargetPosition、含边界钳制，与路径图终点同源）；终局读真实终位置
const settlementPosition = computed(() => (
  isFinal.value
    ? gameStore.mountainPosition
    : getTargetPosition(gameStore.mountainPosition, vector.value)
))
const quadrant = computed(() => getQuadrantName(
  isFinal.value
    ? gameStore.finalQuadrant
    : getQuadrantByMapPosition(settlementPosition.value.row, settlementPosition.value.col),
))
const finalRoundMaterialsConsumed = ref(false)

watch(isSettlementOpen, visible => {
  if (visible) {
    playBgm(settlementBgm, { loop: true, volume: AUDIO_VOLUME.settlementBgm })
  } else {
    stopBgm(settlementBgm)
    playBgm(mapBgm, { loop: true, volume: AUDIO_VOLUME.mapBgm })
  }
}, { immediate: true })

const finalComment = computed(() => {
  if (gameStore.answererValue >= 100) return '你已经把锋利的判断力带回了人群。'
  if (vectorLength.value >= 2.5) return '六次取材汇成了清晰而有力的方向。'
  if (isPassed.value) return '你在文章与地图之间找到了自己的路线。'
  return '旅程还没有给出强烈方向，但每次试探都留下了痕迹。'
})

// 终局评级：按总答主值划档（独立于单局向量投影评级）
const finalRating = computed(() => calcFinalRating(gameStore.answererValue))
// 累计全部已解锁成就（含历史旅程）
const unlockedAchievements = computed(() => achievementStore.unlockedAchievements)

function ratingColor(r: string): string {
  switch (r) {
    case 'SSS': return '#b7793d'
    case 'SS': return '#8e6b7b'
    case 'S': return '#5e8b7e'
    case 'A': return '#6f8f75'
    case 'B': return '#9a8050'
    default: return '#a56352'
  }
}

// ===== 终局旅程路径图（右侧迷你地图，仅 final 模式渲染） =====
const PATH_CELL = 10 // SVG 以 100x100 viewBox 表示 10x10 地图，每格 10 单位

// 按标准直角坐标系展示：横轴 = heat（x=heat，row 越小越靠右）、纵轴 = salt（y=salt，col 越小越靠上），
// 第一象限（观点海洋）落在右上，与直角坐标系惯例一致
function pathPoint(row: number, col: number): { x: number; y: number } {
  return {
    x: (MAP_SIZE - 1 - row) * PATH_CELL + PATH_CELL / 2,
    y: col * PATH_CELL + PATH_CELL / 2,
  }
}

// 所在格/看山位置的展示读数：原点 (0,0) = 出生格（地图中心），与路线图同一套直角坐标，
// 避免格子原始行列号/左下角起算与路线图方向自相矛盾
function displayCell(row: number, col: number): string {
  return `${MAP_CENTER - row}, ${MAP_CENTER - col}`
}

// 象限底色格：象限判定复用领域层 getQuadrantByMapPosition，摆放位置跟随上面的直角坐标变换
const quadrantCells = Array.from({ length: MAP_SIZE * MAP_SIZE }, (_, index) => {
  const row = Math.floor(index / MAP_SIZE)
  const col = index % MAP_SIZE
  return {
    x: (MAP_SIZE - 1 - row) * PATH_CELL,
    y: col * PATH_CELL,
    cls: `pm-${getQuadrantByMapPosition(row, col)}`,
  }
})

// 落点合并：新落点与上一折点重合（原地未移动）时并入同一圆点、局数用“·”并列，
// 避免后画的圆点遮住先画的序号、连线看似跳号（如“1 连 3”）
function appendPathStop(
  stops: Array<{ x: number; y: number; rounds: number[] }>,
  point: { x: number; y: number },
  round: number,
) {
  const last = stops[stops.length - 1]
  if (last.x === point.x && last.y === point.y) last.rounds.push(round)
  else stops.push({ ...point, rounds: [round] })
}

// 落点序列：出生点 → 各局落点；
// 局结算时移动尚未发生（moveHistory 只到上一局）：以出生格起算，
// 并用“看山当前位置 + 本局向量”预推本局落点，使路径图为“到本局结算后的路径”
const pathStops = computed(() => {
  const history = gameStore.moveHistory
  const seed = history.length
    ? pathPoint(history[0].fromRow, history[0].fromCol)
    : pathPoint(gameStore.mountainPosition.row, gameStore.mountainPosition.col)
  const stops: Array<{ x: number; y: number; rounds: number[] }> = [{ ...seed, rounds: [] }]
  for (const record of history) {
    appendPathStop(stops, pathPoint(record.toRow, record.toCol), record.round)
  }
  if (!isFinal.value) {
    appendPathStop(stops, pathPoint(settlementPosition.value.row, settlementPosition.value.col), gameStore.currentRound)
  }
  return stops.map(stop => ({ x: stop.x, y: stop.y, label: stop.rounds.join('·') }))
})

const pathPolyline = computed(() => pathStops.value.map(p => `${p.x},${p.y}`).join(' '))

const pathStart = computed(() => pathStops.value[0] ?? null)
const pathEnd = computed(() => pathStops.value[pathStops.value.length - 1] ?? null)
// 象限角落小标：按直角坐标系象限位（Ⅰ右上、Ⅱ左上、Ⅲ左下、Ⅳ右下），
// 序号沿用约定：Ⅰ观点海洋 Ⅱ盐度冰川 Ⅲ知识荒原 Ⅳ情绪火山；配色取 QUADRANT_CONFIGS 官方色
const quadrantLabels = [
  { x: 96, y: 11, cls: 'q-view', text: `Ⅰ ${QUADRANT_CONFIGS[0].name}`, anchor: 'end' },
  { x: 4, y: 11, cls: 'q-critique', text: `Ⅱ ${QUADRANT_CONFIGS[1].name}`, anchor: 'start' },
  { x: 4, y: 95, cls: 'q-wasteland', text: `Ⅲ ${QUADRANT_CONFIGS[3].name}`, anchor: 'start' },
  { x: 96, y: 95, cls: 'q-emotion', text: `Ⅳ ${QUADRANT_CONFIGS[2].name}`, anchor: 'end' },
] as const
function handleContinueJourney() {
  materialStore.consumeMaterials(gameStore.committedMaterialIds)
  // v5: 不清除工作区（知北针动画还需要 currentVector），由 MapView 的 handleCompassMovementStart 清除
  // 只设置状态，让 MapView 触发知北针动画（beginCompassMovement 由 CompassButton 的 movement-start 事件调用）
  gameStore.preparePostSettlementCompass()
  emit('continue-journey')
}

function handleRestart() {
  writeEssay.resetWriting()
  creationFlowStore.clear()
  workbenchStore.clearWorkbench()
  workbenchStore.currentVector = [0, 0]
  materialStore.clearMaterials()
  gameStore.resetGame()
  emit('restart')
}

watch(isFinal, isFinalSettlement => {
  if (!isFinalSettlement) {
    finalRoundMaterialsConsumed.value = false
    return
  }
  if (finalRoundMaterialsConsumed.value) return
  materialStore.consumeMaterials(gameStore.committedMaterialIds)
  gameStore.clearCommittedMaterialSnapshot()
  finalRoundMaterialsConsumed.value = true
}, { immediate: true })

onBeforeUnmount(() => stopBgm(settlementBgm))
</script>

<template>
  <Teleport to="body">
    <div v-if="isVisible && result" class="settlement-overlay" :class="{ 'settlement-overlay--final': isFinal, 'settlement-overlay--round': !isFinal }">
      <div class="settlement-modal" :class="{ 'settlement-modal--final': isFinal, 'settlement-modal--round': !isFinal }">
        <div class="settlement-body">
        <div class="settlement-column" :class="{ 'settlement-column--final': isFinal }">
        <div class="settlement-icon" :class="showPassed ? 'settlement-icon--pass' : 'settlement-icon--fail'">
          {{ showPassed ? '✓' : '✗' }}
        </div>

        <p v-if="isFinal" class="settlement-eyebrow">旅程完成</p>
        <h2 class="settlement-title" :class="showPassed ? 'settlement-title--pass' : 'settlement-title--fail'">
          {{ isFinal ? '看山的旅途小结' : isPassed ? '看山抵达新坐标' : '看山完成了这次试探' }}
        </h2>

        <div class="settlement-rating" :class="{ 'settlement-rating--final': isFinal }" :style="isFinal ? undefined : { color: ratingColor(rating) }">
          {{ isFinal ? 'FINAL JOURNEY NOTE' : rating }}
        </div>

        <div v-if="isFinal" class="final-settlement-summary">
          <div class="final-rating-line">
            <span class="final-rating-prefix">评级:</span>
            <span class="final-rating" :style="{ color: ratingColor(finalRating) }">{{ finalRating }}</span>
            <span class="final-rating-answerer">总答主值 {{ gameStore.answererValue }}</span>
          </div>
          <p>{{ finalComment }}</p>
          <div class="final-settlement-grid">
            <span>最终方向<strong>{{ quadrant }}</strong></span>
            <span>向量总长<strong>{{ vectorLength.toFixed(2) }}</strong></span>
            <span>所在格<strong>{{ displayCell(settlementPosition.row, settlementPosition.col) }}</strong></span>
          </div>
          <div v-if="unlockedAchievements.length" class="final-achievements">
            <span class="final-achievements-label">获得成就</span>
            <div class="final-achievement-badges">
              <span
                v-for="achievement in unlockedAchievements"
                :key="achievement.id"
                class="final-achievement-badge"
              >
                <img
                  v-if="achievementIconFor(achievement.id, 'UNLOCKED')"
                  :src="achievementIconFor(achievement.id, 'UNLOCKED') ?? undefined"
                  alt=""
                />
                <span v-else class="final-achievement-mark">{{ achievement.name.charAt(0) }}</span>
                {{ achievement.name }}
              </span>
            </div>
          </div>
          <p v-else class="final-achievements-empty">尚未解锁任何成就</p>
        </div>
        <template v-else>
          <div class="settlement-answerer">
            <span v-if="isPassed" class="settlement-answerer-hint">答主值 +{{ answererDelta }}</span>
            <span v-else class="settlement-answerer-hint">本局答主值不变</span>
            <span class="settlement-answerer-detail">当前总值 {{ gameStore.answererValue }}</span>
          </div>
          <div class="settlement-round-detail">
            <span>本局向量 ({{ vector[0].toFixed(2) }}, {{ vector[1].toFixed(2) }})</span>
            <span>所在象限 {{ quadrant }}</span>
            <span>看山位置 {{ displayCell(settlementPosition.row, settlementPosition.col) }}</span>
          </div>
        </template>

        <p class="settlement-round">
          <template v-if="isFinal">第 {{ gameStore.currentRound }} / {{ gameStore.totalRounds }} 局 · 旅程已完成</template>
          <template v-else>第 {{ gameStore.currentRound }} / {{ gameStore.totalRounds }} 局</template>
        </p>

        <button v-if="!isFinal" class="settlement-action-btn" type="button" @click="handleContinueJourney">
          继续旅行 →
        </button>
        <template v-else>
          <div class="settlement-actions">
            <button class="settlement-action-btn settlement-action-btn--secondary" type="button" @click="emit('show-achievements')">查看成就</button>
            <button class="settlement-action-btn settlement-action-btn--retry" type="button" @click="handleRestart">重新开始</button>
          </div>
        </template>
        </div>

        <!-- 右侧旅程路径图（10x10 迷你地图）：终局呈现六局完整路线，局结算呈现到本局结算后的路径 -->
        <aside v-if="pathStops.length" class="journey-path-panel" aria-label="旅程路径图">
          <span class="journey-path-title">{{ isFinal ? '旅程路径' : '旅程路径 · 截至本局' }}</span>
          <svg class="journey-path-svg" viewBox="-7 -7 114 114" role="img" aria-label="看山六局行进路线">
            <g class="journey-path-cells">
              <rect
                v-for="(cell, cellIndex) in quadrantCells"
                :key="cellIndex"
                class="journey-path-cell"
                :class="cell.cls"
                :x="cell.x"
                :y="cell.y"
                width="10"
                height="10"
              />
            </g>
            <text
              v-for="label in quadrantLabels"
              :key="label.cls"
              class="journey-path-qlabel"
              :class="label.cls"
              :x="label.x"
              :y="label.y"
              :text-anchor="label.anchor"
            >{{ label.text }}</text>
            <polyline class="journey-path-line" :points="pathPolyline" />
            <g v-for="(stop, stopIndex) in pathStops" :key="stopIndex" class="journey-path-stop">
              <circle class="journey-path-dot" :cx="stop.x" :cy="stop.y" r="4.6" />
              <text
                v-if="stop.label"
                class="journey-path-num"
                :class="{ 'journey-path-num--multi': stop.label.length > 1 }"
                :x="stop.x"
                :y="stop.y"
                text-anchor="middle"
                dominant-baseline="central"
              >{{ stop.label }}</text>
            </g>
            <g v-if="pathStart" class="journey-path-flag">
              <circle class="journey-path-flag-ring" :cx="pathStart.x" :cy="pathStart.y" r="6.4" />
              <text class="journey-path-flag-text" :x="pathStart.x" :y="pathStart.y + 11" text-anchor="middle">起</text>
            </g>
            <g v-if="pathEnd" class="journey-path-flag">
              <circle class="journey-path-flag-ring journey-path-flag-ring--end" :cx="pathEnd.x" :cy="pathEnd.y" r="6.4" />
              <text class="journey-path-flag-text" :x="pathEnd.x" :y="pathEnd.y - 8.5" text-anchor="middle">终</text>
            </g>
          </svg>
          <span class="journey-path-hint">原点 (0,0) = 出生格；圆点数字 = 落点局数，原地未移动合并显示（如 2·3）</span>
        </aside>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.settlement-round-detail,
.final-settlement-summary {
  display: grid;
  gap: 5px;
  color: var(--pixel-muted, #a7bec8);
  font: 0.68rem/1.45 ui-monospace, SFMono-Regular, Consolas, monospace;
  text-align: center;
}
.final-settlement-summary > p { margin: 0; color: #d8f2ea; font-size: 0.76rem; }
.final-settlement-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; margin-top: 5px; }
.final-settlement-grid span { display: grid; gap: 2px; border: 1px solid rgba(122, 191, 204, 0.24); padding: 6px 4px; }
.final-settlement-grid strong { color: #eafff5; font-size: 0.76rem; }

/* Final settlement is a journal page rather than a HUD panel. */
.settlement-overlay--final {
  background: rgba(66, 48, 32, 0.56);
  backdrop-filter: blur(5px);
  -webkit-backdrop-filter: blur(5px);
}
.settlement-overlay--round {
  background: rgba(66, 48, 32, 0.5);
  backdrop-filter: blur(5px);
  -webkit-backdrop-filter: blur(5px);
}
.settlement-modal--round {
  position: relative;
  width: min(860px, calc(100vw - 32px));
  min-width: 0;
  max-width: 860px;
  gap: 13px;
  overflow: hidden;
  border: 1px solid #b99568;
  border-radius: 14px;
  padding: 30px 28px 24px;
  background:
    radial-gradient(circle at 14% 18%, rgba(166, 123, 70, 0.08) 0 1px, transparent 1.5px),
    radial-gradient(circle at 78% 72%, rgba(120, 92, 52, 0.06) 0 1px, transparent 1.5px),
    linear-gradient(145deg, rgba(255, 252, 236, 0.99), rgba(246, 235, 211, 0.98)),
    #f7edd7;
  background-size: 23px 23px, 31px 31px, auto, auto;
  box-shadow:
    0 20px 42px rgba(45, 31, 20, 0.22),
    4px 5px 0 rgba(105, 75, 40, 0.11),
    inset 0 0 0 1px rgba(255, 255, 255, 0.72);
  color: #594733;
}
.settlement-modal--round::before {
  position: absolute;
  inset: 9px;
  border: 1px solid rgba(157, 121, 70, 0.2);
  border-radius: 9px;
  content: '';
  pointer-events: none;
}
.settlement-modal--round > * { position: relative; z-index: 1; }
/* 局结算双栏：左列沿用原单栏 grid，右列为旅程路径图（与终局结算同构） */
.settlement-modal--round .settlement-body {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  width: 100%;
  gap: 18px;
}
.settlement-modal--round .settlement-column {
  display: grid;
  justify-items: center;
  gap: 13px;
  width: 100%;
  min-width: 0;
  flex: 1 1 340px;
  max-width: 420px;
}
.settlement-modal--round .settlement-icon {
  width: 46px;
  height: 46px;
  border-width: 1px;
  border-color: #a68a5d;
  background: #eadbb8;
  box-shadow: inset 0 0 0 3px rgba(255, 250, 224, 0.42), 2px 3px 0 rgba(105, 75, 40, 0.09);
  color: #6d896d;
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: 1.2rem;
}
.settlement-modal--round .settlement-icon--fail {
  border-color: #ad7963;
  background: #efdbcf;
  color: #a36350;
}
.settlement-modal--round .settlement-title {
  margin: 0;
  color: #624a32;
  font: 800 0.82rem/1.25 'Noto Serif SC', 'Songti SC', serif;
  letter-spacing: 0.12em;
}
.settlement-modal--round .settlement-title--fail { color: #7b5040; }
.settlement-modal--round .settlement-rating {
  margin-top: -5px;
  color: #9a8050;
  font: 800 2.55rem/1 'Noto Serif SC', 'Songti SC', serif;
  letter-spacing: 0.04em;
  text-shadow: 0 1px 0 rgba(255, 252, 236, 0.7);
}
.settlement-modal--round .settlement-answerer {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 10px 14px;
  border: 1px solid rgba(190, 160, 113, 0.6);
  border-radius: 9px;
  background: rgba(255, 249, 226, 0.6);
  box-shadow: 2px 3px 0 rgba(105, 75, 40, 0.07), inset 0 1px 0 rgba(255, 255, 255, 0.6);
  font-family: 'Noto Serif SC', 'Songti SC', serif;
}
.settlement-modal--round .settlement-answerer-hint {
  color: #9a604c;
  font-size: 0.88rem;
  font-weight: 800;
}
.settlement-modal--round .settlement-answerer-detail {
  color: #897153;
  font-size: 0.68rem;
}
.settlement-modal--round .settlement-round-detail {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  width: 100%;
  gap: 7px;
  color: #927957;
  font: 0.63rem/1.45 ui-monospace, SFMono-Regular, Consolas, monospace;
}
.settlement-modal--round .settlement-round-detail span {
  display: grid;
  min-height: 54px;
  align-content: center;
  gap: 3px;
  border: 1px solid #cbb28a;
  border-radius: 8px;
  padding: 8px 5px;
  background: rgba(255, 249, 226, 0.5);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.58);
}
.settlement-modal--round .settlement-round {
  margin: -2px 0 1px;
  color: #927b5d;
  font: 0.66rem/1.4 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.04em;
}
.settlement-modal--round .settlement-action-btn {
  min-height: 42px;
  border: 1px solid #6f907a;
  border-radius: 9px;
  padding: 10px 16px;
  background: #86a888;
  box-shadow: 2px 3px 0 rgba(79, 103, 75, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.38);
  color: #fff9e9;
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: 0.8rem;
  font-weight: 800;
  letter-spacing: 0.05em;
  transition: transform 150ms ease, box-shadow 150ms ease, filter 150ms ease;
}
.settlement-modal--round .settlement-action-btn:hover {
  transform: translateY(-2px);
  border-color: #5f806b;
  box-shadow: 2px 5px 0 rgba(79, 103, 75, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.44);
  filter: brightness(1.04);
}
.settlement-modal--round .settlement-action-btn:active {
  transform: translateY(1px);
  box-shadow: 1px 1px 0 rgba(79, 103, 75, 0.14);
}
.settlement-modal--round .settlement-action-btn:focus-visible {
  outline: 2px solid #a68a5d;
  outline-offset: 3px;
}
.settlement-modal--final {
  position: relative;
  width: min(860px, calc(100vw - 32px));
  min-width: 0;
  max-width: 860px;
  gap: 14px;
  overflow: hidden;
  border: 1px solid #b99568;
  border-radius: 16px;
  padding: 34px 32px 30px;
  background:
    radial-gradient(circle at 14% 18%, rgba(166, 123, 70, 0.09) 0 1px, transparent 1.5px),
    radial-gradient(circle at 78% 72%, rgba(120, 92, 52, 0.07) 0 1px, transparent 1.5px),
    linear-gradient(145deg, rgba(255, 252, 236, 0.99), rgba(244, 232, 202, 0.98)),
    #f7edd7;
  background-size: 23px 23px, 31px 31px, auto, auto;
  box-shadow:
    0 22px 48px rgba(45, 31, 20, 0.24),
    5px 6px 0 rgba(105, 75, 40, 0.12),
    inset 0 0 0 1px rgba(255, 255, 255, 0.72);
  color: #594733;
}
.settlement-modal--final::before {
  position: absolute;
  inset: 9px;
  border: 1px solid rgba(157, 121, 70, 0.22);
  border-radius: 10px;
  content: '';
  pointer-events: none;
}
.settlement-modal--final > * { position: relative; z-index: 1; }
/* 终局双栏：左列沿用原单栏 grid，右列为旅程路径图 */
.settlement-modal--final .settlement-body {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  width: 100%;
  gap: 18px;
}
.settlement-modal--final .settlement-column--final {
  display: grid;
  justify-items: center;
  gap: 14px;
  min-width: 0;
  flex: 1 1 380px;
  max-width: 420px;
  text-align: center;
}
.journey-path-panel {
  display: grid;
  flex: 0 1 380px;
  gap: 8px;
  justify-items: center;
  align-content: start;
  border: 1px solid #cbb28a;
  border-radius: 10px;
  padding: 12px 12px 10px;
  background: rgba(255, 249, 226, 0.6);
  box-shadow: 2px 3px 0 rgba(105, 75, 40, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.6);
}
.journey-path-title {
  color: #927957;
  font: 0.68rem/1.2 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.14em;
}
.journey-path-svg {
  width: 100%;
  height: auto;
  border: 1px solid rgba(157, 121, 70, 0.35);
  border-radius: 6px;
  background: #fbf3dd;
}
.journey-path-hint {
  color: #a08a68;
  font: 0.6rem/1.4 ui-monospace, SFMono-Regular, Consolas, monospace;
  text-align: center;
}
/* 象限底色：沿用 QUADRANT_CONFIGS 官方色，低透明度作地图色块 */
.journey-path-cell.pm-view { fill: rgba(76, 155, 145, 0.13); }
.journey-path-cell.pm-critique { fill: rgba(255, 255, 255, 0.13); }
.journey-path-cell.pm-emotion { fill: rgba(216, 95, 89, 0.13); }
.journey-path-cell.pm-wasteland { fill: rgba(211, 154, 85, 0.13); }
.journey-path-qlabel { font: 3.4px 'Noto Serif SC', 'Songti SC', serif; opacity: 0.85; }
.journey-path-qlabel.q-view { fill: #3a7d74; }
.journey-path-qlabel.q-critique { fill: #8b8f99; }
.journey-path-qlabel.q-emotion { fill: #b04a44; }
.journey-path-qlabel.q-wasteland { fill: #d4a843; }
.journey-path-line {
  fill: none;
  stroke: #6b4a2a;
  stroke-width: 1.6;
  stroke-linejoin: round;
  stroke-linecap: round;
  opacity: 0.85;
}
.journey-path-dot {
  fill: #fff9e9;
  stroke: #6b4a2a;
  stroke-width: 1.2;
}
.journey-path-num {
  fill: #54402c;
  font: 700 5px ui-monospace, SFMono-Regular, Consolas, monospace;
}
/* 同格合并的多局序号（如 2·3）缩小字号以容纳 */
.journey-path-num--multi { font-size: 3.6px; }
.journey-path-flag-ring { fill: none; stroke: #6d896d; stroke-width: 1.1; }
.journey-path-flag-ring--end { stroke: #a36350; }
.journey-path-flag-text {
  fill: #6f5a43;
  font: 700 5px 'Noto Serif SC', 'Songti SC', serif;
}
.settlement-modal--final .settlement-icon {
  width: 40px;
  height: 40px;
  border-width: 1px;
  border-color: #a68a5d;
  border-radius: 50%;
  background: #eadbb8;
  box-shadow: inset 0 0 0 3px rgba(255, 250, 224, 0.42), 2px 3px 0 rgba(105, 75, 40, 0.1);
  color: #6d896d;
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: 1.1rem;
}
.settlement-modal--final .settlement-icon--fail {
  border-color: #ad7963;
  background: #efdbcf;
  color: #a36350;
}
.settlement-modal--final .settlement-eyebrow {
  margin: -2px 0 -9px;
  color: #92754c;
  font: 800 0.62rem/1 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.16em;
}
.settlement-modal--final .settlement-title {
  margin: 0;
  color: #4f3b27;
  font-family: 'Noto Serif SC', 'Songti SC', Georgia, serif;
  font-size: clamp(1.05rem, 3.2vw, 1.22rem);
  font-weight: 800;
  letter-spacing: 0.08em;
  line-height: 1.3;
}
.settlement-modal--final .settlement-title--fail { color: #6b4537; }
.settlement-modal--final .settlement-rating--final {
  margin-top: -5px;
  color: #9b7b4d;
  font: 800 0.72rem/1 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.16em;
}
.settlement-modal--final .final-settlement-summary {
  width: 100%;
  gap: 14px;
  margin-top: 3px;
}
.settlement-modal--final .final-settlement-summary > p {
  max-width: 310px;
  margin: 0 auto;
  color: #6f5a43;
  font: 0.83rem/1.8 'Noto Serif SC', 'Songti SC', serif;
}
.settlement-modal--final .final-settlement-grid {
  width: 100%;
  gap: 9px;
  margin-top: 0;
}
.settlement-modal--final .final-settlement-grid span {
  min-height: 64px;
  align-content: center;
  gap: 6px;
  border: 1px solid #cbb28a;
  border-radius: 9px;
  padding: 10px 8px;
  background: rgba(255, 249, 226, 0.64);
  box-shadow: 2px 3px 0 rgba(105, 75, 40, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.66);
  color: #927957;
  font: 0.64rem/1.2 ui-monospace, SFMono-Regular, Consolas, monospace;
}
.settlement-modal--final .final-settlement-grid strong {
  color: #54402c;
  font: 800 0.88rem/1.25 'Noto Serif SC', 'Songti SC', serif;
}
.settlement-modal--final .final-rating-line {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 8px;
  margin-top: -2px;
}
.settlement-modal--final .final-rating-prefix {
  color: #927957;
  font: 0.66rem/1.2 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.04em;
}
.settlement-modal--final .final-rating {
  font: 800 1.55rem/1 'Noto Serif SC', 'Songti SC', serif;
  letter-spacing: 0.06em;
  text-shadow: 0 1px 0 rgba(255, 252, 236, 0.7);
}
.settlement-modal--final .final-rating-answerer {
  color: #897153;
  font: 0.7rem/1.2 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.04em;
}
.settlement-modal--final .final-achievements {
  display: grid;
  width: 100%;
  gap: 6px;
}
.settlement-modal--final .final-achievements-label {
  color: #927957;
  font: 0.62rem/1.2 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.14em;
  text-align: center;
}
.settlement-modal--final .final-achievement-badges {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
}
.settlement-modal--final .final-achievement-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid #cbb28a;
  border-radius: 999px;
  padding: 4px 10px;
  background: rgba(255, 249, 226, 0.6);
  color: #6f5a43;
  font: 700 0.66rem/1.2 'Noto Serif SC', 'Songti SC', serif;
}
.settlement-modal--final .final-achievement-badge img {
  width: 16px;
  height: 16px;
}
.settlement-modal--final .final-achievement-mark {
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  border: 1px solid #cbb28a;
  border-radius: 50%;
  color: #927957;
  font: 0.55rem/1 ui-monospace, SFMono-Regular, Consolas, monospace;
}
.settlement-modal--final p.final-achievements-empty {
  margin: 0;
  color: #927957;
  font: 0.66rem/1.4 ui-monospace, SFMono-Regular, Consolas, monospace;
}
.settlement-modal--final .settlement-round {
  margin: -3px 0 1px;
  color: #927b5d;
  font: 0.66rem/1.4 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.04em;
}
.settlement-modal--final .settlement-actions {
  display: grid;
  width: 100%;
  gap: 9px;
  margin-top: 2px;
}
.settlement-modal--final .settlement-action-btn {
  min-height: 42px;
  border: 1px solid #9e8767;
  border-radius: 9px;
  padding: 10px 16px;
  box-shadow: 2px 3px 0 rgba(82, 63, 40, 0.13), inset 0 1px 0 rgba(255, 255, 255, 0.3);
  color: #5d4935;
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: 0.8rem;
  font-weight: 800;
  letter-spacing: 0.05em;
  transition: transform 150ms ease, box-shadow 150ms ease, filter 150ms ease;
}
.settlement-modal--final .settlement-action-btn:hover {
  transform: translateY(-2px);
  box-shadow: 2px 5px 0 rgba(82, 63, 40, 0.13), inset 0 1px 0 rgba(255, 255, 255, 0.4);
  filter: brightness(1.04);
}
.settlement-modal--final .settlement-action-btn:active {
  transform: translateY(1px);
  box-shadow: 1px 1px 0 rgba(82, 63, 40, 0.12);
}
.settlement-modal--final .settlement-action-btn:focus-visible {
  outline: 2px solid #a68a5d;
  outline-offset: 3px;
}
.settlement-modal--final .settlement-action-btn--secondary {
  border-color: #c0aa84;
  background: rgba(249, 241, 219, 0.86);
  color: #745e42;
}
.settlement-modal--final .settlement-action-btn--retry {
  border-color: #b88670;
  background: rgba(239, 220, 207, 0.9);
  color: #9a604c;
}
.settlement-modal--final .settlement-action-btn--retry:hover { border-color: #a96f58; }
/* 窄屏放不下右侧路径图：隐藏侧栏，弹窗退回原单栏窄版 */
@media (max-width: 899px) {
  .settlement-modal--final { width: min(430px, calc(100vw - 32px)); max-width: 430px; }
  .settlement-modal--round { width: min(420px, calc(100vw - 32px)); max-width: 420px; }
  .journey-path-panel { display: none; }
}
@media (max-width: 480px) {
  .settlement-modal--round { width: calc(100vw - 24px); padding: 26px 18px 22px; }
  .settlement-modal--round .settlement-round-detail { grid-template-columns: 1fr; }
  .settlement-modal--final { width: calc(100vw - 24px); padding: 28px 20px 24px; }
  .settlement-modal--final .final-settlement-grid { gap: 5px; }
  .settlement-modal--final .final-settlement-grid span { min-height: 60px; padding: 8px 4px; }
}
</style>
