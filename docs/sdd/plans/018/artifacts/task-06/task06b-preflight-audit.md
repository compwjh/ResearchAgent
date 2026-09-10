# Spec018 Task06-B 前置门禁 backend-tester 审计

## 结论

```text
result=NO-GO
closure_matrix=NOT_VERIFIED
production_cutover=BLOCKED
real_data_or_qdrant_touched=false
confirm_replace_executed=false
```

本审计只使用临时目录、`FakeQdrant`、不联网 SDK stub、现有后端测试和静态源码证据。没有读取或写入真实 `data/kb`/`data/papers`，没有连接真实 Qdrant，没有启动或停止服务，也没有执行 `--confirm-replace`。

Task04 closure matrix 的事实状态仍为：`review_status=baseline_frozen`、17/17 entry 为 `current_status=open`、13 个 required test 中 12 个为 `status=pending`。矩阵要求是所有 entry=`closed`、required test=`passed`、退出码为 0、证据非空且 `review_status=verified`；因此不能改为 `verified`，也不能放行 Task06-C/D。

## 1. Pending required tests 逐项执行

项目 `.venv/bin/pytest` 的 shebang 仍指向不存在的旧路径；为确保使用项目虚拟环境，下面的实际执行命令统一使用等价的 `.venv/bin/python -m pytest`。矩阵中的原命令和结果仍按其测试 ID 记录，不把退出 4/5 当作测试通过。

| test_id | 矩阵原命令 | 实际结果（退出码 / real） | 判定与证据 |
|---|---|---:|---|
| `T-OLD-ROUTES` | `pytest -q tests/test_kb_document_routes.py -k legacy` | **5 / 1.66s** | `17 deselected`，没有 legacy case；未执行到断言，不能关闭旧 route。 |
| `T-IMMUTABLE-CREATE` | `pytest -q tests/test_kb_document_routes.py tests/test_paper_import.py -k 'immutable or dedupe or same_name or concurrent'` | **0 / 1.47s** | `1 passed, 25 deselected`；只证明一个匹配 case，远不足以覆盖矩阵四项并发/同 ID/同 hash/同名断言，故 test 仍不可标 passed。 |
| `T-PAPER-IMPORT` | `pytest -q tests/test_paper_import.py tests/test_paper_import_batch.py` | **4 / 0.44s** | `tests/test_paper_import_batch.py` 不存在，`no tests ran`。 |
| `T-IMPORT-COMPENSATION` | `pytest -q tests/test_paper_import.py tests/test_paper_import_batch.py -k compensation` | **4 / 0.40s** | 引用的 `tests/test_paper_import_batch.py` 不存在，`no tests ran`。 |
| `T-BROWSER-BOUNDARY` | `pytest -q tests/test_paper_browser.py tests/test_paper_import_batch.py -k 'login or resume'` | **4 / 0.40s** | `tests/test_paper_browser.py` 与 `tests/test_paper_import_batch.py` 均不存在，`no tests ran`。 |
| `T-DELETE-TOMBSTONE` | `pytest -q tests/test_kb_document_delete.py` | **4 / 0.36s** | `tests/test_kb_document_delete.py` 不存在，`no tests ran`。 |
| `T-DIRECT-SYMBOLS` | `pytest -q tests/test_kb_document_boundary.py` | **4 / 0.37s** | `tests/test_kb_document_boundary.py` 不存在，`no tests ran`。 |
| `T-CANDIDATE-BOUNDARY` | `pytest -q tests/test_kb_candidate_rebuild.py -k destination` | **5 / 0.93s** | `37 deselected`，没有名为 `destination` 的匹配测试；不能据此关闭 CandidateIndexPort 边界。 |
| `T-REINDEX-BOUNDARY` | `pytest -q tests/test_kb_document_reindex.py` | **4 / 0.38s** | `tests/test_kb_document_reindex.py` 不存在，`no tests ran`。 |
| `T-BACKGROUND-INVENTORY` | `pytest -q tests/test_kb_upload_closure_matrix.py -k inventory` | **4 / 0.38s** | `tests/test_kb_upload_closure_matrix.py` 不存在，`no tests ran`。 |
| `T-STARTUP-BOUNDARY` | `pytest -q tests/test_kb_startup_generation_gate.py` | **4 / 0.39s** | `tests/test_kb_startup_generation_gate.py` 不存在，`no tests ran`。 |
| `T-REBUILD-ZERO-WRITES` | `pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_rebuild_cli.py -k 'spy or dry_run or source_hash'` | **4 / 0.37s** | `tests/test_kb_rebuild_cli.py` 不存在，`no tests ran`。 |

