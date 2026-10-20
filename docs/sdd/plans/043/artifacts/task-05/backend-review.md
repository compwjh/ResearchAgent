# Spec043 Task05 后端独立评审

日期：2026-10-20 04:02（Asia/Shanghai）
角色：backend-reviewer（只读）
范围：Task05 后端实际 diff、`analysis.py`、会话消息桥接、真实 manifest 定义、Task05 后端精准测试。
明确不做：不改业务代码或测试、不部署、不调用真实模型/provider、不读取 `.env`/secrets、不跑全量回归。

## 结论

**BLOCK（未通过）**。精准测试虽通过，但核心证据门禁与会话隔离仍有 P1 缺陷；当前结果不能进入验收或部署。

## 阻塞问题

### P1：生成完成后没有再次校验 `source_version`

- `backend/app/literature_maps/application/analysis.py:197-214` 只在检索/生成前读取一次 `source_status` 并比较 `analysis.source_version`；`analysis.py:215-225` 随后调用 `_generate`，再直接构造结果并 `finish_analysis`。
- 若模型生成期间摘要、document source hash、manifest 或 generation 发生变化，仍会把新阶段生成的文本以旧 `source_version` 持久化。违反合同中“来源在生成期间改变时重新校验，不能把新证据输出记成旧 source_version”；也可能把已解绑/过期依据写成 completed。
- 修复方向：生成返回后、`finish_analysis` 前重新读取 map/node/source status，要求 evidence level 的版本仍等于冻结版本；否则 CAS 失败为 `MAP_ANALYSIS_SOURCE_CHANGED`，不写 completed 结果。补一条 model runner 在生成期间改变 source 的精准测试。

### P1：会话没有冻结摘要快照，地图/节点删除后无法恢复摘要依据

- `analysis.py:282-285` 的 binding context 只有 `map_id`、`node_id`、`title`，以及可选 `document_id`；没有 `abstract`（也没有冻结的论文 context/hash）。
- `routes_conversations.py:1029-1069` 唯一消费 binding 的路径只读取 `context.document_id` 做 RAG；不会将 binding 的 title/abstract 注入 `compose_chat_messages`。因此 abstract 会话没有服务端可信的摘要证据输入。
- `store.py:588-605` 删除地图时删除 node/analysis/job，但保留 binding 行；保留下来的 binding 仍只有 title/document_id，若节点无 document_id 或其地图数据已删除，旧会话无法依靠快照回答原论文摘要问题，违反“地图后来解绑/删除不抹掉旧会话证据快照”。
- 修复方向：reservation 时冻结且持久化 title、abstract、external IDs、document/source snapshot 与 evidence level；消息桥接从 binding snapshot 组装上下文，不能回读已删除 `MapPaper`。

### P1：`abstract` 会话会被错误升级为全文单文档 RAG

- `analysis.py:282-285` 即使请求 `evidence_level="abstract"` 也保存 `document_id`。
- `routes_conversations.py:1029-1052` 只要 `document_id` 存在就调用 `list_documents_for_project` 和 `hybrid_search(document_ids=[...])`，完全不检查 `binding.evidence_level`、`binding.source_version` 或全文 readiness。
- 结果是摘要级会话在全文索引可见时注入全文片段；全文未通过 readiness 时也可能因 canonical project record 存在而检索。违反 abstract/full 不静默升级、每次问答核验证据级别与来源版本的合同。
- 修复方向：abstract 仅使用冻结摘要/标题 context，禁止 document RAG；full 才允许单 document 检索，并在每条消息前重新核验 owner、project、document allowlist、generation/manifest/source version。

### P1：binding 读取异常 fail-open 到项目全库

- `routes_conversations.py:1022-1027` 对 `get_literature_map_service()` 或 `get_conversation_binding()` 捕获任意 `Exception` 后把 `binding` 置为 `None`。
- 随后的 `routes_conversations.py:1034-1036` 将有 `conversation.project_id` 的会话当普通项目会话，读取项目全部文档；`routes_conversations.py:1047-1052` 再将全库 document IDs 交给 `hybrid_search`。
- 这会把 map conversation 的单论文约束转换为项目全库检索，既破坏证据隔离，也会在 store 锁、schema、连接或绑定读错误时扩大可见范围。合同要求可信 binding 失败时 fail-closed，不能偷偷退回项目全库。
- 修复方向：binding 读取失败返回稳定可观测错误/证据不足，不生成；仅在明确“无 binding 的普通会话”时走原有项目范围。补 DB 锁/读取异常测试并确认普通聊天仍保持原行为。

