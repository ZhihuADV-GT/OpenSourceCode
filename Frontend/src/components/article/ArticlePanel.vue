<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  buildDynamicCardPayload,
  buildSelectionPayload,
  createDynamicCard,
  getStrokeJudgeErrorMessage,
  judgeSelection,
} from '../../services/strokeJudgeService'
import { triggerJudgeSuccess, triggerJudgeFail } from '../../services/kanshanMessages'
import { fetchArticleHint } from '../../services/hintService'
import { buildMaterialInstanceId, useGameStore, DYNAMIC_CARD_QUOTA_PER_GAME } from '../../stores/game'
import { BACKPACK_CAPACITY, useMaterialStore } from '../../stores/material'
import type { Article, HintItem, HintRange } from '../../types/article'
import type { CollectionFlight, SelectionAnchorRect } from '../../types/collectionMotion'
import type { Material } from '../../types/material'
import type { PendingSelection } from '../../types/selection'
import type { SaltCard } from '../../types/saltCard'
import type { JudgeResult } from '../../types/strokeJudge'

type HighlightType = 'normal' | 'pending' | 'collected' | 'hint'

interface PopupPosition {
  top: number
  left: number
}

interface TextSegment {
  start: number
  end: number
  text: string
  type: HighlightType
}

interface CollectedRange extends PendingSelection {
  type: 'collected'
  informationPointId: string
}

type SelectionFeedbackKind = 'info' | 'warning' | 'error' | 'success'

interface SelectionFeedback {
  kind: SelectionFeedbackKind
  message: string
}

const props = defineProps<{
  article: Article
}>()

const emit = defineEmits<{
  (event: 'material-collected', flight: CollectionFlight): void
}>()

const materialStore = useMaterialStore()
const gameStore = useGameStore()
const { materials } = storeToRefs(materialStore)
const articleElement = ref<HTMLElement | null>(null)
const popupElement = ref<HTMLElement | null>(null)
const pendingSelection = ref<PendingSelection | null>(null)
const popupPosition = ref<PopupPosition | null>(null)
const selectionFeedback = ref<SelectionFeedback | null>(null)
const selectionAnchor = ref<SelectionAnchorRect | null>(null)
const isSubmitting = ref(false)
const hintRanges = ref<HintRange[]>([])
let collectionSequence = 0

const articleTitleSizeClass = computed(() => {
  const titleLength = Array.from(props.article.title).length
  if (titleLength <= 18) return 'article-title--large'
  if (titleLength <= 32) return 'article-title--medium'
  return 'article-title--compact'
})

function getCollectedRanges(paragraphIndex: number): CollectedRange[] {
  const ranges: CollectedRange[] = []

  // 后端不再下发 linespots；当前回合高亮只使用 Judge 返回的 canonical range。
  for (const material of materials.value) {
    if (
      material.collectedRound === gameStore.currentRound
      && material.articleId === props.article.id
      && typeof material.paragraphIndex === 'number'
      && typeof material.canonicalStartOffset === 'number'
      && typeof material.canonicalEndOffset === 'number'
      && material.paragraphIndex === paragraphIndex
    ) {
      ranges.push({
        paragraphIndex: material.paragraphIndex,
        startOffset: material.canonicalStartOffset,
        endOffset: material.canonicalEndOffset,
        text: material.text,
        type: 'collected',
        informationPointId: material.informationPointId,
      })
    }
  }

  return ranges
}

