# Spec-043 知识库导入失败诊断计划

## 诊断结论

- 诊断日期：2026-10-24
- 诊断范围：只读诊断；不修改业务代码、前端代码、生产状态或 SQLite 数据，不触发下载、重试、目录搜索或模型调用。
- 诊断对象：地图节点的“加入知识库”返回 `HTTP 202` 且业务状态为 `failed` 后，界面只显示“入库状态：失败”。
- 当前首要缺陷是前端状态投影：后端已经在新的失败记录中返回并持久化安全的 `error_code`、`resolver_code(s)` 和 `retryable`，但 `importNode` 只把 `status` 投影成通用文案，丢弃了这些字段。
- 另有一条旧失败记录是在诊断字段持久化之前产生的；即使之后的一次受控导入写入了新的诊断，也无法恢复该旧尝试的实际失败码，不能把历史 `PDF_NOT_FOUND` 当成当前 API 的新证据。

本文件是给根 Agent 的只读交接物。实现尚未开始，也没有改变 Spec-043 状态。

## 真实失败记录

证据来自运行中的 `GET /api/literature-maps/{map_id}/graph`、逐节点 `GET /api/literature-maps/{map_id}/nodes/{node_id}`，以及以 `mode=ro` 打开的 `data/literature_maps/literature_maps.sqlite3`。SQLite 连接设置了 `PRAGMA query_only=ON`；节点计数为 `99` 条无状态、`2` 条 `failed`、`1` 条 `indexed`。

| 地图 / 节点 | 当前状态 | 知识库实体 | 当前可见诊断 | 来源身份 | 结论 |
|---|---|---|---|---|---|
| `0baabeae7268429c9f7e4de8098ae1d0` / `56c7189f4f9343c98be3f9a95563cfd6` | `failed` | `document_id=null`、`catalog_paper_id=null` | `error_code=SEMANTIC_SCHOLAR_RATE_LIMITED`；`resolver_code` 相同；`resolver_codes=[ARXIV_MATCH_UNCERTAIN, SEMANTIC_SCHOLAR_RATE_LIMITED]`；`retryable=true` | `source_url=https://www.semanticscholar.org/paper/27fac6147325b49638ff08a93cabf176c95e1b08`；DOI `10.1109/tii.2024.3371489`；Semantic Scholar ID `27fac6147325b49638ff08a93cabf176c95e1b08` | 可确定为 OA/提供方解析阶段的限流失败，尚未进入 PDF 下载或知识库写入阶段；这是当前最完整的可恢复失败证据。 |
| `9b1e4739443e40c98400cfb69aec1e45` / `2e35b888d3cb414090e2d8e55e5bae1a` | `failed` | `document_id=null`、`catalog_paper_id=null` | 预检时 `provenance.import_diagnostics` 不存在；经授权的一次真实 POST 后，当前记录新增 `error_code=SEMANTIC_SCHOLAR_RATE_LIMITED`、`resolver_codes=[ARXIV_IDENTITY_CONFLICT, SEMANTIC_SCHOLAR_RATE_LIMITED]`、`retryable=true` | `source_url=https://www.semanticscholar.org/paper/0000fcfd467a19cf0e59169c2f07d730a0f3a8b9`；arXiv `1809.07041`；DOI `10.1007/978-3-030-01264-9_42`；Semantic Scholar ID `0000fcfd467a19cf0e59169c2f07d730a0f3a8b9` | 这是诊断持久化前的旧记录；新诊断描述的是本次受控导入，不是旧尝试的回填。历史 Task-03 E2E 材料记录当时的响应为 `PDF_NOT_FOUND`，不能据此伪造旧尝试的当前失败原因。 |

第一条记录还出现在地图创建 job `ba6bb4f9471b43afb8b1063cdc3a883d` 的 `failed_units` 和完成事件中，错误码同为 `SEMANTIC_SCHOLAR_RATE_LIMITED`。第二条是后续直接节点导入；直接导入没有单独的 `literature_map_jobs/events` 记录，所以必须以节点状态和 provenance 为准。

