# Spec034 任务索引

> 关联：[Spec034](../../specs/034-conversational-deep-research-agent-runtime.md)
> 当前状态：实施中；Spec034 已确认，Task02 已完成，Task03 可开始。

## 依赖顺序

`02 → 03 → 04 → 05 → 06 → 08 → 09 → 10`

`02 → 05 → 07 → 08`

> Task02 的唯一门禁前置为 Spec 确认与需求/技术双评审通过；其余依赖只引用本索引中实际存在的 Task 文档。

## 任务

- [Task02：数据模型、状态机、迁移与兼容门禁](./task-02-session-state-and-migration-gate.md) — 已完成（backend-reviewer/backend-tester GO）
- [Task03：会话意图、Deep Research Skill 与 Intake](./task-03-conversational-intake.md) — 待执行
- [Task04：计划版本、统一审批命令与前端卡片](./task-04-plan-and-approvals.md) — 待执行
- [Task05：ResearchAgentRunner 与真实子 Agent 循环](./task-05-agent-runtime.md) — 待执行
- [Task06：论文目录、评估、Critic 与覆盖补偿](./task-06-research-execution.md) — 待执行
- [Task07：processing_steps 三级树与实时投影](./task-07-processing-tree.md) — 待执行
- [Task08：报告 Artifact、会话写回与通知](./task-08-report-and-notifications.md) — 待执行
- [Task09：Research Tab 复用、旧入口与旧数据清理](./task-09-workspace-and-cleanup.md) — 待执行
- [Task10：最终评审、回归、真实 Smoke、部署与复盘](./task-10-review-regression-deploy.md) — 待执行

## 状态规则

- 用户确认 Spec 且需求/技术评审通过前，所有任务保持 `待执行`。
- 开始任务时同步更新本索引、任务文件和 Spec 任务表。
- Task 定向通过不代表 Spec 完成；Task10 全量回归、真实运行、部署和三道门禁全部通过后才能收口。