function buildSegments(paragraph: string, paragraphIndex: number): TextSegment[] {
  const ranges: Array<PendingSelection & { type: Exclude<HighlightType, 'normal'>; informationPointId?: string }> = [
    ...getCollectedRanges(paragraphIndex),
  ]
  const pending = pendingSelection.value

  if (pending?.paragraphIndex === paragraphIndex) {
    ranges.push({ ...pending, type: 'pending' })
  }

  // 添加 hint 范围（前端是单段落渲染，paragraphIndex 恒为 0）
  if (paragraphIndex === 0) {
    for (const hint of hintRanges.value) {
      ranges.push({
        paragraphIndex: 0,
        startOffset: hint.start,
        endOffset: hint.end,
        text: '', // hint 不需要 text
        type: 'hint',
      })
    }
  }

  const boundaries = new Set<number>([0, paragraph.length])
  ranges.forEach(range => {
    boundaries.add(Math.max(0, Math.min(paragraph.length, range.startOffset)))
    boundaries.add(Math.max(0, Math.min(paragraph.length, range.endOffset)))
  })

  const sortedBoundaries = [...boundaries].sort((left, right) => left - right)
  const priority: Record<HighlightType, number> = { normal: 0, hint: 1, pending: 2, collected: 3 }
  const segments: TextSegment[] = []

  for (let index = 0; index < sortedBoundaries.length - 1; index += 1) {
    const start = sortedBoundaries[index]
    const end = sortedBoundaries[index + 1]

    if (end <= start) {
      continue
    }

    const activeRange = ranges
      .filter(range => range.startOffset < end && range.endOffset > start)
      .sort((left, right) => priority[right.type] - priority[left.type])[0]
    const type = activeRange?.type ?? 'normal'
    const previous = segments.at(-1)

    if (previous?.type === type && previous.end === start) {
      previous.end = end
      previous.text += paragraph.slice(start, end)
    } else {
      segments.push({ start, end, text: paragraph.slice(start, end), type })
    }
  }

  return segments
}

const renderedParagraphs = computed(() => props.article.paragraphs.map((paragraph, index) => ({
  paragraph,
  index,
  segments: buildSegments(paragraph, index),
})))

function findParagraph(node: Node): HTMLParagraphElement | null {
  const element = node.nodeType === Node.ELEMENT_NODE
    ? node as Element
    : node.parentElement

  return element?.closest<HTMLParagraphElement>('p[data-paragraph-index]') ?? null
}

function getTextOffsetWithinParagraph(paragraph: HTMLParagraphElement, node: Node, offset: number): number {
  const offsetRange = document.createRange()
  offsetRange.selectNodeContents(paragraph)
  offsetRange.setEnd(node, offset)
  return offsetRange.toString().length
}

function copyRect(rect: DOMRect): SelectionAnchorRect {
  return {
    top: rect.top,
    bottom: rect.bottom,
    left: rect.left,
    right: rect.right,
    width: rect.width,
    height: rect.height,
  }
}

function clearNativeSelection() {
  window.getSelection()?.removeAllRanges()
}

function clearPendingSelection(clearFeedback = true) {
  pendingSelection.value = null
  popupPosition.value = null
  selectionAnchor.value = null

  if (clearFeedback) {
    selectionFeedback.value = null
  }
}

function setSelectionFeedback(kind: SelectionFeedbackKind, message: string) {
  selectionFeedback.value = { kind, message }
}

function calculatePopupPosition(anchor: SelectionAnchorRect, width: number, height: number): PopupPosition {
  const gap = 10
  const padding = 12
  const container = articleElement.value?.getBoundingClientRect()
  const originLeft = container?.left ?? 0
  const originTop = container?.top ?? 0
  const containerWidth = container?.width ?? window.innerWidth
  const containerHeight = container?.height ?? window.innerHeight
  const centeredLeft = anchor.left + anchor.width / 2 - originLeft - width / 2
  const maxLeft = Math.max(padding, containerWidth - width - padding)
  const left = Math.max(padding, Math.min(centeredLeft, maxLeft))
  const aboveTop = anchor.top - originTop - height - gap
  const belowTop = anchor.bottom - originTop + gap
  const maxTop = Math.max(padding, containerHeight - height - padding)
  const top = aboveTop >= padding
    ? aboveTop
    : belowTop <= maxTop
      ? belowTop
      : maxTop

  return { top, left }
}

function showJudgeFeedback(
  kind: SelectionFeedbackKind,
  message: string,
  anchor: SelectionAnchorRect | null,
  currentPosition: PopupPosition | null,
) {
  // Feedback must survive clearing the temporary/native selection. Keep the
  // existing popup position as the anchor for the status message only.
  clearPendingSelection(false)
  clearNativeSelection()
  setSelectionFeedback(kind, message)
  popupPosition.value = currentPosition
    ?? (anchor ? calculatePopupPosition(anchor, 220, 76) : null)
}

