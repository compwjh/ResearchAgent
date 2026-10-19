# Task03 service/similarity 修复交接

日期：2026-10-19；角色：backend-dev；范围：`service.py`、`similarity.py`、`catalog_adapter.py` 与地图能力测试。未修改 store/runtime/import_bridge/routes/frontend；`import_node` 保留给后续适配任务。

## 结论

本轮服务层核心修复 **GO（供独立复审）**：官方目录筛选不再被 S2 venue 猜测替代，未知来源/会议在创建边界拒绝；通用 S2 结果仍保留实际 `provider_count`，地图层按年份、身份、相关性和 requested limit 截取。整体 Task03 仍不能据此宣称收口，导入生产组合根及路由错误映射由其他 agent/门禁继续处理。

## 已落实

- 创建使用 store 的 `create_map_with_job` 原子幂等接口；worker 使用 `claim_job`，节点/边写入传 `job_id`，终态 stop 不覆盖已完成作业。
- 成功搜索与 references response 通过 store `request_cache_key/get_request_cache/put_request_cache` 复用；仅成功 envelope 入缓存，缓存 key 包含 provider、operation、query/identifier、filters、page、fields、schema version。失败/429 不写成功空页。
- 发现、每节点 references、similarity 写入 `save_unit_checkpoint`；retry 通过 store CAS 保留失败单元和原 step，只处理未完成 references/similarity，不重搜已持久节点。
- 会议/来源通过 `CatalogSourceAdapter` 窄接缝复用既有 `CatalogSearchAdapter`/`CatalogSearchGraph` 与目录缓存；候选必须有目录适配器 scope 见证，不能从 S2 `venue` 推断会议。未配置官方目录时返回 `CATALOG_SOURCE_UNAVAILABLE` partial，不伪造节点。
- `cosine_similarity` 与 embedding 入缓存前拒绝非有限、空范数、空/维度不一致向量；相似层以 `EMBEDDING_INVALID_RESPONSE` 或 `EMBEDDING_UNAVAILABLE` 明确 unavailable。
- 预期 `ValueError` 收敛为 `MAP_JOB_INVALID_INPUT` failed/partial，终态事件传入首个固定 error code；不写原始异常文本。

## store 对接合同

实际依赖以下已实现签名：

- `create_map_with_job(owner_id, *, topic, name, project_id, filters, requested_count, operation, idempotency_key, params_hash)`
- `request_cache_key(...)`、`get_request_cache(key)`、`put_request_cache(key, payload, ttl_seconds=86400, status="success")`
- `claim_job(job_id, map_id, owner_id)`、`retry_job(job_id, map_id, owner_id)`、`stop_job(job_id, map_id, owner_id)`
- `save_unit_checkpoint(job_id, map_id, owner_id, *, unit_key, status, payload, error_code)`、`completed_units(job_id, map_id, owner_id)`
- `add_nodes(..., job_id=...)`、`add_edges(..., job_id=...)`

接口缺口：官方目录结果的生产组合根尚未把目录 store/元数据 resolver 注入地图 service；窄适配器已有既有 CatalogSearchAdapter 路径和 S2 enrich 接口，下一 agent 可在 runtime 组合时注入，不需复制抓取器。导入桥接与 routes 的 503 错误映射不在本轮文件边界。

## 验证

- `.venv/bin/python -m pytest -q tests/literature_maps/test_map_discovery.py tests/literature_maps/test_map_similarity.py tests/literature_maps/test_map_job_recovery.py`：退出码 0，12 passed。
- 补充受影响地图域回归（identity/store/job-store/api）：退出码 0，25 passed（与上项重叠计数不重复声明为新增总数）。
- `test_map_import_bridge.py` 未纳入本轮通过结论；其当前 3 个失败来自并行 import-bridge agent 尚未落地的新构造/SSRF/回写合同，不是本轮 service/similarity 改动。
- `.venv/bin/ruff check`（上述三份应用代码及三份精准测试）：退出码 0，All checks passed。
- `.venv/bin/python -m py_compile backend/app/literature_maps/application/service.py backend/app/literature_maps/application/similarity.py backend/app/literature_maps/application/catalog_adapter.py`：退出码 0。
- 未运行全量 pytest、未启动服务、未读写 `.env`、未调用真实 provider；真实 S2/embedding E2E 仍需由验收门禁单独记录。

## 2026-10-19 service/catalog P1 接续修复

- `CatalogRow` 现在保留 `catalog_paper_id`、`source_kind`、官方页、官方 PDF、prepublication PDF、DOI、arXiv 以及目录服务端快照；默认目录适配器将既有 `CatalogPaper`/S2 enrich 结果按 catalog ID 对齐，不丢失官方 provenance。
- `_to_node()` 保持 S2 `external_ids.semantic_scholar` 与 `catalog_paper_id` 分离，节点 `source_url` 优先官方页；provenance 暴露经过 HTTP(S)/凭据/fragment 校验的官方候选和脱敏 `catalog_snapshot`，不把 S2 landing 当官方 PDF，也不泄漏快照中的 authorization/secret 类字段。
- source/conference 目录结果不足 requested 时按缺口只发一条有界 S2 `search_bulk(limit=gap)` 请求；S2 返回条数按真实 envelope 计入 `provider_count`，`provider_truncated` 记录 provider 忽略 limit 的情形，`accepted_count`/最终节点数由地图层截取。无 catalog identity scope 证明的 S2 行（包括仅 venue 相似的行）全部排除，官方行优先保留并以 partial 收束，不硬凑。
- 缺口 S2 行仅在 DOI/arXiv 或标题+年份与已认证官方行真实匹配时用于 fill-only 富化；官方标题、作者、年份、摘要和官方下载 provenance 不被 S2 覆盖。
- `_finish()` 已接 store `finish_job(..., status, map_status, step, counts, failed_units, cursor, error_code, event_type)` 原子终态 CAS，移除 service 层先查、再改 map、再改 job 的竞态路径；stop/duplicate worker 不会复活终态。
- retry 对已升级 store 的 queued CAS 使用 `expected_status="queued"` 写回 step/cursor，避免 retry 已成功入队后被旧的 running 默认守卫误判为不存在。

