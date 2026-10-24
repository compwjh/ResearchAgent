# Spec043 Task03 后端独立评审

## 结论

**Block（P1 核心合同缺陷，暂不批准合并/部署）**。后端定向测试通过，但测试仅覆盖 10 条基础路径；真实用户主路径仍有阻塞：会议/来源筛选不会生效，主动入库生产组合根恒为不可用，作业重试会重复成功工作，且若干恢复、缓存、错误体和向量边界不满足冻结合同。

前端文件不在本评审范围内。未修改业务代码、测试或 Spec，未部署、未运行全量回归、未调用真实外部 API。

## 按优先级的问题

### [P1] 主动入库生产路径恒为 503，且结果没有回写节点状态

文件：`backend/app/literature_maps/application/runtime.py:19-24`、`backend/app/literature_maps/application/import_bridge.py:17-27`、`backend/app/literature_maps/application/service.py:233-243`

问题：组合根实例化 `LiteratureMapImportBridge()` 时没有传入既有论文/知识库导入 callable；`importer` 因而始终为 `None`，每次用户点击主动入库都会抛 `IMPORT_BRIDGE_UNAVAILABLE` 并返回 503。即使测试注入 callable，`service.import_node()` 也只返回结果，不把返回的 `document_id`、下载/索引状态写回 `MapPaper`，重开地图仍显示未入库。Task03 的“点击加入知识库”主路径因此没有生产实现。

最小修复：在组合根建立窄适配器，调用现有 `routes_paper`/`paper_import` 安全导入链（不复制 downloader/login/indexer），并在同一 owner/map/node 事务边界记录既有句柄和状态；导入失败只记录稳定错误。

### [P1] `source_ids`/`conference_ids` 是无效筛选，没有会议官方目录优先

文件：`backend/app/literature_maps/application/service.py:61-63,109-132,340-362`

问题：请求中的 source/conference 仅被写入 `filters`，`_select_rows()` 只按年份过滤；发现阶段永远只调用通用 `SemanticScholarGraphClient.search_bulk()`，没有官方会议目录查询、优先合并或补缺。传入任意会议 ID 仍会把通用 S2 结果加入地图，实际违反“已支持会议官方目录优先、再聚合补缺”，也会让用户筛选得到错误节点。临时探针传入 `conference_ids=['usenix']` 后仍得到两个 `venue='Generic'` 节点。

最小修复：对已支持会议先调用既有官方目录能力并保留来源 provenance，再用 S2 仅补缺；对 source/conference 进行服务端白名单与真实身份过滤，无法安全认证时返回 partial/可行动错误，不能静默忽略筛选。

### [P1] 跨地图没有元数据/引用持久缓存，重复创建会重复请求 S2

文件：`backend/app/literature_maps/infrastructure/store.py:179-185,332-342`、`backend/app/literature_maps/application/service.py:109-117,253-298`

问题：SQLite 只有 embedding cache，没有合同要求的元数据/引用 response cache；`run_job()` 每张地图都会重新 `search_bulk()`，`_collect_references()` 每张地图都会重新抓 references。相同主题/相同论文的两张地图临时探针产生 `search_requests=2`、`reference_requests=2`，数据库 cache 表只有 `literature_map_embedding_cache`。这会浪费请求额度并放大 1 RPS 下的等待/429，且不符合跨地图复用与 24h 成功缓存合同。

最小修复：增加带 provider/operation/identifier/query/filters/page/fields/schema 版本的参数化请求缓存，缓存成功元数据/引用及 provenance，失败/429 不写成空成功；普通打开只读缓存，明确 refresh/retry 才重新请求。

### [P1] 创建幂等检查与写入非原子，并发相同 key 可创建多张地图

文件：`backend/app/literature_maps/application/service.py:65-75`、`backend/app/literature_maps/infrastructure/store.py:171-177,201-212`

问题：服务先在事务外 `find_idempotent_map()`，再分别创建 map、job、绑定 idempotency；表约束是 `(map_id,idempotency_key)`，没有 owner+key 的唯一约束。临时探针强制两个请求同时越过查找后得到两个不同 `map_id`，库中有两张地图。该行为违反“所有命令幂等、同一 key 同参数只执行一次”。

最小修复：在单个 `BEGIN IMMEDIATE` 中以 `(owner_id,idempotency_key)` 唯一约束原子插入/读取 map+job+参数哈希；同 key 不同参数返回 409；不要把绑定拆成后置事务。

### [P1] retry 从 discover 重跑整张图，不是只重试失败/缺失单元

文件：`backend/app/literature_maps/application/service.py:208-219`

问题：`retry_job()` 无论失败原因都清空 `failed_units` 并强制 `step='discover'`；`run_job()` 随后再次 `search_bulk()`，并重新遍历已成功节点的引用。临时探针第一次运行 search 次数为 1，retry 后变为 2。该行为重复成功网络请求、可能重复触发限流，并违背合同中“retry 仅 failed/missing 单元、成功单元不重复抓取”。

最小修复：持久化每个发现/引用/相似单元的成功检查点；retry 只重排失败或缺失单元，恢复原 step/cursor；使用单条条件更新抢占 retry，避免同一 job 被重复入队。

### [P1] 终态作业仍可写，stop 可把完成地图改成 stopped

文件：`backend/app/literature_maps/infrastructure/store.py:402-405`、`backend/app/literature_maps/application/service.py:198-206`

问题：`job_can_write()` 只排除 `stopped`、`failed`，`completed` 仍返回可写；`stop_job()` 没有检查 job 是否仍为 queued/running，已完成 job 也会被改为 stopped，并把 map 状态覆盖为 stopped。临时探针确认 completed job 的 `can_write=True`，随后 `stop_job()` 成功将其改为 stopped。两个重试/恢复 worker 并发时还可能重复写节点/边和追加事件。

最小修复：用状态机/CAS 只允许 queued/running→终态、running→stopped；终态 stop 变为幂等 no-op 或稳定 409；worker 的每个写入都带 job 状态条件，completed/failed/stopped 绝不再写。

### [P1] 运行时 ValueError 会让 job 永久停在 running/generating

文件：`backend/app/literature_maps/application/service.py:158-173,325-330`

问题：`run_job()` 对 `ValueError` 直接重新抛出，只在地图已删除或 stopped 时静默返回。向量包含不可转 float 的值即可触发该分支；临时探针得到异常后 `job_after=running/similarity`、`map_after=generating`，没有 failed event，也不会自动恢复。类似的领域/响应数据 ValueError 也会卡住后台任务。

最小修复：将可预期的 provider/vector/store 输入错误映射为稳定 failed/partial 单元并持久化；只有已删除/已停止的资格撤销才静默退出；后台 worker 不得留下 running 无检查点的 job。

### [P1] 非有限向量被接受并把相似层误标为 completed

文件：`backend/app/literature_maps/application/service.py:318-331`、`backend/app/literature_maps/application/similarity.py:13-21,35-42`

问题：仅检查向量是非空 list/tuple 并 `float()`，没有 `math.isfinite()`；`cosine_similarity()` 对 NaN 返回 NaN，阈值判断静默为假，作业却把相似层标为 completed，且 NaN 可写入 embedding cache。临时探针以 `[nan, 1.0]` 返回向量后得到 `similarity.status=completed`、无错误。

最小修复：在写 cache 和计算前逐元素拒绝 NaN/±Inf、空范数和不一致维度，返回 `EMBEDDING_INVALID_RESPONSE`/`unavailable`；`cosine_similarity` 对非有限结果 fail-closed，不能把无效向量当作“0 条相似边”。

### [P1] 删除地图没有清除专属 job 行

文件：`backend/app/literature_maps/infrastructure/store.py:143-157,278-289`

问题：`delete_map()` 删除 events/edges/nodes/idempotencies，却没有删除 `literature_map_jobs`；由于 jobs 外键没有级联，删除后 job 行仍残留。临时探针确认删除地图后 `literature_map_jobs` 仍有 1 行。虽然 deleted_at 阻止当前 worker 复活地图，但这不符合合同“地图删除清除其专属作业”，长期会积累不可见垃圾并增加恢复/迁移歧义。