async function positionPopup() {
  const anchor = selectionAnchor.value

  if (!anchor) {
    return
  }

  popupPosition.value = calculatePopupPosition(anchor, 220, 76)
  await nextTick()

  if (popupElement.value) {
    popupPosition.value = calculatePopupPosition(
      anchor,
      popupElement.value.offsetWidth,
      popupElement.value.offsetHeight,
    )
  }
}

function trimSelectionOffsets(text: string, startOffset: number, endOffset: number) {
  const leadingWhitespace = text.length - text.trimStart().length
  const trailingWhitespace = text.length - text.trimEnd().length

  return {
    startOffset: startOffset + leadingWhitespace,
    endOffset: endOffset - trailingWhitespace,
    text: text.trim(),
  }
}

async function handleSelectionEnd() {
  selectionFeedback.value = null
  const selection = window.getSelection()

  if (!selection || selection.rangeCount === 0) {
    clearPendingSelection()
    return
  }

  const rawText = selection.toString()

  if (!rawText.trim()) {
    clearPendingSelection()
    return
  }

  const range = selection.getRangeAt(0)
  const startParagraph = findParagraph(range.startContainer)
  const endParagraph = findParagraph(range.endContainer)

  if (!startParagraph || !endParagraph || startParagraph !== endParagraph) {
    clearPendingSelection()
    return
  }

  try {
    const paragraphIndex = Number(startParagraph.dataset.paragraphIndex)
    const startOffset = getTextOffsetWithinParagraph(startParagraph, range.startContainer, range.startOffset)
    const endOffset = getTextOffsetWithinParagraph(startParagraph, range.endContainer, range.endOffset)
    const normalized = trimSelectionOffsets(
      rawText,
      Math.min(startOffset, endOffset),
      Math.max(startOffset, endOffset),
    )
    const nextSelection: PendingSelection = {
      paragraphIndex,
      startOffset: normalized.startOffset,
      endOffset: normalized.endOffset,
      text: normalized.text,
    }

    if (!nextSelection.text || nextSelection.endOffset <= nextSelection.startOffset) {
      clearPendingSelection()
      return
    }

    // Read and copy the viewport rect before Vue renders a new pending highlight.
    selectionAnchor.value = copyRect(range.getBoundingClientRect())
    pendingSelection.value = nextSelection
    await positionPopup()
  } catch {
    clearPendingSelection()
  }
}

function cancelSelection() {
  clearPendingSelection()
  clearNativeSelection()
}

function toMaterial(card: SaltCard, selection: PendingSelection): Material {
  const canonicalText = props.article.canonicalContent.slice(
    card.canonicalStartOffset,
    card.canonicalEndOffset,
  )

  return {
    // Material.id is a unique local instance; preserve the backend card ID below.
    id: buildMaterialInstanceId(gameStore.currentRound, props.article.id, card.cardId),
    articleId: props.article.id,
    informationPointId: card.cardId,
    collectedRound: gameStore.currentRound,
    // 卡牌原文与文章高亮必须来自同一 canonical range，而不是玩家多划的范围。
    text: canonicalText,
    type: card.cardType,
    attributeValue: card.attributeValue,
    // 同时保留玩家实际选区，仅用于本次 Judge 的审计/调试。
    paragraphIndex: selection.paragraphIndex,
    startOffset: selection.startOffset,
    endOffset: selection.endOffset,
    canonicalStartOffset: card.canonicalStartOffset,
    canonicalEndOffset: card.canonicalEndOffset,
  }
}

