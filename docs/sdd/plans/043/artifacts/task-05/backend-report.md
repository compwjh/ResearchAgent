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
