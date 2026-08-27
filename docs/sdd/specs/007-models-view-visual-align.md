# 007 - 模型库视图视觉对齐与交互升级

- 状态：`已完成`
- 类型：UI 优化（复用现有设计系统，不推翻重做）
- 关联缺陷：spec-006 功能已实现，但模型库视图为裸 DOM，与站点既有设计语言（紫色 accent / Manrope+DM Mono / 卡片阴影 / 圆角）割裂，且无 hover / 动效 / 当前项高亮。

## 一句话目标

把"模型库"视图的视觉与交互对齐到全站既有设计系统（`.chat-panel`、`.candidate-*`、`.sidebar` 同一套 token），让它不再"很丑"，同时不破坏对话页现有样式。

## 现状（已核实）

- 既有设计令牌：`--ink/#25272b`、`--muted/#8b8e96`、`--paper/#f5f5f7`、`--accent/#6d5dfc`、`--accent-soft/#eeecff`、`--line/#e7e7eb`；字体 Manrope + DM Mono；卡片用 `border:1px solid var(--line); border-radius:12px; background:rgba(255,255,255,.86); box-shadow:0 18px 50px #272a3510`。
- 模型库现有结构（`frontend/index.html`）：
  ```
  <section class="main-area" id="models-view" hidden>
    <header class="topbar"><div class="breadcrumb">...</div></header>
    <section class="workspace" aria-label="模型列表">
      <ul class="model-list" id="model-list"></ul>
      <p class="model-empty" id="model-empty" hidden>没有发现模型</p>
    </section>
  </section>
  ```
- 现有 `.model-list/.model-item/.model-empty` 在 `styles.css` 中**无样式**（裸 DOM），所以呈现为默认 ul/li/p，视觉割裂。

## 目标设计（仅新增样式，不改现有 token 与 chat 页面）

### 1. 布局 / 容器对齐
- `.model-list`：作为纵向列表容器，与 `.messages` 一致的内边距（`padding: 26px 30px`），最大宽度与 `.workspace`（`min(1080px,100%)`）对齐，居中。
- 每个模型项 `.model-item`：复用卡片风格——`border:1px solid var(--line); border-radius:10px; background:white; padding:14px 16px; margin-bottom:10px;`，并加 `transition: .2s ease` 做 hover/active 过渡。

### 2. 模型列表项样式
- `.model-item`：flex 布局，左为模型名（Manrope 600），右侧 badge。
- `.model-name`：字体 14px、颜色 `--ink`；长名截断（`text-overflow:ellipsis; overflow:hidden; white-space:nowrap`）。
- `.model-badge`：DM Mono 11px、`border-radius:6px; padding:3px 8px;`；
  - 普通可用：背景 `--accent-soft`、前景 `--accent`。
  - 当前模型（`.current`）：背景 `--accent`、前景 white、font-weight 700，并左侧加 3px accent 边框或 `box-shadow:0 0 0 2px var(--accent-soft)` 强调。
- hover：`.model-item:hover` 背景变色（`var(--accent-soft)` 或轻微阴影 `+6px`），光标 pointer（已是 li，可加 `role`/`tabindex` 不强制）。

### 3. 空态与加载态
- `.model-empty`：复用 `.subtitle`/`.footer-note` 风格——`color:var(--muted); font:12px 'DM Mono',monospace; text-align:center; padding:40px 0;`，居中显示。
- 加载态（`#model-empty` 文本为"加载中…"时）沿用同一空态样式即可。

### 4. 交互动效
- tab 切换：对 `#chat-view`/`#models-view` 显示切换加 `opacity`/`translateY` 过渡（参考已有 `@keyframes rise`），避免硬切。
- 可复用 `.message` 的 `animation: rise .3s ease-out` 到 `.model-item` 进入时（可选，控制 token 预算，先不做逐条 stagger）。

### 5. 与对话页一致性
- 顶部 breadcrumb 已在用 `.topbar/.breadcrumb`，保持统一；如需，可让模型库列表容器与 `.chat-panel` 视觉重量一致（卡片感）。

