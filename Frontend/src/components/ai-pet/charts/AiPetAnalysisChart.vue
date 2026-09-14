<script setup lang="ts">
/**
 * AI Pet Analysis Chart - 网页 AI 宠物联动分析图表组件
 * 
 * 紧凑版（200x200 桌面宠物内嵌）：
 * - 仅保留指北针圆形图表 + 悬浮文字标签
 * - 去除所有外部容器/标题/调试面板
 * - 纯被动渲染：接收 props.data → ECharts 重绘
 */

import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import type { EChartsType } from 'echarts'

// TypeScript 接口定义
export interface ChartData {
  x: number
  y: number
}

// Props 定义
const props = defineProps<{
  data?: ChartData
  width?: string | number
  height?: string | number
}>()

// 内部状态：接收父组件传入的显示向量，触发 ECharts 重绘
const chartData = ref<ChartData>(props.data ?? { x: 0, y: 0 })

// 监听 props 变化，同步到内部状态
watch(
  () => props.data,
  (newVal) => {
    if (newVal) {
      chartData.value = newVal
    }
  }
)

// 悬浮状态：控制正立标签图层的显示/隐藏
const isHovered = ref(false)

// ECharts 实例引用
const chartContainer = ref<HTMLDivElement>()
let myChart: EChartsType | null = null

/**
 * 初始化图表 - 指北针风格
 */
const initChart = () => {
  if (!chartContainer.value) return

  myChart = echarts.init(chartContainer.value)

  const option = {
    // 隐藏默认网格
    grid: {
      left: 0,
      right: 0,
      top: 0,
      bottom: 0,
      containLabel: false
    },

    // X Axis
    xAxis: {
      show: true,
      splitLine: { show: false },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      min: -1.8,
      max: 1.8
    },

    // Y Axis
    yAxis: {
      show: true,
      splitLine: { show: false },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      min: -1.8,
      max: 1.8
    },

    // 坐标系提示框
    tooltip: {
      show: false
    },

    series: [
      {
        // 第一象限 45° 对称扇形（盐度+热度双高区域）
        name: '45°扇形区域',
        type: 'custom',
        coordinateSystem: 'cartesian2d',
        renderItem: (_params: any, api: any) => {
          const sectorPoints = generateSectorPoints(1, 35, 55)
          const pixelPoints = sectorPoints.map((p: number[]) => api.coord(p))
          return {
            type: 'polygon',
            shape: { points: pixelPoints },
            style: {
              fill: 'rgba(24, 144, 255, 0.15)',
              stroke: 'rgba(24, 144, 255, 0.5)',
              lineWidth: 1.5
            }
          }
        },
        data: [[0, 0]],
        emphasis: {
          disabled: true
        },
        silent: true
      },
      {
        // 外围实线圆周
        name: '外圆',
        type: 'line',
        coordinateSystem: 'cartesian2d',
        showSymbol: false,
        smooth: true,
        data: generateCirclePoints(1),
        lineStyle: {
          color: '#1890FF',
          width: 2,
          type: 'solid'
        },
        emphasis: {
          disabled: true
        },
        silent: true
      },
      {
        // NE 方向箭头 (45°) - 高热
        name: '箭头-NE',
        type: 'line',
        coordinateSystem: 'cartesian2d',
        showSymbol: false,
        data: [
          [0.85, 0],
          [0.95, 0]
        ],
        lineStyle: {
          color: '#1e293b',
          width: 2
        },
        symbol: ['none', 'arrow'],
        symbolSize: [12, 12],
        symbolOffset: [0, -6],
        emphasis: {
          disabled: true
        },
        silent: true
      },
      {
        // SE 方向箭头 (135°) - 低盐
        name: '箭头-SE',
        type: 'line',
        coordinateSystem: 'cartesian2d',
        showSymbol: false,
        data: [
          [0, -0.85],
          [0, -0.95]
        ],
        lineStyle: {
          color: '#1e293b',
          width: 2
        },
        symbol: ['none', 'arrow'],
        symbolSize: [12, 12],
        symbolOffset: [0, -6],
        emphasis: {
          disabled: true
        },
        silent: true
      },
      {
        // SW 方向箭头 (225°) - 低热
        name: '箭头-SW',
        type: 'line',
        coordinateSystem: 'cartesian2d',
        showSymbol: false,
        data: [
          [-0.85, 0],
          [-0.95, 0]
        ],
        lineStyle: {
          color: '#1e293b',
          width: 2
        },
        symbol: ['none', 'arrow'],
        symbolSize: [12, 12],
        symbolOffset: [0, -6],
        emphasis: {
          disabled: true
        },
        silent: true
      },
      {
        // NW 方向箭头 (315°) - 高盐
        name: '箭头-NW',
        type: 'line',
        coordinateSystem: 'cartesian2d',
        showSymbol: false,
        data: [
          [0, 0.85],
          [0, 0.95]
        ],
        lineStyle: {
          color: '#1e293b',
          width: 2
        },
        symbol: ['none', 'arrow'],
        symbolSize: [12, 12],
        symbolOffset: [0, -6],
        emphasis: {
          disabled: true
        },
        silent: true
      },
      {
        // 实时向量指针 - 红色三角形（指南针指针形状）
        name: '向量指针-三角形',
        type: 'custom',
        coordinateSystem: 'cartesian2d',
        renderItem: (_params: any, api: any) => {
          const xVal = normalizedData.value.x
          const yVal = normalizedData.value.y

          const start = api.coord([0, 0])
          const end = api.coord([xVal, yVal])

          const dx = end[0] - start[0]
          const dy = end[1] - start[1]
          const angle = Math.atan2(dy, dx)
          const length = Math.sqrt(dx * dx + dy * dy)

          // 向量太短时不绘制三角形，只显示圆点
          if (length < 5) return null

          // 三角形底边宽度（像素）
          const baseWidth = 12
          // 垂直于向量方向的单位向量分量
          const perpX = -Math.sin(angle) * baseWidth / 2
          const perpY = Math.cos(angle) * baseWidth / 2

          // 三角形底边距离原点的偏移（让圆点覆盖底边）
          // 收回底边偏移，使三角形与固定尺寸的轴心球保持视觉连接。
          const baseDist = 4
          const baseX = start[0] + Math.cos(angle) * baseDist
          const baseY = start[1] + Math.sin(angle) * baseDist

          // 三角形三个顶点：两个底角 + 尖端
          const p1: [number, number] = [baseX + perpX, baseY + perpY]
          const p2: [number, number] = [baseX - perpX, baseY - perpY]
          const tip: [number, number] = [end[0], end[1]]

          return {
            type: 'polygon',
            shape: {
              points: [p1, p2, tip]
            },
            style: {
              fill: '#FF0000',
              stroke: '#1e293b',
              lineWidth: 1.5
            }
          }
        },
        data: [[normalizedData.value.x, normalizedData.value.y]],
        emphasis: {
          disabled: true
        },
        silent: true
      },
      {
        // 实时向量指针 - 深蓝圆（原点处的圆点）
        name: '向量指针-圆',
        type: 'scatter',
        coordinateSystem: 'cartesian2d',
        data: [[0, 0]],
        symbolSize: 13.5,
        itemStyle: {
          color: '#000000', //#001a66 深蓝
          borderColor: '#1e293b',
          borderWidth: 1.5
        },
        emphasis: {
          disabled: true
        },
        silent: true
      }
    ]
  }

  myChart.setOption(option)
}

