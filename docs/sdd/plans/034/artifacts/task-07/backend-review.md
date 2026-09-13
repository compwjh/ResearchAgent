# Spec034 Task07 后端最终复审报告

评审角色：backend-reviewer（只读）  
复审时间：2026-09-13（Asia/Shanghai）  
范围：Task07 最新父节点类型修复及 Task02–06、Spec027、conversations 受影响后端契约。未修改业务代码，未 commit。

## 结论

**GO。** 上一轮唯一 P1（strict 模式未回溯已有父节点 `node_type`）已修复；legacy v1 默认宽松路径仍可读，绑定 research strict 路径拒绝 `operation` 根下的 Agent。P0/P1：无。P2：无新的收口阻塞，仅保留非阻塞测试/观测增强建议。

## 本轮重点复核

### Strict 父节点类型回溯：通过

`MemoryRepository._validate_processing_parent()` 现在查询并保存父链每一行的 `node_type`，strict 模式按 immediate-parent-first 反查整条链：根必须 `phase`、二级父必须 `agent`、三级父必须 `skill/tool`，同时验证当前新边类型（`backend/app/memory/repository.py:2782-2815`）。

- 最小行为测试：legacy `operation` root → strict `agent` child 被拒绝；strict `phase → agent → tool` 成功。
- Task07 合同覆盖该回归（`tests/test_spec034_task07_backend.py:65-76`），通过 `2 passed`。
- 未绑定旧 v1/普通聊天调用不传 `strict_tree`，仍保留原有 operation/扁平兼容。

### 旧 model 单/批兼容：通过

`ProcessingStepProjector.project_events()` 仅在显式 `research_session_id` 时开启 strict；unbound legacy `model` 单事件与批量均走宽松路径并映射为 skill（`backend/app/research/application/processing_projector.py:251-269`；`tests/test_spec034_task07_backend.py:199-207`）。

### 之前 P1 的持续验证

- Runner 在唯一执行 seam 产生 `Phase → Agent → Skill/Tool` ResearchEvent，父 `node_key` 与 canonical `parent_source_event_id` 稳定（`agent_runtime.py:592-607,967-1174`；`orchestrator.py:485-507`）。
- ResearchEvent 落库使用递归 key/value/URL 安全过滤；嵌套 `summary` 中的 Authorization/token/URL 均被 `[REDACTED]` 替换（`research_store.py:103-137,2592-2618`）。
- SSE 先投影再发送，异常只发无 cursor 的稳定 `TRACE_PROJECTION_FAILED`/`trace_syncing` 帧（`routes_research.py:579-621`）；retry `last_error` 固定稳定码（`research_store.py:2644-2660`；`memory/repository.py:2940-2957`）。
- Projector/ResearchStore replay 按 `after_seq` 分页至 `last_event_seq`；1001 事件完整重放。启动、后台 orchestration、SSE reconnect 均执行 bounded retry drain（`research_service.py:203-210,260-278,435-440`；`routes_research.py:579-584`）。

## 兼容性与边界

- migration 仍 additive；旧 processing row 保留 `schema_version=1`/`node_type=operation` 读取语义，新增 strict 只作用于绑定 research tree。
- `source_event_id` canonical、`node_key` 幂等、父身份冲突/循环/孤儿/深度、四级整批预校验、终态屏障、task/conversation/session/activity/owner 归属均保持。
- REST flat 邻接表、SSE upsert、现有 conversations 消息接口没有替换旧字段或创建第二套 event/step 存储。
- 未以 Fake Runner 或本地探针冒充真实 Ollama/外部来源 smoke；真实端到端仍由跨端验收负责。

## P2（非阻塞建议）

- `_runtime_event()` 的 ResearchEvent append 异常仍 best-effort 静默；可在后续观测增强中补稳定计数/补偿告警，但不改变当前状态机。
- 建议补客户端级 SSE 断线测试，验证 raw 已送达而 upsert 丢失时可由 REST flat 邻接表重建；当前服务端 cursor/upsert 契约已通过静态检查。
- `list_projection_retries()` 低层接口继续由 Service 的 owner/session 校验包住，后续若扩展诊断 API 应避免直接暴露跨 owner marker。

## 验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task07_backend.py::test_processing_tree_rejects_cross_message_or_cycle_and_allows_three_levels tests/test_spec034_task07_backend.py::test_unbound_legacy_model_event_uses_broad_replay_path` | 0 | **2 passed** |
| `.venv/bin/python -m pytest -q tests/test_spec034_task07_backend.py tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_spec034_task05_contract.py tests/test_spec034_task06_contract.py tests/test_spec027_backend_research_slice.py tests/test_spec027_runtime_contract.py tests/test_conversations_api.py tests/test_memory_repositories.py` | 0 | **227 passed, 5 subtests passed** |
| `.venv/bin/python -m py_compile`（Task07 改动后端文件及 Task07 测试） | 0 | 通过 |
| `.venv/bin/ruff check`（Task07 改动文件，`E9,F63,F7,F82,I001`） | 0 | All checks passed |
| `git diff --check` | 0 | 通过 |

## 后续动作

Task07 后端评审通过，可进入前端/跨端 SSE smoke 与 Spec034 收口；继续保留上述 P2 观测增强，不作为当前 GO 的阻塞项。
