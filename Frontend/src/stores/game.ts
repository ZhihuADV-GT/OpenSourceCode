import { defineStore } from 'pinia'
import type { Article } from '../types/article'
import type { LocalSettlementResult, Settlement } from '../types/settlement'
import {
  getDirectionByVector,
  getQuadrantByMapPosition,
  getQuadrantByVector,
  getTargetPosition,
  isNonZeroVector,
  MAP_CENTER,
  MAP_SIZE,
} from '../types/mapTypes'
import type { Direction, MountainPosition, QuadrantType } from '../types/mapTypes'
import { fetchRandomAIArticle } from '../services/articleService'
import { calculateLocalSettlement } from '../services/settlementService'
import { useAchievementStore as getAchievementStore } from './achievements'
import { useMaterialStore } from './material'
import { createActor } from 'xstate'
import { createGameMachine } from '../game/machine/gameMachine'
import type { GameScreen as MachineScreen } from '../game/machine/types'
import { drawRandomEvent, executeEventEffect, resetRoundTask, getEventById, ALL_CARD_TYPES } from '../game/events'
import type { EffectContext } from '../game/events'
import { getStoryScript, getFallbackStory, AI_STORY_ID } from '../game/story'
import type { StoryScript } from '../game/story'
import { fetchAIStory } from '../services/storyService'
import type { AIStoryResult, StoryContext } from '../services/storyService'

const STORAGE_KEY = 'game-multi-round-state'
const TOTAL_ROUNDS = 6
/** 每局动态卡配额：每局（单 round）最多收集 10 张动态卡，局间重置（前端本地检查，后端不再强制） */
export const DYNAMIC_CARD_QUOTA_PER_GAME = 10

/**
 * 局间 AI 剧情的预取句柄（模块级，不进 state：既无响应式开销也不参与持久化）。
 * finalizeMovement() 进入结算界面时发起请求，continueJourney() 的 D 类事件消费。
 */
let _pendingStoryPromise: Promise<AIStoryResult | null> | null = null
let _pendingStoryRound: number | null = null
/** 玩家点「继续旅行」后最多再等 AI 剧情的时间（毫秒），超时即降级到本地 A 版 */
const STORY_RESOLVE_TIMEOUT = 12000

function clearPendingStory() {
  _pendingStoryPromise = null
  _pendingStoryRound = null
}

export type GameScreen =
  | 'map'
  | 'round-intro'
  | 'article'
  | 'map-needs-vector'
  | 'map-ready'
  | 'article-gen'
  | 'write'
  | 'random-event'
  | 'map-moving'
  | 'round-settlement'
  | 'final-settlement'

export function buildCollectionSourceKey(round: number, articleId: string, cardId: string): string {
  return `round:${round}|article:${encodeURIComponent(articleId)}|card:${encodeURIComponent(cardId)}`
}

export function buildMaterialInstanceId(round: number, articleId: string, cardId: string): string {
  return `material:${buildCollectionSourceKey(round, articleId, cardId)}`
}

const GAME_SCREENS: readonly GameScreen[] = [
  'map',
  'round-intro',
  'article',
  'map-needs-vector',
  'map-ready',
  'article-gen',
  'write',
  'random-event',
  'map-moving',
  'round-settlement',
  'final-settlement',
]

interface PersistedState {
  currentRound: number
  answererValue: number
  screen: GameScreen
  roundVector: [number, number] | null
  roundVectors: Array<[number, number] | null>
  totalVector: [number, number]
  mountainPosition: MountainPosition
  moveHistory: Array<{
    round: number
    vector: [number, number]
    fromRow: number
    fromCol: number
    toRow: number
    toCol: number
    direction: Direction
    timestamp: number
  }>
  visitedQuadrants: QuadrantType[]
  currentSkin: string
  unlockedSkins: string[]
  localSettlement: LocalSettlementResult | null
  pendingKanshanMove: boolean
  collectedSourceKeys: string[]
  committedMaterialIds: string[]
  /** 【新增】本局提交卡牌的完整数据快照，用于成就计数 */
  committedMaterialsSnapshot: any[]
  currentRandomEventId: string | null
  currentEventMessage: string
  currentStoryId: string | null
  seenArticleIds: string[]
  /** 开场 ADV 介绍是否已看过；与 tutorialSeen 解耦，两个语义各自独立持久化 */
  tutorialIntroSeen: boolean
  /** 首次聚光灯教学是否已完成；false 期间由 TutorialSpotlight 强引导接管 */
  tutorialSeen: boolean
  tutorialAutoGuideEnabled: boolean
  tutorialSkippedRoundNumbers: number[]
  tutorialDismissedContextByRound: Record<string, string[]>
  /** 本局已收集的动态卡数量（前端本地配额检查用） */
  dynamicCardsCollectedThisGame: number
}

const QUADRANTS: readonly QuadrantType[] = ['view', 'critique', 'emotion', 'wasteland']
const DIRECTIONS: readonly Direction[] = [
  'up', 'down', 'left', 'right',
  'up-left', 'up-right', 'down-left', 'down-right',
]

