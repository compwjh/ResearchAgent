# Spec018 Task04-D backend-tester report

## 最终最小复签（2026-09-09）

**结论：PASS（A 功能门）；Task06 production/closure debt 仍 DEFERRED/FAIL。**

- **A / Task05 功能门：PASS（Task04 backend prerequisite）。** 上轮唯一 P1 已关闭：reindex 非 object JSON 统一返回 400 `INVALID_REQUEST`；upload 缺 `file` 统一返回 400 `INVALID_REQUEST`；inspection 缺 manifest 通过真实 `InspectionManifestStore` claim，连续请求返回相同 `task_id` 并只保留一个 claim；source hash 不一致在任何状态更新前 fail-closed 为 `SOURCE_HASH_MISMATCH`，路由映射 409；未知 inspection/reindex 均在 generation gate 前返回 404 `DOCUMENT_NOT_FOUND`。上一轮 reviewer 点名的功能项均无回归。
- **B / Task06 production debt：DEFERRED / FAIL（仍阻塞 production cutover，但不阻塞 Task05 功能门）。** `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json:160-193` 仍为 `review_status=baseline_frozen`，17/17 entry=`open`、12/13 required test=`pending`；`backend/app/main.py:34-39` 仍调用 legacy `mark_interrupted_on_startup`；`backend/app/knowledge_base/application.py:234-244,265-279` 仍保留旧 task/index/delete 直连边界。生产 closure、CandidateIndexPort、rebuild/finalize/alias 等必须在 Task06 独立收口。
- 执行模型：当前任务指定的临时 `gpt-5.6-luna xhigh`。
- 执行时间：2026-09-09 19:08–19:14 +0800。
- 范围：仅 TestClient、pytest、临时目录和 no-op/Fake spies；未访问真实 `data/kb`、真实 Qdrant 或 rebuild；未修改业务代码、fixture 协议或历史评审内容。

### 最终复核证据

| 检查项 | 结果 | 证据 |
|---|---|---|
| reindex 非 object JSON | PASS | `routes_kb.py:479-487`；数组、字符串、整数均为 400 `INVALID_REQUEST`，统一含 `error_code/message/retryable/request_id` |
| upload 缺 file | PASS | `routes_kb.py:293-296`；无 multipart file 为 400 `INVALID_REQUEST`，不进入 create application |
| inspection claim/幂等 | PASS | `routes_kb.py:398-431`；临时 `InspectionManifestStore` 连续两次缺 manifest 返回相同 task ID，第二次命中 `MANIFEST_CLAIMED`，claim 文件仅一份，Retry-After=2 |
| source hash 409 | PASS | `application.py:228-237` 在 `update_chunker_state` 前校验 sha256；临时 source/metadata 不一致抛 `SOURCE_HASH_MISMATCH`，route `routes_kb.py:497-508` 返回 409 |
| unknown 优先 404 | PASS | `routes_kb.py:489-496`；未知 reindex 为 404，unknown inspection `routes_kb.py:389-397` 同样 404，均未调用 generation gate |

