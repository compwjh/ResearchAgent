# Task 06：最终评审、回归、部署与复盘

> 关联：[Spec 028](../../specs/028-research-task-durable-scheduling.md) ｜ 索引：[README](./README.md)
> 依赖：Task02–05 完成；当前状态：`已完成`

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
- 产出评审、验收、复盘与部署证据；调度状态接口、自动化回归与本机服务 smoke 已完成。

## 执行结果

- 需求/技术/验收评审文档已落盘并更新为通过。
- 补齐 `GET /api/research-scheduler/status`，返回队列、额度和安全聚合，不泄露租约 token。
- Spec028 定向回归：24 passed；`node --check`、`py_compile`、`git diff --check` 均通过。
- 唯一最终全量回归：`2481 passed, 1 skipped, 5 warnings, 67 subtests`，退出码 0。
- 8500 本机部署 smoke：`/api/health`、`/api/research-scheduler/status`、首页均 HTTP 200；未知 `/api/*` 仍返回 404。
- 已知环境限制（不改变收口结论）：In-app Browser 对本机地址可能返回 `ERR_BLOCKED_BY_CLIENT`；强退后的真实 Ollama 执行不作为本次部署门禁，持久化恢复合同由 Spec028 定向测试覆盖。

## 变更日志

- 2026-09-12：创建最终收口 Task。
- 2026-09-16：补齐 scheduler status P1；完成定向/全量回归、部署 smoke、评审更新与 Spec028 收口。
