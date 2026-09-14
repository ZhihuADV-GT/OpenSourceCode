<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
// [art-assets disabled]
const landingBackground = ''
const landingMap = ''
const landingKanshan = ''
const landingBgm = ''
import { AUDIO_VOLUME, playBgm, stopBgm } from '../services/audioManager'
import { useGameStore } from '../stores/game'
// [开源版] 知乎 OAuth 相关服务已注释，本地部署无需授权即可游玩
// import {
//   fetchZhihuAuthStatus,
//   logoutZhihu,
//   startZhihuLogin,
//   type ZhihuPublicProfile,
// } from '../services/zhihuAuthService'

const router = useRouter()
const route = useRoute()
const gameStore = useGameStore()
const isLeaving = ref(false)
const authNoticeVisible = ref(false)
const authNoticeMessage = ref('')
// [开源版] 开源版本无需知乎授权，以下认证状态变量已停用
// const zhihuAuthenticated = ref(false)
// const zhihuUser = ref<ZhihuPublicProfile | null>(null)
// const zhihuAuthLoading = ref(false)
const showNewJourneyConfirm = ref(false)
const landingMusicEnabled = ref(false)
let landingActive = false

const hasProgress = computed(() => (
  gameStore.currentRound > 1
    || gameStore.moveHistory.length > 0
    || gameStore.visitedQuadrants.length > 0
    || gameStore.roundVectors.some(vector => vector !== null)
    || Math.hypot(gameStore.totalVector[0], gameStore.totalVector[1]) > 0
    || gameStore.screen !== 'map'
))

const hasUnfinishedJourney = computed(() => hasProgress.value && !gameStore.isGameOver)
const isCompletedJourney = computed(() => gameStore.isGameOver)
const primaryActionLabel = computed(() => {
  if (hasUnfinishedJourney.value) return '继续旅程'
  return '开始旅程'
})
const journeyStatus = computed(() => {
  if (hasUnfinishedJourney.value) return `第 ${gameStore.currentRound} / ${gameStore.totalRounds} 段旅程仍在地图上`
  if (isCompletedJourney.value) return '上一段旅程已经抵达终点'
  return '六段旅程 · 四种区域 · 一张属于你的观点地图'
})

function enterGame() {
  if (isLeaving.value) return
  isLeaving.value = true

  if (isCompletedJourney.value) {
    void window.setTimeout(() => {
      void router.push({ name: 'game', query: { start: 'new' } })
    }, 360)
    return
  }

  gameStore.normalizeLandingEntry()

  void window.setTimeout(() => {
    void router.push({ name: 'game' })
  }, 360)
}

function openNewJourneyConfirm() {
  showNewJourneyConfirm.value = true
}

function cancelNewJourney() {
  showNewJourneyConfirm.value = false
}

function startNewJourney() {
  if (isLeaving.value) return
  isLeaving.value = true
  showNewJourneyConfirm.value = false

  void window.setTimeout(() => {
    void router.push({ name: 'game', query: { start: 'new' } })
  }, 360)
}

// [开源版] 知乎授权处理函数已注释，如需恢复请取消注释并恢复 zhihuAuthService 导入
// async function handleAuthorizationEntry() {
//   if (zhihuAuthLoading.value) return
//
//   if (zhihuAuthenticated.value) {
//     zhihuAuthLoading.value = true
//     try {
//       await logoutZhihu()
//       zhihuAuthenticated.value = false
//       zhihuUser.value = null
//       authNoticeVisible.value = true
//       authNoticeMessage.value = '已退出知乎登录。'
//     } catch {
//       authNoticeVisible.value = true
//       authNoticeMessage.value = '暂时无法退出知乎登录，请稍后重试。'
//     } finally {
//       zhihuAuthLoading.value = false
//     }
//     return
//   }
//
//   zhihuAuthLoading.value = true
//   authNoticeVisible.value = true
//   authNoticeMessage.value = '正在跳转知乎授权页…'
//   startZhihuLogin()
// }
//
// async function refreshZhihuAuthStatus() {
//   try {
//     const status = await fetchZhihuAuthStatus()
//     zhihuAuthenticated.value = status.authenticated
//     zhihuUser.value = status.authenticated ? status.user : null
//     if (!status.configured) {
//       authNoticeVisible.value = true
//       authNoticeMessage.value = '知乎 OAuth 尚未配置，请先在后端 Secret Store 配置黑客松凭证。'
//     }
//   } catch {
//     zhihuAuthenticated.value = false
//     zhihuUser.value = null
//     authNoticeVisible.value = true
//     authNoticeMessage.value = '暂时无法检查知乎登录状态，请确认后端服务已启动。'
//   }
// }

