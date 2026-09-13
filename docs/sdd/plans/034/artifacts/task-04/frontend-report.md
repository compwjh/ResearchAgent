# Spec034 Task04 前端交付报告

状态：前端实现及 frontend-review P1/P2 修复完成；frontend-reviewer/frontend-tester 已 GO，Task04 双端验收完成。

执行元数据：2026-09-13（Asia/Shanghai）；执行模型为当前执行 Agent 自身（主 Agent 指定本轮 Luna high）；未使用网络、未改 backend、未 commit/push/merge/reset/stash/clean。

## 改动文件

- `frontend/app.js`：复用既有 assistant message/SSE 与历史消息 renderer，新增计划字段白名单投影、三类审批按钮、revise/cancel/decline 入口和统一 `/api/research-sessions/{id}/commands` 请求；所有动态计划/审批文本使用 `textContent`，URL/非白名单字段丢弃；按钮提供 loading/success/error/stale/conflict 可观察状态，重复点击禁用且错误状态可重试。
- `frontend/research-tasks.js`：Research Tab 增加会话计划/审批投影，按 session detail 恢复版本和审批历史，复用同一命令 payload、幂等键和状态映射；旧 Research Task 时间线/报告入口保持兼容。
- `frontend/index.html`：加入会话计划/审批区域，`app.js` 与 `styles.css` 资源版本升至 `v45`，保留旧版本兼容标记。
- `frontend/styles.css`：新增 conversation/Research Tab 计划、审批、命令状态样式，全部使用既有作用域。
- `tests/test_frontend_spec034_task04_contract.py`：先于实现新增计划白名单、统一命令、状态可观察性、Research Tab DOM、XSS/class/version 合同。

## frontend-review P1/P2 修复

- Research Tab 直接消费 task detail 的 `research_session_id`、`session_plan`/`research_plan`/`plan`、`session_approvals`/`approvals`/`approval` 投影；若有 session id 则刷新读取 owner-scoped Session detail，并以新版本重绘卡片。
- 移除旧 `research-approve-button` 与 `/api/research-tasks/{id}/feedback` 批准旁路；Research Tab 审批只走统一 commands payload。
- 未知 approval kind 在会话 renderer fail-closed，既不降级为 plan，也不生成批准按钮。
- stale/conflict 后锁定旧按钮并添加“刷新计划/重新加载会话”入口；刷新成功后以最新 `subject_version` 和全新按钮幂等键重绘。
- 字段接缝修复：审批范围优先消费后端真实 `scope`，兼容旧 `requested_scope_json`；降级策略优先消费 `safe_summary`，兼容旧 `safety_summary`，确保 capability/resource 命令不丢失授权范围且计划卡显示降级摘要。

## 验证

| 命令 | 退出码 | 通过数/结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | 通过 |
| `node --check frontend/research-tasks.js` | 0 | 通过 |
| `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task04_contract.py` | 0 | 8 passed |
| `.venv/bin/python -m pytest -q tests/test_frontend*.py tests/test_frontend_spec034_task04_contract.py` | 0 | 186 passed |
| DOM/XSS/class/version 静态检查 | 0 | 新增 class 全部有 CSS；计划/审批 renderer 无 `innerHTML`；`?v=45` 同步 |
| `git diff --check` | 0 | 通过 |

## 关键决策

- 计划和审批均挂在现有 assistant bubble；不新增聊天消息存储或第二套审批持久化状态。
- 计划只展示 objective、scope（包含/排除/方向）、work_items、capabilities/source、budget、report_structure、safety_summary；字段和对象键均为白名单，动态值经 URL 过滤后走 `textContent`。
- 三类批准均提交固定 `{command, subject_version, scope_json, idempotency_key}`；revise/cancel/decline 同样走统一命令层。后端错误码 `APPROVAL_STALE` / `PLAN_VERSION_STALE` / `APPROVAL_CONFLICT` 映射为可观察且可恢复状态。
- Research Tab 的会话投影优先消费任务 detail 中的 session id；可选 session detail 不可用时保留既有 Task 页面，不伪造计划或审批成功。

## 风险与边界

- 当前前端不实现 AgentRunner、搜索、报告生成或终端审批；真实 Session 列表仍由后续后端/工作台任务提供，Tab 仅在已有 session id 或 detail 投影时展示会话卡。
- 审批成功后的 Task/Activity 创建由后端负责；前端只更新按钮和卡片可见状态，不推断后端副作用。
- 未运行后端 pytest、真实 Ollama 或部署 smoke，符合本轮单端边界；需 reviewer/tester 继续独立验收。

## 产物与日志

- 前端合同：`tests/test_frontend_spec034_task04_contract.py`
- 交接报告：本文件
- 进展日志：`.codebuddy/agent-logs/spec-034/task-04/frontend-dev/20260913-frontend-plan-start.md`、`.codebuddy/agent-logs/spec-034/task-04/frontend-dev/20260913-frontend-contract-red.md`、`.codebuddy/agent-logs/spec-034/task-04/frontend-dev/20260913-frontend-implementation-verify.md`
