# Task 14 批次重启恢复后端评审

- 日期：2026-10-08（Asia/Shanghai）
- 分支：`codex/spec032-final-acceptance`
- 角色：backend-reviewer（独立只读评审）
- 评审范围：`current-batch-recovery-fix.md`、`backend/app/paper_discovery/application/paper_import_batch_service.py` 的 diff、`tests/paper_discovery/test_paper_import_batch_service.py` 的新增测试及相关既有存储/API 契约。
- 评审日志：`.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261008-004848.md`
- 结论：**本次 P1-B 批次重启恢复改动通过；P0=0，P1=0。** Spec032 整体仍受交接报告所述 P1-A（恢复后报告新版本/任务续跑）阻塞，本报告不把该未实现范围误判为 P1-B 失败。

## 评审结论摘要

实现只改变 `maybe_recover_batch()` 的进程缓存 gate：queued 批次先走既有 durable snapshot 校验，完整时复用既有 `submit_batch()`；快照缺失/损坏时把仍 queued 的 item 原子地标为 `IMPORT_INTERRUPTED` failed。未新增 schema、字段、API、migration、第二套状态机或列表调度路径。

## 逐项核对

### 1. 新实例 hash 验证快照：通过

- `maybe_recover_batch()` 在 `backend/app/paper_discovery/application/paper_import_batch_service.py:785-794` 调用 `_snapshots_for(batch_id, None)`，不再要求 `_snapshots` 进程缓存存在。
- `_snapshots_for()` 使用既有 `PaperImportBatchStore.get_snapshot()`；`paper_import_batch_store.py:561-577` 对 `snapshot_json` 做 SHA-256 校验、JSON 解码和 `candidate_id/search_id` 必填校验。新实例无 local candidate 时使用 SQLite durable snapshot。
- 验证成功后才提交 runner；runner 内 `run_batch()` 再次通过同一路径读取快照，验证与执行之间的变化不会静默使用无效快照。
- 新增 `test_restarted_service_recovers_queued_batch_from_durable_snapshot` 证明新 service instance 最终完成 batch/item；`test_corrupted_durable_snapshot_still_requires_rebuild` 及新损坏恢复测试覆盖原 hash/JSON 损坏门禁。

### 2. 缺损快照 → `IMPORT_INTERRUPTED` 且可重试：通过（有明确前置条件）

- `_fail_remaining_queued()`（service:759-772）仅处理仍处于 queued 的 item，使用既有 `mark_failed(..., lease_owner=None)`，错误码固定为 `IMPORT_INTERRUPTED`，并刷新批次终态。
- 新增 `test_recovery_with_corrupted_snapshot_becomes_retryable_failure` 证明损坏快照不会永久停留 queued，item/batch 进入 failed，既有 store `retry_batch()` 可回到 queued。
- 需要准确理解“可重试”：如果快照仍损坏，调用 service/API retry 后 runner 会再次发现 `SNAPSHOT_REBUILD_REQUIRED` 并回到 `IMPORT_INTERRUPTED`；成功重试前必须按既有 snapshot rebuild/search 重新建立可信 durable snapshot。该行为避免伪造候选继续下载，不是本次 P1-B 缺陷。

### 3. claim、租约和跨实例重复 runner：通过

- `submit_batch()` 的 `_batch_runners` 仍提供同一 service instance 的 single-flight。
- 不同 service/process instance 的 `_batch_runners` 不共享，但每个 runner 的 `process_item()` 都经过既有持久化 `claim_item()` CAS；失败 claim 的 runner 只等待 winner 状态，不调用 importer。
- `claim_item()` 的 SQLite 条件仍要求 `state=queued`，并写入 lease owner/expiry 与 attempt credentials；后续 transition 要求活动 lease owner 和未过期租约。取消/过期恢复仍走既有 store 条件更新。
- 运行时交叉验证：同一临时 SQLite 中两个独立 service instance 并发调用 `maybe_recover_batch()`，两个 Future 均结束，`importer_calls=1`，item=`completed`，退出码 0。

