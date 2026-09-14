<script setup lang="ts">
/** 等距菱形地图。逻辑坐标与视觉坐标分离，地图只负责展示；所有几何由 MAP_SIZE 推导。 */
import { computed } from 'vue'
const kanshanImg = '' // [art-assets disabled] ../assets/kanshan/map-kanshan.webp
import {
  getQuadrantByMapPosition,
  getQuadrantName,
  MAP_CENTER,
  MAP_SIZE,
  QUADRANT_CONFIGS,
  REGION_VISUAL_CONFIG,
} from '../../types/mapTypes'
import type { BiomeType, MountainPosition, QuadrantType } from '../../types/mapTypes'

const props = withDefaults(defineProps<{
  mountainPosition?: MountainPosition
  visitedQuadrants?: QuadrantType[]
  showArticleBubble?: boolean
}>(), {
  mountainPosition: () => ({
    row: MAP_CENTER,
    col: MAP_CENTER,
    direction: 'down',
    isMoving: false,
  }),
  visitedQuadrants: () => [],
  showArticleBubble: false,
})

const emit = defineEmits<{
  articleBubbleClick: []
}>()

const TILE_WIDTH = 92
const TILE_HEIGHT = 48
const CHARACTER_SIZE = 64

/** Half extents of the whole diamond, including the outer half-tile. */
const HALF_WIDTH = MAP_SIZE * TILE_WIDTH / 2
const HALF_HEIGHT = MAP_SIZE * TILE_HEIGHT / 2
// Leave a real environment ring around the 10×10 plate instead of scaling the
// diamond edge-to-edge. The grid remains dominant while all four biome scenes
// have enough page space to read as environments.
const VIEW_PADDING = 112
const VIEW_BOX = [
  -HALF_WIDTH - VIEW_PADDING,
  -HALF_HEIGHT - VIEW_PADDING,
  2 * (HALF_WIDTH + VIEW_PADDING),
  2 * (HALF_HEIGHT + VIEW_PADDING),
].join(' ')

const OUTLINE_POINTS = `0,${-HALF_HEIGHT} ${HALF_WIDTH},0 0,${HALF_HEIGHT} ${-HALF_WIDTH},0`

/**
 * The two grid directions, drawn as the diagonal reference axes from the screenshot.
 * A line through the centre along either direction leaves the diamond at half extent.
 */
const AXIS_X = HALF_WIDTH / 2
const AXIS_Y = HALF_HEIGHT / 2

interface MapCell {
  row: number
  col: number
  x: number
  y: number
  quadrant: QuadrantType
  biome: BiomeType
}

function cellCenter(row: number, col: number) {
  return {
    x: (col - row) * TILE_WIDTH / 2,
    y: (row + col - (MAP_SIZE - 1)) * TILE_HEIGHT / 2,
  }
}

const cells = computed<MapCell[]>(() => (
  Array.from({ length: MAP_SIZE * MAP_SIZE }, (_, index) => {
    const row = Math.floor(index / MAP_SIZE)
    const col = index % MAP_SIZE
    const quadrant = getQuadrantByMapPosition(row, col)
    return {
      row,
      col,
      ...cellCenter(row, col),
      quadrant,
      biome: REGION_VISUAL_CONFIG[quadrant].biome,
    }
  })
))

/** Quadrant names sit at the centroid of their own cells, so they scale with MAP_SIZE. */
const quadrantLabels = computed(() => QUADRANT_CONFIGS.map(config => {
  const members = cells.value.filter(cell => cell.quadrant === config.id)
  const sum = members.reduce((acc, cell) => ({ x: acc.x + cell.x, y: acc.y + cell.y }), { x: 0, y: 0 })
  const count = Math.max(members.length, 1)
  return {
    quadrant: config.id,
    x: sum.x / count,
    y: sum.y / count,
  }
}))

const renderPosition = computed(() => {
  const position = props.mountainPosition
  const row = position.isMoving && position.targetRow !== undefined
    ? position.targetRow
    : position.row
  const col = position.isMoving && position.targetCol !== undefined
    ? position.targetCol
    : position.col
  return cellCenter(row, col)
})

const currentCell = computed(() => ({
  row: props.mountainPosition.isMoving && props.mountainPosition.targetRow !== undefined
    ? props.mountainPosition.targetRow
    : props.mountainPosition.row,
  col: props.mountainPosition.isMoving && props.mountainPosition.targetCol !== undefined
    ? props.mountainPosition.targetCol
    : props.mountainPosition.col,
}))

function tilePoints(x: number, y: number) {
  return `${x},${y - TILE_HEIGHT / 2} ${x + TILE_WIDTH / 2},${y} ${x},${y + TILE_HEIGHT / 2} ${x - TILE_WIDTH / 2},${y}`
}
</script>

