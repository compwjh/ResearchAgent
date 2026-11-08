> 关联：[spec-044](../../specs/044-conversation-answer-display-and-provenance.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`已完成`

# Task03 前端步骤浮层与记录列表

## 1. 状态与一句话目标
- 状态：`已完成`。
- 一句话目标：把「处理过程」四个步骤卡改造为可点击打开悬浮卡片，展示该步骤真实记录列表与来源类型；无明细时明确空态；交付一个可独立验收的前端交互。

## 2. 背景与前置条件
- 依赖 task-02：后端已在 4 类步骤写入 `step-evidence-v1` 的 `detail_json`。
- 设计依据：spec「边界」「明确不做」章节；`decision-baseline.md` D3/D5/D7/D9/D11 与 C7。
- 真实文件事实：
  - `frontend/app.js:2770-2779` `openFloatingMenu` 提供复用浮层基础。
  - `frontend/processing-tree.js:166-169` 叶子节点点击当前直接 `return`（C7），需改造为可点击打开浮层。
  - `frontend/processing-tree.js:157-159` 已有 `aria-expanded`/`aria-disabled` 可复用。

## 3. 数据、配置与接口
- 增量：消费既有 `GET /api/messages/{message_id}/processing-steps` 返回的步骤 `detail_json`，渲染浮层记录列表。
- 前端展示截断：摘要 `snippet` ≤120 字（D7）。
- 接口：不新增端点，复用既有 `processing-steps` 接口（D1）。

## 4. 实施步骤与文件边界
1. 复用 `openFloatingMenu` 建立单浮层容器；改造 `processing-tree.js` 叶子点击（原 `:166-169` return）为打开浮层。
2. 浮层关闭规则：Esc / 点击外部 / 关闭按钮 / 切换步骤均关闭；关闭后焦点回到触发按钮。
3. 键盘可达：步骤卡可聚焦、浮层内容可 Tab 遍历；动态文本一律 `textContent` / 安全属性写入，禁止 `innerHTML`。
4. 空态：历史无明细（`detail_json` 为 null / 非本 schema / 空 `records`）步骤不可点，显示「该消息生成时未记录召回明细」，不编造。
5. 窄屏（≤760px）浮层 `position: fixed`、宽度 ≤ `100vw - 32px`、内部滚动、触摸目标 ≥44px（D11）。
6. 目标文件：仅 `frontend/**`；CSS 新增 class 必须在 `frontend/styles.css` 有对应规则，并提升 `?v=` 版本号。
- 可观察结果：点击四个步骤卡可开/关浮层、焦点回弹、无明细显示空态、动态文本经 `textContent` 渲染、窄屏不溢出。

## 5. 子代理分派
- 角色：frontend-dev。模型：`Deepseek-V4.1-Flash`。
- 最小上下文：本 task + spec 边界章节 + `decision-baseline.md` D3/D5/D7/D9/D11 与 C7。
- 单次文件范围：仅 `frontend/app.js`（浮层复用）、`frontend/processing-tree.js`（点击改造）、`frontend/styles.css`（新增 class + `?v=`）。
- 回传后架构师读回校验：单浮层、焦点回弹、无 `innerHTML`、空态文案、CSS class 有定义且 `?v=` 已升。

## 6. 边界与明确不做
- 不复制第二套浮层（复用 `openFloatingMenu`，D5）。
- 不展示完整原文，只展示 ≤120 字摘要（D7）。
- 不造 ID/分数/来源；不引入 React 或组件库（D5）。
- 不改后端（task-02 负责）；不新增 HTTP 端点（D1）。
- 不把 URL 落库（C1，前端仅按 `paper_id` 拼既有入口）。

## 7. 验收、风险与回滚
- 验收：① 步骤卡可点击开浮层、单浮层、关闭规则齐全、焦点回弹；② 动态文本 `textContent`；③ 无明细空态文案正确；④ ≤760px 不溢出、触摸目标 ≥44px；⑤ CSS 新 class 有定义且 `?v=` 已升；⑥ `node --check` 通过。
- 风险：`innerHTML` 注入、焦点丢失、窄屏溢出。回滚到 task-02 与 spec，重做前端。

## 8. 产出物、执行结果与变更日志

- 产出文件：`frontend/processing-tree.js`（+43 行）、`frontend/app.js`（+87 行）。新增 `parseStepEvidence()`（fail-closed 解析 6 态）、`renderStepEvidencePanel()`、`renderStepEvidenceSourceText()`；叶子节点按 `evidence.state` 设 `aria-disabled` / `aria-label`，点击经 `onChange('evidence', {step,trigger,records,state})` 抛给 `app.js`，复用既有 `openFloatingMenu` 与全局 Escape / pointerdown 关闭，浮层 `role=dialog` + `aria-label`。14 个 `step-evidence-*` class 已加；`window.__spec044` 预留 task-04 来源动作钩子。
- 真实命令与结果（退出码均为 0）：`node --check frontend/processing-tree.js`、`node --check frontend/app.js` → OK；`node tests/frontend/test_frontend_processing_tree.js` → `processing tree contract: PASS`；临时 mock document 脚本 → `spec044 evidence parse + leaf click: PASS`。
- 主会话读回校验：已 `grep`/`sed` 确认函数落盘、无 `innerHTML`、空态与 truncated 分支正确、`node --check` 通过。
- 计划内延期项：`step-evidence-*` 样式未实现（按「每任务 ≤2 文件」拆分，CSS 由 task-07 统一样式分派补齐）；`?v=` 版本号统一在 task-05 同步，本任务未升。
- 风险：SSE 实时帧不携带 `detail_json`（保持轻量），明细只经历史水合接口读取；`app.js` 的浮层渲染无法在 Node 直接 require（依赖浏览器 DOM），由真实浏览器 E2E 在 task-05 覆盖。
- 变更日志：2026-11-08 frontend-dev 完成实现；2026-11-08 架构师读回校验通过。