function defaultMountainPosition(): MountainPosition {
  return {
    row: 7,
    col: 7,
    direction: 'down',
    isMoving: false,
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function toFiniteNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function toInteger(value: unknown, fallback: number, min: number, max: number): number {
  const number = Number(value)
  if (!Number.isInteger(number)) return fallback
  return Math.max(min, Math.min(max, number))
}

function toVector(value: unknown): [number, number] | null {
  if (!Array.isArray(value) || value.length < 2) return null
  const x = toFiniteNumber(value[0], Number.NaN)
  const y = toFiniteNumber(value[1], Number.NaN)
  return Number.isFinite(x) && Number.isFinite(y) ? [x, y] : null
}

function toVectorList(value: unknown): Array<[number, number] | null> {
  if (!Array.isArray(value)) return Array.from({ length: TOTAL_ROUNDS }, () => null)
  return Array.from({ length: TOTAL_ROUNDS }, (_, index) => toVector(value[index]))
}

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return [...new Set(value.filter((item): item is string => typeof item === 'string' && item.length > 0))]
}

function isGameScreen(value: unknown): value is GameScreen {
  return typeof value === 'string' && GAME_SCREENS.includes(value as GameScreen)
}

function isQuadrant(value: unknown): value is QuadrantType {
  return typeof value === 'string' && QUADRANTS.includes(value as QuadrantType)
}

function isDirection(value: unknown): value is Direction {
  return typeof value === 'string' && DIRECTIONS.includes(value as Direction)
}

function toRoundNumberList(value: unknown): number[] {
  if (!Array.isArray(value)) return []
  return [...new Set(value
    .map(item => Number(item))
    .filter(item => Number.isInteger(item) && item >= 1 && item <= TOTAL_ROUNDS))]
}

function toDismissedContextByRound(value: unknown): Record<string, string[]> {
  if (!isRecord(value)) return {}

  const result: Record<string, string[]> = {}
  for (const roundKey of Object.keys(value)) {
    const round = Number(roundKey)
    if (!Number.isInteger(round) || round < 1 || round > TOTAL_ROUNDS) continue
    const contexts = toStringList(value[roundKey])
    if (contexts.length > 0) {
      result[String(round)] = contexts
    }
  }
  return result
}

// ══════════════════════════════════════════════════════════
//  xstate 状态机 actor（影子层，跟踪屏幕状态）
// ══════════════════════════════════════════════════════════

let _machineActor: ReturnType<typeof createActor> | null = null

function ensureMachineActor() {
  if (_machineActor) return _machineActor
  const machine = createGameMachine()
  const persisted = loadPersistedState()
  const snapshot = machine.resolveState({
    value: persisted.screen as MachineScreen,
    context: { round: persisted.currentRound },
  })
  _machineActor = createActor(machine, { snapshot })
  _machineActor.start()
  return _machineActor
}

function syncMachineScreen(screen: GameScreen, currentRound: number) {
  const actor = ensureMachineActor()
  const current = actor.getSnapshot().value as string
  if (current !== screen) {
    const machine = createGameMachine()
    const resolved = machine.resolveState({
      value: screen as MachineScreen,
      context: { round: currentRound },
    })
    actor.stop()
    _machineActor = createActor(machine, { snapshot: resolved })
    _machineActor.start()
  }
}

function loadPersistedState(): PersistedState {
  const fallback: PersistedState = {
    currentRound: 1,
    answererValue: 0,
    screen: 'map',
    roundVector: null,
    roundVectors: Array.from({ length: TOTAL_ROUNDS }, () => null),
    totalVector: [0, 0],
    mountainPosition: defaultMountainPosition(),
    moveHistory: [],
    visitedQuadrants: [],
    currentSkin: 'default',
    unlockedSkins: ['default'],
    localSettlement: null,
    pendingKanshanMove: false,
    collectedSourceKeys: [],
    committedMaterialIds: [],
    committedMaterialsSnapshot: [],  // 【新增】默认空数组
    currentRandomEventId: null,
    currentEventMessage: '',
    currentStoryId: null,
    seenArticleIds: [],
    tutorialIntroSeen: false,
    tutorialSeen: false,
    tutorialAutoGuideEnabled: true,
    tutorialSkippedRoundNumbers: [],
    tutorialDismissedContextByRound: {},
    dynamicCardsCollectedThisGame: 0,
  }

  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return fallback

    const parsed: unknown = JSON.parse(raw)
    if (!isRecord(parsed)) return fallback

    const persistedRound = Number(parsed.currentRound)
    const wasLegacyRoundSeven = Number.isInteger(persistedRound) && persistedRound > TOTAL_ROUNDS
    const currentRound = toInteger(parsed.currentRound, 1, 1, TOTAL_ROUNDS)
    const position = isRecord(parsed.mountainPosition) ? parsed.mountainPosition : {}
    const roundVector = toVector(parsed.roundVector)
    const roundVectors = toVectorList(parsed.roundVectors)
    const rawSettlement = isRecord(parsed.localSettlement) ? parsed.localSettlement : null
    const localSettlement = rawSettlement
      && typeof rawSettlement.passed === 'boolean'
      && typeof rawSettlement.rating === 'string'
      ? {
          passed: rawSettlement.passed,
          rating: rawSettlement.rating,
          projection: toFiniteNumber(rawSettlement.projection, 0),
          answererDelta: toFiniteNumber(rawSettlement.answererDelta, 0),
        }
      : null

    const restoredScreen = isGameScreen(parsed.screen) ? parsed.screen : 'map'

    return {
      currentRound,
      answererValue: Math.max(0, toFiniteNumber(parsed.answererValue, 0)),
      screen: wasLegacyRoundSeven ? 'final-settlement' : restoredScreen,
      roundVector,
      roundVectors,
      totalVector: toVector(parsed.totalVector) ?? [0, 0],
      mountainPosition: {
        row: toInteger(position.row, MAP_CENTER, 0, MAP_SIZE - 1),
        col: toInteger(position.col, MAP_CENTER, 0, MAP_SIZE - 1),
        direction: isDirection(position.direction) ? position.direction : 'down',
        isMoving: position.isMoving === true,
        targetRow: position.targetRow === undefined
          ? undefined
          : toInteger(position.targetRow, MAP_CENTER, 0, MAP_SIZE - 1),
        targetCol: position.targetCol === undefined
          ? undefined
          : toInteger(position.targetCol, MAP_CENTER, 0, MAP_SIZE - 1),
      },
      moveHistory: Array.isArray(parsed.moveHistory)
        ? parsed.moveHistory
            .filter(isRecord)
            .map(record => ({
              round: toInteger(record.round, 1, 1, TOTAL_ROUNDS),
              vector: toVector(record.vector) ?? [0, 0],
              fromRow: toInteger(record.fromRow, MAP_CENTER, 0, MAP_SIZE - 1),
              fromCol: toInteger(record.fromCol, MAP_CENTER, 0, MAP_SIZE - 1),
              toRow: toInteger(record.toRow, MAP_CENTER, 0, MAP_SIZE - 1),
              toCol: toInteger(record.toCol, MAP_CENTER, 0, MAP_SIZE - 1),
              direction: isDirection(record.direction) ? record.direction : 'down',
              timestamp: toFiniteNumber(record.timestamp, Date.now()),
            }))
            .slice(-TOTAL_ROUNDS)
        : [],
      visitedQuadrants: Array.isArray(parsed.visitedQuadrants)
        ? [...new Set(parsed.visitedQuadrants.filter(isQuadrant))]
        : [],
      currentSkin: typeof parsed.currentSkin === 'string' ? parsed.currentSkin : 'default',
      unlockedSkins: Array.isArray(parsed.unlockedSkins)
        ? [...new Set(parsed.unlockedSkins.filter((item): item is string => typeof item === 'string'))]
        : ['default'],
      localSettlement,
      pendingKanshanMove: parsed.pendingKanshanMove === true,
      collectedSourceKeys: toStringList(parsed.collectedSourceKeys),
      committedMaterialIds: toStringList(parsed.committedMaterialIds),
      committedMaterialsSnapshot: Array.isArray(parsed.committedMaterialsSnapshot) ? parsed.committedMaterialsSnapshot : [],  // 【新增】恢复快照
      currentRandomEventId: typeof parsed.currentRandomEventId === 'string' ? parsed.currentRandomEventId : null,
      currentEventMessage: typeof parsed.currentEventMessage === 'string' ? parsed.currentEventMessage : '',
      currentStoryId: typeof parsed.currentStoryId === 'string' ? parsed.currentStoryId : null,
      seenArticleIds: toStringList(parsed.seenArticleIds),
      tutorialIntroSeen: parsed.tutorialIntroSeen === true,
      tutorialSeen: parsed.tutorialSeen === true,
      tutorialAutoGuideEnabled: parsed.tutorialAutoGuideEnabled !== false,
      tutorialSkippedRoundNumbers: toRoundNumberList(parsed.tutorialSkippedRoundNumbers),
      tutorialDismissedContextByRound: toDismissedContextByRound(parsed.tutorialDismissedContextByRound),
      dynamicCardsCollectedThisGame: typeof parsed.dynamicCardsCollectedThisGame === 'number'
        ? Math.max(0, Math.floor(parsed.dynamicCardsCollectedThisGame))
        : 0,
    }
  } catch {
    return fallback
  }
}

