# 复用审计与 schema 设计复核：Spec015 Task13 子任务A

- 角色：tech-lead ｜ 模型：qwen3.8:27b-mlx ｜ 时间：2026-09-05
- 分支/检查点：`feature/spec-015-security-paper-discovery` @ `c17c7f4`（未提交工作树）
- 性质：**只读代码审查**，未修改任何代码/配置；未触碰 Spec017；无网络请求；无 git 写操作。
- 规范来源：`docs/sdd/specs/015-security-paper-discovery.md`「现有实现复用与替换边界」「SQLite schema v2」；`docs/sdd/plans/015/task-13-catalog-contract-and-reuse-audit.md`
- 关联日志：`.codebuddy/agent-logs/tech-lead-spec015-task13-20260905-090646.md`

## 结论：通过（附意见，含 1 项阻塞与 5 项强制约束）

本审计逐项核对 spec 第 54–91 行复用边界与第 279–293 行 schema v2，并对照 11 个现有模块、5 个测试文件的真实代码。结论：**未发现第二套下载/安全/导入/批任务/身份/embedding 实现**，旧能力均可复用或参数化后复用；schema v2 字段/枚举/约束/外键/UTC 时间**设计自洽、无未决设计问题**。但发现 1 项**阻塞**与 5 项**强制约束**，须在子任务B/C 编码前落实。

## 一、逐文件复用审计表

格式：模块（路径）｜可复用公开符号｜调用者｜现有测试｜处理结论｜禁止重复实现项

### 1. `backend/app/services/paper_download.py`（原样复用）
- 可复用符号：`PaperDownloadError`、`DownloadResult`、`download_candidate`、`_check_peer`、`_validate_pages`、`_timeouts`（重定向/大小/魔数/页数/临时文件/校验和 + DNS rebinding 复核）。
- 调用者：`paper_import.py`（`from ...paper_download import ...`）；`api/routes.py` 间接经 paper_import 使用。
- 现有测试：`tests/test_paper_download.py`（193 行，12 用例）。
- 处理结论：**原样复用**。仅在用户选择导入后调用；搜索/目录同步阶段禁止调用。
- 禁止重复实现：不得新建旁路下载器；搜索/目录同步阶段不得 HEAD/GET 探测 PDF。

### 2. `backend/app/services/paper_download_security.py`（原样复用）
- 可复用符号：`URLSecurityError`、`ValidatedURL`、`validate_url`、`validate_redirect_target`、`validate_redirect_chain`、`validate_peer_ip`、`_public_addresses`（HTTPS/443/allowlist/公共IP/混淆host 校验）。
- 调用者：`paper_browser_manager.py`（`_validate_download_url`→`ValidatedURL`）；`paper_download.py` 间接。
- 现有测试：`tests/test_paper_download_security.py`（116 行，10 用例）。
- 处理结论：**原样复用**。USENIX 页面、PDF 与所有跳转继续经同一安全策略（spec 下载资源与 SSRF 固定上限第 295–298 行）。
- 禁止重复实现：不得弱化 HTTPS、origin、端口、公共 IP 或逐跳校验；不得新建第二套 SSRF 校验。

### 3. `backend/app/services/paper_import.py`（原样复用入口，导入 saga 不变）
- 可复用符号：`PaperImportError`、`PaperImportResult`、`import_candidate`、`safe_import_error_code/message`、`_find_existing`、`_default_indexer`、`_cleanup_*`（导入 saga + 补偿点）。
- 调用者：`api/routes.py`（`from ...paper_import import ...`）。
- 现有测试：`tests/test_paper_import.py`（183 行，8 用例）；批次侧 `test_paper_import_batch_service/store`。
- 处理结论：**原样复用**，作为 v1 同步索引链路。新异步索引（v2）仅追加事件，不撤销 v1 已可检索论文（spec 第 270、308 行）。
- 禁止重复实现：不得建立第二套 PDF 入库流程；不得让客户端提交任意 PDF URL，须从冻结搜索结果解析服务端目录论文标识后进入现有 saga。