矩阵中的 `T-API-DOCUMENT-ROUTES` 不是 pending（matrix 已记录 `passed`、exit 0），本轮未把它冒充为新的独立验证。补充执行当前仓库中实际存在的后端安全/基础测试：

```text
.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_document_foundation.py
exit=0; 44 passed; 5.34s wall (pytest 4.68s)
```

这是隔离功能证据，不等于 closure matrix 的 12 个 pending test 已通过。

## 2. Closure matrix 逐 entry 对账

下表中的 `matrix status` 是文件当前真实值；`required tests` 是 matrix 原始映射；`audit result` 是本轮按上表实际结果和源码核对后的结论。17 个 entry 均必须继续保持 `open`，没有任何 entry 可改成 `closed`。

矩阵 schema 只有顶层 `review_status`，没有逐 entry 的独立字段；因此本表 17 个 entry 的 `review_status` 均继承当前全局值 `baseline_frozen`，不是 `verified`。每行的 required test status 见“本轮状态”列，测试命令的真实退出码见第 1 节。

| entry_id | matrix status（当前/要求） | required tests 的本轮状态 | audit result / 关键证据 |
|---|---|---|---|
| `kb-upload-route` | `open/closed` | `T-OLD-ROUTES` 未执行；`T-IMMUTABLE-CREATE` 覆盖不足 | `/api/kb/upload` 虽转发 `upload_document`，但没有 closure 测试证明完整禁止旧写路径。 |
| `kb-reindex-route` | `open/closed` | `T-OLD-ROUTES` 未执行；`T-REINDEX-BOUNDARY` 命令失败 | legacy alias 存在；canonical `submit_document_reindex` 仍调用 `index_paper_chunker`/`submit_index_task`（`backend/app/knowledge_base/application.py:238-254`）。 |
| `kb-delete-route` | `open/closed` | `T-OLD-ROUTES` 未执行；`T-DELETE-TOMBSTONE` 命令失败 | canonical `delete_document` 仍直接调用 legacy `delete_paper`（`application.py:275`），没有 CandidateIndexPort/向量删除硬门证据。 |
| `kb-route-submit-helper` | `open/closed` | `T-BACKGROUND-INVENTORY`、`T-REINDEX-BOUNDARY` 均命令失败 | required static inventory 测试文件不存在；不能证明 helper 无 source/index 直写。 |
| `paper-import-create-routes` | `open/closed` | `T-PAPER-IMPORT` 命令失败；`T-IMMUTABLE-CREATE` 覆盖不足 | 两条 import route 仍存在（`routes_paper.py:653-662`），没有 matrix-required batch evidence。 |
| `paper-import-retry-routes` | `open/closed` | `T-PAPER-IMPORT`、`T-IMPORT-COMPENSATION` 均命令失败 | retry 两个 alias 仍存在（`routes_paper.py:680-682`），owner-scoped compensation 未按 required test 验证。 |
| `paper-import-cancel-route` | `open/closed` | `T-IMPORT-COMPENSATION` 命令失败 | cancel route 存在（`routes_paper.py:699-700`），没有同 owner/token 资源清理证据。 |
| `paper-import-login-route` | `open/closed` | `T-BROWSER-BOUNDARY` 命令失败 | login route 存在（`routes_paper.py:742-743`）；无持久化写 spy 的 matrix evidence。 |
| `paper-import-resume-route` | `open/closed` | `T-PAPER-IMPORT`、`T-BROWSER-BOUNDARY`、`T-IMPORT-COMPENSATION` 均失败 | resume route 存在（`routes_paper.py:768-769`）；不得用现有单体 import 测试替代三项边界证明。 |
| `paper-import-route-helpers` | `open/closed` | `T-PAPER-IMPORT`、`T-BACKGROUND-INVENTORY` 均失败 | helper 仍存在（`routes_paper.py:422,629`）；静态 inventory 未执行。 |
| `kb-import-adapter` | `open/closed` | `T-PAPER-IMPORT`、`T-IMPORT-COMPENSATION` 失败；`T-IMMUTABLE-CREATE` 不足 | Task03 报告仍把旧 `save_upload`/同 ID 覆盖、unlink durability 留为 security debt；不能宣称适配器已生产收口。 |
| `paper-import-application` | `open/closed` | `T-PAPER-IMPORT`、`T-IMPORT-COMPENSATION` 均失败 | `paper_import.py` 的 download/dedupe/cleanup 路径没有 required owner-compensation 证据。 |
| `store-source-metadata` | `open/closed` | `T-DIRECT-SYMBOLS` 命令失败；`T-IMMUTABLE-CREATE` 不足 | `store.save_upload/save_papers/upsert_paper/remove_paper/update_chunker_state/mark_interrupted_tasks` 仍是公开函数（`store.py:145,159,227,250,387,428`）。Task03 已记录同 ID overwrite、unlink/fsync durability debt。 |
| `index-entrypoints` | `open/closed` | `T-DIRECT-SYMBOLS` 失败；`T-CANDIDATE-BOUNDARY` 无匹配；`T-REBUILD-ZERO-WRITES` 因 CLI 文件缺失失败 | legacy `index_paper/index_paper_chunker/upsert_chunks/delete_paper_chunker/delete_paper` 仍存在（`index.py:104,156,187,209,267`）；隔离 candidate 测试不能替代 closure inventory。 |
| `index-task-entrypoints` | `open/closed` | `T-BACKGROUND-INVENTORY`、`T-REINDEX-BOUNDARY` 均失败 | task symbols 仍存在（`tasks.py:43,65,93,139`）；不得据当前功能测试视为已迁移。 |
| `service-startup-index-migration` | `open/closed` | `T-BACKGROUND-INVENTORY`、`T-STARTUP-BOUNDARY` 均失败 | `main.lifespan` 仍调用 `mark_interrupted_on_startup()`（`backend/app/main.py:34-39`）；这正是 Task04 backend report 标出的生产阻塞项。 |
| `rebuild-cli` | `open/closed` | `T-REBUILD-ZERO-WRITES` 命令失败 | CLI 文件存在且 dry-run 入口可解析，但 matrix 引用的 `tests/test_kb_rebuild_cli.py` 不存在；更有 FinalizeBundle 未接入问题（见第 3 节）。 |

