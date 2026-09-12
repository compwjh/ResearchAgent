# Task02 — 数据模型、状态机、迁移与兼容门禁

> 关联：[Spec034](../../specs/034-conversational-deep-research-agent-runtime.md) ｜ 索引：[README](./README.md)
> 依赖：Task01、Spec确认、需求/技术评审通过；当前状态：`待执行`

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

## 实施步骤与文件边界

1. 先写合同测试和迁移设计文档，不实现业务编排。
2. 后端开发只改 `backend/**` 与后端测试；ProcessingStep 数据迁移也归后端。
3. 验证旧库重复启动迁移幂等、旧 processing_steps 可读、跨 owner 引用拒绝。
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
- 回滚只移除新增 migration/table/index，不覆盖用户数据；旧未绑定数据尚未删除。

## 产出物、执行结果与变更日志

- 产出：合同测试、迁移实现、Schema/状态机说明、Task02 门禁报告。
- 执行结果：待执行后填写真实命令、退出码、通过数量和阻塞。
- 变更日志：待执行后填写。