### 最终测试

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_document_routes.py tests/test_kb_routes.py` | 0 | `47 passed in 13.50s` |
| `.venv/bin/python -m pytest -q tests/test_kb_document_routes.py tests/test_kb_document_foundation.py tests/test_kb_routes.py` | 0 | `54 passed in 12.68s` |
| TestClient/tempfile/focused five-point probe | 0 | 5/5 通过；真实 claim、统一 400、hash 409、unknown 404 均复现；inspection 路径 embedding/Qdrant writes=0 |

### 后续动作

1. Task05 可按功能门继续；本轮无新增 Task04 功能阻塞。
2. Task06 必须继续关闭 closure matrix、startup legacy recovery、CandidateIndexPort、paper-import/rebuild/finalize/alias 生产债务，并以独立 tester/reviewer 证据更新 `review_status`。

### 交接路径

- 报告：`docs/sdd/plans/018/artifacts/task-04/backend-test-report.md`
- 本轮日志：`.codebuddy/agent-logs/spec-018/task-04/backend-tester/20260909-190822.md`

## 修订轮最新结论（2026-09-09）

**结论：FAIL（功能门仍有一个可复现的请求形状缺口；上一轮点名的固定失败已关闭）。**

- **A / Task03–05 功能门：FAIL。** 本轮 Task04 canonical/legacy route 固定样例、inspection 404/202/200+ETag/分页、reindex `400/409/202`、DELETE_PENDING headers/details、PDF/Markdown upload MIME/错误码以及旧 `test_kb_routes` 迁移均通过；但冻结统一错误体要求下，reindex JSON 数组/字符串/整数仍由 FastAPI 返回 `422 {detail:[...]}`，缺少 multipart `file` 的 upload 也返回 422 `detail`，不是 400 + `error_code`。证据为 `backend/app/api/routes_kb.py:293-294,461-466` 与下方复现命令。这不是可延期的 Task06 安全/生产债务，应补统一请求验证后才能把功能门改为 PASS。
- **B / Task06 production/closure debt：FAIL / DEFERRED。** 按用户授权，以下债务不单独阻塞 Task05 功能实现，但仍阻塞 production cutover：`upload-closure-matrix.json:160-193` 仍为 `review_status=baseline_frozen`，17/17 entry=`open`、12/13 required test=`pending`；`backend/app/main.py:34-39` 仍调用 `mark_interrupted_on_startup`；`backend/app/knowledge_base/application.py:234-244,265-279` 仍保留旧 task/index/delete 直连边界。它们不能被本轮 HTTP route 绿灯掩盖。
- 执行模型：当前任务指定的临时 `gpt-5.6-luna xhigh`。
- 执行时间：2026-09-09 18:53–19:06 +0800。
- 范围：仅 TestClient、pytest、临时目录和 no-op/Fake spies；未访问真实 `data/kb`、真实 Qdrant 或 rebuild；未修改业务代码、fixture 协议或历史报告。

### 本轮逐项结果

| 检查项 | 结果 | 证据 |
|---|---|---|
| inspection unknown / generation gate | PASS | `404 DOCUMENT_NOT_FOUND` 优先于 generation；既有未 generation 样例为 `409 INDEX_REBUILD_REQUIRED` |
| inspection building | PASS | `202 INSPECTION_BUILDING`，稳定 `task_id`、`status=building`、`progress=0`、`Location`、`Retry-After: 2` |
| inspection ready | PASS | `200` 三数组按同一页切片，`total`、opaque document/chunker cursor、ETag/304 均存在 |
| reindex invalid/running/queued | PASS（固定样例） | `{"chunker":"bad"}` → `400 INVALID_CHUNKER`；submitted=false → `409 INDEX_ALREADY_RUNNING`；成功 → `202` + `Retry-After: 2` |
| DELETE_PENDING | PASS | `503` + `Retry-After: 10`、同文档 `Location`、`details.retry_after_seconds=10` |
| upload/alias | PASS | 合法 PDF/UTF-8 Markdown `201`；MIME/扩展 `415`；坏/空 PDF `400 INVALID_PDF`；非法 UTF-8/NUL `400 INVALID_ENCODING`；50 MiB+1 `413 PAYLOAD_TOO_LARGE`；`/api/kb/upload` 已 `201` 受控转发 |
| old route migration | PASS | `tests/test_kb_routes.py` 已迁移到 canonical application seam；定向 43 项全通过 |
| malformed request shape | **FAIL / P1** | reindex JSON `[]`、`"x"`、`1` → `422 detail`；缺 upload `file` → `422 detail`，违反 Spec018:305-306 的统一 400 错误体 |

### 命令、退出码与数量

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_document_routes.py tests/test_kb_routes.py` | 0 | `43 passed in 12.67s` |
| `.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_paper_import*.py` | 0 | `390 passed, 5 warnings, 29 subtests passed in 21.58s` |
| TestClient/tempfile focused inspection/reindex/delete/upload probe | 0 | 上表固定样例全部通过；embedding/Qdrant write 计数 0 |
| malformed request-shape probe | 0（探针按观察退出） | 4 个形状均稳定复现 422 `detail`，为功能失败证据而非测试进程失败 |
| Draft 2020-12 `api-schema.json` check | 0 | schema 合法；`api-fixture-index.json` 12 fixtures 可解析 |