### 4. `paper_import_batch_service.py` / `paper_import_batch_store.py` / `domain/paper_import_batch.py`（原样复用，禁止迁移语义）
- 可复用符号：`PaperImportBatchService`（`create_batch`/`process_item`/`run_batch`/`retry_*`/`resume_item`/`cancel_*`/`recover_expired_leases`/`get_status`）；`PaperImportBatchStore`（`claim_item`/`resume_item`/`renew_lease`/`transition_item`/`_write_transaction`/`_init_schema`/`_validate_schema_contract`）。
- 调用者：`api/routes.py`（`PaperImportBatchService`/`PaperImportBatchStore`/`BrowserManagerError`）。
- 现有测试：`test_paper_import_batch_service.py`、`test_paper_import_batch_store.py`（292 行，14 用例）。
- 处理结论：**原样复用**状态机/CAS/租约/重试/恢复/幂等/逐项隔离。
- 禁止重复实现：检索任务必须使用 `search_jobs` 独立状态表，**不得复用导入任务语义或迁移状态机**；不得把导入 CAS/租约逻辑复制到 search 任务。

### 5. `paper_import_identity.py` / `paper_discovery_normalization.py`（原样复用）
- 可复用符号：`PaperImportIdentity`、`build_paper_identity`、`paper_identity_keys`、`deduplicate_candidates`、`build_paper_filename`、`unique_paper_filename`、`filename_for_candidate`、`canonical_doi`、`canonical_dblp_key`；`normalize_doi`、`normalize_title`。
- 调用者：`paper_import.py`、`acm_paper_parser.py`（`canonical_doi`）、`dblp_publication_source.py`/`paper_discovery_store.py`（`normalize_*`）。
- 现有测试：`test_paper_import_identity.py`、`test_acm_paper_parser.py`、`test_ieee_paper_parser.py`。
- 处理结论：**原样复用** DOI/标题/作者/年份/会议/规范文件名规则。新增目录 ID 只能扩展 `PaperImportIdentity`，不得绕过。
- 禁止重复实现：不得用来源 URL 或用户输入直接作为文件名/唯一身份；不得新建第二套身份/命名规范化。

### 6. `usenix_paper_parser.py`（参数化扩展后复用）
- 可复用符号：`UsenixPaperParseError`、`UsenixAcceptedPaper`、`parse_accepted_listing`、`parse_usenix_detail`、`UsenixAcceptedParser`、`_Page`/`_safe_url`/`_page`（同源 URL、显式链接、可注入 fixture 解析边界）。
- 调用者：`usenix_publication_source.py`。
- 现有测试：`tests/test_usenix_paper_parser.py`（85 行，5 用例，含可注入 fixture）。
- 处理结论：**参数化扩展后复用**。保留同源 URL/显式链接/可注入 fixture 边界；扩展列表论文块、详情摘要、官方关键词、cycle/summer/fall 多种页面结构。
- 禁止重复实现：不得新建第二套 HTML 解析器；不得移除可注入 fixture 解析边界。

### 7. `usenix_publication_source.py`（参数化/部分替换后复用）
- 可复用符号：`UsenixAcceptedResult`、`UsenixAcceptedSource`（受控 `httpx.Client`、节流 `_before_request`/`_rate_limit`、安全校验、稳定错误、`_route`/`_listing_url`）。
- 调用者：`api/routes.py`（经 `PaperDiscoverySearchService`）。
- 现有测试：经 `test_paper_discovery_search.py`/`test_paper_discovery_api.py` 间接覆盖。
- 处理结论：**参数化/部分替换后复用**。保留受控 HTTP 客户端、节流、安全校验、稳定错误；改为按来源抓取单元同步全量元数据。
- 必须替换的旧路径：移除进程内字典缓存（`_cached`/`_client` 的权威缓存）与 `_get_pdf`/`_preferred_pdf` 的检索阶段 PDF 探测；移除由单个 `cycle{n}` 模板决定所有年度页面的方式。
- 禁止重复实现：不得新建第二套 HTTP 客户端/节流/安全校验。

