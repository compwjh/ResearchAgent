# Spec-043 Task09 知识库导入真实 API E2E

## 结论

**BLOCKED（可恢复失败，不能报告成功）。** 按授权对既有地图节点只发送了 **一次** `POST /imports`，HTTP `202`，业务结果为 `failed`。失败发生在 OA/provider 解析阶段：官方 arXiv 元数据核对证明论文 ID、标题和年份一致，但现有严格作者门禁把节点作者缩写 `T.Mei` 与官方 `Tao Mei` 判为不一致，触发 `ARXIV_IDENTITY_CONFLICT`；随后 Semantic Scholar 返回 `SEMANTIC_SCHOLAR_RATE_LIMITED`。服务将最终失败标记为 `retryable=true`，但没有 PDF 候选、没有下载、没有知识库索引实体。

POST 后唯一一次节点 GET 已确认：

- `download_status=failed`
- `error_code=SEMANTIC_SCHOLAR_RATE_LIMITED`
- `resolver_codes=[ARXIV_IDENTITY_CONFLICT, SEMANTIC_SCHOLAR_RATE_LIMITED]`
- `retryable=true`
- `document_id=null`、`catalog_paper_id=null`
- arXiv、DOI、Semantic Scholar ID 和 landing `source_url` 均未被改写

这是“作者元数据门禁误拒 + provider 限流”叠加形成的真实、可恢复失败；没有登录/权限绕过，也没有匹配不确定时的假成功。后续必须先修复并验证匹配逻辑、再等待 provider 条件恢复并由用户授权人工重试，不能自动重试或把本次结果写成成功。

## 运行边界与目标

- Spec/Task：`043` / `09`
- 角色：backend-tester；本次是部署版本真实 API 验证，不是代码修改。
- 服务：`http://127.0.0.1:8000/`，使用当前运行服务。
- 目标地图：`9b1e4739443e40c98400cfb69aec1e45`
- 目标节点：`2e35b888d3cb414090e2d8e55e5bae1a`
- 固定身份：arXiv `1809.07041`；DOI `10.1007/978-3-030-01264-9_42`；Semantic Scholar `0000fcfd467a19cf0e59169c2f07d730a0f3a8b9`
- 既有来源身份 URL：`https://www.semanticscholar.org/paper/0000fcfd467a19cf0e59169c2f07d730a0f3a8b9`。该 URL 只作为来源身份，未被当作 PDF 下载地址。
- 允许的写操作：目标节点一次导入 POST；禁止修改 metadata、allowlist、数据库、其他节点或其他地图。

本次没有改业务/测试代码、没有调用模型、没有部署或重启服务、没有直接写 SQLite，也没有清理任何数据。

## 请求轨迹与真实结果

| 顺序 | 请求 | HTTP | 脱敏结果 |
|---:|---|---:|---|
| 1 | `GET /api/literature-maps/9b1e4739443e40c98400cfb69aec1e45/nodes/2e35b888d3cb414090e2d8e55e5bae1a` | 200 | 预检确认 `download_status=failed`、无 `document_id`/`catalog_paper_id`、`import_diagnostics=null`；三种外部身份与授权目标一致。 |
| 2 | `POST /api/literature-maps/9b1e4739443e40c98400cfb69aec1e45/nodes/2e35b888d3cb414090e2d8e55e5bae1a/imports`，body `{}` | 202 | `status=failed`、`download_status=failed`、`error_code=SEMANTIC_SCHOLAR_RATE_LIMITED`、`resolver_code=SEMANTIC_SCHOLAR_RATE_LIMITED`、`resolver_codes=[ARXIV_IDENTITY_CONFLICT, SEMANTIC_SCHOLAR_RATE_LIMITED]`、`retryable=true`；实体 ID 均为 `null`。这是唯一一次 POST。 |
| 3 | 同一节点 GET | 200 | `provenance.import_diagnostics` 已持久化同一错误码、resolver codes 和 `retryable=true`；source URL 与 external IDs 不变。 |

完整脱敏证据见：[evidence.json](task-09-runs/20261024-160056-task09-import-api/evidence.json)。

## 追加只读核实：`ARXIV_IDENTITY_CONFLICT` 的最小比较 diff

为区分“不同论文”与“现有匹配逻辑误拒”，本次在导入 POST 之后没有再调用任何 provider，只对官方 arXiv metadata endpoint 发起一次 GET：

