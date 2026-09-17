# Spec031 Task04 后端交接报告

## 固定字段

- 结果状态摘要：**P1 修复完成（定向验证通过；待 reviewer 复审）**。复用既有 `ResourceProbe`、`ResearchScheduler`、`ResearchStore.resource_reservations` 与 `ModelRouter`，并将 strong 单并发下沉到 ResearchStore 单事务 conditional insert；过期恢复按 durable rows 释放 probe/global quota；grant 按 reservation ids + task ownership + grant token 隔离释放；策略激活改为服务端生成、绑定质量 outcome 与 ResourceProbe snapshot 的 evidence handle。最终质量门还强制取服务端默认阈值与持久化 policy threshold 的 max，调用方低阈值不能降门槛。未启动第二 Ollama、未下载/卸载模型、未跨机器调度。
- 改动范围：仅 `backend/**` 与 `tests/test_spec031_adaptive.py`；未修改 frontend；未运行全量 pytest；未 commit/push。
- 开始/结束/总耗时：2026-09-17 约 15:00 CST – 15:45 CST；约 45 分钟（含 P1 修复）。
- 模型/工具统计：当前 Agent（Luna high 临时执行）；本轮新增 `apply_patch` 约 22 次、`exec_command` 约 13 次、`write_stdin` 约 4 次；未调用网络，未启动/修改 Ollama。

## 改动文件

- `backend/app/platform/ollama.py`
  - 修正 `_GlobalWorkerScheduler` 重复领用绕过 per-task cap 的问题；保留 cap=1/2/4 的全局上限与任务公平分配语义。
- `backend/app/research/application/scheduler.py`
  - 新增不可变 `WorkerGrant` 与 `grant_workers()`；强/27B tier 强制单并发。
  - grant 前执行探针、锁内只做有界内存状态更新；reservation 部分失败时释放已建 reservation 与 probe quota；兼容旧 `acquire_resources() -> (granted, reason)`。
  - `WorkerGrant` 带 grant-specific reservation ids/ownership token；`release_grant()` 仅释放自身 grant，重复释放幂等；`recover()` 按 durable expired rows/count 释放 probe/global quota，支持同 task 多 grant 与重启恢复。
- `backend/app/research/application/adaptive_routing.py`
  - 新增 `AdaptiveRoutingService`（及描述性别名）：先调用旧 `ModelRouter` 再申请 Worker，外部模型调用通过 `execute()` 在 grant 生命周期外执行；记录脱敏的 `worker_grant/resource_reason/policy_version`。
  - 不创建第二模型客户端、第二调度器或第二资源探针；资源不可用时保留旧模型选择并采用单 Worker grant。
- `backend/app/research/application/model_router.py`
  - 增加显式 `resolve_adaptive()` 接缝，旧 `resolve/execute` 签名和生产选择语义保持兼容。
- `backend/app/research/application/routing_observation.py`
  - 增加 `PolicyActivationError`、服务端 `issue_activation_evidence()` 和 `activate_policy()`；evidence 绑定持久化 outcome 的样本/schema/quality 与 ResourceProbe snapshot，拒绝 `True`、`{"passed":true}` 或调用方自报 metrics；服务端默认 quality 0.8 / schema 1.0 / samples 1 与 policy thresholds 取 max；Task03 的 draft/shadow 写入限制保持不变。
- `backend/app/research/infrastructure/research_store.py`
  - 增加 `activate_routing_policy()` 单事务状态迁移：旧 active 原子退役、目标 draft/shadow 原子变为 active；任一冲突回滚。
  - `resource_reservations` 增加 grant token；strong tier 在同一 `BEGIN IMMEDIATE` 内清理过期行、检查 active strong、conditional insert，跨 scheduler 实例只允许一个。
  - 增加 gate evidence 表、质量汇总、过期 reservation rows 和带 task/token ownership 的释放接口。
- `backend/app/api/routes_research_routing.py`、`backend/app/api/routes.py`
  - 增加最小 `POST /api/research-routing/policies/{version}/evidence`（服务端生成证据）与 `POST /api/research-routing/policies/{version}/activate` 控制面，不接前端；错误返回稳定 code，激活 API 不接受 gate true/metrics。
- `tests/test_spec031_adaptive.py`
  - 覆盖 1/2/4 worker cap 与公平性、Fake probe/模型状态、探针失败、strong 单并发、reservation 回滚、过期恢复、脱敏 grant 观测、策略 gate/原子切换和旧 ModelRouter 兼容。

