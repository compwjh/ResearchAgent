# 046 研究任务搜索：按 ID 定位历史任务并按关键字过滤当前列表

> 本文件基于 `docs/sdd/00-sdd-spec-template.md` 编写，遵循 `AGENTS.md` 强制流程。

## 状态

> 只能是其一：`待确认` / `已确认` / `实施中` / `已完成` / `阻塞`。每次状态变更须同步追加 `docs/sdd/spec-status-changelog.md`（`AGENTS.md` 强制流程第 10 条）。

**当前状态：已完成**

> **门禁通过（2026-11-09）**：`docs/sdd/reviews/046-requirement-review.md`（通过，P0=0/P1=4）、
> `046-tech-review.md`（通过，P0=0/P1=5）。四个可行性风险逐条核实后确认**纯前端范围内可解**，
> 无需改后端、无需新增端点、无需回 spec 扩大范围。D1-B 准确调用链见「端点 / 接口」澄清段。
> P1 意见由 `doc-updater` 与实现阶段消化，不改变已确认的 D1–D5 裁决。
>
> **收口记录（2026-11-09）**：需求/技术/验收三份评审均通过，`tester` 出验收报告、
> `architect` 已签字（准备度 **9/10**，P0=0/P1=0，第 10 项为签字后流程待办，已由台账/复盘/
> plans 状态/本地 commit 闭环）。单端回归 `337 passed`（前端精确集合）/ `33 passed`（指定契约）、
> Node 8/8、`node --check` 0、`innerHTML=0`。当前部署版本（`/api/health` 200、
> `/assets/research-tasks.js?v=22`）真实 E2E：M1 粘贴本例 ID → 直查 200 → 选中 →
> SSE 回放 seq 40 → 四项指标可见；M2 前缀过滤 `1/101`；M3 全 0 ID → 404 友好空态 + 重试；
> 17 个 API 请求 16×200 + 1×404、`pageErrors=[]`。证据 `docs/sdd/plans/046/runs/task-05/search-e2e.json`
> 与三张截图；复盘 `docs/sdd/retro/2026-11-09-spec046-research-task-search.md`。
> **不 push、不合 main**，`origin/main` 仍 `1b26c76c`；状态流转见 `docs/sdd/spec-status-changelog.md`。
> 9 条已声明边界（D4 带参 hash 不做、`next_cursor` 未消费、B8 刷新态无自动化覆盖等）如实保留。

> **用户确认（2026-11-09）**：「搜索按推荐方案确认 spec」。D1–D5 全部按推荐方案拍板：
> - **D1 = B**：识别完整 32 位 hex `research_task_id`，前端以反引号模板字符串直查既有 `GET /api/research-tasks/{id}`，成功后 `selectTask(...)` 选中**任意历史任务**（含不在最近 100 条内的本例）；非 ID 输入走当前已加载 ≤100 条的前端过滤。
> - **D2 = 推荐**：haystack 五字段、纯字面量子串、`trim()` + `toLowerCase()`、**长度上限 128**、支持 ID 前缀、`N/M` 计数与无结果空态；输入即触发前端过滤，完整 32 位 hex 或按 Enter 触发直查（直查防抖 250ms）。
> - **D3 = 推荐**：卡片显示并**可复制**完整 `research_task_id`（`createElement` + `textContent`）。
> - **D4 = 本期不做**：不改 hash 路由、不做 `?task=<id>` 可分享链接。
> - **D5 = 推荐**：**不改后端、不新增任何业务端点**，纯前端单端改动（只派 `frontend-dev` / `frontend-tester`）。
>
> 下方「数据模型 / 端点接口 / 边界 / 验证方式」按上述裁决生效，不再视为草案；各小节中的「请用户拍板」文字保留作决策历史。
> 按 `AGENTS.md`：转 `已确认` 后进入需求评审 / 技术评审，评审通过才实现；本 spec 仍**不 push、不合 main**。

## 一句话目标

