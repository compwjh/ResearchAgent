# Spec 030 Task 09 前端实施报告

日期：2026-10-30  
角色：frontend-dev  
范围：仅报告工作区前端与对应前端契约测试；未修改后端、Spec、部署配置或 Git 状态。

## 实施内容

- 在既有报告卡片增加发布状态、报告阶段/实测耗时、质量指标、稳定原因码和未发布版本重试入口。
- 仅在 `report-quality-v1` 与 `count_method=report-quality-v1` 均存在时显示 CJK 正文、有效逐篇、比较、支持发现、定向改写与证据等级；不完整的历史 JSON 标记为“旧版，未按本质量合同核验”。
- 每个新报告提交创建 UUID `Idempotency-Key` 并暂存到本地存储；提交结果不确定时重试复用同一 key，成功受理后清除；后续用户主动重试生成新 key。
- 将 POST 响应视为受理信号，读取服务端 `report_url` 并轮询版本 JSON；只有 `completed + published=true + report-quality-v1 pass` 才显示“正式发布”。离开后重新打开任务时，沿用任务报告 GET 与既有事件游标恢复 generating 状态。
- 版本切换时重新取得对应版本的 artifact 列表。明确 `published=false` 或质量不通过时不渲染下载链接；保留旧版报告选择和已有发布版本的下载。
- 报告事件按合同阶段映射为安全文案，显示版本、改写轮数、实测耗时与稳定原因码；动态内容使用 `textContent` 和既有安全 Markdown 渲染。

## 变更文件

- `frontend/research-tasks.js`
- `frontend/index.html`（资源版本升至 `research-tasks.js?v=18`、`styles.css?v=67`）
- `frontend/styles.css`
- `tests/frontend/test_evidence_report_frontend_contract.py`
- `tests/frontend/test_research_session_workspace.js`
- `tests/frontend/test_report_action_race.js`
- `tests/frontend/test_plan_approval_select.js`（修正两处既有错误相对导入，并清理测试尾部轮询 timer）

## 前端自查

1. 新增 `research-report-*` DOM class 都有 CSS 规则，样式限定在 `#research-view`。
2. `research-tasks.js` 与 `styles.css` 均已同步更新 `index.html` 缓存版本。
3. `frontend/research-tasks.js` 未出现 `innerHTML`；报告状态、质量和原因码都通过 `textContent` 写入。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/research-tasks.js` | 0 | 语法通过 |
| `node tests/frontend/test_research_session_workspace.js` | 0 | 质量指标、正式/草稿/旧版状态、事件阶段/耗时、原因码及未发布/错误质量元数据下载门禁通过 |
| `node tests/frontend/test_report_action_race.js` | 0 | 任务/版本竞态通过；新增报告幂等、202 跟踪、质量 schema、v2→legacy 隔离、页外当前会话/通知及 boot 旧列表成功/失败竞态场景通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_evidence_report_frontend_contract.py -q` | 0 | 3 项静态契约测试通过 |
| `git diff --check` 及 CSS class、缓存版本、`innerHTML` 核对 | 0 | 无空白错误；样式/版本/XSS 自查通过 |

本 worktree 未配置本地 `.venv`，静态契约测试使用同一工作区的可用虚拟环境运行。

## 残项

- 未启动服务或执行浏览器视觉验收；本 Task 分派范围要求前端定向测试，不包含部署。需由后续验收角色在当前部署上验证自然语言主流程、报告事件恢复与实际 artifact 可见性。
- 未运行后端 pytest 或全量回归。

## 独立评审跟进

- 统一使用 `isQualityValidated` 判断正式发布：报告必须同时为 `completed`、`published=true`、质量 schema/count method 均为 `report-quality-v1` 且 `quality_validation.status=pass`。异步 poll 和提交读取路径不再单独相信 `status=pass`。
- 版本选择只使用目标版本的 canonical JSON、Markdown 与 artifact 结果构造 `state.report`，不再把当前版本对象 spread 到另一版本；这样旧版缺少质量/发布字段时显示未核验并清空质量指标。
- 增加恶意/陈旧 schema 的异步 poll 断言、v2→legacy v1 版本隔离断言；保留并发版本请求迟到响应不覆盖当前版本的测试。
- legacy 下载兼容现在只适用于完全没有 `quality_validation` 字段的 completed 旧报告；只要质量字段存在，就必须由 `isQualityValidated` 验证，不能因 `published` 缺失而走旧版回退。新增质量通过但发布字段缺失、malformed quality 且发布字段缺失、显式 `quality_validation: undefined` 均不可下载，同时保留纯旧版下载断言。

