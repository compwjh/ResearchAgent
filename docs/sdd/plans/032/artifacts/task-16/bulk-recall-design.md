# Task 16 候选池辅助召回落地记录

日期：2026-09-21

## 已实现

- `SemanticScholarGraphClient.search_bulk`：限制 query、year、limit 和字段；统一错误码、重试与 1 RPS 限流。
- `CatalogSearchGraph._recall_semantic_scholar_candidates`：候选少于配置阈值（默认 5）且配置允许时才触发；补充数量有界，按 DOI/ArXiv/标题+年份去重。
- 补充论文写入现有 `CatalogPaper`、`SourceFetchUnit`、`CatalogSourceRecord` 和字段 provenance；`source_kind=semantic_scholar` 只作为聚合记录，不加入官方 SourceRegistry 或 `search_source_progress`。
- `source_scope=usenix/dblp` 不触发聚合召回，避免污染官方来源结果；只有 `all` scope 可见聚合候选。

## 门禁

- 不凭 Semantic Scholar venue 字段宣称会议归属。
- 不在搜索阶段下载/验证 PDF。
- API 失败保留官方结果并产生可观察的降级事件；不会清空既有目录。

## 待 Task14 验收

需要在部署环境用真实 key 验证：候选不足时 bulk 请求、重复查询不重复入库、服务重启后 `semantic_scholar` source record 与 provenance 可读；候选仍需经论文评估后才能进入报告。
