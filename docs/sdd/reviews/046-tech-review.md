# SPEC-046 技术评审（Tech Review）

> 评审者 / 角色：架构师（评审/合并）子代理 `architect`，Gate 2 技术评审总控 + 拆任务
> 模型：自身（当前执行任务的 Agent，不写死模型代号）
> 分派方式：`Task(subagent_name="architect")`（SDD-GATE-CHECKLIST.md:65,69）
> 评审对象：`docs/sdd/specs/046-research-task-search.md`（数据模型 / 端点接口 / 边界 B1–B12 / 执行配置 / 明确不做），状态 `已确认`（D1–D5 已拍板）
> 评审依据：Gate 2（SDD-GATE-CHECKLIST.md:65-80）、00-sdd-spec-template.md:92-99、ROLE-ONBOARDING.md:33-43、`coding-standards` / `regression-guard`（含项目回归清单）/ `backend-patterns`（FastAPI 增补）/ `frontend-patterns`（原生 JS 增补）
> 核实方式：**逐文件 Read / Grep 真实代码**（前端 `frontend/research-tasks.js`、`research-session-ui.js`、`index.html`；后端 `backend/app/api/routes_research.py`、`research_service.py`、`research_store.py`；契约测试 `tests/frontend/*.py`；证据 `plans/045/runs/task-07/benchmark-summary.event.json`），无「应该没问题」式结论
> 评审日期：2026-11-09
> 评审阶段：spec 已 `已确认` 后的**技术维度 Gate 2 总控**；不把 spec 状态改为 `实施中`、不写状态台账、不代验收签字。

---

## 结论

**通过（附意见）。**

4 个「必须核实的关键可行性风险」**逐条落到代码事实且全部可在纯前端范围内解决**，无需改后端、无需新增业务端点、无需回到 spec 扩大范围。数据模型仅前端内存状态、接口零新增、模块拆分遵守前后端单端分派、执行配置五行齐全且模型/上下文预算合理；D1-B 的准确调用链已查实并据此在 spec「端点/接口」段补一段澄清（不改 D1–D5 裁决、不扩大范围）。

- **P0 阻塞：0。P1 意见：5。**
- 「通过（附意见）」的意见已沉淀为本文第七节「强制约束清单」，并在 spec「评审记录 / 任务计划 / 端点接口澄清」按授权回填。
- 本结论仅为**技术维度**评审，不代写验收评审、不替 tester 签字、不宣称准备度分数、不 mock 冒充真实 E2E；不 git commit / push / 合 main。

## 一、数据模型 —— 通过（仅前端内存状态，零持久化）

`spec:57-70` 的增量全部是 `research-tasks.js` 模块内 `state` 上的内存字段，逐项核对：

| spec 字段 | 核对结论 |
|---|---|
| `state.taskQuery` | 新增受控值，渲染只经 `input.value`；不写 DOM 文本节点。符合 `frontend-patterns` 增补「XSS：动态文本用 textContent / input.value」。 |
| 归一化查询（trim + toLowerCase + 上限 128） | 纯派生字符串，`String.includes()` 字面量子串，**不进 URL**（直查只接受已校验的 32 位 hex）。B3「超长不拼进 URL」成立。 |
| `state.taskIdLookup` (`status/taskId/result/requestSeq`) | 直查状态机 + 单调递增竞态守卫，对应 B10。纯内存，无缓存落库。 |
| `state.taskSearchCount` (`matched/total`) | `N/M` 计数，`total = 当前已加载条数 ≤100`。对应 B6/B9。 |
| **后端数据** | **零改动**：不动 DB schema、不动 `Session.to_dict()`（`models.py:1005-1022`）、不动 hydrate（`routes_research.py:668-687`、`research-session-ui.js:64`）、不改 SSE 事件协议。`research_task_id` 为 null 的 session（B7）走 haystack 降级，直查不受影响。 |

