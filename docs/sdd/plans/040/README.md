# Spec 040 任务索引

> 关联：[Spec 040](../../specs/040-research-runtime-retry-and-online-fallback.md)

本目录只描述运行时失败恢复的增量。所有 Task 初始为 `待执行`；Spec 确认、需求评审和技术评审通过前不得修改业务代码。

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02 失败分类与 Go/No-Go](./task-02-failure-contract.md) | 冻结可重试错误、回退边界和事件合同 | 01 | 已完成（与 Task03 合并验证） |
| [03 指数退避](./task-03-exponential-backoff.md) | 资源忙时持久化排队、退避、恢复和幂等领取 | 02 | 已完成（后端定向验证通过） |
| [04 线上 Provider 回退](./task-04-online-provider-fallback.md) | 在授权配置下切换线上模型并保留尝试链 | 02、03 | 已完成（后端定向验证通过） |
| [05 观测与前端状态](./task-05-retry-observability.md) | 展示等待、重试、切换和耗尽状态 | 03、04 | 已完成（前后端定向验证通过） |
| [06 收口](./task-06-review-deploy-retro.md) | 定向验收、全量回归、部署和复盘 | 05 | 已完成 |