### 最小修复建议

1. 将 reindex body 改为可接收原始 JSON 的受控入口，或增加全局/路由级 validation handler，将非 object、缺失 multipart 文件等请求格式映射为统一 400 `INVALID_CHUNKER`/明确冻结错误码；禁止泄露 FastAPI `detail`。
2. 为上述形状补 committed tests，并同步 `api-schema.json` 的 request/error fixture 说明；只有这些测试通过后才可把 A verdict 改为 PASS。
3. Task06 继续独立收口 closure matrix、startup legacy recovery、CandidateIndexPort、paper-import/rebuild/finalize/alias 边界；本轮不把这些 production debt 伪装成已完成。

### 交接路径

- 报告：`docs/sdd/plans/018/artifacts/task-04/backend-test-report.md`
- 本轮日志：`.codebuddy/agent-logs/spec-018/task-04/backend-tester/20260909-185328.md`
- 固定交接：`docs/sdd/plans/018/artifacts/task-04/api-schema.json`、`api-fixture-index.json`、`backend-contract-report.md`、`upload-closure-matrix.json`

## 首轮结论（历史）

**FAIL**。

- `functional_verdict`: **FAIL**
- `debt_verdict`: **FAIL / DEFERRED**（旧入口、startup 和 direct-index closure 尚未完成；不能签 production cutover）
- 执行模型：`gpt-5.6-luna xhigh`（本轮临时授权）。
- 执行时间：2026-09-09 18:26:55–18:37:55 +0800。
- 范围：仅使用 TestClient、tempfile、no-op/Fake spies；未访问真实 `data/kb`、真实 Qdrant 或 rebuild，未修改业务代码。

基础 HTTP/source/upload 功能大部分可用，但 Task04-D 的硬门仍未满足：inspection/reindex/DELETE 的固定响应契约不完整，startup 仍调用旧 recovery，canonical reindex/delete 仍越过要求的 CandidateIndexPort/受控边界，且 closure matrix 仍是 baseline 状态。不能放行 Task04。

## 已通过的功能组

| 功能组 | 结果 | 证据 |
|---|---|---|
| PDF 与 UTF-8 Markdown upload | PASS | TestClient tempfile：两者均 201；BOM Markdown 保留原始 bytes/hash |
| 输入拒绝与 50 MiB+1 | PASS | 空、坏 PDF、非法 UTF-8、NUL、BOM/空白 Markdown、txt、50 MiB+1 均稳定拒绝；临时原件/metadata 未提交 |
| 同 hash 去重、同名不同 bytes、并发 create | PASS | 同 hash 返回既有 document；同名不同内容生成不同 ID；6 线程 application create 仅 1 个新记录、其余 dedupe |
| documents list | PASS（已实现部分） | limit/cursor、next_cursor、total、ETag/304 及 invalid limit/cursor 通过 |
| source GET/HEAD/304/单 Range | PASS | ETag、Content-Length、Content-Type、Accept-Ranges、HEAD 无 body、合法 206、越界/多 Range 416 均通过；8 MiB Range guard 存在 |
| generation gate / missing manifest | PASS（门禁部分） | 无 marker 为 409 `INDEX_REBUILD_REQUIRED`；有 marker 无 manifest 为 202 `INSPECTION_BUILDING`，Location/Retry-After 存在 |
| 删除正常/部分失败 | PASS（基础状态部分） | Fake delete spy 下 completed 会删除 source/metadata；vector failure 保留 source/metadata 并返回 503 `DELETE_PENDING` |
| inspection 读路径无副作用 | PASS（spy 部分） | no-op/fail-fast `get_client/embed_texts/encode_sparse/indexer` 未被 inspection/read 路径调用 |
| schema/inventory 基础一致性 | PASS（不等于 closure 放行） | `api-schema.json` Draft 2020-12 check 通过；8 个 inventory file 当前 SHA-256 与矩阵一致 |