- **无并发/事务/外键问题**：纯前端内存状态，不触碰 `store.py` / SQLite / 迁移；`regression-guard` 后端增补（单事务幂等、`UPDATE…RETURNING` 抢锁、外键 RESTRICT、额度 try/finally）本期**不适用**（零后端改动），如实标注「不适用」而非空过。
- **SSRF / 来源可信**：直查 URL 形如 `` `/api/research-tasks/${encodeURIComponent(id)}` ``，`id` 先经 `^[0-9a-f]{32}$` 白名单校验（D1-B 只认完整 32 位 hex），`encodeURIComponent` 再编码；**同源相对路径、不接受任意用户输入 URL、不外发**，无 SSRF 面。任务实体可信度由后端 `owner_id` 隔离保证（见风险 2）。符合 `regression-guard` 增补第 7 条。
- **禁止第二套实现**：过滤函数、直查、复制、计数全部复用 `research-tasks.js` 既有 `requestJson` / `selectTask` / `upsertSessionTask` / `renderBenchmarkSummary` / `literature-maps.js` 的 `createElement`+`textContent` 模式；不新增跨模块公共 API（`spec:111`）。符合 `regression-guard` 增补第 9 条。

## 二、接口 —— 通过（复用既有端点、零新增业务端点）

D1-B 全链路只用到**既有的、已存在的**端点，逐一核对（均无需后端改动）：

| 端点 | 用途 | 现状依据 |
|---|---|---|
| `GET /api/research-tasks/{id}` | 前端直查历史任务（D1-B） | `routes_research.py:1516-1550` `get_research_task`；`selectTask` 内部 `research-tasks.js:3320` **已在用反引号模板字符串** |
| `GET /api/research-sessions/{sid}` | `selectTask` 内部拉 session 详情 | `routes_research.py:1271-1306`；`research-tasks.js:3346` 已在用 |
| `GET /api/research-tasks/{id}/events?after_seq=N` | SSE 回放 seq 40 事件 → 四项指标 | `routes_research.py:1824-1911`；`research-tasks.js:3252-3269` `connectStream` |
| `GET /api/research-tasks/{id}/report`、`/reports/{v}`、`/api/research-sessions/{sid}/artifacts` | `loadReport` 既有 | `research-tasks.js:3053,3059,3070,3091` |
| `GET /api/research-sessions?limit=100` | 列表加载（**不改字面量**） | `research-tasks.js:1089`；契约 `test_research_session_workspace_contract.py:14` 锁死 |

- **零新增业务端点 / 零新增 SSE 事件类型 / 零新增查询参数**：D1 选 C 的 `q`/`task_id` 服务端检索仅为「待确认接口增量」（`spec:81`），本期不实现。符合 D5。
- 404 / 超时 / 网络失败三类在**前端**映射为友好空态 + 重试（`spec:83-86`），不改后端错误体。

## 三、模块拆分与文件边界 —— 通过（只改 `frontend/**` + `tests/frontend/**`）

- **允许改动**：`frontend/research-tasks.js`（过滤纯函数、直查状态机、D3 ID 显示/复制、`state` 新增字段）、`frontend/index.html`（研究视图新增 `input[type=search]#research-task-search`、**`research-tasks.js?v=21` 升版 + 保留旧值兼容标记**，见 P1-2）、`frontend/styles.css`（**本期尽量不动**，若新增 class 则须同步处理 `?v=`，见 P1-3）；测试侧 `tests/frontend/` 新增静态契约 pytest + Node 纯函数单测。
- **禁改**：`backend/**`（D5 硬约束）、`app.js` / `styles.css?v=70` / `app.js?v=72` 的 live tag（`test_frontend_management_contract.py:78-80` 锁死，本期不动）、`GET /api/research-sessions?limit=100` 字面量（`spec:106`）、hash 路由（`app.js:5626-5658`、`research-tasks.js:872-882`，D4 不做）。
- **单端分派**：只派 `frontend-dev` / `frontend-tester`，**不分派 `backend-dev` / `backend-tester`**（`AGENTS.md` §前后端分派原则；`spec:161`）。Gate 4 :95「涉及 ≥3 个文件拆成每任务 ≤2 文件」由主会话在 task-04 内再拆，本轮 task-04 文档已给出 ≤2 文件的分步建议。
- **DOM 契约**（`regression-guard` 前端增补第 1/3/4 条）：新增 class 须在 `styles.css` 存在或复用既有；动态文本一律 `createElement` + `textContent`；样式限定 `#research-view` 作用域。

