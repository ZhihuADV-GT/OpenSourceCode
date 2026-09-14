<script setup lang="ts">
import type { AchievementDefinition } from '../../types/achievement'
import { achievementIconFor } from '../../data/achievementIcons'

defineProps<{
  achievement: AchievementDefinition | null
  visible: boolean
}>()
</script>

<template>
  <Transition name="achievement-unlock-toast">
    <aside
      v-if="visible && achievement"
      class="achievement-unlock-toast"
      :data-achievement-id="achievement.id"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <div class="achievement-unlock-toast__stamp" aria-hidden="true">
        <img
          v-if="achievementIconFor(achievement.id, 'UNLOCKED')"
          :src="achievementIconFor(achievement.id, 'UNLOCKED') ?? undefined"
          alt=""
        />
        <span v-else>✦</span>
      </div>
      <div class="achievement-unlock-toast__copy">
        <p class="achievement-unlock-toast__eyebrow">新的旅行见闻！</p>
        <strong class="achievement-unlock-toast__name">{{ achievement.name }}</strong>
        <p class="achievement-unlock-toast__description">{{ achievement.description }}</p>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.achievement-unlock-toast {
  position: fixed;
  z-index: 300;
  top: clamp(18px, 4vh, 42px);
  right: clamp(18px, 3vw, 44px);
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  width: min(340px, calc(100vw - 36px));
  padding: 14px 16px 15px 14px;
  overflow: hidden;
  pointer-events: none;
  color: #4b3a28;
  background:
    linear-gradient(135deg, rgba(255, 250, 226, 0.98), rgba(241, 226, 181, 0.98)),
    #f8edca;
  border: 2px solid #9d7748;
  border-radius: 11px 5px 11px 5px;
  box-shadow: 0 12px 24px rgba(30, 22, 11, 0.18), 4px 5px 0 rgba(66, 50, 31, 0.16), inset 0 0 0 1px rgba(255, 255, 255, 0.64);
}

.achievement-unlock-toast::after {
  position: absolute;
  inset: 5px;
  border: 1px solid rgba(157, 119, 72, 0.28);
  pointer-events: none;
  content: '';
}

.achievement-unlock-toast__stamp {
  position: relative;
  z-index: 1;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  color: #7a5b31;
  font-size: 1.35rem;
  background: rgba(222, 191, 112, 0.45);
  border: 1px solid rgba(122, 91, 49, 0.55);
  border-radius: 50%;
  box-shadow: inset 0 0 0 3px rgba(255, 248, 212, 0.56);
}

.achievement-unlock-toast__stamp img { display: block; width: 46px; height: 46px; object-fit: contain; }

.achievement-unlock-toast__copy {
  position: relative;
  z-index: 1;
  min-width: 0;
}

.achievement-unlock-toast__eyebrow {
  margin: 0 0 3px;
  color: #7b6747;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.12em;
}

.achievement-unlock-toast__name {
  display: block;
  overflow: hidden;
  color: #42311f;
  font-size: 1rem;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.achievement-unlock-toast__description {
  margin: 3px 0 0;
  color: #6c5638;
  font-size: 0.72rem;
  line-height: 1.45;
}

.achievement-unlock-toast-enter-active,
.achievement-unlock-toast-leave-active {
  transition: opacity 280ms ease, transform 280ms cubic-bezier(0.2, 0.8, 0.2, 1);
}

.achievement-unlock-toast-enter-from,
.achievement-unlock-toast-leave-to {
  opacity: 0;
  transform: translateX(28px);
}
</style>
