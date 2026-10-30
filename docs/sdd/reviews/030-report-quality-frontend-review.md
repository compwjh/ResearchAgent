# Spec 030 Task 09 前端评审

日期：2026-10-30  
评审角色：frontend-reviewer  
范围：本次 `frontend/**` 差异及对应前端测试；未评审 `backend/**`，未运行后端测试、全量回归、部署或 Git 操作。

## 结论

**最新 v21 报告版本增量：PASS / Approve。** v20 发现的 202 响应伪发布问题已修复：POST 受理结果始终投影为 generating / quality pending / unpublished；只有版本号匹配的 canonical GET 才能提供质量和发布字段。GET 失败与成功两例均通过窄复审，先前 v5 通知版本路径也保持通过。

## 历史发现与修复复核

| 历史发现 | 当前修复与证据 | 当前状态 |
|---|---|---|
| 正式发布门禁只看 `quality_validation.status=pass`，未要求 `schema_version`、`count_method` 同为 `report-quality-v1`，可把字段不完整的版本标成已发布。 | [research-tasks.js](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/research-tasks.js:301) 定义完整 schema 检查；`isQualityValidated` 同时要求 completed、published=true 与质量 pass。生成和轮询均复用该判定（约 312、1974、2139 行）。 | 已修复；畸形质量对象不再正式发布或提供下载。 |
| 选择旧报告版本时把 `previousReport` 与目标版本合并，缺质量字段的旧版会继承当前版的通过状态和指标。 | 版本选择现从目标 `canonical` 构造 `state.report`，不继承前一版字段（[research-tasks.js](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/research-tasks.js:2895)）。Fake DOM 复现现返回旧版未知且不显示质量指标。 | 已修复。 |
| 下载兼容分支把所有 completed 且 publication 字段缺失的响应当作旧版，可能让含质量字段但缺少 published 标记的版本出现下载链接。 | [research-tasks.js](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/research-tasks.js:317) 现在只对质量字段完全不存在的历史版本保留兼容；质量合同存在时必须通过完整发布门禁。测试覆盖畸形/缺发布标记与纯旧版兼容（`test_research_session_workspace.js:107–130`）。 | 已修复。 |

## 前端四项必守

| 检查项 | 结果 | 代码依据 |
|---|---|---|
| DOM / CSS 契约 | PASS | 新增反馈区 ID/class 在 [index.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/index.html:331)、[research-tasks.js](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/research-tasks.js:2761) 与 [styles.css](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/styles.css:3719) 双向对应。新增 CSS 钩子均限定在 `#research-view`。 |
| 资源版本 | PASS | 当前脚本版本为 `research-tasks.js?v=21`，样式版本仍为 `styles.css?v=67`，见 [index.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/index.html:8) 和 [index.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/index.html:804)。 |
| XSS | PASS | `frontend/research-tasks.js` 无 `innerHTML`；新反馈字段以 `textContent` 写入（约 2753–2770 行），报告正文仍使用既有安全 Markdown / HTML 渲染路径。 |
| CSS 作用域 | PASS | 新增样式均以 `#research-view` 开头，见 `frontend/styles.css:3719–3727`；没有裸全局选择器。 |

## 指定行为核对

