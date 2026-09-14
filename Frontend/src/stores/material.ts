import { defineStore } from 'pinia'
import type { Material } from '../types/material'
import { useAchievementStore as getAchievementStore } from './achievements'

const STORAGE_KEY = 'game-materials'
export const BACKPACK_CAPACITY = 20

export type AddMaterialResult = 'added' | 'duplicate' | 'full'

function isCanonicalCardId(value: string) {
  // Backend article data uses IDs such as article_1_card_1.  This narrow
  // compatibility check is only for old persisted materials that predate
  // informationPointId; unique instance IDs do not match this shape.
  return /^article_[^|]+_card_[^|]+$/.test(value)
}

function loadMaterials(): Material[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []

    return parsed.flatMap((item): Material[] => {
      if (
        typeof item !== 'object'
        || item === null
        || typeof item.id !== 'string'
        || typeof item.articleId !== 'string'
        || typeof item.text !== 'string'
      ) {
        return []
      }

      const record = item as Partial<Material> & Pick<Material, 'id' | 'articleId' | 'text'>
      const informationPointId = typeof record.informationPointId === 'string'
        ? record.informationPointId.trim()
        : isCanonicalCardId(record.id)
          ? record.id
          : ''

      if (!informationPointId) {
        return []
      }

      return [{ ...record, informationPointId } as Material]
    })
  } catch {
    return []
  }
}

function persistMaterials(materials: Material[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(materials))
  } catch {
    // Keep the in-memory inventory usable if browser storage is unavailable.
  }
}

export const useMaterialStore = defineStore('materials', {
  state: () => ({
    materials: loadMaterials(),
  }),
  getters: {
    getMaterialById: state => (materialId: string) => (
      state.materials.find(material => material.id === materialId)
    ),
  },
  actions: {
    addMaterial(material: Material) {
      if (this.materials.some(existing => existing.id === material.id)) {
        return 'duplicate' as AddMaterialResult
      }

      if (this.materials.length >= BACKPACK_CAPACITY) {
        return 'full' as AddMaterialResult
      }

      this.materials.push(material)
      persistMaterials(this.materials)
      getAchievementStore().recordSuccessfulCollection(material)
      return 'added' as AddMaterialResult
    },
    hasMaterial(articleId: string, informationPointId: string) {
      return this.materials.some(material => (
        material.articleId === articleId
        && material.informationPointId === informationPointId
      ))
    },
    clearMaterials() {
      this.materials = []
      persistMaterials(this.materials)
    },
    consumeMaterials(materialIds: readonly string[]) {
      const idsToConsume = new Set(materialIds.filter(id => typeof id === 'string' && id.length > 0))
      if (idsToConsume.size === 0) return 0

      const previousCount = this.materials.length
      this.materials = this.materials.filter(material => !idsToConsume.has(material.id))
      const consumedCount = previousCount - this.materials.length
      if (consumedCount > 0) {
        persistMaterials(this.materials)
      }
      return consumedCount
    },
  },
})
