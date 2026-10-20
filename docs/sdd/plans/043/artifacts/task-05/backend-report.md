# Task05 后端交接报告：AI 分析与会话

> 角色：backend-dev ｜ 日期：2026-10-20 ｜ 状态：实现完成，等待独立 backend-reviewer/backend-tester
>
> 本报告仅覆盖 `backend/**` 与 `tests/literature_maps/**` 的本端改动；未部署、未调用真实 provider、未修改前端。

## 实际改动

- 新增 `backend/app/literature_maps/domain/analysis.py`：`MapAnalysis`、`MapConversationBinding` 与摘要/全文状态投影。
- 新增 `backend/app/literature_maps/application/analysis.py`：
  - 摘要/全文证据门禁与稳定 `source_version`；全文只接受 owner/project allowlist、canonical source hash、generation、v1 manifest 均通过的单个 document。
  - 复用 `hybrid_search(document_ids=[verified_document_id], chunker="v1")`、`compose_chat_messages`、`run_chat` 和真实 `ChatRun` 结果；空输出、空召回、来源变化均失败，不落盘 prompt/reasoning。
  - MapAnalysis 独立版本结果、幂等分析 job、崩溃恢复/stop/retry；分析 job 不改变地图 graph 状态。
  - map/node→既有 Conversation 的服务端预留 ID→幂等 create→confirm 接缝，绑定 owner/project/evidence/source snapshot。
- 扩展 `LiteratureMapStore` schema v4：独立 analysis/binding 表、owner 查询、CAS job、结果/事件落盘；删除地图清理 analysis，保留会话绑定快照。
- `MemoryRepository.create_conversation` 增加仅内部使用的 `conversation_id` 预留参数。
- 新增 `/api/literature-maps/{map_id}/nodes/{node_id}/analyses` GET/POST、`/analyses/{analysis_id}` GET、`/conversation` POST（并保留复数兼容别名）。
- 普通会话消息链检测可信 map binding；有绑定时只传单 document allowlist，无绑定行为保持原项目/未绑定范围。

