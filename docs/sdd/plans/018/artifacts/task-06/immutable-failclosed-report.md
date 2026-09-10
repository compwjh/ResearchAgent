# Spec018 Task06：immutable create fail-closed 修复报告

## 固定字段

```text
task=T-IMMUTABLE-FAILCLOSED
result=HARDENED-IN-ISOLATION
real_data_or_kb_touched=false
qdrant_or_service_touched=false
network_or_confirm_replace=false
matrix_or_spec_changed=false
```

## 修复内容

- `store._unlink_owned_source` 与 application wrapper 保留 `O_NOFOLLOW`/`fstat` ownership 探测，但彻底取消失败路径的 pathname `unlink`。即使探测到原 inode，也 fail-closed 保留 target；metadata/source create 失败产生的 orphan 由后续 compensation/maintenance 识别和处理，避免 `fstat` 后目录项被替换时误删 replacement。
- `create_immutable_document` 在解析 metadata/source 路径后强制两者落入同一 canonical `immutable_directory_lock` domain；不同 domain 稳定返回 `IMMUTABLE_LOCK_DOMAIN_MISMATCH`，不创建 lockfile、metadata 或 source。
- legacy `save_upload` 继续使用 canonicalized directory lock，并共享 fail-closed source cleanup helper；保留预存普通文件、symlink、O_EXCL 冲突、正常 source/hash/name/dedupe 语义。

## 新增/调整回归

- 注入 cleanup helper `fstat` 返回后立即替换目录项，application create 与 legacy `save_upload` 均断言 replacement 保留。
- metadata failure 场景改为断言 metadata record 回滚但 source orphan 保留，明确由后续 compensation/maintenance 处理。
- 不同 metadata/source lock domain 稳定拒绝且无临时目录副作用。

## 验证

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_immutable_create.py` | 0 | **14 passed** |
| `.venv/bin/python -m pytest -q tests/test_kb_immutable_create.py tests/test_paper_import.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py tests/test_kb_services.py tests/test_kb_document_routes.py tests/test_kb_document_reindex.py` | 0 | **143 passed, 5 warnings, 4 subtests passed** |
| `.venv/bin/ruff check backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py tests/test_kb_immutable_create.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py tests/test_kb_immutable_create.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 安全边界

- 未修改 Spec、closure matrix 或状态文件；未触碰真实 `data/kb`、用户原件、Qdrant、服务和 `confirm-replace`。
- orphan 保留是本修复的明确 fail-closed 结果，不视为泄漏或成功清理；后续 compensation/maintenance 必须基于持久 owner/token 与可证明拓扑再回收，不能恢复按路径猜测删除。

## 交接

- 报告：`docs/sdd/plans/018/artifacts/task-06/immutable-failclosed-report.md`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910-immutable-failclosed.md`
