<script setup lang="ts">
import { computed } from 'vue'
import { useGameRuntimeStore } from '../../stores/gameRuntime'
import { useGameStore } from '../../stores/game'

const runtimeStore = useGameRuntimeStore()
const gameStore = useGameStore()

const answererValueLabel = computed(() => String(gameStore.answererValue) + '%')
const answererProgressPercent = computed(() => Math.min(Math.max(gameStore.answererValue, 0), 100))
const roundLabel = computed(() => 'ROUND ' + gameStore.currentRound + ' / ' + gameStore.totalRounds)
const understandingPercent = computed(() => {
  const target = runtimeStore.understandingTarget
  if (target <= 0) return 0
  return Math.min(100, Math.max(0, Math.round(
    runtimeStore.understandingCurrent / target * 100,
  )))
})
</script>

<template>
  <section class="article-metrics-hud hud-pixel-panel" aria-label="文章实时指标">
    <div class="article-metrics-row article-metrics-row--primary metrics-answerer">
      <div class="article-metrics-label-group">
        <span class="article-metric-label">答主值</span>
        <span class="article-metric-english">AUTHOR VALUE</span>
      </div>
      <div
        class="article-metric-progress"
        role="progressbar"
        aria-label="答主值"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-valuenow="gameStore.answererValue"
      >
        <span class="article-metric-progress-fill" :style="{ width: `${answererProgressPercent}%` }" />
      </div>
      <strong class="article-metric-value article-metric-value--answerer">{{ answererValueLabel }}</strong>
    </div>

    <div class="article-metrics-row article-metrics-row--secondary">
      <div class="article-metric-inline article-metric-inline--round">
        <strong class="article-metric-value article-metric-value--round">{{ roundLabel }}</strong>
      </div>
      <div class="article-metric-inline article-metric-inline--understanding">
        <span class="article-metric-label">理解度</span>
        <strong class="article-metric-value article-metric-value--understanding">
          {{ understandingPercent }}%
        </strong>
      </div>
    </div>
  </section>
</template>