/**
 * 划线判定：AI 动态端点为主，/api/judge 只在它整体不可用时兜底。
 *
 * 为何是「新端点先调」而不是「judge 之后再追加」：judge 的 miss 分支自己就会
 * 建一张本地分类器动态卡并落盘，之后再调新端点会让同一次划线产生两张卡
 * （两边文本不同 → L2 去重的 hash 不命中 → 拦不住），而 judge 建的那张孤儿卡
 * 还会让玩家下次划同一句时被误判「该素材已经收集」。让新端点打头，
 * judge 的 miss 分支就根本不会执行，AI 判型也因而覆盖了 5-200 字的正常划线。
 *
 * 打头不会改变预设卡行为：新端点入口第一步就是同一套 linespot 比对（同 25%
 * 阈值、同 _spot_to_card_response），命中时返回的 card 与 judge 逐字一致，只多
 * 一个 source 字段。这条等价性由后端 test_preset_branch_is_equivalent_to_judge
 * 钉住——前端没有测试设施，两边漂移了在这里看不出来。
 *
 * 只有抛异常（后端未起 / 网络断 / 超时）才回落，保留接入新端点之前的行为；
 * 按已定决策降级不给玩家看，只在 console 留一行供与后端日志的降级档位对照。
 * 新端点「拒绝」（hit:false）**不回落**：judge 既没有去重也没有配额，
 * 回落会让被刻意拒掉的选区（重复、超配额、AI 判无价值）照样建卡。
 */
async function judgeSelectionWithAi(pending: PendingSelection): Promise<JudgeResult> {
  try {
    return await createDynamicCard(
      buildDynamicCardPayload(props.article.id, pending, gameStore.currentRound),
    )
  } catch (error) {
    console.warn('[ArticlePanel] AI 动态判定不可用，回落到 /api/judge:', error)
    return judgeSelection(buildSelectionPayload(props.article.id, pending))
  }
}

async function submitSelection() {
  const pending = pendingSelection.value

  if (!pending || isSubmitting.value) {
    setSelectionFeedback('error', '当前没有有效选区')
    return
  }

  const sourceRect = selectionAnchor.value
    ?? (popupElement.value ? copyRect(popupElement.value.getBoundingClientRect()) : null)
  const feedbackAnchor = selectionAnchor.value
  const feedbackPosition = popupPosition.value

  isSubmitting.value = true
  setSelectionFeedback('info', 'AI正在思索,请稍候…')

  // 前端本地配额检查：一局最多收集 10 张动态卡
  if (gameStore.dynamicCardsCollectedThisGame >= DYNAMIC_CARD_QUOTA_PER_GAME) {
    showJudgeFeedback(
      'warning',
      `本局动态素材已达上限（${gameStore.dynamicCardsCollectedThisGame}/${DYNAMIC_CARD_QUOTA_PER_GAME}），请先使用一些素材后再收集。`,
      feedbackAnchor,
      feedbackPosition,
    )
    isSubmitting.value = false
    return
  }

  try {
    // 全长度走 AI 判定（含 5-200 字的正常划线），/api/judge 降为异常兜底。
    // 详见 judgeSelectionWithAi 的注释：顺序是刻意的，反过来会产生双卡。
    const result = await judgeSelectionWithAi(pending)

    if (result.hit === false) {
      triggerJudgeFail({ articleId: props.article.id, text: pending.text })
      showJudgeFeedback(
        'error',
        result.message || '未发现有效素材',
        feedbackAnchor,
        feedbackPosition,
      )
      return
    }

    if (gameStore.isSourceCollected(gameStore.currentRound, props.article.id, result.card.cardId)) {
      showJudgeFeedback(
        'warning',
        '该素材已经收集',
        feedbackAnchor,
        feedbackPosition,
      )
      return
    }

    const material = toMaterial(result.card, pending)
    const collectionResult = materialStore.addMaterial(material)
    if (collectionResult === 'full') {
      showJudgeFeedback(
        'warning',
        `背包已满（${BACKPACK_CAPACITY}/${BACKPACK_CAPACITY}），请先使用一些素材后再收集。`,
        feedbackAnchor,
        feedbackPosition,
      )
      return
    }
    if (collectionResult !== 'added') {
      showJudgeFeedback(
        'warning',
        '该素材已经收集',
        feedbackAnchor,
        feedbackPosition,
      )
      return
    }
    gameStore.markSourceCollected(gameStore.currentRound, props.article.id, result.card.cardId)
    gameStore.incrementDynamicCards()
    triggerJudgeSuccess({ articleId: props.article.id, text: pending.text })
    clearPendingSelection()
    clearNativeSelection()

    if (sourceRect) {
      collectionSequence += 1
      emit('material-collected', {
        id: `${material.id}-${Date.now()}-${collectionSequence}`,
        materialId: material.id,
        materialType: material.type ?? '素材',
        sourceRect,
      })
    }
  } catch (error) {
    setSelectionFeedback('error', getStrokeJudgeErrorMessage(error))
  } finally {
    isSubmitting.value = false
  }
}

