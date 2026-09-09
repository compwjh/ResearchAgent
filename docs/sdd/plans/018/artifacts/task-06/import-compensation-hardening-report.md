# Spec018 Task06：T-IMPORT-COMPENSATION compensation hardening report

## 固定结果字段

```text
task=T-IMPORT-COMPENSATION
role=backend-dev
result=IMPLEMENTED-IN-ISOLATION
scope=P1 source/download cleanup race, attempt-private temp root, ledger durability
cleanup_contract=owner-token-hash-inode-fail-closed
unknown_result=cleanup_pending
real_data_or_kb_touched=false
qdrant_or_service_touched=false
network_or_confirm_replace=false
batch_retry_cancel_expired_lease=deferred
generation_binding_protocol=unchanged
```

## 本轮实现

- `compensate_import_resource` 保持 immutable lock-domain、owner/token/document/stored-name/hash/dev/ino 校验；source 经 fd 与完整 hash 校验后不再执行 pathname unlink。POSIX 没有 compare-and-unlink 原语时，统一保留 source/metadata orphan，持久化 `cleanup_pending`，避免删除 replacement。
- `_cleanup_download` 改用 `O_NOFOLLOW` fd 与固定 attempt token 校验；attempt root 外、预存文件/目录、symlink、非 regular file 与所有父目录均不删除，无法证明归属时返回 `cleanup_pending`。token 在 downloader 返回后立即捕获，避免 finally 把 replacement 当成当前 attempt 资源。
- `import_candidate(temp_dir=None)` 为每次调用创建 `paper-import-*` attempt-private root，并只在 finally 移除本次创建的空目录；显式 caller root 保留不动，嵌套预存路径由递归 inventory 保护。
- `_write_compensation_ledger` 使用临时文件写入、flush+`fsync`、`os.replace`，再 fsync 父目录；任何未知 durability 失败均不报告 completed。
- 未实现 batch retry/cancel/expired lease，也未引入 generation binding 新协议；existing/dedupe 不创建或补偿资源。

## 改动文件

- `backend/app/knowledge_base/infrastructure/store.py`
- `backend/app/paper_discovery/application/paper_import.py`
- `tests/test_import_compensation.py`
- 本报告

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py` | 0 | 8 passed；覆盖 source fail-closed、检查后 replacement 保留、download replacement/root 边界、temp_dir=None、ledger fsync |
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py tests/test_kb_immutable_create.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py tests/test_kb_startup_generation_gate.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py` | 0 | 60 passed |
| `.venv/bin/python -m pytest -q tests/test_paper_import.py` | 1 | 8 passed、2 failed；既有断言要求 index failure 删除 source/metadata，与本轮 fail-closed orphan/`cleanup_pending` 合同冲突，未修改该非本任务测试文件 |
| `.venv/bin/ruff check backend/app/knowledge_base/infrastructure/store.py backend/app/knowledge_base/application.py backend/app/paper_discovery/application/paper_import.py tests/test_import_compensation.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/store.py backend/app/knowledge_base/application.py backend/app/paper_discovery/application/paper_import.py tests/test_import_compensation.py` | 0 | 编译通过 |
| `git diff --check` | 0 | 无空白/冲突标记 |

## 交接与限制

- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910-060524.md`
- 当前工作树含 parent/其他任务既有改动；本角色未修改 closure matrix、spec 状态、真实 `data/kb`、Qdrant、服务或网络资源。
- 独立 tester 应更新与新合同冲突的旧 import failure 断言，并继续验证 batch compensation、generation collection 绑定与 production gate；这些均不在本轮实现范围内。