function persistState(state: PersistedState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // localStorage can be unavailable in private browsing or embedded previews.
  }
}

function addVector(left: [number, number], right: [number, number]): [number, number] {
  return [left[0] + right[0], left[1] + right[1]]
}

export const useGameStore = defineStore('game', {
  state: () => {
    const persisted = loadPersistedState()
    return {
      energy: 5,
      salt: 100,
      heat: 0,
      article: null as Article | null,
      settlement: null as Settlement | null,
      currentRound: persisted.currentRound,
      totalRounds: TOTAL_ROUNDS,
      answererValue: persisted.answererValue,
      screen: persisted.screen,
      roundVector: persisted.roundVector,
      roundVectors: persisted.roundVectors,
      totalVector: persisted.totalVector,
      localSettlement: persisted.localSettlement,
      mountainPosition: persisted.mountainPosition,
      moveHistory: persisted.moveHistory,
      visitedQuadrants: persisted.visitedQuadrants,
      currentSkin: persisted.currentSkin,
      unlockedSkins: persisted.unlockedSkins,
      pendingKanshanMove: persisted.pendingKanshanMove,
      collectedSourceKeys: persisted.collectedSourceKeys,
      committedMaterialIds: persisted.committedMaterialIds,
      committedMaterialsSnapshot: persisted.committedMaterialsSnapshot,  // 【新增】卡牌快照
      currentRandomEventId: persisted.currentRandomEventId,
      currentEventMessage: persisted.currentEventMessage,
      currentStoryId: persisted.currentStoryId,
      /** 运行时剧情脚本（AI 生成或 A 版降级），不持久化；刷新后由 activeStoryScript 兜底 */
      currentStoryScript: null as StoryScript | null,
      seenArticleIds: persisted.seenArticleIds,
      tutorialIntroSeen: persisted.tutorialIntroSeen,
      tutorialSeen: persisted.tutorialSeen,
      tutorialAutoGuideEnabled: persisted.tutorialAutoGuideEnabled,
      tutorialSkippedRoundNumbers: persisted.tutorialSkippedRoundNumbers,
      tutorialDismissedContextByRound: persisted.tutorialDismissedContextByRound,
      dynamicCardsCollectedThisGame: persisted.dynamicCardsCollectedThisGame,
      // Compatibility mirrors for old debug panels; UI uses roundVector/workbench.currentVector instead.
      lastSettlementVector: persisted.roundVector ?? [0, 0] as [number, number],
      lastSettlementPassed: persisted.localSettlement?.passed ?? false,
    }
  },
  getters: {
    isGameOver: state => state.screen === 'final-settlement',
    roundDisplay: state => `${Math.min(state.currentRound, state.totalRounds)}/${state.totalRounds}`,
    currentArticleId: state => state.article?.id ?? 'ai_loading',
    currentQuadrant: state => getQuadrantByVector(state.roundVector ?? [0, 0]),
    finalQuadrant: state => getQuadrantByVector(state.totalVector),
    totalVectorLength: state => Math.hypot(state.totalVector[0], state.totalVector[1]),
    hasRoundSettlement: state => state.screen === 'round-settlement',
    isMapReady: state => (
      state.screen === 'map-ready'
      && state.pendingKanshanMove
      && state.roundVector !== null
      && isNonZeroVector(state.roundVector)
    ),
    hasRandomEvent: state => state.screen === 'random-event' && state.currentRandomEventId !== null,
    /** 还没看过开场介绍（看山自我介绍的 7 句 ADV） */
    needsTutorialIntro: state => !state.tutorialIntroSeen,
    currentRandomEvent: (state) => {
      if (!state.currentRandomEventId) return null
      return getEventById(state.currentRandomEventId) ?? null
    },
    /**
     * 当前该播放的剧情脚本。
     * 优先用运行时解析出的 currentStoryScript；刷新后运行时脚本丢失时，
     * 按持久化的 currentStoryId 兜底（AI 剧情退到对应序号的 A 版预设）。
     */
    activeStoryScript: (state): StoryScript | null => {
      if (state.currentStoryScript) return state.currentStoryScript
      if (!state.currentStoryId) return null
      if (state.currentStoryId === AI_STORY_ID) {
        return {
          ...getFallbackStory(Math.max(state.currentRound - 1, 1)),
          debug: { fallbackReason: 'refresh_lost_runtime_ai_story' },
        }
      }
      return getStoryScript(state.currentStoryId) ?? null
    },
  },
  actions: {
    persist() {
      persistState({
        currentRound: this.currentRound,
        answererValue: this.answererValue,
        screen: this.screen,
        roundVector: this.roundVector,
        roundVectors: this.roundVectors,
        totalVector: this.totalVector,
        mountainPosition: this.mountainPosition,
        moveHistory: this.moveHistory,
        visitedQuadrants: this.visitedQuadrants,
        currentSkin: this.currentSkin,
        unlockedSkins: this.unlockedSkins,
        localSettlement: this.localSettlement,
        pendingKanshanMove: this.pendingKanshanMove,
        collectedSourceKeys: this.collectedSourceKeys,
        committedMaterialIds: this.committedMaterialIds,
        committedMaterialsSnapshot: this.committedMaterialsSnapshot,  // 【新增】持久化快照
        currentRandomEventId: this.currentRandomEventId,
        currentEventMessage: this.currentEventMessage,
        currentStoryId: this.currentStoryId,
        seenArticleIds: this.seenArticleIds,
        tutorialIntroSeen: this.tutorialIntroSeen,
        tutorialSeen: this.tutorialSeen,
        tutorialAutoGuideEnabled: this.tutorialAutoGuideEnabled,
        tutorialSkippedRoundNumbers: this.tutorialSkippedRoundNumbers,
        tutorialDismissedContextByRound: this.tutorialDismissedContextByRound,
        dynamicCardsCollectedThisGame: this.dynamicCardsCollectedThisGame,
      })
    },
    bumpEnergy() {
      this.energy += 1
    },
    setArticle(article: Article) {
      this.article = article
    },
    /** 记录已读文章ID，用于后续随机抽取时排除 */
    recordSeenArticle(articleId: string) {
      if (!articleId || this.seenArticleIds.includes(articleId)) return
      this.seenArticleIds.push(articleId)
      this.persist()
    },
    /** 动态卡收集成功后调用，递增本局计数器（前端配额检查用） */
    incrementDynamicCards() {
      this.dynamicCardsCollectedThisGame += 1
      this.persist()
    },
    setSettlement(settlement: Settlement) {
      this.settlement = settlement
    },
    beginRoundIntro() {
      if (this.isGameOver) {
        this.resetGame()
      }
      this.screen = 'round-intro'
      this.persist()
      syncMachineScreen('round-intro', this.currentRound)
    },
    openArticle() {
      this.screen = 'article'
      this.persist()
      syncMachineScreen('article', this.currentRound)
    },
    completeReading() {
      if (this.screen !== 'article') return false
      const committedDirectionReady = (
        this.pendingKanshanMove
        && this.roundVector !== null
        && isNonZeroVector(this.roundVector)
      )
      this.screen = committedDirectionReady ? 'map-ready' : 'map-needs-vector'
      if (!committedDirectionReady) {
        this.pendingKanshanMove = false
      }
      this.persist()
      syncMachineScreen(this.screen, this.currentRound)
      return true
    },
    /** 移动开始前可回到同一局文章；不重置背包、创作流或已提交方向。 */
    reopenCurrentArticle() {
      if (
        this.screen !== 'map'
          && this.screen !== 'map-needs-vector'
          && this.screen !== 'map-ready'
      ) return false
      this.screen = 'article'
      this.persist()
      syncMachineScreen('article', this.currentRound)
      return true
    },
    invalidateRoundVector() {
      const vectors: Array<[number, number] | null> = Array.from(
        { length: this.totalRounds },
        (_, index) => index === this.currentRound - 1 ? null : this.roundVectors[index] ?? null,
      )
      this.roundVector = null
      this.roundVectors = vectors
      this.totalVector = vectors.reduce<[number, number]>(
        (total, item) => item ? addVector(total, item) : total,
        [0, 0],
      )
      this.localSettlement = null
      this.lastSettlementVector = [0, 0]
      this.lastSettlementPassed = false
      this.pendingKanshanMove = false
      this.screen = 'map-needs-vector'
      this.persist()
      syncMachineScreen('map-needs-vector', this.currentRound)
    },
    isSourceCollected(round: number, articleId: string, cardId: string) {
      return this.collectedSourceKeys.includes(buildCollectionSourceKey(round, articleId, cardId))
    },
    markSourceCollected(round: number, articleId: string, cardId: string) {
      const sourceKey = buildCollectionSourceKey(round, articleId, cardId)
      if (this.collectedSourceKeys.includes(sourceKey)) return false

      this.collectedSourceKeys = [...this.collectedSourceKeys, sourceKey]
      this.persist()
      return true
    },
    clearRoundCollectedSources() {
      if (this.collectedSourceKeys.length === 0) return
      this.collectedSourceKeys = []
      this.persist()
    },
    /**
     * v5: 提交向量后进入 article-gen 状态，不立即结算。
     * 结算延迟到文章生成完成后由 completeArticleGeneration() 执行。
     */
    commitRoundVector(
      _result: LocalSettlementResult | null,
      vector: [number, number],
      committedMaterialIds: readonly string[] = [],
    ) {
      // 【调试】记录接收到的卡牌ID
      if (import.meta.env.DEV) {
        console.log('[gameStore] commitRoundVector 收到', committedMaterialIds.length, '张卡牌')
        console.log('  卡牌ID列表:', committedMaterialIds)
      }
      
      const committedVector: [number, number] = [
        toFiniteNumber(vector[0], 0),
        toFiniteNumber(vector[1], 0),
      ]
      if (!isNonZeroVector(committedVector)) {
        this.invalidateRoundVector()
        return false
      }
      const vectors: Array<[number, number] | null> = Array.from(
        { length: this.totalRounds },
        (_, index) => this.roundVectors[index] ?? null,
      )
      vectors[this.currentRound - 1] = committedVector

      this.roundVector = committedVector
      this.roundVectors = vectors
      this.totalVector = vectors.reduce<[number, number]>(
        (total, item) => item ? addVector(total, item) : total,
        [0, 0],
      )
      // 结算延迟到文章生成后，此时先清空
      this.localSettlement = null
      this.committedMaterialIds = [...new Set(
        committedMaterialIds.filter(id => typeof id === 'string' && id.length > 0),
      )]
      
      // 【关键修复】保存卡牌完整数据快照，用于后续成就计数
      // 因为 materialStore 会在每局开始时被清空
      const materialStore = useMaterialStore()
      this.committedMaterialsSnapshot = this.committedMaterialIds.flatMap(materialId => {
        const material = materialStore.getMaterialById(materialId)
        return material ? [material] : []
      })
      
      if (import.meta.env.DEV) {
        console.log('[gameStore] 已保存卡牌快照:', this.committedMaterialsSnapshot.length, '张')
      }
      
      this.lastSettlementVector = [...committedVector]
      this.lastSettlementPassed = false
      this.pendingKanshanMove = true
      this.screen = 'article-gen'
      this.persist()
      syncMachineScreen('article-gen', this.currentRound)
      return true
    },
    /**
     * v5: 文章生成完成后调用，执行本地结算并进入 round-settlement。
     * 计算 pass/fail、评级、答主值增量，然后展示结算窗口。
     */
    completeArticleGeneration() {
      if (this.screen !== 'article-gen' || !this.roundVector) return false

      const result = calculateLocalSettlement(this.roundVector)

      this.localSettlement = result
      this.lastSettlementPassed = result.passed
      this.screen = 'round-settlement'
      this.persist()
      syncMachineScreen('round-settlement', this.currentRound)
      return true
    },
    /**
     * v5: 跳过文章生成，直接结算。
     */
    skipArticleGeneration() {
      return this.completeArticleGeneration()
    },
    /** 兼容旧调用方：新主流程应调用 commitRoundVector。 */
    applyLocalSettlement(result: LocalSettlementResult) {
      return this.commitRoundVector(result, this.roundVector ?? [0, 0])
    },
    clearCommittedMaterialSnapshot() {
      this.committedMaterialIds = []
      this.persist()
    },
    /**
     * v5: 结算弹窗关闭后，设置状态让知北针动画接管。
     * 不清除工作区（知北针动画还需要 currentVector 匹配），
     * 由 MapView 的 handleCompassMovementStart 负责清除。
     */
    preparePostSettlementCompass() {
      this.screen = 'map-ready'
      this.pendingKanshanMove = true
      this.persist()
      syncMachineScreen('map-ready', this.currentRound)
    },
    beginCompassMovement() {
      // v5: 支持从 round-settlement（新流程）或 map-ready（旧流程兼容）出发
      const canMove = (this.screen === 'round-settlement' || this.isMapReady)
        && this.roundVector
        && isNonZeroVector(this.roundVector)
      if (!canMove) return false

      const roundVector = this.roundVector!
      const fromRow = this.mountainPosition.row
      const fromCol = this.mountainPosition.col
      const target = getTargetPosition(this.mountainPosition, roundVector)
      this.mountainPosition = {
        ...this.mountainPosition,
        direction: getDirectionByVector(roundVector),
        isMoving: true,
        targetRow: target.row,
        targetCol: target.col,
      }
      this.screen = 'map-moving'
      this.pendingKanshanMove = false
      // 真正出发即视为首次教学完成，此后改由非强制的上下文引导卡接管
      if (!this.tutorialSeen) this.completeFirstRunTutorial()
      this.persist()
      console.log(`[知北针] 看山移动: (${fromRow},${fromCol}) → (${target.row},${target.col})`)
      syncMachineScreen('map-moving', this.currentRound)
      return true
    },
    finalizeMovement() {
      if (this.screen !== 'map-moving') return false

      const position = this.mountainPosition
      const targetRow = position.targetRow ?? position.row
      const targetCol = position.targetCol ?? position.col
      const vector = this.roundVector ?? [0, 0] as [number, number]
      const alreadyRecorded = this.moveHistory.some(record => record.round === this.currentRound)

      this.mountainPosition = {
        row: targetRow,
        col: targetCol,
        direction: position.direction,
        isMoving: false,
      }

      if (!alreadyRecorded) {
        this.moveHistory = [
          ...this.moveHistory,
          {
            round: this.currentRound,
            vector: [...vector] as [number, number],
            fromRow: position.row,
            fromCol: position.col,
            toRow: targetRow,
            toCol: targetCol,
            direction: position.direction,
            timestamp: Date.now(),
          },
        ]
      }

      const quadrant = getQuadrantByMapPosition(targetRow, targetCol)
      if (!this.visitedQuadrants.includes(quadrant)) {
        this.visitedQuadrants = [...this.visitedQuadrants, quadrant]
      }

      if (this.localSettlement?.passed) {
        this.answererValue += this.localSettlement.answererDelta
      }

      this.pendingKanshanMove = false

      // 【注意】成就计数已移至 handleSettlementContinue()，此处不再重复记录
      // 因为知北针动画可能被跳过，导致 finalizeMovement() 在成就记录之前就被调用
      // 如果未来恢复知北针动画作为唯一流程，可以移回此处

      // v5: 最后一局进入 final-settlement，否则直接推进到下一局
      if (this.currentRound === this.totalRounds) {
        this.screen = 'final-settlement'
        this.persist()
        syncMachineScreen('final-settlement', this.currentRound)
      } else {
        // 结算已在移动前完成，清空结算数据防止弹窗闪烁
        this.localSettlement = null
        this.persist()
        // 预取下一段剧情（AI-story 功能），让玩家看旅行笔记时 AI 已在后台生成
        void this.prefetchRoundStory(this.currentRound, quadrant)
        // 直接推进到下一局（跳过 round-settlement，避免结算弹窗闪烁覆盖旅行笔记）
        void this.advanceToNextRound()
      }
      
      return true
    },
    /** 地图刷新时若刚好发生在移动动画期间，恢复到目标格并进入结算，避免卡死。 */
    restoreAfterRefresh() {
      if (this.screen !== 'map-moving') return
      this.finalizeMovement()
    },
    /**
     * 结算界面预取本局对应的 AI 剧情（第 1-5 局结算后各一段）。
     * 必须在 continueJourney() 重置 roundVector / localSettlement /
     * committedMaterialIds 之前调用，否则上下文会全空。
     */
    prefetchRoundStory(round: number, quadrant: QuadrantType) {
      const materialStore = useMaterialStore()
      const cards: Record<string, number> = {}
      for (const cardType of ALL_CARD_TYPES) {
        cards[cardType] = 0
      }
      for (const materialId of this.committedMaterialIds) {
        const cardType = materialStore.getMaterialById(materialId)?.type
        if (!cardType) continue
        cards[cardType] = (cards[cardType] ?? 0) + 1
      }

      const [heat, salt] = this.roundVector ?? [0, 0]
      const context: StoryContext = {
        round,
        quadrant,
        passed: this.localSettlement?.passed ?? false,
        rating: this.localSettlement?.rating ?? '',
        heat,
        salt,
        cards,
        history: this.moveHistory.slice(-3).map(record => record.direction),
      }

      _pendingStoryRound = round
      _pendingStoryPromise = fetchAIStory(context)
      console.log('🎬 [game.ts] 第' + round + '局结算：预取 AI 剧情', context)
    },
    /**
     * 解析本次要播放的剧情脚本：优先用预取的 AI 结果（最多再等 12 秒），
     * 失败/超时/局号对不上则降级到本地 A 版（按触发序号 1-5 索引）。
     */
    async resolveStoryScript(triggerRound: number): Promise<StoryScript> {
      const pending = _pendingStoryRound === triggerRound ? _pendingStoryPromise : null
      let result: AIStoryResult | null = null
      let fallbackReason = pending ? 'ai_result_empty_or_timeout' : 'no_matching_pending_story'

      if (pending) {
        try {
          result = await Promise.race([
            pending,
            new Promise<null>(resolve => {
              setTimeout(() => resolve(null), STORY_RESOLVE_TIMEOUT)
            }),
          ])
          if (result === null) {
            fallbackReason = 'ai_result_empty_or_timeout'
          }
        } catch (error) {
          console.error('❌ [game.ts] AI 剧情解析异常:', error)
          fallbackReason = 'ai_result_rejected'
          result = null
        }
      }
      clearPendingStory()

      if (result && result.lines.length > 0) {
        console.log(`✅ [game.ts] 实际播放 AI 生成剧情: ${result.id} - ${result.title}`)
        return {
          id: result.id,
          title: result.title,
          source: 'ai',
          debug: result.debug,
          lines: result.lines.map(line => ({
            speaker: line.speaker,
            speakerName: line.speakerName,
            text: line.text,
          })),
        }
      }

      const fallback = {
        ...getFallbackStory(triggerRound),
        debug: { fallbackReason, waitMs: STORY_RESOLVE_TIMEOUT },
      }
      console.warn(
        `💡 [game.ts] 实际播放本地预设剧情: ${fallback.id} - ${fallback.title}`,
        fallback.debug,
      )
      return fallback
    },
    /**
     * v5: 移动完成后直接推进到下一局（不经过 round-settlement）。
     * 由 finalizeMovement 调用，无 screen 守卫。
     */
    async advanceToNextRound() {
      // 保存递增前的局号，用于事件条件判定（如教程 maxRound:1 应在第1局结束后触发）
      const previousRound = this.currentRound
      this.currentRound = Math.min(this.currentRound + 1, this.totalRounds)
    
      console.log(`🤖 [game.ts] 第${this.currentRound}局开始：加载AI文章`)
      try {
        const aiArticle = await fetchRandomAIArticle()
        if (aiArticle) {
          console.log(`✅ [game.ts] AI文章加载成功: ${aiArticle.id} - ${aiArticle.title}`)
          this.article = aiArticle
        } else {
          console.warn('⚠️ [game.ts] 没有可用的AI文章，使用默认文章')
        }
      } catch (error) {
        console.error('❌ [game.ts] AI文章加载失败:', error)
      }
    
      this.roundVector = null
      this.collectedSourceKeys = []
      this.committedMaterialIds = []
      this.localSettlement = null
      this.lastSettlementVector = [0, 0]
      this.lastSettlementPassed = false
      this.pendingKanshanMove = false
      this.dynamicCardsCollectedThisGame = 0
      resetRoundTask()
    
      const drawn = drawRandomEvent({
        currentRound: previousRound,
        answererValue: this.answererValue,
        visitedQuadrants: this.visitedQuadrants,
      })
    
      if (drawn && drawn.conditionMet) {
        this.currentRandomEventId = drawn.event.id
        const effectCtx: EffectContext = {
          conditionCtx: {
            currentRound: previousRound,
            answererValue: this.answererValue,
            visitedQuadrants: this.visitedQuadrants,
          },
          applyVectorEffect: (_action, _targetQuadrant) => {
            console.log(`[随机事件 A] 位置效果: ${_action} → ${_targetQuadrant ?? '默认'}`)
          },
          giveCard: (_cardType, _count) => {
            console.log(`[随机事件 C] 获得 ${_count} 张 ${_cardType}`)
          },
          setRoundTask: (_task, _cardType, _count) => {
            console.log(`[随机事件 B] 任务: ${_task} ${_cardType} x${_count}`)
          },
          triggerStory: (_storyId) => {
            this.currentStoryId = _storyId
          },
        }
        const message = executeEventEffect(drawn.event, effectCtx)
        this.currentEventMessage = message
        // D 类事件：先把运行时剧情脚本解析好，再切到 random-event 屏弹 ADV
        if (drawn.event.effect.type === 'D') {
          this.currentStoryScript = await this.resolveStoryScript(previousRound)
        } else {
          this.currentStoryScript = null
        }
        this.screen = 'random-event'
        this.persist()
        syncMachineScreen('random-event', this.currentRound)
        console.log(`[随机事件] 触发: ${drawn.event.name} - ${message}`)
      } else {
        this.currentRandomEventId = null
        this.currentEventMessage = ''
        this.currentStoryId = null
        this.currentStoryScript = null
        clearPendingStory()
        this.screen = 'round-intro'
        this.persist()
        syncMachineScreen('round-intro', this.currentRound)
      }
    },
    /** 兼容旧调用：从 round-settlement 状态继续旅程（ SettlementModal 使用） */
    async continueJourney() {
      if (this.screen !== 'round-settlement') return
      await this.advanceToNextRound()
    },
    /** 解决随机事件，进入下一局的 round-intro */
    resolveRandomEvent() {
      if (this.screen !== 'random-event') return

      this.currentRandomEventId = null
      this.currentEventMessage = ''
      this.currentStoryId = null
      this.currentStoryScript = null
      this.screen = 'round-intro'
      this.persist()
      syncMachineScreen('round-intro', this.currentRound)
    },
    /** 开场 ADV 介绍播完；只关掉开场对话，不影响聚光灯教学进度 */
    markTutorialIntroSeen() {
      this.tutorialIntroSeen = true
      this.persist()
    },
    /** 首次聚光灯教学结束（玩家完成第一次出发），毕业后只剩非强制引导卡 */
    completeFirstRunTutorial() {
      this.tutorialSeen = true
      this.persist()
    },
    setTutorialAutoGuideEnabled(enabled: boolean) {
      this.tutorialAutoGuideEnabled = enabled
      this.persist()
    },
    dismissTutorialContext(contextKey: string, round?: number) {
      const roundKey = String(round ?? this.currentRound)
      const dismissed = this.tutorialDismissedContextByRound[roundKey] ?? []
      if (dismissed.includes(contextKey)) return
      this.tutorialDismissedContextByRound = {
        ...this.tutorialDismissedContextByRound,
        [roundKey]: [...dismissed, contextKey],
      }
      this.persist()
    },
    skipTutorialRound(round?: number) {
      const roundNumber = round ?? this.currentRound
      if (this.tutorialSkippedRoundNumbers.includes(roundNumber)) return
      this.tutorialSkippedRoundNumbers = [...this.tutorialSkippedRoundNumbers, roundNumber]
      this.persist()
    },
    /** 从 Landing 进入时回到地图主页；只收起可恢复的入口弹层，不清理旅程数据。 */
    normalizeLandingEntry() {
      if (this.isGameOver || this.screen === 'map') return

      this.screen = 'map'
      this.persist()
      syncMachineScreen('map', this.currentRound)
    },
    /** 强制完全初始化：重置一切状态（含教程），回到初始地图 */
    forceInitGame() {
      this.resetGame()
    },
    resetGame() {
      this.currentRound = 1
      this.answererValue = 0
      this.article = null
      this.settlement = null
      this.screen = 'map'
      this.roundVector = null
      this.collectedSourceKeys = []
      this.committedMaterialIds = []
      this.roundVectors = Array.from({ length: this.totalRounds }, () => null)
      this.totalVector = [0, 0]
      this.localSettlement = null
      this.lastSettlementVector = [0, 0]
      this.lastSettlementPassed = false
      this.mountainPosition = defaultMountainPosition()
      this.moveHistory = []
      this.visitedQuadrants = []
      this.currentSkin = 'default'
      this.unlockedSkins = ['default']
      this.pendingKanshanMove = false
      this.currentRandomEventId = null
      this.currentEventMessage = ''
      this.currentStoryId = null
      this.currentStoryScript = null
      clearPendingStory()
      this.seenArticleIds = []
      this.tutorialIntroSeen = false
      this.tutorialSeen = false
      // A new journey starts with fresh round-scoped guide state. The
      // auto-guide preference is intentionally preserved as a user setting.
      this.tutorialSkippedRoundNumbers = []
      this.tutorialDismissedContextByRound = {}
      this.dynamicCardsCollectedThisGame = 0
      this.persist()
      getAchievementStore().resetAchievements()
      syncMachineScreen('map', this.currentRound)
    },
  },
})