## 阻塞问题

### P0：upload-closure matrix 与 startup/direct symbol 硬门未关闭

- `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json` 当前 `entries=17`，`open=17`；`tests=13`，`pending=12`；`review_status=baseline_frozen`。Task04-D 要求所有 entry `closed`、required test `passed`、exit code 0、证据非空、`review_status=verified`，当前完全未达到。
- 运行 TestClient lifespan 的 startup spy 观察到 `backend/app/main.py:34-39` 实际调用 `mark_interrupted_on_startup`。Spec018 closure 要求 startup 移除旧 fixed-collection/backfill/rebuild-FSM 猜测，只允许 generation marker 校验和受控 document reindex recovery；本次 `startup_does_not_call_legacy_mark_interrupted` 断言失败，调用次数为 1。
- `backend/app/knowledge_base/application.py:234-244` 的 `submit_document_reindex` 仍闭包调用 `index_paper_chunker`/`submit_index_task`，没有 CandidateIndexPort 的显式 destination/document identity 边界；`application.py:265-279` 的 delete 仍直接调用 legacy `delete_paper`，随后使用 legacy `remove_paper`。这直接违反矩阵 `index-entrypoints`、`index-task-entrypoints`、`kb-delete-route` 和 `store-source-metadata` 的 forbidden calls，不能用“HTTP route 已转发”宣称 closure 已完成。
- 建议：先完成矩阵逐 entry 的实现/静态 inventory/真实 spy 测试，再将状态和 evidence paths 更新为事实；main lifespan 不得再调用 legacy startup mutation；reindex/delete 必须经过受控 application/port，禁止 implicit live collection 和旧 metadata/source helper。

### P1：inspection 202/200 响应不满足冻结契约

- `backend/app/api/routes_kb.py:319-326` 缺 manifest 时返回 202 `INSPECTION_BUILDING`，但 body 只有统一错误体字段，没有 Spec018 要求的 `task_id`、`status`、`progress`；实际响应为 `{'error_code':'INSPECTION_BUILDING', ...}`。`Retry-After` 为 `5`，固定契约要求 `2`。
- `routes_kb.py:320-326` 只读 manifest，不提交一次幂等的 build task；重复 GET 只是重复返回 202，没有 claim/task identity。
- `routes_kb.py:327-339` 的 ready response 只返回 `{document_id,chunker,manifest,next_cursor}`，没有 required `total` 和 inspection ETag；只切 `manifest["chunks"]`，`blocks`/`anchors` 仍是全量，不满足“当前 cursor 页三类数组”。
- 有 generation marker 时请求不存在的 document 也会在 manifest 缺失分支返回 `INSPECTION_BUILDING`，而非 Spec 要求的优先 404 `DOCUMENT_NOT_FOUND`。
- 建议：在 generation gate 后先验证 canonical document/source；使用受控 claim/build task，返回稳定 `task_id/status/progress`、`Retry-After: 2`；按 document+chunker 绑定 opaque cursor 对 blocks/chunks/anchors 分页，计算 manifest ETag，并补 `total={blocks,chunks,anchors}`。

### P1：reindex 输入错误体、headers 和状态冲突不符合契约

- `routes_kb.py:342-358` 使用 Pydantic `KBReindexRequest` 直接触发默认 FastAPI 422；`POST .../reindex {"chunker":"bad"}` 实际为 `422 {"detail":[...]}`，不是统一体的 400 `CHUNKER_UNSUPPORTED`。
- 有效 reindex 202 的 `Retry-After` 在 `routes_kb.py:357` 为 `5`，Spec 固定为 `2`；没有针对 `INDEX_ALREADY_RUNNING`、`SOURCE_HASH_MISMATCH` 的实现/测试。`submit_document_reindex` 只检查 document/source 存在（`application.py:222-227`）。
- `update_chunker_state` 在 `application.py:232` 修改 metadata，而 generation marker 绑定旧 metadata hash；成功 reindex 后 marker 会失配，后续正常 inspection 将被 `INDEX_FINALIZE_REQUIRED` 关闭，缺少 marker/metadata 协同更新协议。
- 建议：统一处理 request validation；补 running/hash 状态机和 reindex response；按 finalize/generation 协议提交可验证的 metadata 状态，不能让普通 reindex 破坏 generation gate。

