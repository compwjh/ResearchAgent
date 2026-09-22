# Task 16 缓存语义审查记录

日期：2026-09-22

## 结论

`CatalogSearchGraph._recall_semantic_scholar_candidates` 现按稳定的
`semantic_scholar|conference|bulk|query-hash` 单元读取 `PaperDiscoveryStore.get_fetch_unit`。
已有 `status=completed` 的单元直接结束，不再发起 bulk 请求，也不会重复写入论文、source record
或 provenance。成功写入后通过现有 `save_fetch_unit` 回填 `paper_count` 与 `last_success_at`。

未修改官方来源、`SourceRegistry` 或任何 SQLite `CHECK` 约束；未新增 store API。

## 定向验证

```text
.venv/bin/python -m pytest -q tests/paper_discovery/test_semantic_scholar_graph_integration.py
退出码：0

.venv/bin/python -m ruff check \
  backend/app/paper_discovery/application/catalog_search_graph.py \
  tests/paper_discovery/test_semantic_scholar_graph_integration.py
退出码：0
```

补充测试覆盖同一 query + conference + scope 连续调用：第二次调用复用 completed
`SourceFetchUnit`，外部调用次数、候选写入和 source record 数量均保持不变。

## 风险与后续

缓存键沿用 Task16 已落地的 conference + query hash；当前方法仅对 `source_scope=all` 生效，
因此 scope 不会与其它 scope 冲突。并发请求协调仍依赖后续专门的租约/原子获取设计；本次不扩展
现有 store API，也不把失败响应错误标记为 completed。