### Inventory hash 对账

矩阵的 8 个 `inventory_files` SHA-256 均与当前工作树匹配；按其声明的 `shasum -a 256` 排序算法重算，digest 也匹配 `960366...b2962c`。这证明 baseline 绑定未漂移，但不代表 entry 已关闭。矩阵的 `review_status=baseline_frozen` 必须保留。

## 3. Task02A/02B 生产安全债务审计

| 项目 | 本轮结论 | 证据与边界 |
|---|---|---|
| CandidateIndexPort `authorize_retire` | **FAIL（安全绕过可复现）** | 标准 `FakeQdrant`/弱 port 缺失 authorizer 的 committed test 通过，但独立临时 `PermissivePort`（`bind_candidate` 存在、`authorize_retire` 空实现、`delete_collection` 忽略 allowlist）使 `CandidateRebuildService` 返回 `completed`、删除 `papers`，alias 指向候选。说明 service 仍信任 port 的可调用方法，capability 未形成不可伪造的删除边界。相关实现：`candidate_rebuild.py:719-755`、`candidate_index.py:130-160,308-403`。未触碰真实 collection。 |
| fresh topology / action after-effect | **PARTIAL；生产未执行** | `_action` 已在 `candidate_rebuild.py:634-676` 写 before intent、after observed、fresh topology digest，unknown 会报 `ACTION_RESULT_UNKNOWN`；现有测试覆盖 create-alias post-failure、generic unknown、resume alias drift（`tests/test_kb_candidate_rebuild.py:203-217,433-446,504-517`）。但没有 real Qdrant 的 switch/retire/finalize/cleanup 全动作 before/after/unknown 矩阵，也没有真实网络中断，因此不能关闭 production debt。 |
| FinalizeBundle / generation marker | **FAIL（主链未接入）** | `FinalizeBundleStore` 的独立 marker-last/idempotency 测试通过（`tests/test_kb_document_foundation.py::test_finalize_bundle_is_idempotent_and_marker_is_last`，对应实现 `manifest_store.py:301-467`）。但 `CandidateRebuildService.__init__` 默认 `finalizer` 是 no-op（`candidate_rebuild.py:506-520`），`rebuild_index.main` 只构造 service/index，未注入 `FinalizeBundleStore`（`rebuild_index.py:46-55`）。独立 tempfile FakeQdrant confirm run 返回 `completed`，同时 `data/kb/index-generation.json` 不存在；不能把 schema/store PASS 当成 rebuild finalize PASS。 |
| Qdrant alias SDK 参数 | **PASS（不联网 stub）；生产未验证** | 当前 `QdrantCandidateIndexPort.create_alias/delete_alias` 传入 `change_aliases_operations` 的 list（`candidate_index.py:252-266`），严格 stub 测试通过（`tests/test_kb_candidate_rebuild.py::test_qdrant_alias_update_uses_api_compatible_keyword`）。没有真实 Qdrant HTTP/服务端原子性、超时、网络 after-effect 证据，故仅关闭 SDK value-shape 缺陷，不能授予 production GO。 |
| fsync / durable artifact | **PASS（candidate runtime 隔离）；manifest production 未验证** | `_fsync_directory` 将目录 fsync 失败转为 `RUNTIME_FSYNC_FAILED`（`candidate_rebuild.py:347-355`），测试注入 state/artifact/lock 三条路径通过（`tests/test_kb_candidate_rebuild.py:470-493`）。`FinalizeBundleStore`/manifest store 的故障点、跨进程恢复和真实磁盘 crash 未执行；Task03 曾记录 metadata/source copy 的 fsync/unlink debt，仍由 closure/Task06 处理。 |
| lock schema / stale recovery | **PARTIAL；正向生产恢复未执行** | lock JSON 已强制 `schema_version/run_id/owner/pid/host/token/command/started_at/heartbeat_at`，live PID 和 run-id mismatch fail closed（`candidate_rebuild.py:250-345`）；CLI 支持 `--recover-stale-lock RUN_ID`（`rebuild_index.py:24,40-45`）。当前 committed test 只证明 schema 和错误/存活 PID 拒绝（`tests/test_kb_candidate_rebuild.py:250-259`），没有死亡 PID + state/topology/action 唯一匹配的成功接管测试，也没有真实运行目录恢复。 |
| candidate validation / tamper chain | **PASS（隔离）** | 当前 `tests/test_kb_candidate_rebuild.py` 的 dense/sparse/payload/anchor/config tamper、协同 state+validation tamper、resume fingerprint 与 topology drift tests 随补充回归通过；仍只在 FakeQdrant/tempfile，不能替代真实 Qdrant/maintenance gate。 |
| Task02B source/provenance | **功能 GO；生产 DEFERRED_SECURITY_DEBT** | 最新 `source-anchor-revalidation-report.md` 明确 7/7 fixture、PDF bbox、Markdown 行号和隔离 candidate 通过；真实 Qdrant/alias/网络/生产拓扑没有执行，不能把 `production_cutover_verdict=DEFERRED_SECURITY_DEBT` 改为 GO。 |