async function toggleLandingAudio() {
  if (landingMusicEnabled.value) {
    stopLandingBgm()
    return
  }

  landingMusicEnabled.value = await playBgm(landingBgm, {
    loop: true,
    volume: AUDIO_VOLUME.landingBgm,
    autoplayFallback: false,
  })
}

function stopLandingBgm() {
  landingActive = false
  landingMusicEnabled.value = false
  stopBgm(landingBgm)
}

onMounted(() => {
  landingActive = true
  // [开源版] 知乎授权回调处理已注释
  // if (route.query.zhihu_auth === 'success') {
  //   authNoticeVisible.value = true
  //   authNoticeMessage.value = '知乎授权成功，服务端会话已建立。'
  //   void router.replace({ name: 'landing', query: {} })
  // } else if (route.query.auth_required === '1') {
  //   authNoticeVisible.value = true
  //   authNoticeMessage.value = route.query.backend_error === '1'
  //     ? '后端服务不可用，请先启动后端再登录。'
  //     : '进入游戏前需要先完成知乎授权登录。'
  //   void router.replace({ name: 'landing', query: {} })
  // }
  // void refreshZhihuAuthStatus()
  void playBgm(landingBgm, {
    loop: true,
    volume: AUDIO_VOLUME.landingBgm,
    onAutoplayUnblocked: () => {
      if (landingActive) landingMusicEnabled.value = true
    },
  }).then(started => {
    if (landingActive) landingMusicEnabled.value = started
  })
})

onBeforeRouteLeave(stopLandingBgm)
onBeforeUnmount(stopLandingBgm)
</script>

