import { defineStore } from 'pinia'
import { watch } from 'vue'
import type { CombinationResult } from '../services/combinationService'
import { syncCombination } from '../services/workspaceApi'
import type { SlotSnapshot } from '../types/workspace'
import { useMaterialStore as getMaterialStore } from './material'
import { useCreationFlowStore as getCreationFlowStore } from './creationFlow'

const MIN_MATERIALS = 2
const MAX_MATERIALS = 3
const VECTOR_SYNC_DEBOUNCE_MS = 400
let slotSyncStop: (() => void) | null = null
let slotSyncTimer: ReturnType<typeof window.setTimeout> | null = null

export const useWorkbenchStore = defineStore('workbench', {
  state: () => ({
    selectedMaterialIds: [] as string[],
    feedback: '',
    lastResult: null as CombinationResult | null,
    /** 后端返回的最近一次即时向量（协议链路3） */
    currentVector: [0, 0] as [number, number],
    isSyncingVector: false,
  }),
  // The watcher is installed by GameView and must be stopped when that route unmounts.
  // Keeping this outside Pinia state avoids serializing timers into devtools/localStorage.
  getters: {
    selectedCount: state => state.selectedMaterialIds.length,
    isFull: state => state.selectedMaterialIds.length >= MAX_MATERIALS,
    canPlay: state => state.selectedMaterialIds.length >= MIN_MATERIALS,
    maxMaterials: () => MAX_MATERIALS,
  },
  actions: {
    addMaterial(materialId: string) {
      if (this.hasMaterial(materialId)) {
        this.feedback = '该素材已在工作台'
        return false
      }

      if (this.isFull) {
        this.feedback = '工作台已满'
        return false
      }

      this.selectedMaterialIds.push(materialId)
      this.feedback = ''
      this.lastResult = null
      return true
    },
    removeMaterial(materialId: string) {
      this.selectedMaterialIds = this.selectedMaterialIds.filter(id => id !== materialId)
      this.feedback = ''
      this.lastResult = null
    },
    clearWorkbench() {
      this.selectedMaterialIds = []
      this.feedback = ''
      this.lastResult = null
    },
    hasMaterial(materialId: string) {
      return this.selectedMaterialIds.includes(materialId)
    },
    setFeedback(message: string) {
      this.feedback = message
    },
    setLastResult(result: CombinationResult) {
      this.lastResult = result
      this.feedback = ''
    },
    /**
     * 将创作流卡槽快照同步到后端（协议链路3：POST /api/workspace/vectors）
     * 卡槽为空时也发送空快照，后端返回零向量（保证 AI 子模块轮询时知北针回中心）。
     */
    async syncSlotsToBackend() {
      const creationStore = getCreationFlowStore()
      const materialStore = getMaterialStore()
      const occupiedSlots = creationStore.slots.filter(slot => slot.materialId !== null)
      const payloadSlots: SlotSnapshot['slots'] = []

      for (const slot of occupiedSlots) {
        const materialId = slot.materialId
        if (materialId === null) {
          continue
        }

        const material = materialStore.getMaterialById(materialId)
        const canonicalCardId = material?.informationPointId?.trim()

        // 自愈：卡槽（game-creation-flow）与素材仓库（game-materials）是两份独立存档，
        // 素材在结算时被消耗后、卡槽要等知北针动画才清空，中间刷新/出发被拦下就会留下
        // “幽灵卡槽”——UI 上显示为空位（无 × 按钮、不可拖出），却能让同步永久失败并锁死提交。
        // 这里剔除失效引用（removeMaterial 内部会持久化），用剩余有效卡槽继续同步。
        if (!material || !canonicalCardId) {
          console.warn(
            '[workbench] Creation Flow 卡槽素材已失效，自动移除:',
            materialId,
            material ? '(缺少 informationPointId)' : '(素材不存在)',
          )
          creationStore.removeMaterial(slot.index)
          this.feedback = `已移除失效的创作流卡槽素材 ${materialId}`
          continue
        }

        payloadSlots.push([String(slot.index), canonicalCardId])
      }

      const snapshot: SlotSnapshot = {
        slots: payloadSlots,
      }

      this.isSyncingVector = true
      try {
        const result = await syncCombination(snapshot)
        this.currentVector = result.instant_vector
        return true
      } catch (error) {
        this.currentVector = [0, 0]
        console.error('[workbench] 卡槽向量同步失败:', error)
        return false
      } finally {
        this.isSyncingVector = false
      }
    },
    /**
     * watchSlotChanges：安装卡槽变更自动同步监听（协议要求）。
     * 一旦创作流卡槽配置增/删/换，立即触发 syncSlotsToBackend()。
     * 需在应用启动时调用一次（App.vue onMounted）。
     */
    setupSlotSync() {
      const creationStore = getCreationFlowStore()
      if (slotSyncStop) {
        return
      }

      slotSyncStop = watch(
        () => creationStore.slots.map(slot => slot.materialId).join('|'),
        () => {
          // 卡槽一旦变化，先撤下旧的预览方向；新的方向必须等后端
          // 返回最新 instant_vector 后才重新可用。
          this.currentVector = [0, 0]
          if (slotSyncTimer !== null) {
            window.clearTimeout(slotSyncTimer)
          }
          slotSyncTimer = window.setTimeout(() => {
            slotSyncTimer = null
            void this.syncSlotsToBackend()
          }, VECTOR_SYNC_DEBOUNCE_MS)
        },
        { immediate: true },
      )
    },
    stopSlotSync() {
      slotSyncStop?.()
      slotSyncStop = null
      if (slotSyncTimer !== null) {
        window.clearTimeout(slotSyncTimer)
        slotSyncTimer = null
      }
    },
  },
})