## 验证命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m py_compile backend/app/literature_maps/domain/analysis.py backend/app/literature_maps/infrastructure/store.py backend/app/literature_maps/application/analysis.py backend/app/literature_maps/application/runtime.py backend/app/literature_maps/application/service.py backend/app/api/routes_literature_maps.py backend/app/api/routes_conversations.py backend/app/memory/repository.py` | 0 | 通过 |
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_evidence.py tests/literature_maps/test_map_conversation_binding.py tests/literature_maps/test_map_analysis_api.py` | 0 | 5 passed |
| `.venv/bin/python -m pytest -q tests/literature_maps` | 0 | 113 passed |
| `.venv/bin/python -m pytest -q tests/conversation/test_conversations_api.py tests/conversation/test_chat_route.py tests/conversation/test_conversation_filters.py tests/memory/test_memory_repositories.py` | 0 | 59 passed |
| `git diff --check` | 0 | 通过 |

## 产物与日志

- 精准测试：`tests/literature_maps/test_map_analysis_evidence.py`、`test_map_conversation_binding.py`、`test_map_analysis_api.py`。
- 进展日志：`.codebuddy/agent-logs/spec-043/task-05/backend-dev/20261020-033729.md`。
- 共享工作区中同时存在 frontend-dev 的未提交改动（`frontend/**` 及对应前端测试/报告），未由本角色编辑或覆盖。

## 尚未完成 / 风险

- 未运行真实模型、真实全文索引或 API E2E；原因是 Task05 指令明确禁止本角色调用真实 provider/部署，需由 backend-tester/验收阶段执行脱敏真实摘要/全文 smoke。
- 未验证生产数据库 `data/literature_maps`，未读改生产 DB；迁移仅在临时 SQLite 测试库验证。
- 需要独立 backend-reviewer 检查公开 JSON 与现有会话消息链契约，再由 backend-tester 执行精确后端验收；不应把本报告的 mock/合成模型测试当作真实 E2E。

## 评审阻塞修复追加（18:59）

根据 `backend-review.md` 的六项 P1 BLOCK，已在同一 Task 范围内集中修复：

1. `_generate` 返回后、`finish_analysis` 前重新读取 `source_status`；版本漂移只落盘 `MAP_ANALYSIS_SOURCE_CHANGED` 失败，不落盘旧依据的 completed 结果。
2. binding context 冻结 title、abstract、external_ids 与摘要 hash；abstract 会话消息链从快照注入上下文，地图/节点删除后仍可用，不回读已删除节点。
3. abstract binding 永不进入 RAG；full binding 每条消息调用服务端 context gate，重复核验 owner/project/document allowlist、generation、manifest、source version，并在 hybrid_search 前只传单 document ID。
4. binding/store 读取异常改为稳定 `MAP_CONVERSATION_CONTEXT_UNAVAILABLE` fail-closed SSE；只有明确无 binding 的普通 project conversation 保留既有 project allowlist 路径。
5. 全文 manifest gate 明确要求 `status=ready`、`progress=100`、`source_hash_state=verified`、source/index hash 一致、index fingerprint 存在且 committed generation 可验证；增加临时真实 `FinalizeBundleStore`/`InspectionManifestStore` fixture 覆盖 missing、partial、mismatch、legacy_unknown、generation drift。
6. 会话复用仅限 active；archived/deleted 会话会将历史 binding 标记 superseded 并使用新的服务端 conversation reservation，保留历史快照。删除会话不再删除 binding 审计行；project move 由 binding project snapshot mismatch fail-closed。

## 评审修复后的实际验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m py_compile backend/app/literature_maps/application/analysis.py backend/app/literature_maps/infrastructure/store.py backend/app/memory/repository.py backend/app/api/routes_conversations.py` | 0 | 通过 |
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_evidence.py tests/literature_maps/test_map_conversation_binding.py` | 0 | 13 passed |
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_lifecycle.py` | 0 | 4 passed |
| `.venv/bin/python -m pytest -q tests/literature_maps` | 0 | 122 passed |
| `.venv/bin/python -m pytest -q tests/conversation tests/memory` | 0 | 184 passed |
| `git diff --check` | 0 | 通过 |

仍未部署、未调用真实 Ollama/provider、未读取或修改生产地图数据库；真实 API smoke 与验收阶段证据仍由 backend-tester/验收角色负责。

## 2026-10-21 追加窄复审修复

针对 `backend-review.md` 追加 BLOCK 的 5 项问题，本轮仅修改 backend 与对应能力测试；未修改独立的 `test_map_analysis_lifecycle.py`。

1. shared-pool 全文：`analysis.py:115` 的 `MapAnalysisService._full_source_for_project` 仅要求 document identity，不再把 `project_id=None` 当作不可用；仍调用 `list_documents_for_project(None, owner_id=...)`，所以只允许 owner-scoped shared pool。`analysis.py:162` 的 full `conversation_context` 对 `project_id=None` 跳过 project lookup，但保留 source/generation/manifest/document gate。
2. chunker 隔离：`analysis.py:185` 的 full `conversation_context` 返回已核验 `chunker`，`routes_conversations.py:1082-1128` 将其原样传给 `hybrid_search`，不再使用默认 `None`；`test_map_conversation_binding.py:141` 补 route-level 捕获断言。
3. reservation created 语义：`analysis.py:396-420` 的 `created` 现在只由当前请求实际成功插入 `MemoryRepository` 时置 true；binding reservation 的获胜者不再错误决定响应标志。`test_map_conversation_binding.py:191` 跨 SQLite 连接 8 轮并发均得到同一 ID 且 `[False, True]`。
4. binding 读取解耦：`routes_conversations.py:105` 新增 `_read_map_conversation_binding`，直接只读既有 `LiteratureMapStore`，不启动 `get_literature_map_service`/provider；不存在 map DB 时明确视为无 binding，已存在 DB 的 store/query 异常仍返回 `MAP_CONVERSATION_CONTEXT_UNAVAILABLE` fail-closed；只有明确返回 None 才走普通 project allowlist。补 runtime 故障下普通无 binding 会话回归。
5. 删除会话 API：`test_map_analysis_api.py:15` 补临时 SQLite API smoke，删除后消息 GET 返回 404；原 binding 审计行保留，同 idempotency key 会生成新的 conversation ID 与 confirmed binding。

### 本轮验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `LITERATURE_MAP_DB_PATH=/tmp/spec043-map-review2-20261021.sqlite3 .venv/bin/python -m pytest -q tests/literature_maps` | 0 | 132 passed |
| `LITERATURE_MAP_DB_PATH=/tmp/spec043-map-review2-chat-20261021.sqlite3 .venv/bin/python -m pytest -q tests/conversation tests/memory` | 0 | 184 passed（仅 observability span batch 超时警告，无测试失败） |
| `LITERATURE_MAP_DB_PATH=/tmp/spec043-map-direct-binding-20261021.sqlite3 .venv/bin/python -m pytest -q tests/literature_maps/test_map_conversation_binding.py` | 0 | 7 passed |
| `git diff --check` | 0 | 通过 |
| `.venv/bin/python -m py_compile backend/app/literature_maps/application/analysis.py backend/app/api/routes_conversations.py backend/app/memory/repository.py backend/app/literature_maps/infrastructure/store.py` | 0 | 通过 |

仍未部署、未调用真实 provider、未执行全量回归或提交。临时测试 DB 均位于 `/tmp`，未读取或修改生产地图 DB。

## 2026-10-21 真实 GAT 全文 409 只读诊断

针对候选 `b94717c` 部署后 `55afc3b8f01445429462fe78ed0d4c98` 的 `source_status.fulltext_ready=false` / `MAP_FULLTEXT_UNAVAILABLE`，本轮只读取 KB canonical 元数据、generation marker、manifest 与本地 canonical collection 元数据；未读取 `.env`、PDF 正文，未写数据库、索引或 manifest。

### 结论

这是当前真实 KB 发布物不满足全文证据门禁，不是 generation 路径漂移或 source hash 比对 bug：

1. canonical `data/kb/papers.json` 中存在目标 `document_id`，`source_sha256=a7d811a44e1c65bf27da3a01859f23a8edbe33b8f96114b4b5066aedb078f284`，记录状态为 `indexed`。该旧 metadata 记录的 `indexed_source_sha256=null`、`source_hash_state=legacy_unknown` 不能单独证明全文 readiness；当前分析 gate 使用 owner-scoped canonical record 的 `source_sha256`，再核验 manifest。
2. generation 只读校验通过：`FinalizeBundleStore.require_generation()` 返回 `run_id=38efa91a33154fd097c61d1c745d408f`；实时 manifests digest 与 marker 的 `a0aaaba228854109707e0b56432d3816831e139fa86cccd41d3b8812f8cf8ad3` 一致，canonical alias 为 `papers -> papers_rebuild_38efa91a33154fd097c61d1c745d408f`。因此不是全局 generation/alias 门禁拒绝。
3. 目标 `v1` manifest 不存在：`InspectionManifestStore.read(document_id, "v1")` 返回 `MANIFEST_NOT_FOUND (404)`。`analysis.py:136-138` 会将该异常安全转换为 `None`，随后 `source_status` 返回 `MAP_FULLTEXT_UNAVAILABLE`。
4. 现有目标 `v2` manifest 虽有 `source_hash_state=verified`、source/index hash 均为上述 canonical hash、`progress=100` 和 fingerprint，但状态是 `partial`，`mapped_count=81`、`unmapped_count=11`、`error=HOSTILE_FEATURES_NOT_EXECUTED`；即便切换 chunker 也不满足当前严格 `status=ready` 门禁。Task05 合同明确默认目标 chunker 为既有 `v1`，代码 `analysis.py:140-148` 还要求 `ready`、100%、verified、双 hash 一致、document/chunker 一致和 fingerprint。
5. 只读 canonical collection 存在目标文档的 `paper_id` 记录，但缺失匹配的 v1 manifest 意味着该物理索引不能被本功能当作可证明的全文依据；不能用已有 `papers.json` 的 `chunkers.v1.status=indexed` 或手工把 v2 `partial` 改成 `ready` 绕过证据门禁。

### 最小恢复方向

由有权限的 KB rebuild/finalize 流程重新为该 document 发布与当前 canonical source hash 一致、`chunker=v1`、`status=ready`、`progress=100`、`source_hash_state=verified`、`indexed_source_sha256` 一致且带有效 fingerprint 的 manifest，并在真实 candidate alias/topology 校验后刷新/提交 generation marker。若 v2 仍作为目标，也必须先处理 11 个 unresolved mapping/`HOSTILE_FEATURES_NOT_EXECUTED`，不能只改状态字段。当前无需修改 Task05 代码。

### 只读诊断命令结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `git rev-parse --short HEAD` | 0 | `b94717c` |
| `.venv/bin/python -c 'FinalizeBundleStore(Path.cwd()).require_generation()'` | 0 | generation marker/metadata/manifests digest 校验通过 |
| `.venv/bin/python` 只读 `InspectionManifestStore.read(..., "v1")` / `read(..., "v2")` | 0 | v1=`MANIFEST_NOT_FOUND`; v2=可读但 `partial` |
| `jq` 读取目标 canonical record/manifest/marker 顶层字段 | 0 | 仅输出元数据计数/哈希/状态，未输出论文正文 |

## 2026-10-21 scoped v1 reindex 后续只读诊断

读取 `runs/20261021-003209-b94717c-v1-reindex/reindex-e2e.json` 及对应只读 KB 状态，未再次提交 reindex，未读 `.env`/PDF，未修改代码、数据库或索引。

### 准确状态与根因

1. artifact 记录的 POST `/reindex` 于 `00:32:38` 返回 202，`task_id=b41b7c83c071448d8fc2630d4988b093`，三次 metadata poll 都只看到 `v1 indexed/100/error=null`，最终明确记为 `blocked`；它没有声称 reindex 已达到全文 ready。
2. 该任务不是“仍缺 manifest”或仅旧 metadata：当前 `data/kb/manifests/55afc3b8f01445429462fe78ed0d4c98/v1.json` 的 mtime 为 `00:32:43`，晚于提交时间；只读读取结果为 `progress=100`、`source_hash_state=verified`、source/index hash 均为 `a7d811...f284`、fingerprint 存在、`mapped_count=57`、`unmapped_count=0`，但 `status=partial`、`error=HOSTILE_FEATURES_NOT_EXECUTED`。同时 generation marker 在同一时间刷新，`FinalizeBundleStore.require_generation()` 通过。
3. 受控 worker 确实发布了 manifest：`index.py:414-435` 构造并 `InspectionManifestStore.write()`，随后刷新 generation digest；`index.py:549-562` 在索引点写入后调用该发布路径。v1 的 `partial` 来自真实 PDF provenance：`parse.py:500-501` 在 active feature 状态为 hostile 时固定产出 `partial/HOSTILE_FEATURES_NOT_EXECUTED`，不是 map analysis 虚构的错误。
4. 因而 `source_status.fulltext_ready=false` 的直接原因是 map gate `analysis.py:140-148` 要求目标 v1 manifest `status=ready`；当前 v1 manifest 已存在但为 partial。不能把 metadata 的 `v1 indexed/100/error=null` 当成全文 ready 证据，也不能手工把 manifest partial 改成 ready。

### 两个 KB 底层边界缺陷

- `submit_document_reindex()` (`application.py:801-849`) 生成的 `task_id` 只用于 202 响应，实际 worker 使用进程内 `_running`/Future，没有可按该 ID 查询的持久终态。因此 artifact 能证明提交被接受、manifest 在提交后生成并达到 partial 终态，但不能从 task ID 查询一个正式的 completed/partial 任务状态。
- reindex worker 的 `update_chunker_state()` (`index.py:469-471,549-557` → `store.py:744-781`) 只同步 `papers.json` 的 chunker/top-level indexed 状态，不同步顶层 `indexed_source_sha256`/`source_hash_state`；所以当前 canonical record 仍是 `legacy_unknown`/`indexed_source_sha256=null`。这解释了 tester 的 metadata 观察，但不是本次 map gate 的直接拒绝条件：Task05 gate 使用 canonical `source_sha256` 加 manifest 的 verified source/index hash。

### 最小同范围修复建议（不在本角色实施）

1. KB reindex worker 应在 manifest 发布结果确定后，将 chunker 状态与 manifest 状态保持一致：`partial/HOSTILE_FEATURES_NOT_EXECUTED` 不得对外显示为 `indexed/error=null`；只有 ready manifest 才可显示 indexed/ready。对顶层 source hash 字段的同步应与既有 canonical metadata 契约一起冻结，不能以 map 代码绕过。
2. 若产品需要按 `task_id` 证明终态，应为 scoped reindex 增加持久任务状态或复用已有可查询任务记录；当前 202 task_id 不是可恢复的终态凭据。
3. GAT 要达到全文分析，仍需授权 KB 流程处理 hostile PDF provenance 并发布 `v1 status=ready` manifest；Task05 map analysis 不应放宽 gate 或把 partial 当 ready。当前不建议再次 reindex。

### 本轮只读核对结果

| 核对 | 结果 |
|---|---|
| `reindex-e2e.json` | `accepted=202`，三次 poll 后 `blocked`，未宣称 ready |
| `v1` manifest | 已存在且由本次提交后生成，但 `partial/HOSTILE_FEATURES_NOT_EXECUTED` |
| `v2` manifest | 仍为 `partial`，`unmapped_count=11`、同一 hostile error |
| generation | marker 与 manifests digest 一致，`require_generation()` 退出码 0 |
| canonical `papers.json` | `v1 indexed/100/error=null`，但顶层仍 `legacy_unknown`/indexed hash null；属于 worker metadata 同步缺口 |
