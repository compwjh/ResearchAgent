# Spec034 Task10 后端最终评审

评审角色：backend-reviewer（Luna high）  
评审时间：2026-09-15（Asia/Shanghai）  
评审范围：当前候选 `backend/**`、Task02–09 后端交付/评审交接物及受影响后端合同测试；未修改业务代码，未 commit/push，未运行全量回归或真实 Ollama Smoke。

## 最终结论

**NO-GO。** 当前候选的 Task02–09 后端定向合同和静态检查通过，但会话式主链仍有一个核心运行阻断：`approve_plan` 只把 Session/Task 留在排队状态，没有启动 Orchestrator/ResearchService，因此真实子 Agent、目录 Tool、报告和三级运行树不会执行。另有命令幂等重放在计划版本变化后错误返回 stale，以及已交付的 cleanup CLI 无法提供跨库快照、始终 fail-closed 的问题。

P0：0。  
P1：3 项。  
P2：2 项。

## P1 阻断项

### P1-01：批准计划后没有启动真实研究运行

`PlanApprovalService._resume_activity()`（`backend/app/research/application/approval_service.py:235-274`）只创建/复用 activity message、将 outbox 标为 completed、更新 Session 为 `queued`，没有调用 `ResearchService.start()`、`Orchestrator.run()`，也没有 outbox worker 消费 `research_activity_outbox`。当前代码库中 `ResearchService.start()` 只从旧 `create_task()`/旧 `feedback()` 路径调用；`POST /api/research-sessions/{id}/commands` 仅调用 `PlanApprovalService.command()`（`backend/app/api/routes_research.py:805-818`）。

独立探针结果：

```text
session_status queued
task_status planning
work_items [(s1, queued), (s2, queued), (e1, queued)]
```

因此批准后的新 Session 不会进入 `running`，不会创建/执行 AgentRun，必然无法完成 Spec034 要求的真实 Planner/Search Worker/Evaluator/Critic/Synthesizer、ProcessingStep 三级树和报告交付 Smoke。这是核心验收阻断，必须先补受控启动接缝（推荐由批准 Saga 后调用 owner-scoped service dispatcher，或实现带 claim/idempotency 的 outbox worker），并补批准后最终状态/AgentRun 产生的后端行为测试。

### P1-02：命令幂等重放在计划版本变化后违反“返回原响应”

`PlanApprovalService.command()` 在 `backend/app/research/application/approval_service.py:145-152` 先比较当前 `session.current_plan_version`，再读取 `research_command_results`。若版本 1 的命令已成功落盘，随后 `revise_plan` 生成版本 2，再用同一个幂等 key 重放版本 1 命令，会先返回 `PLAN_VERSION_STALE`，而不是已持久化的原响应。

独立探针复现：

```text
first_status rejected revised_version 2
replay_error PLAN_VERSION_STALE 计划版本已更新，请刷新计划卡
```

应先按 owner + idempotency key 读取并校验命令身份，身份一致时直接返回原响应；只有未找到记录的新命令才校验当前 `subject_version`。

### P1-03：交付的 legacy cleanup CLI 无法完成跨库安全删除

`backend/scripts/cleanup_legacy_research_tasks.py:31-34` 调用 `execute_legacy_cleanup()` 时没有注入 `external_snapshot`。而 `ResearchStore._cross_store_snapshot(None)` 按设计返回 `status=unverified`，`execute_legacy_cleanup()` 会在删除前返回 `LEGACY_CLEANUP_CROSS_STORE_UNVERIFIED`。因此即使操作者提供了有效 `--dry-run-id --execute --confirm`，随附 CLI 也无法完成任何清理；Task09 测试中的成功路径依赖测试注入的跨库 snapshot provider，并不等于交付脚本可用。

应为维护入口接入只读、owner-scoped 的 sessions/catalog/kb 计数或内容 digest provider，并保留当前 fail-closed 与事务回滚语义；禁止通过删除跨库校验来“修复”该问题。

## P2 非阻断问题

### P2-01：研究错误响应未完全遵守统一错误体

Spec034 要求 `{error:{code,message,retryable,subject_version}, data:...}`。当前 `routes_research.py:247-256` 的 `_error()`/`_api_error()` 只返回 `code/message`，`_command_error()`（约 `:420-426`）只补 `retryable`，均缺少 `subject_version` 和 `data`。独立探针输出：

```text
api 409 {"error":{"code":"APPROVAL_STALE","message":"stale"}}
service 503 {"error":{"code":"SOURCE_UNAVAILABLE","message":"unavailable"}}
command 409 {"error":{"code":"APPROVAL_STALE","message":"stale","retryable":false}}
```

建议统一由一个安全序列化器生成 HTTP/SSE 错误体，并按当前 Session 版本填充 `subject_version`。

### P2-02：Store 层未校验 trigger message 必须是 user 消息

`validate_session_external_references()`（`backend/app/research/infrastructure/research_store.py:162-176`）校验了 conversation/message 的 owner 和 conversation 归属，但没有校验 `message.role == "user"`。HTTP 表单路径有额外检查，然而直接使用 ResearchStore/Coordinator 的调用仍可把 assistant 消息作为 `trigger_message_id` 持久化，偏离数据模型约束。建议在跨库接缝统一拒绝非 user trigger，并补负向合同测试。

## 已通过的核对项

- Task02–Task09 后端受影响合同测试：`124 passed in 4.11s`。
- 所有当前候选变更后端文件 `py_compile`：退出码 0。
- 聚焦 Ruff `E9,F63,F7,F82,I001`：退出码 0，All checks passed。
- `git diff --check -- backend tests`：退出码 0。
- Task09 的项目继承/显式 project mismatch、创建竞争幂等、Session cursor、dry-run 前置门禁、跨库不一致/未验证回滚和 aborted 审计在定向合同中保持通过。
- Artifact 下载按 owner→task→artifact 关联授权，不解析任意 `storage_ref`；inline 仅允许 HTML；运行事件/ToolResult/计划输出有字段白名单及敏感信息过滤。

## 评审范围外/未执行

- 未提前运行全量 pytest；需待 P1 修复后由 Task10 主 Agent 执行一次最终全量回归。
- 未声称真实 Ollama、真实 USENIX 目录 Tool、浏览器审批或部署成功；P1-01 已证明当前后端批准路径无法到达该 Smoke。

进展日志：`.codebuddy/agent-logs/spec-034/task-10/backend-reviewer/20260915-013540.md`。