### P1：真实 manifest readiness 校验不完整，精准测试用 fake checker 绕过全部门禁

- 生产路径 `analysis.py:114-143` 读取 canonical project record、`FinalizeBundleStore.require_generation()` 和 `InspectionManifestStore.read(document_id, "v1")`，检查 `status=ready`、document/chunker、`source_sha256` 与 `indexed_source_sha256`；但没有要求 manifest `source_hash_state == "verified"`。
- 真实 `inspection-manifest.schema.json:217-220,258-285` 明确存在 `source_hash_state`（`verified`/`legacy_unknown`/`mismatch`）及 ready 的 `progress=100`/`index_fingerprint` 条件。实现只凭两个 hash 相等而接受，未明确拒绝非 verified 状态；ready manifest 的真实语义门禁不完整。
- `test_map_analysis_evidence.py:71-83` 传入的 `checker` 直接返回 `{"document_id":"doc-a","source_version":"source-v1","chunker":"v1"}`，完全绕过 generation、manifest schema/status、owner/project canonical record；`test_map_analysis_api.py:15-18` 又 patch 了 `MapAnalysisService.run_analysis_job`，只验证 pending handle，不执行真实全文生成/检索。
- 修复方向：生产 `_full_source` 显式要求 `source_hash_state=verified`、target chunker manifest 为 ready 且 generation marker 通过；增加真实临时 `FinalizeBundleStore` + `InspectionManifestStore` fixture，覆盖 missing/partial/mismatch/legacy_unknown/changed generation，不能只用 `source_checker` fake 作为全文门禁证据。

### P1：归档会话会被静默复用

- `analysis.py:303-308` 以 `memory.get_conversation()` 返回非空作为可复用条件，只校验 `project_id`；`MemoryRepository.get_conversation`（`backend/app/memory/repository.py:776-779`）筛除的是 `status!='deleted'`，因此 `archived` 会返回。
- 对已归档的 map conversation 再次打开会直接返回 `created=False`，不会新建 active 会话或返回冲突；违反 binding 合同中“被删、归档或手工移项目的会话不静默复活/复用”。deleted 行也会因固定预留 ID 无法插入新会话，重试可能返回 `MAP_CONVERSATION_CREATE_FAILED`，而不是新预留 ID。
- 修复方向：复用前强制 `status == "active"`；archived/deleted 绑定按失效历史处理，使用新的服务端 reservation ID 创建新 active 会话，旧 binding 保留审计快照。

## 相关错误形状与持久作业观察

- 全文 `searcher` 在 `analysis.py:205-214` 抛异常时会被 `analysis.py:226-230` 的宽泛异常处理转换为 `MAP_MODEL_FAILED`，而不是明确的 evidence/retrieval failure；这会误导重试与用户恢复提示。空召回才得到 `MAP_EVIDENCE_UNAVAILABLE`。
- stop/retry 的 CAS 结构总体存在：`store.py:770-790,1317-1355,1357-1380` 能阻止非 running 晚回调写入；但本评审未将其视为通过，因为上述 source/binding 门禁仍能在作业成功边界写入错误依据。

## 精准验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_evidence.py tests/literature_maps/test_map_conversation_binding.py tests/literature_maps/test_map_analysis_api.py` | 0 | **5 passed in 1.26s** |
| `git diff --check -- backend/app/api/routes_conversations.py backend/app/api/routes_literature_maps.py backend/app/literature_maps/application/analysis.py backend/app/literature_maps/application/runtime.py backend/app/literature_maps/application/service.py backend/app/literature_maps/domain/analysis.py backend/app/literature_maps/infrastructure/store.py backend/app/memory/repository.py tests/literature_maps/test_map_analysis_evidence.py tests/literature_maps/test_map_conversation_binding.py tests/literature_maps/test_map_analysis_api.py` | 0 | 通过 |

backend-dev 报告中的 `tests/literature_maps` **113 passed** 未在本轮独立复跑；本轮遵守只跑 Task05 精准后端测试。现有 5 项测试不覆盖上述 P1：没有生成期间来源变化、摘要快照/地图删除、abstract/full 隔离、binding 读失败、归档复用、真实 manifest/generation、跨连接并发 reservation 或真实 API/model smoke。

## 未覆盖的运行验证

- 未启动服务、未运行真实 FastAPI API E2E、未调用 Ollama/真实 provider、未执行真实 hybrid search/Qdrant 检索。
- 未验证生产 `data/literature_maps` 数据库迁移、跨进程重启、真实 stop/retry/recover 与真实 manifest/generation 变更。
- 因此本报告不声称部署可用；需要先修复 P1，再由 backend-tester 做真实 API 摘要/全文分析与 conversation bridge smoke，并保存脱敏请求、响应、job/analysis/conversation/source_version 证据。