本接续 handoff 给 import agent 的稳定字段路径：`MapPaper.catalog_paper_id`；`MapPaper.provenance.catalog_snapshot`；`MapPaper.provenance.official_page_url`、`official_pdf_url`、`prepublication_pdf_url`、`source_kind`、`doi`、`arxiv_id`。import 仍应只消费 server-owned snapshot，不接受客户端 URL override。

### 接续验证

- `.venv/bin/python -m pytest -q tests/literature_maps/test_map_discovery.py tests/literature_maps/test_map_job_recovery.py tests/literature_maps/test_map_api.py tests/literature_maps/test_map_api_errors.py`：退出码 0，15 passed。
- `.venv/bin/ruff check backend/app/literature_maps/application/service.py backend/app/literature_maps/application/catalog_adapter.py tests/literature_maps/test_map_discovery.py tests/literature_maps/test_map_job_recovery.py tests/literature_maps/test_map_api.py`：退出码 0，All checks passed。
- `.venv/bin/python -m py_compile backend/app/literature_maps/application/service.py backend/app/literature_maps/application/catalog_adapter.py`：退出码 0；`.venv/bin/python scripts/check_test_layout.py`：退出码 0。
- 追加 scoped 地图域回归 `.venv/bin/python -m pytest -q tests/literature_maps`：退出码 0，48 passed；未运行项目全量测试。

## 2026-10-19 最终冻结复审 P1 接续

- `CatalogSourceAdapter` 对多 source/conference 构造合法兼容 pair 并逐项查询；列表内部是 OR，source 与 conference 取兼容交集。默认既有 CatalogSearchAdapter 路径现在依据 `CatalogPaper.conference_id` 与 store `get_catalog_source_kinds()` 的实际记录填写 scope，绝不把请求数组回填成 provenance；无真实 source identity 的目录行不入 scoped map。
- service 创建边界将未知 source、未知 conference 和不支持的 source/conference 组合统一拒绝为 `ValueError("INVALID_MAP_SCOPE")`；该固定类型供 route 层映射为 400，目录运行时不可用仍保持 `CATALOG_SOURCE_UNAVAILABLE`/partial 语义。
- references provider budget 使用持久 `job.counts.provider_request_count` 计算剩余额度，跨 retry 不重置；缓存命中不消耗外呼额度，client 内部 retry 仍按一次逻辑 provider 请求计数。达到 60 后只写 `MAP_GRAPH_BUDGET_EXCEEDED` checkpoint/partial event，不再调用 provider；新 job 重新拥有独立预算。

### 最终接续验证

- `.venv/bin/python -m pytest -q tests/literature_maps`：退出码 0，62 passed。
- `.venv/bin/ruff check backend/app/literature_maps/application/service.py backend/app/literature_maps/application/catalog_adapter.py tests/literature_maps/test_map_discovery.py tests/literature_maps/test_map_job_recovery.py tests/literature_maps/test_map_api.py`：退出码 0，All checks passed。
- `.venv/bin/python -m py_compile backend/app/literature_maps/application/service.py backend/app/literature_maps/application/catalog_adapter.py`：退出码 0；`.venv/bin/python scripts/check_test_layout.py`：退出码 0。
- 未修改 routes/API mapper、store、import/runtime/frontend；未运行全量 pytest、生产服务或真实 provider。

## 2026-10-19 unscoped relevance endpoint 接续修复

- `SemanticScholarGraphClient.search_relevance()` 新增窄方法，复用同一限流、有限 retry、fields 和错误映射，改用官方 `/paper/search` relevance-ranked endpoint；原 `search_bulk()` 保持不变。
- unscoped 地图首批 discovery 优先调用 `search_relevance()`，缓存 operation 改为 `search_relevance`，与旧 bulk 缓存严格分离；缺少新方法的旧注入测试 client 保留有限 fallback，不改变生产路径。
- `_select_rows()` 对 unscoped rows 保留 provider 返回顺序，仅做身份/年份/去重/主题非零 gate 和 requested limit 截取；scoped catalog 仍保留原 lexical/ID 排序与官方 scope 约束。
- 不接受 `data=null` 为零引用；引用解析、catalog scoped 流程、provider 预算和 routes/store/runtime/frontend 均未改。

### 接续验证

- `.venv/bin/python -m pytest -q tests/paper_discovery/test_semantic_scholar_graph_api.py tests/literature_maps/test_map_discovery.py`：退出码 0，20 passed。
- `.venv/bin/ruff check backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py backend/app/literature_maps/application/service.py tests/paper_discovery/test_semantic_scholar_graph_api.py tests/literature_maps/test_map_discovery.py`：退出码 0，All checks passed。
- `.venv/bin/python -m py_compile backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py backend/app/literature_maps/application/service.py`：退出码 0；`.venv/bin/python scripts/check_test_layout.py`：退出码 0；`git diff --check`：退出码 0。
- 新增 mock-transport 证据覆盖 relevance endpoint/参数/顺序、旧 bulk endpoint 不变、429/503 错误映射；新增地图测试覆盖 relevance 顺序与缓存 operation 隔离。
- 本轮未发起真实 provider 请求、未部署/重启服务；已有旧 map retry 不会重搜，后续需由主会话决定是否创建新图复验。
