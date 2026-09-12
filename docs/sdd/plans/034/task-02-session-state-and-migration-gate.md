# Task02 — 数据模型、状态机、迁移与兼容门禁

> 关联：[Spec034](../../specs/034-conversational-deep-research-agent-runtime.md) ｜ 索引：[README](./README.md)
> 依赖：Spec确认、需求/技术评审通过；当前状态：`已完成`

## 一句话目标

先冻结 ResearchSession、Intake、Approval、AgentRun、Artifact、Notification、ProcessingStep v2 的 Schema、状态机和跨库幂等接缝，以自动合同测试阻止后续切片各自发明数据结构。

## 背景与前置条件

- 必读 Spec034 的数据模型、状态机、存储与删除章节。
- 复用 Spec027 的研究库和 MemoryRepository 迁移范式；不得复制论文目录或模型客户端。
- 读取当前研究库 schema、memory schema v7、ResearchTask store 和会话消息接口的最小相关文件。

## 数据、配置与接口

- 冻结新增表、索引、状态枚举、稳定错误码、owner/外部 ID 校验和迁移顺序。
- 冻结 v1→v2 processing step 兼容合同与 `/research-sessions`、统一 commands 的基础 Schema。
- 冻结跨库 Saga 幂等键、补偿策略和启动 interrupted 审计。
- 冻结 ResearchSession/Intake/Approval/AgentRun/Artifact/Notification 的状态转移矩阵、命令 CAS/幂等和 active Session 唯一性。
- Artifact 与 Notification 为两张独立表，分别冻结 `(research_task_id, report_version, artifact_type)`、`(owner_id, idempotency_key)` 唯一索引及保留/删除规则。
- Approval/Notification 均沿用 owner 隔离；Notification 额外冻结 `(owner_id,event_seq)` 唯一索引与 `unread/read`、`read_at` 一致性。
- AgentRun 必须保存 `research_session_id`；计划批准前 Planner Run 允许暂不绑定 Task/WorkItem，批准后的执行 Run 必须绑定二者，Coordinator 不进入 AgentRun role 枚举。
- ProcessingStep v2 只做 additive migration，冻结 `(message_id,node_key)`、`source_event_id`、v1 映射和 `research-event:{task}:{seq}` 规范 ID。

## 实施步骤与文件边界

1. 先写合同测试和迁移设计文档，不实现业务编排；状态机逐项覆盖 Spec034 合法/非法转移。
2. 后端开发只改 `backend/**` 与后端测试；ProcessingStep 数据迁移也归后端。
3. 验证旧库重复启动迁移幂等、旧 processing_steps 可读、跨 owner 引用拒绝、父链/三级校验和 projector 重放标记。
4. 旧未绑定 Task 的实际删除留给 Task09，本任务只冻结选择条件和不可波及断言。

## 子代理分派

- `backend-dev`：复杂任务；每次最多一个实现文件，最小上下文为本任务、当前 schema/store。
- `backend-reviewer`：检查事务、外键 RESTRICT、幂等、状态转移和数据删除边界。
- `backend-tester`：只跑相关迁移、store、API 合同测试。
- 研发子代理模型按 Spec 执行配置解析；本轮临时模型选择不得落盘为长期规则。

## 边界与明确不做

- 不实现完整 UI、Agent 模型循环、论文搜索或报告。
- 不建立跨 SQLite 外键或伪原子事务。
- 不删除已绑定 Task、会话、目录或知识库。

## 验收、风险与回滚

- 新库、旧库、重复迁移、失败回滚和并发幂等测试通过。
- 状态机非法转移均返回稳定错误；Session 状态不可由前端直接写。
- 每条命令按 `subject_version + idempotency_key` CAS；重复返回原响应，竞争返回 `APPROVAL_CONFLICT`/`APPROVAL_STALE`。
- v2 迁移不重写旧行；同一 `source_event_id/node_key` 重放只更新一个节点，投影失败不回滚研究事件。
- Replay seam 只接受 canonical `research-event:{research_task_id}:{event_seq}`，拒绝跨 Task/custom ID，并按 parent-first 后 event_seq 回放；成功清除 retry，失败递增 attempts。
- 回滚只移除新增 migration/table/index，不覆盖用户数据；旧未绑定数据尚未删除。

## 产出物、执行结果与变更日志

- 产出：合同测试、迁移实现、Schema/状态机说明、Task02 门禁报告。
- 执行结果：后端实现、独立复审与验收均通过；合同测试 12 passed，受影响后端回归 146 passed、5 subtests，运行时探针 5/5，通过 `py_compile`、`git diff --check` 和新增代码聚焦 Ruff 检查。详见 [`backend-report.md`](./artifacts/task-02/backend-report.md)、[`backend-review.md`](./artifacts/task-02/backend-review.md)、[`backend-test-report.md`](./artifacts/task-02/backend-test-report.md)。
- 变更日志：2026-09-13 完成研究库 v2、MemoryRepository ProcessingStep v2 加性迁移、状态/幂等/三级树合同；关闭 owner/跨库 ID、通知幂等、同 kind 节点和 replay seam P1。backend-reviewer 与 backend-tester 均 GO；遗留仅为基线已有的 14 条 Ruff 风格告警，不阻塞 Task02。