<template>
  <main class="landing-view" :class="{ 'landing-view--leaving': isLeaving }">
    <div class="landing-backdrop" aria-hidden="true">
      <img class="landing-backdrop__image" :src="landingBackground" alt="" />
      <div class="landing-backdrop__veil" />
      <div class="landing-map-decor">
        <img :src="landingMap" alt="" />
      </div>
    </div>

    <header class="landing-header">
      <span class="landing-mark" aria-hidden="true">知</span>
      <span class="landing-header__copy">旅行看山 · 答主之路</span>
      <span class="landing-header__edition">MAP JOURNEY 01</span>
      <button
        class="landing-audio-toggle"
        type="button"
        :aria-label="landingMusicEnabled ? '关闭声音' : '开启声音'"
        @click="toggleLandingAudio"
      >
        <span aria-hidden="true">{{ landingMusicEnabled ? '🔊' : '🔇' }}</span>
        <small>{{ landingMusicEnabled ? '声音开' : '声音关' }}</small>
      </button>
    </header>

    <section class="landing-content" aria-labelledby="landing-title">
      <div class="landing-copy">
        <p class="landing-kicker">TRAVEL KANSHAN · THE ANSWERER'S ROAD</p>
        <h1 id="landing-title" aria-label="旅行看山：答主之路"><span>旅行看山</span><i aria-hidden="true">：</i><strong>答主之路</strong></h1>
        <p class="landing-subtitle">在地图上走出属于你的回答</p>
        <div class="landing-rule" aria-hidden="true"><span /><b>✦</b><span /></div>
        <p class="landing-intro">收集见闻，组合答案，让每一次选择<br class="landing-intro__break" />成为地图上真实走过的一步。</p>

        <div class="landing-actions">
          <!-- [开源版] 移除 v-if="zhihuAuthenticated" 限制，本地部署无需知乎授权即可游玩 -->
          <button
            class="landing-primary"
            type="button"
            @click="enterGame"
          >
            <span>{{ primaryActionLabel }}</span>
            <small aria-hidden="true">→</small>
          </button>
          <button
            v-if="hasUnfinishedJourney"
            class="landing-new-journey"
            type="button"
            @click="openNewJourneyConfirm"
          >
            <span>开始新旅程</span>
            <small aria-hidden="true"></small>
          </button>
          <!-- [开源版] 知乎授权登录按钮已注释，如需恢复请取消下方注释并恢复 zhihuAuthService 导入 -->
          <!-- <button class="landing-auth" type="button" :disabled="zhihuAuthLoading" @click="handleAuthorizationEntry">
            <span class="landing-auth__identity">
              <img
                v-if="zhihuAuthenticated && zhihuUser?.avatar_path"
                class="landing-auth__avatar"
                :src="zhihuUser.avatar_path"
                alt=""
              />
              <span>{{ zhihuAuthenticated ? (zhihuUser?.fullname || '知乎已登录') : zhihuAuthLoading ? '跳转中…' : '知乎授权登录' }}</span>
            </span>
            <small aria-hidden="true">{{ zhihuAuthenticated ? '退出' : '↗' }}</small>
          </button> -->
          <aside class="landing-audio-note" aria-label="音乐提示">
            <span class="landing-audio-note__pin" aria-hidden="true" />
            <span class="landing-audio-note__glyph" aria-hidden="true">♪</span>
            <span class="landing-audio-note__title">内置音乐</span>
            <span class="landing-audio-note__caption">推荐打开音响游玩</span>
          </aside>
          <p class="landing-status" aria-live="polite">{{ journeyStatus }}</p>
          <p v-if="authNoticeVisible" class="landing-auth-notice" role="status" aria-live="polite">
            {{ authNoticeMessage }}
          </p>
          <div v-if="showNewJourneyConfirm" class="landing-new-journey-confirm" role="dialog" aria-modal="false" aria-labelledby="new-journey-title">
            <p id="new-journey-title">要开始一段新的旅程吗？</p>
            <p>当前未完成的旅程记录将被重置。</p>
            <div class="landing-new-journey-confirm__actions">
              <button type="button" @click="cancelNewJourney">取消</button>
              <button type="button" @click="startNewJourney">开始新旅程</button>
            </div>
          </div>
        </div>
      </div>

      <div class="landing-companion" aria-label="看山，等待你开始旅程">
        <img :src="landingKanshan" alt="看山" />
        <span class="landing-companion__caption">看山在这里等你</span>
      </div>
    </section>

    <footer class="landing-footer">
      <span>OCEAN · GLACIER · VOLCANO · DESERT</span>
      <span class="landing-footer__dot" aria-hidden="true">·</span>
      <span>LOCAL JOURNEY / v1.0</span>
    </footer>
  </main>
</template>