<template>
  <div class="diamond-map-root" :aria-label="`${MAP_SIZE}×${MAP_SIZE} 等距旅行地图`">
    <svg
      class="diamond-map"
      :viewBox="VIEW_BOX"
      :data-map-size="MAP_SIZE"
      :data-cell-count="MAP_SIZE * MAP_SIZE"
      xmlns="http://www.w3.org/2000/svg"
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <radialGradient id="map-backdrop" gradientUnits="userSpaceOnUse" cx="0" cy="0" :r="HALF_WIDTH">
          <stop offset="0" stop-color="#14343f" />
          <stop offset="0.62" stop-color="#0c2530" />
          <stop offset="1" stop-color="#071a23" />
        </radialGradient>
        <linearGradient id="tint-ocean" gradientUnits="userSpaceOnUse" :x1="-HALF_WIDTH" :y1="-HALF_HEIGHT" :x2="0" :y2="0">
          <stop offset="0" stop-color="#1d6f86" stop-opacity="0.5" />
          <stop offset="1" stop-color="#154f6b" stop-opacity="0.34" />
        </linearGradient>
        <linearGradient id="tint-glacier" gradientUnits="userSpaceOnUse" :x1="-HALF_WIDTH" :y1="0" :x2="0" :y2="HALF_HEIGHT">
          <stop offset="0" stop-color="#7fb6d8" stop-opacity="0.42" />
          <stop offset="1" stop-color="#4a86ad" stop-opacity="0.3" />
        </linearGradient>
        <linearGradient id="tint-volcano" gradientUnits="userSpaceOnUse" :x1="0" :y1="-HALF_HEIGHT" :x2="HALF_WIDTH" :y2="0">
          <stop offset="0" stop-color="#6d3a44" stop-opacity="0.48" />
          <stop offset="1" stop-color="#94472f" stop-opacity="0.34" />
        </linearGradient>
        <linearGradient id="tint-desert" gradientUnits="userSpaceOnUse" :x1="0" :y1="0" :x2="HALF_WIDTH" :y2="HALF_HEIGHT">
          <stop offset="0" stop-color="#b99a5c" stop-opacity="0.44" />
          <stop offset="1" stop-color="#8d6a41" stop-opacity="0.3" />
        </linearGradient>
        <filter id="map-outline-glow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="5" stdDeviation="6" flood-color="#04121a" flood-opacity="0.6" />
        </filter>
        <marker
          id="axis-arrow-salt"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        >
          <path d="M0 0 L10 5 L0 10 Z" class="axis-arrow-head axis-arrow-head--salt" />
        </marker>
        <marker
          id="axis-arrow-heat"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        >
          <path d="M0 0 L10 5 L0 10 Z" class="axis-arrow-head axis-arrow-head--heat" />
        </marker>
      </defs>

      <rect
        class="map-backdrop"
        :x="-HALF_WIDTH - VIEW_PADDING"
        :y="-HALF_HEIGHT - VIEW_PADDING"
        :width="2 * (HALF_WIDTH + VIEW_PADDING)"
        :height="2 * (HALF_HEIGHT + VIEW_PADDING)"
        fill="url(#map-backdrop)"
      />

      <polygon :points="OUTLINE_POINTS" class="map-outline-shadow" />
      <polygon :points="OUTLINE_POINTS" class="map-plate" />

      <g class="map-cells" data-layer="grid">
        <g
          v-for="cell in cells"
          :key="`grid-${cell.row}-${cell.col}`"
          class="map-cell"
          :class="[
            `map-cell--${cell.quadrant}`,
            `map-biome--${cell.biome}`,
            { 'map-cell--current': cell.row === currentCell.row && cell.col === currentCell.col },
            { 'map-cell--visited': props.visitedQuadrants.includes(cell.quadrant) },
          ]"
          :data-row="cell.row"
          :data-col="cell.col"
          :data-quadrant="cell.quadrant"
          :data-biome="cell.biome"
        >
          <polygon :points="tilePoints(cell.x, cell.y)" :fill="`url(#tint-${cell.biome})`" class="map-tile-fill" />
          <polygon :points="tilePoints(cell.x, cell.y)" class="map-tile" />
        </g>
      </g>

      <polygon :points="OUTLINE_POINTS" class="map-outline" />

      <g class="map-axes" aria-hidden="true" data-layer="axes">
        <line
          :x1="AXIS_X"
          :y1="AXIS_Y"
          :x2="-AXIS_X"
          :y2="-AXIS_Y"
          class="axis-line axis-line--salt"
          marker-end="url(#axis-arrow-salt)"
        />
        <line
          :x1="-AXIS_X"
          :y1="AXIS_Y"
          :x2="AXIS_X"
          :y2="-AXIS_Y"
          class="axis-line axis-line--heat"
          marker-end="url(#axis-arrow-heat)"
        />
      </g>

      <g class="map-labels" aria-hidden="true">
        <text
          v-for="label in quadrantLabels"
          :key="label.quadrant"
          :x="label.x"
          :y="label.y"
          :class="['quadrant-label', `quadrant-label--${label.quadrant}`]"
          text-anchor="middle"
        >{{ getQuadrantName(label.quadrant) }}</text>
      </g>

      <g
        class="kanshan-layer"
        :class="{ 'kanshan-layer--moving': props.mountainPosition.isMoving }"
        :transform="`translate(${renderPosition.x} ${renderPosition.y - 24})`"
        :data-row="props.mountainPosition.row"
        :data-col="props.mountainPosition.col"
        :data-direction="props.mountainPosition.direction"
        :data-moving="props.mountainPosition.isMoving"
      >
        <!-- 每局文章生成：感叹号气泡 -->
        <g
          v-if="props.showArticleBubble"
          class="article-bubble-group"
          style="cursor: pointer"
          @click="emit('articleBubbleClick')"
        >
          <circle cx="28" cy="-38" r="14" class="article-bubble-bg" />
          <text x="28" y="-33" class="article-bubble-icon" text-anchor="middle">!</text>
        </g>
        <image
          :href="kanshanImg"
          :x="-CHARACTER_SIZE / 2"
          :y="-CHARACTER_SIZE / 2"
          :width="CHARACTER_SIZE"
          :height="CHARACTER_SIZE"
          class="kanshan-image"
          preserveAspectRatio="xMidYMid slice"
        />
      </g>
    </svg>
  </div>