最小修复：在墓碑标记和 worker 资格撤销后事务内删除/归档该 map 的 jobs；删除期间保留明确 tombstone，确保晚回调只能得到资格失败而不能写回。

### [P1] 终态事件丢失实际 error_code

文件：`backend/app/literature_maps/application/service.py:245-251`、`backend/app/literature_maps/infrastructure/store.py:375-393,427-430`

问题：`_finish()` 把 failed units 写入 job，但调用 `update_job()` 时没有传 `error_code`；`MapEvent.error_code` 因而始终为 `None`。实际限流/引用截断/embedding 错误的最终事件无法给前端稳定可行动错误。临时限流探针的 final event 为 `('completed','partial',None,'finished')`，尽管 failed_units 有 `SEMANTIC_SCHOLAR_RATE_LIMITED`。

最小修复：终态事件传入首个稳定失败码（或固定聚合码），并在每个失败单元事件保留允许名单中的 code；禁止动态异常文本进入 payload。

### [P1] 多个只读/删除端点未把 store 异常映射为稳定 503

文件：`backend/app/api/routes_literature_maps.py:107-118,134-137,170-175,184-185`

问题：list、map detail、delete、job detail 以及 events 的第二次 `get_map()` 直接调用 store，没有 `try/except` 调用 `_error()`。临时将 store 置为抛出 `RuntimeError('db down')`，上述 GET 均返回裸 `500 Internal Server Error`，而冻结合同要求存储不可用返回结构化 503 `{detail:{code,message,retryable}}`。

最小修复：所有跨库调用都置于统一异常映射边界；正常 404/409 仍原样保留，意外异常统一 `MAP_STORAGE_UNAVAILABLE` 503，补充各端点的故障注入测试。

### [P1] 导入 URL 可被客户端覆盖且没有 SSRF/主机白名单校验

文件：`backend/app/api/routes_literature_maps.py:66-70,207-213`、`backend/app/literature_maps/application/service.py:233-243`

问题：请求可直接提供任意 `http/https` `source_url`；服务仅拒绝凭据和非 HTTP scheme，不拒绝回环/内网地址、不解析 DNS/绑定 peer、不限制允许 host 或重定向。临时注入 bridge 后，`http://127.0.0.1:9/internal` 被原样交给 importer。当前生产 bridge 为空使该风险暂未触发，但一旦按合同接入导入链将形成 SSRF 入口，也绕过既有论文导入接口的 server-side search snapshot/allowlist 设计。

最小修复：不要信任客户端 URL，优先使用服务端冻结候选；窄 bridge 复用既有 `validate_url`、allowed_hosts、DNS/peer、无任意重定向和下载链，拒绝 loopback/private/link-local/metadata 地址；必要时只接受既有候选句柄。

## 正向核对

- 身份归一化按 DOI→arXiv→Semantic Scholar，未把 S2 ID 写入 `catalog_paper_id`；同图 `UNIQUE(map_id, identity_key)` 保持稳定 node ID。
- SQLite 连接启用 WAL/外键，写事务使用 `BEGIN IMMEDIATE`；owner 查询大多带 owner/deleted 条件；revision 更新使用单事务条件检查；引用边方向实现为 citing→cited，相似边端点排序去重并禁止自环。
- 向量调用复用既有 `embed_texts` 入口，S2 调用复用既有 client/全局 limiter，未发现第二套 downloader、embedding 服务或限流器；图读取不隐式联网。
- `positions`、事件页、地图列表、references/provider 请求均有明确上限，首批结果会二次截断且不以无关论文凑满。

## 验证记录

| 命令/探针 | 结果 |
|---|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/literature_maps/test_map_identity.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_discovery.py tests/literature_maps/test_map_similarity.py tests/literature_maps/test_map_api.py` | 退出码 0；10 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 退出码 0；`test layout: ok` |
| `ruff check`（地图后端、路由、相关测试） | 退出码 1；6 项（import 排序、B905 strict、未使用 import） |
| 临时 SQLite/fake client/bridge 探针 | 复现筛选无效、缓存缺失、并发幂等重复、retry 重搜、NaN completed、删除 job 残留、ValueError 卡 running、终态 stop、裸 500、SSRF URL 直传 |

未执行全量 pytest、真实 Semantic Scholar/Ollama API、浏览器 smoke、部署或 commit；这些未验证项不能被本报告视为通过。

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| P0 | 0 | pass |
| P1 | 12 | block |
| P2 | 1 | warn（ruff） |
| LOW | 0 | pass |

Verdict: **BLOCK — 12 个 P1 后端合同/运行时缺陷必须在进入验收或部署前修复；10 条精准测试通过不构成后端门禁通过。**

## Store 层复核（2026-10-19；service/import 仍待）

本轮只复核 `infrastructure/store.py`、`test_map_store.py`、`test_map_job_store.py`、`test_map_identity.py` 以及 `store-fixes.md`；没有修改业务代码、生产库、环境或部署。结论不代表 Task03 整体通过：service/import/runtime/routes 仍需另一轮复核。

### 已验证通过的 store 修复

- 同一 owner + 同一 idempotency key 的并发 `create_map_with_job` 只有一个 `created=True`，两次返回同一 map/job；参数哈希不同稳定抛 `ValueError("idempotency conflict")`。
- request cache key 对 filters/fields 做稳定规范化；只有 `status="success"` 可写入；失败/429、过期缓存均不会被当成成功空响应复用。
- `claim_job` 是 queued→running CAS；`stop_job` 对 queued/running 生效、对 completed/failed/partial/stopped 幂等 no-op；`job_can_write` 和带 `job_id` 的节点/边写入拒绝 queued/terminal/stopped worker。
- checkpoint 可在新 store 实例中恢复，按 owner/map/job 隔离；节点导入回写按 owner/node 同事务约束；删除在事务内先墓碑后清理 jobs/checkpoints/events/nodes/edges/idempotency，删除后的迟回调不能重新写入。
- embedding 写入拒绝空向量、NaN/±Inf、空范数和维度漂移，读取也 fail-closed。

### [P1] `update_job` 仍可被迟到 worker 越过终态守卫

`update_job()` 先按 owner 读取 job，但最终 `UPDATE literature_map_jobs ... WHERE job_id=? AND map_id=?` 没有 `status='running'` 或 expected-state CAS；因此 queued/running 被 `stop_job()` 置为 stopped 后，迟到 worker 仍可调用 `update_job(status="completed")`，实际会把 job 改回 completed（本轮临时 SQLite 探针复现）。`set_map_status()` 同样是无 job 资格条件的自由写。service 的 `_finish()` 先检查再 `set_map_status`/`update_job`，存在 stop 与完成写交错时覆盖终态的窗口。

最小修复：将普通 progress/final `update_job` 限制为当前 running（或增加 expected status/job-generation CAS）；queued→running 只走 `claim_job`，failed/partial/stopped→queued 只走 `retry_job`，终态 stop 保持 no-op；service 终态写入必须使用同一守卫。补一条“claim→stop→迟到 finish”并发回归，确保 job/map 不会被复活。

### [P1] 旧库幂等重复数据会使新增唯一索引阻断启动

本轮新增 `idx_literature_map_idempotency_owner_key(owner_id,idempotency_key)` 时没有迁移/冲突处理。用本轮修复前允许产生的两个同 owner/key idempotency 行构造旧 SQLite 后，重新初始化直接失败：`UNIQUE constraint failed: literature_map_idempotencies.owner_id, literature_map_idempotencies.idempotency_key`。Spec 要求保留既有库并采用增量 schema；若此前并发缺陷已经留下重复行，服务重启会在 schema 初始化阶段不可用。

最小修复：新增唯一索引前执行可审计、确定性的 legacy 冲突迁移（保留 canonical idempotency 绑定、其余绑定明确标记/清理且不删除 map/job 数据），再建立唯一索引；或采用等价的向后兼容迁移策略，并增加含重复旧数据的启动测试。

### service agent 必须复用的 store API（签名以实现为准）

- `create_map_with_job(owner_id, *, topic, name, project_id, filters, requested_count, operation, idempotency_key, params_hash) -> (map, job, created)`；生产路径不得回退为 `create_map` + `create_job` + `bind_map_idempotency` 三段写入。
- `request_cache_key(...)`、`get_request_cache(key)`、`put_request_cache(key, payload, ttl_seconds=86400, status="success", ...)`；失败/429 不写成功缓存。
- `claim_job(job_id, map_id, owner_id)`、`retry_job(job_id, map_id, owner_id)`、`stop_job(job_id, map_id, owner_id)`；当前 `retry_job` 不接受 `step` 关键字，重排信息需另用受守卫的 job 更新接口。
- `save_unit_checkpoint(job_id, map_id, owner_id, *, unit_key, status, payload, error_code)`、`completed_units(job_id, map_id, owner_id)`；`add_nodes(..., job_id=job_id)`、`add_edges(..., job_id=job_id)`。
- `update_node_import_result(map_id, node_id, owner_id, import_result=...)`；`put_embedding(..., dimension=.../expected_dimension=...)`。

### 本轮精准验证

| 命令/探针 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_store.py tests/literature_maps/test_map_job_store.py tests/literature_maps/test_map_identity.py` | 退出码 0；12 passed |
| `.venv/bin/ruff check backend/app/literature_maps/infrastructure/store.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_job_store.py` | 退出码 0；All checks passed |
| 临时 SQLite 并发/缓存/终态/迟回调/checkpoint/import-owner/vector 探针 | 基础 store 修复全部 PASS；另复现“stop 后迟到 update_job 可改回 completed” |
| 旧库重复 owner/key 后重新初始化探针 | 复现新增唯一索引 `IntegrityError`，见上方 P1 |

