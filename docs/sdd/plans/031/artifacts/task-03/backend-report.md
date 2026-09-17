# Spec031 Task03 后端交接报告

## 固定字段

- 结果状态和摘要：**P1 修复完成（待复审；单实例、ResourceProbe 受限的值级脱敏观测与 shadow replay）**。实现了路由决策、模型结果、资源快照和版本化 shadow policy 的独立 SQLite 持久化；shadow 只计算候选模型，不改变生产 `chosen_model`，不提供 policy 激活入口。
- 改动范围：仅后端 Research/观测接缝、必要 SQLite 加性表迁移和 Task03 定向测试；未修改 frontend、Ollama listener/部署或 Spec027/028 的既有选择/调度语义。
- 开始/结束/总耗时：2026-09-17 14:30 CST – 15:12 CST；约 42 分钟。
- 模型/工具统计：当前 Agent（Luna high 临时决策）；`apply_patch` 8 次、`exec_command` 10 次；未调用网络、未启动/修改 Ollama、未使用全量 pytest。

## 改动文件

- `backend/app/research/application/routing_observation.py`
  - 新增有界、脱敏的 `RoutingDecision`、`ModelOutcome`、`ResourceObservation`、`ShadowReplay` 与 `RoutingObservationService`；共享值级检查覆盖大小写、下划线/连字符拼接及 JSON/键值表达式。
  - 决策公开字段严格为 `task_type/features/candidate_models/chosen_model/reason/policy_version`；结果严格为 `schema_valid/quality_score/ttft/duration/tokens/error_code`。
  - features、候选模型、规则和文本均有数量/长度边界；拒绝 prompt/回答/思维链/凭据形态字段。
  - ResourceProbe 异常或无有效 footprint 时持久化显式 `RESOURCE_PROBE_FAILED` 快照；不伪造内存/模型数据。
  - policy 只接受 `draft/shadow/retired`，`active` 明确拒绝；回放输出原生产选择和 shadow 候选，不回写决策。
- `backend/app/research/infrastructure/research_store.py`
  - 增加幂等、owner 隔离的 `research_routing_decisions`、`research_model_outcomes`、`research_resource_snapshots`、`research_routing_policies` 表及索引。
  - 保存/读取/列表接口均按 owner 过滤；重复 decision/outcome/snapshot 返回既有记录，冲突拒绝。
- `backend/app/research/application/model_router.py`
  - 增加可选只写观测 sink；默认行为不变，实际模型仍由原有 `_pick_model` 决定。
- `backend/app/research/application/agent_runtime.py`
  - 仅在 router 显式安装观测 sink 时传递 owner 和有限特征；FakeModelRouter 等旧签名保持兼容。
- `backend/app/platform/observability/spans.py`、`__init__.py`
  - 增加 `record_routing_observation` allowlist 接缝；与 routing service 复用值级敏感内容校验，配置/客户端/上报异常由 `safe_call` 静默降级，不阻塞业务。
- `backend/app/research/application/entry.py`
  - 生产 `build_research_service()` 通过现有 `ResearchStore` opt-in 装配 `RoutingObservationService` 和 Langfuse routing seam；装配失败回退无观测 `ModelRouter`，不改变路由选择或兼容签名。
- `tests/test_spec031_shadow_observation.py`
  - 覆盖 SQLite 原始值级敏感内容拒绝、store 直达边界、policy/Langfuse metadata 脱敏、生产 entry 装配、脱敏/幂等、owner 隔离、结果 allowlist、探针失败、shadow 不改生产选择和 router 只写观测。

## 测试命令 / 退出码 / 结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest --noconftest -q tests/test_spec031_shadow_observation.py` | 0 | 16 passed |
| `.venv/bin/python -m pytest --noconftest -q tests/test_spec031_shadow_observation.py tests/test_spec027_runtime_contract.py tests/test_spec027_backend_research_slice.py` | 0 | 111 passed，5 subtests passed |
| `python -m py_compile backend/app/platform/observability/__init__.py backend/app/platform/observability/spans.py backend/app/research/application/routing_observation.py backend/app/research/application/model_router.py backend/app/research/application/agent_runtime.py backend/app/research/application/entry.py backend/app/research/infrastructure/research_store.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 决策依据

- Task02 审查仅放行单实例、ResourceProbe cap=1 的动态观测和 shadow policy；本实现没有提高并发、启动第二实例或激活策略。
- `ResourceProbe` 的失败语义保持 `RESOURCE_PROBE_FAILED` 和单 Worker fallback；快照失败记录显式错误，不使用猜测值。
- 既有 `ModelRouter` 继续负责生产模型选择；观测 sink 是 opt-in、异常隔离的旁路。

## 风险与阻塞

- Task02 的固定 JSON 质量校验、环境 provenance 等 P1 缺口仍属于 Task06 收口项，本 Task 没有伪造或补写 benchmark 证据。
- 资源快照复用既有 `ResourceProbe.snapshot()` 可提供的 footprint/count；真实模型名仍由既有 Ollama `/api/ps` 接缝负责，未新增客户端。
- 生产 entry 的 outcome 自动记录仍未接通：当前安全调用范围内没有稳定的模型执行成功/失败出口可传入 `RoutingObservationService.record_outcome()`，强行接入会改变 Task02/Spec027 运行时契约；按评审要求留给 Task06，并在本报告明确记录，不伪造已接通。
- 未运行全量 pytest，未执行运行时部署；由主 Agent 在 Task03 汇总后按项目流程继续评审/验收。

## 主 Agent 后续动作

1. 复核本报告和 `git diff`，将 Task03 代码与测试纳入同一分支提交。
2. 运行后端评审和 Task03 定向验收；确认 owner 隔离、敏感字段扫描及 SQLite 加性迁移。
3. Task06 补齐 Task02 质量/provenance 合同，完成全量回归、部署和运行时验证后再更新 Spec031 收口状态。
