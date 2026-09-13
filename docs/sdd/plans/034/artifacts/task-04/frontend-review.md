# Spec034 Task04 前端复审报告

## 固定字段

- spec：034 — 会话式深度研究与真实子 Agent Runtime
- task：Task04 — 计划版本、统一审批命令与前端卡片
- reviewer：frontend-reviewer（当前执行 Agent）
- review_base：当前工作树相对 `1879fb3` 的前端实际差异
- review_scope：`frontend/app.js`、`frontend/research-tasks.js`、`frontend/index.html`、`frontend/styles.css`、`tests/test_frontend_spec034_task04_contract.py`；只读复审
- conclusion：GO
- blocking_levels：P0=0，P1=0，P2=0

## 结论

GO。上一轮发现的 Research Tab Session projection、旧 `/feedback` 旁路、unknown kind、stale/conflict 刷新及跨端 `scope/safe_summary` 字段接缝均已修复。任务详情现在 owner-scoped 返回白名单计划/审批，前端同时优先消费 `scope`/`safe_summary` 并兼容旧别名；capability/resource 审批会把展示范围正确转换为统一 command payload。旧按钮已移除，过期/竞争状态禁用旧卡并提供刷新；定向测试、Node、静态安全和 diff 门禁通过，可进入下一门禁。

## 首轮问题（已关闭）

### 已关闭：Research Tab 的 Session 计划/审批投影在当前 API 接线下不可达

- 证据：`frontend/research-tasks.js:784-801` 只在旧任务详情包含 `task.session_plan`/`task.research_session_id` 等字段时渲染，随后才请求 `GET /api/research-sessions/{id}`。
- 当前响应：`backend/app/api/routes_research.py:440-451` 的 `GET /api/research-tasks/{research_task_id}` 仅返回 `_task_summary`、旧 ResearchPlan 和时间戳，没有 Session ID、`session_plan` 或 `session_approvals`；当前路由也没有供该 Tab 使用的 Session 列表/按 Task 解析接缝。因而 `research-session-plan-section` 通常一直 hidden，新三类审批按钮不能在 Research Tab 找到。
- 影响：Spec034 要求计划/能力/资源审批可在会话和 Research Tab 完成；当前会话消息卡可达不等于 Tab 入口可用。
- 最小修复建议：由同一产品入口提供 owner-scoped Session projection（任务详情至少返回 `research_session_id`，或 Tab 消费有 `research_task_id` 的 Session 列表），并为历史/刷新返回 `plan` 与 `approvals`；前端继续只消费该 projection，不自行猜测或复制 Session 存储。

### 已关闭：Research Tab 保留旧 `/feedback` 批准旁路，未统一到 Task04 命令合同

- 证据：`frontend/index.html:194` 保留“批准计划并开始执行”按钮；`frontend/research-tasks.js:872-905` 的 `approveTask()` 仍 POST `/api/research-tasks/${taskId}/feedback`，body 只有 `{action: "approve"}`。
- 影响：该按钮没有 `command`、`subject_version`、`scope_json`、`idempotency_key`，与 `frontend/research-tasks.js:430-455`/`frontend/app.js:1596-1611` 的统一命令不同；双击、多窗口、旧版本和自然语言/按钮竞争可能走两套语义，违反“所有按钮与自然语言调用同一命令层”。它也使旧 `waiting_approval` 任务看起来像 Task04 计划审批，却绕过三类 Approval 状态和 stale/conflict 映射。
- 最小修复建议：移除/隐藏该旧批准控件，或先解析并绑定对应 Session 后只调用统一 `/api/research-sessions/{id}/commands` 的 `approve_plan`，使用当前 plan version、allowlisted scope 和按钮稳定幂等键；保留旧 Task 监控/取消兼容时不得保留第二个批准实现。

## 首轮问题（已关闭）

### 已关闭：会话 renderer 将未知审批 kind 伪装成计划审批

