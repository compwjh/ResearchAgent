> 关联：[spec-019](../../specs/019-paper-import-status-feedback.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`已完成`

# Task03 前端导入状态反馈统一（单一状态源）

## 状态与一句话目标

`待执行`。把"添加到知识库"的状态表达收敛为**单一状态源**：`importPhase` + 每批次独立状态，汇总后再写状态栏，消除"先报导入暂不可用、后显示导入完成"的互相覆盖。

## 背景与前置条件

- `frontend/app.js:916-955` `importPaperCandidates`：按 `search_id` 分组循环提交，任一分组抛错即跳到外层 `catch`（952），`created` 中已创建批次不再启动轮询（951 被跳过）。
- 状态栏 `paperImportStatus` 被三处覆写：单篇结果（944）、异常（953）、轮询进度（1008）。
- 静默失败：`app.js:921`（`!searchId` 跳过）、`app.js:925`（`!groups.size` return）无任何反馈。
- 前置：Task02 结论已产出（决定"搜索会话不存在"的修法归属）。

## 数据、配置与接口

- 新增单一状态源（仅前端内存态，不改后端接口）：
  - `paperState.importPhase`：`idle`/`submitting`/`running`/`partial_success`/`completed`/`failed`
  - `paperState.batches: Map<batch_id, {state, error_code, message}>` 补全终态与错误码
  - 汇总函数：由各批次聚合 `{total, completed, failed, waiting_login}`
- 消费接口不变：`POST /api/papers/imports`、`GET /api/papers/imports/{id}`、`POST .../retry`。

## 实施步骤与文件边界

1. 引入 `setImportPhase()` / `aggregateImportSummary()`：状态栏**只在汇总终态**写入一次，禁止逐条覆写。
2. 分组循环改为：**各组独立 try/catch**，一组失败不影响其余组；失败组的 `error.code` 记入 `paperState.batches` 并在末尾汇总呈现。
3. 保证任一分组成功即 `schedulePaperBatchPoll()`（不再因后续分组失败而跳过）。
4. 静默路径补反馈：`!searchId` / `!groups.size` 时写入可见提示（如"未能确定该论文所属检索，请重新检索后再导入"）。
5. 区分 `partial_success`：同时呈现成功数与失败数。
6. 保持 DOM 契约：不新增/更名现有 `id`（`#paper-import-status`、`#paper-import-summary`、`#paper-import-selected` 等），`index.html` 静态资源 `?v=N` 按约定递增。
7. 不引入框架/构建，沿用无构建静态站写法。

**文件边界**：只改 `frontend/app.js`（必要时 `frontend/styles.css`、`frontend/index.html` 的版本号）。

## 子代理分派

- 角色 `frontend-dev`（`qwen3.8:27b-mlx`）：一次性只产出 `frontend/app.js` 的增量改动。
- 最小上下文：spec-019 背景+边界章节、Task02 结论、`app.js:900-1010` 片段、DOM 契约清单。
- 日志：`.codebuddy/agent-logs/spec-019/task-03/frontend-dev/<时间戳>.md`。
- 完成后由 `frontend-tester`（`qwen3.5:9b`）做 `node --check` 与契约核对（只读 DOM id 与 `?v=N`）。

## 边界与明确不做

- 不做：改后端接口与错误码（属 Task04）。
- 不做：重构整体前端、引入框架或构建。
- 不做：新增"一键导入全部"等新功能。
- 不改：`paper_import_batch_store.py` 状态机。

## 验收、风险与回滚

- 验收：
  1. 选中跨两个 `search_id` 的候选且其一失败 → 另一组照常完成，界面同时显示成功/失败数量与原因，**不出现先错后完成**。
  2. `partial_success` 明确区别于 `completed`。
  3. 无法解析 `search_id` 时有可见提示，不静默。
  4. `node --check frontend/app.js` 通过；现有 `tests/test_frontend_paper_contract.py` 全绿。
- 风险：轮询与状态栏改造可能影响既有契约测试 → 先跑契约测试再提交。
- 回滚：`git revert` 本任务提交（前端单端改动，回滚成本低）。

## 产出物、执行结果与变更日志

- **状态**：已完成（前端 single-source 状态表达统一）。
- **改动文件**：
  - `frontend/app.js`（仅改导入相关逻辑，未新增/更名任何 DOM id）
  - `frontend/index.html`（`app.js` / `styles.css` 的 `?v=18` → `?v=19`）
  - `tests/test_frontend_paper_contract.py`（`test_paper_app_version_bumped` 的断言 `?v=18` → `?v=19`，该测试是"版本须随改动递增"的护栏，必须同步更新才能保持绿）
- **新增状态字段**（`paperState`）：
  - `importPhase`：`idle`/`submitting`/`running`/`partial_success`/`completed`/`failed`（唯一状态源）
  - `failedGroups`：提交阶段失败的分组 `{search_id, candidate_ids, code}`
  - `skippedImports`：无法解析 `search_id` 的候选计数
  - `directSuccess`：单篇兼容形态（`!data.batch_id`）直接成功计数
  - `lastImportError`：轮询/重试的末次错误 code
- **核心实现**：
  - 新增 `setImportPhase()` 与 `renderImportSummary()`；状态栏 `paperImportStatus` **只在 `renderImportSummary()` 单一入口写入一次**，不再逐条覆写。
  - `importPaperCandidates` 改为**各组独立 try/catch**：一组失败记入 `failedGroups` 不影响其余；任一分组成功即 `schedulePaperBatchPoll()`；末尾 `renderImportSummary()` 汇总终态。
  - 静默路径补反馈：`!searchId` 计数 `skippedImports`、`!groups.size` 直接 `renderImportSummary()` 显示"未能确定该论文所属检索，请重新检索后再导入"。
  - `partial_success` 与 `completed` 通过文案与色类（`is-partial` / `is-completed`）明确区分：部分完成显示"X 篇成功，Y 篇失败（原因）"。
  - `schedulePaperBatchPoll` 终态调用 `renderImportSummary()`；轮询错误改为记录 `lastImportError` 不再覆写状态栏；重试失败同理。
  - 移除 `renderPaperBatch` 内逐批覆写状态栏/汇总的两行。
- **未新增 `PAPER_ERROR_TEXT` code**：复用既有 `IMPORT_BATCH_ERROR` 等映射，无新增错误码。
- **`?v=N` 新旧值**：`?v=18` → `?v=19`（app.js 与 styles.css 同步）。
- **执行结果**：
  - `node --check frontend/app.js`：通过。
  - `tests/test_frontend_paper_contract.py`：8 passed。
- **范围外（明确不做）**：`paperLogin`/`paperResume`（受控登录子流程，非本次"先错后完成"根因）仍保留即时反馈式状态栏写入，未纳入统一；不改后端接口/错误码（属 Task04）；未引入框架/构建。

## P1 修复（前端评审 019-frontend-review 回填，20260910）

> 依据：`docs/sdd/reviews/019-frontend-review.md` 的 P1-1 / P1-2（同会话重复"添加到知识库"状态泄漏）。本次仅修这两个 P1，未扩大范围/重构状态机其它部分。

- **改动文件**：
  - `frontend/app.js`（仅导入相关逻辑；未新增/更名任何 DOM id，未引入框架/构建）
  - `frontend/index.html`（`app.js` / `styles.css` 的 `?v=19` → `?v=20`）
  - `tests/test_frontend_paper_contract.py`（`test_paper_app_version_bumped` 断言 `?v=19`→`?v=20`；新增 `test_paper_import_status_resets_per_round` 锁定 P1 修复）
- **P1-1 修复**：`importPaperCandidates` 起始重置块（1018-1022）补 `paperState.directSuccess = 0;`，与 `skippedImports/failedGroups/lastImportError` 一同在每轮导入动作开始时归零。
- **P1-2 修复**：新增 `paperState.currentRoundBatchIds: Set()`；在 `importPaperCandidates` 起始重置为 `new Set()`，创建批次时 `add(batch_id)`；`renderImportSummary`（913-916）改为只聚合该集合内的批次，不再统计整个 `paperState.batches` Map。`paperState.batches` Map 本身保留全量，轮询（`schedulePaperBatchPoll`）、重试（`renderPaperBatch` 内"重试失败项"）、续传（`paperResume`）仍按 `batch_id` 正常查到批次，功能不受影响。
- **`?v=N` 新旧值**：`?v=19` → `?v=20`（app.js 与 styles.css 同步）。
- **TDD**：先加契约回归测试（断言 `directSuccess=0` 重置、`currentRoundBatchIds` 在导入与汇总两处出现），跑出 RED（2 failed）；再实现，跑出 GREEN。
- **执行结果**：
  - `node --check frontend/app.js`：通过。
  - `tests/test_frontend_paper_contract.py`：**9 passed**（原 8 + 新增 1 个 P1 回归）。
- **"重复导入两次，成功数不再翻倍"如何保证**：
  - 计数口径：`totalSuccess = completedItems + paperState.directSuccess`。`directSuccess` 每轮导入起始归零（P1-1），故第二轮不会把第一轮的 `directSuccess` 累加进来。
  - 批次口径：`renderImportSummary` 只用本轮 `currentRoundBatchIds` 过滤 `paperState.batches`；第二轮起始重置该集合并记录本轮新建批次，第一轮的旧批次被排除，故 `completedItems/totalBatches/totalFailed` 只反映本轮，不会因历史批次虚高或误判完成。
  - 重试/续传兼容：被重试的批次 `batch_id` 本就属本轮集合，仍被聚合；`paperResume` 新建的批次属登录子流程（范围外、即时写入状态栏），不进入本轮集合亦不影响轮询查询 Map。
- **边界**：未改 `backend/**`、未改后端错误码映射；未新增 DOM id / 未更名现有 id；未引入 `innerHTML` 拼接（新增逻辑均为状态读写）；未顺手重构状态机其它部分。