## 四、模型与上下文预算 —— 通过

- 执行配置五行齐全（`spec:156-162`）：架构师（自身 / 200k）、`doc-updater`、`architect`（评审）、`frontend-dev`/`backend-dev`、`frontend-tester`/`backend-tester`/`tester`；本期 `backend-dev` / `backend-tester` 写「不适用（纯前端单端改动）」而非删行。架构师行填「自身」不写死型号（`spec:158`），符合 Gate 1 :57。
- 各执行角色 `hy4` / 32k（`spec:164` 说明为临时决策、不写死流程文档、分派前以 agent 文件实时值为准）。本轮拆出的 task-04/task-05 均为「单点、纯前端、最小上下文」（spec 数据模型/接口/边界 + 目标文件行号），32k 足够；task-02/03（评审）与 task-06（验收收口）为文档/判定型，无代码大上下文需求。**无预算异常**，不深入模型库（ROLE-ONBOARDING.md:41「忽略」）。

## 五、4 个必须核实的关键可行性风险 —— 逐条结论

### 风险 1：`selectTask` 入参契约 / `research_session_id` 是否可得 / `knownSession` 从哪来 / session 不在 `state.sessions` 时能否工作 —— **已查实，可解**

代码事实（逐行）：

- `selectTask(taskId, sessionId = null, knownSession = null)` 定义于 `frontend/research-tasks.js:3271`。
- **`GET /api/research-tasks/{id}` 返回的实体「含」`research_session_id`**：`routes_research.py:1524` `detail = _task_summary(task)`，`_task_summary`（`:668-687`）给出 `research_task_id`/`status`/`goal_excerpt`/`created_at` 等；随后 **`:1528-1529` `session = _store().get_session_by_task(research_task_id, OWNER_ID)`；`detail["research_session_id"] = session.research_session_id if session else None`** —— 后端**显式注入**该字段。`:1525-1527` 另加 `updated_at`/`completed_at`/`plan`；`:1530-1546` 加 `plans`/`approvals`。故 sid **可得**（可能为 null，走 B7 降级）。
- **`knownSession` 与 sid 无关，无需构造**：`:3310` `sessionDetail = knownSession?.research_session_id === sessionId ? knownSession : null` —— `knownSession` 契约是「**session 详情对象**」（`GET /api/research-sessions/{sid}` 的响应，含 `session.to_dict()` + `task` 投影，`routes_research.py:1294-1306`），其用途是「复用已加载/通知携带的 session 详情以省一次请求」（见调用点 `:768/:779`）。D1-B 的历史任务**完全不在已加载 100 条内**，没有任何可复用的 session 详情，故 **`knownSession` 传 `null`**。把它误当成 task 实体的第三个参数会破坏 `sessionTaskProjection`（`research-session-ui.js:29-63` 的 `projectSession`）的形状假设，属参数语义滥用，**禁止**。
- **`selectTask` 在 session 不在 `state.sessions` 时照常工作，不依赖该缓存**：
  - `:3284` `state.selectedSessionId = sessionId || state.tasks.find(...)?.research_session_id || null` —— 找不到就 null，**不抛错**；
  - `:3336` `const listed = state.tasks.find(...) || {}` —— 用空对象兜底，**不抛错**；
  - `:3341` `resolvedSessionId = task.research_session_id || task.session_id || task.research_session?.research_session_id || sessionId` —— 从**直查实体**取 sid；
  - `:3342-3357` **会主动去拉 session 详情**：`:3346` `requestJson(`/api/research-sessions/${encodeURIComponent(resolvedSessionId)}`)`，且整段包在 `:3343-3355` 的 `try/catch` 内，**拉取失败也不抛错**（`:3353-3355` catch 用 task 自带的 legacy 投影降级）；
  - `:3358` `upsertSessionTask(state.selectedTask, resolvedSessionId)` → `:1000-1009` 把该历史任务**插入 `state.tasks`（`state.sessions` 与之同一数组引用，见 `:1007/:1095/:1102`）并 `renderTaskList()`** —— 这正是「不在 100 条内的历史任务进入 DOM / 单独呈现置顶」的落地机制；
  - `:3359-3364` `setDetailVisibility(true)` → `renderBenchmarkSummary()` → `Promise.all([loadMatrix, loadReport])` → `connectStream()`。
  - 注意：`selectTask` 函数体内**没有直接引用 `state.sessions`**；它读的是 `state.tasks`。`state.sessions = state.tasks` 多处赋值使二者等价，故「session 不在 `state.sessions`」等价于「task 不在 `state.tasks`」，已被 `:3284/:3336/:3358` 全覆盖。
