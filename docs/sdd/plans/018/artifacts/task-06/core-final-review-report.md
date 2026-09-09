# Spec018 Task06 core-final backend review

## 评审元数据与范围

- 角色：Task06 backend-reviewer（线上 Luna high）
- 时间：2026-09-10（Asia/Shanghai）
- 评审对象：当前工作树中的 closure-core 实现、交接报告、固定 core 测试与 `upload-closure-matrix.json`
- 只评审，不修改业务代码、测试、matrix 或 spec；本报告为本角色允许的落盘交付物
- 安全范围：未读取/写入真实 `data/kb`，未连接真实 Qdrant，未启动服务，未执行 `--confirm-replace`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-reviewer/20260910-034114.md`

## 结论

```text
isolated_core_closure=GO
new_P0=0
new_P1=0
allow_core_closure_commit=true
production_cutover=NO-GO
real_data_or_qdrant_touched=false
```

上一轮列出的 P0/P1 核心旁路已在当前实现中关闭，允许将 core closure 实现与本报告提交到同一分支/提交。这个 GO 只表示隔离 core 门通过，不表示 Task04 closure matrix 已 verified，也不授权真实 Qdrant、alias/Collection 写删、服务重启或生产切换。

## P0/P1 逐项裁决

| 问题 | 当前证据 | 裁决 |
|---|---|---|
| P0-1 legacy index 写入口缺 destination | `index.py:_required_destination()` 在 `ensure_collection`、`upsert_chunks`（有实际 chunks 时）、`delete_paper_chunker`、`delete_paper`、`index_paper`、`index_paper_chunker`、`backfill_chunker_defaults` 的写路径前拒绝缺失/非法 destination；不再 `or KB_COLLECTION`。`tests/test_kb_document_boundary.py` 6 个负例通过。 | **PASS（写入路径）** |
| P0-2 Candidate bind 到正式 collection | `candidate_index.py:_validate_binding()` 要求 `papers_rebuild_` 命名并拒绝 candidate 等于 source/alias；FakeQdrant 与 QdrantCandidateIndexPort 共用校验。Fake 写入测试确认正式 collection 保持不变，Qdrant adapter 的恶意 bind 负例也覆盖。 | **PASS** |
| P0-3 generation marker 可被显式 destination 绕过 | `application._generation_bound_collection()` 每次先读取/验证 marker，再要求请求 destination 与 marker `alias_target` 完全相等；reindex/delete 均在任何 index/delete 前调用它。无 marker 或 target 漂移不执行写删；reindex 无 marker/错误 target 负例通过。 | **PASS** |
| P1-1 reindex 后 marker metadata hash 失配 | `FinalizeBundleStore.refresh_live_digests()` 原子刷新 metadata/manifests digest 并再次 `require_generation()`；reindex 状态写入后测试真实执行 parser/chunker/embed/upsert stub，并成功 `require_generation()`。 | **PASS** |
| P1-2 paper-import default consumer 绕过 canonical boundary | `_default_indexer`/`_default_deleter` 均先解析 marker，再使用 destination-bound `GenerationBoundIndexPort`；不再直接导入 legacy index/delete helper；导入状态 patch 后也刷新 marker digest。默认 indexer 的 marker-bound 临时测试通过。 | **PASS（实现；端到端证据有限）** |
| P1-3 startup 证据被 mock 抹掉 | `main.lifespan` 移除 KB legacy backfill/interrupted mutation，仅保留 catalog recovery 与 KB generation read。新增测试使用真实临时 `PaperDiscoveryStore` 执行 running→queued recovery，并断言 KB 目录未创建；graph submit 被隔离替换，不接触网络/Qdrant。 | **PASS（隔离边界）** |
| P1-4 inventory 未比较 frozen hash/digest | `tests/test_kb_upload_closure_matrix.py` 逐项比较 frozen SHA，并按排序 SHA 行重算 `inventory_digest`；当前 8 个 inventory 文件 hash 与 matrix 一致，digest 测试通过；AST 检查 application/routes 的 legacy import/call 与 health 写调用。 | **PASS（当前冻结清单）** |

### 非阻塞 hardening 观察

- `upsert_chunks()` 在 `chunks` 为空时先返回 `0`，因此“无 destination 必须抛错”的字面契约未覆盖 no-op 调用；该路径不触碰 client/collection，未形成 live 写入旁路，故不计为本轮 P0/P1。
- paper-import 专项测试直接调用 default indexer，未端到端执行 default deleter；实现调用图已核对为 marker-bound，完整 `T-PAPER-IMPORT`/compensation 仍由 matrix owner 收口。
- `GenerationBoundIndexPort` 是内部 composition seam，构造器本身只校验 collection 名称而不读取 marker；当前生产调用者均由 application 先解析 marker，禁止把该内部 seam 当作新的外部 API。

## 固定八项 core 命令

以下命令均已由本轮复跑，退出码全部为 0；均使用临时目录、FakeQdrant、隔离 client 或 stub。

| Test ID | 命令 | 结果 |
|---|---|---|
| T-OLD-ROUTES | `.venv/bin/python -m pytest -q tests/test_kb_document_routes.py -k legacy` | 1 passed, 17 deselected |
| T-DELETE-TOMBSTONE | `.venv/bin/python -m pytest -q tests/test_kb_document_delete.py` | 3 passed |
| T-DIRECT-SYMBOLS | `.venv/bin/python -m pytest -q tests/test_kb_document_boundary.py` | 14 passed |
| T-CANDIDATE-BOUNDARY | `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py -k destination` | 1 passed, 43 deselected |
| T-REINDEX-BOUNDARY | `.venv/bin/python -m pytest -q tests/test_kb_document_reindex.py` | 4 passed |
| T-BACKGROUND-INVENTORY | `.venv/bin/python -m pytest -q tests/test_kb_upload_closure_matrix.py -k inventory` | 2 passed |
| T-STARTUP-BOUNDARY | `.venv/bin/python -m pytest -q tests/test_kb_startup_generation_gate.py` | 3 passed |
| T-REBUILD-ZERO-WRITES | `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_rebuild_cli.py -k 'spy or dry_run or source_hash'` | 4 passed, 42 deselected |

## 回归与静态检查

- `.venv/bin/python -m pytest -q tests/test_kb_services.py tests/test_kb_tasks.py tests/test_paper_import.py tests/test_kb_application_boundary.py tests/test_kb_routes.py`：**137 passed**, 5 warnings，4 subtests，exit 0。
- 全部 `test_kb_*.py`（排除历史 `tests/test_legacy_kb_integration.py`）：**378 passed**, 5 warnings，29 subtests，exit 0。
- `.venv/bin/ruff check`（本轮后端实现与 core 测试）：exit 0，`All checks passed!`。
- `.venv/bin/python -m py_compile`（本轮后端实现）：exit 0。
- `git diff --check`：exit 0。

## 测试过拟合与证据边界

这些限制不推翻隔离 core GO，但禁止把测试绿灯扩展为 production closure：

1. `T-OLD-ROUTES` 主要做源码字符串检查与 canonical forwarding；没有为每个 forbidden helper 安装真实调用 spy。
2. `T-CANDIDATE-BOUNDARY` 只选中一个 destination 测试；正式 Qdrant adapter 只做 bind 负例，实际写入验证主要在 FakeQdrant。
3. default paper-import 测试直接调用 `_default_indexer`，没有端到端跑 default deleter、batch/browser 全链路；因此 matrix 中纸面导入条目仍不能自动关闭。
4. `T-REBUILD-ZERO-WRITES` 注入 service/index double，未调用生产 CLI 的默认 `get_client()`；它证明隔离 dry-run 不写，不证明真实 Qdrant dry-run。
5. startup 测试真实写临时 catalog SQLite，但将 graph submit 隔离替换；它证明 KB 边界，不证明真实第三方 catalog graph 成功。

## Matrix 与生产门禁

当前 `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json` 的 inventory SHA/digest 与工作树一致，但流程状态仍为：

- `review_status=baseline_frozen`
- 17/17 entry 为 `open`
- required test 仍为 `pending`（除既有 API route 记录外）

因此本报告明确允许 **core closure commit**，同时保持 **production cutover NO-GO**。matrix owner 仍须逐 entry 更新真实 `current_status`、test `status/exit_code/evidence_paths`，并独立完成停服、真实资源、拓扑、hash 和重启验证；不得因为本报告的隔离 GO 而执行 `--confirm-replace` 或真实 Collection/alias 写删。

