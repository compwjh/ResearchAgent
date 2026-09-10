# Task 07：能力方法记忆与 Skill 改进建议

> 关联：[Spec 022](../../specs/022-project-conversation-memory.md) ｜ 索引：[README](./README.md)
> 依赖：Task04；被依赖：Task08；当前状态：`待执行`

## 一句话目标

把经过失败—修正—验证的稳定做法沉淀为可召回的方法卡，并只生成可审查的 Skill 改进建议，绝不自动改项目规则或代码。

## 增量范围

- `capability_method` 记录适用场景、步骤、验证、失败信号、关键词和证据。
- 方法卡必须来自明确用户要求、跨会话重复或工具失败后验证成功。
- 运行时按任务召回少量方法卡，遵守同一 scope 和 token 预算。
- Skill 改进建议包含目标文件、问题证据、建议 diff 摘要、验证方式和风险，状态只允许 `proposed / accepted / rejected / applied`。
- `applied` 只能由 SDD 外部开发流程在用户确认后写回，产品运行时无文件写权限。

## 子 Agent 分派

- backend-dev：方法卡与建议队列；不得获得修改 `.agents/skills`、AGENTS 或代码的运行时能力。
- reviewer/tester：证据门、scope、重复合并、错误方法撤销和文件零写探针。

## 边界与明确不做

- 不自动改 Skill、Prompt、AGENTS、代码或用户级 Codex 配置。
- 不从隐藏思维链、Langfuse、Agent logs 或未脱敏工具输出学习。
- 不把一次成功做法直接升格为通用能力。

## 测试与验收

- 有证据的方法卡可被相关任务召回，无关项目不可召回。
- 失败信号触发降权/候选复审，不静默覆盖。
- 生成建议前后受保护文件 hash 不变；建议可导出供后续 SDD 使用。

## 风险与回滚

- 任意运行时文件写入能力视为 P0，立即关闭建议功能。
- 错误方法卡可停用或 supersede，不删除证据链。

## 产出物

- `artifacts/task-07/implementation-report.md`
- `artifacts/task-07/test-report.md`
- `artifacts/task-07/review-report.md`

## 执行结果

待执行后填写。

## 变更日志

- 2026-09-11：创建能力方法与只读改进建议 Task。

