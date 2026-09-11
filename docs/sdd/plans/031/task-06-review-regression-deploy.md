# Task 06：最终评审、基准、回归、部署与复盘

> 关联：[Spec 031](../../specs/031-dynamic-model-resource-routing.md) ｜ 索引：[README](./README.md)
> 依赖：Task02–05 完成；当前状态：`待执行`

## 一句话目标

证明优化策略不降低质量、不超卖资源且可回滚，并完成唯一全量回归、部署和复盘。

## 完整分派 Prompt

```text
角色：双端 reviewer/tester、跨端 tester、architect；读取 Spec031、所有报告、基准和 diff。
允许修改：reviews/031-*.md、plans/031/artifacts/task-06/**、对应 retro；修复退回开发 Task。
禁止用不可比基准宣称提升、破坏局域网 Ollama、push/merge/reset/stash/clean。
验证：质量门、静态/候选策略 A/B、资源边界、故障回退、前端、唯一全量回归、部署。
完成状态：多实例按 Task02 结论实施或明确不实施；三评审与签字齐全。
返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 质量退化、内存超卖、观测故障影响业务均阻塞。
- 产出评审、基准、验收、复盘和部署证据；执行结果待填写。

## 变更日志

- 2026-09-12：创建最终收口 Task。