### 8. `dblp_publication_source.py`（参数化后复用）
- 可复用符号：`filter_main_conference_records`（主会过滤，按 `dblp_stream`/`venue_aliases`/`year`/type 严格校验）、`deduplicate_publications`（DOI/DBLP key/title+year+conference 去重）、`DBLPPublicationResult`、`DBLPPublicationSource`（`search`/`_request`/`_extract_hits`，timeout/retries/backoff 稳定错误）。
- 调用者：`api/routes.py`（`DBLPPublicationSource`）；`dblp_publication_source.py` 自身导入 `normalize_doi/normalize_title`。
- 现有测试：经 `test_paper_discovery_search.py` 间接覆盖。
- 处理结论：**参数化后复用**。保留 stream/year、主会过滤、重试、稳定错误、去重；新流程中只补 DOI/DBLP key 等缺失书目信息。
- 禁止重复实现：DBLP 绝不覆盖 USENIX 官方标题/作者/摘要/关键词；不得新建第二套 DBLP 客户端。

### 9. `paper_discovery_store.py`（参数化扩展后复用，重点）
- 可复用符号：`SCHEMA_VERSION`、`PaperDiscoveryStore`（`_connect` 设 `PRAGMA journal_mode=WAL/foreign_keys=ON/busy_timeout=5000`、显式事务、`_validate_schema_meta`、`_migrate_source_fields`(ALTER 兼容式)、`_migrate_global_candidate_key`、`_normalize_persisted_titles`、`_seed`、`save_conference`/`save_search`/`get_*`)。
- 调用者：`api/routes.py`（`PaperDiscoveryStore`）。
- 现有测试：`tests/test_paper_discovery_store.py`（**仅 55 行 / 5 用例，覆盖薄弱**）。
- 处理结论：**参数化扩展后复用**。保留 WAL/外键/busy_timeout/显式事务/schema_meta 迁移框架与 `_migrate_*` ALTER 兼容式风格；升级为全局目录/抓取单元/搜索任务/来源进度/事件/冻结结果模型。
- 禁止重复实现：不得新建数据库连接层；不得删除/重命名 v1 表；不得改导入表语义。

### 10. `paper_discovery_search.py`（参数化扩展后复用）
- 可复用符号：`PaperDiscoverySearchError`、`SearchResult`、`PaperDiscoverySearchService`（`search`/`_validate`/`_sort_key`/`_merge_candidate`/`_strong_identity_conflict`/`_metadata_richness`/`_identity_keys`，输入校验/来源告警/规范化/合并/稳定排序）。
- 调用者：`api/routes.py`。
- 现有测试：`tests/test_paper_discovery_search.py`、`tests/test_paper_discovery_api.py`。
- 处理结论：**参数化扩展后复用**。保留输入校验/来源告警/规范化/合并/稳定排序思想；同步编排改为 LangGraph 异步工作流。
- 禁止重复实现：不得新建第二套搜索编排/合并/排序逻辑。

### 11. `services/kb/{embed,index,retrieve}.py`（参数化后复用）
- 可复用符号：`embed_texts`/`encode_sparse`/`EmbeddingError`（BGE-M3 dense+sparse）、`index_paper_chunker`/`delete_paper_chunker`/`get_client`/`ensure_collection`（Qdrant 初始化）、`hybrid_search`/`rrf_fuse`/`reranker_available`/`reranker_health`（RRF + 可选 reranker）。
- 调用者：`paper_import.py`（index/delete chunker）、`api/routes.py`（embed_texts/reranker_health）、`kb/__init__.py` 统一出口。
- 现有测试：`tests/test_kb_services.py`（**686 行 / 75 用例，覆盖充分**）。
- 处理结论：**参数化后复用**。把 collection、payload 映射、过滤器参数化；论文发现目录使用独立 collection。
- 禁止重复实现：不得新建第二套 embedding/索引/检索/RRF/reranker；不得把论文发现目录混入个人 PDF 分块 collection。

### 附：`paper_browser_manager.py`（原样复用，与检索正交）
- 可复用符号：`PaperBrowserManager`/`BrowserSession`（`authenticated_pdf_request`/`validate_origin`/`open_session`/`session`、`_ProfileLock` 单 profile 文件锁、`_validate_download_url`→`ValidatedURL`）。
- 调用者：`api/routes.py`。
- 处理结论：**原样复用**，仅用于 ACM/IEEE 等合法登录下载与既有导入等待流程。
- 禁止重复实现：公开 USENIX 元数据同步与检索不得要求登录或读取浏览器凭证。

## 二、SQLite schema v2 设计复核（spec 第 279–293 行）