- **结论**：sid 可得、knownSession 传 null、session 缓存缺失不抛错且由 selectTask 自行 HTTP 拉取 + upsert 补齐。**D1-B 在纯前端可行**。

### 风险 2：`GET /api/research-tasks/{id}` 的 404 / owner 隔离、`requestJson` 抛错形状 —— **已查实，可解**

- **404**：`routes_research.py:1519-1522` `task = _service().get_task(research_task_id, OWNER_ID)`，`except ResearchServiceError as exc: return _error(exc)`。`research_service.py:269-274`：`self._store.get_task(id, owner_id)` 返回 None → `raise ResearchServiceError("TASK_NOT_FOUND", 404, ...)`。`_error`（`routes_research.py:528-530`）稳定返回 `{"error": {"code": "TASK_NOT_FOUND", "message": ...}}` + HTTP **404**。非 404 的意外异常走 `:1548-1550` 返回 503 `SOURCE_UNAVAILABLE`（稳定错误体，符合 `regression-guard` 增补第 11 条，本期不改）。
- **owner 隔离**：`research_store.py:1400-1406` `SELECT * FROM research_tasks WHERE research_task_id=? AND owner_id=?`，查不到返回 None（docstring 明写「owner 隔离是 Spec027 硬约束」）。`OWNER_ID` 为后端常量（`routes_research.py` 多处 `_service().get_task(..., OWNER_ID)`），**非前端可传参数**，前端无法越权读取他人任务；不存在即 404，不泄露「他人任务是否存在」的差异化信息。
- **`requestJson` 抛错形状（`research-tasks.js:625-639`）**：
  - 网络层失败（`root.fetch` 抛）：`:629-633` 构造 `Error`，`network.code = 'NETWORK_ERROR'`，`network.cause = error`，**无 `.status`**；
  - HTTP 非 2xx：`:637` `throw errorFromResponse(response, data)`；`errorFromResponse`（`:614-622`）返回 `Error`，带 **`result.status = response.status`**（404 → `status===404`）、**`result.code = error.code`**（取自 `body.error.code`，如 `TASK_NOT_FOUND`）、`result.message`；
  - `userError`（`:865-870`）按 `error.code` 映射中文文案，HTTP 错误码不在 `ERROR_TEXT` 时给「错误码未知」兜底。
- **如何区分 404 与网络错误（可直接落成断言）**：`error.status === 404`（或 `error.code === 'TASK_NOT_FOUND'`）→ 「未找到该任务」；`error.code === 'NETWORK_ERROR'`（无 `.status`）或超时 → 「定位失败，请重试」+ 重试入口；503 `SOURCE_UNAVAILABLE` 归入后者。三类均保持列表原状、不 blank 视图（B5/M3）。**前端可干净区分，无需后端改动**。

### 风险 3：静态契约硬约束 / 反引号模板字符串是否撞 `:17` 禁则 —— **已查实，不撞**