- 202 无论响应体声称什么，都只投影为“已受理 / 生成中”；canonical 版本读取成功后才展示对应质量状态，且完整质量合同通过后才标记正式发布。v20 伪发布反例已在 v21 修复并复核通过，见本报告末尾。
- 幂等 key 使用 UUID 并持久化；提交结果不确定时重试复用同 key，收到受理后清理；用户主动重试使用新 key。`test_report_action_race.js` 覆盖同 key 网络重试和新 key。
- 版本竞态由 request ID 守卫；切换任务时递增 task generation 并取消定时器。正在飞行的轮询响应再检查 poll identity 和 task generation，离开当前任务后不写入状态。
- 阶段、版本、改写轮数、实测 elapsed 与稳定原因码通过安全文案显示；离页重进从当前报告恢复 generating 并重新启动版本轮询。
- 草稿和质量失败报告不显示 Artifact 下载链接；仅纯旧版（没有 `quality_validation` 字段）继续保留历史下载兼容。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/research-tasks.js` | 0 | 语法通过 |
| `node tests/frontend/test_research_session_workspace.js` | 0 | 前端会话/质量/旧版/下载契约通过 |
| `node tests/frontend/test_report_action_race.js` | 0 | 任务隔离、版本竞态、202、幂等重试通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_evidence_report_frontend_contract.py -q` | 0 | 3 passed |
| `git diff --check -- frontend/index.html frontend/research-tasks.js frontend/styles.css tests/frontend/test_evidence_report_frontend_contract.py tests/frontend/test_report_action_race.js tests/frontend/test_research_session_workspace.js` | 0 | 无空白错误 |

## 质量报告增量 Review Summary（历史结论）

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | info |
| LOW | 0 | note |

Verdict: **APPROVE** — 该轮质量报告差异无未解决的 CRITICAL 或 HIGH 问题；不代表后续页外目标增量通过。

评审日志：`.codebuddy/agent-logs/spec-030/task-09/frontend-reviewer/20261030-125831.md`

## 页外会话目标 / 通知直达增量初审记录（已修复）

### 结论

初审结论为 **BLOCK — HIGH**：目标会话可从当前 conversation metadata、最后一张 research card 或同会话 notification 解析，并由 `selectTask` 通过 session/task 详情载入；当时 `loadTasks()` 的失败分支在 [research-tasks.js](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/research-tasks.js:1088) 不区分请求新旧，无条件清空 `state.tasks` 和 `state.sessions`。窄复审确认该问题现已修复，见下节。

### 可复现反例

Fake DOM 探针按真实页面时序执行：`boot()` 启动的列表请求 A 保持 pending；并发 `refreshWorkspace()` 从 conversation metadata 得到真实 `session-target`，列表请求 B 返回空列表，随后 owner-scoped session 详情和 task 详情成功，报告正文加载并将目标插入列表；最后请求 A reject。结果为 `before=true`、`after=false`，同时 `selectedSessionId=session-target`、`selectedTaskId=task-target`、`selectedReport='published body'`。这证明失败的旧请求会覆盖列表；初审时新增测试只覆盖超过前 100 条恢复和 session-only 通知直达，未覆盖该并发交错。后续已追加旧请求 reject 与空列表 resolve 两个用例，见窄复审。

初审建议加入列表请求代次或等价守卫。作者已实现并在冻结差异上复核，修复证据见下节。

### 本轮通过项与验证

- 100 条列表外的真实 session ID 能通过详情接口恢复对应 task/report 并加入现有列表；session-only 完成通知可标记已读并直达该报告。新增目标测试通过。
- DOM/CSS 变更没有发现新增契约；脚本资源版本更新到 `v18`，XSS 与 CSS 作用域延续此前 PASS。
- `node --check frontend/research-tasks.js`：退出码 0。
- `node tests/frontend/test_report_action_race.js`：退出码 0。
- `node tests/frontend/test_research_session_workspace.js`：退出码 0。
- `node tests/frontend/test_plan_approval_select.js`：退出码 0。
- `node tests/frontend/test_research_report_notifications.js`：退出码 0。
- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_research_report_notifications_contract.py tests/frontend/test_research_plan_cards_contract.py -q`：退出码 0，13 passed。
- 并发旧列表失败探针：复现目标从列表消失，未通过。


## 窄复审：列表请求 generation 守卫

### 结论

**PASS / Approve。** `loadTasks()` 在请求启动时取得 `taskListRequestGeneration`；取得列表响应后、所有 session hydration 完成后，以及失败分支写状态前均检查该 generation。`selectTask()` 开始时推进代次，因此旧启动请求在新目标被选中后无论成功或失败都不能提交列表状态。

### 指定竞态反例

新增 Fake DOM 探针真实调用 `api.boot()`：boot 自己的列表请求 A 保持 pending；boot 定时器触发正常 workspace refresh，识别 conversation metadata 中 `session-target`，加载 session/task 和已发布 v2 报告，并将目标插入列表；随后分别让 A reject、以及让 A resolve 一个空列表。两种情况下测试均断言 selected task/session、v2 report 和目标列表项保持不变。前者覆盖旧失败 catch，后者覆盖旧成功响应；成功响应的 generation 守卫位于请求后和 hydration 后，能阻止列表替换。

### 验证

- `node --check frontend/research-tasks.js`：退出码 0。
- `node tests/frontend/test_report_action_race.js`：退出码 0，包含旧请求 reject/resolve 两个 boot 并发用例。
- `node tests/frontend/test_research_session_workspace.js`：退出码 0。
- `node tests/frontend/test_plan_approval_select.js`：退出码 0。
- `node tests/frontend/test_research_report_notifications.js`：退出码 0。
- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_research_report_notifications_contract.py tests/frontend/test_research_plan_cards_contract.py -q`：退出码 0，13 passed。