用户反馈「找不到研究任务 `2eb327f2cefb5fc7b5ac60e0454294f6`」。根因：研究视图列表实际是 **session 列表**（`loadTasks()` 拉 `/api/research-sessions?limit=100`，`frontend/research-tasks.js:1089`，忽略 `next_cursor` `:1091-1092`，`state.tasks = state.sessions` `:1095-1103`）；本例任务是更早的历史任务，`GET /api/research-sessions?limit=100` 返回 100 条且 `next_cursor` 非空、命中 0 条，**从未进入 DOM**；且 `research_task_id` 只在卡片 `data-task-id`（`:1019`），可见文本只有 `goal_excerpt` 与 `会话 {research_session_id}`（`:1024/:1030`），**用户看不到也复制不到 ID**；研究视图无搜索框（`frontend/index.html:192-378`，全文件仅 2 个 `type="search"` 分别在 `:615`、`:784`，均不在研究视图）。目标：在研究视图提供搜索入口，①按目标/ID 关键字过滤**当前已加载**列表，②**按 `research_task_id` 直查并选中任意历史任务**（含不在 100 条内的本例任务）。做成什么样算对，以「产品使用步骤」主案例 M1 为准：粘贴本例 ID → 命中并选中 → 受控基准摘要四项指标可见。

## 设计决策（D1–D5，2026-11-09 已按推荐方案确认）

> 五项已于 2026-11-09 由用户「搜索按推荐方案确认 spec」拍板，结论固化在「状态」段。
> 以下保留备选方案与理由作决策历史，各小节的「请用户拍板」文字为决策前原文；
> 「数据模型 / 端点接口 / 边界 / 验证方式」按已确认结论生效，不再是草案。

### D1 搜索范围（最关键，决定能否解决本次问题）
- **备选 A（纯前端过滤，零后端改动）**：只过滤当前已加载的 100 条 session。**明确局限：只做前端过滤无法解决用户这次的问题**——本例 `2eb327f2…` 是更早历史任务，100 条命中 0，从不进入 DOM，前端过滤再完备也搜不到；`routes_research.py:1333` 的 `limit` 上限 100，调参无解。
- **推荐方案 B（按 ID 定位任意历史任务，不新增端点）**：前端识别输入为完整 `research_task_id`（32 位 hex）时，以**反引号模板字符串** `/api/research-tasks/${id}` 调用既有 `GET /api/research-tasks/{id}`（`routes_research.py:1516-1522`，本例真实返回 **200**），拿到实体后调用模块内既有 `selectTask(taskId, sessionId, knownSession)`（定义 `research-tasks.js:3271`）选中并展现详情；非 ID 输入仍走当前 100 条的前端过滤。理由：零后端改动、不新增业务端点、复用既有直查端点与选中逻辑，能直接命中本例历史任务。
- **备选 C（服务端检索）**：给 `GET /api/research-tasks` 列表（`:1466-1501`）与 `GET /api/research-sessions` 列表（`:1328-1370`）加 `q` / `task_id` 服务端过滤（现两者均无 `q`/`keyword`/`id`，只有 `project_id`/`status`/`cursor`/`limit`）。理由：可做全量检索，但需改后端、扩接口契约、回归面最大，且与「明确不做 / 不新增业务端点」冲突，须按 D5 回到 spec 修订。
- **请用户拍板**：A / **B（推荐）** / C。

### D2 匹配字段与语义
- **推荐**：haystack 至少含 `research_task_id`、`research_session_id`、`goal_excerpt`、状态、时间五字段；纯 `String.includes()` 字面量子串匹配、大小写不敏感（`toLowerCase()`）、先 `trim()` 去首尾空白；支持 ID 前缀/子串（完整 32 位 hex 优先触发 D1-B 直查）；显示 `N/M` 计数与「无匹配结果」空态（复用 `frontend/literature-maps.js:1851-1856` 模式）。
- **备选**：仅匹配 ID + `goal_excerpt` 且不计数、只给空态；或大小写敏感、只支持完整 ID 精确匹配。
- **理由**：五字段 + 子串 + 不敏感最贴合「记不清 ID 只记得目标片段」；纯函数便于 Node 单测；`N/M` 让用户知道「只搜了已加载 100 条」的边界（见 B6）。长度上限具体值、触发方式（输入即触发 / 按 Enter）随本项一并确认。

### D3 ID 可见性
- **推荐**：在卡片上显示并**可复制** `research_task_id`（`textContent` + 复制按钮，`createElement`），否则即便「按 ID 搜到」也无法核对是否命中目标。
- **备选**：只显示完整 32 位 ID、不做复制按钮；或只显示 8 位短前缀 + 悬浮 `title` 显示全 ID。
- **理由**：现状 ID 只在 `data-task-id`，用户看不见也复制不到，D1-B 的「粘贴 ID」主路径要求用户能拿到 / 核对 ID。请用户确认是否做、显示完整还是短前缀、是否要复制按钮。