<style scoped>
.landing-view {
  position: fixed;
  z-index: 0;
  inset: 0;
  isolation: isolate;
  overflow: hidden;
  min-width: 320px;
  height: 100dvh;
  min-height: 560px;
  color: #4b3828;
  background: #f7f1df;
  opacity: 1;
  transition: opacity 420ms ease, transform 420ms ease;
}
.landing-view--leaving { opacity: 0; transform: scale(1.018); }
.landing-backdrop { position: absolute; z-index: -2; inset: 0; overflow: hidden; background: #f7f1df; pointer-events: none; }
.landing-backdrop__image {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
}
.landing-backdrop__veil {
  position: absolute;
  z-index: 1;
  inset: 0;
  background:
    linear-gradient(90deg, rgba(248, 239, 214, 0.82) 0%, rgba(248, 239, 214, 0.58) 28%, rgba(248, 239, 214, 0.12) 65%, rgba(248, 239, 214, 0.2) 100%),
    linear-gradient(180deg, rgba(255, 253, 239, 0.08) 0%, rgba(255, 249, 226, 0.04) 52%, rgba(221, 198, 151, 0.18) 100%);
}
.landing-map-decor {
  position: absolute;
  z-index: 2;
  right: -2vw;
  bottom: 13vh;
  width: clamp(460px, 58vw, 880px);
  aspect-ratio: 4 / 3;
  opacity: 0.24;
  filter: blur(4px) saturate(0.86);
  mix-blend-mode: multiply;
  -webkit-mask-image: radial-gradient(ellipse at center, #000 42%, rgba(0, 0, 0, 0.72) 68%, transparent 100%);
  mask-image: radial-gradient(ellipse at center, #000 42%, rgba(0, 0, 0, 0.72) 68%, transparent 100%);
  transform: rotate(-4deg);
}
.landing-map-decor img { display: block; width: 100%; height: 100%; object-fit: cover; }
.landing-header, .landing-footer { position: absolute; z-index: 10; display: flex; align-items: center; }
.landing-header { top: clamp(22px, 5vh, 46px); left: clamp(24px, 5vw, 72px); gap: 10px; color: rgba(75, 56, 40, 0.78); }
.landing-mark { display: grid; width: 27px; height: 27px; place-items: center; border: 1px solid rgba(104, 78, 49, 0.7); color: #5e4733; font: 700 0.82rem/1 serif; }
.landing-header__copy { font-size: 0.68rem; letter-spacing: 0.14em; }
.landing-header__edition { margin-left: 12px; color: rgba(91, 72, 49, 0.52); font: 0.57rem ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: 0.17em; }
.landing-audio-toggle { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-width: 92px; min-height: 40px; margin-left: 12px; border: 1px solid rgba(104, 78, 49, 0.34); border-radius: 999px; padding: 7px 12px; background: rgba(255, 250, 232, 0.52); color: rgba(75, 56, 40, 0.72); font-size: 0.9rem; cursor: pointer; transition: background 140ms ease, border-color 140ms ease, transform 140ms ease; }
.landing-audio-toggle > span { font-size: 1.08rem; line-height: 1; }
.landing-audio-toggle small { font-size: 0.6rem; letter-spacing: 0.08em; }
.landing-audio-toggle:hover, .landing-audio-toggle:focus-visible { border-color: rgba(104, 78, 49, 0.62); background: rgba(255, 253, 243, 0.78); transform: translateY(-1px); }
.landing-content { position: relative; z-index: 8; display: grid; grid-template-columns: minmax(360px, 540px) minmax(230px, 330px); align-items: center; justify-content: center; gap: clamp(20px, 7vw, 110px); width: min(1180px, calc(100% - 96px)); height: 100%; margin: 0 auto; padding: 50px 0 30px; transform: translateX(-5vw); }
.landing-copy { position: relative; z-index: 4; padding: clamp(18px, 2.6vw, 32px); border-radius: 18px 6px 18px 6px; background: linear-gradient(90deg, rgba(248, 239, 214, 0.88), rgba(248, 239, 214, 0.62) 76%, rgba(248, 239, 214, 0)); box-shadow: 0 16px 30px rgba(111, 84, 47, 0.08); text-shadow: none; }
.landing-kicker { margin: 0 0 22px; color: #8a7041; font: 700 0.62rem/1 ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: 0.28em; }
.landing-copy h1 { display: flex; align-items: center; gap: clamp(6px, 1vw, 13px); margin: 0; color: #4c3828; font: 500 clamp(2.5rem, 5.2vw, 5.15rem)/0.98 Georgia, "Times New Roman", serif; letter-spacing: -0.07em; white-space: nowrap; }
.landing-copy h1 span { color: #4c3828; }
.landing-copy h1 i { color: #6e9a8b; font: italic 400 0.4em Georgia, serif; letter-spacing: 0; }
.landing-copy h1 strong { color: #aa7b42; font-weight: 500; }
.landing-subtitle { margin: 17px 0 0; color: #5f745f; font: 400 clamp(1.1rem, 2vw, 1.45rem)/1.4 serif; letter-spacing: 0.16em; }
.landing-rule { display: flex; align-items: center; gap: 12px; width: 230px; margin: 22px 0 18px; color: #ae8148; }
.landing-rule span { display: block; width: 82px; height: 1px; background: linear-gradient(90deg, rgba(174, 129, 72, 0), rgba(174, 129, 72, 0.78)); }
.landing-rule span:last-child { background: linear-gradient(90deg, rgba(174, 129, 72, 0.78), rgba(174, 129, 72, 0)); }
.landing-rule b { font-size: 0.65rem; font-weight: 400; }
.landing-intro { margin: 0; color: rgba(75, 56, 40, 0.74); font-size: 0.83rem; line-height: 1.85; letter-spacing: 0.08em; }
.landing-actions { position: relative; display: flex; flex-direction: column; align-items: flex-start; width: 272px; margin-top: 31px; }
.landing-primary { display: flex; align-items: center; justify-content: center; cursor: pointer; }
.landing-primary { justify-content: space-between; width: 272px; min-height: 55px; border: 1px solid rgba(184, 143, 75, 0.8); border-radius: 7px 3px 7px 3px; padding: 0 19px 0 24px; background: rgba(255, 250, 232, 0.94); box-shadow: 0 7px 20px rgba(111, 84, 47, 0.17), inset 0 1px 0 rgba(255, 255, 255, 0.82); color: #5b4630; font-size: 0.94rem; font-weight: 800; letter-spacing: 0.21em; transition: background 160ms ease, color 160ms ease, transform 160ms ease, box-shadow 160ms ease; }
.landing-primary small { color: #aa7b42; font-size: 1.25rem; font-weight: 400; letter-spacing: 0; transition: transform 160ms ease; }
.landing-primary:hover, .landing-primary:focus-visible { background: #fffdf3; color: #4d3a29; box-shadow: 0 10px 25px rgba(111, 84, 47, 0.23); transform: translateY(-2px); }
.landing-primary:hover small, .landing-primary:focus-visible small { transform: translateX(4px); }
.landing-primary:active { transform: translateY(1px); }
.landing-new-journey {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 272px;
  min-height: 46px;
  margin-top: 9px;
  border: 1px solid rgba(184, 164, 119, 0.8);
  border-radius: 7px 3px 7px 3px;
  padding: 0 16px 0 19px;
  background: rgba(255, 250, 232, 0.8);
  box-shadow: 0 5px 15px rgba(111, 84, 47, 0.14), inset 0 1px 0 rgba(255, 255, 255, 0.62);
  color: #5b6046;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  cursor: pointer;
  transition: background 160ms ease, transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
}
.landing-new-journey small { color: #aa7b42; font-size: 1rem; letter-spacing: 0; }
.landing-new-journey:hover, .landing-new-journey:focus-visible {
  border-color: rgba(123, 157, 139, 0.9);
  background: #fffdf3;
  box-shadow: 0 8px 20px rgba(111, 84, 47, 0.2);
  transform: translateY(-2px);
}
.landing-new-journey:active { transform: translateY(1px); }
.landing-auth {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 272px;
  min-height: 42px;
  margin-top: 8px;
  border: 1px solid rgba(143, 161, 169, 0.62);
  border-radius: 7px 3px 7px 3px;
  padding: 0 16px 0 19px;
  background: rgba(255, 250, 232, 0.68);
  box-shadow: 0 4px 13px rgba(111, 84, 47, 0.13), inset 0 1px 0 rgba(255, 255, 255, 0.58);
  color: #536976;
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  cursor: pointer;
  transition: background 160ms ease, transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
}
.landing-auth small { color: #5d8aa2; font-size: 0.95rem; letter-spacing: 0; }
.landing-auth__identity { display: flex; align-items: center; min-width: 0; gap: 8px; }
.landing-auth__identity > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.landing-auth__avatar { width: 24px; height: 24px; flex: 0 0 24px; border-radius: 50%; object-fit: cover; }
.landing-auth:hover, .landing-auth:focus-visible {
  border-color: rgba(93, 138, 162, 0.72);
  background: #fffdf3;
  box-shadow: 0 7px 18px rgba(111, 84, 47, 0.18);
  transform: translateY(-2px);
}
.landing-auth:active { transform: translateY(1px); }
.landing-status { min-height: 16px; margin: 14px 0 0; color: rgba(75, 56, 40, 0.62); font-size: 0.64rem; letter-spacing: 0.05em; }
.landing-auth-notice { margin: 8px 0 0; color: #8a7041; font-size: 0.68rem; line-height: 1.4; letter-spacing: 0.04em; }
.landing-new-journey-confirm {
  width: 272px;
  margin-top: 12px;
  border: 1px solid rgba(184, 164, 119, 0.8);
  border-radius: 9px 4px 9px 4px;
  padding: 12px 14px 13px;
  background: rgba(255, 250, 232, 0.96);
  box-shadow: 0 8px 22px rgba(111, 84, 47, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.68);
  color: #5b4630;
  text-shadow: none;
}
.landing-new-journey-confirm p { margin: 0; font-size: 0.68rem; line-height: 1.5; }
.landing-new-journey-confirm p + p { margin-top: 3px; color: #856c4b; }
.landing-new-journey-confirm__actions { display: flex; justify-content: flex-end; gap: 7px; margin-top: 10px; }
.landing-new-journey-confirm__actions button {
  border: 1px solid rgba(152, 119, 72, 0.5);
  border-radius: 6px 3px 6px 3px;
  padding: 6px 9px;
  background: rgba(255, 250, 235, 0.76);
  color: #6a5337;
  font-size: 0.64rem;
  font-weight: 800;
  cursor: pointer;
  transition: background 140ms ease, transform 140ms ease;
}
.landing-new-journey-confirm__actions button:last-child { background: #789b82; border-color: #5f836c; color: #fff8e5; }
.landing-new-journey-confirm__actions button:hover { background: #fffaf0; transform: translateY(-1px); }
.landing-new-journey-confirm__actions button:last-child:hover { background: #6b9076; }
.landing-audio-note { position: absolute; top: -14px; left: calc(100% + 60px); box-sizing: border-box; width: 158px; height: 230px; margin: 0; border: 1px solid rgba(180, 139, 76, 0.72); border-radius: 3px 5px 4px 2px; padding: 38px 18px 34px; background: linear-gradient(135deg, rgba(255, 245, 190, 0.98), rgba(250, 224, 144, 0.96)); box-shadow: 5px 8px 13px rgba(111, 84, 47, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.68); color: #74522e; transform: rotate(3deg); transform-origin: top center; }
.landing-audio-note::after { position: absolute; top: 10px; right: 14px; left: 14px; height: 1px; background: rgba(174, 129, 72, 0.22); content: ''; }
.landing-audio-note__pin { position: absolute; top: -9px; left: 50%; width: 15px; height: 15px; border-radius: 50%; background: radial-gradient(circle at 35% 28%, #f8d8ae 0 18%, #b5654b 36%, #813e35 76%); box-shadow: 1px 2px 3px rgba(91, 55, 39, 0.28); transform: translateX(-50%); }
.landing-audio-note__pin::after { position: absolute; top: 11px; left: 6px; width: 2px; height: 8px; border-radius: 2px; background: #7b4a3c; content: ''; transform: rotate(11deg); transform-origin: top; }
.landing-audio-note__glyph { display: block; margin-bottom: 12px; color: #a86343; font: 1.3rem/1 Georgia, serif; }
.landing-audio-note__title { display: block; font-size: 0.9rem; font-weight: 800; letter-spacing: 0.12em; }
.landing-audio-note__caption { display: block; max-width: 5em; margin-top: 12px; color: rgba(116, 82, 46, 0.78); font-size: 0.72rem; letter-spacing: 0.05em; line-height: 1.65; }
.landing-companion { position: relative; align-self: end; justify-self: center; width: min(340px, 32vw); margin-bottom: 2vh; text-align: center; filter: drop-shadow(0 18px 18px rgba(86, 65, 42, 0.16)); transform: translateX(3vw); }
.landing-companion img { position: relative; z-index: 2; display: block; width: 128%; max-width: none; height: auto; margin-left: -14%; max-height: 49vh; object-fit: contain; object-position: bottom; animation: landing-companion-idle 5.6s ease-in-out infinite; }
.landing-companion__caption { display: inline-block; position: relative; z-index: 3; margin-top: -2px; color: rgba(75, 56, 40, 0.66); font-size: 0.64rem; letter-spacing: 0.17em; }
.landing-footer { right: clamp(24px, 5vw, 72px); bottom: clamp(18px, 4vh, 35px); gap: 11px; color: rgba(75, 56, 40, 0.54); font: 0.57rem ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: 0.12em; }
.landing-footer__dot { color: #ae8148; font-size: 0.9rem; }
button:focus-visible { outline: 2px solid #c08c4d; outline-offset: 4px; }
@keyframes landing-companion-idle { 0%, 100% { transform: translateY(0) rotate(0deg); } 50% { transform: translateY(-7px) rotate(-0.7deg); } }
@media (prefers-reduced-motion: reduce) {
  .landing-view { transition: none; }
  .landing-view--leaving { opacity: 0; transform: none; }
  .landing-companion img { animation: none; }
  .landing-primary, .landing-primary small, .landing-new-journey, .landing-auth, .landing-new-journey-confirm__actions button { transition: none; }
}
@media (max-width: 760px) {
  .landing-backdrop__image { object-position: 58% center; }
  .landing-map-decor { right: -18%; bottom: -5%; width: 76vw; opacity: 0.18; }
  .landing-content { grid-template-columns: minmax(280px, 430px); justify-items: center; width: min(100% - 40px, 500px); padding-top: 60px; transform: none; }
  .landing-copy { width: 100%; text-align: center; }
  .landing-kicker, .landing-rule, .landing-actions { margin-right: auto; margin-left: auto; }
  .landing-actions { align-items: center; }
  .landing-audio-note { position: relative; top: auto; left: auto; align-self: center; margin: 14px auto 0; text-align: left; }
  .landing-new-journey { width: 272px; }
  .landing-auth { width: 272px; }
  .landing-intro__break { display: none; }
  .landing-companion { position: absolute; right: 0; bottom: 5%; width: 170px; opacity: 0.86; transform: translateX(3vw); }
  .landing-companion__caption { font-size: 0.52rem; }
  .landing-footer { left: 20px; right: 20px; justify-content: center; font-size: 0.49rem; }
  .landing-footer__dot { display: none; }
  .landing-header__edition { display: none; }
}
@media (min-width: 761px) and (max-width: 960px) {
  .landing-audio-note { position: relative; top: auto; left: auto; align-self: center; margin: 14px auto 0; }
}
@media (min-width: 761px) and (max-width: 1300px) {
  .landing-map-decor { right: -1vw; bottom: 11vh; width: 54vw; }
}
@media (max-height: 680px) and (min-width: 761px) {
  .landing-content { padding-top: 40px; }
  .landing-kicker { margin-bottom: 13px; }
  .landing-rule { margin-top: 15px; margin-bottom: 11px; }
  .landing-actions { margin-top: 20px; }
  .landing-companion { width: min(250px, 27vw); }
}
</style>