## 明确不做
- 不引入新字体、不换主色、不重构 chat 页面、不引入组件库。
- 不做后端改动（模型数据接口不变）。
- **不新增/修改 DOM 节点**：加载态复用已有 `#model-empty`（JS 动态改 textContent 为"加载中…"/"暂无可用模型"），不新增结构。
- tab 切换仅由现有 JS 切换 `hidden` 属性驱动，CSS 只加淡入动画，不改切换逻辑。

## 数据模型 / 接口
- 复用 `/api/health` 的 `models[]` 与 `model`，前端仅改渲染样式与少量结构 class；`renderModelList` 已有 `.model-name/.model-badge/.current` 输出，仅需补齐 CSS（及必要时结构微调）。

## 端点 / 接口
- 无新增接口。

## 产品使用步骤（PM 补充）
1. 用户打开站点，左侧可见"模型库"导航。
2. 点击"模型库" tab：视图淡入切换，展示当前 Ollama 可用模型卡片列表。
3. 每个卡片显示模型名 + 状态徽标；当前生效模型以 accent 高亮。
4. 若加载中显示"加载中…"；若无模型显示"暂无可用模型"。
5. 悬停卡片有视觉反馈，点击（若启用）可切换当前模型（本期仅展示，切换逻辑以 chat 区 select 为准，不重复实现）。

## 验收点（可映射）
- V1 模型列表容器/卡片与 chat 卡片视觉一致（圆角/边框/阴影/token）。
- V2 当前模型高亮明显、普通徽标区分清晰。
- V3 空态/加载态文案居中、风格统一。
- V4 tab 切换有过渡、无硬闪。
- V5 不破坏对话页现有样式（回归）。

## 执行配置

| 角色 | 选用模型 | 上下文上限 | 职责 |
|---|---|---|---|
| 架构师 | Hy3（即当前执行本任务的 Agent 自身） | 200k | 编写/修订本 spec、技术决策、落地校验 |
| 产品经理 | qwen3.5:9b（本地 Ollama） | 32k | 梳理产品使用步骤、验收场景 |
| 开发主管 | qwen3.8:27b（本地 Ollama） | 32k | 需求/技术/验收评审、CSS 审查、合并裁决 |
| 初级开发 | oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU（本地 Ollama 量化 27B） | 32k | 编写/补全 model 视图 CSS 与必要结构微调 |
| 测试 | qwen3.5:9b（本地 Ollama） | 32k | 视觉验收、回归检查 |

> 选型依据：纯前端样式优化，复杂度低；中低复杂度角色优先本地 Ollama 省成本。本地模型名以 `ollama list` 实际输出为准（已核对）。架构师角色由当前 Agent（Hy3）自身承担。

## 评审记录

- 需求评审：`docs/sdd/reviews/007-requirement-review.md`（结论：通过，附带 2 澄清已采纳）
- 技术评审：`docs/sdd/reviews/007-tech-review.md`（结论：通过）
- 验收评审：`docs/sdd/reviews/007-acceptance-review.md`（结论：/）

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-08-27 | 架构师(Hy3) | 编写 spec-007（视觉对齐，复用现有设计系统） |
| 2026-08-27 | 开发主管(qwen3.8:27b) | 需求评审通过、技术评审通过 |
| 2026-08-27 | 初级开发(qwen3.8:27b 量化) | 产出模型库 CSS（片段式指导），架构师落地校验 |
| 2026-08-27 | 测试(qwen3.5:9b) | 验收评审通过（V1–V5 全过） |
| 2026-08-27 | 开发主管(qwen3.8:27b) | 验收签字，spec 转 `已完成` |
| 2026-08-27 | 架构师(Hy3) | 复盘闭环：修复三处落地偏差——(1) JS 渲染 class(.model-list-item)与 CSS(.model-item)不匹配，改为生成 .model-item/.model-name/.model-badge；(2) app.js 引用漏加版本号导致浏览器沿用旧缓存，补 `?v=2`；(3) 原文件 media query 含非法 `padding` 声明，修掉。经验已沉淀至 AGENTS.md 复盘纪律 |