**Store 层结论：基础修复项通过，但仍有 2 个 P1（终态更新 CAS、旧库唯一索引迁移）未闭环。其他 service/import/runtime/routes 缺陷仍待整体复审，当前不批准 Task03。**

## 整体冻结复审（2026-10-19；前端不在范围）

service/import 两批已冻结，本轮补读交接报告与实际代码；没有真实下载、生产数据库、环境、部署或全量回归。测试中的 fake callable 只作为 seam 证据，不等同生产导入或官方目录 E2E。

### 已核实的正向项

- 官方 scope 的默认适配器确实沿既有 `CatalogSearchAdapter` → `CatalogSearchGraph`/`CatalogRagAdapter`（非地图自建 crawler）查询；S2 venue 不再作为会议证明。服务层保留 scope 见证后才接受节点。
- map service 已接入原子创建、request cache、claim/checkpoint、job-qualified node/edge writes、向量有限性校验、retry 的持久节点恢复；删除/项目解绑和路由存储异常边界有对应精准覆盖。
- 既有 `import_candidate` 的 S2 OA fallback 在具备 DOI/arXiv、匹配身份且返回固定 allowlist 中 OA PDF 时可成功回到同一 importer；本轮临时探针验证了这一点。

### 仍存在的 P1 核心缺陷

#### [P1] 生产导入把 S2 landing/page 当成 PDF，且没有官方候选 PDF resolver

文件：`backend/app/literature_maps/application/runtime.py:16-39`、`backend/app/literature_maps/application/service.py:326-336`、`backend/app/literature_maps/application/catalog_adapter.py:44-60,123-162`、`backend/app/literature_maps/application/service.py:689-696`

`_existing_paper_import()` 无条件执行 `candidate["pdf_url"] = node.source_url`。而地图节点的 `source_url` 来自 `SemanticScholarMetadata.url`（通常是 `semanticscholar.org/paper/...` landing），不是 PDF；`download_candidate` 看到已存在的 `pdf_url` 后不会再解析 `source_page_url`。现有 fallback 只能在首次下载失败后按 DOI/arXiv 调 Semantic Scholar 的 `openAccessPdf.url`，没有从官方目录记录取得 `official_pdf_url`/prepublication URL，也没有复用 source-specific official/arXiv resolver。无 DOI/arXiv 或无 OA 的官方候选会落到 `DOWNLOAD_BLOCKED`，不能完成用户点击入库；本轮 runtime shape 与 no-OA 临时探针均复现该边界。

最小修复：让官方目录结果沿既有 candidate snapshot 保留 `catalog_paper_id`、官方页/PDF、arXiv/DOI identity 与来源类型；在进入 `import_candidate` 前只调用既有 source/DOI/OA resolver 得到可下载候选，并继续让 `import_candidate`/`download_candidate` 执行最终 allowlist、DNS/peer、redirect、PDF 校验。resolver 返回结果必须再次核对 DOI/arXiv 或标题/年份/作者，不能把 S2 landing 伪装成 PDF，也不能新建下载栈。

#### [P1] 官方目录 identity 在 adapter→node 边界丢失，无法可靠复用既有候选导入链

`CatalogRow` 只有 `metadata/source_id/conference_id`，`_existing_catalog_search()` 从已有目录查到 `catalog_paper_id` 后只取 S2 enrich 的 `SemanticScholarMetadata`；`_to_node()` 也没有传 `catalog_paper_id`。本轮 patched default seam probe 确认实际经过 `CatalogSearchAdapter.search`、catalog lookup、S2 enrich，但 `CatalogRow` 没有 catalog identity 字段，最终 map node 的 `catalog_paper_id` 为空。这样即使目录查询是真实官方路径，导入仍拿不到 `import_candidate` 所需 server-owned candidate ID/官方 URL，回到上一项的 S2 landing fallback。

最小修复：扩展内部 `CatalogRow`/metadata envelope 以携带 catalog ID、source kind、official page/PDF/arXiv/DOI provenance，并在 `_to_node()` 保持 `catalog_paper_id` 与 S2 `external_ids.semantic_scholar` 分离；导入只按该服务端快照取候选，不接受 HTTP URL override。

#### [P1] source/conference scope 没有“官方优先后聚合补缺”

文件：`backend/app/literature_maps/application/service.py:338-374`

只要存在 `source_ids` 或 `conference_ids`，`_discover_rows()` 就只返回目录 adapter 结果并结束；即使官方目录少于 requested limit，也不会调用通用 S2 进行未覆盖部分的补缺。临时 scope 适配器返回 1 个官方 row、requested limit=20 时，client 的 `search_bulk` 调用数为 0。官方优先方向正确，但“再聚合补缺”仍未实现，稀疏官方目录会产生不必要的 partial/漏项。

最小修复：保留已认证的官方 rows 及 provenance/identity，计算缺口后仅以缺口预算调用既有 S2 search/enrich；补入候选必须经过 identity 去重和 scope/年份过滤，不能以 S2 venue 反向证明会议成员。

#### [P1] importer 失败没有稳定 map import result/节点状态回写

文件：`backend/app/literature_maps/application/import_bridge.py:41-59`、`backend/app/api/routes_literature_maps.py:74-96,230-236`

桥接只对 importer 正常返回的 DTO 做 `_normalize_import_result` 后回写；`PaperDownloadError`/`PaperImportError` 等既有链路异常直接冒泡，桥接不会把固定 `error_code/status` 写入 node。路由 `_error()` 又把该异常归为泛化 `503/MAP_STORAGE_UNAVAILABLE`，丢失 `DOWNLOAD_BLOCKED`/`LOGIN_REQUIRED`/`KB_IMPORT_FAILED` 等稳定可行动码。本轮注入 `PaperDownloadError(DOWNLOAD_BLOCKED)` 的 route probe 得到 `503 MAP_STORAGE_UNAVAILABLE`，没有 map import failure 状态。

最小修复：在 bridge 边界捕获既有稳定 import/download 异常，投影为允许的 map import result 并通过 owner/map/node 事务回写（或由 route 映射固定导入错误后保证状态可查询）；禁止原始异常文本进入响应/事件，同时保留成功 DTO 的真实 document/paper handle。

### Store 层遗留 P1（仍有效）

