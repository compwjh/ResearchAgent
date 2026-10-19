# Task03 导入桥接与 API 修复交接

日期：2026-10-19；角色：backend-dev；范围：`application/import_bridge.py`、`application/runtime.py`、`api/routes_literature_maps.py` 与地图导入/API错误测试。

## 状态

实现完成，待独立 backend reviewer/tester 复核；本轮未执行真实外部下载、生产数据库、API E2E、部署或 commit。

## 实际改动

- 生产组合根把现有 `import_candidate` 安全导入链注入地图桥接，复用 `common._paper_candidate_hosts` 固定 allowlist；地图读取不触发导入，只有用户点击导入端点才调用。
- 新增 `paper_import_adapter.py`，优先消费节点内服务端冻结的 catalog snapshot（catalog ID、official/prepublication PDF、DOI/arXiv/source）；没有官方 PDF 时才走既有 Semantic Scholar OA 元数据适配器。它不下载、不跟随 redirect、不扩展 host allowlist。
- 桥接仅接收节点冻结的 action `source_url`，拒绝客户端/内部 override、凭据、fragment、localhost 和私网/保留 IP；S2 landing page 不再被当作 `pdf_url`，实际 DNS、host、redirect、PDF 校验仍由既有下载链执行。
- 既有导入结果归一为安全句柄，`paper_id` 作为真实 `document_id` 回写 `store.update_node_import_result(map,node,owner)`；捕获 `PaperDownloadError`/`PaperImportError` 后持久化固定失败/等待登录状态；不把 Semantic Scholar ID 冒充 `catalog_paper_id`，不暴露异常文本。
- `ImportRequest` 保留为空动作模型（禁止 `source_url`），空 `{}` 可接受；路由调用 `service.import_node(map_id,node_id,owner_id)` 不传 URL override。
- 地图路由的 store 读写异常统一固定 `503/MAP_STORAGE_UNAVAILABLE`；404/409 语义保持，异常文本不进入响应。列表、地图详情、删除、job、events 等直接 store 入口均纳入错误边界。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/opt/anaconda3/bin/pytest -q tests/literature_maps`（临时 stub 仅满足本机缺失的 `langchain_ollama`） | 0 | 52 passed；含 landing/客户端 URL 拒绝、冻结官方 PDF 优先、无 OA 固定失败、身份冲突、导入异常持久化、API错误注入 |
| `/opt/anaconda3/bin/python -m ruff check ...`（6 个本轮应用/测试文件） | 0 | All checks passed |
| `/opt/anaconda3/bin/python -m py_compile ...` + `scripts/check_test_layout.py` | 0 | 语法与测试布局通过 |
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/pytest -q tests/literature_maps` | 0 | 50 passed；使用仓库已有 site-packages，并仅以临时 stub 补齐本机缺失的 `langchain_ollama`，未改仓库依赖 |

## 明确限制

- 未调用真实 Semantic Scholar/OA/下载器/知识库，不将 fake importer 测试当作真实 API E2E；生产 importer 会在用户点击后才解析/下载，依赖部署已有论文导入配置。
- 未运行全量回归、未启动服务、未读写 `.env`、未提交或推送；Spec/Task 状态与统一 changelog 由主会话收口。仓库 `.venv` 的 Python 链接仍指向已不存在的 PyCharm 路径，因此本轮用已有 site-packages 运行离线地图域测试；未将其当作真实 API E2E 或部署验收。

## 最终接缝修复（2026-10-19）

