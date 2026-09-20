# Task 04：实现报告生成、版本和导出

> 关联：[Spec 030](../../specs/030-research-evidence-reporting.md) ｜ 索引：[README](./README.md)
> 依赖：Task03；被依赖：Task05–06；当前状态：`已完成`

## 一句话目标

从已校验证据矩阵生成不可覆盖的只读报告版本，并提供一致的 Markdown、HTML 和 JSON 引用产物。

## 完整分派 Prompt

```text
角色：backend-dev；读取 Spec030、本 Task、Task03 报告和现有安全 Markdown 渲染边界。
允许修改：backend/app/research/**、routes_research.py、tests/test_spec030_report*.py；本地模型按两文件拆分。
禁止富文本编辑、自动投稿、无证据断言、前端、全量回归、push/merge/reset/stash/clean。
完成状态：生成失败不发布半份正式报告；成功报告版本不可覆盖；三格式引用一致。
验证：中断、重试、重复、引用丢失、XSS、语言、下载头、定向 pytest、git diff --check。
报告：artifacts/task-04/backend-report.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 抽样逐 Claim 回查 manifest；Markdown 为权威产物。
- 产出报告代码、测试和报告；执行结果待填写。

## 变更日志

- 2026-09-12：创建报告生成与导出 Task。
- 2026-09-17：复用既有安全渲染器实现 evidence-report-v1 版本化报告与三格式导出；定向测试 4 passed，判定 PASS。