</template>

<style scoped>
.diamond-map-root {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  isolation: isolate;
  background: transparent;
}

.diamond-map {
  width: 100%;
  height: 100%;
  display: block;
}

.map-backdrop {
  fill: transparent;
}
.map-plate {
  fill: rgba(249, 238, 206, 0.18);
}
.map-outline-shadow,
.map-outline {
  fill: none;
  pointer-events: none;
}
.map-outline-shadow {
  stroke: rgba(108, 193, 196, 0.16);
  stroke-width: 5;
  filter: none;
}
.map-outline {
  stroke: rgba(178, 240, 229, 0.62);
  stroke-width: 2;
}

.map-cell .map-tile-fill {
  stroke: none;
  opacity: 0.9;
  filter: brightness(1.1) saturate(0.92);
  transition: filter 180ms ease, opacity 180ms ease;
}
.map-cell .map-tile {
  fill: none;
  stroke: rgba(216, 246, 242, 0.46);
  stroke-width: 1.15;
  vector-effect: non-scaling-stroke;
  transition: stroke 180ms ease, stroke-width 180ms ease, opacity 180ms ease;
}
.map-cell:hover .map-tile-fill { filter: brightness(1.16) saturate(1.08); }
.map-cell:hover .map-tile { stroke: rgba(238, 255, 250, 0.72); }
.map-cell--current .map-tile-fill { filter: brightness(1.22) saturate(1.12); }
.map-cell--current .map-tile { stroke: rgba(255, 229, 157, 0.9); stroke-width: 2; }
.map-cell--visited .map-tile { stroke: rgba(231, 255, 247, 0.74); stroke-width: 1.5; }

.axis-line {
  fill: none;
  stroke-width: 2.5;
  vector-effect: non-scaling-stroke;
  stroke-linecap: round;
  opacity: 0.72;
  pointer-events: none;
}
.axis-line--salt { stroke: #63d68a; }
.axis-line--heat { stroke: #ef6a63; }
.axis-arrow-head--salt { fill: #63d68a; }
.axis-arrow-head--heat { fill: #ef6a63; }

.quadrant-label {
  fill: #d7c39a;
  font-family: ui-monospace, "SFMono-Regular", Consolas, "Noto Sans SC", "Microsoft YaHei", sans-serif;
  font-size: clamp(17px, 1.35vw, 21px);
  font-weight: 900;
  letter-spacing: 0.06em;
  paint-order: stroke;
  stroke: rgba(72, 58, 43, 0.82);
  stroke-linejoin: round;
  stroke-width: 1.6px;
  text-shadow: 1px 1px 0 rgba(55, 43, 30, 0.55);
  pointer-events: none;
}
.quadrant-label--view { fill: #9fb8b0; }
.quadrant-label--critique { fill: #b7c2c6; }
.quadrant-label--emotion { fill: #c58e78; }
.quadrant-label--wasteland { fill: #c7aa78; }

.kanshan-layer {
  transition: transform 650ms cubic-bezier(0.22, 0.78, 0.28, 1);
}
.kanshan-layer--moving { animation: kanshan-bob 650ms ease-in-out; }
.kanshan-image {
  display: block;
  border-radius: 50%;
}

@keyframes kanshan-bob {
  0%, 100% { opacity: 1; }
  45% { opacity: 0.8; }
}

/* 每局文章生成感叹号气泡 */
.article-bubble-bg {
  fill: #ffeaa7;
  stroke: #d4a017;
  stroke-width: 2;
  animation: article-bubble-bounce 1.2s ease-in-out infinite;
}
.article-bubble-icon {
  fill: #5d4037;
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: 18px;
  font-weight: 900;
}
@keyframes article-bubble-bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}
</style>
