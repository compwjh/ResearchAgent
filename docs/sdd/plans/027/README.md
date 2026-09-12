# Spec 027 执行计划：Research Task 动态编排 MVP

> 关联：[Spec 027](../../specs/027-research-task-dynamic-orchestration-mvp.md)
> 当前状态：实施中；Spec027 已确认，Task02–04 已完成，当前执行 Task05。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-orchestration-runtime-gate.md) | 冻结 Planner Schema、动态 fan-out、模型路由和资源额度 | Spec确认、双评审 | 已完成 |
| [03](./task-03-backend-research-task-slice.md) | 持久化任务、计划、WorkItem、事件与最小后端闭环 | 02 | 已完成 |
| [04](./task-04-frontend-research-workspace.md) | 深度研究入口、任务工作台、SSE 恢复与手机基础可用 | 03 | 已完成（评审 GO；390px 运行时 smoke 延 Task06） |
| [05](./task-05-replan-report-integration.md) | 覆盖评估、Re-plan、模型升级与初步报告 | 03、04 | 实施中 |
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
- 2026-09-12：Task02、Task03 已完成，按用户继续开发指示启动 Task04。
- 2026-09-12：Task04 完成。研究入口/工作台/SSE 恢复与安全报告展示已实现；补齐 report selections 与 Worker 模型字段合同；前端验收 101 passed、后端定向回归 90 passed，复审 GO；桌面入口 smoke 通过，390px smoke 延 Task06。
- 2026-09-12：Task05 依赖满足，启动 Re-plan、报告、模型升级与集成；按前后端分端并行分派。
- 2026-09-12：Task05 第二阶段完成软预算闸门与 `MODEL_ESCALATED` 安全事件接线（含 search-worker）；后端定向回归 95 passed、5 subtests，Task05 仍实施中，真实 Ollama 路由与最终浏览器/全量验收延 Task06。
