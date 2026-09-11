# Task 03：接入 OpenAlex 与 Crossref

> 关联：[Spec 032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md)
> 依赖：Task02 GO；被依赖：Task05–06；当前状态：`待执行`

## 一句话目标

把现有 OpenAlex/Crossref 能力迁入统一全局目录 Adapter，作为辅助书目来源并保留字段 provenance。

## 完整分派 Prompt

```text
角色：backend-dev；读取 Spec032、Task02 报告、现有 article_assistant OpenAlex/Crossref 代码和 paper_discovery source/store。
允许修改：backend/app/paper_discovery/**、必要 api 装配、tests/test_spec032_aggregate_sources*.py；本地模型按两文件拆分。
禁止并行复制旧客户端、覆盖官方字段、下载 PDF、前端、全量回归、push/merge/reset/stash/clean。
完成状态：两个来源按统一 fetch unit 增量同步，重启后缓存可识别，字段只补缺并记录 provenance。
验证：固定 JSON、限流/超时/分页、ETag/hash、重复记录、定向 pytest、git diff --check。
报告：artifacts/task-03/backend-report.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 确认旧能力被抽取复用而非复制，官方字段不被降级。
- 产出 adapters、测试和报告；执行结果待填写。

## 变更日志

- 2026-09-12：创建聚合来源接入 Task。