## 失败发生在哪一层

| 阶段 | 现有实现与证据 | 对当前失败的判断 |
|---|---|---|
| HTTP 入口 | `backend/app/api/routes_literature_maps.py:591-597` 的 `POST /api/literature-maps/{map_id}/nodes/{node_id}/imports` 调用 service，并固定返回 `202`；业务失败不是 HTTP 异常。 | 前端必须解析 `202` body，不能只在 `catch` 中处理错误。 |
| 节点导入编排 | `backend/app/literature_maps/application/service.py:857-867` 获取节点、校验来源 URL 后调用 `import_bridge`。 | 没有证据表明本次失败来自 URL 校验。 |
| 来源解析 | `backend/app/literature_maps/application/paper_import_adapter.py:23-55` 在没有已证明 PDF 时调用受控 `oa_resolver`；没有 PDF 候选时返回失败。 | 第一条记录的失败发生在得到 PDF 候选之前。 |
| OA resolver | `backend/app/literature_maps/application/runtime.py:61-168` 记录 arXiv 与 Semantic Scholar 的固定诊断码；提供方限流时返回 `SEMANTIC_SCHOLAR_RATE_LIMITED`，并保留 resolver code 列表。 | `56c718...` 的 `SEMANTIC_SCHOLAR_RATE_LIMITED` 是已保存的真实 provider failure；不应在前端重写或猜测更细的原因。 |
| Bridge / 持久化 | `backend/app/literature_maps/application/import_bridge.py:63-106,283-298` 组装安全失败结果；`backend/app/literature_maps/infrastructure/store.py:2486-2535` 将 allowlist 内诊断写入 `provenance_json.import_diagnostics`。 | 新链路已经有安全诊断与持久化。`56c718...` 没有进入 importer；不涉及下载、PDF 校验、知识库写入或模型调用。 |
| 界面投影 | `frontend/literature-maps.js:3581-3604` 的 `importNode` 收到 `202` 后只读取 `payload.status`，设置 `入库状态：失败。`，再把 `download_status` 写成该字符串；没有保留 `error_code`、resolver code、`retryable` 或 `provenance`。`renderNodeDetail` 位于 `:3313-3400`，也没有渲染 `provenance.import_diagnostics`。 | 这是截图中“只有失败、没有原因/恢复”的直接根因。`runNodeAction`（`:3555-3579`）只处理移除/恢复，不参与导入失败。 |

`frontend/literature-maps.js:187-224` 的 `request` 只会在非 2xx 时抛出 `LiteratureMapError`；由于导入业务失败是 202，故不会进入现有 `catch` 分支。这解释了为什么后端诊断已存在，界面仍只显示通用失败。

## 最小同 Spec 修复方案

修复应保持在 Spec-043 已确认的节点导入反馈范围内，优先由前端 Agent 完成；本诊断 Agent 不修改前端。

1. 在 `importNode` 中统一投影 202 body：保留 `status/download_status`、`document_id`、`paper_id`、`error_code`、`resolver_code`、`resolver_codes`、`retryable`，并合并到当前节点的安全状态或 `provenance.import_diagnostics`。不要把 `source_url` 当作 PDF URL，也不要把 provider 原始异常文本写入界面。
2. 在 `renderNodeDetail` 中同时读取 POST 返回的诊断和重新打开节点时已有的 `node.provenance.import_diagnostics`。使用固定错误码到用户文案的 allowlist 映射；至少对 `SEMANTIC_SCHOLAR_RATE_LIMITED` 显示“提供方暂时限流”及“可重试”，并保留代码供排查。
3. 对 `retryable=true` 显示明确的人工“重试”入口，复用现有受控导入请求并保持空 body；禁止自动重试、直接下载 landing URL 或让用户输入 provider URL。重试后的状态仍以节点 GET/POST 的服务端结果为准。
4. 对 `2e35...` 这类没有诊断字段的旧记录显示“失败原因未记录”，不得显示伪造的 `PDF_NOT_FOUND` 或其他码；可以提供一次人工重新提交以获取新诊断，但不应把旧历史结果标记成可恢复或不可恢复。
5. 成功变为 `indexed` 时清除失败诊断并显示实际 `document_id`；失败时保留诊断，避免再次渲染节点详情后丢失。

