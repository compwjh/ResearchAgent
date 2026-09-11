# Spec 027 执行计划：Research Task 动态编排 MVP

> 关联：[Spec 027](../../specs/027-research-task-dynamic-orchestration-mvp.md)
> 当前状态：待确认；确认和双评审前所有 Task 保持待执行。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-orchestration-runtime-gate.md) | 冻结 Planner Schema、动态 fan-out、模型路由和资源额度 | Spec确认、双评审 | 已完成 |
| [03](./task-03-backend-research-task-slice.md) | 持久化任务、计划、WorkItem、事件与最小后端闭环 | 02 | 待执行 |
| [04](./task-04-frontend-research-workspace.md) | 深度研究入口、任务工作台、SSE 恢复与手机基础可用 | 03 | 待执行 |
| [05](./task-05-replan-report-integration.md) | 覆盖评估、Re-plan、模型升级与初步报告 | 03、04 | 待执行 |
| [06](./task-06-review-regression-deploy.md) | 最终复用审计、全量回归、真实 smoke、部署与复盘 | 02–05 | 待执行 |

## 统一规则

- Task02 必须先证明单 Ollama 服务的 9B 并行额度和有界重规划合同可行。
- 只复用 Spec015 的目录、增量缓存、RAG 和导入标识；Spec027 禁止下载 PDF。
- 每个开发 Task 只跑本 Task 定向测试，Task06 才运行一次全量回归。
- 线上子 Agent 正常运行时等待其主动返回，不频繁读取日志。
- 产出写入 `docs/sdd/plans/027/artifacts/task-NN/`；范围变化必须回到 Spec。

## 里程碑

- M1：固定样本证明动态计划、fan-out/fan-in、模型升级和资源额度。
- M2：后端可以持久化运行并输出可恢复事件。
- M3：用户能从会话创建任务并观察执行过程。
- M4：覆盖不足会有界 Re-plan，最终生成可追溯初步报告。
- M5：全量回归、部署和复盘完成。

## 变更日志

- 2026-09-12：随 Spec027 创建，全部 Task 初始为待执行。