- 路由将 service 的 `INVALID_MAP_SCOPE` 固定映射为 400 和不含请求值的中文提示；存储异常仍固定为 503，保留既有 404/409 分支。
- HTTP 测试改为调用真实地图 service 组合根，以未知 source/conference 验证 400、固定错误码和无 raw input；未创建地图（service 在存储写入前完成 scope 校验）。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/pytest -q tests/literature_maps/test_map_api_errors.py` | 0 | 6 passed |

本次仍未执行真实论文下载、生产数据库写入、服务启动、全量回归、部署或 commit。

## 真实 API E2E 的 arXiv `PDF_NOT_FOUND` 诊断（2026-10-19）

本节为只读诊断；没有再次调用导入、下载论文、访问密钥或修改业务代码。E2E 证据见 `api-e2e.md` / `api-evidence.json`：节点包含 arXiv `1809.07041`、DOI `10.1007/978-3-030-01264-9_42` 和 Semantic Scholar ID，但为未选 catalog scope 的 S2 节点，`catalog_paper_id=null`；唯一导入请求返回 `202` 业务失败 `PDF_NOT_FOUND`，且持久化为 `download_status=failed`、无 document ID。

### 链路证据

- 地图 `PaperImportSourceAdapter.resolve()` 在无已证明 catalog PDF 时只调用注入的 `oa_resolver`；OA 无结果即固定 `PDF_NOT_FOUND`（`application/paper_import_adapter.py:30-50`）。
- runtime 的 `_existing_oa_resolver()` 只实例化 `SemanticScholarFallbackAdapter`，将节点 arXiv ID 优先传给 S2 的 `paper/ARXIV:1809.07041` 查询；任意 S2 错误、无 `openAccessPdf`、匹配不确定或返回 PDF 主机不在固定 allowlist 时都被压成 `None`（`application/runtime.py:52-84`，S2 adapter `:215-237`）。E2E artifact 没有保存原始 provider envelope 或 resolver code，因此不能从本次结果证明“arXiv 真实无 OA”。
- 既有 `ArxivFallbackAdapter` 确实存在，但其 `lookup(title, authors, year)` 只在 `UsenixAcceptedSource` 的官方媒体缺失分支调用（`infrastructure/arxiv_adapter.py:74-101`、`usenix_publication_source.py:230-245`）；地图 import runtime 没有装配该能力，也没有把节点已有 arXiv ID 交给它。故当前失败至少存在“既有 arXiv fallback 未复用”的确定性接缝，不能标记为真实无 OA。
- `import_candidate()` 自身的 fallback 仍是同一个 Semantic Scholar OA adapter，并非 `ArxivFallbackAdapter`（`application/paper_import.py:419-444`）；由于 map bridge 要求 resolver 先提供显式 `pdf_url`，本次 resolver 返回空时不会进入 importer fallback。

### 最小修复方案（待主会话确认后另行实现）

在 `runtime` 的现有 OA resolver 内增加一个窄的、只读 arXiv 元数据 fallback：仅当节点已有确定 arXiv ID（优先直接身份核对；必要时复用现有 `ArxivFallbackAdapter` 的安全匹配能力）且返回地址通过既有 `builtin_allowed_hosts("arxiv")` / `import_candidate` 安全链时，才产生 `pdf_url`；不从标题把目录记录绑定到节点，不复制 downloader，不扩展 allowlist。resolver 应保留稳定失败原因（至少区分 `ARXIV_MATCH_UNCERTAIN`、`ARXIV_UNAVAILABLE`、`SEMANTIC_SCHOLAR_NO_OPEN_PDF`/其他 S2 失败）供桥接持久化，避免把真实无 OA 与 provider/主机失败混为单一 `PDF_NOT_FOUND`。

当前结论：**不能证明 arXiv 1809.07041 真实无 OA；已确认地图导入路径未复用既有 `ArxivFallbackAdapter`。** Task03 继续 BLOCKED，E2E 的 HTTP 202 失败结果不作成功依据。

## arXiv fallback 接入修复（2026-10-19）

- runtime 现在在确定 arXiv identity 存在时先调用既有 `ArxivFallbackAdapter`；仅当返回的 arXiv ID 与节点 identity 完全一致且 adapter 自身返回安全 PDF 地址时使用该候选。adapter 未命中、异常或身份冲突后，按既有顺序再调用 `SemanticScholarFallbackAdapter`。
- 不拼接 arXiv URL、不新增 downloader、不扩展 host allowlist；两类 metadata adapter 的地址仍交给唯一既有 `import_candidate`/下载安全链。S2 返回的 arXiv/DOI identity 也再次核对，冲突不进入 importer。
- resolver 失败不再全部返回 `None`：返回固定 `error_code=PDF_NOT_FOUND` 以及受控 `resolver_code`/`resolver_codes`（如 `ARXIV_UNAVAILABLE`、`ARXIV_IDENTITY_CONFLICT`、`SEMANTIC_SCHOLAR_NO_OPEN_PDF`），不携带异常文本。地图桥接仍持久化稳定 PDF failure，不把 provider code当作客户端原始错误。

### 离线能力命名/边界测试

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/pytest -q tests/literature_maps/test_map_import_bridge.py` | 0 | 21 passed；覆盖 arXiv 成功优先、S2 有序 fallback、arXiv identity conflict、provider failure、无 PDF |
| 同上 `pytest -q tests/literature_maps` | 0 | 67 passed；未调用真实 provider/download |
| `ruff check runtime.py paper_import_adapter.py test_map_import_bridge.py` | 0 | All checks passed |
| `py_compile runtime.py paper_import_adapter.py test_map_import_bridge.py` | 0 | 通过 |

