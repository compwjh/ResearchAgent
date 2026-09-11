# Task 06：最终评审、回归、部署与复盘

> 关联：[Spec 028](../../specs/028-research-task-durable-scheduling.md) ｜ 索引：[README](./README.md)
> 依赖：Task02–05 完成；当前状态：`待执行`

## 一句话目标

完成独立并发/恢复审计、唯一全量回归、部署和 Spec028 收口。

## 完整分派 Prompt

```text
角色：双端 reviewer/tester、跨端 tester、architect；读取 Spec028、全部 Task 报告和实际 diff。
允许修改：reviews/028-*.md、plans/028/artifacts/task-06/**、对应 retro；修复退回原开发 Task。
禁止扩大范围、伪造崩溃恢复、push/merge/reset/stash/clean。
验证：两个进程领用、强退恢复、审批/取消竞态、公平性、前端交互、唯一全量回归、部署 health/smoke。
完成状态：三份评审和签字齐全，状态台账一致。
返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- P0/P1、重复执行或资源超卖均阻塞收口。
- 产出评审、验收、复盘与部署证据；执行结果待填写。

## 变更日志

- 2026-09-12：创建最终收口 Task。