本次只窄复核列表请求竞态，没有运行后端测试、全量测试、部署或 Git 操作，也未修改业务代码。前述初审 BLOCK 标记为已修复；最新前端增量 PASS。

## 窄复审：通知真实形状与 refresh 竞态

### 结论

**PASS / Approve。** 通知 ID 222 的新增 fixture 覆盖根级 `research_task_id` / `research_session_id`、无 `payload.conversation_id`、仅在 payload 携带 report version/message/artifact IDs 的形状。前端先用 session ID 读取 owner-scoped session detail，从其 `conversation_id` 打开对话，并复用 detail 中匹配 task ID 的嵌套 task projection；不再依赖额外 `/research-tasks/{taskId}` 请求。报告版本 5 加载成功。

`refreshWorkspace()` 在对话和列表请求 await 前捕获 `taskGeneration`，并在 await 后校验。通知选择若在旧 refresh 期间开始，旧 refresh 会直接返回当前 task list，不执行 reset/重选覆盖。新增延迟旧列表返回用例确认 target 仍在列表、task/session 仍选中且报告 v5 保留。

### 验证

- `node --check frontend/research-tasks.js`：退出码 0。
- `node tests/frontend/test_report_action_race.js`：退出码 0，包含 notification #222 nested-task response 与旧列表晚回竞态。
- `node tests/frontend/test_research_session_workspace.js`：退出码 0。
- `node tests/frontend/test_plan_approval_select.js`：退出码 0。
- `node tests/frontend/test_research_report_notifications.js`：退出码 0。
- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_research_report_notifications_contract.py tests/frontend/test_research_plan_cards_contract.py -q`：退出码 0，13 passed。

本轮只审查通知响应形状和 refresh 竞态，未运行后端测试、全量测试、部署或 Git 操作，也未修改业务代码。最新前端差异 PASS，可进入主Agent要求的浏览器通知路径复测。

## 窄复审：v20 通知版本身份与手选保持、202 初审

### 通过项

- 通知版本按 `research_task_id` 写入 `reportVersionSelections`，不再从 `current_plan_version` 推导；真实响应夹具为 plan v1、report v5，canonical JSON 返回 `report_content` 对象及 `quality_validation.cjk_count=2912`，Markdown 正文通过版本化 Markdown 路由读取。报告状态、质量值和正文均对应 v5。
- 手动选择 v5 时 `pendingReportVersion` 让下拉在等待期间保持 v5；成功后按 task ID 记忆选择。后续 `loadReport()` 和 terminal/SSE 刷新读取该 task 的 canonical v5 JSON/Markdown，不用默认 legacy `/report` v1 覆盖。
- 选择和加载均由 task generation / request ID 守卫；版本记忆以 task ID 为 key。切换 task 会更新 task generation，旧 task 的异步选择/加载不能写进当前 task。新增延迟 default report 与 Markdown 响应的探针通过。
- 脚本资源版本更新到 `research-tasks.js?v=20`。

### v20 BLOCK — HIGH 发现（v21 已修复）

`generateReportVersion()` 收到任意 2xx POST 响应后，会把响应体的 `status`、`published`、`generation.published` 和 `quality_validation` 直接复制进 `state.report`（[research-tasks.js](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/research-tasks.js:2183)）。随后 `readGeneratedReportVersion()` 若 canonical GET 失败，会恢复其入口时保存的 `previousReport`，即这份未经 canonical 确认的 POST 响应。标准 generating/published=false fixture 不暴露此路径。

最小 Fake DOM/API 探针让 POST 返回 HTTP 202，响应体人为带 `status=completed`、`published=true`、`generation.published=true` 及完整 `report-quality-v1/status=pass`；其后 canonical `/reports/5?format=json` 返回 500。最终状态为 action `retryable`，但 `state.report` 仍是 v5 completed，`isQualityValidated(state.report) === true`、`cjk_count=2912`。因此 202 响应本身可以被 UI 判定为正式发布，违反“202 仅表示受理”。

修复要求：将 POST 202 响应强制投影为受理/生成中状态、清除发布与质量通过字段；只有版本号一致的 canonical GET 结果可覆盖为已发布，并补充 canonical GET 暂时失败 fixture。v21 已满足并通过下节复核。

### 验证

- `node --check frontend/research-tasks.js`：退出码 0。
- `node tests/frontend/test_report_action_race.js`：退出码 0。
- `node tests/frontend/test_research_session_workspace.js`：退出码 0。
- `node tests/frontend/test_plan_approval_select.js`：退出码 0。
- `node tests/frontend/test_research_report_notifications.js`：退出码 0。
- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_evidence_report_frontend_contract.py -q`：退出码 0，3 passed。
- v20 202 伪发布 body + canonical GET 500 聚焦探针：曾复现 `isQualityValidated(state.report) === true`；v21 修复后的回归断言见下节。