### D4 是否支持 URL / 可分享链接直达（`?task=<id>`）
- **推荐：本期不做**。hash 路由 `app.js:5640-5658` 用 `hasOwnProperty` 精确匹配，`#research-view?task=<id>` 会回落 chat；`research-tasks.js:880-881` 会把 hash 重写回纯 `#research-view`。实现成本大：需同时改 `app.js:5626-5658` 与 `research-tasks.js:872-882` 两处视图同步器、扩路由解析、处理与既有 hash 重写冲突。
- **备选**：若用户要做，列为范围扩大，回到 spec 修订并追加带参路由 E2E；本期默认「不做」。
- **理由**：与本期「找到并选中历史任务」目标无强依赖（YAGNI）；改动触及全局路由，回归风险高于收益。

### D5 是否改后端
- **推荐：不改后端、不新增任何业务端点**（D1-B 完全复用既有 `GET /api/research-tasks/{id}`）。
- **备选 / 触发条件**：若用户在 D1 选 C（服务端检索），或后续要求任何服务端检索能力，即产生**待确认的接口增量**（新增 / 扩展查询参数 `q`/`task_id`），必须回到本 spec 修订「数据模型 / 端点接口 / 边界 / 验证方式」并重新评审，**不写成既定事实**。
- **理由**：遵循「禁止第二套实现 / 复用既有」与前后端单端分派原则；纯前端方案可只跑前端回归，成本最低。

## 数据模型

> 仅新增前端内存状态，**不新增任何持久化 / DB 字段、不改 `Session.to_dict()`**（`backend/app/research/domain/models.py:1005-1022`，不含 goal/title、`research_task_id` 可空）、不改 hydrate 投影（`routes_research.py:668-687`、`frontend/research-session-ui.js:64`）。

| 字段 / 项 | 类型 | 约束（必填？范围？默认？）|
|---|---|---|
| `state.taskQuery` | `string` | 搜索框受控值；默认 `''`、可空；渲染只经 `input.value`，不写入 DOM 文本节点 |
| 归一化查询（派生） | `string` | `taskQuery.trim()` 去首尾空白 + `toLowerCase()` 折叠大小写；**长度上限 128 字符**（D2 已确认值，超出截断）；允许中/英文、数字、空白、常见标点；**纯字面量匹配，禁止正则 / HTML 解析** |
| `state.taskIdLookup`（可选，D1-B） | `{ status, taskId, result, requestSeq }` | 直查结果缓存；`status ∈ idle\|loading\|hit\|miss\|error`；`requestSeq` 单调递增做竞态守卫（见 B10）；默认 `idle` / `null` |
| `state.taskSearchCount`（可选） | `{ matched, total }` | `N/M` 计数；`total` = 当前已加载条数（≤100）；`matched` 来自前端过滤或直查命中；默认 `null` |
| 输入约束 · 空白 | — | 空串 / 纯空格 / 全角空白 → 视为**无查询**，恢复完整列表，不发直查 |
| 输入约束 · 长度 | — | 超过上限 128 字符按约定截断或提示，不做静默无限增长、不拼进 URL |
| 输入约束 · 允许字符 | — | 不限制输入字符（含 `<` `>` `'` `"` `&` 与中文），但落地一律 `textContent` / `input.value` / `createElement`，**禁止 `innerHTML`** |
| 后端数据 | — | **不新增**：不动 DB schema、不动 `Session.to_dict()`、不动 hydrate；`research_task_id` 为 `null` 的 session 参与前端过滤时降级处理（见 B7） |

## 端点 / 接口

> **不新增任何业务端点**，不改 SSE 事件协议。下表除「前端过滤」外全部为**复用既有端点**；D1 选 C 时的服务端检索仅为「待确认接口增量」，**不是既定事实**。

