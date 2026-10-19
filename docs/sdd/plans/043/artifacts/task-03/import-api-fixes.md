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