```text
GET https://export.arxiv.org/api/query?id_list=1809.07041&start=0&max_results=1
HTTP 200
```

返回的脱敏元数据为：entry `1809.07041v1`；标题 `Exploring Visual Relationship for Image Captioning`；年份 `2018`；作者 `Ting Yao / Yingwei Pan / Yehao Li / Tao Mei`。没有请求 PDF，也没有调用 Semantic Scholar；完整字段见同一 run 的 `arxiv_metadata_probe`。

| 比较项 | 节点值 | 官方 arXiv 值 | 现有逻辑结果 |
|---|---|---|---|
| arXiv ID | `1809.07041` | `1809.07041v1` | `normalize_arxiv_id` 后由 `arxiv_identity_matches` 判定相同；裸 ID 允许匹配返回版本。 |
| 标题 | `Exploring Visual Relationship for Image Captioning` | 同值 | `normalize_title` 后完全相同，`title_score=1.0`，高于 `TITLE_THRESHOLD=0.90`。 |
| 年份 | `2018` | `2018` | 相同。 |
| 作者 | `TingYao`、`Ying-WeiPan`、`Ye-HaoLi`、`T.Mei` | `Ting Yao`、`Yingwei Pan`、`Yehao Li`、`Tao Mei` | 前三项规范化后相同；`T.Mei -> tmei`、`Tao Mei -> taomei` 不同，交集 `3/4=0.75`，低于 `AUTHOR_THRESHOLD=0.80`。 |

代码证据为 `backend/app/paper_discovery/infrastructure/arxiv_adapter.py:77-98,251-290`：当 exact arXiv ID 已匹配、但标题/年份/作者门禁不通过时，`metadata_conflict=True`，结果码为 `ARXIV_IDENTITY_CONFLICT`。因此这不是 arXiv ID 解析错误，也不是不同论文；证据充分支持同一论文被作者缩写的严格比较误拒。Semantic Scholar 限流是随后独立的 provider 失败，不能掩盖这个本地匹配问题。

### 交根 Agent 的最小修复路径（本次不实现）

应由 backend-dev 另开窄修复任务：保留 exact arXiv ID、标题和年份门禁，仅增加保守的“首字母 + 相同姓氏”作者匹配（例如 `T.Mei` ↔ `Tao Mei`），不得退化为只比较标题/年份或任意模糊作者匹配；补充一个官方元数据形状的 adapter 回归测试，确认返回 `1809.07041v1` 时不再产出 `ARXIV_IDENTITY_CONFLICT`。修复后才可在 provider 条件恢复且用户再次授权时安排新的真实导入验证；本次不重试、不取 PDF、不改代码。

## 阶段判定

| 阶段 | 判定 | 依据 |
|---|---|---|
| 来源身份与安全校验 | PASS（身份未改写） | 前置/后置 GET 的 arXiv、DOI、Semantic Scholar ID 与 source URL 一致。 |
| 官方 PDF / prepublication PDF 候选 | 未产生可交付候选 | 服务最终没有返回 PDF candidate；本报告不臆测未暴露的 provider 内部响应。 |
| 严格 arXiv 回退 | BLOCKED | `ARXIV_IDENTITY_CONFLICT`，不能放宽匹配或覆盖论文身份。 |
| Semantic Scholar OA 回退 | BLOCKED（可恢复） | `SEMANTIC_SCHOLAR_RATE_LIMITED`；按固定语义可有限退避，但本次不得重复请求。 |
| 下载与 PDF 校验 | 未进入 | `pdf_candidate_observed=false`，无下载记录、无 PDF 校验结果。 |
| 知识库导入/索引 | 未进入 | `document_id=null`、`catalog_paper_id=null`，无产物路径。 |
| 失败诊断持久化 | PASS | POST 返回诊断，后置 GET 在 `provenance.import_diagnostics` 中读回相同 allowlist 字段。 |

## 安全与固定链路核对

导入 POST 沿用服务端现有受控链路，不直接调用 provider 或下载工具。技能要求的顺序为：官方 PDF/prepublication PDF → 严格 arXiv → Semantic Scholar API 返回的 OA PDF；只有固定 allowlist 主机、身份匹配且 PDF 校验通过才允许进入导入工具。追加根因核实时只对官方 arXiv metadata endpoint 进行了上述一次 ID 查询，没有调用 Semantic Scholar；导入阶段没有抓取 Semantic Scholar 搜索页/Reader 页面，没有绕过登录或付费墙，没有新增主机或放宽 allowlist，也没有输出凭据、Cookie、Token 或 Authorization。

