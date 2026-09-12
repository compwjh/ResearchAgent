# Spec034 Task02 后端交付报告

状态：后端实现及 backend-review P1 修复完成，待主 Agent 复审/验收。

执行元数据：开始约 2026-09-13（Asia/Shanghai），结束约 2026-09-13（Asia/Shanghai），总耗时约 20 分钟；可用模型为当前执行 Agent 自身；使用工具为 shell/py_compile/pytest/apply_patch，未使用外部网络或子 Agent；token/调用额度由主会话统一统计。

## 本批范围

- 研究库 ResearchStore schema v2：ResearchSession、ResearchIntakeDraft/Field、ApprovalRequest、AgentRun、ResearchArtifact、ResearchNotification，以及活跃 Session、owner+幂等键、Artifact 版本/类型和 Notification owner 事件序列约束。
- 领域模型与状态转移：新增实体 dataclass、稳定状态集合/错误码、Session/Intake/Approval/AgentRun/Notification 非法转移拒绝。
- 会话库 ProcessingStep additive v2：parent/node/detail/source event/session/schema 字段、`(message_id,node_key)` 与非空 `source_event_id` 唯一索引、投影重试标记；旧行不改写并按 v1 根节点读取。
- 统一 `research-event:{research_task_id}:{event_seq}` canonical ID，以及 ResearchStore / MemoryRepository 的最小投影接缝。
- 增加 `/api/research-sessions` 创建请求和 commands 请求的严格基础 Pydantic Schema（不实现 Task03+ 会话业务路由）。
- P1 收口：Session 创建强制复用既有 MemoryRepository 并 fail-closed，且事务内校验传入 Task；未批准 Session 仅允许无 Task/WorkItem 的 Planner Run，已绑定 Session 严格校验 Task/WorkItem/owner/continued Run；Notification 校验 session-task 关系并按完整身份比对幂等请求；ProcessingStep v2 多同 kind 子节点避开 v1 sequence 唯一索引；replay seam 拒绝非 canonical source_event_id，并固定 parent-first 与 retry marker 清除/递增语义。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task02_contract.py` | 0 | 12 passed |
| `.venv/bin/python -m pytest -q tests/test_spec034_task02_contract.py tests/test_memory_repositories.py tests/test_memory_analysis_repair.py tests/test_spec027_backend_research_slice.py tests/test_spec027_runtime_contract.py` | 0 | 146 passed, 5 subtests passed |
| `.venv/bin/python -m py_compile backend/app/api/routes_research.py backend/app/memory/models.py backend/app/memory/repository.py backend/app/research/domain/contracts.py backend/app/research/domain/models.py backend/app/research/domain/state_machine.py backend/app/research/infrastructure/research_store.py tests/test_spec034_task02_contract.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| `.venv/bin/ruff check [8 个改动文件] --output-format concise` | 1 | 14 个既有 MemoryRepository lint 告警（HEAD 基线同样 14 个，集中在原有行）；新增/修改代码无对应告警 |
| `.venv/bin/ruff check --select E701,E702,I001,F401 [8 个改动文件] --output-format concise` | 0 | All checks passed |

说明：按 Task02 要求未运行全量回归；未修改 frontend、论文目录/下载/RAG、模型客户端或 Tool Runtime。

## 决策与风险

- MemoryRepository 的公开 `schema_version` 保持 v7；ProcessingStep v2 作为 v7 上的加性扩展，与项目既有 Task07/Task025 扩展一致，避免破坏既有迁移标记/测试。
- 新研究库迁移为 v2，旧 v1 库仅在同一事务内新增表/索引并升级 metadata，不删除旧任务或旧研究数据。
- 跨 SQLite 的 conversation/task owner 归属仍由上层 API/service 读取 MemoryRepository 后校验；ResearchStore 只执行本库 owner 过滤，未声称跨库原子事务。
- Projector 失败记录 `TRACE_PROJECTION_FAILED` 与待重放标记；研究事件本身不回滚。三层树校验拒绝孤儿、跨消息父节点、循环和第四级。
- replay seam 接受已持久化事件列表，统一验证 `source_event_id == research-event:{research_task_id}:{event_seq}`，拒绝跨 Task/custom ID，按 parent-first 后 event_seq 排序；ResearchStore/MemoryRepository 投影成功把 retry 标记置为非 pending，失败按 source_event_id 累加 attempts。完整跨库 projector 编排继续留给 Task07。
- 本批未修复既有 MemoryRepository 的 14 个 Ruff 风格告警，避免把 Task02 P1 修复扩大为无关重构；基线对比已确认告警在 HEAD 即存在。

## 主 Agent 后续动作

1. 检查 ResearchStore 新增 CRUD 命名与后续 Task03/04 service 的接口适配。
2. 运行 backend reviewer / tester 的独立门禁；确认后更新 Task02/Spec034 状态台账及最终验收材料。
3. Task07 接入时复用 `MemoryRepository.project_research_event_step`，不要另建 ProcessingStep 表或第二个 projector。