/**
 * 生成扇形区域数据点（从原点出发到圆弧）
 * @param radius 扇形半径
 * @param startAngle 起始角度（度）
 * @param endAngle 结束角度（度）
 */
const generateSectorPoints = (radius: number, startAngle: number, endAngle: number): number[][] => {
  const points: number[][] = []
  // 从原点开始
  points.push([0, 0])
  const steps = 30
  for (let i = 0; i <= steps; i++) {
    const angle = ((startAngle + (i / steps) * (endAngle - startAngle)) * Math.PI) / 180
    points.push([radius * Math.cos(angle), radius * Math.sin(angle)])
  }
  return points
}

/**
 * 生成圆形数据点
 */
const generateCirclePoints = (radius: number): number[][] => {
  const points: number[][] = []
  const steps = 100
  for (let i = 0; i <= steps; i++) {
    const angle = (i / steps) * 2 * Math.PI
    const x = radius * Math.cos(angle)
    const y = radius * Math.sin(angle)
    points.push([x, y])
  }
  return points
}

/**
 * 更新向量指针数据
 */
const updateVector = () => {
  if (!myChart) return

  myChart.setOption({
    series: [
      {}, // 45°扇形不变
      {}, // 外圆不变
      {}, // 箭头-NE不变
      {}, // 箭头-SE不变
      {}, // 箭头-SW不变
      {}, // 箭头-NW不变
      {
        // 更新三角形数据，触发重绘
        data: [[normalizedData.value.x, normalizedData.value.y]]
      },
      {}  // 圆不变（始终在原点）
    ]
  } as any)
}