本次未重跑真实 API E2E、未下载论文、未部署、未读取密钥、未提交。既有 E2E 的 `202 + PDF_NOT_FOUND` 仍是失败，不作成功依据；主会话需在重启服务后独立复跑真实导入验收。

## Resolver 诊断码跨桥接/API 接缝修复（2026-10-19）

- import bridge 的归一化结果现在仅从受控白名单保留 `resolver_code`/`resolver_codes`（arXiv/Semantic Scholar 的固定诊断码）；任意异常文本、URL、key 或未知 provider 字段均被丢弃。
- 主业务 `error_code` 仍保持 `PDF_NOT_FOUND` 等既有稳定值；安全诊断码随 bridge 结果进入 `update_node_import_result(import_result=...)` 调用，并由导入 HTTP 响应返回，便于 store 接缝与 API 验证。未修改 store schema/服务层；现有生产 store 仍按既有契约持久化 document/status/catalog 字段，诊断码的本轮持久化证据由 fake store 捕获的完整 import_result 提供。
- 精确测试覆盖：bridge/store 调用捕获白名单诊断码并过滤 secret URL；route 直调及 HTTP 202 返回诊断码；主 error code 兼容不变。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/pytest -q tests/literature_maps/test_map_import_bridge.py tests/literature_maps/test_map_api_errors.py` | 0 | 30 passed |
| 同上 `pytest -q tests/literature_maps` | 0 | 71 passed |
| `ruff check` 六个受影响应用/测试文件 | 0 | All checks passed |
| `py_compile` 六个受影响应用/测试文件 | 0 | 通过 |

本次未下载、未部署、未重跑真实 API、未提交；真实 E2E 的 `202 + PDF_NOT_FOUND` 仍不作成功依据。

## Resolver 诊断码真实 SQLite 持久化修复（2026-10-19）

- 独立复审确认原实现只把诊断码传入 `update_node_import_result(import_result=...)`，SQLite store 仅更新 document/status/catalog 三列，节点 GET/重开 store 后丢失诊断码。
- 复用现有 `MapPaper.provenance_json`，新增受控命名空间 `provenance.import_diagnostics`，不新增列、迁移或第二模型；保留其他 provenance 字段。store 边界再次过滤主 `error_code` 和固定 resolver 白名单，原始异常、URL、key 与未知字段不入库。
- `indexed`/`completed` 成功重试删除过期 `import_diagnostics`，并保留真实 document handle；owner/map/node SQL 守卫不变。
- 精确 SQLite/HTTP 测试覆盖：失败 POST 返回诊断码，随后 GET 与重开 `LiteratureMapStore` 可见；成功重试后 GET 与再次重开均清除诊断码，同时保留原 provenance。测试使用临时 SQLite 和 fake importer，不触发下载。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `pytest -q tests/literature_maps/test_map_store.py tests/literature_maps/test_map_api_errors.py tests/literature_maps/test_map_import_bridge.py` | 0 | 39 passed |
| `pytest -q tests/literature_maps` | 0 | 73 passed |
| `ruff check store.py test_map_store.py test_map_api_errors.py` | 0 | All checks passed |
| `py_compile` 三个受影响文件 | 0 | 通过 |

本次未下载、未部署、未重跑真实外部 API、未提交；生产真实 API 需由主会话在服务重启后独立复审。

## r2 真实导入诊断：resolver 接缝与失败码白名单（2026-10-19）

### 已确认的调用链与输入

- 只读打开临时/当前 SQLite 中的真实 r2 节点 `0baabeae7268429c9f7e4de8098ae1d0 / 21041260a5394f42891b020128fa60fa`：标题 `Graph Attention Networks`，6 位作者，年份 `2017`，外部身份含 arXiv/DOI/Semantic Scholar；节点 `source_url` 仍是 S2 landing，`catalog_paper_id` 与 catalog snapshot 均为空。
- `PaperImportSourceAdapter.resolve()` 在该节点没有服务端官方 PDF 时确实调用注入的 runtime OA resolver；只读 fake-adapter trace 确认调用发生。
- runtime 给既有 `ArxivFallbackAdapter.lookup()` 的形状是 `(title, authors, year)`，即标题、6 位作者、2017；arXiv identity 不直接作为 arXiv API 查询参数，而是在返回 metadata 后由 runtime 严格核对。S2 adapter 收到 `arxiv_id=1710.10903`、DOI、年份及完整外部身份，allowlist 含 arXiv host；没有 title-only 绑定。

### 可验证的确定性缺陷

runtime 可能产生的稳定 provider 失败码包括 `ARXIV_RATE_LIMITED`、`ARXIV_HTTP_ERROR`、`ARXIV_INVALID_RESPONSE`、`SEMANTIC_SCHOLAR_RATE_LIMITED`，但当前 `import_bridge` 与 SQLite store 的 resolver 白名单只覆盖 `ARXIV_UNAVAILABLE`、`ARXIV_MATCH_UNCERTAIN` 等码，遗漏上述四类。若本次 resolver 只返回其中一个遗漏码，bridge/store 会安全地丢弃它，GET 节点就只剩主错误 `PDF_NOT_FOUND`。这是代码级可复现的诊断丢失根因，不涉及客户端 URL 或异常泄露。

### 一次受控公共 metadata probe

仅复用既有 `ArxivFallbackAdapter` 对同一节点 metadata 做一次查询，`retries=0`，不下载 PDF、不调用导入链、不读取或输出 key。结果仅记录固定摘要：`code=ARXIV_UNAVAILABLE`、`matched=false`、`identity_matches=false`、`year_matches=false`、无安全 PDF 候选。该结果只证明本次 probe 的 provider/网络不可用，不能证明论文没有 OA，也不能反推 r2 导入当时的 provider 分支。

### 当前结论与最小修复建议

- 已确认 bridge source→runtime resolver 调用未断；节点身份与 resolver 输入形状正确。
- 已确认失败码白名单存在遗漏，足以解释“provider failure 后只剩 `PDF_NOT_FOUND`”。但脱敏 r2 artifact 没有 provider envelope，不能断言 r2 实际命中 rate-limit、HTTP/invalid response，或是 resolver 成功给出 PDF 后下游安全 downloader 返回真实 `PDF_NOT_FOUND`。
- 最小修复应仅扩展 bridge/store 两处固定白名单，加入上述四个稳定 provider code，并为每个 code 增加 bridge→SQLite→HTTP GET 回归；不放宽 URL/身份规则，不新增 downloader。修复后需重启服务并以一次新的受控真实导入复核，不得把当前 r2 的 `PDF_NOT_FOUND` 改判为无 OA。

本次为只读诊断：未修改业务代码、未再次 POST 导入、未下载论文、未部署、未读取/输出密钥、未提交。

## Resolver 稳定码与可重试语义修复（2026-10-19）

- 新增 literature-map domain 小模块 `domain/import_diagnostics.py`，集中维护既有 arXiv/Semantic Scholar resolver 稳定码、transient retryable 码、无安全 PDF 候选码及持久化 normalizer；`import_bridge` 与 SQLite store 不再各自维护白名单。
- 覆盖并保留：`ARXIV_RATE_LIMITED`、`ARXIV_HTTP_ERROR`、`ARXIV_INVALID_RESPONSE`、`ARXIV_UNAVAILABLE`、`SEMANTIC_SCHOLAR_RATE_LIMITED` 及既有身份/无 OA/主机校验码。未知字符串、URL、key 和 provider 原始字段仍被丢弃。
- runtime 对 provider operational failure 返回固定 provider 主 `error_code`，并保留 adapter 的真实 retryable（另对既有明确 transient code 做受控兜底）；只有确实没有安全 PDF 候选时才返回 `PDF_NOT_FOUND`。HTTP 公共结果 shape 未新增字段，原有 `retryable` 语义被修正。
- SQLite `import_diagnostics` 使用同一 normalizer 持久化主错误码、resolver codes、retryable；失败 POST→GET→重开 store 可见，成功 indexed 重试清除旧诊断并保留 document/provenance。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `pytest -q tests/literature_maps/test_map_import_bridge.py tests/literature_maps/test_map_api_errors.py tests/literature_maps/test_map_store.py` | 0 | 50 passed |
| `pytest -q tests/literature_maps` | 0 | 84 passed |
| `ruff check` 受影响 domain/runtime/bridge/store 与测试文件 | 0 | All checks passed |
| `py_compile` 受影响 domain/runtime/bridge/store 与测试文件 | 0 | 通过 |

本次仅使用 fake adapter、临时 SQLite 和 HTTP 测试；未真实下载、未真实导入、未部署、未读取/输出密钥、未提交。r2 的真实 `PDF_NOT_FOUND` 仍需主会话重启服务后独立复核，不能据此宣称无 OA。

交接日志：`.codebuddy/agent-logs/spec-043/task-03/backend-dev/20261019-000000.md`

## r3 arXiv identity-only resolver诊断（2026-10-19）

本轮为只读代码诊断；未发起外部请求、未调用导入/下载、未读取密钥，也未修改业务代码。目标是解释真实 r3 中已有 arXiv `1710.10903` 仍产生 `ARXIV_MATCH_UNCERTAIN` 后才进入 Semantic Scholar 限流的原因。

### 现有能力核对

- `backend/app/paper_discovery/infrastructure/arxiv_adapter.py` 的 `ArxivFallbackAdapter` 只有 `lookup(title, authors, year, *, usenix_pdf_available=False)`，没有按 arXiv ID 查询的公开入口。
- `lookup()` 将标题、规范化作者集合和年份组成缓存键，并把请求固定为 `search_query=ti:"<title>"`, `start=0`, `max_results=20`；节点已有 arXiv ID 没有进入 HTTP 查询参数。
- Atom 解析和安全地址校验已经可复用：`_arxiv_id()` 只接受 allowlisted `https://arxiv.org/abs/...` identity，`_safe_pdf()` 只接受 allowlisted `https://arxiv.org/pdf/...`、无 query/fragment 的地址；解析还要求年份相等、标题相似度至少 `0.90`、作者相似度至少 `0.80`。
- runtime 在 `application/runtime.py` 中以 `(title, authors, year)` 调用该 adapter，拿到结果后才把返回的 `match.arxiv_id` 与节点 arXiv identity 比较。因而这是“先标题检索、后 ID 核对”，不是“按确定 ID 精确获取”。