| 动作 | 输入 | 成功返回 | 失败情况（状态码）|
|---|---|---|---|
| 直查历史任务（复用，D1-B 推荐） | `GET /api/research-tasks/{id}`，`id` = 归一化后 32 位 hex；前端以**反引号模板字符串** `/api/research-tasks/${id}` 调用 `requestJson(...)`（非被 `test_research_session_workspace_contract.py:17` 禁止的单引号 legacy 字面量） | `200` + 任务实体（本例 `2eb327f2…` 真实 200，`routes_research.py:1516-1522`）；据此调用 `selectTask(...)` 选中并展现 | `404`（ID 不存在 → 友好空态）、请求超时、`fetch` / 网络失败 → 错误提示 + 可重试；均不抛未捕获异常、不清空既有列表 |
| 加载列表（既有，不改） | `GET /api/research-sessions?limit=100`（`research-tasks.js:1089`，**URL 字面量契约锁死**，`test_research_session_workspace_contract.py:14`） | `200` + 100 条 + 非空 `next_cursor`（本例命中 0 条） | 既有行为不变，本期不改 |
| 前端过滤（新增，纯函数，无 HTTP） | 归一化 `taskQuery` + 当前 ≤100 条 session | 过滤后子集 + `N/M` | 无匹配 → 空态（不产生 HTTP 请求） |
| ~~按 `q` / `task_id` 服务端检索~~ | — | — | **本期不实现**；仅 D1 选 C 时作为**待确认接口增量**回到 spec 修订 |

**直查端点三类结果（逐条落成测试断言）**：
- 请求：`GET /api/research-tasks/2eb327f2cefb5fc7b5ac60e0454294f6`（当前部署版本取证基线见「验证方式」第 5 条）。
- 成功：`200` + 实体 → `selectTask(taskId, sessionId, ...)` 选中，展示受控基准摘要。
- 失败：`404` → 「未找到该任务」友好提示；超时 / 网络失败 → 「定位失败，请重试」+ 重试入口；三类均保持列表原状，旧直查结果不被污染。

**D1-B 调用链澄清（2026-11-09 技术评审补充，仅澄清既有裁决的实现方式，不改变 D1–D5、不新增端点、不扩大范围）**：
> 依据 `docs/sdd/reviews/046-tech-review.md` 第五/六节的代码事实；实现细则见 `docs/sdd/plans/046/task-04-frontend-implementation.md`。上表 `selectTask(taskId, sessionId, ...)` 的 `...` 在此明确：
- `GET /api/research-tasks/{id}` 返回实体**含 `research_session_id`**：后端 `routes_research.py:1528-1529` 由 `get_session_by_task()` 显式注入（无关联 session 时为 `null`，走 B7 降级）；故 `sessionId` 直接取 `detail.research_session_id`，**无需另造来源**。
- `selectTask` 的第三参 `knownSession` 契约是「session 详情对象」（`research-tasks.js:3310` 要求 `knownSession.research_session_id === sessionId`），**不是 task 实体**；D1-B 的历史任务完全不在已加载 100 条内、无可复用缓存，故调用固定为 `await selectTask(id, sid)`（`knownSession` 省略 = `null`）。**禁止把直查得到的 task 实体当 `knownSession` 传入**。
- `selectTask` 在 session 不在 `state.sessions` 时照常工作、**不抛错**：它只读 `state.tasks`，内部 `:3346` 自行 `GET /api/research-sessions/{sid}` 拉详情（失败 `:3353` catch 降级），`:3358` `upsertSessionTask` 把历史任务并入列表并渲染。因此**前端无需单独 `GET /api/research-sessions/{sid}`**；用户提示中的该步由 `selectTask` 内部既有逻辑承担。四项指标经既有 `connectStream()`（`after_seq=0`）回放 seq 40 事件渲染，**不依赖 session 上下文**。
- `selectTask` 内部 `:3320` 会再直查一次同一幂等 GET（接受这一次重复，不为消除它改 `selectTask` 既有逻辑或引入第二套数据装配）；404 / 网络错误由前端直查层用 `requestJson` 的 `error.status===404` / `error.code==='NETWORK_ERROR'` 区分（owner 隔离由后端 `research_store.py:1400-1406` 保证）。
- 全链路仍**零新增业务端点、零后端改动、零 SSE 协议改动**，与「明确不做」及 D5 一致。

## 边界（每条之后会变成一条测试）

