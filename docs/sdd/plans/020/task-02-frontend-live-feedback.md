> 关联：[spec-020 零碎 bug 解决](../../specs/020-misc-bug-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`

# Task02 前端即时反馈与批次卡片动画

## 状态与一句话目标

`待执行`。让点击"批量导入"后**立即**出现可见反馈，并让批次卡片创建即显示、非终态带进行中动画。

## 背景与前置条件

- `importPaperCandidates`（`frontend/app.js` 约 1014-1058）：`setImportPhase('submitting')`（1029）+ 面板显示（1030）之后**未调用 `renderImportSummary()`**，直到 1057 才渲染。导入耗时数十秒，期间界面无变化 → 用户"点了没反应"并重复点击。
- 文案 `正在提交 ${totalBatches + submitFailed} 个导入批次…`（约 957）在 submitting 阶段用**已创建**批次数，而 `renderImportSummary` 只统计本轮 `currentRoundBatchIds`（此时为空）→ 恒显 **0**。
- 单篇直成功（无 `batch_id`，`directSuccess` 分支）在提交阶段无任何可见反馈。
- 批次卡片 `renderPaperBatch(data)` 缺少"进行中"视觉表达与动画。

## 数据、配置与接口

- 新增 `paperState.pendingGroups`（待提交分组数），导入开始即置值。
- 提交阶段文案取 `pendingGroups`；**任何路径不得显示 0**（含单篇直成功与全部分组跳过）。
- 批次卡片：非终态加进行中 class + CSS 动画；终态移除动画 class。
- 接口契约不变。

## 实施步骤与文件边界

1. `importPaperCandidates` 中：`setImportPhase('submitting')` 与面板显示后，**立即调用一次** `renderImportSummary()`，保证点击后马上可见反馈。
2. 引入 `paperState.pendingGroups = groups.size`，提交阶段文案用它，取代 `totalBatches + submitFailed` 的 0 值口径。
3. 单篇直成功与 skipped 场景也要各有一条可见反馈（成功计入 `directSuccess`，跳过给出可见提示）。
4. 批次卡片创建即渲染；为非终态批次添加进行中样式与动画（CSS 新增动画需作用于 `#papers-view` 作用域内），终态移除。
5. 保持去重：重复点击不产生重复批次、计数不翻倍。

**文件边界**：只改 `frontend/app.js`、`frontend/styles.css`、`frontend/index.html`（`?v=N`）；必要时更新 `tests/test_frontend_paper_contract.py`。

## 子代理分派

- `frontend-dev`（hy3）：一次只产出 `frontend/app.js` 的增量改动。
- 完成后 `frontend-tester`（hy3）做 `node --check`、DOM 契约与 `?v=N` 核对（只读）。
- 日志：`.codebuddy/agent-logs/spec-020/task-02/<role>/<时间戳>.md`。

## 边界与明确不做

- 不改后端接口与错误码；不做 v2 相关改动（属 Task03）。
- **不得新增/更名现有 DOM id**；`?v=N` 必须同步递增并更新契约测试断言。
- 新增代码一律 `textContent`，禁止 `innerHTML` 拼接；不引入框架/构建。
- 不顺手重构状态机其它部分。

## 验收、风险与回滚

- 验收：
  1. 单次点击即出现"正在提交 N（≥1）个导入批次…"，无需点两次。
  2. 批次卡片立即出现；非终态有动画，终态停止。
  3. 单篇直成功亦有可见反馈；重复点击计数不翻倍。
  4. `node --check frontend/app.js` 通过；契约测试全绿。
- 风险：CSS 动画可能影响既有卡片样式 → 限定作用域并跑契约测试。
- 回滚：`git revert` 本任务提交（前端单端改动）。

## 产出物、执行结果与变更日志

### 改动文件
- `frontend/app.js`：① `paperState` 新增 `pendingGroups` 字段；② `importPaperCandidates` 在 `setImportPhase('submitting')` 与面板展开后**立即**调用 `renderImportSummary()`（约 1033），并在导入开始即置 `paperState.pendingGroups = groups.size`（约 1020）；③ `renderImportSummary` 提交阶段文案改用 `pendingGroups`（约 958），并加守卫"submitting 阶段不被 skipped 误判为 failed"（约 946）；④ `renderPaperBatch` 非终态卡片加 `is-progressing` 类（约 1109）。
- `frontend/styles.css`：新增 `@keyframes paperBatchPulse` 与作用域内规则 `#papers-view .paper-import-batch.is-progressing`（含 `prefers-reduced-motion` 降级）。
- `frontend/index.html`：`app.js` / `styles.css` 的 `?v=20` → `?v=21`。
- `tests/test_frontend_paper_contract.py`：版本断言 20→21；新增 `test_paper_submit_feedback_uses_pending_groups`、`test_paper_import_batch_progress_indicator`。

### 验收自检结果
- `node --check frontend/app.js`：通过（exit=0）。
- `.venv/bin/python -m pytest tests/test_frontend_paper_contract.py -q`：**11 passed**（含 2 条新增）。
- "单次点击即有反馈且 N≥1"由以下行保证：
  - 即时反馈：`setImportPhase('submitting')`（1031）+ 面板展开（1032）+ 立即 `renderImportSummary()`（1033），点击即重绘面板与文案。
  - N≥1：`paperState.pendingGroups = groups.size`（1020）且仅在 `groups.size ≥ 1` 时才进入 submitting（否则 1025 行提前 return 走 failed 分支）；submitting 文案取 `pendingGroups`（958），故任何进入 submitting 的路径 N≥1（含单篇直成功、部分分组跳过）。
  - 守卫（946）确保 skipped>0 时不把 submitting 翻转为 failed，文案始终为"正在提交 N 个导入批次…"。

### 三项强制自查
1. DOM 契约：JS 新增类 `is-progressing` 在 `styles.css` 存在（`#papers-view .paper-import-batch.is-progressing`）；反向确认 app.js 1109 渲染该 class。
2. 资源版本号：`index.html` `?v=20`→`?v=21`（app.js、styles.css 均升），契约测试同步断言。
3. XSS：新增代码仅 `classList.toggle`，无 `innerHTML` 拼接；既有 `textContent` 路径未动。

### 风险与边界
- 仅改 `frontend/**`，未碰 `backend/**` 与 v2 相关逻辑；未重构状态机其余部分；未新增/更名现有 DOM id。
- 重复点击去重：`inFlightImports` 逻辑未动，`pendingGroups` 为确定性 `groups.size`，计数不翻倍。
