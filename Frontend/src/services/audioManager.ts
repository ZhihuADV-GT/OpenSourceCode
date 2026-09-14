export type BgmOptions = {
  loop?: boolean
  volume?: number
  autoplayFallback?: boolean
  /** 当自动播放被浏览器拦截后，用户首次交互触发重试成功时回调 */
  onAutoplayUnblocked?: () => void
}

export type SfxOptions = {
  volume?: number
}

export const AUDIO_VOLUME = {
  landingBgm: 0.20,
  mapBgm: 0.20,
  readingBgm: 0.14,
  settlementBgm: 0.16,
  achievementBgm: 0.20,
  cardFlowDrop: 0.45,
} as const

let activeBgm: HTMLAudioElement | null = null
let activeBgmSource: string | null = null
let clearAutoplayFallback: (() => void) | null = null

function clampVolume(volume: number | undefined, fallback: number) {
  const value = volume ?? fallback
  return Math.min(1, Math.max(0, value))
}

function clearPendingAutoplayFallback() {
  clearAutoplayFallback?.()
  clearAutoplayFallback = null
}

function registerAutoplayFallback(audio: HTMLAudioElement, onUnblocked?: () => void) {
  if (typeof window === 'undefined') return

  clearPendingAutoplayFallback()

  const retry = () => {
    clearPendingAutoplayFallback()
    if (activeBgm !== audio) return
    void audio.play().then(() => {
      onUnblocked?.()
    }).catch(() => {
      // Autoplay can still be blocked after the first interaction. Audio is optional.
    })
  }

  const events: Array<keyof WindowEventMap> = ['pointerdown', 'keydown']
  events.forEach(event => window.addEventListener(event, retry, { once: true, passive: true }))
  clearAutoplayFallback = () => {
    events.forEach(event => window.removeEventListener(event, retry))
  }
}

export async function playBgm(source: string, options: BgmOptions = {}) {
  if (typeof window === 'undefined') return false

  const volume = clampVolume(options.volume, 0.3)
  if (activeBgm && activeBgmSource === source) {
    activeBgm.loop = options.loop ?? true
    activeBgm.volume = volume
    if (activeBgm.paused) {
      try {
        await activeBgm.play()
        clearPendingAutoplayFallback()
        return true
      } catch {
        if (options.autoplayFallback !== false) registerAutoplayFallback(activeBgm, options.onAutoplayUnblocked)
        return false
      }
    }
    return true
  }

  stopActiveBgm()

  const audio = new window.Audio(source)
  audio.preload = 'auto'
  audio.loop = options.loop ?? true
  audio.volume = volume
  activeBgm = audio
  activeBgmSource = source

  try {
    await audio.play()
    clearPendingAutoplayFallback()
    return true
  } catch {
    if (activeBgm === audio && options.autoplayFallback !== false) registerAutoplayFallback(audio, options.onAutoplayUnblocked)
    return false
  }
}

function stopActiveBgm() {
  clearPendingAutoplayFallback()

  const audio = activeBgm
  activeBgm = null
  activeBgmSource = null
  if (!audio) return

  audio.pause()
  audio.currentTime = 0
}

export function stopBgm(source?: string) {
  if (source && activeBgmSource !== source) return
  stopActiveBgm()
}

export function playSfx(source: string, options: SfxOptions = {}) {
  if (typeof window === 'undefined') return

  const audio = new window.Audio(source)
  audio.preload = 'auto'
  audio.volume = clampVolume(options.volume, 0.45)
  void audio.play().catch(() => {
    // Sound effects are optional and may be blocked before the first interaction.
  })
}
