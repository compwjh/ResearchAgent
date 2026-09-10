# Spec018 Task06：批量补偿真实闭环加固报告

## 结论

**IMPLEMENTED-IN-ISOLATION**。本轮修复了评审指出的批量编排与既有论文导入适配器之间的凭证、补偿注入和 attempt 审计缺口；验证仅使用临时目录与隔离 SQLite，没有访问真实 Qdrant、服务、网络或 `confirm-replace`。

## 改动文件

- `backend/app/paper_discovery/application/paper_import_batch_service.py`
  - claim/resume 为当前 attempt 生成 owner/token，并显式传给 `import_candidate`；旧 importer 签名仍由既有参数兼容层支持。
  - 真实导入异常保留 capability，供失败状态持久化与补偿。
  - 同进程 snapshot 只有在 canonical JSON 的 SHA-256 与 SQLite 记录一致时才复用，否则使用已校验的持久化快照。
- `backend/app/paper_discovery/application/paper_import.py`
  - 将批次凭证写入既有 `PaperImportRequest`；导入结果转异常时保留 resource capability。
- `backend/app/api/common.py`
  - 默认批服务绑定既有 `PaperImportPort.compensate_import`，与单篇导入共用同一个应用适配器。
- `backend/app/paper_discovery/infrastructure/paper_import_batch_store.py`
  - `cancel_batch` 只更新每个条目的当前 attempt，历史 attempt 状态保持不变。
- `tests/test_paper_import_batch_service.py`
  - 覆盖 claim 凭证传递。
- `tests/test_paper_import_batch_integration.py`
  - 使用真实 `KnowledgeBasePaperImportAdapter` + SQLite 批服务验证索引失败、capability 持久化、真实 compensator 和重试闭环；另验证默认 composition root 绑定同一 KB port。

## 验证命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_import_batch_service.py tests/test_paper_import_batch.py tests/test_paper_import_batch_integration.py tests/test_paper_import.py tests/test_import_compensation.py tests/test_kb_application_boundary.py` | 0 | 44 passed |
| `.venv/bin/ruff check backend/app/api/common.py backend/app/paper_discovery/application/paper_import.py backend/app/paper_discovery/application/paper_import_batch_service.py backend/app/paper_discovery/infrastructure/paper_import_batch_store.py backend/app/paper_discovery/domain/paper_import_batch.py tests/test_paper_import_batch.py tests/test_paper_import_batch_integration.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile`（上述实现与测试文件） | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 剩余风险与边界

- 本轮未修改 browser；browser session/profile、generation binding 和生产门禁仍需后续 Task06 阶段处理。
- 既有 fail-closed 策略在无法证明安全删除 source 时会保留 `cleanup_pending`；测试通过受控删除模拟维护完成后的补偿闭环，不改变该安全语义。
- `PaperImportBatchStore` 的 schema 版本演进仍按既有实现处理，未在本轮扩大范围。
- 本轮不提交 commit，由主 Agent 在独立评审和 Task06 矩阵更新后统一提交。

## 日志

`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910-071500.md`
