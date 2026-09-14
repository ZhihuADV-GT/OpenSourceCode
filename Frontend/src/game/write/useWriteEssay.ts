/**
 * Write 模块 —— 最终回答生成、缓存和打字机效果。
 *
 * 生成结果按当前完成旅程的 runId 缓存；重新打开或刷新不会重复请求，
 * 明确重试才会再次调用 AI。网络失败只显示保底文案，不改变游戏状态。
 */

import { computed, ref } from 'vue'
import type { FinalJourneySummary, WriteEssayRequest, WriteEssayResult } from './types'
import { generateEssay } from './essayGenerator'

const STORAGE_KEY = 'game-final-essay-v1'

interface PersistedEssay {
  runId: string
  title: string
  content: string
  generatedAt: number
}

const essayResult = ref<WriteEssayResult | null>(null)
const displayedText = ref('')
const isWriting = ref(false)
const isGenerating = ref(false)
const generationError = ref('')
const currentCharIndex = ref(0)
const activeRunId = ref<string | null>(null)
let typingTimer: ReturnType<typeof setTimeout> | null = null
let generationToken = 0

function clearTimer() {
  if (typingTimer) {
    clearTimeout(typingTimer)
    typingTimer = null
  }
}

function readPersistedEssay(runId: string): WriteEssayResult | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null) return null
    const record = parsed as Partial<PersistedEssay>
    if (
      record.runId !== runId
      || typeof record.title !== 'string'
      || typeof record.content !== 'string'
      || !record.content
      || typeof record.generatedAt !== 'number'
    ) return null
    return {
      title: record.title,
      content: record.content,
      isAIGenerated: true,
      generatedAt: record.generatedAt,
    }
  } catch {
    return null
  }
}

function persistEssay(runId: string, result: WriteEssayResult) {
  if (!result.isAIGenerated || !result.generatedAt) return
  const value: PersistedEssay = {
    runId,
    title: result.title,
    content: result.content,
    generatedAt: result.generatedAt,
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
  } catch {
    // The in-memory result remains available when browser storage is unavailable.
  }
}

function startTyping() {
  clearTimer()
  displayedText.value = ''
  currentCharIndex.value = 0
  isWriting.value = true
  typeNextChar()
}

function typeNextChar() {
  if (!essayResult.value || !isWriting.value) return

  const content = essayResult.value.content
  if (currentCharIndex.value < content.length) {
    displayedText.value = content.slice(0, currentCharIndex.value + 1)
    currentCharIndex.value++
    typingTimer = setTimeout(typeNextChar, 28)
  } else {
    isWriting.value = false
    typingTimer = null
  }
}

function applyResult(result: WriteEssayResult, runId: string) {
  essayResult.value = result
  activeRunId.value = runId
  isGenerating.value = false
  generationError.value = result.isAIGenerated ? '' : '看山暂时没能整理好这篇回答，先为你保留一份旅途手记。'
  if (result.isAIGenerated) persistEssay(runId, result)
  startTyping()
}

export function useWriteEssay() {
  const isComplete = computed(() => {
    if (!essayResult.value || isGenerating.value) return false
    return currentCharIndex.value >= essayResult.value.content.length
  })

  const title = computed(() => essayResult.value?.title ?? '')
  const fullContent = computed(() => essayResult.value?.content ?? '')

  async function startWriting(req: WriteEssayRequest, force = false): Promise<void> {
    const runId = req.summary.runId
    if (!force && activeRunId.value === runId && (essayResult.value || isGenerating.value)) return

    clearTimer()
    generationToken += 1
    const token = generationToken
    activeRunId.value = runId
    generationError.value = ''

    if (!force) {
      const cached = readPersistedEssay(runId)
      if (cached) {
        applyResult(cached, runId)
        return
      }
    }

    essayResult.value = null
    displayedText.value = ''
    currentCharIndex.value = 0
    isWriting.value = false
    isGenerating.value = true

    const result = await generateEssay(req)
    if (token !== generationToken) return
    applyResult(result, runId)
  }

  async function ensureWriting(summary: FinalJourneySummary): Promise<void> {
    await startWriting({ summary })
  }

  function skipWriting() {
    clearTimer()
    if (essayResult.value) {
      displayedText.value = essayResult.value.content
      currentCharIndex.value = essayResult.value.content.length
    }
    isWriting.value = false
  }

  function resetWriting() {
    clearTimer()
    generationToken += 1
    essayResult.value = null
    displayedText.value = ''
    currentCharIndex.value = 0
    isWriting.value = false
    isGenerating.value = false
    generationError.value = ''
    activeRunId.value = null
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      // Ignore unavailable browser storage.
    }
  }

  return {
    startWriting,
    ensureWriting,
    skipWriting,
    resetWriting,
    displayedText,
    title,
    fullContent,
    isWriting,
    isGenerating,
    generationError,
    isComplete,
    isAIGenerated: computed(() => essayResult.value?.isAIGenerated ?? false),
  }
}
