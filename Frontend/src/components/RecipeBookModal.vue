<script setup lang="ts">
/** 创作流配方书弹窗：三折页布局，含卡牌介绍、相邻效应、结构配方 */
import { ref, watch } from 'vue'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ close: [] }>()

// 卡牌类型定义
const TYPES: Record<string, string> = {
  V: 'viewpoint', F: 'flaw', E: 'emotion', R: 'rhetoric',
  X: 'forbidden', _: 'empty',
}
const TYPE_LABELS: Record<string, string> = {
  viewpoint: '观', flaw: '漏', emotion: '情', rhetoric: '修',
}

// 7 种配方 + 1 种反例
const RECIPES: Record<string, {
  name: string; subtitle: string; desc: string; tip: string; tipType: string;
  grid: string[][];
}> = {
  refutation: {
    name: '驳论论证', subtitle: '先立靶，再反驳',
    desc: '最前面一行只放漏洞卡（可掺情绪），绝不放观点——这是你要反驳的"靶子"；后面用观点卡逐条猛烈反驳。',
    tip: ' 火力集中、说服力最强，是顶级阵型（×1.15）',
    tipType: 'normal',
    grid: [['X','F','F','F','X'],['V','V','V','V','V'],['_','V','_','V','_'],['X','_','V','_','X']],
  },
  parallel: {
    name: '并列论证', subtitle: '左右对称，多面开花',
    desc: '中间两行的观点卡左右对称成双摆放（位①位⑤、位②↔位④），彼此不挨着；再留一行只放一个观点当"总纲"。',
    tip: '💡 面面俱到、结构均衡，稳扎稳打',
    tipType: 'normal',
    grid: [['X','_','V','_','X'],['V','_','_','_','V'],['V','_','_','_','V'],['X','_','_','_','X']],
  },
  progressive: {
    name: '递进论证', subtitle: '层层错位，步步深入',
    desc: '中间两行多放观点卡，且两行互相错开（既别上下对齐、也别左右挨着），像台阶一样层层推进。',
    tip: '💡 逻辑层层深入，说理透彻',
    tipType: 'normal',
    grid: [['X','_','_','_','X'],['V','_','V','_','_'],['_','V','_','_','V'],['X','_','_','_','X']],
  },
  tot: {
    name: '总-分-总', subtitle: '首尾呼应，中间展开',
    desc: '开头放一个观点点题；中间铺开分论点；结尾再放一个观点收束、呼应开头。',
    tip: '💡 有头有尾、结构完整，最经典的知乎体',
    tipType: 'normal',
    grid: [['X','_','V','_','X'],['_','V','_','V','_'],['_','_','V','_','_'],['X','_','V','_','X']],
  },
  ts: {
    name: '总-分', subtitle: '开头点题，越写越开',
    desc: '开头放一个总观点；结尾一行铺开多个分观点。（中间行可自由放情绪/漏洞/修辞调味）',
    tip: '💡 先抛结论、再展开，干脆利落',
    tipType: 'normal',
    grid: [['X','_','V','_','X'],['_','_','_','_','_'],['_','_','_','_','_'],['X','V','V','V','X']],
  },
  st: {
    name: '分-总', subtitle: '层层铺垫，最后点题',
    desc: '开头铺开多个分观点；结尾收束为一个总观点。（中间行同样可放调味卡）',
    tip: '💡 先分述、后总结，水到渠成',
    tipType: 'normal',
    grid: [['X','V','V','V','X'],['_','_','_','_','_'],['_','_','_','_','_'],['X','_','V','_','X']],
  },
  other: {
    name: '其它', subtitle: '杂乱无章（反面教材）',
    desc: '卡牌随手堆放，凑不成上面任何一种阵型。文章松散、说服力弱——尽量避免落到这一步。',
    tip: '⚠️ 全局乘数仅 ×0.75，效果大打折扣',
    tipType: 'warn',
    grid: [['X','V','E','_','X'],['F','_','V','E','_'],['_','V','F','_','V'],['X','E','_','_','X']],
  },
}