## 真实浏览器复现跟进

- 根因在前端：`loadTasks` 只读取 `/api/research-sessions?limit=100`，`refreshWorkspace` 只从这页列表选当前会话；列表没有目标 session 时会清空详情。通知点击只有同时带 task ID 才会触发任务选择；session-only 通知虽然标记已读，却只打开对话。即使直接按 session ID 调用选择，旧路径也不会从 session detail 恢复 task ID 并加载报告。
- 修复：当前会话优先从会话详情元数据、当前对话最后一个 Research Plan/Intake 卡片或同一对话通知恢复 session ID；列表没有目标 session 时直接 GET `/api/research-sessions/{id}`。session-only 选择从 owner-scoped detail 取 task ID，尝试读取 task 详情，继续用现有 report API 加载报告，并把该会话插回现有列表。通知携带 session ID 时也直接打开研究工作区并选择它。
- 新增回归覆盖：目标 session 不在前 100 条列表时从当前对话卡片直达已发布 v2；completed 通知没有 task ID 时仍从 session ID 恢复并加载 v2。两项测试已先在旧实现上复现失败，再在修复后通过。
- 本轮验证：`node --check frontend/research-tasks.js`、`node tests/frontend/test_report_action_race.js`、`node tests/frontend/test_research_session_workspace.js`、`node tests/frontend/test_research_report_notifications.js`、`node tests/frontend/test_plan_approval_select.js`、两个静态契约文件（13 passed）、test naming/layout 检查与 `git diff --check` 均通过；脚本缓存版本升至 `research-tasks.js?v=18`。
- `test_plan_approval_select.js` 原有两处相对导入指向不存在的 `tests/frontend/frontend/`；已改为项目内真实 frontend 路径，并清理该测试的轮询 timer，以便精准脚本自然退出。修复后 Task12 的三项审批/重选 race 断言全部通过。

## boot 列表请求竞态评审跟进

- 根因：`boot()` 会不等待地启动一次列表请求，工作区正常恢复又启动另一请求。旧请求缺少代际校验，其晚到的成功响应可覆盖新列表，拒绝响应会清空 `tasks`/`sessions`，即使目标 session、task 和 report 已由 owner-scoped 详情恢复成功。
- 修复：新增 `taskListRequestGeneration`。每个列表读取和显式选择都会推进代次；旧请求在列表读取后、session hydration 后及 `catch` 中发现自己已过期时直接返回当前列表，不再写 `tasks`/`sessions` 或错误状态。
- 新增真实 boot 流程测试：启动列表请求保持 pending；boot 定时工作区刷新加载 100 条旧列表并直达当前 session/task/report；随后分别令旧列表请求 reject 和 resolve 为空。两种情况下目标会话仍留在列表且报告 v2 保持已加载。
- 定向回归：`node tests/frontend/test_report_action_race.js` 覆盖上述两种旧请求结果并通过；语法、Session Workspace、通知、审批选择、静态契约、test naming/layout 与差异检查也通过。

## 通知目标详情与旧刷新竞态复核