- 证据：`frontend/app.js:1619-1628` 仅过滤状态，随后 `const kind = RESEARCH_APPROVAL_LABELS[approval.kind] ? approval.kind : 'plan'`；未知/未来/污染的 kind 会显示“计划审批”并生成 `approve_plan` 按钮。Research Tab 的对应代码 `frontend/research-tasks.js:439-450` 会过滤未知 kind，行为不一致。
- 影响：不可信 projection 的未知审批被错误标识并可能诱导用户提交错误命令。后端最终会校验，但 UI 白名单应 fail-closed，不能把未知能力请求降级为计划批准。
- 最小修复建议：在 `renderConversationApprovals` 先按 `RESEARCH_APPROVAL_LABELS[approval.kind]` 过滤，未知 kind 只保留安全诊断（或完全丢弃），不得创建审批按钮。

### 已关闭：stale/conflict 状态没有在当前卡片上提供刷新后的可恢复接缝

- 证据：`frontend/app.js:1606-1611` 和 `frontend/research-tasks.js:406-414` 在 `APPROVAL_STALE`/`PLAN_VERSION_STALE`/`APPROVAL_CONFLICT` 后把原按钮重新设为 `disabled=false`，保留旧的 `subject_version` 闭包和原 `idempotency_key`；会话卡没有刷新 Session/最新计划的操作。
- 影响：直接再次点击仍会重复提交旧版本并再次 stale/conflict；Spec034 要求过期卡保留历史但禁用，失败恢复应进入可重试/刷新后的新卡片。普通 error 可以同 key 重试，但 stale/conflict 不应伪装成可直接重试。
- 最小修复建议：stale/conflict 后禁用旧按钮，并提供“刷新计划/重新加载会话”动作；刷新后以新 `subject_version` 和新卡片幂等键重绘待审批卡。若产品选择允许刷新页面恢复，也应至少禁用旧卡并明确 focusable 的刷新入口。

## 本轮新发现（已关闭）

### 已关闭：Task detail 审批 projection 的字段名与 Research Tab command scope 不兼容

- 证据：`backend/app/api/routes_research.py:296-321` 的 `_approval_payload()` 将经过白名单的请求范围命名为 `scope`；`frontend/research-tasks.js:399-405` 的 `sessionCommandScope()` 只读取 `approval.requested_scope_json`。
- 故障表现：`GET /api/research-tasks/{id}` 返回的 capability/resource approval 在 Tab 首次渲染或 `GET /api/research-sessions/{id}` 失败的回退路径中，按钮会构造 `skill: ''`、空 tools 或 0 额度，后端 `CAPABILITY_NOT_AUTHORIZED`/错误额度，而不是批准 projection 中展示的范围。定向 Python probe 实际看到 capability projection 为 `{scope: {skill: 's', tools: ['t']}}`。
- 最小修复建议：冻结 task-detail 与 session-detail 相同的 approval DTO（推荐前端同时读取 `scope` 作为兼容别名，或后端输出 `requested_scope_json` 的解析对象），并新增 capability/resource Tab 回退提交测试，确保 scope 与 UI 展示/命令 payload 一致。

### 已关闭：Task detail 计划安全摘要命名不一致，降级路径丢失“降级策略”字段

- 证据：`backend/app/api/routes_research.py:275-293` 输出 `safe_summary`；`frontend/research-tasks.js:42-47,370-396` 的白名单字段为 `safety_summary`，只读取 `safety_summary` 或 `safety_summary_json`。
- 影响：任务详情首次渲染或 Session detail 请求失败时，计划卡的“降级策略”显示“未提供”；Session detail 成功后因返回原始 `safety_summary_json` 才可能恢复，两个 projection 不一致。
- 最小修复建议：统一 DTO 字段名为 `safety_summary`（或前端显式兼容 `safe_summary`），并在任务详情合同测试断言该字段被显示。

## 本轮已通过项

- **owner/白名单任务详情**：`routes_research.py:497-527` 先由 owner-scoped Task 查询，再用 `get_session_by_task(..., OWNER_ID)`；计划和审批仅输出固定字段，未输出幂等内部字段。
- **统一入口与状态修复**：`frontend/research-tasks.js:435-450`、`frontend/app.js:1614-1630` 继续统一 POST 命令、稳定幂等键、subject version；旧批准按钮和 `/feedback` 路径已从本轮前端删除。unknown kind 在 `app.js:1638` 与 Tab `research-tasks.js:457` 均 fail-closed；stale/conflict 禁用旧按钮并追加 refresh action。