后端 resolver、下载/导入链和 SQLite schema 不需要为这个 UI 问题改动。当前 API 已提供足够的固定码；若实现者认为必须增加 human message，也只能使用后端既有 allowlist，不能透传原始异常或 URL，且应另行说明扩大后端范围的理由。

## 明确不做

- 不对 `56c718...` 或 `2e35...` 发起 POST 重试，不下载论文，不调用 Semantic Scholar/arXiv 或其他网络 provider，不调用模型。
- 不修改节点状态、`provenance_json`、地图 job/event 或生产数据库，不做历史诊断回填，不启动/停止/重启服务。
- 不改变 `import_bridge` 的 resolver 顺序、PDF 验证、身份冲突规则或知识库导入契约。
- 不把旧材料中的 `PDF_NOT_FOUND` 当作 `2e35...` 当前可验证的失败原因，也不声称当前服务已经恢复。
- 本任务不修改 `frontend/**`、`backend/**`、Spec、评审文件或状态台账；前端修复和后续验收由根 Agent 编排。

## 精确验证方案

### 实现后的定向前端验证

在既有 `tests/frontend/test_frontend_literature_map_contract.py` 中增加或扩展同一能力的契约测试（测试名称按被测能力命名，不带 Spec/Task 编号）：

1. 用模拟的 `POST /imports` 202 body：
   `status=failed`、`download_status=failed`、`error_code=SEMANTIC_SCHOLAR_RATE_LIMITED`、`resolver_code` 同值、`resolver_codes` 含两个固定码、`retryable=true`。断言界面显示安全的限流原因和可重试提示，不显示原始异常或把 Semantic Scholar landing URL 当 PDF。
2. 用节点 GET body 的 `provenance.import_diagnostics` 重开详情，断言刷新/重新选择节点后诊断仍可见，且失败状态没有被降级成只剩“失败”。
3. 用没有 `import_diagnostics` 的 `2e35...` fixture，断言显示“原因未记录”类文案，不凭空渲染 `PDF_NOT_FOUND`，并保留人工重新提交入口。
4. 用 `status=indexed` 和 `document_id` 的成功 body，断言失败诊断被清除、知识库实体 ID 可见。

只涉及前端时运行：

```text
.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py
```

若后续实现确实触碰后端，再追加精确后端回归，而不是全量回归：

```text
.venv/bin/python -m pytest -q tests/literature_maps/test_map_import_bridge.py tests/literature_maps/test_map_api_errors.py tests/literature_maps/test_map_store.py
```

### 收口前的真实 API 验收（需根 Agent 另行授权）

代码测试通过后，根 Agent 才可在 provider/network 条件明确、用户允许重试时，对一个失败节点执行一次真实 `POST /api/literature-maps/{map_id}/nodes/{node_id}/imports`，随后用 `GET` 节点轮询一次最终状态。验收材料应记录请求、响应、节点 ID、最终 `download_status`、`document_id`（成功时）或 allowlist 诊断（失败时）及产物路径；不得用 mock、内部函数或自动重试替代真实 API。该步骤不属于本次只读诊断，当前未执行。

## 已执行的只读检查

- `GET /api/health` 返回 200；运行服务为当前部署版本。
- `GET /api/literature-maps?limit=100`、五张地图的 graph GET、两条失败节点 GET 均成功。
- SQLite 仅以 URI `mode=ro` 连接并设置 `PRAGMA query_only=ON`；没有 store 初始化、写事务或状态变更。
- 初始只读诊断阶段未发送 POST/PUT/PATCH/DELETE；后续经授权的唯一一次目标节点 POST 及一次官方 arXiv metadata GET 已在追加 E2E 报告中单独记录。全程未访问外部下载接口或 Semantic Scholar 搜索/Reader，未调用模型。