- 真实 API 只读核对（conversation metadata、目标 session detail、通知 #222；报告正文及其他记录未读取）：conversation metadata 没有 session ID；通知的 `research_task_id` / `research_session_id` 在顶层，payload 仅含 report version、message ID 与 artifact IDs，没有 conversation ID；session detail 的 task ID 位于嵌套 `task`，顶层同时有 `conversation_id`。真实 detail 还可同时呈现 session `completed` 与 task `failed`，前端必须用合同投影处理该形状，不从通知 payload 猜测。
- 根因：通知路径先用 session ID 取到 owner-scoped detail，但只要通知顶层带 task ID，`selectTask` 就绕过 detail 内嵌 task 并依赖单独 task 查询；此外，通知打开时启动的旧 `refreshWorkspace` 可在通知选择完成后继续按其 100 条列表结果清空详情。前者使已有会话详情未被利用，后者与真实“短暂恢复后清空”的时间序列吻合；未读取 task endpoint，未改后端。
- 修复：当通知 task ID 与已取 session detail 投影的 task ID 一致时，直接复用 owner-scoped session/task 投影；`refreshWorkspace` 记录开始时的任务选择代次，在 conversation/list await 前后检测代次变化，任何更晚的显式选择都阻止旧刷新清空或重选详情。
- 新增真实响应形状回归：顶层 task/session ID、无 payload conversation ID、session 中嵌套 task、报告 v5；旧 100 条列表请求保持 pending，通知选择并加载报告后再返回旧列表。先验证旧实现发起多余 task 查询并失败，再验证目标仍选中、v5 正文保留、目标会话仍在列表。
- 本轮验证：`node --check frontend/research-tasks.js`、`node tests/frontend/test_report_action_race.js`、`node tests/frontend/test_research_session_workspace.js`、`node tests/frontend/test_research_report_notifications.js`、`node tests/frontend/test_plan_approval_select.js` 均退出 0；两项前端静态 pytest 共 13 passed；`git diff --check` 通过。脚本资源版本升至 `research-tasks.js?v=19`。真实诊断只 GET 三项指定 API，未请求 task endpoint、未修改后端/部署/数据库。

## 报告版本选择与刷新恢复复核

- 真实浏览器复现：通知 #222 的报告版本为 v5，但所选研究任务的计划版本仍为 v1；报告区最初显示 v1。版本选择器渲染函数每次都会将 `<select>` 重设成当前 `state.report` 版本，因此手动选择 v5 后，目标请求开始时控件立即跳回 v1。终态 SSE 又调用 `loadReport()`，该函数只读默认 `/report` 版本，随后以计划 v1 覆盖已选择的报告。
- 真实 v5 JSON 的脱敏字段核对：顶层含 `report_content`（结构化对象）、`quality_validation`、`generation`、`report_version` 等；质量字段为 `report-quality-v1`/`pass`、正文计数 2912、5 篇论文、5 项比较、6 项支持发现、revision 0。捕获样本当时尚未提供顶层 `status`/`published` 或 Markdown 字符串；没有从研究任务的 `failed` 状态推断报告状态，也没有合成报告正文。父会话随后确认后端读取修复已部署为 `404279dd`，真实 v5 JSON 现返回 `completed`/`published=true`/质量指标，Markdown API 返回 HTTP 200 和 11905 字节；前端继续依赖版本化 canonical JSON 和 Markdown API。
- 修复：通知报告版本先按 task ID 记录；版本控件在异步请求期间尊重 pending 选择。各 task 分别记忆已明确选择的报告版本；终态/工作区刷新从该版本重新读取 JSON、Markdown 和同版 artifact，报告版本状态只由该 canonical 对象构造，不继承 `/report` 计划版本上的质量/发布字段。版本请求开始时会使旧的 report refresh 失效，旧刷新不能回写 v1。新生成的报告接受后将其新版本设为当前选择。
- 新增精确测试覆盖真实 v5 字段形状（结构化 `report_content`、2912 指标、显式 durable status/published）、通知 v5 与基础计划 v1 分离、Markdown 按 v5 读取、下拉框异步选择保持，以及启动旧版本刷新后选 v5、旧响应迟到、后续终态刷新恢复 v5 的时序。
- 本轮定向验证：`node --check frontend/research-tasks.js`、`node tests/frontend/test_report_action_race.js`、`node tests/frontend/test_research_session_workspace.js` 与 `node tests/frontend/test_research_report_notifications.js` 均退出 0。前端资源版本升至 `research-tasks.js?v=20`；未改后端、spec 或部署，未运行后端 pytest。
- 残项：前端测试和节点语法检查通过；父会话需在修复后的部署版本复核真实浏览器中的 v5 正文、指标、通知打开与终态 SSE 刷新。前端未部署，也未独立重启或改动后端。

## 202 受理响应发布边界复核

