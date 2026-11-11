# Task08 Runtime Integration 交接

日期：2026-09-20

## 结论

Task08 的最小 runtime 契约通过定向验证。七个受控来源均可由 `SourceRegistry.adapter()` 懒加载并缓存；来源同步 API 对未知/停用来源 fail-closed，并将受控同步写入既有 SQLite `search_jobs` 与 `search_source_progress`，返回真实完成终态。

本轮发现并修复一个明显契约 bug：generic adapter 路径在抓取后先保存了 `completed` 单元，随后汇总持久化又用原始 `pending` descriptor 覆盖状态；现在汇总保留 adapter 返回的 updated unit，缓存命中保留已有 completed unit。

## 共享 schema 与持久化

没有新增作业表或缓存表，复用 `PaperDiscoveryStore` 现有 schema v4：

- `search_jobs`：一条来源同步对应一条 `SearchJob`，`graph_version = catalog-source-sync-v1`，终态为 `completed` / `partial` / `failed`。
- `search_source_progress`：按 `(search_id, source_kind)` 保存 `queued → fetching → completed/cached/failed` 与安全消息码。
- `source_fetch_units`：保存来源年度/范围单元、内容 hash 和终态；本轮测试确认 `openalex|2024` 在成功抓取后保持 `completed`。
- `catalog_papers`、`catalog_source_records`、`field_provenance`：runtime 通过现有 Store 接口写入目录记录、原始来源记录和字段 provenance。

重启恢复验证：关闭首个 Store 后以同一临时 SQLite 路径重新构造 `PaperDiscoveryStore`，`search_jobs` 与 `search_source_progress` 仍读取到 `completed` 终态。

## 来源与接口样例

Registry 工厂覆盖：`usenix`、`dblp`、`ieee_sp`、`ccs`、`ndss`、`openalex`、`crossref`。每个 adapter 按 source ID 缓存，未触发网络抓取。

请求：

```http
POST /api/papers/sources/openalex/sync
{"scope":{"years":[2024]}}
```

响应先返回 `202` 与 `status=queued`；后台 runtime 完成后：

```http
GET /api/papers/sources/openalex/sync/{sync_id}
```

返回 `200`、`status=completed`、`error_code=null`，并带有 `progress.status=completed`、`paper_count` 与 `message_code=SOURCE_COMPLETED`。

Task07 官方目录交接：`CatalogSourceRuntime` 对 `ndss` 的 2024 年单元传递
`{"years":[2024],"route":"official"}`，复用已验证的 NDSS accepted-papers HTML 路由；
同一请求中的其它年份仍按默认 Crossref fallback。目录阶段只抓 HTML，不探测或下载 PDF。

边界响应：

- 未知来源：`404 SOURCE_NOT_FOUND`，不会创建 `search_jobs`。
- 已停用来源：`422 SOURCE_DISABLED`，不会创建 `search_jobs`。
- runtime 事件：启动写入 `SOURCE_STARTED`，成功写入 `SOURCE_COMPLETED`；异常写入 `SOURCE_FAILED` 并将 job/progress 收敛到 failed。

## 改动与验证

本轮直接改动：

- `backend/app/paper_discovery/application/catalog_runtime.py`：保留 updated/cache-hit fetch unit，清理本文件 lint 违规。
- `backend/app/paper_discovery/application/entry.py`、`backend/app/api/routes_paper.py`：Task08 runtime 出口与同步 API 接线已由工作树现有改动提供，本轮仅复核并整理 import。
- `tests/test_catalog_runtime.py`：新增七来源工厂、未知/停用 API、真实终态、SQLite job/progress 与重启读取覆盖。

验证命令与结果：

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_catalog_runtime.py tests/test_spec032_task07_ndss_official.py tests/test_spec032_ndss_source.py` | 74 passed，退出码 0 |
| `.venv/bin/python -m pytest -q tests/test_paper_discovery_api.py tests/test_paper_discovery_async_api.py tests/test_paper_discovery_store.py` | 45 passed，12 subtests passed，退出码 0 |
| `.venv/bin/ruff check backend/app/paper_discovery/application/catalog_runtime.py backend/app/paper_discovery/application/entry.py backend/app/paper_discovery/infrastructure/source_registry.py backend/app/api/routes_paper.py tests/test_catalog_runtime.py` | All checks passed，退出码 0 |
| `.venv/bin/python -m compileall -q backend/app/paper_discovery/application/catalog_runtime.py backend/app/paper_discovery/application/entry.py backend/app/paper_discovery/infrastructure/source_registry.py backend/app/api/routes_paper.py tests/test_catalog_runtime.py` | 通过，退出码 0 |
| `git diff --check` | 通过，退出码 0 |

说明：仓库 `.venv/bin/pytest` 的 shebang 指向已不存在的旧路径，本轮统一使用 `.venv/bin/python -m pytest`，不修改环境文件。

## 范围与剩余风险

未触碰 frontend、Research Graph 重构、模型路由、报告或其他 Spec 文件。真实外站抓取不在本测试中执行；测试使用受控 fake adapter 验证 runtime/store 接缝。主 Agent 仍需复查 Graph 对 USENIX/DBLP 的既有路径与 Task07 来源覆盖矩阵，再决定后续 Task09 放行。