## 最终裁定

**BLOCK。** 不能以当前精准测试通过或 backend-report 的地图域测试数量替代证据版本竞态、会话快照/隔离、fail-closed binding 和真实 manifest readiness 验证。

---

## 2026-10-21 六项 P1 集中修复窄复审

本节追加并覆盖本轮修复后的实际结论；不删除前文原始 BLOCK 证据。范围仍仅为 backend/**、Task05 后端测试与本 Task 合同；不部署、不调用真实 provider、不修改业务代码、不跑全量回归。

### 逐项结果

| 原 P1/复核项 | 结果 | 实际证据 |
|---|---|---|
| 生成后 source recheck | **PASS（单测范围）** | `analysis.py:265-281` 在 `_generate` 后重新读取 `source_status`，漂移走 `MAP_ANALYSIS_SOURCE_CHANGED`；`test_map_analysis_evidence.py:181-208` 让 model runner 改 source version，断言 failed 且不落盘 stale completed。 |
| 真实 manifest fixture/readiness | **PASS（门禁与 fixture）** | `analysis.py:115-157` 现在要求 canonical owner/project record、committed generation、`status=ready`、`progress=100`、`source_hash_state=verified`、source/index hash 相等和 index fingerprint；`test_map_analysis_evidence.py:104-178` 用真实 `FinalizeBundleStore`/`InspectionManifestStore` fixture 覆盖 missing、partial、mismatch、legacy_unknown、generation drift。未做真实 API/Qdrant smoke。 |
| 摘要快照与删图后上下文 | **PASS（上下文单测；真实问答未覆盖）** | `analysis.py:338-348` 冻结 title/abstract/external_ids/hash；`conversation_context`（159-184）不回读 map/node；`test_map_conversation_binding.py:34-56` 与 lifecycle `197-240` 删除地图后仍读出冻结摘要且 visible docs 为空。测试调用的是 context bridge，不是实际 SSE/provider 问答，故只能证明输入快照可恢复。 |
| abstract 不进 RAG | **PASS（窄链路）** | `conversation_context:171-184` 对 abstract 返回空 `visible_document_ids`；消息链 `routes_conversations.py:1145-1152` 注入冻结摘要；binding 测试及生命周期测试通过。 |
| full 每次单 document 门禁 | **BLOCK（P1）** | owner/project/document/generation/manifest/source version 每次由 `conversation_context:185-193` 重验，且 route 只传一个 document ID（`routes_conversations.py:1115-1127`）；但 context 没有返回已核验的 `chunker`，route 也未将 `chunker="v1"` 传给 `hybrid_search`，实际调用默认 `chunker=None`（`retrieve.py:139-149`），可能混入同 document 的其他 chunker 版本，违反合同的目标 chunker 隔离。 |
| binding fail-closed | **PASS（安全方向；存在普通聊天可用性回归）** | `routes_conversations.py:1023-1114` 对 binding/service/context/allowlist 异常返回稳定失败，不回退项目全库；`test_map_conversation_binding.py:76-94` 通过。由于每个普通会话也必须先调用 map service，map service 整体不可用时普通 project chat 同样失败；实现无法区分“明确无 binding”和“binding store 读失败”，与合同“普通聊天行为不变”存在 P1/P2 设计冲突，未有普通聊天回归测试。 |
| archived/deleted 重 reservation + 审计行安全 | **PASS（并发 created 标记另有 BLOCK）** | `analysis.py:350-405` 使用 `get_conversation_including_deleted`，archived/deleted 先 `retire_conversation_binding` 再新 reservation；`test_map_conversation_binding.py:58-74` 通过。`remove_conversation`（`routes_conversations.py:2022-2025`）不删除 binding 审计行；旧行改为 `superseded` 后不被 `get_conversation_binding`（仅 confirmed）返回，且 owner 过滤，不会被另一 owner 读取。新请求不会复用旧 conversation ID。 |

### 新发现的阻塞问题

#### P1：未绑定/shared-pool 地图的全文能力被修复版直接禁用

- 既有 `list_documents_for_project(None, owner_id=...)` 合法表示 owner-scoped 的 unbound/shared pool（`backend/app/knowledge_base/application.py:731-756`）；合同只规定 unbound conversation 不使用项目记忆，并未禁止 unbound map 使用已核验的共享文档。
- 修复版 `analysis.py:115-123` 以 `if not project_id or not document_id: return None` 拒绝 `project_id=None`，使未绑定地图的 `source_status.fulltext_ready` 永远为 false，即便 node.document_id 已在 owner shared pool、generation/manifest 全部 ready。
- 修复版 `analysis.py:187-193` 还要求 `get_project(binding.project_id_snapshot, owner_id)` 非空；full conversation 的 `project_id_snapshot=None` 因此永远返回 `MAP_FULLTEXT_UNAVAILABLE`，与“未绑定不使用项目记忆”混淆为“不可全文分析”。
- 该路径未被项目绑定的 fixture 覆盖；现有全文正例固定 `project_id="project-a"`（`test_map_analysis_evidence.py:78-80`）。应允许 `project_id=None` 进入 owner-scoped shared-pool allowlist，同时跳过 project instructions/memory，不扩大到其他 owner/project 文档。

#### P1：跨 SQLite 连接并发时 `created` 响应标记不确定

- `analysis.py:355` 的 reservation CAS 能保证同一 conversation ID/单 binding；但 `analysis.py:373-387` 在另一线程已用 reservation ID 创建 conversation 后，会走 existing-active 分支并返回 `created=False`，即使当前调用或另一调用实际完成了底层创建。
- 精准生命周期测试首次整组运行结果为 **18 passed, 1 failed**：`test_map_analysis_lifecycle.py:143-194` 断言 `[False, True]`，实际得到 `[False, False]`；单独重跑该测试为 1 passed，随后整组重跑为 **19 passed**，说明这是可复现窗口竞态，不是稳定绿灯。ID 和行数仍唯一，但 API `created` 语义不稳定，不能作为幂等创建结果的可靠信号。
- 应在跨库 reservation/create 流程中明确记录“本请求是否实际插入 memory conversation”，并在竞争路径返回一真一假或改为文档化的稳定语义；补多轮并发 probe 后再放行。

### 删除会话后的 binding 审计与泄露核查

- `remove_conversation` 只软删 MemoryRepository 行；不会删除 binding。该行仍可被 owner-scoped `get_conversation_binding(conversation_id, owner_id)` 读取，但正常消息入口先用 `get_conversation` 排除 deleted 会话，因此不会通过公开消息路由恢复旧上下文。
- 同一 map/node/idempotency key 再次建会话时，`get_conversation_including_deleted` 识别 deleted 状态，`retire_conversation_binding` 将旧行改为 `superseded` 并改写历史 key，然后生成新 conversation ID；已有测试覆盖 deleted 后 ID 不复用。
- 未发现跨 owner 读取路径：binding 查询包含 owner，conversation context 还校验 owner/status/project。保留审计行本身不会导致当前实现的 owner 越界或旧 ID 静默复用；但建议补一个 API-level deleted conversation message 404 + binding row 保留/新 reservation 的 smoke，当前仅有 service-level 测试。

### 本轮精准验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_evidence.py tests/literature_maps/test_map_conversation_binding.py tests/literature_maps/test_map_analysis_lifecycle.py tests/literature_maps/test_map_analysis_api.py`（首次） | 1 | **18 passed, 1 failed**：跨连接 reservation 的 `created` 断言得到 `[False, False]`。 |
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_lifecycle.py::test_concurrent_conversation_reservation_across_sqlite_connections_uses_one_id` | 0 | 1 passed（竞态窗口未出现）。 |
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_lifecycle.py` | 0 | **5 passed**（生命周期数量核实为 5）。 |
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_evidence.py tests/literature_maps/test_map_conversation_binding.py tests/literature_maps/test_map_analysis_lifecycle.py tests/literature_maps/test_map_analysis_api.py`（随后重跑） | 0 | **19 passed**；不能抵消首次并发失败。 |

### 未覆盖与最终裁定

- 未启动服务、未执行真实 FastAPI/API E2E、未调用 Ollama/provider、未执行真实 Qdrant/hybrid search；真实 API 摘要/全文问答 smoke 仍未有证据。
- 真实 manifest fixture 已在临时目录验证门禁，但不等于生产知识库 readiness；删图后的“可问答”只验证服务端 context bridge，未验证真实 SSE 消息及模型输出。
- **最终裁定：BLOCK。** 六项原 P1 的来源复核、快照、abstract 隔离、fail-closed、manifest 与 archived/deleted reservation 已有窄测试支撑；但 full 单 document 的 chunker 约束缺失、unbound/shared-pool full 被错误禁用、并发 `created` 竞态仍未解决，且首次精准测试已失败，不能 GO。

## 2026-10-21 最终窄复审（追加修复）

本节只复核上一节列出的原阻塞修复；不把旧轮次的失败结果当作本轮结果。未修改业务代码、未部署、未调用 provider、未跑全量回归。

### 原阻塞逐项裁定

| 项目 | 最终结果 | 证据 |
|---|---|---|
| `project_id=None` shared-pool 全文分析/问答 | **PASS（精确链路）** | `analysis.py:115-160` 不再拒绝 `project_id=None`，调用 `list_documents_for_project(None, owner_id=...)`；`conversation_context:190-200` 仅在有项目快照时查 project，仍执行 owner/document/source/generation/manifest 门禁。`test_map_analysis_evidence.py:215-237` 验证 source status、full reservation/context 和 owner-scoped document。未绑定路径不读取项目 instructions/memory。 |
| full RAG 的目标 chunker 贯穿 | **PASS** | `conversation_context:193-200` 返回门禁确认的 `chunker`；`routes_conversations.py:1081-1095,1149-1155` 将同一值与单 document ID 一起传入 `hybrid_search`。`test_map_conversation_binding.py:141-188` 做 route-level 捕获断言。 |
| 生成后 source recheck 与真实 manifest | **PASS（窄测试范围）** | `analysis.py:277-281` 在 `_generate` 后、`finish_analysis` 前重读 source status；`analysis.py:140-149` 检查 ready/progress/source_hash_state/document/chunker/hash/index fingerprint；evidence 测试使用真实 `FinalizeBundleStore`/`InspectionManifestStore` fixture，并覆盖 changed-generation、legacy/partial/mismatch/missing。 |
| 跨连接 reservation `created` | **PASS** | `analysis.py:396-420` 以当前请求实际插入 MemoryRepository 为 `created` 来源；8 轮跨 SQLite 连接断言同一 ID、恰好一个 true。该用例在本轮完整精确套件中通过，并以独立进程/临时库重复 3 次，均通过。 |
| binding 独立持久读取与 fail-closed | **PASS** | `routes_conversations.py:105-122` 直接读取 `LiteratureMapStore`，不调用 `get_literature_map_service` 或 provider；无数据库文件明确视为无 binding，已有数据库的构造/查询异常由 `routes_conversations.py:1047-1079` 返回 `MAP_CONVERSATION_CONTEXT_UNAVAILABLE`，不降级项目全库。普通无 binding runtime 故障回归测试和 binding 读取失败测试均通过。 |
| 删除会话 404、审计保留、同 key 新 reservation | **PASS** | `routes_conversations.py:2051-2054` 仍通过 MemoryRepository soft-delete；`test_map_analysis_api.py:15-48` 验证旧消息 GET 为 404、binding 审计行保留为 `superseded`、同 idempotency key 获得不同新 conversation ID 且新行 `confirmed`。未发现 owner 越界读取。 |

### 本轮独立精准验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_evidence.py tests/literature_maps/test_map_conversation_binding.py tests/literature_maps/test_map_analysis_lifecycle.py tests/literature_maps/test_map_analysis_api.py` | 0 | **24 passed in 2.07s** |
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_conversation_binding.py::test_concurrent_reservation_reports_actual_memory_creator_once_per_round`（独立重跑 1） | 0 | **1 passed**；内部 8 轮均 `[False, True]` |
| 同一并发精准用例（独立重跑 2） | 0 | **1 passed**；内部 8 轮均 `[False, True]` |
| 同一并发精准用例（独立重跑 3） | 0 | **1 passed**；内部 8 轮均 `[False, True]` |
| `py_compile`（4 个相关 backend 文件） | 0 | 通过 |
| `git diff --check`（相关 backend/测试文件） | 0 | 通过 |

### 未覆盖的运行验证

- 按任务边界未启动服务、未运行真实 FastAPI API E2E、未调用 Ollama/真实 provider、未执行真实 Qdrant/hybrid-search 数据检索。
- 未验证生产 `data/literature_maps` 数据库、跨进程重启或部署后真实 stop/retry/recovery；shared-pool full 本轮验证的是 owner-scoped source/context 以及受控测试接缝，不声称真实模型问答已完成。
- 以上是后续 backend-tester/验收阶段的运行验证缺口，不构成本轮已复核 P1 的阻塞。

### 最终裁定

**GO（Task05 backend 窄复审）。** 本轮未发现仍存在的 P0/P1：shared-pool `None` 语义、full chunker 单文档隔离、生成后来源复核、真实 manifest 门禁、binding 直接读取/fail-closed、跨连接幂等 `created`、删除会话 404 与新 reservation 均有实现证据和精准测试支撑。该 GO 仅表示后端窄复审通过，不替代真实 API/provider smoke、部署验证或 Spec 收口验收。
