# Task 15 定向验证记录

日期：2026-09-21

## 代码与边界

- `SemanticScholarGraphClient` 通过 Academic Graph 批量详情、bulk search、autocomplete、citations/references 返回结构化数据。
- `CatalogSearchGraph.merge_catalog_metadata` 只补缺摘要、作者、DOI、ArXiv ID；官方字段、关键词和 PDF 链接不被覆盖。
- Semantic Scholar 记录为聚合 provenance；未加入旧 `search_source_progress` 的 CHECK/SourceRegistry，避免 SQLite schema 未迁移时写入失败。
- 进程内所有实例共享 1 秒请求槽位；重试会重新取槽；批量详情最多 500 个 ID。

## 定向命令

```bash
.venv/bin/python -m pytest -q \
  tests/paper_discovery/test_semantic_scholar_adapter.py \
  tests/paper_discovery/test_semantic_scholar_import_fallback.py \
  tests/paper_discovery/test_semantic_scholar_metadata.py \
  tests/paper_discovery/test_source_authority_contract.py \
  tests/paper_discovery/test_catalog_search_graph_backend_fix.py
```

结果：`30 passed`（含 Graph 元数据补全、bulk recall 接线、Semantic Scholar ID 入口和跨客户端限流），退出码 `0`。

```bash
.venv/bin/python -m ruff check \
  backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py \
  backend/app/paper_discovery/application/catalog_search_graph.py \
  backend/app/paper_discovery/domain/source_authority.py \
  tests/paper_discovery/test_semantic_scholar_metadata.py \
  tests/paper_discovery/test_source_authority_contract.py
```

结果：`All checks passed`，退出码 `0`。

## 尚未宣称完成

本记录没有伪造外部 API 成功。真实部署环境仍需用已配置 key 复验：批量详情、候选不足时的 bulk recall、服务重启后的缓存和评估器贯通；API 不可达时必须保留官方结果并显示降级。
