# CyberJudger Frontend

The project is currently maintained as a Vue 3 frontend on the `migration/vue3` branch. The original React scaffold remains in Git history at `419c84f`.

Current frontend stack and project status are documented below. The old React plugin notes from the scaffold are no longer authoritative.

- React source remains available in Git history only; current development and verification use Vue 3.
- The old React scaffold notes are kept only as historical context.

## Migration Note

React source remains available in Git history only. Current development and verification use the Vue 3 implementation.

## Oxlint Configuration Reference

If type-aware lint rules are enabled later, the configuration can be extended with `oxlint-tsgolint` and `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "typescript/no-explicit-any": "warn"
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.

## Current Frontend Stack

- Vue 3
- TypeScript
- Vite
- Pinia
- Axios（Stroke Judge 已通过 `/api` 接入真实后端；Creation 仍 pending）
- TailwindCSS / CSS UI foundation

Vue 迁移和 Week 1 Demo 已完成并保留在本地 Git 历史中；当前 Phase 7 UI 优化改动仍处于未提交状态。

## Current Demo Architecture

```text
Article JSON
    ↓
Article Service
    ↓
ArticlePanel
    ↓
Selection + Selection Popup
    ↓
Stroke Judge Service Adapter
    ↓
POST /api/judge → Vite Proxy → http://localhost:8000
    ↓
Backend Salt Card → Frontend Salt Card Adapter
    ↓
Material Store
    ↓
Backpack
    ↓
Creation Flow Store
    ↓
Fixed Creation Flow (Slot 1–5)
    ↓