## 已通过项

- **计划字段白名单与不泄露敏感内容**：`frontend/app.js:1441-1531` 与 `frontend/research-tasks.js:42-47,348-397` 仅投影 objective/scope/work_items/capabilities/budget/report_structure/safety_summary；嵌套对象只取固定键，动态内容走 `textContent`/`replaceChildren`，新计划 renderer 不使用 `innerHTML`，未展示 prompt、CoT 或任意 URL（scheme URL 被丢弃）。
- **会话消息/SSE 复用**：`frontend/app.js:1177-1194,2662-2673,2759-2764` 将历史 `plan/research_plan/approval(s)` 与实时事件挂到现有 assistant message/bubble；不新建第二条消息流。
- **统一新命令形状**：`frontend/app.js:1596-1601` 与 `frontend/research-tasks.js:420-430` 均提交 `{command, subject_version, scope_json, idempotency_key}`，六种命令文案/分派齐全；按钮点击期间禁用并在成功后锁定。
- **状态与可观察性**：两套新 renderer 均有 loading/success/error/stale/conflict class、`data-state`、`aria-busy` 和错误恢复分支；审批状态/版本/请求 ID 用文本节点展示。
- **Research Tab DOM 与可达性基础**：`frontend/index.html:181-225` 有明确会话计划 section、`dl` 字段和 `aria-live="polite"` 审批容器；新增按钮均为 `type="button"`，既有 Research 导航保留键盘 Enter/Space 路径（`research-tasks.js:953-960`）。
- **CSS/资源与 XSS 静态边界**：新增 conversation/Research Tab class 在 `frontend/styles.css:122-166,3440-3458` 有对应规则并按 `#research-view` 作用域隔离；`frontend/index.html:8,679` 的 `app.js`/`styles.css` 已同步为 `?v=45`。静态资源由后端 `NoCacheStaticFiles` 回源校验，未将 `research-tasks.js?v=1` 单独认定为阻塞项。
- **与既有功能边界**：本轮前端没有新增搜索、AgentRunner、报告执行或第二套持久化；旧 Task 时间线/报告 renderer 保持存在。既有 `setConversationAnswer` 的 Markdown `innerHTML` 不在本轮新增计划 renderer 内，仍走已有净化路径。

## P0/P1/P2 汇总

- P0：无。
- P1：无。本轮复审确认 Task detail approval scope 接缝已修复。
- P2：无。本轮复审确认 safe summary 展示接缝已修复。

## 验证命令与退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js && node --check frontend/research-tasks.js` | 0 | 两个 JavaScript 文件语法通过 |
| `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task04_contract.py tests/test_frontend_conversation_contract.py` | 0 | 28 passed |
| `.venv/bin/ruff check tests/test_frontend_spec034_task04_contract.py --output-format concise` | 0 | 合同测试 Ruff 通过；Ruff 不适用于 JS/HTML/CSS |
| 静态 DOM/XSS/URL/CoT/class/accessibility/version 检查（Node/rg） | 0 | 计划 renderer 无新 `innerHTML`/prompt/CoT，新增 class 存在，app/styles 为 `v45`，状态和 ARIA 标记存在 |
| `git diff --check 1879fb3 -- frontend/app.js frontend/research-tasks.js frontend/index.html frontend/styles.css tests/test_frontend_spec034_task04_contract.py` | 0 | 通过 |

## 复审边界

- 本次仅读取并更新本报告；未修改业务代码、Spec、Task/状态台账，未 commit/push/merge/reset/stash/clean。
- 本轮复审通过跨端字段接缝实际 probe 与静态检查；未在本任务代改业务代码。仍建议后续浏览器级会话/Tab 审批 smoke。
- 复审进展日志：`.codebuddy/agent-logs/spec-034/task-04/frontend-reviewer/20260913-020000.md`。