- **B1 空输入 / 纯空格**：`taskQuery` 为空或全空白 → 恢复完整列表，`N/M` 中 `N = M =` 当前条数，不发直查。→ 测试：纯函数输入 `''` / `'   '` 返回全量。
- **B2 大小写与中英文**：大写 / 小写 ID、中文 `goal_excerpt` 片段均能命中，`toLowerCase()` 生效。→ 测试：大小写变体与中文关键字命中集一致。
- **B3 超长输入**：>128 字符按约定截断 / 拒绝，不卡死、不把超长串拼进 URL、不触发直查。→ 测试：1000 字符输入返回受控结果且无异常。
- **B4 特殊字符与 XSS**：输入 `<img src=x onerror=alert(1)>`、`'`、`"`、`&`、中文标点 → 仅作字面量匹配，落地只用 `textContent` / `input.value`；`research-tasks.js` 不得出现 `innerHTML`（`test_frontend_literature_map_expansion.py:30` 同款断言，模块 `clearNode()` 用 `replaceChildren()` `:924`）。→ 测试：静态契约扫描 + 特殊字符输入断言不产生 DOM 注入。
- **B5 不存在的 ID（404）**：格式合法但不存在的 ID → 友好「未找到该任务」空态，不抛未捕获异常、不 blank 整个视图。→ 测试：mock 404 断言空态文案与列表保持。
- **B6 100 条截断与 `next_cursor` 未消费**：前端过滤只覆盖已加载 100 条；本例历史任务不在其中，必须由 D1-B 直查兜底（这正是「只做前端过滤无法解决」的测试化）。`loadTasks()` 忽略 `next_cursor`（`:1091-1092`）本期不改。→ 测试：构造不含目标 ID 的 100 条 + 输入该 ID，断言走直查分支而非 0 命中。
- **B7 session 的 `research_task_id` 为 null**：该项不因 `null` 报错，haystack 拼接降级为其余字段；直查不受影响。→ 测试：含 `null` 的样本集过滤不抛异常。
- **B8 搜索与刷新 / 新建任务 / 通知跳转交互**：`loadTasks()` 刷新（`:3398`）、新建任务、通知跳转（`:768/:779`）后，`taskQuery` 保持或按约定清空，`selectTask` 选中态与搜索结果不冲突、不重复渲染。→ 测试：模拟刷新后断言查询态与选中态一致。
- **B9 结果计数与空态**：`N/M` 精确、无结果显示空态文案；直查命中时计数 / 文案与前端过滤区分。→ 测试：`3/100`、`0/100`、直查命中三种断言。
- **B10 直查请求并发与竞态**：连续改 ID / 快速输入时，旧请求晚到不得覆盖新结果；以 `requestSeq` 单调递增守卫，仅最新请求生效。→ 测试：乱序 resolve 两个 mock 请求，断言只应用最新。
- **B11 `?v=` 与既有契约测试一致性**：改 `research-tasks.js` 须递增 `?v=`（当前 live `index.html:807` 为 `research-tasks.js?v=21`，`test_paper_issue_ui_contract.py:65` 精确锁），`styles.css?v=70` / `app.js?v=72`（`test_frontend_management_contract.py:78-80`）本期不动；`test_research_session_workspace_contract.py:14/17` 的 URL 字面量契约保留。递增需同步这些测试或把旧值留作注释兼容标记（`test_frontend_paper_contract.py:90-97` 只读 live tag）。→ 测试：契约 pytest 全绿 + live tag 与测试期望一致。
- **B12 带参 hash（D4，本期不做）**：`#research-view?task=<id>` 回落 chat 属已知现状，本期不修（除非用户 D4 选择要做）。→ 测试：本期不新增，仅记录现状。

## 明确不做（划出范围，防 AI 自由发挥）

- 不新增业务端点、不改 SSE 事件协议。
- 不改 `GET /api/research-sessions?limit=100` 的 URL 字面量（契约锁死，`test_research_session_workspace_contract.py:14`）。
- 不做全文检索 / 正则 / 模糊搜索 / 服务端分页改造；`next_cursor` 消费留后续 spec，`loadTasks()` 忽略 `next_cursor` 本期不改。
- 不改 hash 路由与可分享链接（`?task=<id>`）；除非 D4 用户明确选择要做，才回 spec 修订。
- 不改研究任务状态机与评测 / 观测逻辑。
- 不引入 `innerHTML` 或任何新依赖；全 `createElement` + `textContent`，复用 `frontend/literature-maps.js`（`:1008-1010`、`:1536-1539`、`:1653-1666`、`:1851-1856`）既有模式。
- 不新增跨模块公共 API：`selectTask` 保持模块内部调用（`frontend/app.js` 对 `selectTask` 零引用），本期不对外暴露。
- 本轮不改 `docs/sdd/spec-status-changelog.md`（主会话负责台账）、不创建 `plans/046/` 与 `reviews/046-*`、不 push、不合 main。

## 验证方式