## 追加只读根因核实（真实导入后）

后续在用户/根 Agent 明确授权下，目标旧节点仅执行了一次真实导入 POST；该次 POST 已在 [Task09 导入 E2E 报告](task-09-import-api-e2e.md) 中记录。为解释其中的 `ARXIV_IDENTITY_CONFLICT`，本次没有再次导入或下载，只对官方 arXiv metadata endpoint 执行一次 GET：

```text
GET https://export.arxiv.org/api/query?id_list=1809.07041&start=0&max_results=1
HTTP 200
```

返回 `1809.07041v1`，标题为 `Exploring Visual Relationship for Image Captioning`，年份为 2018，作者为 `Ting Yao / Yingwei Pan / Yehao Li / Tao Mei`。节点值为标题同值、年份 2018、裸 ID `1809.07041`、作者 `TingYao / Ying-WeiPan / Ye-HaoLi / T.Mei`。

现有 adapter 的可复核比较为：

- `normalize_arxiv_id("1809.07041")` 与返回的 `1809.07041v1` 通过 `arxiv_identity_matches` 匹配；不是 ID 解析错误。
- `normalize_title` 后标题完全一致（`title_score=1.0`），年份一致。
- 作者前三项规范化后分别相同；`T.Mei` 规范化为 `tmei`，`Tao Mei` 规范化为 `taomei`。作者交集为 `3/4=0.75`，低于 `AUTHOR_THRESHOLD=0.80`，`_parse_feed` 因此将同一 exact arXiv ID 标记为 metadata conflict 并返回 `ARXIV_IDENTITY_CONFLICT`。

结论：证据支持这是同一论文被作者缩写门禁误拒，不是不同论文，也不是 arXiv ID 解析错误；随后出现的 `SEMANTIC_SCHOLAR_RATE_LIMITED` 是独立 provider 失败。最小后续修复应由 backend-dev 在不放宽 exact ID、标题/年份门禁的前提下，增加保守的“首字母 + 相同姓氏”匹配（仅覆盖 `T.Mei` ↔ `Tao Mei` 形态），并补 adapter 回归测试；本诊断不改业务代码。

追加证据（同一唯一 run）：[evidence.json](task-09-runs/20261024-160056-task09-import-api/evidence.json)。

## 最终修复复验状态

原失败诊断后，最终修复已部署。对同一节点先 GET 确认仍未 indexed，再只发送一次真实导入 POST；本轮返回 HTTP `202`、`status=indexed`、`download_status=indexed`、`document_id=ae3a1c3f7ee746bba031b06306ff3230`。后置 GET 与知识库摘要确认：PDF `application/pdf`、`source_immutable=true`、v1 `indexed/progress=100`、`chunk_count=66`，source HEAD HTTP 200 且长度 3088287 bytes；失败诊断已清除。原失败 run 未覆盖，新证据见 [最终 run evidence.json](task-09-runs/20261024-204558-task09-import-api-final/evidence.json)。

v2 chunker 摘要仍为既有 `pending/progress=16`，本次验收明确以 v1 导入/索引为成功标准；服务返回不是 `partial`，没有触发额外重试。

## Full gate 接缝诊断（只读，2026-10-24）

本节只核对现有安全 inspection/reindex/generation 发布链和论文导入调用链；没有执行 inspection、reindex、嵌入、模型、网络、数据库/manifest 写入或代码修改。

### 当前文档的真实阻塞

目标文档 `ae3a1c3f7ee746bba031b06306ff3230` 的只读 `papers.json` 记录为：

