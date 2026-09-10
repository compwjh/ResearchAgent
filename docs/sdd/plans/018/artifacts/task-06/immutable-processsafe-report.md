# Spec018 Task06：immutable create process-safe hardening report

## 固定字段

```text
task=T-IMMUTABLE-CREATE
result=HARDENED-IN-ISOLATION
real_data_or_kb_touched=false
qdrant_or_service_touched=false
network_or_confirm_replace=false
matrix_or_spec_changed=false
```

## 修复内容

- `store.immutable_directory_lock()` 使用 metadata directory 下的同一 lockfile 和 `fcntl.flock(LOCK_EX)`；`create_immutable_document` 在该锁与既有 `_UPLOAD_LOCK` 内完成 metadata strict read、hash/media dedupe、server basename 选择、O_EXCL source create、metadata append 与 generation digest refresh。跨进程同 hash create 因此只保留一个 canonical record 和一个 source。
- source cleanup 不再执行 `lstat` 后无条件按路径 `unlink`。本次 source 的 device/inode token 仅在 O_EXCL fd 成功后生成；cleanup 以 `O_NOFOLLOW` 打开当前 target、用 `fstat` 校验 token 和独占 link count，并在同一 process lock 内删除。无法证明 ownership、目标已替换/变为 symlink、或发生异常时 fail-closed，保留可识别 orphan。
- legacy `save_upload` 同样改为 O_EXCL fd + token，并受同目录 process lock 保护；写入/fsync 异常不再无条件删除 target，replacement 场景保留 caller-owned bytes。
- 保持 upload/paper-import 唯一 create seam、hash/media/name/ETag 行为、source_path caller ownership、generation-bound 语义和既有线程锁。

## 新增回归

- fork 双进程同 hash：断言结果只有一个 canonical `document_id`、只有一个非-deduplicated winner、metadata 只有一条、papers 目录没有 orphan source。
- metadata failure 后 target replacement：断言 replacement 保留，并通过禁用 `Path.lstat` 的注入回归确保清理不回到 lstat→unlink 实现。
- legacy `save_upload` 在 source fsync 后 replacement + exception：断言 replacement 保留。

## 验证

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_immutable_create.py tests/test_paper_import.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py tests/test_kb_services.py tests/test_kb_document_routes.py tests/test_kb_document_reindex.py` | 0 | **140 passed, 5 warnings** |
| `.venv/bin/python -m pytest -q tests/test_kb_immutable_create.py` | 0 | **11 passed** |
| `.venv/bin/ruff check backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py tests/test_kb_immutable_create.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py tests/test_kb_immutable_create.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 后续未完成范围与安全边界

- 本轮只处理 immutable create 的 source target ownership 和跨进程 create metadata/dedupe；paper-import indexing/patch 失败后的持久化 owner/token compensation、cleanup lease、resume/retry 仍属于后续 T-IMPORT-COMPENSATION。
- batch/retry、browser session、过期 lease 和跨进程 compensation 仍未完成；本报告不将它们标记为已关闭。
- 未修改 closure matrix/spec/status，不读取或写入真实 `data/kb`、用户原件、真实 Qdrant 或服务；未联网、未执行 `confirm-replace`。生产 cutover 仍需独立门禁。

## 固定交接

- 报告：`docs/sdd/plans/018/artifacts/task-06/immutable-processsafe-report.md`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910-012652.md`