serializeSlots() → { index, cardId }
```

当前文章 source 仍来自本地 mock，Phase 8C-A 只把 Stroke Judge 接到真实后端，不接入 `/api/articles`。新的 Backpack → Creation Flow 主路径不依赖旧 Workbench。旧 `judgeSelection()`、Workbench Store、Combination Service 和 Numeric Judge 作为 legacy/reference path 保留，但默认 Article → Backpack 路径不再调用本地 judge。Creation service 继续保持 `BACKEND_ENDPOINT_PENDING`。

## Week 1 MVP

- 1 篇文章
- 预设 LineSpot 信息点
- Selection Popup
- 本地 Material 生成
- 动态 Backpack
- 2–3 张 Material 组合出牌
- 集中配置的 Prototype Rule Engine
- Local Numeric Judge
- `targetValue` 结果比较
- Creation 无外部 API；Stroke Judge 通过真实后端接口
- 无局外 Meta Progression

### Prototype Combination Rules

以下规则明确标记为 `PROTOTYPE ONLY`，不是最终游戏数值：

- 3 种不同素材类型：`+20`，多角度组合
- 观点卡 + 漏洞卡：`+20`，观点核验
- 观点卡 + 修辞卡：`+10`，表达拆解
- 情绪卡 + 修辞卡：`+15`，情绪识别
- 只取最高匹配 Bonus，不叠加多个规则

```text
finalValue >= targetValue       → success
finalValue >= targetValue * 0.8 → partial
otherwise                       → fail
```

## Known Data Issue

文章 `article_002` 存在独立的 LineSpot 数据问题：

```text
linespot.start/end 与 canonicalContent 的稳定语义范围不一致
```

Phase 5.2 的诊断结论为：

```text
Content Version / Offset Source Mismatch
```

已经排除前端 Adapter 中的 `trim/split/join` 改写，也无法由单纯 CRLF 或 Markdown stripping 稳定解释全部 7 个范围。当前前端保留 `canonicalContent` 架构，并在 DEV Debug 面板中显示 RAW、CRLF candidate 和 Markdown candidate。不要人工修改原始 JSON offset；正确的 LineSpot 数据需要由数据或策划侧重新生成或确认。

## Player State Boundary

Week 1 不实现以下局外状态：

- 答题力
- 粉丝数
- 体力
- 跨局累积
- LocalStorage Meta Progression
- Achievement Unlock

这些状态属于未来的 Meta Progression，不会混入当前 Week 1 Pinia 游戏状态。

## Phase 7 — HUD / Card UX Polish

本阶段只优化 Vue 前端的 HUD 与卡片交互表现，不新增 gameplay 规则或数据流：

- AI 观察员支持本地折叠 / 展开，并提供按钮状态和辅助标签
- Backpack 改为横向卡片轮播，支持 CSS Scroll Snap、左右箭头、当前位置和少量卡片圆点导航
- Workbench 使用紧凑的 3 Slot 卡片布局，Material → Workbench 的加入、移除和组合逻辑保持不变
- Numeric Judge 结果优先显示状态，再突出 `Final / Target`，未出牌时显示等待状态
- 左侧 HUD 保留 sticky 和内部滚动，同时降低信息密度，补齐触屏、键盘焦点和响应式适配
- 右侧面板只做间距微调，不增加新的功能逻辑

本阶段没有加入 AI、后端、拖拽、CreationArea 生成逻辑或新的 gameplay 系统。

## Phase 7.1 Hotfix — Workbench Horizontal Slot Scrolling

修复 Workbench Slot 在左侧 HUD 中被裁剪的问题：

- Slot Track 改为独立的 flex 横向滚动容器
- 保留 mouse / trackpad 横向滚动、touch swipe 和 CSS Scroll Snap
- 三个 Slot 始终渲染，窄栏中单个 Slot 使用约 80% 宽度并露出下一张提示
- 只有 Slot Track 横向移动，组合按钮和 Numeric Judge 保持正常宽度
- 移除原有桌面 / 平板 / 移动端 3 / 2 / 1 列 Grid 覆盖，不改变任何 gameplay 状态

## Phase 7.2 — Immersive HUD & Collection Motion

本阶段继续保持 UI / UX / Motion 范围，不进入 Phase 8：

- AI Assistant 折叠后收缩为 48px 图标按钮，展开 / 收起保持本地 UI 状态
- 成功收集后，从 Selection Anchor Rect 飞出轻量 Material Token，飞向 Backpack 区域并触发轻微 pulse
- Material 仍然立即写入 Store，飞行动画使用 UI-only overlay，不参与 gameplay state
- 动画支持连续收集队列、`prefers-reduced-motion` 降级和 `pointer-events: none`
- 减少桌面端外侧 gutter，适当增加左右 HUD 宽度，保持中央文章阅读宽度
- GameLayout 使用共享 CSS 背景，左右 HUD 保持半透明悬浮层，Article 保持近不透明工作区
- 通过 CSS Variables 集中背景、HUD、Workspace 和 accent 主题值，为未来主题替换预留空间

本阶段没有加入 AI Response、后端、API、Mission Progression、Gameplay 数值更新或像素风资源。

## Phase 7.3 — Visual Direction Prototype + Art Integration Shell

本阶段先建立以下视觉方向原型；Phase 7.3.1 进一步完成了视觉对比度验收修正：

```text
Digital Investigation
        +
Floating HUD
        +
