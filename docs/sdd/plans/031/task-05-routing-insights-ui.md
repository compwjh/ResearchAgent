# Task 05：实现路由解释与基准界面

> 关联：[Spec 031](../../specs/031-dynamic-model-resource-routing.md) ｜ 索引：[README](./README.md)
> 依赖：Task04；被依赖：Task06；当前状态：`实施中`

## 一句话目标

向用户解释每个 Research WorkItem 的模型选择、升级和 Worker 额度，并提供受控基准结果视图。

## 完整分派 Prompt

```text
角色：frontend-dev；读取 Spec031、本 Task、Task04 API 报告和 research-tasks.js。
允许修改：frontend/research-tasks.js、frontend/styles.css、必要模板和 tests/test_spec031_frontend*；本地模型按两文件拆分。
禁止暴露 Prompt/回答/思维链/详细主机秘密、直接编辑策略规则、修改后端、全量回归。
完成状态：任务时间线显示实际模型/原因/升级；管理视图显示脱敏基准和 active/shadow 状态。
验证：node --check、DOM/XSS/空指标/手机合同、浏览器 smoke、git diff --check。
报告：artifacts/task-05/frontend-report.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 用户界面只显示可理解摘要，诊断细节留给 Langfuse。
- 产出 UI、合同测试和报告；执行结果待填写。

## 变更日志

- 2026-09-12：创建路由 Insights UI Task。
- 2026-09-17：Task04 reviewer/tester GO，启动前端路由解释与基准视图；只显示脱敏摘要，不开放策略编辑或后端修改。