- 独立评审指出 POST 202 body 即使含有 `completed`、`published=true` 和 report-quality-v1 pass，也只能证明请求已受理，不能作为报告 canonical 状态；旧实现 spread 整个 body 会提前显示正式发布。
- 修复：受理响应仅保留已校验的 report version，前端固定投影为 `generating`、`published=false`、`generation.published=false` 与 `quality_status=pending`，不把受理 body 的 quality/generation 字段带入报告。版本化 canonical GET 成功前，不显示质量指标、正式发布或下载；读取失败仍留在生成中并安排同版本轮询/读取重试。
- 测试：将伪正式的 202 body 加入现有幂等/轮询测试；新增 canonical GET 返回 500 场景，断言报告保持生成中、没有质量指标和下载、且继续追踪。现有延迟轮询测试仍验证 canonical GET 返回合规 completed + published + quality-v1 pass 后才转正式并读正文。
- 定向验证：`node --check frontend/research-tasks.js`、`node tests/frontend/test_report_action_race.js`、`node tests/frontend/test_research_session_workspace.js` 与 `git diff --check -- frontend/research-tasks.js frontend/index.html tests/frontend/test_report_action_race.js` 均退出 0；缓存版本升至 `research-tasks.js?v=21`，未发现 `innerHTML`。未跑后端测试、未部署。

## 静态前端契约同步（2026-10-31）

前端 tester 的 R3 全量重跑（由 root 转报）为 **385 passed / 0 skipped，另有 3 个静态失败**；所有浏览器用例实际通过。3 个静态失败正是以下陈旧断言：它们仍引用旧入口缓存版本或旧提示。当前生产源码与此前已确认的前端行为一致，因此只同步测试预期，没有改生产代码。

| 精确测试节点 | 旧预期 → 新预期 | 依据 |
|---|---|---|
| `test_frontend_management_contract.py::test_keeps_static_asset_versions_and_scoped_css` | `styles.css?v=66` → `styles.css?v=67` | 当前入口 `frontend/index.html:8` 引用 v67；Spec030 前端评审 `docs/sdd/reviews/030-report-quality-frontend-review.md:24` 也确认 styles v67。`app.js?v=66` 仍是当前入口版本，原断言保持不动。 |
| `test_paper_issue_ui_contract.py::test_report_action_uses_an_explicit_versioned_generation_button` | `research-tasks.js?v=16` → `research-tasks.js?v=21` | 当前入口 `frontend/index.html:804` 引用 v21；Spec030 前端评审 `docs/sdd/reviews/030-report-quality-frontend-review.md:24` 确认 v21。精确版本门禁仍保留。 |
| `test_paper_issue_ui_contract.py::test_report_action_failure_restores_the_previous_report_for_retry` | 已不存在的 `旧报告保持不变` → 当前提示 `提交结果尚未确认；重试会沿用同一请求标识，避免创建重复版本。` | `frontend/research-tasks.js:2267` 是现行用户提示；`generateReportVersion()` 仍将 `state.report`、视图、版本列表与格式恢复到前一快照。测试原有 `state.report = previousReport` 回滚断言保留。Task09 合同要求不覆盖旧版本且失败可重试，Spec030 前端评审 v21 PASS。 |

### 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_frontend_management_contract.py::test_keeps_static_asset_versions_and_scoped_css tests/frontend/test_paper_issue_ui_contract.py::test_report_action_uses_an_explicit_versioned_generation_button tests/frontend/test_paper_issue_ui_contract.py::test_report_action_failure_restores_the_previous_report_for_retry -q` | 0 | 3 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q tests/frontend/test_frontend_management_contract.py::test_keeps_static_asset_versions_and_scoped_css tests/frontend/test_paper_issue_ui_contract.py::test_report_action_uses_an_explicit_versioned_generation_button tests/frontend/test_paper_issue_ui_contract.py::test_report_action_failure_restores_the_previous_report_for_retry` | 0 | 3 collected，无 collection error |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check tests/frontend/test_frontend_management_contract.py tests/frontend/test_paper_issue_ui_contract.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | test layout: ok |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | 无 spec/task 编号违规 |

**交接状态：** 三处陈旧预期已按精确版本和当前提示同步；版本门禁及旧报告恢复断言保留。改动已冻结，待 frontend-reviewer 独立复核；本次未改生产代码或部署。