- `schema_version=knowledge-document-v1`、`status=indexed`、`source_immutable=true`；
- `source_sha256=d923185e9e7a8887b2a10f7f6f9041cd7182fb63a6cd6b603aefc78d07394644`；
- `source_hash_state=legacy_unknown`、`indexed_source_sha256=null`；
- v1 `indexed / progress=100 / chunk_count=66`，v2 当前也为 `indexed / progress=100 / chunk_count=51`；
- `data/kb/manifests/ae3a1c3f7ee746bba031b06306ff3230/v1.json` 与 v2 manifest 均不存在，claim/tombstone 也不存在。

因此当前 `GET /api/literature-maps/9b1e4739443e40c98400cfb69aec1e45/nodes/2e35b888d3cb414090e2d8e55e5bae1a/analyses` 仍只返回 `available_evidence_levels=["abstract"]`、`fulltext_ready=false`、`source_versions.full=null`。这不是旧的 `fullready` 文档证据；本目标的 full gate 仍未通过。

当前 `data/kb/index-generation.json` 存在且为 `index-generation-v1`，绑定 alias `papers_rebuild_38efa91a33154fd097c61d1c745d408f`。它只证明有代际标记；每次 reindex 仍会重新校验 metadata/manifest digest 和 generation，不能因此手写或放宽 gate。

### 现有合法恢复动作（本轮未执行）

唯一适合补齐当前 canonical 文档派生状态的现有公开动作是：

```text
POST /api/kb/documents/ae3a1c3f7ee746bba031b06306ff3230/reindex
Content-Type: application/json

{"chunker":"v1"}
```

路由在 `backend/app/api/routes_kb.py:887-936`，实际安全提交在 `backend/app/knowledge_base/application.py:810-858`：

1. 文档必须仍是 `knowledge-document-v1` canonical record，原件文件必须存在；
2. 服务端重新计算原件 SHA-256，必须等于记录中的 `source_sha256`，不接受调用方提供的 hash；
3. `FinalizeBundleStore.require_generation()` 必须通过，且目标代际/collection 仍然有效；
4. `chunker` 只能是 `v1`、`v2` 或 `all`。本目标只需 `v1`，避免无关的 v2 工作。

成功提交的预期是 HTTP `202`，body 形如 `{"task_id":"...","document_id":"ae3a...","chunker":"v1","status":"queued","progress":0}`，并带 `Location: /api/kb/documents/{document_id}/inspection`、`Retry-After: 2`。这是排队确认，不是全文成功；随后应低频 GET inspection，直到读取到真实 manifest，再重新 GET 节点 analyses 确认 `fulltext_ready=true` 和 `available_evidence_levels` 含 `full`。

必须保留并报告以下可恢复错误，不得手写修正：`SOURCE_HASH_MISMATCH`（409）、`SOURCE_NOT_FOUND`/`DOCUMENT_NOT_FOUND`（404）、`INDEX_ALREADY_RUNNING`（409）、`CHUNKER_UNSUPPORTED`（400）；generation marker 缺失时 `_require_generation` 返回 `INDEX_REBUILD_REQUIRED`（通常 409），代际摘要失配或队列层不可用则可能是 `INDEX_FINALIZE_REQUIRED`/`QDRANT_UNAVAILABLE`（503）。若 manifest 生成后是 `partial`/`failed`，full gate 仍应保持阻塞，不能伪造 ready。

`GET /api/kb/documents/{document_id}/inspection?chunker=v1` 不是当前状态下的纯读探针。`backend/app/api/routes_kb.py:713-886` 在 manifest 缺失且文档有 source hash 时会调用 `submit_document_reindex`；没有 hash 时还会 claim manifest。因此它只能在显式 reindex 已获授权并排队后作为轮询，不能作为本轮诊断动作或第一步恢复动作。

没有可供调用方直接“发布 manifest/source hash”的 HTTP API。manifest 由 `InspectionManifestStore` 写入，`FinalizeBundleStore` 只在受控 generation finalize/refresh 中维护 live marker；全库 `rebuild_index --confirm-replace` 是独立的代际替换维护流程，不是当前单文档缺口的必要修复。禁止直接改 `papers.json`、manifest 或 index marker。

### 实际 import_candidate 接缝