1. **前端静态契约测试**：新增 `input[type=search]` 的 id `#research-task-search`、过滤 marker、`?v=` 递增、`"innerHTML" not in research-tasks.js`、`research_task_id` 进入 haystack；仿 `tests/frontend/test_frontend_literature_map_expansion.py:30`。
2. **Node 纯过滤函数单测**：仿 `tests/frontend/test_research_report_notifications.js`，覆盖 B1/B2/B3/B4/B7/B9/B10（纯函数、无 DOM 依赖）。
3. **真实浏览器 E2E**：输入本例 ID → 选中任务 → 四项指标可见；截图落盘到 `docs/sdd/plans/046/runs/task-05/screenshots/`（`M1-*.png`、`M2-filter.png`、`M3-not-found.png`），E2E 报告与取证落盘到 `docs/sdd/plans/046/runs/task-05/`（例如汇总截图 `search-e2e.png`、取证 JSON `search-e2e.json`），目录与命名约定与 `docs/sdd/plans/046/task-05-frontend-regression-and-e2e.md` 一致。以上均为产物命名约定（纯文本占位说明），目录与文件在 task-05 执行时创建，本 spec 文档阶段不要求其此刻已存在。
4. **单端回归**：推荐方案为纯前端改动，只跑前端契约 / 静态检查（`node --check`、`frontend` 契约 pytest），**不跑后端 pytest**（`AGENTS.md` §前后端分派原则）。
5. **Spec 收口前真实 API 端到端成功案例**（`00-sdd-spec-template.md:38`、`AGENTS.md` §56）：对**当前部署版本**记录真实请求 `GET /api/research-tasks/2eb327f2cefb5fc7b5ac60e0454294f6`、响应状态码（已核实基线 200）、实体 ID、最终状态（选中并展现受控基准摘要）与产物路径；mock / 内部函数 / 仅表单调用不可代替。已核实事实第 4 条仅作基线取证，收口须重跑。准备度十项检查至少通过九项，且无 P0/P1、无关键产物缺失。

## 产品使用步骤（由产品经理在 spec 确认后填写）

> 初稿由架构师代填核心场景与可执行人工验收案例；spec 确认后由 `doc-updater` 复核并补齐完整用户旅程（模板 `:33`、`:36`）。主路径为自然语言 / ID 入口，不以表单或内部 API 调用替代（`00-sdd-spec-template.md:36`、`AGENTS.md` §57）。
> 产物路径约定：M1–M3 的「最终产物路径」均为纯文本命名占位说明，目录与文件在 `docs/sdd/plans/046/task-05-frontend-regression-and-e2e.md` 执行时生成，本 spec 文档阶段不要求其此刻已存在（目录 / 命名见「验证方式」第 3 条）。

核心场景：用户在研究视图搜索框输入目标关键字或 `research_task_id`，即时过滤当前列表；输入完整历史任务 ID 时定位并选中该任务。

