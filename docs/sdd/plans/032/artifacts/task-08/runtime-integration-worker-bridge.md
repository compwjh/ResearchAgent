# Task08 后端：Planner → paper_discovery Worker runtime 接线

## 结果

已完成最小运行时接线。Planner 生成的 `source_ids`/`sources` 经过既有 `SearchWorker` 和
`CatalogSearchAdapter` 时，`ieee_sp`、`ccs`、`ndss`、`openalex`、`crossref` 不再进入仅支持
USENIX/DBLP 的旧 Graph，而是复用 `CatalogSourceFactory` 装配的
`PaperDiscoveryToolFacade`。Worker 的 `WorkerToolResult` 先通过既有 validator，再转换为既有
`CatalogPaper`、`CatalogSourceRecord`、字段 provenance 与 `SearchJob`/`SearchResult` 冻结快照。

`usenix`、`dblp`、`all` 仍使用既有 `CatalogSearchGraph` 路径；没有新增抓取客户端、下载器、URL
安全链、导入器或 embedding 实现。Worker 没有候选时写入失败终态，不把空列表伪装为成功。

Task07 官方目录交接：`CatalogSourceRuntime` 对 NDSS 2024 选择
`{"years":[2024],"route":"official"}`，并将其它年份保留在默认 Crossref fallback；
定向测试确认官方 HTML 请求不会探测 PDF。

## 改动文件

- `backend/app/research/application/search_catalog_adapter.py`
  - `CatalogSourceFactory` 接受七来源 scope，统一装配 `SourceRegistry` 与 `PaperDiscoveryToolFacade`。
  - 新增非旧来源 Worker envelope → catalog/frozen snapshot contract bridge。
  - 维持 USENIX/DBLP/all 旧 Graph 构造与 scope 行为。
- `tests/test_catalog_runtime.py`
  - 新增 OpenAlex Worker runtime 接线、冻结快照、source record 和字段 provenance 合同。
  - 新增非旧 scope 工厂返回 Worker facade、Graph 不复用的合同。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_catalog_runtime.py tests/test_spec032_task07_ndss_official.py tests/test_spec032_ndss_source.py` | 0 | 74 passed |
| `.venv/bin/python -m pytest -q tests/test_spec032_aggregate_sources.py tests/test_spec032_ccs_source.py tests/test_spec032_ieee_sp_source.py tests/test_spec032_ndss_source.py tests/test_spec032_task06_contract.py tests/test_spec032_task09_worker_tools.py tests/test_catalog_runtime.py tests/test_catalog_search_graph_backend_fix.py tests/test_spec029_search_id_bridge.py` | 0 | 215 passed |
| `.venv/bin/ruff check --fix backend/app/research/application/search_catalog_adapter.py tests/test_catalog_runtime.py` | 0 | 3 个导入格式告警自动修复 |
| `.venv/bin/ruff check backend/app/research/application/search_catalog_adapter.py tests/test_catalog_runtime.py` | 0 | All checks passed |
| `.venv/bin/python -m compileall -q backend/app/research/application/search_catalog_adapter.py backend/app/paper_discovery/application/worker_tool.py backend/app/paper_discovery/infrastructure/source_registry.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| `rg -n '^<<<<<<<|^=======|^>>>>>>>' --glob '!**/.venv/**' --glob '!**/.git/**' backend/app/research/application/search_catalog_adapter.py tests/test_catalog_runtime.py` | 1 | 无冲突标记（无匹配的预期退出码） |

## 风险与后续

Worker bridge 在 RAG/index 不可用时保留 Worker 返回顺序并将快照标记为 degraded；不伪造向量分数。
真实外部目录/Ollama/Qdrant smoke 仍属于 Task14 收口范围。Task09 可在此统一 runtime 合同上继续
接入其他 Skill，不应再直接调用来源专用抓取器。