- `update_job()` 没有 running/expected-state CAS，stop 后迟到 finish 可把 stopped job 改回 completed；`set_map_status()` 也无 job 资格守卫。
- 新增 `(owner_id,idempotency_key)` 唯一索引没有旧库重复数据迁移；本轮构造旧重复行后重新初始化复现 `sqlite3.IntegrityError`，升级已有数据库可能直接不可用。

### 精准验证与静态检查

| 命令/探针 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/literature_maps` | 退出码 0；36 passed |
| `.venv/bin/python -m pytest -q tests/conversation/test_conversations_api.py -k 'project'` | 退出码 0；2 passed，14 deselected |
| `.venv/bin/ruff check backend/app/literature_maps backend/app/api/routes_literature_maps.py backend/app/api/routes_conversations.py tests/literature_maps tests/conversation/test_conversations_api.py` | 退出码 1；仅 `tests/literature_maps/test_map_api.py:1` import 排序 `I001` |
| patched default catalog seam / sparse scope / runtime candidate / existing importer OA fallback / no-OA import route probes | 见上述结论；未下载真实论文、未调用真实 provider |

**整体复审结论：P0=0；仍有 6 个 P1 核心缺陷（4 个 import/catalog/service 边界、2 个 store 遗留）与 1 个 P2 静态检查。当前仍 BLOCK，不批准验收/部署；最小修复顺序为：官方 candidate identity+PDF resolver → import failure durable mapping → scope 补缺 → store terminal CAS/legacy migration。**

## 最终冻结复审（2026-10-19；仅 backend，前端不在范围）

本轮重新读取了 `store-fixes.md`、`service-fixes.md`、`import-api-fixes.md` 及实际冻结代码；没有修改业务代码/测试，没有生产下载、网络、部署、环境或全量回归。此前“整体冻结复审”中记录的 6 个 P1（store 终态 CAS、旧库幂等迁移、CatalogRow/官方 provenance、scope 补缺、导入 resolver、导入失败持久化）均以实际代码和精准测试核实为已闭环，不再重复计数。

### 已核实闭环

- `finish_job()` 在同一 `BEGIN IMMEDIATE` 内以 `running` CAS 更新 job、map 和终态 event；`stop/delete` 先获资格时迟到 finish 返回 `None`。普通 `update_job()` 默认 `expected_status="running"`，终态 worker 写入和 job-qualified node/edge 写入均被拒绝。
- 旧库 owner/key 重复绑定会在建唯一索引前确定性保留活动 canonical 绑定，写 migration log，并保留 map/job 数据；同 key 并发创建仍只有一个 map/job。request cache 仅成功写入，向量拒绝非有限、零范数和维度漂移。
- `CatalogRow`/node 已保留 `catalog_paper_id`、source kind、官方页/正式 PDF/prepublication PDF、DOI/arXiv 和脱敏 snapshot；scoped S2 结果只作已认证官方行的 fill-only 富化，未知行不会被 venue 误认入图；`_finish()` 已走原子终态接口。
- 生产 import bridge 只消费 server-owned snapshot，优先官方/prepublication PDF，缺失时调用既有 OA resolver；Semantic Scholar landing 不再作为 PDF，最终仍由既有 `import_candidate`/安全下载链做 allowlist、DNS/redirect/PDF 校验；已知 download/import 异常会持久化稳定失败或 waiting-login 状态并回写节点真实 document handle。

### 仍存在的 P1 核心缺陷

#### [P1] source/conference 组合会伪造 scope，且多选筛选静默只查第一项

文件：`backend/app/literature_maps/application/catalog_adapter.py:167-190`。

`_existing_catalog_search()` 把 `source_ids[0]` 或 conference 映射后的单个 source 传给既有 `CatalogSearchAdapter`，即使请求包含多个 source/conference 也只查第一项；随后直接把请求的 `conference_ids[0]` 写进每个返回 row，而不是核对被查出的 `CatalogPaper.conference_id`/source record。只读探针用真实 adapter 形状构造“目录纸是 `usenix-security`、请求 source=`usenix` + conference=`ccs`”，实际得到 `CatalogRow(source_id='usenix', conference_id='ccs')`；同时 SearchAdapter 收到的 sources 只有 `('usenix',)`。这会把官方 USENIX 行冒充 CCS，违背“官方目录身份见证”及数组筛选语义。

最小修复：把 source/conference 组合先做兼容校验；查询所有请求的 canonical source（或将完整 scope 传入既有 adapter），仅依据 catalog paper/source-record 的真实归属填写 row，缺失真实归属时拒绝而不是回填请求值。补 mixed-scope 与多选回归。

#### [P1] 未知 source/conference 的 HTTP 错误被错误归类为存储故障

文件：`backend/app/api/routes_literature_maps.py:74-96`。

service 已在创建前抛出 `UNSUPPORTED_SOURCE`/`UNSUPPORTED_CONFERENCE`，但 route `_error()` 没有把这两个固定输入错误列入 400 分支，实际 `POST /api/literature-maps` 传未知 source 或 conference 返回 `503 MAP_STORAGE_UNAVAILABLE`。这既误导用户，也使“unknown 不得创建/不得静默补入”无法成为可行动的 API 合同。

最小修复：将 `UNSUPPORTED_SOURCE`、`UNSUPPORTED_CONFERENCE` 映射为固定 400（或既有 422 输入错误包），保留 `CATALOG_SOURCE_UNAVAILABLE` 等运行时来源故障的 503/partial 语义，并补 HTTP 精准测试。

#### [P1] 导入 fallback 仍可仅凭标题把无 catalog identity 的 S2 节点绑定到目录论文

文件：`backend/app/literature_maps/application/paper_import_adapter.py:98-116`。

当节点没有 `catalog_paper_id` 且没有 DOI/arXiv 时，`_match()` 允许 normalized title 唯一匹配目录 paper；只读探针对无 DOI/arXiv 的 S2 节点返回了 `catalog_paper_id='cat'` 和官方 PDF。这违反 Spec 的确定身份边界（仅标题近似/标题本身不能自动合并），可能把通用 S2 结果错误导入到另一条官方目录记录。

最小修复：无 explicit catalog ID 时仅允许确定 DOI 或 arXiv 匹配；没有 deterministic external ID 就返回 `PDF_NOT_FOUND`/`IMPORT_IDENTITY_CONFLICT`，不要使用 title-only 目录回查。保留显式 catalog snapshot 的 server-owned identity 校验。

#### [P1] 60 次 S2 graph budget 只在单次 worker invocation 内生效，显式 retry 可无限超预算

文件：`backend/app/literature_maps/application/service.py:179-187,700-718`。

`_collect_references()` 每次调用都把 `request_count` 置零并以 `GRAPH_REQUEST_BUDGET=60` 重新计数；job 的累计 `provider_request_count` 只被展示/累加，未作为剩余预算门禁。用 20 节点、每次 references 返回可重试 429 的只读 client 探针得到：首次 job 21 次 provider request，三次显式 retry 后累计分别为 41、61、81，已超过合同“单作业最多 60 次 S2 逻辑请求”。

最小修复：把持久化累计 provider request count（或明确的 graph budget cursor）作为 `_collect_references()` 的剩余预算输入；达到总预算后持久化 `MAP_GRAPH_BUDGET_EXCEEDED`，retry 只允许未超预算的失败单元，超预算返回稳定冲突/partial，不因 retry 重置计数。

### 最终精准验证与门禁索引

| 命令/探针 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/literature_maps` | 退出码 0；52 passed |
| `.venv/bin/python -m pytest -q tests/conversation/test_conversations_api.py -k 'project'` | 退出码 0；2 passed，14 deselected |
| `.venv/bin/ruff check backend/app/literature_maps backend/app/api/routes_literature_maps.py backend/app/api/routes_conversations.py tests/literature_maps tests/conversation/test_conversations_api.py` | 退出码 0；All checks passed |
| `.venv/bin/python -m py_compile`（literature_maps 全部 Python、`routes_literature_maps.py`、`routes_conversations.py`） | 退出码 0 |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0；`test layout: ok` |
| 临时 SQLite / fake provider / patched catalog seam / import identity probes | 见上述 4 个 P1；未下载真实论文、未调用真实 provider |