### r3 失败点

r3 的 `resolver_codes=[ARXIV_MATCH_UNCERTAIN, SEMANTIC_SCHOLAR_RATE_LIMITED]` 与现有实现一致：标题查询没有产生同时通过年份/标题/作者门禁并带安全 PDF 的 Atom entry 时，adapter 返回 `match=None, code=ARXIV_MATCH_UNCERTAIN`；runtime 随后才调用 Semantic Scholar，命中其限流。即使 arXiv 已知 ID 为 `1710.10903`，当前 adapter 也不会先请求该 ID，也不会把它作为查询过滤条件。因此 `ARXIV_MATCH_UNCERTAIN` 不能解释为“该 ID 没有 OA”，而是“标题查询未得到身份安全候选”。若标题查询返回同名但不同 ID 的记录，runtime 会追加 `ARXIV_IDENTITY_CONFLICT`，同样拒绝导入。

### 最小可验证建议

增加一个窄的 identity-first adapter seam（例如 `lookup_by_id(arxiv_id, title, authors, year)`），内部复用现有 HTTP client、限流/重试、Atom parser、`_arxiv_id()`、`_safe_pdf()` 以及既有标题/作者/年份门禁；请求仅把已冻结、已规范化的 ID 作为 arXiv API 的 `id_list` 参数，不自行拼接 PDF URL。返回前仍必须同时满足：Atom entry ID 与节点 ID 完全相等、年份一致、标题/作者门禁通过、PDF 地址通过现有安全校验。任何冲突返回固定 `ARXIV_IDENTITY_CONFLICT`，transport/HTTP/XML 失败保留既有固定 adapter code。