`ARXIV_IDENTITY_CONFLICT` 不能通过改写 DOI、arXiv ID 或 source URL 解决；`SEMANTIC_SCHOLAR_RATE_LIMITED` 只说明 provider 暂时限流，服务将其保留为 `retryable=true`。因此下一次动作只能是条件恢复后的受控人工重试，不是本次自动补偿。

## 验证命令与覆盖

本次执行的是三步真实 HTTP 验证：目标节点 GET 预检 → 唯一一次空 body 导入 POST → 同节点 GET 读回。没有运行 pytest，因为本次没有代码变更，且用户授权范围限定为一次真实导入验证；不能用测试替代 provider 结果。

| 检查项 | 结果 |
|---|---|
| 预检状态与身份 | PASS |
| 唯一导入 POST | PASS（请求已受理，业务结果为失败） |
| 失败码与可恢复性 | PASS（服务返回并持久化 allowlist 诊断） |
| 下载/知识库产物 | BLOCKED（没有 PDF 候选，实体 ID 为空） |
| 重复 POST / 自动重试 | PASS（次数为 1；未发送第二次） |
| 模型、部署、直接数据库写 | PASS（均未发生） |

## 交接与下一步

- 当前节点已经从“旧失败且无诊断”变为“失败且有安全诊断”；前端 Agent 可直接用 GET 返回的 `provenance.import_diagnostics` 投影原因和“可重试”状态。
- 不要把历史 Task-03 的 `PDF_NOT_FOUND` 复写为本次结果；本次真实结果是 `ARXIV_IDENTITY_CONFLICT` + `SEMANTIC_SCHOLAR_RATE_LIMITED`。
- provider 限流解除并明确允许后，根 Agent 可安排一次新的人工重试；若仍返回匹配冲突或限流，应继续保留失败，不补假成功。
- 进展日志：[20261024-160056.md](../../../../.codebuddy/agent-logs/spec-043/task-09/backend-tester/20261024-160056.md)。

## 最终修复复验（新 run，不覆盖原失败 artifact）

Run ID：`20261024-204558-task09-import-api-final`。根 Agent 已部署最终修复（ready=true、JS v18）后，按授权先 GET 预检，再对同一节点只发送一次 POST，随后只读回节点和知识库状态。原失败 run `20261024-160056-task09-import-api` 保留不变。

**最终结论：PASS_INDEXED_V1。** 本轮真实导入 HTTP `202`，业务 `status=indexed`、`download_status=indexed`，生成 `document_id=ae3a1c3f7ee746bba031b06306ff3230`；后置 GET 确认失败诊断清除，身份未改写。

| 顺序 | 请求 | HTTP | 真实结果 |
|---:|---|---:|---|
| 1 | 目标节点 GET 预检 | 200 | 仍为 `failed`、无 document，arXiv/DOI/Semantic Scholar 身份与标题年份一致，满足唯一 POST 条件。 |
| 2 | 同一节点 `POST /imports`，body `{}` | 202 | `status=indexed`、`download_status=indexed`、`document_id=ae3a1c3f7ee746bba031b06306ff3230`；`error_code/resolver_code(s)=null`、`retryable=false`。这是本 run 唯一一次 POST。 |
| 3 | 节点 GET 后置回读 | 200 | document ID 持久化，source URL/external IDs 未变，`import_diagnostics=null`。 |
| 4 | `GET /api/kb/documents?limit=100` | 200 | 同一 document：`application/pdf`、`status=indexed`、`source_immutable=true`、`chunk_count=66`；v1 `indexed/progress=100`，无错误。 |
| 5 | `HEAD /api/kb/documents/ae3a1c3f7ee746bba031b06306ff3230/source` | 200 | `content-type=application/pdf`、`content-length=3088287`、ETag 与 source SHA-256 一致、`accept-ranges=bytes`；未读取 PDF body。现存产物本地类型核对为 `PDF document, version 1.5`。 |

产物已核对存在：`data/kb/papers/2018-Conference-Exploring-Visual-Relationship-for-Image-Captioning.pdf`，大小 3088287 bytes，SHA-256 `d923185e9e7a8887b2a10f7f6f9041cd7182fb63a6cd6b603aefc78d07394644`。v2 chunker 在摘要中仍是既有 `pending/progress=16`，本次验收口径为 v1 导入与索引；它不是本次导入的 `partial` 失败，未触发额外重试。