- `test_research_session_workspace_contract.py:14`：`assert "requestJson('/api/research-sessions?limit=100')" in RESEARCH` —— 锁死**单引号字面量**（`research-tasks.js:1089`）。本期**不改**这一行 → 不受影响。
- `test_research_session_workspace_contract.py:17`：`assert "requestJson('/api/research-tasks'" not in RESEARCH` —— 禁的是**单引号 legacy 字面量** `requestJson('/api/research-tasks'`。新增的 **反引号模板字符串** `` requestJson(`/api/research-tasks/${encodeURIComponent(id)}`) `` 的字面文本是 `` requestJson(` `` 开头，**不含** `requestJson('/api/research-tasks'` 这一子串 → **不撞禁则**。
- **强证据（既有实现已在用且契约当前为绿）**：`research-tasks.js:3320` `` requestJson(`/api/research-tasks/${encodeURIComponent(taskId)}`) ``、`:3053`、`:3070`、`:3091`、`:3257`、`:3346` 均已大量使用反引号模板字符串，而 `:17` 测试当前通过 —— 反引号写法与 `:17` 共存已被实证。
- **`?v=` 升版与契约兼容（P1-2 详述）**：
  - `test_paper_issue_ui_contract.py:65` `assert "/assets/research-tasks.js?v=21" in INDEX`，live tag 在 `index.html:807` 当前为 `?v=21`。改 `research-tasks.js` 必须升 `?v=`（`frontend-patterns` 增补第 2 条 / `spec:100` B11）。
  - `test_frontend_paper_contract.py:90-97` 的 `_current_asset_version()` 用 `re.search(r'(?:href|src)="/assets/<asset>\?v=(\d+)"')` **只读 live tag**；`test_paper_app_version_bumped()`（`:100-110`）只校验 `app.js >= 29`、`styles.css >= 29` 及兼容标记 `app.js?v=31` / `styles.css?v=30`，**不锁 research-tasks.js 的 live 版本**。
  - 故升版做法：把 `index.html:807` live tag 升到 `?v=22`（或更大），并在 `index.html` **保留 `/assets/research-tasks.js?v=21` 作为注释兼容标记**（`:806`、`:809` 已有大量同类兼容注释标记，如 `?v=2/3/9/10`），使 `:65` 的 `in INDEX` 仍成立 → **无需改任何既有契约测试**（`test_paper_issue_ui_contract.py:65` 与 `test_frontend_paper_contract.py:90-97` 都满足）。此为 P1-2 强制约束，task-04/task-05 必须落。
  - `test_research_session_workspace_contract.py:58` `/assets/research-tasks.js?v=3`、`test_research_task_actions_contract.py:45/48` `?v=3`/`?v=2`（compatibility marker）、`test_routing_frontend_contract.py:78` `?v=11` 均为**历史兼容标记**，靠 index.html 注释保留，与 live `?v=` 升版不冲突（`:809` 已实证该模式）。
- `test_frontend_management_contract.py:78-80`：锁 `href="/assets/styles.css?v=70"` / `src="/assets/app.js?v=72"`（`index.html:810` 为 `app.js?v=72`）。**本期不动 app.js / styles.css 的 live tag** → 不受影响；若 task-04 需改 `styles.css` 新增 class，须按 P1-3 处理。
- **`innerHTML`**：`Grep innerHTML frontend/research-tasks.js` → **0 命中**（现状合规）；B4 / `spec:93` 要求新增代码仍不得引入，D3 复制、空态、计数一律 `createElement` + `textContent`。

### 风险 4：纯前端能否达成 M1（seq 40 与 benchmark_summary 是否依赖 session 上下文）—— **已查实，可达，且不依赖 session 上下文**

- **四项指标不来自直查实体**：`_task_summary`（`routes_research.py:668-687`）**不含** `benchmark_summary`；`benchmarkSummaryFromState()`（`research-tasks.js:591-602`）的候选为 `state.selectedTask.benchmark_summary/.benchmark/.routing_benchmark` 或 **`[...state.events.values()].reverse().map(e => e.payload?.benchmark_summary || e.payload?.benchmark)`** —— 即来自 **SSE 事件流里的事件 payload**。
- **seq 40 真实存在且可回放**：`docs/sdd/plans/045/runs/task-07/benchmark-summary.event.json` 读回为 `{"task_id": "2eb327f2cefb5fc7b5ac60e0454294f6", "event_seq": 40, "event_type": "task", "status_before": "completed", "status_after": "completed", "payload_complete": true, "benchmark_summary": {"warm": {"median_ttft_ms": 38478.927, "throughput_completion_tokens_per_s": 19.735, "peak_memory_bytes": 106070016, "failure_rate": 0.0}}}`。`event_type = "task"` 在前端 `EVENT_TYPES`（`research-tasks.js:12`）订阅列表内。Spec045 task-07「A 裁决打通」经**既有 `append_event` 事件通道**把该事件写入（`045-acceptance-review.md:54` 判定通过、前端零改动）。
- **回放链路（全既有、按 task_id 走、不依赖 session）**：
  1. `selectTask` `:3300` `state.lastSeq = 0`、`:3301` `state.streamEnded = false` → `:3364` `connectStream()`；
  2. `connectStream`（`:3252-3269`）`after_seq = state.lastSeq = 0` → `GET /api/research-tasks/{id}/events?after_seq=0`；
  3. 后端 `stream_research_events`（`routes_research.py:1824-1850`）→ `_event_stream`（`:1863-1911`）用 `_service().list_events(research_task_id, OWNER_ID, after_seq=cursor, ...)`（`:1873-1874`）**回放全部已持久化事件**，`yield _sse_frame(..., event.event_seq, event.event_type, _safe_payload(event))`（`:1896`）；
  4. 前端 `handleSseEvent`（`:3222-3238`）`state.events.set(seq, { seq, type, payload })`（`:3235`）→ `applyEvent`（`:3238`）→ `:3218` `renderSummary()` → `:2536` `renderBenchmarkSummary()` → `benchmarkSummaryFromState()` 反查命中 seq 40 的 `payload.benchmark_summary` → `renderBenchmarkSummary`（`:1537-1564`）渲染四项指标（`BENCHMARK_METRICS` `:109-114` 白名单 + 边界校验）。
- **是否依赖 session 上下文：否**。SSE 端点按 `research_task_id` 走（`/api/research-tasks/{id}/events`），`list_events` 按 task_id 取事件，`benchmark_summary` 在事件 payload，全程**不读 `state.sessions` / 不读 session 详情**；`:3342-3357` 的 session 详情拉取是**可选增强**且失败被 `:3353` catch 降级，不影响 `:3364` `connectStream()`。故「session 不在 100 条 / session 详情拉取失败」都不阻断四项指标。
- **`loadReport` 是否阻断 connectStream**：`selectTask:3362` `await Promise.all([loadMatrix(activeTaskId), loadReport(activeTaskId)])` 在 `:3364` 之前。`loadReport`（`:3026-3174`）自带 `try/catch`（`:3139-3173`），**捕获异常后 `return null` 不外抛**（`:3145/:3172`），`loadMatrix`（`:3013`）同样 try 包裹；故报告/matrix 失败不会中断 `connectStream()`。M1 主链路稳健。
- **结论**：M1 在纯前端可达；但须**真实浏览器 E2E 等四项指标出现再断言**（`:3360` 首次 `renderBenchmarkSummary()` 发生在 SSE 回放前，此时 `state.events` 为空会短暂显示「当前任务没有受控基准指标」空态，属既有行为，非缺陷）。**不得用 mock 冒充**。此为 P1-5 / task-05 验收点。

## 六、D1-B 的准确调用链（写进 task-04，并据此在 spec 补澄清）

> spec 现行描述（`spec:33`、`:78`、`:85`）为「前端以反引号模板字符串直查 `GET /api/research-tasks/{id}` → 拿到实体后 `selectTask(...)` 选中」，方向正确但**未说清**：实体是否含 sid、`selectTask` 三个参数怎么填、前端是否要自己先拉 session、`selectTask` 内部会再做什么。下列调用链据代码事实固化，**不改变 D1–D5 裁决、不新增端点、不扩大范围**。

```
[前端搜索层 · research-tasks.js 模块内新增]
1. 识别输入：trim + toLowerCase；匹配 /^[0-9a-f]{32}$/ → 判定为完整 research_task_id（D1-B 直查分支）；
   其余输入走「当前已加载 ≤100 条」前端过滤分支（D1 / D2）。
2. 直查前：防抖 250ms（D2）；state.taskIdLookup.requestSeq += 1 做竞态守卫（B10）；
   置 loading「正在按 ID 定位任务…」，列表保持可交互、不清空、计数不置 0（M1 步骤 3）。
3. 直查（前端这层不可省 —— 它驱动 404/网络错误区分、loading、N/M 计数、重试、竞态）：
       const detail = await requestJson(`/api/research-tasks/${encodeURIComponent(id)}`);
   · 反引号模板字符串，不撞 test_research_session_workspace_contract.py:17；
   · 404（error.status===404 / code==='TASK_NOT_FOUND'）→「未找到该任务，请检查 ID」空态（B5/M3）；
   · error.code==='NETWORK_ERROR'（无 status）/ 超时 / 503 →「定位失败，请重试」+ 重试按钮；
   · 三类均保持列表原状、旧直查结果不被污染；旧请求晚到按 requestSeq 丢弃（B10）。
4. detail 含 research_session_id（后端 routes_research.py:1528-1529 显式注入），sid = detail.research_session_id（可能 null → B7 降级）。
5. 选中（复用模块内既有函数，不新增公共 API）：
       await selectTask(id, sid);          // 第三参 knownSession 省略 = null（见风险 1）
   selectTask 内部（既有实现，前端无需重复做）：
     :3320  requestJson(`/api/research-tasks/${encodeURIComponent(taskId)}`)  // 自带反引号直查（幂等 GET，见下方「重复直查」说明）
     :3341  resolvedSessionId = task.research_session_id || ... || sessionId
     :3346  requestJson(`/api/research-sessions/${encodeURIComponent(resolvedSessionId)}`)  // 自行拉 session 详情，失败 :3353 catch 降级不抛错
     :3358  upsertSessionTask(...)  // 把不在 100 条内的历史任务并入 state.tasks 并 renderTaskList（单独呈现/置顶）
     :3360  renderBenchmarkSummary()
     :3362  loadMatrix + loadReport（各自 try/catch，不外抛）
     :3364  connectStream() → SSE 回放 seq 40 → applyEvent → renderSummary → 四项指标可见
6. 直查命中后提示「已定位并选中历史任务 2eb327f2…」，N/M 按直查命中口径（B9）；
   用户下一步查看受控基准摘要四项指标（M1 步骤 4/5）。
```

**要点与禁令**：

1. **`research_session_id` 可得**：来自 `GET /api/research-tasks/{id}` 响应（后端 `:1528-1529`），无需另造来源。
2. **`knownSession` 传 `null`**：它是 session 详情对象（复用缓存以省请求），不是 task 实体；D1-B 历史任务无缓存可复用。**禁止把 `detail` 当 `knownSession` 传入**。
3. **前端无需单独 `GET /api/research-sessions/{sid}` 再 `selectTask`**：这一步由 `selectTask` 内部 `:3346` 完成（且失败自动降级）。用户提示里的「再 GET /api/research-sessions/{sid}」在本实现中由 **selectTask 内部**承担，前端多做一次纯属冗余。
4. **`selectTask` 只读 `state.tasks`、会自行 upsert**：session 不在 `state.sessions` 时照常工作、不抛错（风险 1）。
5. **重复直查说明（P1-4）**：前端第 3 步直查 + `selectTask:3320` 内部直查 = 同一幂等 GET 两次。因 `selectTask` 的 `:3318` 分支只在传入有效 `knownSession`（其 `sessionProjection.research_task_id === taskId`）时才跳过内部直查，而在「传 null」口径下必然再查一次。这是既有实现的既有行为，**接受这一次幂等重复**，不得为消除它而改 `selectTask` 既有逻辑或引入第二套数据装配（超出范围 / 违反 DRY）。若 task-04 评估要消除，须把「前端直查仅做存在性/错误态判定、把 detail 以受支持的方式交给 selectTask」作为独立设计并回到本评审复核，**不得自行扩大**。
6. **零后端改动**：整条链只用既有端点；404/owner 隔离由后端保证（风险 2）；四项指标经既有 SSE 事件通道（风险 4）。

## 七、P0 / P1 清单与强制约束（Gate 2 :73 沉淀）

**P0（阻塞）：0。**

| # | P1 意见 | 依据 | 强制约束（下游 task 必须落） |
|---|---|---|---|
| P1-1 | **D1-B 调用链澄清** | spec `:33/:78/:85` 未说清 sid 来源、knownSession 契约、selectTask 内部行为 | 按本文第六节实现；已在 spec「端点/接口」段补澄清（不改 D1–D5）。task-04 全文引用该调用链。 |
| P1-2 | **`?v=` 升版与契约兼容** | `test_paper_issue_ui_contract.py:65` 锁 `?v=21`；`frontend-patterns` 增补要求升版 | live tag 升 `?v=22`+，**把 `?v=21` 保留为 index.html 注释兼容标记**（`:806/:809` 既有模式）；`test_frontend_paper_contract.py:90-110` 不锁 research-tasks.js live 版本 → 无需改既有契约测试。task-04 改、task-05 验「契约 pytest 全绿 + live tag 与测试期望一致」（B11）。 |
| P1-3 | **`styles.css` / `app.js` 不动** | `test_frontend_management_contract.py:78-80` 锁 `styles.css?v=70` / `app.js?v=72` | 搜索框样式优先复用既有 class 或 `#research-view` 作用域内联；**不擅自升 `styles.css?v=70` / `app.js?v=72`**。若确需新增 class 改 styles.css，须论证兼容标记 + 回本评审复核。 |
| P1-4 | **重复幂等直查** | `selectTask:3320` 内部会再直查一次 | 接受一次幂等 GET 重复；不为消除它改 `selectTask` 既有逻辑 / 引入第二套数据装配（DRY、范围）。 |
| P1-5 | **M1 等待条件** | `benchmark_summary` 经 SSE 回放 seq 40 才渲染；`:3360` 首帧为空态 | 真实浏览器 E2E **等四项指标出现再断言**，不得 mock 冒充；E2E 报告记等待条件与截图（M1 步骤 5 / `spec:118,120`）。 |

**沉淀为 spec 强制约束**：以上 P1-1~P1-5 连同需求评审的 5 条，一并作为「通过（附意见）」的强制约束清单；其中 P1-1 已按授权写入 spec「端点/接口」段澄清，其余由 `plans/046/task-04`、`task-05` 的「验收点 / 明确不做」承载，spec「评审记录」行标注「通过（附意见）」。

## 八、回归维度自查（regression-guard 项目增补）

- 前端 1 DOM 契约 / 2 资源版本号 / 3 XSS / 4 CSS 作用域：见第三节与 P1-2/P1-3，命中并给出处置。
- 后端 5–14（迁移 / 抢锁 / SSRF / 来源 / 禁重复实现 / 额度 try/finally / 稳定错误体 / 测试不恒真 / SSE 合成帧 / payload 脱敏）：本期**零后端改动**，逐条标注「不适用（纯前端单端改动）」；其中第 7 条 SSRF 与第 9 条禁重复实现已在第一/二节正面核对（直查同源相对路径 + 白名单 hex、复用既有实现）；第 11 条稳定错误体由后端既有 `_error` 保证、本期不改；第 13 条 SSE 合成帧协议本期不改（D5）。**不因「不适用」而空过**，逐条给出理由。

## 九、评审边界声明

- 4 个风险若任一无法在纯前端解决，本应判「打回」或写明「需回 spec 修订并请用户确认」；本次**全部查实可在纯前端解决**，故判「通过（附意见）」，且**未偷偷扩大到后端**。
- 本轮不改任何业务代码 / 测试、不 git commit / push / 合 main、不写 `spec-status-changelog.md`、不把 spec 状态改为 `实施中`；只创建 `reviews/` 两份评审、`plans/046/` 任务文档，并按授权回填 spec 指定三处 + 一段「端点/接口」澄清。
- 进展日志：`.codebuddy/agent-logs/spec-046/architect-gates/20261109-012550.md`。