runtime 仅在节点具有确定 arXiv identity 时走该 identity-first seam；没有 arXiv identity 的既有 USENIX 路径继续使用 title lookup，避免破坏既有调用者。成功候选仍唯一交给现有 `import_candidate` 安全链，不新增 downloader、不放宽 host/DNS/redirect/PDF 校验；失败后才按原顺序尝试 Semantic Scholar。应以 fake HTTP transport 覆盖：精确 ID 成功、相同标题不同 ID 被拒、标题/作者冲突被拒、无 entry、provider 固定失败码；本轮不执行真实外呼。

结论：**已有 Atom parser 与安全 HTTP 接缝可复用，但当前没有 arXiv ID 精确查询能力；r3 的身份不确定发生在标题查询阶段，随后 Semantic Scholar 限流是次级 provider 失败。** 这解释了为何不能把 r3 判为真实无 OA，也不授权再次限流重试或直接下载。

## arXiv identity-first 精确解析修复（2026-10-19）

本轮按批准范围实现并仅做离线 mock 验证；没有真实 provider 外呼、PDF 下载、导入、部署、密钥读取或 commit。

### 实际改动

- `ArxivFallbackAdapter` 新增 `lookup_by_id()`，复用既有 HTTP client、限流/重试、Atom 解析和安全 PDF/abs 地址校验；请求使用 `id_list`，不拼接 URL、不新增下载器。
- 新增单一 `normalize_arxiv_id()`：接受规范的新格式、旧格式及版本后缀（含可选 `arxiv:` 前缀），拒绝 HTTP(S) URL、query、注入文本和非法版本；runtime 与 map source adapter 共用该 normalizer。
- exact 查询仍强制年份、标题相似度和作者相似度门禁；回传 ID 不同、同标题不同 ID、或 exact ID 的 metadata 冲突均固定为 `ARXIV_IDENTITY_CONFLICT`，不会静默采纳。
- runtime 对确定 arXiv identity 先走 `lookup_by_id()`，成功后才交既有 `import_candidate` 安全链；exact 失败再按既有顺序走 Semantic Scholar。没有 arXiv identity 时保留原 title lookup；无效 URL/注入 identity 不触发 title lookup，S2 结果也不会绕过冲突。
- 公共地图 API shape 未改变；现有受控 resolver diagnostics 白名单已包含 `ARXIV_IDENTITY_CONFLICT`，桥接/SQLite/API 接缝继续复用同一诊断码。