最终修复已消除本节点的 arXiv 作者缩写误拒：本轮响应不再包含 `ARXIV_IDENTITY_CONFLICT` 或 Semantic Scholar 限流诊断。没有直接 DB 写、没有修改 metadata/allowlist、没有第二次 POST；导入链允许的既有嵌入副作用由服务正常完成，本代理未直接调用模型。

本轮唯一脱敏证据：[20261024-204558-task09-import-api-final/evidence.json](task-09-runs/20261024-204558-task09-import-api-final/evidence.json)。

## Full 分析入口 source gate 复验（新 run，未发送分析 POST）

Run ID：`20261024-204946-task09-full-analysis-gate`。导入已经成功后，对同一 map/node 只读查询分析历史与 source gate；因为 full 不在可用 evidence levels 中，本轮没有发送 `POST /analyses`，也没有读取全文正文或模型结果。

**结论：FULL_GATE_BLOCKED。** `GET /nodes/{node_id}/analyses` 返回 HTTP 200：

```text
analyses=[]
fulltext_ready=false
available_evidence_levels=["abstract"]
source_versions.full=null
```

当前知识库文档 GET 仍为 `status=indexed`，v1/v2 均为 `indexed/progress=100`；但 full gate 还要求 canonical record 的 `source_hash_state=verified`、`indexed_source_sha256=source_sha256`，以及 `data/kb/manifests/ae3a1c3f7ee746bba031b06306ff3230/v1.json` 中的 ready manifest。只读核对到：`source_hash_state=legacy_unknown`、`indexed_source_sha256=null`，该 v1 manifest 不存在。因此 source gate 具体缺失为“来源哈希未验证 + indexed hash 为空 + v1 inspection manifest 缺失”。

代码定义的 full 请求门禁码是 `MAP_FULLTEXT_UNAVAILABLE`（默认 HTTP 409）；本轮没有 POST，所以没有实际 HTTP 错误响应、没有 analysis/job ID、没有 result length/citation/source_refs/generation 可记录。不得把 v1/v2 indexed 的 KB 状态误报为 full analysis 可用，也不得在本轮自行 inspection/reindex 或修复 manifest。

本轮脱敏证据：[20261024-204946-task09-full-analysis-gate/evidence.json](task-09-runs/20261024-204946-task09-full-analysis-gate/evidence.json)。

## Full gate 修复后真实闭环（新 run）

Run ID：`20261024-210815-task09-full-analysis-v1`。根 Agent 已部署 JS v18（PID `2252`、服务端口 `8000`）；本轮不重新导入、不下载、不修改 metadata/allowlist，不直接写 DB 或 manifest。原失败 run、`PASS_INDEXED_V1` run 和此前 `FULL_GATE_BLOCKED` run 均保留不覆盖。

**阶段结论：PASS_FULL_ANALYSIS。** 只执行了一次授权的 v1 reindex 和一次授权的 full analysis POST；source gate 已真实变为 full-ready，full analysis 进入 `completed`，结果非空且引用全部绑定目标 document。

### Reindex 与 source gate

| 顺序 | 请求 | HTTP | 真实结果 |
|---:|---|---:|---|
| 1 | `GET /api/health` | 200 | 当前服务 `status=ok`、paper discovery 可用。 |
| 2 | `GET /api/kb/documents?limit=100` | 200 | 目标 document `ae3a1c3f7ee746bba031b06306ff3230` 仍为 `indexed`，v1/v2 均为 `indexed/100%`；此前 source hash 状态未在该公开摘要中显示。 |
| 3 | 目标节点 analyses GET | 200 | reindex 前 `fulltext_ready=false`、`available_evidence_levels=["abstract"]`、`source_versions.full=null`。 |
| 4 | `POST /api/kb/documents/ae3a1c3f7ee746bba031b06306ff3230/reindex`，body `{"chunker":"v1"}` | 202 | 唯一 reindex task `d9bea649bb634c46a140b8894b8b03db`，`status=queued`、`progress=0`。响应 Location 为该 document 的 inspection 路径，Retry-After 为 2 秒。 |
| 5 | 既有文档状态 GET（低频读回） | 200 | v1 已到 `indexed/progress=100/chunk_count=66/error=null`；没有第二次 reindex。 |
| 6 | 目标节点 analyses/source_status GET | 200 | `fulltext_ready=true`、`available_evidence_levels=["abstract","full"]`；full source version 为 `70ed7281386eae343d39c479e8dec6962c8cd3954659db1e3d26b33c53aba862`。 |