## 测试命令 / 退出码 / 结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest --noconftest -q tests/test_spec031_adaptive.py tests/test_spec031_shadow_observation.py tests/test_spec028_scheduler_lease_recovery.py tests/test_spec027_runtime_contract.py tests/test_spec028_runtime_contract.py tests/test_spec027_backend_research_slice.py tests/test_spec028_hitl.py tests/test_spec028_recovery_api_ui.py tests/test_spec028_scheduler_status.py tests/test_spec034_task07_backend.py` | 0 | **154 passed，5 subtests passed，3.67s**；含跨 scheduler strong race、过期 quota recovery、same-task grant isolation、伪造 gate rejection、恶意低阈值/低质量拒绝 |
| `.venv/bin/python -m py_compile backend/app/platform/ollama.py backend/app/research/application/model_router.py backend/app/research/application/routing_observation.py backend/app/research/application/scheduler.py backend/app/research/application/adaptive_routing.py backend/app/research/infrastructure/research_store.py backend/app/api/routes.py backend/app/api/routes_research_routing.py tests/test_spec031_adaptive.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

附加 API/SPA 集合在 16 个测试通过后因线程长时间无输出手动中断；该集合不属于 Task04 定向验收，未将中断误报为通过。未运行全量 pytest。

## 决策依据

- Task02 明确多实例 NO-GO、当前机器 ResourceProbe cap=1；实现不硬编码放大 cap，继续由既有 probe 的 footprint/20% margin 裁决，探针或 footprint 不可用时沿用 `RESOURCE_PROBE_FAILED` 单 Worker。
- 9B/fast 使用既有全局调度额度和 per-task cap；27B/strong 在 ResearchStore 的 durable reservation 单事务层加 conditional singleton，避免跨 scheduler/注入 Fake probe 绕过质量档位约束。
- 不把外部 provider/model 调用放进 `_GlobalWorkerScheduler` 锁；`AdaptiveRoutingService` 先解析旧 Router，再 grant，`execute()` finally 释放。
- Task03 shadow/draft policy 仍不能通过普通保存接口写成 active；Task04 仅在 manual confirmation + server-issued evidence handle 通过 outcome/schema/ResourceProbe snapshot 校验后调用 ResearchStore 的单事务激活接缝。
- 质量阈值以 `max(SERVER_MIN_QUALITY_SCORE, policy.thresholds.min_quality_score, caller_requested_threshold)` 计算；activate 会再次读取 policy/evidence 并复验，不能使用低质量 evidence 或恶意低阈值绕过。
- 观测只写 bounded、脱敏标量（grant/reason/policy_version），不写 prompt、回答、思维链、owner token 或模型响应。

## 风险 / 阻塞

- Task02 benchmark 的质量/provenance P1 缺口仍属于 Task06 收口项，本 Task 未伪造补齐。
- `AdaptiveRoutingService` 是显式应用接缝；现有 AgentRuntime 的旧 `ModelRouter.resolve` 主路径仍保持兼容，主 Agent 需要决定后续是否在 runtime 任务生命周期中接入该接缝并补充端到端 smoke。
- 原附加 API/SPA 集合此前曾出现长时间无输出并被手动中断；本轮只运行 Task04+Task03/Spec027/028 指定集合，未将附加集合误报为通过。

## 主 Agent 后续动作

1. 重新运行 backend reviewer / backend tester，重点复核四个 P1 的证据与并发边界。
2. 若接受 `AdaptiveRoutingService` 作为 production 接缝，在 Task06 补 runtime smoke、API 权限边界与全量回归。
3. 按项目流程由主 Agent 在最终验收阶段更新 spec 状态、部署并做运行时验证；本 Task 未提交、未推送。

## 进展日志

- `.codebuddy/agent-logs/spec-031/task-04/backend-dev/20260917T000001Z.md`
- `.codebuddy/agent-logs/spec-031/task-04/backend-dev/20260917T000002Z.md`
- `.codebuddy/agent-logs/spec-031/task-04/backend-dev/20260917T000003Z.md`
- `.codebuddy/agent-logs/spec-031/task-04/backend-dev/20260917T000004Z.md`
- `.codebuddy/agent-logs/spec-031/task-04/backend-dev/20260917T001001Z.md`
- `.codebuddy/agent-logs/spec-031/task-04/backend-dev/20260917T001002Z.md`
- `.codebuddy/agent-logs/spec-031/task-04/backend-dev/20260917T001003Z.md`
- `.codebuddy/agent-logs/spec-031/task-04/backend-dev/20260917T001004Z.md`
- `.codebuddy/agent-logs/spec-031/task-04/backend-dev/20260917T002001Z.md`
- `.codebuddy/agent-logs/spec-031/task-04/backend-dev/20260917T002002Z.md`
- `.codebuddy/agent-logs/spec-031/task-04/backend-dev/20260917T002003Z.md`