### 精准验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/python -m pytest -q tests/paper_discovery/test_arxiv_adapter.py tests/literature_maps/test_map_import_bridge.py tests/literature_maps/test_map_api_errors.py tests/literature_maps/test_map_store.py` | 0 | 60 passed |
| 同上 `pytest -q tests/paper_discovery/test_usenix_publication_source.py` | 0 | 42 passed，旧 title lookup 调用链保持兼容；5 个既有 DeprecationWarning |
| `.venv/bin/ruff check` 受影响 adapter/runtime/import-adapter 与测试文件 | 0 | All checks passed |
| `/opt/anaconda3/bin/python -m py_compile` 受影响生产/测试文件 | 0 | 通过 |

测试覆盖 exact `id_list` 参数、版本归一化、旧格式、URL/注入拒绝、错 ID、同标题不同 ID、metadata 冲突、runtime exact 调用、无 ID 的旧 title lookup、S2 fallback 和冲突不静默成功。未执行真实 API E2E；r3 的生产限流结果仍保持原证据与 BLOCKED 判定。

## r4 精确 arXiv Atom 证据诊断（2026-10-19）

本节为一次授权的公共 metadata-only probe；只请求 Atom XML，不请求 PDF、不调用地图导入、不读取密钥、不修改代码。请求为 `GET https://export.arxiv.org/api/query?id_list=1710.10903&start=0&max_results=1`，UTC `2026-10-19T14:36:13Z` 返回 HTTP 200，`totalResults=1`。