const RECIPE_KEYS = ['refutation', 'parallel', 'progressive', 'tot', 'ts', 'st', 'other']
const currentRecipeKey = ref('refutation')

function switchRecipe(key: string) {
  currentRecipeKey.value = key
}

function navigateRecipe(direction: number) {
  const idx = RECIPE_KEYS.indexOf(currentRecipeKey.value)
  const newIdx = (idx + direction + RECIPE_KEYS.length) % RECIPE_KEYS.length
  currentRecipeKey.value = RECIPE_KEYS[newIdx]
}

const currentRecipe = ref(RECIPES.refutation)

// 监听配方切换
watch(currentRecipeKey, (key) => {
  currentRecipe.value = RECIPES[key]
})

// 相邻效应迷你网格数据
const effectGrids = [
  [['_','_','_'],['_','V','_'],['_','E','_']],
  [['_','_','_'],['_','V','_'],['_','F','_']],
  [['_','_','_'],['_','V','_'],['_','R','_']],
  [['_','_','_'],['_','V','_'],['_','V','_']],
]
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="recipe-book-modal-overlay" @click.self="emit('close')">
      <div class="recipe-book-modal">
        <!-- 关闭按钮 -->
        <button class="recipe-book-modal__close" type="button" aria-label="关闭配方书" @click="emit('close')">✕</button>

        <div class="recipe-book">
          <!-- ═══ 面板 1：四种卡牌 ══ -->
          <div class="recipe-panel">
            <div class="panel-title">
              <span class="panel-title__icon"></span>
              <div>
                <div class="panel-title__eyebrow">CARD_TYPES</div>
                <div class="panel-title__text">四种卡牌</div>
              </div>
            </div>

            <div class="card-intro-grid">
              <div class="card-intro-item">
                <div class="card-intro__swatch swatch--viewpoint">
                  <span class="card-intro__swatch-label">观</span>
                </div>
                <span class="card-intro__name">观点卡</span>
                <span class="card-intro__desc">文章主力<br>罗盘往北推</span>
              </div>
              <div class="card-intro-item">
                <div class="card-intro__swatch swatch--flaw">
                  <span class="card-intro__swatch-label">漏</span>
                </div>
                <span class="card-intro__name">漏洞卡</span>
                <span class="card-intro__desc">犀利找茬<br>罗盘往西偏</span>
              </div>
              <div class="card-intro-item">
                <div class="card-intro__swatch swatch--emotion">
                  <span class="card-intro__swatch-label">情</span>
                </div>
                <span class="card-intro__name">情绪卡</span>
                <span class="card-intro__desc">共鸣热度<br>罗盘往东偏</span>
              </div>
              <div class="card-intro-item">
                <div class="card-intro__swatch swatch--rhetoric">
                  <span class="card-intro__swatch-label">修</span>
                </div>
                <span class="card-intro__name">修辞卡</span>
                <span class="card-intro__desc">催化观点<br>自己不出力</span>
              </div>
            </div>

            <div class="compass-hint">
              <div class="compass-hint__title"> 罗盘指引</div>
              <div class="compass-hint__grid">
                <div class="compass-row">
                  <span class="compass-arrow">⬆️</span>
                  <span class="compass-label">正北</span>
                  <span>答主之路（最理想）</span>
                </div>
                <div class="compass-row">
                  <span class="compass-arrow">↗️</span>
                  <span class="compass-label">东北</span>
                  <span>有观点 + 有热度</span>
                </div>
                <div class="compass-row">
                  <span class="compass-arrow">️</span>
                  <span class="compass-label">西北</span>
                  <span>有观点 + 犀利</span>
                </div>
                <div class="compass-row">
                  <span class="compass-arrow">➡️</span>
                  <span class="compass-label">正东</span>
                  <span>纯情绪 / 流量文</span>
                </div>
                <div class="compass-row">
                  <span class="compass-arrow">⬅️</span>
                  <span class="compass-label">正西</span>
                  <span>纯找茬 / 漏洞文</span>
                </div>
              </div>
            </div>

            <div class="recipe-legend">
              <div class="recipe-legend__item">
                <span class="recipe-legend__swatch" style="background: #5b8fd9"></span>
                <span>观点</span>
              </div>
              <div class="recipe-legend__item">
                <span class="recipe-legend__swatch" style="background: #5aad5a"></span>
                <span>漏洞</span>
              </div>
              <div class="recipe-legend__item">
                <span class="recipe-legend__swatch" style="background: #d95b5b"></span>
                <span>情绪</span>
              </div>
              <div class="recipe-legend__item">
                <span class="recipe-legend__swatch" style="background: #8B6914"></span>
                <span>修辞</span>
              </div>
            </div>
          </div>

          <!-- ═══ 面板 2：相邻效应 ═══ -->
          <div class="recipe-panel">
            <div class="panel-title">
              <span class="panel-title__icon">⚗️</span>
              <div>
                <div class="panel-title__eyebrow">ADJACENT_EFFECTS</div>
                <div class="panel-title__text">相邻效应</div>
              </div>
            </div>

            <div class="reaction-direction-note">
              顶行/底行只和左右邻居反应；中行还能和上下邻居反应。多个相邻同时生效时乘数连乘。
            </div>

            <div class="effect-list">
              <div v-for="(grid, idx) in effectGrids" :key="idx" class="effect-item">
                <div class="effect-mini-grid">
                  <div v-for="(row, rowIdx) in grid" :key="rowIdx" class="effect-mini-row">
                    <div
                      v-for="(cell, cellIdx) in row"
                      :key="cellIdx"
                      class="effect-mini-cell"
                      :class="`effect-mini-cell--${TYPES[cell] || 'empty'}`"
                    >
                      <span v-if="TYPE_LABELS[TYPES[cell]]" class="effect-mini-cell__label">
                        {{ TYPE_LABELS[TYPES[cell]] }}
                      </span>
                    </div>
                  </div>
                </div>
                <div class="effect-info">
                  <div class="effect-name" v-if="idx === 0">观点 ▸ 情绪 → 升温</div>
                  <div class="effect-name" v-else-if="idx === 1">观点 ◇ 漏洞 → 加盐</div>
                  <div class="effect-name" v-else-if="idx === 2">观点 ▸ 修辞 → 增色</div>
                  <div class="effect-name" v-else>观点 ▸ 观点 → 无反应</div>
                  <div class="effect-desc" v-if="idx === 0">文章更热、更有感染力，指针往东偏</div>
                  <div class="effect-desc" v-else-if="idx === 1">文章更犀利、更"盐"，指针往西偏</div>
                  <div class="effect-desc" v-else-if="idx === 2">文采加持，方向不变却更坚定</div>
                  <div class="effect-desc" v-else>同类不产生反应，但分量累加</div>
                </div>
              </div>
            </div>

            <div class="recipe-tip" style="margin-top: auto;">
              💡 一张观点卡可同时被多张邻居影响：想更热就多贴情绪，想更犀利就多贴漏洞
            </div>
          </div>

          <!-- ══ 面板 3：配方图形 ═══ -->
          <div class="recipe-panel">
            <div class="panel-title">
              <span class="panel-title__icon">📖</span>
              <div>
                <div class="panel-title__eyebrow">RECIPES</div>
                <div class="panel-title__text">结构配方</div>
              </div>
            </div>

            <div class="recipe-tabs">
              <button
                v-for="key in RECIPE_KEYS"
                :key="key"
                class="recipe-tab"
                :class="{
                  'recipe-tab--active': currentRecipeKey === key,
                  'recipe-tab--counter': key === 'other',
                }"
                @click="switchRecipe(key)"
              >
                {{ key === 'refutation' ? '驳论' : key === 'parallel' ? '并列' : key === 'progressive' ? '递进' : key === 'tot' ? '总分总' : key === 'ts' ? '总分' : key === 'st' ? '分总' : '杂乱' }}
              </button>
            </div>

            <div class="recipe-detail">
              <div>
                <span class="recipe-name">{{ currentRecipe.name }}</span>
                <span class="recipe-subtitle">{{ currentRecipe.subtitle }}</span>
              </div>

              <div class="recipe-nav">
                <button class="recipe-nav__btn" type="button" title="上一个配方" @click="navigateRecipe(-1)">
                  <svg viewBox="0 0 14 14"><polyline points="9 2 4 7 9 12"/></svg>
                </button>
                <div class="recipe-grid-wrapper" style="flex: 1;">
                  <div class="recipe-grid">
                    <div v-for="(row, rowIdx) in currentRecipe.grid" :key="rowIdx" class="recipe-grid-row">
                      <div
                        v-for="(cell, cellIdx) in row"
                        :key="cellIdx"
                        class="recipe-cell"
                        :class="`recipe-cell--${TYPES[cell] || 'empty'}`"
                      >
                        <span v-if="TYPE_LABELS[TYPES[cell]]" class="recipe-cell__label">
                          {{ TYPE_LABELS[TYPES[cell]] }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
                <button class="recipe-nav__btn" type="button" title="下一个配方" @click="navigateRecipe(1)">
                  <svg viewBox="0 0 14 14"><polyline points="5 2 10 7 5 12"/></svg>
                </button>
              </div>

              <p class="recipe-desc">{{ currentRecipe.desc }}</p>
              <p class="recipe-tip" :class="{ 'recipe-tip--warn': currentRecipe.tipType === 'warn' }">
                {{ currentRecipe.tip }}
              </p>
            </div>

            <div class="recipe-legend">
              <div class="recipe-legend__item">
                <span class="recipe-legend__swatch" style="background: #5b8fd9"></span>
                <span>观点</span>
              </div>
              <div class="recipe-legend__item">
                <span class="recipe-legend__swatch" style="background: #5aad5a"></span>
                <span>漏洞</span>
              </div>
              <div class="recipe-legend__item">
                <span class="recipe-legend__swatch" style="background: #d95b5b"></span>
                <span>情绪</span>
              </div>
              <div class="recipe-legend__item">
                <span class="recipe-legend__swatch" style="background: #8B6914"></span>
                <span>修辞</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* 遮罩层 */
.recipe-book-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(4, 16, 23, 0.75);
  backdrop-filter: blur(4px);
  padding: 40px 20px;
}

