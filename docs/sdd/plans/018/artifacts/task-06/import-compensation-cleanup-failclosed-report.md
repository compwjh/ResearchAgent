# Spec018 Task06：import cleanup fail-closed 修复报告

## 固定字段

```text
task=T-IMPORT-COMPENSATION-CLEANUP-FAILCLOSED
result=HARDENED-IN-ISOLATION
cleanup_contract=single-path-retained-private-root-rmtree-only
replacement_path=retained
explicit_temp_dir=caller-owned-never-removed
private_attempt_root=shutil-rmtree-symlink-attack-resistant-only
real_data_or_kb_touched=false
qdrant_or_service_touched=false
network_or_confirm_replace=false
matrix_or_spec_changed=false
```

## 修复内容

- `_cleanup_download` 不再对任何单文件 pathname 执行 `unlink`。只要 downloader 返回文件路径，就稳定返回 `cleanup_pending`；不返回路径才返回 `completed`。这样即使 fd/stat 校验后目录项被 replacement 替换，也不会误删 replacement。
- `import_candidate` 传入显式 `temp_dir` 时继续保留 caller root 及其全部文件，不回收父目录；相关成功导入和直接 cleanup 测试已按新契约更新。
- `temp_dir=None` 时由 `import_candidate` 创建的 attempt-private root 仍在 finally 中统一回收。创建时记录 root 的 dev/ino token，`_cleanup_attempt_root` 仅在 token 仍匹配、`shutil.rmtree.avoids_symlink_attacks` 可用且 root 当前为非 symlink 目录时执行；回收器不跟随 root 或其内容中的 symlink 到 root 外。
- 新增回归覆盖：单文件清理禁止 pathname unlink、replacement 路径保留、显式 caller temp root/文件保留、attempt root 被替换为外部 symlink 时外部 sentinel 保留。

## 验证

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py tests/test_paper_import.py` | 0 | **20 passed** |
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py tests/test_paper_import.py tests/test_kb_immutable_create.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py tests/test_kb_startup_generation_gate.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py tests/test_paper_import_identity.py tests/test_paper_import_batch_store.py` | 0 | **101 passed** |
| `.venv/bin/ruff check backend/app/paper_discovery/application/paper_import.py tests/test_import_compensation.py tests/test_paper_import.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/paper_discovery/application/paper_import.py` | 0 | 编译通过 |
| `git diff --check` | 0 | 通过 |

## 明确 deferred 风险

- **batch compensation deferred**：`paper_import_batch_service.py` 尚未持久化并驱动 `resource_capability` / `cleanup_status`，batch failure、cancel、expired lease、retry/resume 仍需独立任务和 contract tests；本报告不宣称跨 batch/重启补偿闭合。
- **generation binding deferred**：`ImportResourceCapability.destination_collection` 仍未绑定创建/索引时的实际 generation collection，`_default_deleter` 仍按补偿时 active generation 解析目标；缺少 marker/target 全等校验，不能作为向量补偿安全证明。
- **生产门 deferred**：未访问真实 `data/kb`、用户原件、Qdrant、服务、网络或 `confirm-replace`；closure matrix 与 spec 均未修改，生产切换仍为 NO-GO。

## 交接

- 报告：`docs/sdd/plans/018/artifacts/task-06/import-compensation-cleanup-failclosed-report.md`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910-000000.md`
