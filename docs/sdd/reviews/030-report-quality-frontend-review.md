# Spec 030 Task 09 前端评审

日期：2026-10-30  
评审角色：frontend-reviewer  
范围：本次 `frontend/**` 差异及对应前端测试；未评审 `backend/**`，未运行后端测试、全量回归、部署或 Git 操作。

## 结论

**最新页外目标增量：PASS / Approve。** 初审发现的旧列表并发覆盖 HIGH 已由 `taskListRequestGeneration` 守卫修复，窄复审通过旧列表失败与空结果成功两种延迟响应反例。此前报告质量增量的三项 HIGH 缺陷也均已修复并通过复核；历史记录保留如下。

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
| 资源版本 | PASS | 当前脚本版本为 `research-tasks.js?v=19`，样式版本仍为 `styles.css?v=67`，见 [index.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/index.html:8) 和 [index.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/index.html:804)。 |
| XSS | PASS | `frontend/research-tasks.js` 无 `innerHTML`；新反馈字段以 `textContent` 写入（约 2753–2770 行），报告正文仍使用既有安全 Markdown / HTML 渲染路径。 |
| CSS 作用域 | PASS | 新增样式均以 `#research-view` 开头，见 `frontend/styles.css:3719–3727`；没有裸全局选择器。 |

## 指定行为核对

- POST 的 202 只显示“已受理 / 生成中”；完成状态要求版本已发布且质量合同完整通过。测试覆盖 202 pending、随后轮询至发布。
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
