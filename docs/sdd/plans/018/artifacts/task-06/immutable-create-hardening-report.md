# Spec018 Task06：immutable create hardening report

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

- `application._write_source_exclusive` 使用 `O_EXCL` 创建 source，并返回本次创建对象的设备/inode ownership token。打开失败没有 token，不执行 unlink；写入或 fsync 失败由写入函数按 token 清理自己创建的部分文件。
- `create_immutable_document` 的异常路径只按 token 清理本次成功创建且仍由当前调用独占的 target。若目标被另一进程替换、变成 symlink，或获得额外 hard link，则保留目标；metadata partial append 只回滚本次 server-generated `document_id`，不再调用会按路径删除 source 的通用删除函数。
- `source_path` 成功、去重、metadata 失败及 indexing 失败均不由知识库 create seam unlink；论文下载临时文件继续由 `paper_discovery.application.paper_import.import_candidate` 的 `finally` 清理。
- 直接 adapter 测试契约已更新为调用者 source 保留，并新增普通预存文件、悬空 symlink、替换 target 后 metadata 失败的清理回归。

## 验证

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_immutable_create.py tests/test_paper_import.py tests/test_kb_application_boundary.py` | 0 | 25 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_document_reindex.py tests/test_kb_document_routes.py tests/test_kb_startup_generation_gate.py -k 'generation or destination'` | 0 | 8 passed, 17 deselected |
| `.venv/bin/ruff check backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py tests/test_kb_immutable_create.py tests/test_paper_import.py tests/test_kb_application_boundary.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py tests/test_kb_immutable_create.py tests/test_paper_import.py tests/test_kb_application_boundary.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| `.venv/bin/python -m pytest -q tests/test_kb_upload_closure_matrix.py -k 'inventory'` | 1 | 1 passed、1 failed；冻结 matrix 中 `application.py` SHA 与当前工作树不一致。按任务要求未修改 matrix；该失败不是本轮 hardening 断言失败 |

## 剩余 owner/token compensation 风险

- 本轮只关闭 immutable create 的 target/source ownership 清理缺口；paper import/batch retry、resume、过期 lease、browser session 和跨进程 compensation 的 owner/token capability 仍未实现。
- 当前 adapter indexing 失败后的 vector/source compensation 仍依赖后续 T-IMPORT-COMPENSATION；本轮不宣称其幂等持久化 lease、`cleanup_pending` 或恢复协议已完成。
- 进程内 `_UPLOAD_LOCK` 不构成跨进程互斥；文件系统层通过 `O_EXCL` 与 token 校验避免误删，但生产级跨进程 metadata lease/owner 仍属后续任务。
- closure matrix 仍保持原状态，真实 data/kb、Qdrant、服务启动和 `--confirm-replace` 均未触碰。

## 交接

- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910-immutable-create-hardening.md`
- 主 Agent 应让独立 backend-tester 按上述命令复验，并由 matrix owner 单独处理冻结 inventory hash 证据；不得据此更新 matrix 为 `verified` 或放行生产切换。