Light Pixel UI
```

已完成的原型范围：

- 整理统一的 Game / HUD / Workspace / UI Visual Tokens
- 为 AIHelper、Backpack、MissionTracker 增加一致的 HUD Header、边框和轻切角语言
- 将 AI 图标替换为带 `TEMPORARY FRONTEND PLACEHOLDER` 标记的 inline SVG Pixel Bot 原型
- Mission Header 使用 `MISSION_01` 终端式展示；Backpack 使用 `BACKPACK`，避免把素材数量伪装成真实数据
- MaterialCard 增加 `frame`、`type-icon`、`rarity`、`content`、`actions` 等 Art Integration Shell
- 创建 `src/assets/` 下的 UI、Card、AI 资源目录和前端美术接入说明
- Article 继续使用现代阅读字体和近不透明 Workspace，没有 Pixel Font、CRT、Scanline 或强霓虹效果

正式 Card Art、AI Avatar、Type Icon 和 Rarity Decoration 由专门美术流程负责；前端只提供容器、Asset Slot、加载边界、响应式和状态展示。本阶段没有加入新的 gameplay logic。

### Phase 7.3.1 — Visual Contrast Pass

Phase 7.3 的技术结构已通过，但初版页面的人工视觉差异不足，因此本阶段进行集中对比度修正：

- 页面背景改为明显的深蓝灰 / 深海军蓝数字调查环境，保留网格、节点和静态渐变层
- Left / Right HUD 改为暗色半透明 Surface，统一浅色正文、蓝灰次级文字和 cyan / teal accent
- HUD 面板增加可见 Header Bar、顶部 accent line、状态块和轻量像素角标，形成统一 System UI
- Article 保持近白高可读性，并增加 `ARTICLE_ANALYSIS` 文档窗口头部和更强前景阴影
- Pixel UI 只保留在角标、Header、AI 图标和小型状态指示器，不扩散到文章正文
- `ART SLOT` 占位降低视觉权重，MaterialCard 正式美术边界不在本阶段重新设计
- 未修改 Selection、Popup、Material Flight、Backpack、Carousel、Workbench、Combination、Numeric Judge 和 Responsive 行为

本阶段目标是让用户不查看代码即可明显感知“深色游戏环境 → 暗色 HUD → 明亮文章工作区”的层级变化；正式美术资源仍等待人工视觉验收。

### Phase 7.3.2 — Readability & Case Panel Polish

根据 Phase 7.3.1 的人工视觉反馈，本阶段继续保持 Dark HUD + Bright Article 方向，只做可读性和 Case UI 优化：

- 提亮 `--game-bg`、`--game-bg-secondary` 和 `--game-bg-accent`，将环境调整为中深蓝灰，降低 Grid、Node 和 Ambient Gradient 的对比度
- MaterialCard 增加稳定的 `material-card__content-surface`，强化 Type、Rarity、Preview、Attribute Value、Button 和 disabled 状态的前端 fallback 可读性
- 降低 `ART SLOT` 占位权重，不决定正式 Card Art、Frame、Type Icon 或 Rarity Visual
- MissionTracker 增加本地 Expanded / Collapsed 状态，默认折叠，只显示当前任务；展开后按现有 `missionSteps` 显示 CURRENT、COMPLETED、PENDING
- Case Toggle 使用 button、`aria-expanded` 和展开 / 收起 `aria-label`，支持键盘操作和 `prefers-reduced-motion`
- 没有修改 Sidebar Width、Outer Gutter、Article Layout、Material Store、Judge、Combination、Numeric Judge 或 Phase 8 功能

### Phase 7.4 — Four Card Type Image Mapping

`MaterialCard` 现在根据 `Material.type` 映射到四张完整 JPG 卡牌，只显示卡牌图片。`rarity`、`attributeValue`、`text` 和 `type` 等字段仍保留在 Material 数据中，供 Workbench、Combination 和 Numeric Judge 使用；卡片不再叠加文字或显示可见的加入工作台按钮，整张卡片作为无障碍交互 Surface。

#### Phase 7.4.1 — Card Acquisition Animation

素材收集成功后，Material Store 立即更新；前端通过 UI-only pending arrival 状态暂时隐藏 Backpack 中的新卡，并播放“完整卡牌弹出 → Showcase 停留 → 缩小弧线飞向 Backpack → Backpack Reveal”的获取动画。连续收集使用队列，Workbench 和判定逻辑不等待动画。

#### Phase 7.4.2 — Inventory Slot System

- Backpack 从横向 Carousel 改为 3 列 rectangular card slot grid；至少渲染 6 个视觉 Slot，素材超过 6 张时按 3 的倍数扩展，不引入背包容量玩法
- Backpack Slot 使用四张完整 JPG 的真实比例 `1279 / 1706`，空 Slot 保持暗色凹槽和轻量 HUD 边框，不显示 `EMPTY` 文本
- Workbench 固定显示 3 个同风格 Card Slot，组合按钮和 Numeric Judge 继续位于 Slot 区域下方
- Backpack 与 Workbench 共用 `CardSlot.vue` 的图片槽位视觉；Backpack 卡牌整格可点击加入 Workbench，已选卡保留在 Backpack 中并使用轻量 selected 状态
- Workbench 使用独立的 icon-only `×` 按钮移除素材，不显示 type、rarity、value、preview 或 score 等卡牌数据
- Acquisition Animation 按 Material ID 找到对应的 Backpack Slot：收集期间该 Slot 保持空槽，动画到达后显示 JPG 并触发约 190ms reveal；连续收集的卡牌各自预留自己的 Slot
- Backpack Slot Area 使用内部纵向滚动和 `overflow-x: hidden`，不撑宽 Left Sidebar；移动端保持 3 列并避免 body 横向溢出

#### Phase 7.4.3 — Backpack → Workbench Transfer Animation

- Backpack 卡牌点击时直接保存当前 Slot 的 viewport rect；只有现有 `workbenchStore.addMaterial(material.id)` 返回成功后，才创建 UI-only transfer request
- `LeftPanel` 作为 Backpack 与 Workbench 的共同父级，维护 `pendingWorkbenchArrivalIds` 和短 transfer queue；不把动画状态放入 Workbench Store
- Transfer Overlay 复用 `cardAssets.ts` 的同一张完整 JPG，从 Backpack Slot Lift 120ms 后飞向对应 Workbench Slot，Flight 500ms，保持轻微弧线路径和约 0.9–1 的目标缩放
- Workbench 根据 `selectedMaterialIds.indexOf(materialId)` 映射到 `data-workbench-slot-index`；pending Slot 暂时显示空槽，到达后再 Reveal JPG 并触发该 Slot 的 border pulse
- Workbench 已满或卡牌已选中时不创建动画；Backpack 原卡继续保留，只显示现有 selected 状态；Workbench 移除仍是立即操作，不增加反向动画

## Phase 7.6 — Pixel HUD Language Prototype

本阶段只在 Backpack Slot、Workbench Slot、HUD Header、COMBINE Button 和 AI Icon Frame 五个位置试验 Light Pixel Game UI Language：减少现代大圆角和模糊阴影，加入硬边、内高光、偏移硬阴影、方形状态标记和实体按压反馈。Article 正文、四张 JPG、布局宽度、Sidebar、背景和 gameplay 保持不变。

- Backpack / Workbench Slot 使用统一的矩形卡牌槽视觉；Backpack 是 Storage，Workbench 使用更亮的 Active Area 边框
- AI、Backpack、Workbench、Mission Header 使用统一的终端式标题、分段线、方角状态块和真实状态信息，不添加伪造 CPU、网络或容量数据
- COMBINE 使用实体按钮交互：Normal、Hover、Pressed、Disabled、Ready 和 Loading 状态均有独立视觉
- 四张正式 JPG 仍保持原样；Pixel 样式不作用于正式 Card Image，Article 继续使用原有阅读字体和排版

### Phase 7.6.1 — Pixel UI Amplification

人工视觉反馈指出上一版的 Card-to-Slot 留白和静态 Pixel 识别度仍偏弱。本阶段借鉴经典游戏 Inventory 的通用原则——明确 Slot 单元、较高 item fill ratio、hard pixel framing 和 tactile controls——继续使用 CyberJudger 自己的 Deep Blue / Cyan / Digital Investigation 语汇，不复制任何 Stardew Valley 素材、配色或图标。

- Backpack 与 Workbench occupied Slot 的 padding 从 4px 收紧到 1px；继续使用 `width: 100%`、`height: 100%`、`object-fit: contain`，让完整 JPG 更接近填满可用槽位面积
- Slot 改为 outer dark border、inner main border、top/left highlight、bottom/right recess 和 2px hard shadow 的多层构造；空 Workbench Slot 继续使用低透明度中心 `+`，不显示 `EMPTY` 文字
- Backpack / Workbench Frame 使用更稳定的 solid-ish navy surface、内高光和像素角标；Workbench 使用更亮 cyan active frame，Article Workspace 不跟随 Pixel 化
- HUD Header 使用实色 title plate、方形装饰块、硬分隔线和低圆角，统一 AI、Backpack、Workbench、Mission 的 Game Window Title Bar 语言
- COMBINE 保留真实 Disabled / Ready / Loading 状态，强化 2px border、bottom/right hard shadow、Hover 位移和 Pressed `translate(3px, 3px)`；不加入大面积 glow
- 静态 HUD 减少 rounded / glass / blurred shadow；Card Acquisition 与 Transfer Flight 保留原有 reward motion 和适量动画 glow，飞行轨迹不改
- 四张正式 JPG、Article Typography、Material Store、Judge、Combination Rules、Numeric Judge、Selection、Responsive 和 Sidebar Width 均保持不变

### Phase 7.7A — Backpack → Workbench Drag Prototype

本阶段在现有 Click Transfer 之外增加 Backpack → Workbench 的 Pointer Events 拖拽原型。短点击仍是快捷操作；按住卡牌并超过约 7px 阈值后，卡牌进入独立 Drag Overlay，拖到空 Workbench Slot 的矩形范围内并松手后立即进入对应槽位，否则短暂返回 Backpack 原位。

- `CardSlot.vue` 继续使用真实 `button`，不使用 HTML5 Drag API；Enter / Space 仍走原有点击加入流程
- `LeftPanel` 作为 UI-only Drag Coordinator，维护 pointer id、起点、viewport rect、当前位置、active target 和拖拽阶段，不把 HTMLElement 放入状态，也不创建新的 Gameplay Store
- Backpack 原始 Slot 不移动；拖拽时使用复用 `cardAssets.ts` 的 `CardDragOverlay.vue`，正式 JPG 不加 brightness、saturate、contrast、blur 或 pixelation filter
- 超过约 7px 才进入 Drag，未超过阈值的 pointerup 保持 Click fallback；拖拽成功后抑制后续 click，避免重复触发 `CardTransferOverlay.vue` 的完整自动飞行
- Workbench 固定 3 个槽位，pointer 只命中空槽的 viewport rect；DROP_READY 使用 cyan hard border、inner highlight、中心 `+` 和轻微放大，occupied / locked 不接收新卡牌
- 有效 Drop 先调用现有 `workbenchStore.addMaterial(materialId)`，随后只播放约 160ms 的短 Settle 和单槽 pulse；无效 Drop 使用约 220ms Snap Back，不执行 replace、swap 或 stack
- 支持 `pointerdown`、`pointermove`、`pointerup`、`pointercancel`、pointer capture 和 Escape 取消；移动端保留 `touch-action: pan-y` 与 Tap fallback，拖拽为 Desktop-first prototype，不破坏 Backpack 纵向滚动
- 本阶段暂不实现复杂 Magnetic Snap、Workbench → Backpack Drag、Slot Reorder、Card Swap、自动滚动、Audio、Particles，也不进入 Phase 8

### Layout Refactor Prototype v1 — Phase 8 Layout Prototype

本阶段只重构前端布局和 UI 壳，不接入新的 gameplay 逻辑。页面改为「左大栏文章 + 右侧双栏」：文章列约占一半宽度，右侧中栏放置 Creation Flow 与 Backpack，最右栏放置 Achievement System 与知北针 Compass。

- 文章列顶部新增始终可见的指标 HUD，使用文章列内部 `position: sticky`，不是全局 fixed 顶栏
- Creation Flow 使用现有 Workbench 的展示和组合逻辑，显示 5 个带编号槽位；前 3 个仍对应现有 `workbenchStore.maxMaterials`，五个槽位统一作为 Creation Flow presentation，不新增判定或组合规则
- Backpack 保持 Card Slot Grid，并在右侧中栏中使用更紧凑的 4 列布局，让卡槽约缩小到旧布局的 2/3 视觉尺寸；素材收集和卡牌飞入背包链路保留
- Achievement System 与知北针 Compass 目前都是占位壳，不包含成就计算、导航、舆论方向或后端接口
- 右侧中栏和最右栏分别使用独立 sticky 容器，内容过高时各自内部滚动；中等屏幕最右栏折到下一行，移动端简化为纵向堆叠
- 本阶段未实现 Achievement 真实逻辑、Compass 真实逻辑、Creation Flow 思维导图、Creation Flow 真实判定、后端接口或 Phase 8 Response 生成

### Layout Refinement — Phase 8A.1

本阶段继续只做前端布局和反馈密度，不接入 AI、后端或新的 gameplay 判定。当前桌面结构保持「左文章 + 右侧 Creation Flow / Backpack + 最右 Achievement / Compass」。

- Article Metrics 改为更短、更轻的两行 HUD：第一行只有 Answerer Value、百分比和 3–5px 进度条；第二行右对齐 Countdown 与 `理解点 selected / total`。静态 mock 从 `src/config/articleMetrics.ts` 读取，并按秒数格式化时间
- 指标 mock 遵循 `answererValuePercent`、`passThresholdPercent`、`timeRemainingSeconds`、`understandingSelected`、`understandingTotal` contract；当前 `150` 秒仅用于展示 `02:30`，不启动真实倒计时
- Creation Flow 固定为两行 `[1][2]` / `[3][4][5]`，五个 Slot 使用统一视觉，不再展示 placeholder、等待组合、COMBINE、Numeric Judge、Combination Result、Final Value 或 Target
- 新增 `CreationFlowSlot { index: 1 | 2 | 3 | 4 | 5; materialId: string | null }` contract，并为五个 slot 输出稳定的 `data-creation-slot-index`；旧 Workbench 文件、`maxMaterials = 3`、组合服务和拖拽兼容目标保留
- Right Primary 的 Creation Flow 与 Backpack 在普通桌面视口中同时可见，不使用内部纵向滚动；Backpack 保持桌面 4 列、至少 6 个视觉 Slot，并进一步收紧卡槽尺寸
- Achievement System 与知北针 Compass 继续沿用当前占位壳；本阶段不实现真实成就、方向、理解度玩法、实时倒计时、AI 或后端逻辑

### Phase 8A.2 — Real 5-Slot Creation Flow

本阶段将 Creation Flow 从视觉上的 5 个卡槽升级为独立的 5-slot state，并把 Backpack → Workbench 的首屏路径迁移为 Backpack → Creation Flow。旧 `Workbench.vue`、`workbenchStore.maxMaterials = 3`、CombinationService 和 Numeric Judge 保留给历史路径，不再作为新 Creation Flow 的 source of truth。

- `src/stores/creationFlow.ts` 使用 Pinia 持有固定的五个 `{ index, materialId }` 槽位，提供 `placeMaterial(materialId, slotIndex)`、`removeMaterial(slotIndex)`、`clear()`、`getMaterialAt()`、`hasMaterial()` 和 `serializeSlots()`；payload 永远按 1 → 5 保留五个 entry
- Drag 使用当前 `CardDragOverlay` 和约 7px threshold，但目标查询已迁移到 `[data-creation-drop-target]`；五个空 Creation Slot 都是真实 target，拖拽落点决定 slot，不会自动塞入第一个空位
- Click 与 Drag 有意区分：短点击 Backpack Card 使用第一个空 Creation Slot；拖拽 Backpack Card 使用玩家指针所在的指定 Slot。occupied Slot 拒绝 drop，不做 replace、swap 或 stack
- 成功拖拽使用约 160ms settle 到目标槽位；删除使用 icon-only `×` 立即清空对应 Slot，Backpack 素材继续保留并取消 selected / in-use 状态，不播放反向飞行动画
- Creation Flow 卡牌在保持 2 + 3 排列的前提下放大约 10%，继续保持 JPG 原比例和 1–2px 内边距；Backpack 不跟随放大，继续使用 compact 4-column layout
- Article Metrics 背景透明度从约 `0.64` 调整到 `0.46`，保留轻量 border、约 5px blur、thin progress bar 和 18px sticky offset
- 本阶段仍不实现 Backend Judge、AI Output、Real Countdown、Pass Flow、Achievement Logic 或 Compass Logic

### Phase 8A.3 — Salt Card / Fixed Creation Flow Backend Contract

本阶段只建立前后端职责边界，不虚构或接入尚未提供的后端 endpoint，也不改变已经验证的 Creation Flow UI 行为。

#### Salt Card

前端可见的 Salt Card contract 只有：

```typescript
interface SaltCard {
  cardId: string
  sourceText: string
  type: 'opinion' | 'emotion' | 'flaw' | 'rhetoric'
}
```

四种类型的权威判定来自 Backend。Backend 可以为卡牌保存内部数值状态，但该状态不进入 Salt Card 前端类型、Pinia、Vue props、浏览器存储、mock fixture 或 console 输出。

当前既有 `Material` / `materialId` 命名保留在内部，以避免一次性机械 rename；`CreationFlowStore.serializeSlots()` 是明确的兼容边界，将内部 `materialId` 映射为后端语义的 `cardId`。后续可以在低风险阶段再逐步重命名。

#### Stroke Judge

`src/types/strokeJudge.ts` 的 request 使用当前 ArticlePanel 已存在的玩家选区数据：`articleId`、`paragraphIndex`、`startOffset`、`endOffset`；这些 offset 只用于 POST `/api/judge` 判定。命中响应的 raw DTO 还包含后端命中 linespot 的 `start` / `end`：

```typescript
{
  hit: true,
  matchRate: number,
  card: {
    card_id: string,
    attribute_value: number,
    card_type: string,
    start: number,
    end: number,
  },
}
// 或
{ hit: false, matchRate: number, message: string }
```

后端 linespot 内部 convention 是闭区间 `[start, end]`；`src/services/strokeJudgeService.ts` 的 Adapter 将它转换为前端 domain 的 `[start, end)`，保存为 `canonicalStartOffset` / `canonicalEndOffset`。玩家的 `startOffset` / `endOffset` 仍然单独保留，只代表实际选择范围。Judge 命中后，Article 永久高亮和 Material/Salt Card source text 都使用 canonical range，不使用玩家的宽选区。

#### Fixed Creation Flow

Creation submission 的外部 payload 只包含固定顺序的五个 `{ index, cardId }`：

```typescript
interface CreationSubmissionRequest {
  slots: Array<{
    index: 1 | 2 | 3 | 4 | 5
    cardId: string | null
  }>
}
```

`serializeSlots()` 始终输出恰好 5 项，顺序为 `1 → 5`，空槽为 `null`，与玩家实际放置顺序无关。Backend 根据 slot index 使用固定规则并完成内部计算；Frontend 不发送 role、operator、weight、formula 等规则信息，也不执行其内部计算。

`src/services/creationService.ts` 提供 `submitCreation()` 和最小 `CreationResult { success, resultId? }` 边界。最终 Creation Result schema 与 endpoint 尚未提供，因此当前为 `CONTRACT ONLY / BACKEND ENDPOINT PENDING`，不会声明真实 API 已连接。

明确约束：`NO DYNAMIC RECIPE SYSTEM`。不建立 `CreationRecipe`、`RecipeGraph`、动态 operators、可编辑 edges 或可变 slot count；新的 Creation Flow 仍然只有固定 Slot 1–5。旧 `Workbench.vue`、`workbenchStore`、CombinationService 和 Numeric Judge 继续保留为 legacy path，新 Creation Flow 不依赖它们作为 source of truth。

### Phase 8B — Submit 恢复与 Fixed Creation Flow Backend Integration Boundary

本阶段恢复 Creation Flow 内部的 Submit Button，并建立正式的提交状态链路，但由于真实 Creation endpoint 尚未提供，当前仍然不会发送假请求或生成假结果。

- Submit 位于 Creation Flow Slot 区域下方，保留 `[1][2] / [3][4][5]` 布局；放卡、拖拽、点击或填满五槽都不会自动提交，只有玩家主动点击 Submit 才会触发
- Submit handler 只执行 `creationFlowStore.serializeSlots()` → `creationService.submitCreation(payload)`；不要求五槽全部填满，`cardId: null` 原样提交给后端决定是否接受
- Submit 状态包含 `idle`、`submitting`、`success`、`error`；submitting 时禁止重复点击，success / error 都不清空 Slot 或 Backpack，error 状态允许再次提交
- 当前 `creationService.submitCreation()` 会明确返回 `BACKEND ENDPOINT PENDING` 对应错误，页面显示 `Backend endpoint pending`，不会显示虚构的 `Submission accepted` 或 fake Creation Result
- `src/services/creationService.ts` 是唯一 Creation Backend integration point；`CreationFlow.vue`、`Backpack.vue`、`LeftPanel.vue` 不直接调用 fetch / axios，也不包含后端 URL
- 新增正式中文手册：[docs/前后端联调操作手册.md](D:/Hackathon/cyberjudger-frontend/docs/前后端联调操作手册.md)，包含 Stroke Judge、Creation Engine、payload、空槽、错误保留、联调步骤和后端待提供信息
- 本阶段继续保持 `NO DYNAMIC RECIPE SYSTEM`、固定 Slot 1–5、hidden vector backend-only，以及 `REAL BACKEND NOT YET CONNECTED`

## Phase 8C-A — Real Stroke Judge Backend Integration

本阶段只修改最新版 Vue frontend，不修改参考 backend，也不虚构 Creation endpoint。

- `src/services/strokeJudgeService.ts` 通过共享 Axios client `POST /judge` 调用真实后端；client base URL 为 `/api`，Vite proxy 转发到 `http://127.0.0.1:8000`
- Frontend request 的 `sourceText` 只在 transport adapter 中映射为后端要求的 `text`；可选 `stroke` 保留在前端类型中，但当前不会发送
- Backend response 的 `hit`、`card.id`、`card.text` 和中文卡型会分别适配为 `valid`、`cardId`、`sourceText` 和 `opinion/emotion/flaw/rhetoric`
- Backend card ID 直接作为 canonical Material ID 使用，不再拼接 `${articleId}-${card.id}`
- `attribute_x`、`attribute_y` 等隐藏向量不会进入 frontend `SaltCard`、Material Store、Backpack 或浏览器存储
- `UNKNOWN_BACKEND_CARD_TYPE`、未知响应结构、404、422、网络错误和超时会在 service 层转换为前端可消费错误；selection 状态保留
- 当前 Backend 仍会在 Network Response 中暴露 hidden vector，这是后端 future privacy work，不能仅靠前端过滤视为已解决
- `/api/articles` 仍未接入新版 Article source，因为它会返回 `informationPoints` 和隐藏字段
- Creation service 仍为 `BACKEND_ENDPOINT_PENDING`；固定 Slot 1–5、`serializeSlots` 和 Submit Button 保持不变

Stroke Judge 联调命令：

```powershell
cd D:\Hackathon\Connect_FrontToBack\backend
python -m uvicorn api:app --reload --host localhost --port 8000

cd D:\Hackathon\cyberjudger-frontend
npm run dev
```

当前状态：

```text
STROKE JUDGE REAL BACKEND CONNECTED
CREATION BACKEND STILL MISSING
FIXED SLOT 1~5 PRESERVED
SUBMIT BUTTON PRESERVED
BACKEND SOURCE UNCHANGED
```

## Not Implemented Yet

- 正式 Article 数据集
- 正式 Combination Recipe
- Creation / Response generation
- AI Response
- Backend API（本阶段仅完成 contract boundary，endpoint pending）
- Feedback Gameplay
- Mission Progression 动态推进
- Meta Progression
- Local Save
- Achievements

## Development

```bash
npm install
npm run dev
npm run build
npm run lint
```

当前核心验证命令为 `npm run build`、`npm run lint` 和 `git diff --check`。

## Next Phase

```text
Phase 7.x — Visual / Motion Polish（可继续）
        ↓
Phase 8 — Creation / Response Flow
```

计划方向：Workbench Combination → 生成本地 Demo Response → CreationArea 展示 / 发布。暂不接入外部 AI API。
