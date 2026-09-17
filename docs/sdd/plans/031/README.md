# Spec 031 执行计划：动态模型路由与资源调度优化

> 关联：[Spec 031](../../specs/031-dynamic-model-resource-routing.md)
> 当前状态：实施中。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-ollama-topology-benchmark.md) | 1–4 个 9B Worker 与多实例 Go/No-Go | Spec027/028、确认、双评审 | 已完成（单实例条件放行） |
| [03](./task-03-routing-observation-shadow.md) | 路由决策、结果和 shadow policy | 02 | 已完成（单实例条件放行） |
| [04](./task-04-adaptive-worker-routing.md) | 内存感知扩缩、升级和策略激活 | 03 | 已完成（后端 GO） |
| [05](./task-05-routing-insights-ui.md) | 路由解释和基准视图 | 04 | 已完成（前端 GO） |
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
- 2026-09-17：Task03 完成值级脱敏观测、生产 opt-in 装配与 shadow replay；独立复审 GO，111 passed、5 subtests。生产 outcome 和 Task02 证据增强留给 Task06。
- 2026-09-17：Task04 启动；在 Task02 cap=1 门禁下实现 Fake 资源感知、全局额度、公平调度、升级与策略回滚，禁止多实例和自动模型生命周期变更。
- 2026-09-17：Task04 完成 strong 原子单并发、过期 quota 回收、grant 隔离与服务端 evidence gate；reviewer/tester GO，154 passed、5 subtests，Task05 可开始。
- 2026-09-17：Task05 启动；前端仅展示脱敏模型/原因/Worker/升级摘要和受控基准状态，禁止显示 prompt、回答、思维链或主机秘密。
- 2026-09-17：Task05 完成路由解释、Worker/降级、升级和 warm/cold 基准只读卡；reviewer/tester GO，43 passed，Task06 进入最终收口。
