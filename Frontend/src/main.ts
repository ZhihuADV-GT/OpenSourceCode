import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { useAchievementStore as getAchievementStore } from './stores/achievements'
import './style.css'

const pinia = createPinia()

if (import.meta.env.DEV) {
  const achievementStore = getAchievementStore(pinia)
  achievementStore.evaluateAchievements()
  window.__achievementDebug = () => ({
    stats: {
      ...achievementStore.stats,
      completedRoundNumbers: [...achievementStore.stats.completedRoundNumbers],
      usedMaterialInstanceIds: [...achievementStore.usedMaterialInstanceIds],
      countedKanshanInteractionIds: [...achievementStore.countedKanshanInteractionIds],
    },
    summary: {
      collected: {
        rhetoric: achievementStore.stats.rhetoricCollectedTotal,
        emotion: achievementStore.stats.emotionCollectedTotal,
        viewpoint: achievementStore.stats.viewpointCollectedTotal,
        loophole: achievementStore.stats.loopholeCollectedTotal,
      },
      used: {
        rhetoric: achievementStore.stats.rhetoricUsedTotal,
        emotion: achievementStore.stats.emotionUsedTotal,
        viewpoint: achievementStore.stats.viewpointUsedTotal,
        loophole: achievementStore.stats.loopholeUsedTotal,
      },
      kanshanInteractions: achievementStore.stats.kanshanInteractionTotal,
    },
    states: achievementStore.achievementStates.map(state => ({ ...state })),
    hasUnseenUnlocks: achievementStore.hasUnseenUnlocks,
  })
}

createApp(App)
  .use(pinia)
  .use(router)
  .mount('#app')
