# Task06 closure-core backend implementation report

## Scope and safety boundary

- 修复 `closure-core-review-report.md` 记载的核心阻塞：legacy index 写入口 fail-closed、CandidateIndexPort 候选边界、generation-bound reindex/delete、marker digest 协同、paper-import default consumer、startup recovery 证据和 inventory 调用图校验。
- 只使用临时目录、FakeQdrant、隔离客户端和静态源码检查；未读取或写入真实 `data/kb`，未连接真实 Qdrant，未启动生产服务，未执行 `--confirm-replace`。
- 初始实现阶段未修改 `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json`；随后主 Agent 根据独立复测与复审结果刷新了 8 个 core test 的命令、退出码、证据路径、对应核心 entry 状态，以及 inventory revision/SHA/digest。论文导入相关 entry/test 仍保持 `open/pending`，整体 review 状态未标记 `verified`。

## 实现改动

### 1. legacy index 写入口与真实 consumer

- `backend/app/knowledge_base/infrastructure/index.py` 的 `ensure_collection`、`upsert_chunks`、`delete_paper_chunker`、`delete_paper`、`index_paper`、`index_paper_chunker`、`backfill_chunker_defaults` 均要求合法、显式的 `destination_collection`，缺失时抛出稳定的 `IndexWriteBoundaryError(code="DESTINATION_COLLECTION_REQUIRED")`，不再隐式回落 `KB_COLLECTION`。
- `GenerationBoundIndexPort` 将目的地固定到应用层已验证的 generation collection；reindex/delete application 与 paper-import default indexer/deleter 不再直接调用 legacy write helper。
- `routes_kb.kb_component_status` 只读取并验证 generation marker、检查 marker 指向 collection，再对该 collection 计数；health 不再创建或写入 fixed collection。
- 真实调用者已检索并更新：paper-discovery catalog 使用显式隔离 collection；测试中的 legacy helper 调用全部补上显式 destination，未恢复危险默认行为。

### 2. candidate、reindex/delete 与 tombstone 边界

- `QdrantCandidateIndexPort.bind_candidate` 与 `FakeQdrant.bind_candidate` 共用绑定校验：候选必须匹配 `papers_rebuild_<run>` 命名，且不得等于正式 source collection 或 alias。
- `submit_document_reindex`、`delete_document` 每次都先读取并验证当前 generation marker；外部传入的 destination 只能与 marker `alias_target` 完全相等，否则返回 `INDEX_TOPOLOGY_AMBIGUOUS`，无 marker 时返回 `INDEX_REBUILD_REQUIRED`。
- 共享 tombstone 文件增加 owner/chunker 校验：其他 owner 得到 `TOMBSTONE_OWNER_MISMATCH`，同 owner 重试保持 created timestamp 并幂等移除对应 manifest；删除失败继续返回稳定 `DELETE_PENDING`。

### 3. marker hash 漂移与 paper-import

- 新增 `FinalizeBundleStore.refresh_live_digests()`，在已有 marker 时原子刷新 metadata/manifests digest，重新验证 marker；不创建 marker、不改变 alias/topology。
- canonical metadata 保存、上传创建、paper-import 写入/状态 patch、reindex chunker 状态写入以及 tombstone 成功路径均能保持已提交 generation 可恢复校验；custom test/legacy metadata 路径不触碰 marker。
- paper-import default consumer 通过 marker-bound `GenerationBoundIndexPort` 索引和删除；cleanup 使用命名的 canonical document adapter，不再直连 legacy `remove_paper`。

### 4. startup 与 inventory 证据

- startup 仍只读 KB generation gate，同时保留 paper catalog 自身的真实 recovery；新增临时 SQLite `PaperDiscoveryStore` 测试，执行 running→queued recovery，并断言 KB 目录不存在，证明 startup 不产生知识库持久写。
- inventory 测试现在逐文件比较 frozen SHA，并按当前实现重新计算 `inventory_digest`；同时用 AST 检查 application/API 是否直接导入或调用退休 write helper，以及 health 是否出现写调用。

## 固定八项矩阵命令实测（初始实现轮）

执行方式为 `.venv/bin/python -m pytest`，避免项目 pytest shebang 的历史解释器路径问题。