### P1：DELETE_PENDING 缺少固定重试 headers/details

- `routes_kb.py:361-371` 的 503 `DELETE_PENDING` 没有 `Retry-After`、指向同一文档的 `Location`，也没有 `details.retry_after_seconds`。实际 partial delete 响应只有 error body 与 tombstone 摘要。
- Spec018 要求所有可重试 503 默认 `Retry-After: 10`，DELETE_PENDING 另带删除重试 URI；建议统一补齐并测试 tombstone owner/token/idempotent retry。

### P1：分页、容量、cursor 和 manifest runtime 校验不完整

- `routes_kb.py:197-201` documents 默认 `limit="20"`，冻结契约要求默认 50；`routes_kb.py:296-302` inspection 默认 `page_size="100"`，要求默认 200。
- `routes_kb.py:149-163`/`327-339` 使用 base64 编码的裸整数 offset；没有绑定 document、chunker、schema version，违反 Spec 的跨文档 cursor fail-closed 要求。
- `build_uploaded_knowledge_document` `migration.py:311-346` 只拒绝 slash/backslash/空名；实测 303-byte `file_name` 被接受，未执行 Spec 的 UTF-8 255-byte display-name 上限。
- `InspectionManifestStore.write` `manifest_store.py:162-170` 只做 JSON Schema 校验；`x-max-serialized-bytes`、block/chunk/anchor/manifest serialized byte ceilings 没有 runtime enforcement。`x-*` annotation 不会被 Draft validator 自动执行。
- source Range 8 MiB 和 upload 50 MiB+1 本轮通过，但 upload/read/build timeout、manifest 256 MiB、单页 8 MiB 和 DTO byte limits 仍缺实现级断言。

### P1：冻结错误码存在契约冲突/遗漏

- API 实际与 `api-schema.json` 使用 `SOURCE_MEDIA_TYPE_UNSUPPORTED`、`SOURCE_TOO_LARGE`；Spec018 `:271`/`:307` 又分别写 `UNSUPPORTED_MEDIA_TYPE`、`PAYLOAD_TOO_LARGE`。此外实际的 `SOURCE_EMPTY`、`INVALID_PDF`、`INVALID_UTF8`、`MARKDOWN_PARSE_FAILED`、`CHUNKER_UNSUPPORTED` 等未完整列入 `api-schema.json.status_codes`。
- 建议在 Task04-D 前冻结单一错误码表，schema、路由、旧 alias 和测试逐字一致；不得同时保留两个名称。

### P2：legacy alias 虽受控转发，但 HTTP 契约未完全对齐

- `routes_kb.py:374-377` `/api/kb/upload` 确实只调用 `upload_document`，没有 `save_upload`；`routes_kb.py:380-393` reindex/delete 也只是转发，静态受控边界 PASS。
- 但旧 alias 未声明 `status_code=201`，实际 `/api/kb/upload` 成功为 200，而 canonical `/api/kb/documents/upload` 为 201；若 alias 是兼容契约，应明确并统一状态码/响应体，或在变更日志中明确移除时间表。

## inspection/no-write 与安全观察

- 临时 TestClient/Fake spies 观察到 inspection/list/source 读取没有 embedding、切分、Qdrant write；并发 immutable create 未覆盖 source，重复 hash 只创建一个新 source。
- DELETE 的正常路径在本轮使用 no-op `delete_paper`，未连接真实 Qdrant；因此不能将 completed 结果解释为当前 Collection vector deletion 已被真实 CandidateIndexPort 验证。
- `FinalizeBundleStore`/manifest foundation 的既有定向测试仍通过，但 API route 只消费 marker/manifest，未证明 alias、live vector、generation metadata 和 finalize failure matrix 已闭环。

## closure matrix / fixture 状态真实性