### 脱敏 entry 证据

| 字段 | 实际 Atom 形态 | 当前门禁结果 |
|---|---|---|
| entry id | scheme=`http`, host=`arxiv.org`, path=`/abs/1710.10903v3` | 当前 `_arxiv_id()` 只接受 `https`，因此直接返回 `None` |
| PDF link | scheme=`https`, host=`arxiv.org`, path=`/pdf/1710.10903v3`, `title=pdf` | 当前 `_safe_pdf()` 可接受；没有请求该地址 |
| alternate link | scheme=`https`, host=`arxiv.org`, path=`/abs/1710.10903v3` | 可作为 canonical metadata page，不是下载入口 |
| arXiv version | `v3` | 节点冻结 identity 是裸 `1710.10903`；当前 strict `!=` 也会拒绝 base→latest |
| title | `Graph Attention Networks` | 与节点标题完全匹配，`title_score=1.0` |
| published year | `2017` | 与节点年份匹配 |
| authors | 6 位：Petar Veličković、Guillem Cucull、Arantxa Casanova、Adriana Romero、Pietro Liò、Yoshua Bengio | 规范化重音后与节点 6 位作者匹配，`author_score=1.0` |

未保留摘要、API query token、响应内部 id 或任何凭据。公共 Atom 返回的 `http` abs entry 与 `https` PDF/alternate link 是本次证据中唯一需要的链接形态。

### 可验证根因

r4 的 `ARXIV_MATCH_UNCERTAIN` 不是论文无 OA：真实 Atom 确实有唯一 entry，标题/年份/作者门禁均通过。当前实现有两个连续的确定性断点：

1. `_arxiv_id()` 要求 entry id scheme 为 `https`，而真实 Atom entry id 为 `http://arxiv.org/abs/1710.10903v3`，所以解析成 `None`。
2. 即使仅修正 metadata entry 的 scheme，expected 裸 ID `1710.10903` 与真实最新版 `1710.10903v3` 的严格字符串比较仍会失败。当前 `_safe_pdf()` 使用的是独立 `https` PDF link，本次不构成 HTTP PDF 放宽问题。

### 最小修复方案（待实施）

- 仅对已认证 `arxiv.org` / `export.arxiv.org` 的 metadata `abs` entry 接受 `http` 或 `https`，拒绝 credentials、非默认 port、query、fragment 和其他 host，并立即 canonicalize 为 `https://<allowlisted-host>/abs/<normalized-id>`；绝不因此允许 HTTP PDF 下载。
- 保留单一 arXiv ID normalizer，并增加明确的 base/version 比较：expected 裸 ID可匹配同 base 的 Atom latest version（本例 `1710.10903`→`1710.10903v3`）；expected 显式 `vN` 时必须 exact `vN`，不接受其他版本。`id_list` 仍只发送规范裸/显式 ID，不接受 URL 或注入文本。
- Atom 的返回 ID、标题/作者/年份和安全 `https` PDF link 仍需全部通过；错 base、显式版本冲突或 metadata 冲突继续固定 `ARXIV_IDENTITY_CONFLICT`。runtime 的返回 identity 比较也必须使用同一 base/version 规则，避免 adapter 成功后又被 runtime 的字符串 `!=` 二次误拒。
- 实际 PDF 地址仍只交给既有 `import_candidate` 下载安全链；不拼接新 URL、不请求 HTTP PDF、不放宽 DNS/redirect/host/PDF 校验。应新增 mock 断言覆盖真实 Atom 的 `http` abs + `https` PDF、bare→latest、explicit-version mismatch 和 metadata conflict，再由主会话重启后单次真实 API 复核。

结论：**已取得真实 Atom 证据，r4 的身份不确定根因是 metadata abs scheme 与 arXiv version 语义，而不是缺少 OA。当前不应继续把该节点判为稳定 `PDF_NOT_FOUND`，待上述窄修复后再按既有一次性 E2E 门禁复核。**