| test id | 命令 | exit | 实际结果 |
|---|---|---:|---|
| `T-OLD-ROUTES` | `.venv/bin/python -m pytest -q tests/test_kb_document_routes.py -k legacy` | 0 | 1 passed, 17 deselected |
| `T-DELETE-TOMBSTONE` | `.venv/bin/python -m pytest -q tests/test_kb_document_delete.py` | 0 | 3 passed |
| `T-DIRECT-SYMBOLS` | `.venv/bin/python -m pytest -q tests/test_kb_document_boundary.py` | 0 | 14 passed |
| `T-CANDIDATE-BOUNDARY` | `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py -k destination` | 0 | 1 passed, 43 deselected |
| `T-REINDEX-BOUNDARY` | `.venv/bin/python -m pytest -q tests/test_kb_document_reindex.py` | 0 | 4 passed |
| `T-BACKGROUND-INVENTORY` | `.venv/bin/python -m pytest -q tests/test_kb_upload_closure_matrix.py -k inventory` | 1 | 1 failed, 1 passed；按新测试正确暴露 frozen matrix 中 `backend/app/main.py` SHA 漂移（实际 `74b6f4…599c8`，存储 `990f1d…07e42`） |
| `T-STARTUP-BOUNDARY` | `.venv/bin/python -m pytest -q tests/test_kb_startup_generation_gate.py` | 0 | 3 passed |
| `T-REBUILD-ZERO-WRITES` | `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_rebuild_cli.py -k 'spy or dry_run or source_hash'` | 0 | 4 passed, 42 deselected |

## 相关回归与静态验证

- `.venv/bin/python -m pytest -q $(rg --files tests | rg 'test_kb_.*\\.py$' | sort) --ignore=tests/test_legacy_kb_integration.py --maxfail=20`：**377 passed, 1 failed, 5 warnings**，exit 1；唯一失败为上述 inventory frozen hash mismatch，非业务断言失败。
- `.venv/bin/python -m pytest -q tests/test_kb_services.py tests/test_kb_tasks.py`：**91 passed**，exit 0。
- `.venv/bin/python -m pytest -q tests/test_paper_import.py tests/test_kb_application_boundary.py tests/test_kb_routes.py`：**46 passed**，exit 0。
- `.venv/bin/python -m pytest -q tests/test_kb_document_delete.py tests/test_kb_document_foundation.py`：**10 passed**，exit 0。
- `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_rebuild_cli.py -k 'spy or dry_run or source_hash'`：**4 passed**，exit 0。
- `.venv/bin/ruff check backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/index.py backend/app/knowledge_base/infrastructure/candidate_index.py backend/app/knowledge_base/infrastructure/manifest_store.py backend/app/knowledge_base/infrastructure/store.py backend/app/api/routes_kb.py tests/test_kb_document_boundary.py tests/test_kb_document_reindex.py tests/test_kb_document_delete.py tests/test_kb_startup_generation_gate.py tests/test_kb_upload_closure_matrix.py tests/test_paper_import.py`：exit 0，`All checks passed!`。
- `.venv/bin/python -m py_compile`（上述 backend 实现与本轮涉及测试）：exit 0。
- `git diff --check`：exit 0。

## 独立复测与复审

- backend-tester：8/8 core 命令 exit 0，137 项选定回归通过，全部 `test_kb_*.py`（排除历史 legacy integration）378 项通过；未接触真实 data/kb、Qdrant 或服务。
- backend-reviewer：`isolated_core_closure=GO`，新增 P0/P1 为 0，允许提交 core closure；`production_cutover=NO-GO`。
- matrix inventory 在刷新 frozen SHA/digest 后通过；matrix 仍因论文导入 4 个 required test pending 而保持整体未验证。

## 风险、阻塞与主 Agent 后续动作

- **当前收口阻塞：** 论文导入四项 required tests（同 ID 不可变创建、单/批/重试/续传、owner/token 补偿、浏览器边界）仍 pending；整体 matrix 尚未 `verified`。core matrix 的 inventory files、digest、revision 已按独立复测事实刷新。
- `tests/test_legacy_kb_integration.py` 仍依赖已退休的旧 route patch seam（期望 `routes_kb.KB_PAPERS_DIR`），未为恢复危险 legacy 行为而修改；若要保留该历史回归，应由主 Agent 另行决定迁移到 canonical application seam。
- 未验证真实 Qdrant SDK/network after-effect、真实 alias/topology、真实 stale-lock recovery、服务启动和生产 metadata；这些仍属于 Task06-C/D 的前置门禁与真实维护窗口范围。
- 主 Agent 后续：先让矩阵 owner 刷新并复跑 inventory；再由独立 `backend-tester`/`backend-reviewer` 依据本报告和新证据复核，保持 matrix `open/pending` 期间禁止真实 Qdrant、alias 切换、Collection 删除及 `--confirm-replace`。