### 4. single-flight 与取消：通过

- 同实例重复 `submit_batch(batch_id)` 返回同一 Future；既有 `test_submit_batch_is_single_flight_and_runs_in_background`、失败重试 single-flight 测试通过。
- `cancel_batch()`/`cancel_item()` 未被本次 diff 改动；store 仍以条件 UPDATE 清除 lease 并将当前 attempt 标记 cancelled。runner 之后的状态更新受 lease/CAS 约束，不会把 cancelled item 覆盖成 completed。
- 服务、batch/store 和 API 相关测试均通过，未见恢复 gate 绕过取消状态的问题：`maybe_recover_batch()` 首先要求 batch 状态为 queued。

### 5. list 只读、不新增 GET 写语义：通过

- `PaperImportBatchService.list_batches()`（service:955-986）只调用 `store.list_batches()` 和 `store.get_items()`，没有 `recover_expired_leases()`、`maybe_recover_batch()` 或 `submit_batch()`。
- `GET /api/papers/imports` 路由 diff 未改变，仍只调用 `service.list_batches()`；只有既有详情 GET `/api/papers/imports/{batch_id}` 才执行 lease recovery/queued recovery。
- API 列表测试覆盖 active/status/limit/redaction，21 个 API 测试全通过；列表不会因为读取而启动 runner。

### 6. schema 与变更边界：通过

- 生产 diff 仅为 `paper_import_batch_service.py` 的注释和 `maybe_recover_batch()` gate；测试 diff 仅新增两个能力测试及 `Future/sqlite3` 测试辅助导入。
- 未发现 migration、DDL、domain schema、公开 API response、`list_batches()` 或 downloader 改动。
- `ruff check`、`py_compile`、`git diff --check` 均退出码 0。

## 评审验证命令

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_paper_import_batch_service.py` | 0 | 29 passed |
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_paper_import_batch.py tests/paper_discovery/test_paper_import_batch_store.py` | 0 | 21 passed |
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_paper_import_batch_api.py` | 0 | 21 passed |
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_paper_import_batch_integration.py tests/paper_discovery/test_acquisition_snapshot_refresh.py tests/paper_discovery/test_acquisition_bridge.py` | 0 | 11 passed |
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_paper_import_batch_service.py -k 'submit_batch_is_single_flight or concurrent_processing or concurrent_resume or expired_lease or old_worker or restarted_service or corrupted_snapshot'` | 0 | 7 passed，22 deselected |
| 两独立 service instance 临时 SQLite 并发 recovery 交叉验证 | 0 | `importer_calls=1`，item completed |
| `.venv/bin/ruff check backend/app/paper_discovery/application/paper_import_batch_service.py tests/paper_discovery/test_paper_import_batch_service.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile ...` | 0 | 编译通过 |
| `git diff --check -- backend/app/paper_discovery/application/paper_import_batch_service.py tests/paper_discovery/test_paper_import_batch_service.py` | 0 | 通过 |

## 非阻塞建议与剩余风险

- 建议后续补一个 API spy 测试：调用 `GET /api/papers/imports` 时断言 `maybe_recover_batch`/`recover_expired_leases` 未被调用；当前实现与现有列表测试已证明该路径，但主要是静态/间接证据。
- 损坏快照的 service/API retry 只能在快照重建后成功；不能把短暂的 queued 响应当作恢复成功，详情 GET/后台 runner 的最终 `IMPORT_INTERRUPTED` 才是稳定结果。
- `_snapshots` 和 `_batch_runners` 仍是进程内执行缓存；跨实例一致性依赖 SQLite durable snapshot 与 item claim CAS，当前交叉验证通过。若未来替换状态存储，必须保留这两个持久化门禁。

## 交接

- 被评审交接：[current-batch-recovery-fix.md](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-batch-recovery-fix.md)
- 本评审报告：[current-batch-recovery-review.md](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-batch-recovery-review.md)
- 评审日志：[20261008-004848.md](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261008-004848.md)

