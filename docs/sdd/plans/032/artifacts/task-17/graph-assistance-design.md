# Task 17 图辅助客户端记录

日期：2026-09-21

`SemanticScholarGraphClient` 已提供受控的 `autocomplete`、`citations` 和 `references` 调用：

- autocomplete 查询截断至 100 字符，最多返回 20 个短候选；
- 图边只允许 `citations`/`references`，单页最多 100 条；
- 返回仅作为交互或覆盖审查的辅助，不自动进入官方目录、引用清单或 PDF 下载链；
- 统一复用 API key、1 RPS 限流和降级错误码。

产品 API/UI 入口暂不提前开放，待 Task16 的来源 schema 和 Task14 最终评审确认后再接线，避免把聚合图边误当成冻结报告证据。