**最终结论：P0=0；历史 6 个 P1 修复已闭环，但当前仍发现 4 个真实 P1（scope 真实归属/多选、unknown HTTP 映射、title-only import identity、跨 retry graph budget）。结论仍为 BLOCK，不批准验收或部署；先按上述最小修复补齐，再重新做一次整体冻结复审。**

## Task03 最后四项 P1 窄复审（2026-10-19；backend reviewer）

本轮仅复核上一节列出的四项 P1，按当前工作树实际代码和精准域测试判定；未修改 backend 业务代码或测试，未部署、未调用真实 provider、未读取密钥，也未运行 backend 全量回归。

### 四项复核结论：均已闭环

1. **source/conference 多选真实 scope：通过。** `compatible_scope_pairs()` 先生成兼容的 canonical source/conference 对；`CatalogSourceAdapter.search()` 对每一对调用既有 `CatalogSearchAdapter`，随后按目录 `CatalogPaper.conference_id` 与 `get_catalog_source_kinds()` 的真实记录过滤，`CatalogRow`/snapshot 使用实际归属，不回填请求数组的第一项。`test_default_catalog_adapter_queries_each_scope_and_uses_recorded_identity` 证明两对请求分别为 `("usenix",)`、`("ccs",)`，并得到对应目录身份；`test_multiple_scopes_use_actual_catalog_attestations_with_or_semantics` 证明服务层只接受两个实际 scope 的节点。
2. **`INVALID_MAP_SCOPE` HTTP 400：通过。** `routes_literature_maps._error()` 现将该服务端固定输入错误映射为 400、固定 error code/message、`retryable=false`；真实 `POST /api/literature-maps` 对未知 `source_ids` 和 `conference_ids` 均返回 400，未回显原始输入。覆盖测试为 `test_http_unknown_scope_from_real_service_is_fixed_400_without_raw_input`（两参数化例）。
3. **禁止 title-only 目录关联：通过。** `PaperImportSourceAdapter._match()` 仅按 normalized DOI 或 arXiv 唯一确定匹配；无 `catalog_paper_id`/deterministic external ID 的同标题节点返回 `PDF_NOT_FOUND`，不同 DOI 的同标题也不会绑定。`test_catalog_adapter_does_not_bind_same_title_without_deterministic_identity` 与 `test_catalog_adapter_rejects_same_title_with_different_doi` 均通过。
4. **每 job 60 次 graph 逻辑请求跨 retry 持久计数：通过。** `run_job()` 以持久化 `counts.provider_request_count` 计算剩余预算并传给 `_collect_references()`；重试不会将计数清零，达到 60 后不再发起 graph request，并记录 `MAP_GRAPH_BUDGET_EXCEEDED`。`test_reference_budget_is_persisted_across_retries` 验证 21 → 41 → 60、预算耗尽后调用数不再增长。

### 精准验证