## 4. 最小后续修复/分派建议

1. **backend-dev（CandidateIndexPort）**：把 retire 变成由 service 创建的不可转移 action capability/专用 `retire_current(run, expected_previous_target, fresh_topology)`，禁止公开 `authorize_retire(collection, ...)` 作为可被弱实现空实现的信任根；对任何不提供强制能力或不执行 capability 的 port fail closed。新增恶意/弱 port regression，证明 current collection 始终保留。
2. **backend-dev（FinalizeBundle integration）**：为 rebuild CLI/service 注入真正的 `FinalizeBundleStore.stage/commit/resume_finalize` finalizer；在 alias 已证明指向候选、metadata/manifest staged/live hash 复核后才 marker-last，marker 缺失/不一致保持 `INDEX_FINALIZE_REQUIRED`/`finalize_pending`。新增“service completed 必有 marker、finalize failure 可幂等恢复”测试。
3. **backend-dev + backend-tester（closure matrix）**：恢复或重命名 matrix 引用的缺失测试文件，逐项覆盖 17 entry；至少包括 `main.py` startup legacy mutation、reindex/delete 的 source/index write spy、paper-import batch/browser compensation、CandidateIndexPort explicit destination、rebuild CLI dry-run 全写 spy。测试全部真实执行后，才可更新 `exit_code/status/evidence_paths`。
4. **backend-dev（startup/reindex/delete）**：移除 `main.lifespan` 的 `mark_interrupted_on_startup` 旧 fixed-collection mutation；将 reindex/delete 从 `index_paper_chunker/delete_paper` 迁移到文档 application + CandidateIndexPort/受控 tombstone protocol，避免 metadata/source/vector partial success。
5. **backend-tester/reviewer（recovery/Qdrant）**：补死亡 PID 正向 stale recovery；为 switch alias、retire old collection、finalize bundle/marker、cleanup delete 分别注入 before/after/unknown，并断言 fresh topology/action digest 不漂移、不删除外部 alias target。使用当前安装 SDK 的不联网 strict stub；真实 Qdrant 仍只能在全部 closure 通过、停服和用户授权后执行。
6. **backend-dev（Task03 security debt）**：关闭或明确阻塞 same-ID `save_upload` overwrite、unlink 失败一致性、copy-source directory fsync durability、paper import owner compensation；不能用 44 个隔离测试绿灯覆盖这些入口债务。