### 主案例 M1（必须）：粘贴本例 ID → 命中并选中 → 受控基准摘要四项指标可见
- **步骤 1（控件）**：打开研究视图 `#research-view`，可见列表上方新增搜索框 `input[type=search]#research-task-search`（占位符「按目标 / ID 搜索研究任务」）；列表默认已加载（≤100 条）。
- **步骤 2（输入）**：在搜索框粘贴完整 32 位 hex `2eb327f2cefb5fc7b5ac60e0454294f6`。按已确认的 D1=B / D2 口径：输入即触发当前 ≤100 条列表的前端过滤（五字段 haystack、纯字面量子串、`trim()` + `toLowerCase()`、长度上限 128、`N/M` 计数）；本例为完整 32 位 hex，前端随即按 D1=B 直查既有 `GET /api/research-tasks/{id}` 定位任意历史任务（防抖 250ms），完整 32 位 hex 或按 Enter 均触发该直查；非 ID 关键字输入只走前端过滤。
- **步骤 3（是否等待 / 等待期间状态）**：**是**，等待按 ID 直查 `GET /api/research-tasks/2eb327f2…` 返回（通常 <1s）；期间搜索框旁显示「正在按 ID 定位任务…」loading 态，列表保持可交互、不被清空，计数区暂不更新为 0。
- **步骤 4（点击后提示 / 下一步）**：返回 200 后提示「已定位并选中历史任务 2eb327f2…」；`selectTask(...)` 选中该任务，详情面板展现（当前 100 条列表本不含该任务，直查结果单独呈现 / 置顶）。
- **步骤 5（下一步 / 等待 SSE 回放及等待期间状态 / 最终可见产物）**：下一步查看该任务**受控基准摘要**。**需等待**：选中后详情面板经既有 `connectStream()` 以 `after_seq=0` 回放历史 SSE 事件（seq 40）才渲染基准摘要，首帧可能短暂显示空态（既有行为）；等待条件为四项指标全部出现在详情面板后再断言，不提前判失败。等待期间提示「正在加载基准摘要…」loading / 空态占位，搜索框与列表保持可交互、选中态不变、不 blank 视图。四项指标可见：`median_ttft_ms`（≈38478.927）、`throughput_completion_tokens_per_s`（≈19.735）、`peak_memory_bytes`（≈106070016）、`failure_rate`（=0.0）；证据基线 `docs/sdd/plans/045/runs/task-07/benchmark-summary.event.json`。
- **步骤 6（失败恢复）**：直查 404（ID 不存在）→ 显示「未找到该任务，请检查 ID」友好空态 +「重试」按钮；超时 / `fetch` 网络失败 → 显示「定位失败，请重试」+「重试」按钮；点「重试」重发直查，或改回本例 ID 重新定位。若步骤 5 等待 SSE 回放期间四项指标迟迟未出现，同样点「重试」重新触发定位与回放。以上失败期间列表与已加载结果保持原状、不 blank 视图、不抛未捕获异常（见「端点 / 接口」三类结果与 B5）。
- **最终产物路径**：验收截图 `docs/sdd/plans/046/runs/task-05/screenshots/M1-*.png`、E2E 取证 JSON `docs/sdd/plans/046/runs/task-05/search-e2e.json`（汇总截图 `docs/sdd/plans/046/runs/task-05/screenshots/search-e2e.png`）；四项指标基线见上（路径为纯文本占位说明，见段首「产物路径约定」）。

### 场景 M2：按目标关键字过滤当前列表
- **步骤 1（控件）**：同一搜索框输入 `goal_excerpt` 片段或 `会话`（中英文均可）。
- **步骤 2（是否等待 / 等待期间状态）**：**否**，纯前端同步过滤，无网络等待、无 loading，输入即收敛。
- **步骤 3（点击后提示 / 下一步）**：列表即时显示匹配项，计数区显示 `N/M`（如 `3/100`）；卡片文本匹配不引入 `innerHTML`。
- **步骤 4（空态）**：无匹配显示「无匹配结果」+ `0/100`。
- **失败恢复**：清空搜索框或点清除按钮 → 恢复完整 100 条列表。
- **最终产物路径**：`docs/sdd/plans/046/runs/task-05/screenshots/M2-filter.png`（纯文本占位说明，见段首「产物路径约定」）。

### 场景 M3：不存在的 ID 空态（404）
- **步骤 1（控件）**：输入格式合法但不存在的 32 位 hex，如 `00000000000000000000000000000000`。
- **步骤 2（是否等待 / 等待期间状态）**：**是**，等待直查返回 404，期间显示「正在定位…」。
- **步骤 3（点击后提示）**：显示「未找到该任务，请检查 ID」友好空态，不抛 JS 异常、不清空列表。
- **失败恢复**：点「重试」或改回本例 ID → 回到 M1。
- **最终产物路径**：`docs/sdd/plans/046/runs/task-05/screenshots/M3-not-found.png`（纯文本占位说明，见段首「产物路径约定」）。

## 执行配置（由架构师填写，落盘可查）

> 模型真值按 `docs/sdd/MODEL_REGISTRY.md` §54-68 的规则读取 `.codebuddy/agents/<role>.md` 的 `model` 字段；五行必须齐全；架构师行填「自身」，不写死模型代号。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师（编写/修订本 spec） | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、技术决策、划模块与边界、落地校验 |
| 文档更新 `doc-updater` | `hy4` | 32k | `Task(doc-updater)` | 基于已确认 spec 补齐产品使用步骤、用户旅程、验收场景 |
| 架构师（评审/合并）`architect` | `hy4` | 32k | `Task(architect)` | 需求/技术评审总控、拆任务、合并裁决 |
| 前端/后端开发 `frontend-dev` / `backend-dev` | `hy4` | 32k | `Task(frontend-dev)` / `Task(backend-dev)` | 已确认范围内的编码实现；推荐方案为纯前端改动，**本期不分派 `backend-dev`**（仅 D1 选 C 时启用） |
| 测试 `frontend-tester` / `backend-tester` / `tester` | `hy4` | 32k | `Task(frontend-tester)` / `Task(backend-tester)` / `Task(tester)` | 单端回归（前端契约/静态核对）+ 跨端验收签字；推荐方案只跑前端 |

