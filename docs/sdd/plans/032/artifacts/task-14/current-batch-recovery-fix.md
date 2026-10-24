# Spec032 Task14：批次重启恢复修复交接

- 角色：backend-dev
- 日志：`.codebuddy/agent-logs/spec-032/task-14/backend-dev/20261008-004452.md`
- 日期：2026-10-08（Asia/Shanghai）
- 范围：仅 P1-B「持久 queued 批次在服务实例重启后恢复」
- 结论：P1-B 已在本地定向测试中修复；P1-A「登录/上传/重试与报告新版本接缝」仍未修复，未在本次改动中处理。

## 根因与修复

原 `PaperImportBatchService.maybe_recover_batch()` 以进程内
`self._snapshots` 作为恢复 gate。批次创建时已经把候选服务端快照及
`snapshot_hash` 持久化到 SQLite，但新实例没有这份进程缓存，因此对同一
`batch_id` 直接返回，批次永久保持 `queued`，也不会提交既有 runner。

本次只调整 `backend/app/paper_discovery/application/paper_import_batch_service.py`：

1. `maybe_recover_batch()` 对 queued 批次调用既有 `_snapshots_for(batch_id, None)`；该路径通过 `PaperImportBatchStore.get_snapshot()` 校验 `snapshot_json` 的 SHA-256，并在验证成功后使用 SQLite 快照，不依赖进程缓存。
2. 验证成功后仍只调用既有 `submit_batch()`，保留 `_batch_runners` 的单实例 single-flight、item 的原子 claim/租约/取消语义；跨实例竞争仍由已有持久化 CAS claim 阻止重复下载。
3. 缺失或损坏快照沿用现有中断协议：`_fail_remaining_queued()` 将 queued item 转为 `IMPORT_INTERRUPTED` failed，批次不再永久停留 queued，之后可走已有 `retry_batch()`/人工重试入口。没有新增错误码、schema、公开接口或第二套状态。
4. 更新服务内注释，明确 `_snapshots` 只是执行便利缓存，持久化快照才是重启恢复依据。

## 红灯复现与绿灯证据

先以临时 SQLite 建立批次：第一个 service 写入 queued item 和持久快照，第二个 service 重新打开同一数据库、没有进程缓存，再调用 `maybe_recover_batch()`。

红灯（修复前）：

```text
.venv/bin/python -m pytest -q tests/paper_discovery/test_paper_import_batch_service.py -k restarted_service_recovers_queued_batch_from_durable_snapshot
1 failed, 27 deselected
KeyError: 'future'
```

失败表明重启后的 service 没有调用 `submit_batch()`，与原 `batch_id not in self._snapshots: return` gate 一致。

绿灯新增回归：

- `test_restarted_service_recovers_queued_batch_from_durable_snapshot`：新实例从持久快照提交 runner，最终 batch/item 均为 `completed`。
- `test_recovery_with_corrupted_snapshot_becomes_retryable_failure`：损坏快照不留在 queued；状态为 `failed/IMPORT_INTERRUPTED`，现有 `store.retry_batch()` 能将其恢复到 queued。

## 定向验证

以下均使用仓库 `.venv/bin/python` 和临时测试数据库，未写生产数据库、未创建真实 issue、未执行登录或上传：

```text
.venv/bin/python -m pytest -q tests/paper_discovery/test_paper_import_batch_service.py -k 'restarted_service_recovers_queued_batch_from_durable_snapshot or recovery_with_corrupted_snapshot_becomes_retryable_failure'
2 passed, 27 deselected

.venv/bin/python -m pytest -q \
  tests/paper_discovery/test_paper_import_batch_service.py \
  tests/paper_discovery/test_paper_import_batch.py \
  tests/paper_discovery/test_paper_import_batch_store.py \
  tests/paper_discovery/test_paper_import_batch_catalog_fallback.py \
  tests/paper_discovery/test_paper_issue_recovery.py \
  tests/paper_discovery/test_approved_plan_auto_import.py
69 passed

.venv/bin/python -m pytest -q \
  tests/paper_discovery/test_paper_import_batch_api.py \
  tests/paper_discovery/test_paper_import_batch_integration.py \
  tests/paper_discovery/test_acquisition_snapshot_refresh.py \
  tests/paper_discovery/test_acquisition_bridge.py \
  tests/research/test_candidate_acquisition_integration.py
33 passed

.venv/bin/ruff check backend/app/paper_discovery/application/paper_import_batch_service.py tests/paper_discovery/test_paper_import_batch_service.py
All checks passed!

.venv/bin/python -m py_compile backend/app/paper_discovery/application/paper_import_batch_service.py tests/paper_discovery/test_paper_import_batch_service.py
exit 0
```

## 现有 API 接缝与用户操作说明

- `GET /api/papers/imports` / `PaperImportBatchStore.list_batches()` 仍是只读列表，不触发隐藏调度；因此列表暂时显示 `queued` 是可能的、且有意保留的行为。
- 用户应打开已有详情入口 `GET /api/papers/imports/{batch_id}`（兼容别名 `/api/papers/import-batches/{batch_id}`）。该详情读取先执行 lease recovery，再调用 `maybe_recover_batch()`；持久快照完整时会提交恢复 runner。
- Research 侧既有 `GET /api/research-tasks/{research_task_id}/acquisitions` 经 `ResearchAcquisitionService.status()` 使用同一 recovery 出口，不新增第三条调度路径。
- 快照损坏/缺失时，详情不会声称仍在运行：queued item 进入稳定 `failed`，错误码为 `IMPORT_INTERRUPTED`，用户可沿用已有批次 retry；如果仍缺少服务端快照，按既有 `SNAPSHOT_REBUILD_REQUIRED`/搜索快照重建协议处理。

本次没有启动服务或对 8000 端口执行写入型 API E2E；Spec032 的真实 API 成功方案、只读线上证据和 P1-A 缺口仍以同 Task14 的 `current-recovery-audit.md` 为准。

## 变更边界

- 生产代码：仅 `backend/app/paper_discovery/application/paper_import_batch_service.py`。
- 测试：仅 `tests/paper_discovery/test_paper_import_batch_service.py`，测试名按能力命名，无 spec/task 编号。
- 未修改：`routes_paper.py`、报告生成/版本化代码、issue 登录/上传/重试代码、schema/migration、`list_batches()`、生产数据。
- 未提交 git commit；工作树中的其他 agent 改动保持原样。

