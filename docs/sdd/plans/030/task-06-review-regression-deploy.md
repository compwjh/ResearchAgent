# Task 06：最终评审、回归、部署与复盘

> 关联：[Spec 030](../../specs/030-research-evidence-reporting.md) ｜ 索引：[README](./README.md)
> 依赖：Task02–05 完成；当前状态：`待执行`

## 一句话目标

证明所有主要结论均可追溯、三种报告格式一致，并完成唯一全量回归、部署和复盘。

## 完整分派 Prompt

```text
角色：双端 reviewer/tester、跨端 tester、architect；读取 Spec030、全部 Task 报告和 diff。
允许修改：reviews/030-*.md、plans/030/artifacts/task-06/**、对应 retro；修复退回开发 Task。
禁止扩大报告编辑/投稿范围、伪造证据、push/merge/reset/stash/clean。
验证：固定冲突矩阵、逐 Claim 引用回查、三格式、XSS、浏览器、唯一全量回归、部署。
完成状态：三评审与签字齐全，Spec/Task/台账同步。
返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 任一孤立 Claim、错引或格式语义漂移均阻塞。
- 产出评审、验收、复盘和部署证据；执行结果待填写。

## 变更日志

- 2026-09-12：创建最终收口 Task。
