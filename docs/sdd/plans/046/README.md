# 实施计划索引：spec-046 研究任务搜索

> 关联：[spec-046 研究任务搜索](../../specs/046-research-task-search.md) ｜ 三份评审：`docs/sdd/reviews/046-{requirement,tech,acceptance}-review.md`
> Spec 当前状态：**`已完成`**（2026-11-09 收口；三份评审通过并双签、准备度 9/10、P0/P1=0、真机 M1/M2/M3 E2E 成功）。D1–D5 按推荐拍板并固化于 spec「状态」段；**不 push、不合 main**。
> 本目录由架构师（评审/合并）子代理 `architect` 于 Gate 2 需求/技术评审通过后，按 `00-sdd-spec-template.md:92-99`「规范化流程」创建；**仅含任务文档，不含任何代码文件**。
> 纪律：本轮不改任何业务代码 / 测试、不写 `spec-status-changelog.md`（主会话负责台账）、不把 spec 状态改为 `实施中`、不 push、不合 main。

## 目标（一句话）

在研究视图提供搜索入口：①按目标 / ID 关键字过滤**当前已加载** ≤100 条列表，②按完整 32 位 hex `research_task_id` 直查并选中**任意历史任务**（含不在 100 条内的 `2eb327f2…`），使「粘贴 ID → 命中并选中 → 受控基准摘要四项指标可见」（M1）成为可人工执行的主案例。

## 已确认裁决（D1–D5，不得改变）

- **D1 = B**：识别完整 32 位 hex `research_task_id` → 前端以**反引号模板字符串**直查既有 `GET /api/research-tasks/{id}` → `selectTask(...)` 选中任意历史任务；非 ID 输入走已加载 ≤100 条前端过滤。
- **D2 = 推荐**：五字段字面量子串 + `trim()` + `toLowerCase()` + 长度上限 128 + `N/M` 计数与空态；输入即触发过滤，完整 32 位 hex 或 Enter 触发直查（防抖 250ms）。
- **D3 = 推荐**：卡片显示并可复制完整 `research_task_id`（`createElement` + `textContent`）。
- **D4 = 本期不做**：带参 hash / 可分享链接。
- **D5 = 推荐**：**不改后端、不新增业务端点**，纯前端单端改动（只派 `frontend-dev` / `frontend-tester`）。

## 前置与硬约束（详见 `046-tech-review.md`）

- 4 个关键可行性风险已逐条以代码事实核实、全部可在纯前端解决：`research_session_id` 由后端 `routes_research.py:1528-1529` 注入直查响应、**可得**；`selectTask(taskId, sessionId, null)` 在 session 不在 `state.sessions` 时自行拉 session + `upsertSessionTask` 补齐、不抛错；404/owner/网络错误可由 `requestJson` 的 `error.status` / `error.code` 干净区分；反引号模板字符串不撞 `test_research_session_workspace_contract.py:17`；四项指标经既有 SSE 回放 seq 40 事件渲染、不依赖 session 上下文。
- **D1-B 准确调用链**：见 `046-tech-review.md` 第六节（前端直查 `requestJson(\`/api/research-tasks/${encodeURIComponent(id)}\`)` → 取 `detail.research_session_id` → `await selectTask(id, sid)`，第三参 `knownSession` 省略 = null）。task-04 必须全文引用。
- **`?v=` 升版**：改 `frontend/research-tasks.js` 须升 `index.html:807` 的 `research-tasks.js?v=21` → `?v=22`+，并把 `?v=21` 保留为 index.html 注释兼容标记（`test_paper_issue_ui_contract.py:65` 精确锁）。`styles.css?v=70` / `app.js?v=72` 本期不动（`test_frontend_management_contract.py:78-80`）。
- **零 `innerHTML`**、全 `createElement` + `textContent`；新增 class 复用既有或限定 `#research-view` 作用域。
- **只改 `frontend/**` + `tests/frontend/**`**；涉及 ≥3 文件按 Gate 4 :95 拆成每任务 ≤2 文件（task-04 内分步）。

## 任务索引

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-046（含 D1–D5 拍板、状态转 `已确认`） | [spec-046 本体](../../specs/046-research-task-search.md) | — | **已完成**（`待确认` → `已确认`，2026-11-09 用户确认） |
| 02 | 需求评审（Gate 1 / Gate 2） | [task-02](./task-02-requirement-review.md) | 01 | **已完成**（本轮：`046-requirement-review.md` 判「通过（附意见）」，P0=0 / P1=4） |
| 03 | 技术评审（Gate 2 总控）+ 4 风险核实 + 拆任务 | [task-03](./task-03-tech-review.md) | 01 | **已完成**（本轮：`046-tech-review.md` 判「通过（附意见）」，P0=0 / P1=5；本目录落地） |
| 04 | 前端实现与自测（D1-B 直查 + D2 过滤 + D3 复制） | [task-04](./task-04-frontend-implementation.md) | 02, 03 | **已完成**（红→绿，`runs/task-04/implementation.md`） |
| 05 | 前端契约 / 静态 / 单测与真实浏览器 E2E（单端回归） | [task-05](./task-05-frontend-regression-and-e2e.md) | 04 | **已完成**（`337 passed` + 真机 M1/M2/M3） |
| 06 | 验收评审与收口 | [task-06](./task-06-acceptance-and-closure.md) | 05 | **已完成**（三份评审通过并双签、台账/复盘/commit 闭环） |

> 依赖无环：01 → 02/03 → 04 → 05 → 06。所有任务文档链接均为真实相对路径，无占位死链。
> 任务 01 以 spec 本体为文档，不重复创建 task 文件（模板 `:63`）。
> **全部 6 个任务已完成，spec 状态 `已完成`（2026-11-09）**；证据索引 `runs/task-04/`、`runs/task-05/`，
> 三份评审 `docs/sdd/reviews/046-*.md`，复盘 `docs/sdd/retro/2026-11-09-spec046-research-task-search.md`。
> 真实 E2E 截图 / 取证产物目录：`runs/task-05/screenshots/`（执行 task-05 时创建，M1-*.png / M2-filter.png / M3-not-found.png 与取证 JSON）；收口前真实 API 取证记入 task-06。
