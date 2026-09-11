# Task 03：实现路由观测与 Shadow Policy

> 关联：[Spec 031](../../specs/031-dynamic-model-resource-routing.md) ｜ 索引：[README](./README.md)
> 依赖：Task02；被依赖：Task04–06；当前状态：`待执行`

## 一句话目标

持久化脱敏路由决策、模型结果和资源快照，并在不影响线上选择的情况下回放候选策略。

## 完整分派 Prompt

```text
角色：backend-dev；读取 Spec031、Task02 报告、Spec013 Langfuse adapter 和 Research Task router。
允许修改：backend/app/research/**、backend/app/platform/observability/** 的最小接缝、必要迁移、tests/test_spec031_shadow*.py；本地模型按两文件拆分。
禁止记录 Prompt/回答/思维链、让 Langfuse 故障阻塞业务、直接激活策略、前端和全量回归。
完成状态：每次路由有 policy/version/reason/outcome；shadow 只计算不控制；观测不可用静默降级。
验证：脱敏 allowlist、缺指标、重复事件、策略回放、定向 pytest、git diff --check。
报告：artifacts/task-03/backend-report.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 检查观测依赖方向和敏感字段；不跑全量。
- 产出数据/观测代码、测试和报告；执行结果待填写。

## 变更日志

- 2026-09-12：创建路由观测 Task。
