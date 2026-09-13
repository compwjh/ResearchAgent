# Spec034 Task07 后端交付报告

状态：后端 Task07 reviewer P1 修复完成，待主 Agent 复审与跨端验收。

本轮 reviewer 修复：已将 projector 接入 Orchestrator/ResearchService/SSE；补齐 activity assistant、task/session/conversation/owner 绑定；冻结 Phase→Agent→Skill/Tool 校验；ResearchStore replay 改为整批预校验并支持分页到 `last_event_seq`；统一异常 retry marker 与 detail_json 安全边界。原始 ResearchEvent SSE 帧仍保留，新增 upsert 帧不改变旧客户端游标语义。

## 结果状态和摘要

已在既有 `MemoryRepository` / `ResearchStore` seam 上完成 ProcessingStep v2：

- additive 迁移保留 v1 行，新增树字段、节点/事件唯一索引和投影 retry marker；旧行读取为 v1 根节点。
- 父节点同 message 校验、父先存在、不可重父、循环/孤儿/超过三级拒绝；普通聊天既有一至二级调用保持兼容。
- 新增 `ProcessingStepProjector`，从持久化 `ResearchEvent` 通过 ResearchStore parent-first replay 投影到会话库；canonical `research-event:{task}:{seq}` 幂等，同 node_key 更新，终态迟到 running/terminal 事件不会覆盖终态。
- 失败保留 ResearchEvent 并写 `TRACE_PROJECTION_FAILED` 待重放标记；成功 replay 清除 marker；detail_json 仅保存受限安全展示字段。
- REST `GET /messages/{id}/processing-steps` 返回扁平邻接表 v2 字段；projector 提供增量 upsert SSE envelope。
- `ResearchService`/`Orchestrator` 已装配 projector：真实后台事件在 ResearchEvent 落库后尝试投影到绑定的 activity assistant message；研究 SSE 保留原始事件帧并追加 `processing_step/upsert` 帧。
- Projector 强制 task/conversation/activity/session/owner 绑定，研究树严格为 Phase → Agent → Skill/Tool；ResearchStore replay 先整批预校验，分页重放直至 `last_event_seq`，非法四级不会落前三层。
- 在唯一 `ResearchAgentRunner` seam 发出 Skill 激活、Tool 调用开始/完成/失败事件；node key 与父 source 身份稳定，ToolResult 仅保留状态、长度、hash、result id 和安全摘要。
- ResearchStore.append_event 做稳定字段白名单与敏感内容/URL过滤；两侧 retry marker 的 `last_error` 统一为 `TRACE_PROJECTION_FAILED`。SSE 先投影再发送 legacy raw event，upsert/失败 retry 帧不重复占用 event id，失败仅发送 `trace_syncing` 稳定码；增加单次有界 retry drain。
- 摘要字符串也递归遮蔽 Authorization/Bearer、token、secret、password、cookie 和 URL；ResearchService 启动、后台编排入口、SSE 建立时各执行一次有界幂等 drain，空闲/重启后无需新事件即可恢复 pending marker。
- strict replay 回溯父链验证每个父节点类型；projector 仅在显式绑定 research session 时启用 strict，旧未绑定 model 事件沿宽松兼容路径读取。

## 改动文件

- `backend/app/memory/models.py`
- `backend/app/memory/repository.py`
- `backend/app/research/application/processing_projector.py`
- `backend/app/research/application/entry.py`
- `backend/app/research/infrastructure/research_store.py`
- `backend/app/api/routes_conversations.py`
- `backend/app/api/routes_research.py`
- `backend/app/research/application/research_service.py`
- `backend/app/research/application/orchestrator.py`
- `backend/app/research/application/agent_runtime.py`
- `tests/test_spec034_task07_backend.py`

## 测试命令 / 退出码 / 结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task07_backend.py tests/test_spec034_task02_contract.py tests/test_memory_repositories.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_spec034_task05_contract.py` | 0 | 100 passed |
| `.venv/bin/python -m pytest -q tests/test_spec034_task06_contract.py` | 0 | 12 passed（受影响邻接回归） |
| `.venv/bin/python -m pytest -q tests/test_conversations_api.py` | 0 | 16 passed（REST 兼容回归） |
| `.venv/bin/python -m pytest -q tests/test_spec034_task07_backend.py tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_spec034_task05_contract.py tests/test_spec034_task06_contract.py tests/test_spec027_backend_research_slice.py tests/test_conversations_api.py` | 0 | 162 passed, 5 subtests passed |
| `.venv/bin/python -m py_compile backend/app/api/routes_research.py backend/app/memory/repository.py backend/app/research/application/agent_runtime.py backend/app/research/application/entry.py backend/app/research/application/orchestrator.py backend/app/research/application/processing_projector.py backend/app/research/application/research_service.py backend/app/research/infrastructure/research_store.py tests/test_spec034_task07_backend.py` | 0 | 通过 |
| `.venv/bin/python -m py_compile backend/app/api/routes_conversations.py backend/app/memory/models.py backend/app/memory/repository.py backend/app/research/application/entry.py backend/app/research/application/processing_projector.py backend/app/research/infrastructure/research_store.py tests/test_spec034_task07_backend.py` | 0 | 通过 |
| `.venv/bin/ruff check [Task07 改动文件] --select E9,F63,F7,F82,I001 --output-format concise` | 0 | All checks passed |
| `git diff --check` | 0 | 通过 |

## 产物路径

- 本报告：`docs/sdd/plans/034/artifacts/task-07/backend-report.md`
- 进展日志：`.codebuddy/agent-logs/spec-034/task-07/backend-dev/20260913-111449.md`

## 决策依据

- 不新增 ProcessingStep 表、事件表或替代仓储；ResearchEvent 仍由 ResearchStore 持久化，ProcessingStep 仍由 MemoryRepository 写入。
- ProcessingStep v2 不提升公开 memory schema version，沿用项目 additive extension 约定，避免破坏历史迁移标记消费者。
- 节点父链写入后不可静默移动；同 node_key 的生命周期事件可更新 running 节点，但任何终态节点均为屏障。
- 跨库不存在 SQLite 原子事务；研究事实先保留，投影失败只记录 retry marker 并可从 ResearchStore 重放。

## 风险与阻塞

- 未做跨设备树展开状态同步（Spec 明确不做）。
- 真实 Ollama/外部来源端到端运行不属于本 Task，需由集成验收验证；后台事件投影与原始事件 SSE 已接线。
- 线上真实来源/Ollama 不属于本 Task，未声称已验证。

## 主 Agent 后续动作

1. 运行 backend reviewer，重点复核 parent-first replay、retry marker 跨库语义和终态屏障。
2. 与前端 Task07 对接 `ProcessingStepProjector.as_sse_upsert()` / REST 字段契约并做 SSE 重连 smoke。
3. 完成跨端 smoke 后再更新 Spec034/Task07 状态台账；本 Agent 未 commit、push、merge、reset、stash 或 clean。

## 执行元数据

- 开始：2026-09-13 11:14（Asia/Shanghai）
- 结束：2026-09-13 12:43（Asia/Shanghai）
- 总耗时：约 89 分钟（含最终 reviewer P1 修复与回归）
- 可用模型：当前执行 Agent 自身；主 Agent 指定临时 Luna high
- token 统计：子任务上下文未提供可查询 token 计数
- 工具统计：`apply_patch` 62 次，`exec_command` 59 次，`write_stdin` 24 次；未使用网络或子 Agent