// 生命周期钩子
onMounted(() => {
  initChart()
  
  // 监听窗口大小变化
  window.addEventListener('resize', () => {
    myChart?.resize()
  })
})

onUnmounted(() => {
  myChart?.dispose()
})

// 监听数据变化并更新图表
watch(chartData, () => {
  updateVector()
}, { deep: true })

/**
 * 绘图归一化（不修改原始 instant_vector）：
 * 后端已统一除以 50 缩放，前端只需保证绘图值落在 ECharts ±1.8 坐标系内：
 * - 模长 > 1 → 化为单位方向向量（防止超出图表范围）
 * - 模长 ≤ 1 → 保持不变（已在合理绘图范围）
 */
const normalizedData = computed(() => {
  const x = chartData.value.x
  const y = chartData.value.y
  const magnitude = Math.sqrt(x * x + y * y)
  let result: { x: number; y: number }
  if (magnitude === 0) {
    result = { x: 0, y: 0 }
  } else if (magnitude > 1) {
    result = { x: x / magnitude, y: y / magnitude }
  } else {
    result = { x, y }
  }
  return result
})
</script>

<template>
  <!-- 
    紧凑版模板：仅包含 SVG/ECharts 容器 + 悬浮标签层
    无外部 padding/margin，直接由父容器控制尺寸
  -->
  <div
    class="relative w-full h-full select-none"
    @mouseenter="isHovered = true"
    @mouseleave="isHovered = false"
  >
    <!-- ECharts 容器：带 -rotate-45 实现整体逆时针旋转 45° -->
    <div class="w-full h-full -rotate-45">
      <div
        ref="chartContainer"
        class="w-full h-full"
      />
    </div>

    <!-- 悬浮文字标签图层：pointer-events-none 避免遮挡图表交互 -->
    <div v-show="isHovered" class="absolute inset-0 pointer-events-none z-10">

      <!-- ================= 4个正方向分区标签（通过百分比牢牢锁死在正方形边缘内侧） ================= -->
      <!-- 正上方 (12点钟) -->
      <div class="absolute top-[2%] left-1/2 -translate-x-1/2 text-[10px] font-semibold text-slate-800 whitespace-nowrap">
        列观点💡
      </div>
      <!-- 蓝色扇形内的"答主之路"竖排紫色字 -->
      <div
        class="absolute top-[22.5%] left-1/2 -translate-x-1/2 text-[8px] font-bold text-purple-500 tracking-widest"
        style="writing-mode: vertical-rl;"
      >
        答主之路
      </div>
      <!-- 正下方 (6点钟) -->
      <div class="absolute bottom-[2%] left-1/2 -translate-x-1/2 text-[10px] font-semibold text-slate-800 whitespace-nowrap">
        知识的荒原🏜️
      </div>
      <!-- 正左方 (9点钟) -->
      <div class="absolute left-[2%] top-1/2 -translate-y-1/2 text-[10px] font-semibold text-slate-800 whitespace-nowrap">
        挑漏洞🔓
      </div>
      <!-- 正右方 (3点钟) -->
      <div class="absolute right-[2%] top-1/2 -translate-y-1/2 text-[10px] font-semibold text-slate-800 whitespace-nowrap">
        上情绪❤️
      </div>

      <!-- ================= 4个斜方向轴端标签（通过对称的百分比锁定在正方形的四个角落） ================= -->
      <!-- 东北方向 (1点半钟) -->
      <div class="absolute top-[8%] right-[8%] text-[9px] font-medium text-slate-700 whitespace-nowrap">
        高热🌡️
      </div>
      <!-- 西北方向 (10点半钟) -->
      <div class="absolute top-[8%] left-[8%] text-[9px] font-medium text-slate-700 whitespace-nowrap">
        高盐🧂
      </div>
      <!-- 西南方向 (7点半钟) -->
      <div class="absolute bottom-[8%] left-[8%] text-[9px] font-medium text-slate-700 whitespace-nowrap">
        低热❄️
      </div>
      <!-- 东南方向 (4点半钟) -->
      <div class="absolute bottom-[8%] right-[8%] text-[9px] font-medium text-slate-700 whitespace-nowrap">
        低盐💧
      </div>

    </div>
  </div>
</template>

<style scoped>
/* 额外确保graphic元素的文字不会被容器overflow影响 */
:deep(.echarts-tooltip) {
  border-radius: 8px !important;
  padding: 8px 12px !important;
}
</style>
