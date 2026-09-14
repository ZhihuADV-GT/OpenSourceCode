export {}

declare global {
  interface Window {
    __achievementDebug?: () => {
      stats: Record<string, unknown>
      summary: {
        collected: Record<string, number>
        used: Record<string, number>
        kanshanInteractions: number
      }
      states: Array<Record<string, unknown>>
      hasUnseenUnlocks: boolean
    }
  }
}
