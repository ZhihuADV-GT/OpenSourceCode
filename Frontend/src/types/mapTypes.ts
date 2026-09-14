/** 游戏地图与象限的单一领域定义。 */
export type QuadrantType = 'view' | 'critique' | 'emotion' | 'wasteland'
export type BiomeType = 'ocean' | 'glacier' | 'volcano' | 'desert'

export type Direction =
  | 'up'
  | 'down'
  | 'left'
  | 'right'
  | 'up-left'
  | 'up-right'
  | 'down-left'
  | 'down-right'

export interface MountainPosition {
  row: number
  col: number
  direction: Direction
  isMoving: boolean
  targetRow?: number
  targetCol?: number
}

export interface MoveRecord {
  round: number
  vector: [number, number]
  fromRow: number
  fromCol: number
  toRow: number
  toCol: number
  direction: Direction
  timestamp: number
}

export interface JourneyDirection {
  rowDelta: -1 | 0 | 1
  colDelta: -1 | 0 | 1
  screenDirection: Direction
  /** CSS rotation from the compass' north-facing zero angle. */
  compassAngle: number
}

export interface QuadrantConfig {
  id: QuadrantType
  name: string
  shortName: string
  color: string
}

export interface RegionVisualConfig {
  quadrant: QuadrantType
  biome: BiomeType
  className: string
  assetKey: BiomeType
}

export const MAP_SIZE = 10
export const MAP_CENTER = Math.floor(MAP_SIZE / 2)
export const VECTOR_EPSILON = 1e-6

/** 统一判断预览/提交向量是否足以形成可执行方向。 */
export function isNonZeroVector(vector: [number, number]): boolean {
  return Number.isFinite(vector[0])
    && Number.isFinite(vector[1])
    && Math.hypot(vector[0], vector[1]) > VECTOR_EPSILON
}

export const QUADRANT_CONFIGS: readonly QuadrantConfig[] = [
  { id: 'view', name: '观点海洋', shortName: 'VIEW', color: '#4c9b91' },
  { id: 'critique', name: '盐度冰川', shortName: 'CRITIQUE', color: '#ffffff' },
  { id: 'emotion', name: '情绪火山', shortName: 'EMOTION', color: '#d85f59' },
  { id: 'wasteland', name: '知识荒原', shortName: 'WASTELAND', color: '#d39a55' },
] as const

export const QUADRANT_NAME: Record<QuadrantType, string> = {
  view: '观点海洋',
  critique: '盐度冰川',
  emotion: '情绪火山',
  wasteland: '知识荒原',
}

/** 玩法象限到视觉地貌的唯一映射；地貌不改变象限判定或移动坐标。 */
export const REGION_VISUAL_CONFIG: Record<QuadrantType, RegionVisualConfig> = {
  view: { quadrant: 'view', biome: 'ocean', className: 'map-biome--ocean', assetKey: 'ocean' },
  critique: { quadrant: 'critique', biome: 'glacier', className: 'map-biome--glacier', assetKey: 'glacier' },
  emotion: { quadrant: 'emotion', biome: 'volcano', className: 'map-biome--volcano', assetKey: 'volcano' },
  wasteland: { quadrant: 'wasteland', biome: 'desert', className: 'map-biome--desert', assetKey: 'desert' },
}

/**
 * 所有 UI 都使用这一个向量象限判定：vector = [热度, 盐度]（对齐后端 x=heat, y=salt）。
 * 零向量属于低盐低热的"知识的荒原"。单轴为零时，非零轴仍决定方向。
 */
export function getQuadrantByVector(vector: [number, number]): QuadrantType {
  const [heat, salt] = vector

  if (salt === 0 && heat === 0) {
    return 'wasteland'
  }

  if (salt >= 0 && heat >= 0) {
    return 'view'
  }

  if (salt >= 0 && heat < 0) {
    return 'critique'
  }

  if (salt < 0 && heat >= 0) {
    return 'emotion'
  }

  return 'wasteland'
}

/** 将地图格子映射回同一套"盐度/热度"语义，避免各 UI 各判一套。 */
export function getQuadrantByMapPosition(row: number, col: number): QuadrantType {
  // 偶数边长没有中心格，几何中心落在格线之间；按半格索引取偏移，四象限才会等分并对齐参考轴。
  // 向量格式 [heat, salt] 对齐后端 x=heat, y=salt 约定。
  const center = (MAP_SIZE - 1) / 2
  return getQuadrantByVector([
    center - row,  // heat: row 越小（上方）热度越高
    center - col,  // salt: col 越小（左方）盐度越高
  ])
}

export function getQuadrantName(quadrant: QuadrantType): string {
  return QUADRANT_NAME[quadrant]
}

const COMPASS_ANGLE_BY_DIRECTION: Record<Direction, number> = {
  up: 0,
  down: 180,
  left: -90,
  right: 90,
  'up-left': -60,
  'up-right': 60,
  'down-left': -120,
  'down-right': 120,
}

/**
 * 向量到旅途方向的唯一语义映射。
 *
 * heat > 0 → row - 1 → 屏幕右上
 * salt > 0 → col - 1 → 屏幕左上
 *
 * CompassButton and grid movement both consume this record so they cannot
 * silently diverge through separate sign or projection formulas.
 */
export function getJourneyDirectionByVector(vector: [number, number]): JourneyDirection {
  const [heat, salt] = vector
  const rowDelta: -1 | 0 | 1 = heat === 0 ? 0 : heat > 0 ? -1 : 1
  const colDelta: -1 | 0 | 1 = salt === 0 ? 0 : salt > 0 ? -1 : 1

  let screenDirection: Direction = 'down'
  if (rowDelta < 0 && colDelta < 0) screenDirection = 'up'
  else if (rowDelta < 0 && colDelta > 0) screenDirection = 'right'
  else if (rowDelta > 0 && colDelta < 0) screenDirection = 'left'
  else if (rowDelta > 0 && colDelta > 0) screenDirection = 'down'
  else if (rowDelta < 0) screenDirection = 'up-right'
  else if (rowDelta > 0) screenDirection = 'down-left'
  else if (colDelta < 0) screenDirection = 'up-left'
  else if (colDelta > 0) screenDirection = 'down-right'

  return {
    rowDelta,
    colDelta,
    screenDirection,
    compassAngle: rowDelta === 0 && colDelta === 0
      ? 0
      : COMPASS_ANGLE_BY_DIRECTION[screenDirection],
  }
}

/** 向量决定一次最多一格的逻辑方向；原始向量本身不会被破坏性量化。 */
export function getDirectionByVector(vector: [number, number]): Direction {
  return getJourneyDirectionByVector(vector).screenDirection
}

export function getTargetPosition(
  position: Pick<MountainPosition, 'row' | 'col'>,
  vector: [number, number],
): { row: number; col: number } {
  const { rowDelta, colDelta } = getJourneyDirectionByVector(vector)

  return {
    row: Math.max(0, Math.min(MAP_SIZE - 1, position.row + rowDelta)),
    col: Math.max(0, Math.min(MAP_SIZE - 1, position.col + colDelta)),
  }
}