> 说明：模板示例中的角色名 `pm` / `junior-dev` / `tech-lead` 在本项目**均不存在**（`.codebuddy/agents/` 无对应文件），已按现行 RACI 替换为真实角色 `doc-updater` / `architect`（评审）/ `frontend-dev`·`backend-dev` / `frontend-tester`·`backend-tester` / `tester`；示例型号 `qwen3.5:9b` / `qwen3.8:27b` 亦不照抄。型号列取各 agent 文件 `model` 字段**当前真实值 `hy4`**，该值属**用户临时决策**（见 `MODEL_REGISTRY.md` §70-79 事故记录），**不写死到流程文档**，分派前须以 agent 文件实时值为准，若报 `model not found` 按「选型速查」回退并在备注说明。

## 任务计划

> 本章是任务索引，只写任务标题 / 依赖 / 状态，不重复实施细节；详细步骤在确认后写入 `docs/sdd/plans/046/task-NN-*.md`。

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写本 spec | 本文件 | — | **已完成**（`待确认` → `已确认`） |
| 02 | 需求评审 | [`task-02-requirement-review.md`](../plans/046/task-02-requirement-review.md) | 01 | **已完成**（通过（附意见），2026-11-09） |
| 03 | 技术评审 | [`task-03-tech-review.md`](../plans/046/task-03-tech-review.md) | 01 | **已完成**（通过（附意见），2026-11-09） |
| 04 | 前端实现与自测 | [`task-04-frontend-implementation.md`](../plans/046/task-04-frontend-implementation.md) | 02, 03 | **已完成**（红→绿，报告 `runs/task-04/implementation.md`） |
| 05 | 前端契约/静态/单测与真实 E2E | [`task-05-frontend-regression-and-e2e.md`](../plans/046/task-05-frontend-regression-and-e2e.md) | 04 | **已完成**（`337 passed` + 真机 M1/M2/M3） |
| 06 | 验收评审与收口 | [`task-06-acceptance-and-closure.md`](../plans/046/task-06-acceptance-and-closure.md) | 05 | **已完成**（双签 + 台账/复盘/commit） |

> **全部 6 个任务已完成，spec 状态 `已完成`（2026-11-09）**。任务文档链接均为真实相对路径、依赖无环（01 → 02/03 → 04 → 05 → 06）。证据索引 `docs/sdd/plans/046/runs/task-04/` 与 `runs/task-05/`，三份评审见下，复盘 `docs/sdd/retro/2026-11-09-spec046-research-task-search.md`。

## 评审记录

> 三份评审均有真实结论；验收评审由 `tester` 产出、`architect` 签字。

- 需求评审：`docs/sdd/reviews/046-requirement-review.md`（**通过（附意见）**，2026-11-09 架构师评审子代理 `architect`；P0=0 / P1=4，4 条 P1 已由 `doc-updater` 消化）
- 技术评审：`docs/sdd/reviews/046-tech-review.md`（**通过（附意见）**，2026-11-09 架构师评审子代理 `architect`；P0=0 / P1=5，4 个可行性风险全部查实可纯前端解决，D1-B 准确调用链见该文档第六节）
- 验收评审：`docs/sdd/reviews/046-acceptance-review.md`（**通过**，2026-11-09 `tester` 产出；准备度 9/10、P0=0 / P1=0；**`architect` 已签字**，见该文档第 9 节）

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-11-09 | 架构师(自身) | 编写本 spec（待确认） |
| 2026-11-09 | 用户 | 「搜索按推荐方案确认 spec」，D1–D5 按推荐拍板，状态 `待确认` → `已确认`，台账已追加 |
| 2026-11-09 | 架构师 / `doc-updater` / `frontend-dev` | 需求·技术评审通过并消化 P1，`已确认` → `实施中`；完成纯前端红绿实现与单端回归 |
| 2026-11-09 | `tester` / `architect` / 主会话 | 验收评审通过并签字；真机 M1/M2/M3 E2E、台账、复盘、本地 commit 闭环，`实施中` → `已完成` |
