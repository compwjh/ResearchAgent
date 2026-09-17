# Spec 031 执行计划：动态模型路由与资源调度优化

> 关联：[Spec 031](../../specs/031-dynamic-model-resource-routing.md)
> 当前状态：实施中。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-ollama-topology-benchmark.md) | 1–4 个 9B Worker 与多实例 Go/No-Go | Spec027/028、确认、双评审 | 已完成（单实例条件放行） |
| [03](./task-03-routing-observation-shadow.md) | 路由决策、结果和 shadow policy | 02 | 待执行 |
| [04](./task-04-adaptive-worker-routing.md) | 内存感知扩缩、升级和策略激活 | 03 | 待执行 |
| [05](./task-05-routing-insights-ui.md) | 路由解释和基准视图 | 04 | 待执行 |
| [06](./task-06-review-regression-deploy.md) | 最终验收、回归、基准、部署和复盘 | 02–05 | 待执行 |

## 统一规则

- 多实例必须通过 Task02 数据门；NO-GO 时保留单实例实现。
- Langfuse 不可用不能影响 Research Task。
- 开发 Task 定向测试，Task06 唯一一次全量回归。
- 产出写入 `docs/sdd/plans/031/artifacts/task-NN/`。

## 变更日志

- 2026-09-12：随 Spec031 创建。
- 2026-09-17：用户确认 Spec031，开始 Task02 基准门；本阶段不提前运行全量回归。
- 2026-09-17：Task02 完成真实 1–4 Worker 基准；单实例 GO（ResourceProbe cap=1）、多实例 NO-GO/blocked；复核有条件通过，Task03 仅按单实例 shadow/观测路径放行。