## arXiv metadata scheme/version 最小修复（2026-10-19）

本轮按真实 Atom 证据实施；只修改 metadata identity 解析与 runtime 比较接缝及精准测试。未修改 `_safe_pdf`、下载器、import_candidate、安全 host/DNS/redirect 链；未真实外呼、下载、导入、部署或提交。

### 实际改动

- `_arxiv_id()` 现在仅对固定可信 `arxiv.org`/`export.arxiv.org` metadata abs 链接接受 HTTP 或 HTTPS，拒绝凭据、非法 port、query、fragment 和其他 host，并只提取规范 arXiv identity；`ArxivMatch.source_page_url` 仍输出 canonical HTTPS。HTTP 仅限 metadata identity，实际 PDF 仍由原 HTTPS `_safe_pdf()` 校验。
- 新增共享 `arxiv_identity_matches()`：裸 expected ID 可匹配同 base 的返回版本（如 `1710.10903`→`1710.10903v3`）；显式 `vN` 必须 exact，版本不同返回 `ARXIV_IDENTITY_CONFLICT`。adapter、runtime 的 exact match 和 S2 回退 identity gate 共用该 helper，不再二次 raw string `!=`。
- 保留 `id_list` 只发送规范裸/显式 ID；URL、host 注入和 query 文本仍在请求前拒绝。题名/作者/年份门禁保持不变；`_safe_pdf` 未改。

### 精准验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/python -m pytest -q tests/paper_discovery/test_arxiv_adapter.py tests/literature_maps/test_map_import_bridge.py tests/literature_maps/test_map_api_errors.py tests/literature_maps/test_map_store.py` | 0 | 63 passed |
| 同上 `pytest -q tests/paper_discovery/test_usenix_publication_source.py` | 0 | 42 passed；旧 title lookup 保持兼容；5 个既有 DeprecationWarning |
| `.venv/bin/ruff check` 受影响 adapter/runtime/import-adapter 与测试文件 | 0 | All checks passed |
| `/opt/anaconda3/bin/python -m py_compile` 受影响生产/测试文件 | 0 | 通过 |

fixture 覆盖真实 Atom 结构：`http://arxiv.org/abs/<base>v3` entry、`https://arxiv.org/pdf/<base>v3` link、bare→latest、explicit-version mismatch、错误 host/凭据/query、metadata 冲突，以及 runtime 不回退旧 title lookup。等待独立 review 后再决定是否进行新的单次真实 API 复核。

## 最终窄审冲突归类修复（2026-10-19）

独立 review 指出 exact parser 在 expected 裸 ID、返回带版本且 metadata 不匹配时，仍有一处旧 raw-string 比较，可能把冲突误归类为 `ARXIV_MATCH_UNCERTAIN`；runtime 的 S2 成功组合也必须继续被冲突门禁拒绝。本轮仅修正该比较并补精准回归，未部署、未真实外呼/下载/导入、未提交。

- Atom parser 的 metadata conflict 判定现在复用同一 `arxiv_identity_matches()`；expected `2501.00001` 与返回 `2501.00001v3` 先按同 base 识别，再在标题/作者/年份不符时固定返回 `ARXIV_IDENTITY_CONFLICT`。
- 既有 runtime 组合门禁回归确认：当 arXiv resolver 返回 `ARXIV_IDENTITY_CONFLICT` 时，即使 S2 返回同 arXiv identity 的安全 PDF，也不会静默成功，结果仍为无 PDF 失败并保留冲突诊断。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/python -m pytest -q tests/paper_discovery/test_arxiv_adapter.py tests/literature_maps/test_map_import_bridge.py tests/literature_maps/test_map_api_errors.py tests/literature_maps/test_map_store.py` | 0 | 64 passed |
| `.venv/bin/ruff check` 受影响 adapter/runtime 与精准测试 | 0 | All checks passed |
| `/opt/anaconda3/bin/python -m py_compile` 受影响 adapter/runtime 与精准测试 | 0 | 通过 |

本轮仅针对该 P1 窄缺陷；真实 API 复核仍等待独立 review，不以 mock 结果替代生产证据。
