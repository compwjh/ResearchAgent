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
