> 关联：[Spec039](../../specs/039-api-e2e-manual-acceptance-protocol.md) ｜ 索引：[README](./README.md)
> 依赖：Task04、Task05；当前状态：`部分完成（阻塞）`

# Task06：为 Spec032 生成首份真实验收案例

## 一句话目标

使用当前部署版本跑通 Spec032 的自然语言 Intake API E2E，并生成用户可执行的 USENIX 单来源人工验收案例。

## 前置门禁

- Spec032 主路径代码和服务可启动；
- 自然语言 Intake 必须成功识别主题、目标和时间范围；
- 失败时先修复或记录为 Spec032 阻塞，不得用创建表单路径替代。

## 产出物

- `artifacts/spec032-api-e2e-success.md`
- `artifacts/spec032-manual-acceptance.md`
- 真实任务 ID、报告路径和准备度评分。

## 执行结果

已在当前部署服务完成真实自然语言 Intake、计划生成和审批调用，并复核一份历史真实完成任务。
详见：

- `artifacts/spec032-api-e2e-success.md`
- `artifacts/spec032-manual-acceptance.md`
- `artifacts/spec032-readiness-matrix.md`

结论为 `BLOCKED`：真实任务最终已完成且生成 Artifact，但报告缺少标题、摘要、关键词和方法比较，
并且尚未完成真实浏览器投影复核，不能交给用户人工验收。该 Task 不得宣称 Spec032 已通过。