### 迁移框架现状（来自 `paper_discovery_store.py` 实读）
- 现状 `SCHEMA_VERSION = 1`；`schema_meta(version INTEGER NOT NULL)` + 单行 `UNIQUE INDEX ON schema_meta((1))` 防多行；`_connect` 固定 `WAL/foreign_keys=ON/busy_timeout=5000`；迁移采用 `_migrate_source_fields` 的 `ALTER TABLE ADD COLUMN` 兼容式。
- **关键设计要点（须落实）**：`_validate_schema_meta` 现有严格分支 `if row[0] != SCHEMA_VERSION: raise "Unsupported ... version"`。v1→v2 升级**不能**简单把 `SCHEMA_VERSION` 改 2 后直接启动旧库——会触发版本不匹配拒绝。迁移必须由显式迁移函数在事务内 `ALTER`/`CREATE` 新表，迁移完成后才把 `schema_meta` 升为 2，且保证幂等（重复执行不报错）。此为子任务B 必须解决点。
- 修正表述：实读第 101 行为 `if row[1] != "integer" or row[0] != SCHEMA_VERSION: raise`，即版本不匹配即拒绝；迁移须先迁移后升版本号，且幂等。

### 七张新表设计自洽性（逐表）
- `source_fetch_units`：字段含 status 枚举(pending/fetching/completed/partial/failed)、`lease_owner`/`lease_expires_at`/`last_attempt_at`/`last_success_at`、`etag`/`last_modified`/`content_hash`；唯一 `(source_kind,conference_id,year,unit_key)`。✓ 自洽，租约字段齐备可支撑原子领取与恢复。
- `catalog_papers`：含 `metadata_hash`、`index_status(pending/indexed/failed)`、`index_version`、可空唯一身份(DOI 与 规范标题+作者+年份+会议)。✓ 与设计一致。
- `catalog_source_records`：唯一 `(source_kind,source_key)`，外键删除 `RESTRICT`（保留来源证据）。✓。
- `search_jobs`：status(queued/running/completed/partial/failed)、`graph_version`/`degraded`/`total_results`/`expires_at`。✓。
- `search_source_progress`：主键 `(search_id,source_kind)`，source_kind(usenix/dblp)，status(queued/checking_cache/fetching/merging/completed/cached/failed)。✓ 联合主键合理。
- `search_events`：单调 `event_id`、`safe_payload_json`（仅预定义字段+脱敏）。✓。
- `search_results`：唯一 `(search_id,catalog_paper_id)` 与 `(search_id,rank)`，冻结后不可更新。✓ 双唯一约束支撑 10 条固定分页。

### 时间/哈希/外键行为
- UTC：spec 第 274、293 行要求 RFC3339 UTC 含 `Z`；store `_utcnow()` 已产 UTC，新表沿用。✓
- `metadata_hash`：哈希不变→不更新 `updated_at`/不重复 embedding；变化→先写目录置 `index_status=pending`，索引成功后条件更新 `indexed`。✓ 自洽。
- 外键：`catalog_source_records.catalog_paper_id` RESTRICT；`search_results.search_id`/`catalog_paper_id` 应引用 `search_jobs`/`catalog_papers`（建议 ON DELETE 行为在实现中显式声明，见强制约束）。

### 设计复核结论
七张表字段、状态枚举、唯一约束、外键、UTC 时间与 `metadata_hash` 行为**设计自洽、无未决设计问题**。
- 外键 ON DELETE 行为：`catalog_source_records → catalog_papers` 已写明 `RESTRICT`（spec 第 287 行）；导入对搜索/候选为 RESTRICT/保留快照（spec 第 270 行）。据此推断 `search_results`/`catalog_source_records` 引用搜索与目录时应统一 `RESTRICT`/保留快照，与"冻结不可改写、来源证据保留、导入引用不删"语义一致，**非未决设计问题**；仅需在 schema 实现文档显式声明为 `RESTRICT`（见强制约束 C-3），不得猜测为 CASCADE。