安全下载边界本身没有被绕过：

- `backend/app/literature_maps/application/runtime.py:26-58` 将服务端选出的 `pdf_url` 交给既有 `import_candidate`；
- `backend/app/paper_discovery/application/paper_import.py:447-589` 负责安全下载、校验 PDF、计算 `source_sha256`，再构造 `PaperImportRequest`；
- `KnowledgeBasePaperImportAdapter.import_paper` (`backend/app/knowledge_base/application.py:1245-1430`) 先调用 `create_immutable_document`，这一步确实写出了完整 canonical record（`source_sha256`、`indexed_source_sha256=null`、`source_hash_state=legacy_unknown`）。

缺口在 canonical record 创建之后：`import_paper` 在 `application.py:1343-1361` 重新构造只含旧字段的 `PaperRecord`，没有把 canonical `source_sha256`、显式 `document_id`、`media_type`/schema 字段传给默认 indexer；随后 `:1161-1222` 把这个 legacy object 交给 `GenerationBoundIndexPort.index_document`。`record_id()` 会从 `paper_id` 兜底得到 ID，但 `_build_index_bundle()` (`backend/app/knowledge_base/infrastructure/index.py:384-417`) 取不到 `source_sha256`，返回 `None`，于是 `index_paper_chunker()` (`:597-750`) 走 legacy 分支：只更新 v1/v2 chunker 状态为 indexed，不进入 `_publish_manifest_and_state()`。

严格 canonical 路径本来已经存在：`submit_document_reindex()` 直接把完整 document mapping 传入 generation-bound indexer；`_publish_manifest_and_state()` (`index.py:516-580`) 会从实际送入索引的 chunks 生成 manifest，并在同一发布锁下写入 `indexed_source_sha256=source_sha256`、`source_hash_state=verified`，刷新并验证 generation digest。HTTP 上传路径在 `routes_kb.py:592-626` 也复用这个显式 reindex 路径，所以该缺口特指 `import_candidate → KnowledgeBasePaperImportAdapter` 的输入重建，不是 source 下载安全链或 full gate 设计问题。

结论是：当前文档可以由一次经授权的 `POST .../reindex` 合法修复派生状态；但若不修复上述输入接缝，今后每个走默认 `import_candidate` 的新论文都可能出现“v1/v2 indexed、`legacy_unknown`、无 v1 manifest、full 不可用”的同型状态。最小同 Spec-043 修复应是让默认 paper-import indexer 保留并传递 canonical document 的 `document_id`、`source_sha256`、`media_type`（或直接传递 canonical mapping），使其走已存在的 strict bundle/manifest publication；不得放宽 full gate 或手写状态。

### 最小后续与精确验证

1. 根 Agent 另行授权后，对本 document 仅执行一次 `POST .../reindex`、body `{"chunker":"v1"}`；本轮未执行。
2. 只读轮询该 operation 的 inspection 结果，要求 manifest 的 `document_id/chunker`、`source_sha256`、`indexed_source_sha256` 全部一致，`source_hash_state=verified`、`status=ready`、`progress=100` 且有 `index_fingerprint`；同时确认 papers record 的 v1 状态仍为 indexed/100、indexed hash 等于 source hash。
3. 再 GET 节点 analyses/source_status，只有 `fulltext_ready=true`、`available_evidence_levels` 含 `full` 才算 source gate 闭环；否则按实际 code/manifest 状态报告 blocked，不发送分析 POST。
4. 代码接缝修复后，增加一条默认 paper-import 集成回归：用真实 canonical document 进入默认 indexer，断言 v1 产出 `inspection-manifest-v1`、hash verified/indexed hash 相等、generation digest 可读；同时保留 `tests/kb/test_kb_document_routes.py` 中 reindex 202/错误码契约。不得用手写 papers/manifest fixture 代替这条调用链断言。

本节没有产生新的成功 artifact；当前唯一真实成功仍只是 `PASS_INDEXED_V1` 导入复验，不能替代 full gate 验证。