## 5. 放行裁决

- 不得把 `upload-closure-matrix.json` 改为 `verified`；保持 `baseline_frozen`、17 open、12 pending。
- 不得执行真实 dry-run、`--confirm-replace`、alias/Collection 写删、真实 generation marker 或服务重启验收。
- 当前可确认的是：Task02A/02B 的隔离功能链大部分已通过，Qdrant SDK 参数 value-shape 和 runtime fsync 局部缺陷已有隔离证据；生产门仍因 closure matrix、FinalizeBundle 主链未接入、弱 Port retire 绕过、真实 alias/topology/recovery 未验证而 **NO-GO**。

## 审计范围与证据路径

- Task plans：`docs/sdd/plans/018/task-02a-production-provenance-foundation.md`、`task-02b-revalidate-source-anchor-feasibility.md`、`task-03-document-contract-and-migration.md`、`task-04-backend-document-inspection-api.md`、`task-06-legacy-backfill-and-resilience.md`。
- Fixed artifacts：`docs/sdd/plans/018/artifacts/task-02a/backend-test-report.md`、`backend-review-report.md`、`implementation-contract.md`、`docs/sdd/plans/018/artifacts/task-02b/source-anchor-revalidation-report.md`、`docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json`。
- Supplemental test evidence：`tests/test_kb_candidate_rebuild.py`、`tests/test_kb_document_foundation.py`。
- 本轮进度日志：`.codebuddy/agent-logs/spec-018/task-06/backend-tester/20260910-011103.md`。