- `api-fixture-index.json` 的 6 个 fixture 与其 `tests/test_kb_document_routes.py` 结果一致，定向 route/foundation 测试共 `13 passed`；但它只覆盖 upload/list/source/未 generation inspection，未覆盖 ready manifest、inspection 202 字段、reindex、delete pending、startup、旧 route、concurrent/size 全矩阵。
- `upload-closure-matrix.json` 的 inventory revision 与 8 个文件 SHA-256 全部匹配当前文件，说明基线绑定本身没有伪造；但 17 entries 全 open、12 tests pending、`baseline_frozen` 真实反映“未完成”，不能作为 Task04-D 通过证据。

## 现有旧测试回归：不可简单忽略

命令：

`.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_paper_import*.py`

结果：退出码 **1**，`370 passed, 13 failed, 5 warnings, 29 subtests passed`。

13 项失败全部位于旧 `tests/test_kb_routes.py`，原因需明确分类：

- 4 项旧 upload 错误体/状态断言仍期待 `detail`、400；新 Spec/API 已要求统一 `{error_code,...}`，并将 unsupported/size 固定为 415/413。
- 1 项旧 upload 测试 patch `routes_kb.new_record`，canonical route 已不再暴露该旧 helper。
- 3 项旧 delete 测试 patch `routes_kb.remove_paper`，canonical delete 已迁移到 application boundary。
- 5 项旧 reindex 测试 patch `routes_kb.get_paper/submit_index_task/update_chunker_state`，旧 route-owned symbols 已移除。

这些不是应被静默忽略的“绿灯”：它们证明旧测试协议尚未迁移到新契约；应将预期替换项改写成 canonical/closure tests，并补上本报告指出的真实失败项。旧回归当前不能报整体 PASS。

## 命令与退出码

| 命令/探针 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_document_routes.py tests/test_kb_document_foundation.py` | 0 | `13 passed in 0.82s` |
| TestClient/tempfile/Fake/no-op 综合探针 | 1 | 8 组通过、4 组失败：inspection ready shape/ETag；reindex invalid body；legacy alias status；startup legacy call |
| 实际 PDF + UTF-8 Markdown TestClient upload | 0 | 两者均 201 |
| inspection 202 / invalid reindex focused probe | 0 | 202 body 缺 task/status/progress；Retry-After=5；invalid reindex=422/detail（证据输出已记录） |
| `.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_paper_import*.py` | 1 | `370 passed, 13 failed, 5 warnings, 29 subtests passed`；13 项为旧契约/旧 patch seam 失败，详见上节 |
| Draft 2020-12 check `api-schema.json` | 0 | schema 本身合法 |
| closure inventory hash/digest probe | 0 | 8/8 file hashes match；但 17/17 entry open、12/13 test pending、review baseline_frozen |

## 主 Agent 后续动作

1. 先修复 inspection 404/202/200 schema：真实、幂等 build claim/task、task/status/progress、Retry-After=2、分页 blocks/chunks/anchors、total、ETag 和 cursor 绑定。
2. 统一 FastAPI validation/error code；补 reindex running/hash conflict、generation marker 协同及固定 headers；DELETE_PENDING 补 Retry-After/Location/details。
3. 移除或受控替换 startup `mark_interrupted_on_startup`；reindex/delete 改走 CandidateIndexPort/文档 application，不调用 legacy fixed collection/index symbols。
4. 强制 file name/manifest/DTO/page/time limits，并为 413/503/数量与字节边界写真实 tempfile tests。
5. 迁移旧 `tests/test_kb_routes.py` 到新契约，不隐藏 13 个失败；补齐矩阵所有 required tests，逐 entry 更新为 `closed`，最后将 `review_status` 改为 `verified`，再重新计算 inventory revision/hash/digest。

## 交接

- 报告：`docs/sdd/plans/018/artifacts/task-04/backend-test-report.md`
- 日志：`.codebuddy/agent-logs/spec-018/task-04/backend-tester/20260909-182655.md`
- 本轮未修改业务代码、fixture 协议、真实 data、真实 Qdrant 或 Git 历史。