const isSelectionBlocked = computed(() => (
  isSubmitting.value
))

function handleViewportChange() {
  if (pendingSelection.value) {
    clearPendingSelection()
    clearNativeSelection()
  }
}

function handleArticleScroll() {
  if (pendingSelection.value || selectionFeedback.value) {
    clearPendingSelection()
    clearNativeSelection()
  }
}

/**
 * 显示 hint 高亮
 */
function showHintHighlight(ranges: HintRange[]) {
  hintRanges.value = ranges
}

/**
 * 获取当前 hint 数据（供外部弹窗使用）
 */
async function fetchHintsForModal(): Promise<{ message: string; hints: HintItem[] } | null> {
  const result = await fetchArticleHint(props.article.id, 'rule')
  if (!result) {
    return null
  }
  return {
    message: result.message,
    hints: result.hints,
  }
}

watch([() => props.article.id, () => gameStore.currentRound], () => {
  clearPendingSelection()
  // 重置 hint 高亮
  hintRanges.value = []
})

onMounted(() => {
  window.addEventListener('scroll', handleViewportChange, { passive: true })
  window.addEventListener('resize', handleViewportChange)
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', handleViewportChange)
  window.removeEventListener('resize', handleViewportChange)
})

// 暴露方法给外部（ArticleOverlay）使用
defineExpose({
  showHintHighlight,
  fetchHintsForModal,
})
</script>

<template>
  <div class="article-scroll-area article-scroll-area--book">
    <article ref="articleElement" class="article-card article-card--book-split">
      <header class="article-book-meta">
        <p class="article-kicker">看山拾取的旅行笔记</p>
        <h2 class="article-title" :class="articleTitleSizeClass">{{ article.title }}</h2>
        <p class="article-newcomer-guide">
          <span>新手指引</span>
          <span>看山拾取了旅行笔记，</span>
          <span>请在文中划线，收集其中隐藏的知识素材。</span>
        </p>
      </header>

      <div class="article-book-body-scroll" @scroll="handleArticleScroll">
        <div class="article-body" @mouseup="handleSelectionEnd">
          <p
            v-for="paragraph in renderedParagraphs"
            :key="`${article.id}-${paragraph.index}`"
            :data-paragraph-index="paragraph.index"
          >
            <template v-for="segment in paragraph.segments" :key="`${paragraph.index}-${segment.start}-${segment.end}-${segment.type}`">
              <span
                :class="segment.type === 'pending'
                  ? 'article-highlight-pending'
                  : segment.type === 'collected'
                    ? 'article-highlight-collected'
                    : segment.type === 'hint'
                      ? 'article-highlight-hint'
                      : 'article-text-normal'"
              >{{ segment.text }}</span>
            </template>
          </p>
        </div>
      </div>

      <div
        v-if="popupPosition && (pendingSelection || selectionFeedback)"
        ref="popupElement"
        class="selection-popup"
        :style="{ top: `${popupPosition.top}px`, left: `${popupPosition.left}px` }"
        @mousedown.stop
        @mouseup.stop
        @click.stop
      >
        <strong v-if="pendingSelection">收集该素材？</strong>
        <div
          v-if="selectionFeedback"
          class="selection-popup-feedback"
          :data-kind="selectionFeedback.kind"
          role="status"
        >
          {{ selectionFeedback.message }}
        </div>
        <div v-if="pendingSelection" class="selection-popup-actions">
          <button type="button" class="popup-button popup-button-cancel" @click="cancelSelection">取消</button>
          <button
            type="button"
            class="popup-button popup-button-confirm"
            :disabled="isSelectionBlocked"
            @click="submitSelection"
          >{{ isSubmitting ? '判定中…' : '提交' }}</button>
        </div>
      </div>
    </article>
  </div>
</template>