/* 弹窗容器 */
.recipe-book-modal {
  position: relative;
  max-width: 95vw;
  max-height: 95vh;
}

/* 关闭按钮 */
.recipe-book-modal__close {
  position: absolute;
  top: -12px;
  right: -12px;
  z-index: 10;
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(170, 133, 83, 0.5);
  border-radius: 50%;
  background: linear-gradient(180deg, #fffef8 0%, #f5ecda 100%);
  color: #5a4030;
  font-size: 0.9rem;
  font-weight: 800;
  cursor: pointer;
  transition: all 100ms ease;
  box-shadow: 1px 2px 0 rgba(106, 77, 43, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.6);
}
.recipe-book-modal__close:hover {
  background: linear-gradient(180deg, #fff 0%, #f8f0dd 100%);
  border-color: rgba(170, 133, 83, 0.7);
  transform: scale(1.05);
}

/* 配方书三折页 */
.recipe-book {
  display: flex;
  border: 1px solid rgba(188, 157, 111, 0.55);
  border-radius: 11px 5px 11px 5px;
  overflow: hidden;
  box-shadow:
    4px 5px 0 rgba(106, 77, 43, 0.12),
    0 16px 36px rgba(82, 62, 39, 0.18),
    inset 0 0 0 1px rgba(255, 255, 255, 0.42);
}

/* 每个面板 */
.recipe-panel {
  width: 390px;
  padding: 24px 21px 21px;
  background:
    linear-gradient(rgba(121, 89, 57, 0.035) 1px, transparent 1px) 0 0 / 14px 14px,
    #f7efd9;
  color: #4b3828;
  display: flex;
  flex-direction: column;
  gap: 15px;
  position: relative;
}
.recipe-panel + .recipe-panel {
  border-left: 1px solid rgba(188, 157, 111, 0.35);
  box-shadow: inset 3px 0 6px -2px rgba(106, 77, 43, 0.1);
}

/* 面板标题 */
.panel-title {
  display: flex;
  align-items: center;
  gap: 9px;
  padding-bottom: 10px;
  border-bottom: 1px dashed rgba(107, 62, 43, 0.25);
}
.panel-title__icon { font-size: 1.6rem; line-height: 1; }
.panel-title__eyebrow {
  width: fit-content;
  border: 1px solid rgba(170, 133, 83, 0.42);
  padding: 2px 6px;
  background: rgba(107, 62, 43, 0.07);
  font: 800 0.66rem/1.2 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.08em;
  color: #806a4e;
  text-transform: uppercase;
  border-radius: 2px;
}
.panel-title__text {
  font: 800 1.14rem/1.2 'Noto Serif SC', 'Songti SC', serif;
  color: #4a3022;
  letter-spacing: 0.03em;
}

/* 卡牌介绍网格 */
.card-intro-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
}
.card-intro-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 9px 9px;
  border: 1px solid rgba(170, 133, 83, 0.3);
  border-radius: 6px 3px 6px 3px;
  background: rgba(255, 250, 240, 0.5);
}
.card-intro__swatch {
  width: 54px;
  height: 54px;
  border-radius: 5px;
  border: 1px solid rgba(255, 255, 255, 0.4);
  box-shadow: 1px 1px 0 rgba(0, 0, 0, 0.12), inset 0 0 0 1px rgba(255, 255, 255, 0.2);
  display: grid;
  place-items: center;
}
.card-intro__swatch-label {
  font: 800 0.75rem/1 'Noto Sans SC', sans-serif;
  color: rgba(255, 255, 255, 0.92);
  text-shadow: 0 1px 1px rgba(0, 0, 0, 0.3);
}
.card-intro__name {
  font: 800 0.9rem/1 'Noto Sans SC', sans-serif;
  color: #4a3022;
}
.card-intro__desc {
  font: 600 0.72rem/1.4 'Noto Sans SC', sans-serif;
  color: #6b5038;
  text-align: center;
}
.swatch--viewpoint { background: #5b8fd9; }
.swatch--flaw { background: #5aad5a; }
.swatch--emotion { background: #d95b5b; }
.swatch--rhetoric { background: #8B6914; }

/* 罗盘指引 */
.compass-hint {
  border-top: 1px dashed rgba(107, 62, 43, 0.22);
  padding-top: 12px;
}
.compass-hint__title {
  font: 800 0.84rem/1.2 'Noto Serif SC', serif;
  color: #4a3022;
  margin-bottom: 7px;
}
.compass-hint__grid {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.compass-row {
  display: flex;
  align-items: center;
  gap: 7px;
  font: 600 0.72rem/1.3 'Noto Sans SC', sans-serif;
  color: #6b5038;
}
.compass-arrow {
  width: 27px;
  text-align: center;
  font-size: 0.97rem;
  flex-shrink: 0;
}
.compass-label {
  font-weight: 800;
  color: #4a3022;
}

/* 相邻效应 */
.effect-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.effect-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 9px 10px;
  border: 1px solid rgba(170, 133, 83, 0.25);
  border-radius: 5px 3px 5px 3px;
  background: rgba(255, 250, 240, 0.4);
}
.effect-mini-grid {
  display: flex;
  flex-direction: column;
  gap: 1px;
  flex-shrink: 0;
}
.effect-mini-row {
  display: flex;
  gap: 1px;
}
.effect-mini-cell {
  width: 24px;
  height: 24px;
  border-radius: 2px;
  display: grid;
  place-items: center;
}
.effect-mini-cell--empty {
  border: 1px dashed rgba(170, 133, 83, 0.25);
  background: rgba(255, 250, 240, 0.3);
}
.effect-mini-cell--viewpoint { background: #5b8fd9; border: 1px solid rgba(255, 255, 255, 0.35); }
.effect-mini-cell--flaw { background: #5aad5a; border: 1px solid rgba(255, 255, 255, 0.35); }
.effect-mini-cell--emotion { background: #d95b5b; border: 1px solid rgba(255, 255, 255, 0.35); }
.effect-mini-cell--rhetoric { background: #8B6914; border: 1px solid rgba(255, 255, 255, 0.35); }
.effect-mini-cell__label {
  font: 800 0.45rem/1 'Noto Sans SC', sans-serif;
  color: rgba(255, 255, 255, 0.9);
  text-shadow: 0 1px 1px rgba(0, 0, 0, 0.3);
}
.effect-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.effect-name {
  font: 800 0.84rem/1.2 'Noto Serif SC', serif;
  color: #4a3022;
}
.effect-desc {
  font: 600 0.69rem/1.4 'Noto Sans SC', sans-serif;
  color: #6b5038;
}
.reaction-direction-note {
  border-top: 1px dashed rgba(107, 62, 43, 0.22);
  padding-top: 10px;
  font: 600 0.69rem/1.5 'Noto Sans SC', sans-serif;
  color: #806a4e;
  font-style: italic;
}

/* 配方 Tab */
.recipe-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.recipe-tab {
  border: 1px solid rgba(170, 133, 83, 0.5);
  border-radius: 5px 3px 5px 3px;
  padding: 7px 15px;
  background: linear-gradient(180deg, rgba(255, 253, 245, 0.9) 0%, rgba(245, 235, 215, 0.8) 100%);
  color: #5a4030;
  font: 800 0.81rem/1.2 'Noto Sans SC', sans-serif;
  cursor: pointer;
  transition: all 100ms ease;
  white-space: nowrap;
  box-shadow: 1px 2px 0 rgba(106, 77, 43, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.6);
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.5);
}
.recipe-tab:hover {
  background: linear-gradient(180deg, #fffef8 0%, #f5ecda 100%);
  border-color: rgba(170, 133, 83, 0.7);
  transform: translateY(-1px);
}
.recipe-tab--active {
  background: linear-gradient(180deg, #7aaa9c 0%, #5e8f80 100%);
  border-color: #4a7a6c;
  color: #fff9e9;
  box-shadow: 1px 2px 0 rgba(60, 90, 75, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.25);
  text-shadow: 0 1px 1px rgba(0, 0, 0, 0.2);
}
.recipe-tab--counter {
  background: linear-gradient(180deg, rgba(255, 235, 230, 0.9) 0%, rgba(240, 210, 200, 0.8) 100%);
  border-color: rgba(200, 100, 80, 0.45);
  color: #a05040;
}
.recipe-tab--counter.recipe-tab--active {
  background: linear-gradient(180deg, #c87060 0%, #b05848 100%);
  border-color: #904030;
  color: #fff9e9;
}

/* 配方详情 */
.recipe-detail {
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.recipe-name {
  font: 900 1.08rem/1.2 'Noto Serif SC', 'Songti SC', serif;
  color: #4a3022;
  letter-spacing: 0.02em;
}
.recipe-subtitle {
  color: #806a4e;
  font: 600 0.81rem/1 'Noto Sans SC', sans-serif;
  margin-left: 6px;
}

/* 导航箭头 */
.recipe-nav {
  display: flex;
  align-items: center;
  gap: 9px;
}
.recipe-nav__btn {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(170, 133, 83, 0.45);
  border-radius: 50%;
  background: linear-gradient(180deg, #fffef8 0%, #f5ecda 100%);
  color: #5a4030;
  cursor: pointer;
  transition: all 100ms ease;
  box-shadow: 1px 2px 0 rgba(106, 77, 43, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.7);
  flex-shrink: 0;
}
.recipe-nav__btn:hover {
  background: linear-gradient(180deg, #fff 0%, #f8f0dd 100%);
  border-color: rgba(170, 133, 83, 0.65);
  transform: translateY(-1px);
}
.recipe-nav__btn svg {
  width: 21px;
  height: 21px;
  stroke: #5a4030;
  stroke-width: 2.5;
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
}

/* 矩阵网格 */
.recipe-grid-wrapper {
  display: flex;
  justify-content: center;
  padding: 6px 0;
}
.recipe-grid {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.recipe-grid-row {
  display: flex;
  gap: 3px;
}
.recipe-cell {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: 3px;
  transition: transform 120ms ease;
}
.recipe-cell:hover {
  transform: scale(1.1);
  z-index: 2;
}
.recipe-cell__label {
  font: 800 0.6rem/1 'Noto Sans SC', sans-serif;
  color: rgba(255, 255, 255, 0.9);
  text-shadow: 0 1px 1px rgba(0, 0, 0, 0.3);
  pointer-events: none;
}
.recipe-cell--viewpoint {
  background: #5b8fd9;
  border: 1px solid rgba(255, 255, 255, 0.4);
  box-shadow: 1px 1px 0 rgba(0, 0, 0, 0.12), inset 0 0 0 1px rgba(255, 255, 255, 0.2);
}
.recipe-cell--flaw {
  background: #5aad5a;
  border: 1px solid rgba(255, 255, 255, 0.4);
  box-shadow: 1px 1px 0 rgba(0, 0, 0, 0.12), inset 0 0 0 1px rgba(255, 255, 255, 0.2);
}
.recipe-cell--emotion {
  background: #d95b5b;
  border: 1px solid rgba(255, 255, 255, 0.4);
  box-shadow: 1px 1px 0 rgba(0, 0, 0, 0.12), inset 0 0 0 1px rgba(255, 255, 255, 0.2);
}
.recipe-cell--rhetoric {
  background: #8B6914;
  border: 1px solid rgba(255, 255, 255, 0.4);
  box-shadow: 1px 1px 0 rgba(0, 0, 0, 0.12), inset 0 0 0 1px rgba(255, 255, 255, 0.2);
}
.recipe-cell--forbidden {
  background: repeating-linear-gradient(
    45deg,
    rgba(74, 56, 40, 0.16),
    rgba(74, 56, 40, 0.16) 2px,
    rgba(74, 56, 40, 0.05) 2px,
    rgba(74, 56, 40, 0.05) 4px
  );
  border: 1px solid rgba(74, 56, 40, 0.18);
}
.recipe-cell--empty {
  border: 1px dashed rgba(170, 133, 83, 0.28);
  background: rgba(255, 250, 240, 0.35);
}

.recipe-desc {
  color: #5d4834;
  font: 600 0.87rem/1.5 'Noto Sans SC', sans-serif;
  margin: 0;
}
.recipe-tip {
  color: #6d886e;
  font: 700 0.78rem/1.35 'Noto Sans SC', sans-serif;
  margin: 0;
  padding: 4px 9px;
  background: rgba(109, 136, 110, 0.07);
  border-left: 3px solid rgba(109, 136, 110, 0.35);
  border-radius: 0 3px 3px 0;
}
.recipe-tip--warn {
  color: #a06050;
  background: rgba(217, 91, 91, 0.06);
  border-left-color: rgba(217, 91, 91, 0.35);
}

/* 图例 */
.recipe-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  border-top: 1px dashed rgba(107, 62, 43, 0.22);
  padding-top: 10px;
}
.recipe-legend__item {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #6b5038;
  font: 700 0.69rem/1 'Noto Sans SC', sans-serif;
}
.recipe-legend__swatch {
  display: inline-block;
  width: 13px;
  height: 13px;
  border-radius: 2px;
  border: 1px solid rgba(0, 0, 0, 0.12);
}

/* 响应式 */
@media (max-width: 1350px) {
  .recipe-book {
    flex-direction: column;
    max-width: 450px;
  }
  .recipe-panel { width: 100%; }
  .recipe-panel + .recipe-panel {
    border-left: none;
    border-top: 1px solid rgba(188, 157, 111, 0.35);
  }
}
</style>