本轮只复核版本身份、手动选择保持、跨 task 隔离和 202 发布边界；未运行后端测试、全量测试、部署或 Git 操作，也未修改业务代码。页外目标、通知真实形状及 v20 报告身份增量历史结论保持 PASS；v20 的 202 BLOCK 在 v21 关闭。

## 最终窄复审：v21 202 接受投影

### 结论

**PASS / Approve。** `generateReportVersion()` 现在不把 POST 响应的 status、published、generation 或 quality 字段复制到 `state.report`；只保留返回的版本号，并固定设置 `status='generating'`、`quality_status='pending'`、`published=false`、`generation.published=false`、空正文/产物。canonical GET 由 `readGeneratedReportVersion()` 校验对象和报告版本 ID 后才写入报告状态。

新增伪发布 202 fixture 返回 HTTP 202 + completed/published=true + 完整 quality pass，随后 canonical JSON GET 返回 500。断言报告仍为 generating、未发布、质量字段未知、无指标/下载链接，action 保持 retryable 并继续轮询。成功路径通过 canonical generating 响应后，后续 canonical poll 返回 completed/quality pass，才将 action 标成 completed。

### v5 路径未回退

同一目标 Node 测试仍覆盖 plan v1 / report v5 的真实响应形状：通知版本按 task 预选；从 canonical v5 JSON 的对象型 `report_content` 读取 `quality_validation.cjk_count=2912`，再从 v5 Markdown 路由读取正文。手动选择 v5 在延迟 legacy v1 报告和后续 `loadReport()` 刷新期间保持；task-keyed 版本选择和请求代次隔离仍通过。

### 验证

- `node --check frontend/research-tasks.js`：退出码 0。
- `node tests/frontend/test_report_action_race.js`：退出码 0；含 202 伪发布 + canonical 500、canonical 成功发布及 v5 通知/手选保持用例。
- `node tests/frontend/test_research_session_workspace.js`：退出码 0。
- 未运行后端测试、全量测试、部署或 Git 操作；未修改业务代码。v21 前端增量 PASS，可供主 Agent 继续浏览器通知路径最终复测。