| 命令/探针 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/literature_maps` | 退出码 0；62 passed |
| 四项窄回归：多 scope/目录归属、INVALID_MAP_SCOPE HTTP、title-only identity、跨 retry budget | 退出码 0；9 passed |
| `_error(ValueError("INVALID_MAP_SCOPE"))` 只读探针 | `400`；固定 `INVALID_MAP_SCOPE` detail，未泄露输入 |

**本轮结论：四项目标 P1 均已实际闭环，未发现新增 P1；就这四项可判 GO。** 这不是 Task03 整体验收或部署批准：此前报告中的其他范围、真实 API/provider E2E、全量回归及验收门禁仍由主会话继续处理。

## Import runtime 与 S2 relevance 最终集中复审（2026-10-19；backend-reviewer）

本轮按主会话通知，将已完成的 import runtime 修复与 `search_relevance` 修复一起复审。范围仅为实际 `backend/**` 代码、`tests/literature_maps` 及共享 Semantic Scholar 精准测试；未改业务代码或测试，未调用真实 provider/download、未读取 `.env`、未启动服务、未部署、未提交。

### 逐项结论

| 检查项 | 结论 | 实际证据 |
|---|---|---|
| arXiv fallback 优先与身份核对 | GO | `runtime.py:76-104` 仅在节点已有确定 arXiv identity 时调用既有 `ArxivFallbackAdapter`；返回值必须与节点 arXiv ID归一后完全相等才进入 importer；未命中/冲突后才按顺序走 S2。 |
| S2 fallback、DOI/arXiv identity 与 source page 区分 | GO | `runtime.py:106-124,136-149` 调既有 `SemanticScholarFallbackAdapter`，再次校验节点 identity；`paper_import_adapter.py`/`import_bridge.py` 不把 Semantic Scholar landing 当 PDF，桥接只接受服务端解析出的 `pdf_url`。 |
| allowlist 与唯一安全 importer | GO | runtime allowlist 来自 `common._paper_candidate_hosts()` 加注册表 `builtin_allowed_hosts("arxiv")`；最终调用链为 `LiteratureMapImportBridge` → `_existing_paper_import` → 既有 `import_candidate`，未新增 downloader/redirect 跟随/host 推导。桥接还拒绝凭据、fragment、localhost、保留/私网 IP 与 landing page。 |
| owner-scoped 持久化与稳定基础错误码 | GO | `import_bridge.py:112-123,172-204,271-286` 通过 `update_node_import_result(map,node,owner,...)` 回写 document/download 状态；异常投影为固定 `PDF_NOT_FOUND`/既有安全导入码，不把 raw exception 写入响应。 |
| resolver 诊断错误码可见/可持久化 | **BLOCK** | `runtime.py:127-133` 生成 `resolver_code`/`resolver_codes`，但 `import_bridge.py:67-70,271-286` 将其送入 `_failure_result()` 后，`_normalize_import_result()` 只保留 `error_code/status/retryable/...`（`172-204`），丢弃两字段；route 202 响应与节点持久状态因此仍只有 `PDF_NOT_FOUND`。只读探针复现：resolver 返回 `ARXIV_MATCH_UNCERTAIN` + `SEMANTIC_SCHOLAR_NO_OPEN_PDF`，返回/写回结果均无 resolver 诊断。 |
| unscoped relevance search | GO | `semantic_scholar_metadata.py:314-329` 新增 `/paper/search` relevance 方法，复用同一限流/retry/字段/错误映射；`service.py:508-546` 生产 GraphClient 优先调用该方法，缓存 operation 为 `search_relevance`，`_select_rows()` 对 unscoped 保留 provider 顺序并继续做身份/年份/主题门禁。 |
| scoped search 不受误改 | GO | `service.py:363-506` 的官方目录优先、多 scope 见证、gap 补缺和 fill-only 路径仍使用原 scoped 逻辑；`search_bulk` 仅用于 scoped gap。 |

### 阻塞项与最小修复

当前唯一新增阻塞是 resolver 诊断码在 bridge 边界丢失。应在固定 map import result 合同允许的安全字段中保留受控 `resolver_code`/`resolver_codes`（或将其映射为明确、稳定且不暴露 provider 原文的公开错误码），并由 `update_node_import_result`/API 结果以同一固定字段持久化和返回；不得保存动态异常文本或 provider envelope。补一条从 runtime resolver failure 到 bridge/store/HTTP 响应的端到端离线契约测试，证明 arXiv 未命中、S2 无 OA、S2 unavailable 可区分且不泄露凭据。

### 精准验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/pytest -q tests/literature_maps` | 0 | **68 passed**（未调用真实 provider/download） |
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/pytest -q tests/paper_discovery/test_semantic_scholar_graph_api.py tests/literature_maps/test_map_discovery.py` | 0 | **20 passed**；覆盖 `/paper/search` relevance 参数/顺序、旧 bulk endpoint、429/503 映射与地图缓存/选择顺序 |
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/pytest -q tests/paper_discovery/test_semantic_scholar_adapter.py tests/paper_discovery/test_semantic_scholar_import_fallback.py` | 0 | **9 passed**；共享 S2 OA allowlist/身份/既有 importer fallback |
| `.venv/bin/ruff check`（runtime、paper import adapter、bridge、service、metadata client 与上述精准测试） | 0 | All checks passed |
| `/opt/anaconda3/bin/python -m py_compile`（runtime、paper import adapter、bridge、service、metadata client） | 0 | 通过 |
| resolver failure 只读 bridge/store 探针 | 0 | 复现 resolver_code(s) 在持久结果/API 业务结果不可见；未触发网络/下载 |

**本轮逐项结论：import arXiv 优先、身份、allowlist、唯一 importer、基础稳定错误码均 GO；resolver 诊断错误码 BLOCK；S2 relevance endpoint、unscoped 顺序/缓存隔离、scoped 保持均 GO。总体 backend gate：BLOCK（1 个 P1，需修复后重新复审）。** 本报告不把 68+20+9 离线测试或既有失败 E2E 当作真实 API 成功；真实 HTTP 创建→完成/partial→graph→import 与部署仍由主会话按验收门禁执行。

## Resolver 诊断码真实 SQLite/HTTP 窄复审（2026-10-19；backend-reviewer）

本轮只复审上一节唯一 P1。未修改业务代码/测试，未调用真实 provider/download、未读取 `.env`、未部署或提交。重点是验证 bridge 白名单字段是否从 runtime 贯通到 HTTP，并且是否真正落入生产 `LiteratureMapStore` 的节点持久状态。

### 结果

| 层级 | 结论 | 实际证据 |
|---|---|---|
| runtime → bridge | GO | resolver 返回的 `resolver_code(s)` 进入 bridge；`_safe_resolver_codes()` 只保留固定 arXiv/Semantic Scholar 诊断码，未知 code、异常文本和 `raw_url` 均被过滤。主 `error_code=PDF_NOT_FOUND` 未被覆盖。 |
| bridge → HTTP 202 | GO | 使用真实 FastAPI route/service/bridge 组合与临时 SQLite，POST 导入返回 202，响应含 `resolver_code=SEMANTIC_SCHOLAR_NO_OPEN_PDF`、`resolver_codes=[ARXIV_UNAVAILABLE, SEMANTIC_SCHOLAR_NO_OPEN_PDF]`，不含 secret URL。 |
| bridge → 真实 SQLite 节点 | **BLOCK** | `LiteratureMapStore.update_node_import_result()` 只从 `import_result` 写 `document_id`、`download_status`、`catalog_paper_id`；`literature_map_nodes` schema 没有 resolver 字段，`MapPaper`/`_node()` 也没有 resolver 字段。真实 SQLite node GET 读回只有 `download_status=failed` 和 `error_code`未落盘（node API 本身也不返回 import resolver 诊断）。 |

真实 SQLite 临时探针（未触碰项目数据）得到：

- `PRAGMA table_info(literature_map_nodes)` 仅包含原有 18 列，无 `resolver_code`/`resolver_codes`；
- `update_node_import_result(..., import_result={error_code, resolver_code, resolver_codes})` 后，node 重读的 `to_dict()` 没有 resolver 字段；
- 同一真实 store 的 HTTP POST 202 响应有诊断码，但随后 GET `/nodes/{node_id}` 没有诊断码。

因此开发报告中“由 FakeStore 捕获完整 import_result”的测试只证明 bridge 调用参数，不等同真实持久化；本 P1 不能关闭。最小闭环方案是为地图节点增加版本化、owner-scoped 的受控诊断字段（显式列或纳入服务端 provenance，并同步 `MapPaper`、SQLite migration、`update_node_import_result()`、`_node()` 和 node GET），只写白名单 code，不写异常文本/provider envelope；同时保留 HTTP 202 当前主错误码兼容。

### 窄复审验证

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/pytest -q tests/literature_maps/test_map_import_bridge.py tests/literature_maps/test_map_api_errors.py` | 0 | **30 passed**；FakeStore/route 白名单和 HTTP 响应契约通过 |
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/pytest -q tests/literature_maps` | 0 | **71 passed**；仍不覆盖真实 resolver 字段 schema 持久化 |
| `.venv/bin/ruff check`（bridge/store/routes 与两份精准测试） | 0 | All checks passed |
| `/opt/anaconda3/bin/python -m py_compile`（bridge/store/routes） | 0 | 通过 |
| 真实 `LiteratureMapStore` 临时 SQLite + FastAPI TestClient | 0 | HTTP 202 有 resolver 诊断；节点 GET/SQLite schema 无 resolver 诊断，复现阻塞 |

**窄复审最终结论：白名单过滤与 HTTP 202：GO；真实 SQLite 节点持久化/重读可见性：BLOCK。总体 backend gate 仍 BLOCK（同一 P1 尚未闭环），不得据此进入验收收口或部署。**

## Resolver 诊断码真实持久化最终窄复审（2026-10-19；backend-reviewer）

本轮只复核上一节最后一个 P1 的修复，不扩大到其他地图能力，未修改 backend 业务代码/测试，未调用真实 provider 或下载，不读取 `.env`，未部署或提交。已直接读取当前 `import_bridge.py`、`store.py`、节点 API 与真实持久化回归；FakeStore 证据未被当作持久化证据。

### 逐项结论：最后 P1 已闭环

| 检查项 | 结论 | 实际证据 |
|---|---|---|
| runtime/bridge 白名单及主错误码兼容 | GO | `_safe_resolver_codes()` 只接受固定 arXiv/Semantic Scholar/OA 诊断码，未知 code、异常字段和 URL 不进入结果；`PDF_NOT_FOUND` 等主 `error_code` 保留。 |
| 真实 SQLite 失败写入 | GO | `LiteratureMapStore.update_node_import_result()` 在 owner/map/node 事务内把受控诊断写入既有 `provenance_json.import_diagnostics`，不需要 schema migration；真实 HTTP POST 202 后 node GET 的 `provenance` 可见。 |
| provenance 保留与重开可见性 | GO | 临时 SQLite 实例写入既有 `provider`/`keep`/catalog snapshot 后，POST→GET 和关闭/重开 `LiteratureMapStore` 均保留原 provenance 及诊断；未知 `provider_exception`/secret URL 未落库或回显。 |
| owner 守卫 | GO | 节点更新先以 `map_id + node_id + owner_id + deleted_at IS NULL` 查询；错误 owner 得到 `LookupError`，不能写入其他 owner 的节点。 |
| 成功重试清理旧诊断 | GO | `indexed`/`completed` 被解释为清理操作；HTTP 重试后 node GET 与再次重开的 store 均不含 `import_diagnostics`，同时保留其他 provenance 并写入 document handle。 |

### 精准验证

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/pytest -q tests/literature_maps/test_map_store.py tests/literature_maps/test_map_api_errors.py tests/literature_maps/test_map_import_bridge.py` | 0 | **39 passed** |
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/pytest -q tests/literature_maps` | 0 | **73 passed** |
| 三项真实持久化/owner/HTTP 回归（`test_http_import_round_trip_persists_diagnostics_in_sqlite_provenance`、`test_node_import_diagnostics_are_provenance_scoped_and_cleared_on_success`、`test_node_import_result_and_embedding_validation_are_scoped`） | 0 | **3 passed** |
| `.venv/bin/ruff check`（store、bridge、route 及相关精准测试） | 0 | All checks passed |
| `/opt/anaconda3/bin/python -m py_compile`（store、bridge、route） | 0 | 通过 |

以上真实持久化用的是临时 SQLite 文件和 FastAPI TestClient，验证了 POST→GET→重开 store→成功重试→再次重开的链路；没有把 mock provider 或 FakeStore 当成真实 E2E，也未证明外部 API/download 成功。

**最终集中结论：GO（最后 resolver 诊断持久化 P1 已闭环）。** 本结论仅关闭本项 backend 窄复审，不替代 Task03 的真实 provider/API E2E、全量回归、验收签字或部署门禁。

## 稳定 resolver 码白名单与 provider failure 最终窄复审（2026-10-19；backend-reviewer）

本轮只复核真实 E2E 暴露的稳定码白名单修复；未修改业务代码/测试，未部署、未下载、未调用真实 provider。重点是 domain 唯一白名单/normalizer 的输入过滤、provider operational failure 的主错误码与 retryable 语义，以及临时 SQLite 节点 GET/重开一致性。

### 逐项结论：GO

| 检查项 | 结论 | 实际证据 |
|---|---|---|
| 唯一白名单贯通 | GO | `domain/import_diagnostics.py` 是 resolver 诊断码唯一列表；runtime 用 `resolver_failure()`，bridge 用 `safe_resolver_codes()`，store 用 `normalize_import_diagnostics()`，不再各自维护副本。已覆盖 arXiv rate-limit/HTTP/invalid/unavailable 与 S2 rate-limit/unavailable/HTTP/invalid 等固定码。 |
| 任意输入不泄漏 | GO | resolver code 只按固定集合精确匹配；主 import error 只接受固定 `SAFE_IMPORT_ERROR_CODES` 或 resolver 集合；未知字符串、URL、provider exception、key 既不进入 HTTP 结果也不进入 `provenance.import_diagnostics`。独立临时 SQLite probe 以 secret URL 作为错误输入，结果只保留 `KB_IMPORT_FAILED`，持久化/重读均无 secret。 |
| provider unavailable 语义 | GO | `resolver_failure()` 将 provider operational code 作为主 `error_code`；`ARXIV_UNAVAILABLE`、`ARXIV_RATE_LIMITED`、`SEMANTIC_SCHOLAR_UNAVAILABLE`、`SEMANTIC_SCHOLAR_RATE_LIMITED` 保留可重试语义。只有 `NO_PDF_CANDIDATE_CODES`（例如 `SEMANTIC_SCHOLAR_NO_OPEN_PDF`）且没有 provider failure 时才归为 `PDF_NOT_FOUND`。 |
| SQLite GET 一致 | GO | provider failure 通过真实 `LiteratureMapStore` 写入既有 `provenance_json.import_diagnostics`；HTTP GET、重开 store 都能读到主错误码/resolver code/retryable，成功 `indexed` 重试继续清理旧诊断并保留其他 provenance/document。 |

### 精准验证

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/pytest -q tests/literature_maps/test_map_import_bridge.py tests/literature_maps/test_map_api_errors.py tests/literature_maps/test_map_store.py` | 0 | **50 passed** |
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/pytest -q tests/literature_maps` | 0 | **84 passed** |
| `.venv/bin/ruff check`（domain/runtime/bridge/store 与相关精准测试） | 0 | All checks passed |
| `/opt/anaconda3/bin/python -m py_compile`（domain/runtime/bridge/store） | 0 | 通过 |
| 独立 domain + 临时 SQLite probe（未知 secret code/URL、provider unavailable 与 `PDF_NOT_FOUND` 分流、重开 store） | 0 | `diagnostic whitelist/provider semantics/SQLite persistence: OK` |

本轮没有把 50/84 离线测试当作真实 provider 或下载成功；真实外部 API/download、服务重启后的 E2E 仍由主会话按验收门禁复核。

**最终集中结论：GO（稳定 resolver 码、provider failure 语义及 SQLite GET 接缝均闭环）。** 本结论仅关闭本次新增稳定码 P1 窄复审，不替代 Task03 整体验收/部署结论。

## arXiv identity-first fallback 最终窄复审（2026-10-19；backend-reviewer）

本轮仅复核新增 `lookup_by_id()`、arXiv ID normalizer 与 runtime identity-first 分支；未修改业务代码/测试，未发起真实请求、下载、部署或读取密钥。

### 逐项结论：GO

| 检查项 | 结论 | 实际证据 |
|---|---|---|
| exact ID 请求与安全复用 | GO | `ArxivFallbackAdapter.lookup_by_id()` 复用既有 client、限流/重试、Atom 解析及 `_arxiv_id()`/`_safe_pdf()`，请求只使用规范化 `id_list`；缓存 key 与旧 title lookup 分离，未新增 downloader 或 URL 拼接。 |
| ID normalizer 边界 | GO | `normalize_arxiv_id()` 接受新格式、旧格式和合法 version 后缀/可选 `arxiv:` 前缀；拒绝 HTTP(S) URL、query/injection、非法版本。`_arxiv_id()` 也经同一 normalizer，回传 identity 使用同一规范。 |
| metadata/回传 ID 冲突 | GO | exact feed 中回传 ID 不同或 exact ID 的标题/作者/年份门禁冲突时返回固定 `ARXIV_IDENTITY_CONFLICT`；安全 PDF 候选必须同时满足 exact ID、metadata 门禁和既有 host 校验。 |
| runtime 顺序与 S2 防绕过 | GO | 有合法 arXiv identity 时先调用 `lookup_by_id()`；无 identity 保留旧 title lookup。exact identity 冲突、无效 URL/injection identity 不会因 S2 成功而返回 PDF；exact 失败后的普通 provider miss 才按原顺序走 S2。 |
| 既有 title 调用链兼容 | GO | 无 arXiv identity 的 runtime 路径仍调用旧 `lookup(title, authors, year)`；USENIX publication-source 旧 title 回归保持通过。 |

### 精准验证

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/python -m pytest -q tests/paper_discovery/test_arxiv_adapter.py tests/literature_maps/test_map_import_bridge.py tests/literature_maps/test_map_api_errors.py tests/literature_maps/test_map_store.py` | 0 | **60 passed** |
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/python -m pytest -q tests/paper_discovery/test_usenix_publication_source.py` | 0 | **42 passed**，5 个既有 DeprecationWarning |
| `.venv/bin/ruff check`（adapter/runtime 与受影响精准测试） | 0 | All checks passed |
| `/opt/anaconda3/bin/python -m py_compile`（adapter/runtime） | 0 | 通过 |
| 独立 runtime probe（无效 arXiv URL identity + 成功 S2 mock） | 0 | 未触发 arXiv title 查询；S2 PDF 未绕过冲突，固定 `PDF_NOT_FOUND`/identity diagnostics |

未执行真实 arXiv/S2 请求或下载；本结论证明离线调用链和安全边界，不把生产 r3 的限流结果改判为无 OA，也不替代真实 API E2E。

**最终集中结论：GO（arXiv identity-first 修复及既有 title fallback 兼容通过）。** 本结论仅关闭本次 adapter/runtime 窄复审，不替代 Task03 整体验收或部署门禁。

## arXiv Atom scheme/version 兼容最终窄复审（2026-10-19；backend-reviewer）

本轮只复核最新 Atom 兼容改动及其身份安全边界，未修改业务代码或测试，未发起真实 provider 请求、下载、部署，也未读取密钥。既有上一轮 identity-first 的 GO 不能覆盖本轮发现；本段以当前实际代码和独立探针为准。

### 逐项结论

| 检查项 | 结论 | 实际证据 |
|---|---|---|
| Atom entry scheme 与 canonical source URL | GO | arxiv_adapter.py:65-76 的 _arxiv_id() 仅接受固定 arxiv.org/export.arxiv.org host、无凭据/端口/query/fragment 的 HTTP(S) /abs/；ArxivMatch.source_page_url 仍固定输出 HTTPS。最新 fixture 覆盖 http://arxiv.org/abs/1710.10903v3 与 HTTPS PDF，title/author/year 解析一致。 |
| bare ID 与 returned latest version | GO | arxiv_identity_matches() 对无版本 expected 允许同 base 的 returned vN，显式 vN 仍精确匹配；URL、非法版本和注入文本先被 normalize_arxiv_id() 拒绝。runtime exact-ID gate 与 S2 candidate gate 已复用该 helper。 |
| exact returned ID 的 metadata conflict 固定码 | BLOCK | arxiv_adapter.py:272-274 在 title/author/year 门禁失败时仍使用原始 arxiv_id == expected_arxiv_id。当 expected 为 bare 2501.00001、Atom 返回合法 2501.00001v3 但 metadata 冲突时，helper 判定身份相同，却因裸字符串不等而不置 metadata_conflict，结果为 ARXIV_MATCH_UNCERTAIN，不是契约要求的 ARXIV_IDENTITY_CONFLICT。 |
| identity conflict 不被 S2 成功覆盖 | BLOCK | runtime 只有收到 ARXIV_IDENTITY_CONFLICT 才设置 arxiv_identity_conflict（runtime.py:125-150）。上述 bare→latest metadata-conflict 返回 ARXIV_MATCH_UNCERTAIN 后，成功的 S2 mock 会被返回，实际结果含 semantic_scholar_id 和 PDF URL；因此该冲突可绕过。 |
| safe PDF 边界 | GO | 本轮 diff 未放宽 _safe_pdf()；PDF 仍要求 HTTPS、固定 arXiv host、无凭据/端口/query/fragment 且 /pdf/ 路径。 |

### 独立窄探针

以下探针使用本地 Atom fixture 与 mock transport，不访问外部网络：

1. HTTP Atom entry http://arxiv.org/abs/2501.00001v3，expected bare ID 2501.00001，故意提供冲突 title/author/year；lookup_by_id() 返回 ARXIV_MATCH_UNCERTAIN。探针期望 ARXIV_IDENTITY_CONFLICT，退出码 1。
2. runtime 注入同一 ARXIV_MATCH_UNCERTAIN，再注入匹配 arXiv ID 的成功 S2 PDF；_existing_oa_resolver() 实际返回 S2 PDF，探针期望无 PDF/identity failure，退出码 1。

最小修复边界：arxiv_adapter.py:273 应改为使用 arxiv_identity_matches(expected_arxiv_id, arxiv_id)，并补一条 bare expected + returned vN metadata-conflict 测试及 runtime S2-success 不绕过测试；不需要改变 _safe_pdf() 或扩大 importer。

### 精准验证

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/python -m pytest -q tests/paper_discovery/test_arxiv_adapter.py tests/literature_maps/test_map_import_bridge.py tests/literature_maps/test_map_api_errors.py tests/literature_maps/test_map_store.py | 0 | 63 passed |
| PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/python -m pytest -q tests/paper_discovery/test_usenix_publication_source.py | 0 | 42 passed，5 个既有 DeprecationWarning |
| .venv/bin/ruff check（adapter/runtime 与受影响精准测试） | 0 | All checks passed |
| /opt/anaconda3/bin/python -m py_compile（adapter/runtime） | 0 | 通过 |
| bare→latest metadata conflict adapter probe | 1 | 当前返回 ARXIV_MATCH_UNCERTAIN，未固定为 ARXIV_IDENTITY_CONFLICT |
| runtime metadata conflict + successful S2 probe | 1 | 当前错误返回 S2 PDF，identity conflict 可被绕过 |

**最终集中结论：BLOCK（Atom HTTP scheme、canonical URL、bare/version normalizer 及 safe PDF 边界为 GO；但 bare expected → returned latest version 的 metadata conflict 未固定为 ARXIV_IDENTITY_CONFLICT，且可被成功 S2 fallback 覆盖）。** 在开发补齐 helper 比较和两条回归前，不得关闭本 P1 或宣称该窄项整体通过。本结论不扩大到其他已通过项，也不替代 Task03 整体验收/部署门禁。

## arXiv bare/latest metadata conflict 修复最终窄复审（2026-10-19；backend-reviewer）

本轮仅复核上一轮 BLOCK 的两处修复：adapter metadata conflict 使用共享身份 helper，以及 runtime 在成功 S2 返回时仍拒绝 arXiv identity conflict。未修改代码或测试，未调用真实 provider、下载、部署或读取密钥。

### 逐项结论：GO

| 检查项 | 结论 | 实际证据 |
|---|---|---|
| adapter bare→latest metadata conflict | GO | arxiv_adapter.py:273 现在使用 arxiv_identity_matches(expected_arxiv_id, arxiv_id)。expected 2501.00001 与 Atom 返回 2501.00001v3 且 title/author/year 冲突时，实际返回 ARXIV_IDENTITY_CONFLICT。 |
| runtime S2 不绕过 | GO | runtime.py:125-153 保留 ARXIV_IDENTITY_CONFLICT 状态；即使 S2 mock 返回匹配 arXiv identity 的 PDF，实际结果无 pdf_url，主 error_code 为 PDF_NOT_FOUND，resolver_codes 仅保留 ARXIV_IDENTITY_CONFLICT。 |
| 相关分支回归 | GO | 新增 adapter bare/latest metadata-conflict 测试，并保留 runtime 成功 S2 不静默接受测试；当前交接报告记录 64 passed。 |

### 两条独立 probe

| probe | 退出码 | 实际结果 |
|---|---:|---|
| 本地 Atom fixture：HTTP abs entry 返回 2501.00001v3，expected bare 2501.00001，metadata 冲突 | 0 | adapter_code=ARXIV_IDENTITY_CONFLICT |
| runtime 注入 arXiv ARXIV_IDENTITY_CONFLICT，再注入成功匹配 S2 PDF | 0 | 无 pdf_url；error_code=PDF_NOT_FOUND；resolver_codes=[ARXIV_IDENTITY_CONFLICT] |

本轮只证明上述 P1 的离线身份/回退组合已闭环；未把 mock probe 当作真实 provider/API E2E。

**最终集中结论：GO（bare/latest metadata conflict 已固定为 ARXIV_IDENTITY_CONFLICT，成功 S2 不再绕过）。** 本结论仅关闭上一轮该窄缺陷，不替代 Task03 整体验收、真实 API E2E、全量回归、验收签字或部署门禁。

## arXiv identity contract runtime→adapter→bridge→importer 窄复审（2026-10-19；backend-reviewer）

本轮只复核桥接层版本比较修复及身份合同沿生产组合链的一致性，未修改代码或测试，未发起真实 provider 请求、下载、部署或读取密钥。

### 逐项结论：GO

| 检查项 | 结论 | 实际证据 |
|---|---|---|
| runtime→adapter→bridge→importer bare→latest | GO | 生产组合测试 test_runtime_source_adapter_bridge_accepts_latest_arxiv_identity_without_download 通过：节点 expected 1710.10903，Atom mock 返回 1710.10903v3，runtime→PaperImportSourceAdapter→LiteratureMapImportBridge 最终把安全 PDF 交给注入的既有 importer，S2 未被调用。 |
| bridge identity conflict expected-left | GO | import_bridge.py:256-259 使用 arxiv_identity_matches(external_arxiv, arxiv)，节点 external ID 在左；bare expected 可接受 returned vN，显式版本不同和跨 base 均拒绝。 |
| source adapter catalog matching | GO | paper_import_adapter.py:112-123 的 _match() 和 :160-167 的 _matching_external_id() 均以节点 expected ID 为左侧并复用同一 helper；不再存在 raw-string version 比较。 |
| DOI conflict 不可绕过 | GO | catalog source 即使 arXiv base 匹配而 DOI 不同，bridge :252-259 仍返回 IMPORT_IDENTITY_CONFLICT，不调用 importer；不同 DOI 且无可证明身份时 adapter 返回 PDF_NOT_FOUND。 |

### 组合与负向验证

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| 受影响地图/import/adapter 精准 pytest | 0 | **66 passed** |
| 显式版本不同、runtime→bridge latest 组合、跨 base、S2 冲突、catalog DOI 冲突等 6 项精准测试 | 0 | **6 passed** |
| 真实生产组合离线 probe：explicit version mismatch / cross-base / DOI conflict with matching arXiv | 0 | 三种情形均未调用 importer；前两者为 PDF_NOT_FOUND，DOI 冲突为 IMPORT_IDENTITY_CONFLICT |
| git diff --check（本报告与日志） | 0 | 通过 |

本轮证明的是本地真实对象组合与身份/导入门禁，不把 mock provider 或离线 importer 当作真实 API、下载或持久化成功。

**最终集中结论：GO（arXiv base/version identity contract 已从 runtime 经 adapter、source adapter、bridge 一致贯通；显式版本不同、跨 base 与 DOI 冲突均不可绕过）。** 本结论仅关闭本次 r5 桥接身份 P1，不替代 Task03 整体验收、真实 API E2E、全量回归或部署门禁。