只读产物核对：

- canonical record：`source_hash_state=verified`，`indexed_source_sha256` 与 `source_sha256` 均为 `d923185e9e7a8887b2a10f7f6f9041cd7182fb63a6cd6b603aefc78d07394644`；v1 `indexed/100%`。
- 原件：`data/kb/papers/2018-Conference-Exploring-Visual-Relationship-for-Image-Captioning.pdf`，3088287 bytes，实际 SHA-256 与上述值一致；本轮没有读取 PDF 正文。
- manifest：`data/kb/manifests/ae3a1c3f7ee746bba031b06306ff3230/v1.json`，`inspection-manifest-v1`、`status=ready`、`progress=100`、`source_hash_state=verified`、`index_fingerprint=840c4989f88c1f9b53f3a7ac74069fb24eed82560c56b4c1835111699d2daf2f`、66 chunks、`error=null`。
- generation：`data/kb/index-generation.json` 的 `index-generation-v1` marker 仍绑定 `papers_rebuild_38efa91a33154fd097c61d1c745d408f`；live `manifests_digest` 已包含目标 manifest。

### 唯一 full analysis 请求与终态

source gate 通过后，唯一一次请求为：

```text
POST /api/literature-maps/9b1e4739443e40c98400cfb69aec1e45/nodes/2e35b888d3cb414090e2d8e55e5bae1a/analyses
{"evidence_level":"full","idempotency_key":"task09-full-analysis-20261024-210815-v1"}
HTTP 202
```

响应创建 `analysis_id=04ff00a37f8247379878ecaf7fc6703e`、`job_id=ca2e1852b8cc49cab80300c84347c89c`，`evidence_level=full`，source version 与 source gate 一致。低频 GET 轨迹为 `queued → running → completed/finished`，`failed_units=[]`；没有重复 POST 或 retry。

最终只读取结果元数据，不读取 summary/citation 的正文：

- analysis `status=completed`、`evidence_level=full`；
- 非空 summary 长度 `592`，citations 数量 `5`；
- `source_refs=[{kind:"fulltext", document_id:"ae3a1c3f7ee746bba031b06306ff3230", chunker:"v1"}]`；
- 五条 citation 的唯一 `document_id` 和 `paper_id` 都是 `ae3a1c3f7ee746bba031b06306ff3230`；
- 最终节点 GET 仍为 `fulltext_ready=true`、`available_evidence_levels=["abstract","full"]`，full analysis 可见。

完整脱敏请求/响应摘要、状态轨迹、实体 ID、hash、manifest、generation 和产物路径见：[20261024-210815-task09-full-analysis-v1/evidence.json](task-09-runs/20261024-210815-task09-full-analysis-v1/evidence.json)。该 JSON 不含全文正文、summary、citation text、凭据或隐藏思维。

### 本阶段验收判定

| 检查项 | 判定 | 依据 |
|---|---|---|
| 当前部署健康 | PASS | health HTTP 200。 |
| 唯一 reindex 请求 | PASS | HTTP 202；task `d9bea...`；reindex POST 计数为 1。 |
| source hash 与实际原件 | PASS | canonical/indexed/manifest/实际文件四处 SHA-256 一致。 |
| 合法 v1 manifest/generation | PASS | manifest ready/100%、verified hash、fingerprint 存在，generation marker 可读。 |
| full source gate | PASS | 节点 source status 明确返回 full-ready。 |
| 唯一 full analysis | PASS | HTTP 202；analysis POST 计数为 1，idempotency key 唯一。 |
| full analysis 终态与依据 | PASS | completed、非空结果、full evidence、5 citations、全部绑定目标 document。 |
| 安全边界 | PASS | 未重新 import/download，未读取 PDF/结果正文，未直接写 DB/manifest，使用既有部署模型链完成受控分析。 |

本轮只证明后端 source gate 与 full analysis API 已真实闭环；前端地图详情的诊断投影和人工 UI 验收仍由前端 Agent/根 Agent 负责，不以本报告替代。
