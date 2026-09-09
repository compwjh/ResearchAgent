# Spec018 Task06 closure-core backend review

## 评审元数据与安全范围

- 角色：Task06 backend-reviewer（临时 Luna xhigh）
- 时间：2026-09-10（Asia/Shanghai）
- 评审对象：当前未提交的 closure-core diff；未修改业务代码、测试或 closure matrix
- 重点：`T-OLD-ROUTES`、`T-DELETE-TOMBSTONE`、`T-DIRECT-SYMBOLS`、`T-CANDIDATE-BOUNDARY`、`T-REINDEX-BOUNDARY`、`T-BACKGROUND-INVENTORY`、`T-STARTUP-BOUNDARY`、`T-REBUILD-ZERO-WRITES`
- 真实资源：未读取/写入真实 `data/kb`，未连接真实 Qdrant，未启动服务，未执行 `--confirm-replace`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-reviewer/20260910-000001.md`

## 结论

```text
isolated_closure_core=NO-GO
P0=3（均阻塞当前 isolated closure-core）
P1=4（另有测试证据缺口）
real_data_or_qdrant_touched=false
production_cutover=NO-GO
```

八个固定命令虽然全部退出 0，但绿灯不能证明 closure 已闭合：关键测试显式传入任意 `destination_collection`，绕过 generation marker；`__all__` 测试没有验证显式 import/调用；inventory hash 测试只检查摘要长度。`upload-closure-matrix.json` 仍应保持 `baseline_frozen/open/pending`，本报告不授予真实切换资格。

## 逐项裁决

| 门 | 代码核对 | 测试/证据核对 | 裁决 |
|---|---|---|---|
| T-OLD-ROUTES | `routes_kb.py:552-571` 的旧 upload/reindex/delete 只转发到 canonical document route，没有重新调用旧 helper | `tests/test_kb_document_routes.py:216-236` 检查源码并 patch canonical forwarding；未真正安装 forbidden-call spies，但转发实现本身符合 target | **实现 PASS；证据弱** |
| T-DELETE-TOMBSTONE | `application.py:293-309` 的顺序是 vector delete → v1/v2 tombstone → `remove_paper`，vector 失败不会删原件/metadata，partial 返回 `DELETE_PENDING` | `tests/test_kb_document_delete.py:26-43,59-87` patch 掉了真实 vector port，并传入无 marker 的任意 destination；没有 owner 冲突负例，也没有真实顺序 spy | **部分 PASS，不能放行** |
| T-DIRECT-SYMBOLS | `application.__all__` 收窄，但 `application.py:39-49,90-116` 仍绑定 legacy symbols；`index.py:85,123,171,199,215-217` 等仍可省略目标并回落 `KB_COLLECTION` | `tests/test_kb_document_boundary.py:8-45` 只测 `__all__`、metadata-only side effect 和 AST 名称存在；显式 import 仍能取得 `upsert_paper/index_paper_chunker/delete_paper_chunker/delete_paper/submit_index_task` | **FAIL** |
| T-CANDIDATE-BOUNDARY | CandidateRebuildService 的正常路径在 `candidate_rebuild.py:829,873` 传 candidate + document id；但 `candidate_index.py:144-150` 的 `bind_candidate` 不要求 `papers_rebuild_`、不拒绝 candidate 等于 source/alias | `tests/test_kb_candidate_rebuild.py:229-272` 只覆盖合法 candidate 名称，并直接使用 FakeQdrant；没有测试恶意 bind 到 `papers` 或 `QdrantCandidateIndexPort` 的真实 adapter | **正常服务路径 PASS；Port 安全边界 FAIL** |
| T-REINDEX-BOUNDARY | HTTP route `routes_kb.py:479-498` 先 generation gate；但 `application.py:231,254-270` 允许调用方传任意 `destination_collection`，存在时完全跳过 `_active_generation_collection` | `tests/test_kb_document_reindex.py:34-44,62-66` 恰好以无 marker + `papers_rebuild_test` 驱动 application，不能证明“valid marker required”；另未覆盖成功 runner 修改 metadata 后 marker 失配 | **FAIL** |
| T-BACKGROUND-INVENTORY | `routes_kb._submit_index_task` 已移除；但 `application.py:457-472` 的 paper-import default indexer/deleter 仍直调 legacy index symbols；`routes_kb.py:93-96` health 仍默认 ensure fixed collection | inventory 测试只按函数名/正则静态列名，不检查调用图、import consumer 或 write-capable body | **FAIL** |
| T-STARTUP-BOUNDARY | `main.py:26-39` 已移除 KB legacy backfill/interrupted task call，只做 paper-catalog recovery 和 marker read | `tests/test_kb_startup_generation_gate.py:26-35` 将 `recover_paper_catalog_searches` 替换为 lambda，未观察真实 recovery 的 SQLite/Qdrant catalog 写；该 recovery 会 reset queued jobs 并提交 graph | **legacy 部分 PASS；整体证据不足** |
| T-REBUILD-ZERO-WRITES | `CandidateRebuildService.run(dry_run=True)` 的 FakeQdrant 路径不 create/upsert/alias/runtime；candidate build 使用 explicit destination/document id | `tests/test_kb_rebuild_cli.py:24-42` 注入 fake index，仅测一个 source；未验证 production CLI 默认 `get_client()`、全部 source ID/hash 集合、orphan 不变。`rebuild_index.py:46-49` 的默认 `get_client()` 仍会 mkdir Qdrant path | **隔离路径 PASS；零写证明不完整** |

## P0 问题（必须先修）

### P0-1：legacy index 写入口仍可隐式写 live `KB_COLLECTION`

证据：

- `backend/app/knowledge_base/infrastructure/index.py:72-91` 的 `ensure_collection(..., collection_name=None)` 用 `collection_name or KB_COLLECTION`，所以默认调用会创建/触碰正式 collection。
- `index.py:105-156` 的 `upsert_chunks`、`:159-189` 的 `delete_paper_chunker`、`:192-210` 的 `delete_paper` 都以 `destination_collection or KB_COLLECTION` 为目标。
- `index.py:220-265` 的 `index_paper` 没有 destination 参数，必然走 fixed collection；`:276-381` 的 `index_paper_chunker` 的 destination 仍是 optional。
- 真实应用旁路仍存在：`backend/app/api/routes_kb.py:93-96` 的 health 调用 `ensure_collection(client)`；`backend/app/knowledge_base/application.py:457-472` 的 paper-import default indexer/deleter 不传 destination。

这直接违反矩阵 `index-entrypoints` 的 `implicit KB_COLLECTION` forbidden call。即使 CandidateRebuildService 自己只用 CandidateIndexPort，任意 legacy/health/import 调用仍可对 live collection 建写删，故不能把 candidate isolation 宣称为闭合。

最小修复：

1. 将所有写入口的 destination 改为必填（或拆成明确命名的 legacy-only private adapter，缺 destination 直接抛稳定错误），禁止 `or KB_COLLECTION` 作为写路径默认值。
2. health 改为 generation-bound read/status，不在 health 中创建 fixed collection；paper import default path 改走 document application，并传入 marker 解析出的 active collection/受控 reindex port。
3. 增加无 destination、destination=`papers`、destination 与 marker 不一致的 negative tests；不得只测 `__all__`。

### P0-2：CandidateIndexPort 可以被直接 bind 到正式 collection

证据：`backend/app/knowledge_base/infrastructure/candidate_index.py:144-150` 只做通用名称校验并保存 candidate/source/alias；没有要求 candidate 是 `papers_rebuild_<run-id>`，也没有拒绝 `candidate == source_collection` 或 `candidate == alias`。因此调用者可 `bind_candidate("papers", source_collection="papers", alias="papers", ...)` 后以合法 Port API `ensure_collection/upsert_document("papers", ...)` 写当前 collection。现有测试 `tests/test_kb_candidate_rebuild.py:237-272` 只绑定合法的 `papers_rebuild_run`，没有覆盖该反例。

最小修复：`bind_candidate` 强制 candidate 命名/生命周期约束（`papers_rebuild_` 前缀、不得等于 source 或 alias），并在 `QdrantCandidateIndexPort` 与 FakeQdrant 两个实现中一致拒绝；补真实 adapter 的恶意 bind/写入 negative test。服务层 `_new_state()` 的命名约束不能替代 Port 自身安全边界。

### P0-3：reindex/delete application 的显式 destination 可绕过 generation gate

证据：

- `backend/app/knowledge_base/application.py:231,254`：`submit_document_reindex(..., destination_collection=...)` 只在 destination 为空时调用 `_active_generation_collection`；调用方可跳过 marker。
- `application.py:282,294-295`：`delete_document(..., destination_collection=...)` 同样绕过 marker。
- 现有测试明确利用此旁路：`tests/test_kb_document_reindex.py:34-37,62-65` 和 `tests/test_kb_document_delete.py:27-33,62-68` 在没有 generation marker 的 tempfile 中传 `papers_rebuild_test`，因此“valid generation marker is required”并未被验证。

最小修复：application 每次都先读取并验证 marker；若提供 destination，仅允许它与 marker `alias_target` 完全相等，否则返回稳定 `INDEX_REBUILD_REQUIRED`/`INDEX_TOPOLOGY_AMBIGUOUS`。更稳妥的是去掉对外 optional destination，仅由受控内部 composition seam 注入已验证 port。测试 fixture 应真实写入合法 marker，并增加无 marker/错误 target/marker target 漂移负例。

## P1 问题与证据缺口

### P1-1：成功 reindex 会使 generation marker 的 metadata hash 失配

`backend/app/knowledge_base/infrastructure/index.py:368-376` 的成功 `index_paper_chunker` 会调用 `update_chunker_state` 修改 `papers.json`；而 `FinalizeBundleStore.require_generation()` 在 `manifest_store.py:480-494` 按 marker 的 `metadata_sha256` 校验整个 metadata 文件。当前没有 reindex 后更新 generation marker 的协议，所以一次真实 reindex 成功后，后续 inspection/list gate 会看到 `INDEX_FINALIZE_REQUIRED`。现有 reindex 测试 patch 掉 indexer（`tests/test_kb_document_reindex.py:31-43`），完全没有覆盖此 after-effect。

最小修复：为 document reindex 定义不破坏 generation 的状态存储（例如将运行状态移出 marker 绑定的 immutable metadata，或在受控 finalize/update 协议中原子更新 marker），并加入“reindex runner 成功 → marker 仍可 require_generation → inspection 可读”的临时目录测试。

### P1-2：paper-import consumer 仍绕过 canonical/reindex boundary

`backend/app/knowledge_base/application.py:457-472` 的 `_default_indexer/_default_deleter` 仍调用 `index_paper_chunker/delete_paper_chunker`，并且 `:520-524` 仍为兼容失败注入调用 `upsert_paper`。这些对象虽然从 `__all__` 删除，仍是模块 public attributes，显式 import 可得（本评审实测可取得五个 legacy symbol）。`tests/test_paper_import.py` 的 45 项回归通过，但大多注入 `indexer/deleter`，没有运行 default consumer，因此不能关闭矩阵 paper-import entries 或证明“direct production collection write”消失。

最小修复：将 legacy imports 改为 private aliases 并移除对外属性，default importer 只调用 immutable create + marker-bound document reindex/compensation；补不注入 default importer 的临时目录测试，断言 collection、source、metadata 和 owner/token compensation。

### P1-3：startup 测试把真实可写 recovery 替换掉

`backend/app/main.py:27-30` 仍调用 `recover_paper_catalog_searches()`。其实现 `backend/app/api/common.py:150-157` 会 reset running jobs 并提交 graph；`backend/app/paper_discovery/application/catalog_search_graph.py:111-147,295+,603+,713+` 会写 paper-discovery SQLite 状态并可能创建/upsert 独立 catalog collection。它不是“document reindex state recovery”。现有 `tests/test_kb_startup_generation_gate.py:26-27` 用 lambda 替换该调用，所以只证明 marker store read，不证明 startup write boundary。

最小修复：若 Task06 startup 契约确实是“只校验 marker + document reindex recovery”，从 lifespan 移除 paper-catalog recovery，改由独立 scheduler/其自身启动入口负责；否则必须把该写入明确加入允许清单并给出独立 collection/SQLite spy，不能用 mock 抹掉它。

### P1-4：closure matrix inventory 没有冻结 hash，且静态扫描漏调用图

`tests/test_kb_upload_closure_matrix.py:70-83` 只计算每个实际文件 digest 的长度是否为 64；没有与 `inventory_files[*].sha256`、`inventory_digest` 或 `inventory_git_revision` 比较。实测当前 matrix 中至少三项已漂移：`backend/app/main.py`、`backend/app/knowledge_base/application.py`、`backend/app/knowledge_base/infrastructure/index.py` 的 stored SHA-256 均与当前实际值不符，stored digest 也不符。第 43-68 行还把 `ensure_collection`、`upsert_chunks` 等 write-capable 名称放进 allowlist，只按函数名 token 检查，不能发现 `_default_indexer` 或 health 中的直接调用。

最小修复：由 matrix owner 重新生成 revision、逐文件 SHA 和排序 digest；测试逐项 equality 比较并拒绝 stale matrix；AST/静态检查增加 import/call-site 规则，至少禁止 application/API/health/import consumer 直接调用 legacy write symbols，禁止写函数无显式 destination。

## 删除顺序与 tombstone 专项结论

当前 `delete_document` 的基本顺序是正确的：`application.py:293-309` 先删 active vector，再写两版本 tombstone，最后由 `remove_paper` 删除 metadata/source；vector 或 tombstone 失败均返回 `DELETE_PENDING`，`store.remove_paper` 在 source unlink 失败时会恢复 metadata（`store.py:227-247`）。这一点可作为局部 PASS。

但仍有两个不能忽略的边界：

1. 其 application destination 可绕过 marker（P0-3）。
2. `InspectionManifestStore.tombstone()`（`manifest_store.py:278-297`）对已存在 tombstone 不核验 owner/token，直接覆盖同一 document 的 tombstone；当前测试只断言最终文本含 `document-api`（`test_kb_document_delete.py:86-87`），没有另一 owner/重复 retry 的拒绝或保留规则。因此“owner-scoped”只能记为未证明，不能把这两项测试绿灯写成完整 DELETE-TOMBSTONE closure。

## 验证命令

以下均使用项目 `.venv`、临时目录/FakeQdrant/monkeypatch，不连接真实服务：

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_kb_document_routes.py -k legacy` | 1 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_document_delete.py` | 2 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_document_boundary.py` | 3 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_document_reindex.py` | 3 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_upload_closure_matrix.py -k inventory` | 2 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_startup_generation_gate.py` | 2 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py -k destination` | 1 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_rebuild_cli.py -k 'spy or dry_run or source_hash'` | 4 passed |
| `.venv/bin/python -m pytest -q tests/test_paper_import.py tests/test_kb_application_boundary.py tests/test_kb_routes.py` | 45 passed |
| `.venv/bin/ruff check`（本轮后端/测试文件） | passed |
| `git diff --check` | passed |

## 后续放行条件

1. 先修 P0-1～P0-3，并为每个 direct write/reindex/delete/candidate bypass 加失败用例。
2. 修复 P1-1 的 marker 协同和 P1-2 的 import consumer；明确 startup catalog recovery 的归属后重写 P1-3 测试。
3. 重新生成并机械校验 closure matrix hashes/digest；逐 entry 将 `current_status`、test `status/exit_code/evidence_paths` 更新为事实，不能手改成 `closed/passed`。
4. 重新进行独立 backend-tester/backend-reviewer 评审；在 closure matrix `verified` 前保持 Task06-C/D、真实 Qdrant、alias/Collection 写删和服务重启验收禁止。