## 三、明确缺口（实现层 TODO，非设计缺陷）
- G-1（高）：`services/kb/{index,retrieve}.py` 的 `KB_COLLECTION` 为**全局硬编码常量**（来自 `core.config`），`ensure_collection`/`hybrid_search` 未接受 collection 参数。spec 第 76 行要求"collection/payload/过滤器参数化，论文发现目录使用独立 collection"。**须参数化**，不得新建第二套 Qdrant 客户端。
- G-2（高）：`paper_discovery_store.py` 测试仅 5 用例/55 行，覆盖薄弱；v2 七表与并发领取/租约恢复/冻结不可改写需子任务C 大补。
- G-3（中）：`usenix_publication_source.py` 的 `_cached`/`_client` 进程内权威缓存与 `_get_pdf`/`_preferred_pdf` PDF 探测为待替换旧路径，须随抓取单元重构移除。
- G-4（中）：`_validate_schema_meta` 严格版本校验要求 v1→v2 迁移必须"先迁移后升版本号"且幂等，子任务B 须显式实现迁移事务与回滚。

## 四、强制约束（实现必须遵守）
- C-1：v1→v2 迁移在单一显式事务内执行，完成后才把 `schema_meta` 升为 2；重复执行幂等；任何失败整体回滚，不留半张表；禁止手工删表补救。
- C-2：检索任务状态机使用 `search_jobs`/`search_source_progress`/`search_events` 独立表；**不得**复用 `paper_import_batch_*` 的 CAS/租约/状态迁移语义。
- C-3：v2 新增外键的 ON DELETE 行为统一显式声明为 `RESTRICT`/保留快照（与 spec 第 270、287 行一致），禁止 CASCADE，禁止删除导入历史/来源证据/冻结结果。
- C-4：`kb/index.py`/`retrieve.py`/`embed.py` 的 collection、payload、过滤器以参数传入；论文发现目录使用独立 collection（`PAPER_DISCOVERY_QDRANT_COLLECTION`=`paper-discovery-catalog`），不得混入个人 PDF 分块；不得新建第二套 embedding/索引/检索。
- C-5：本任务不得新建 HTTP 路由、不得访问外部网络、不得创建 Qdrant collection（spec Task13 第 32 行）；PDF 仅在导入阶段经 `paper_download.py` 下载，搜索/同步阶段禁止探测。
- C-6（禁止重复实现总则）：不得新增第二套 下载器(`paper_download`)/SSRF 校验(`paper_download_security`)/导入流程(`paper_import`)/批任务状态机(`paper_import_batch_*`)/身份规范化(`paper_import_identity`)/embedding(`kb/*`)；任何替换须给出无法安全复用的可复现证据、迁移范围与回归测试。

## 五、验证与证据
- 已用 grep 核对全部引用路径真实存在：`backend/app/services/{paper_download,paper_download_security,paper_import,paper_import_batch_service,paper_import_batch_store,paper_import_identity,paper_discovery_normalization,paper_discovery_search,usenix_paper_parser,usenix_publication_source,dblp_publication_source,paper_browser_manager,paper_discovery_store}.py`、`backend/app/domain/paper_discovery.py`、`backend/app/services/kb/{embed,index,retrieve}.py`、`tests/test_{paper_download,paper_download_security,paper_import,kb_services,paper_discovery_store,usenix_paper_parser,paper_import_batch_store,paper_import_identity,paper_discovery_search,paper_discovery_api}.py`、`frontend/index.html`、`backend/app/api/routes.py`。
- 调用者核对：`api/routes.py` 为统一装配点；`paper_import.py`/`acm_paper_parser.py`/`dblp_publication_source.py`/`paper_browser_manager.py` 为直接复用者。
- 未触碰 Spec017；无网络请求；未做 git add/commit/reset/stash/clean。

## 六、风险与阻塞
- 总体风险：**中**。复用边界清晰、无第二套实现；主要风险在 v2 迁移事务完整性（C-1）与 kb collection 参数化（G-1/C-4）的实现落地。
- 阻塞：**无设计级阻塞**。schema v2 设计自洽。G-1/G-2/G-3/G-4 与 C-1~C-6 为实现层须落地项，由子任务B/C 处理，不阻塞本审计"通过"结论。

## 七、主 Agent 后续动作
1. 按 C-1~C-6 分派子任务B（领域模型+v2 迁移）与子任务C（仓储并发测试），优先解决 G-1（kb collection 参数化）与 G-2（store 测试补齐）。
2. 子任务B/C 读回时，按本审计逐项核对无新建同类基础设施。
3. 子任务B 须在 schema 实现文档显式记录 C-3 外键 ON DELETE 决策。
