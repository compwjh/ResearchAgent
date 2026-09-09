# Spec018 Task06：T-IMPORT-COMPENSATION backend implementation report

## 状态摘要

```text
task=T-IMPORT-COMPENSATION
result=IMPLEMENTED-IN-ISOLATION
cleanup_contract=owner-token-hash-inode-fail-closed
unknown_result=cleanup_pending
real_data_or_kb_touched=false
qdrant_or_service_touched=false
network_or_confirm_replace=false
```

本轮只实现单篇 paper-import 的 attempt capability 与 source/metadata/vector 补偿 seam。没有修改 closure matrix 或 spec 状态；batch 状态机、browser login/resume boundary 和真实切换仍未完成。

## 改动文件

- `backend/app/platform/ports.py`
  - `PaperImportRequest` 每次构造生成不可猜测 `attempt_owner`/`attempt_token`，并记录 `source_sha256`。
  - 新增内部 `ImportResourceCapability`（owner/token/document/source hash/stored name/inode）；`PaperImportResult` 记录 capability 与 `cleanup_status`。
  - 扩展 `PaperImportPort.compensate_import` seam；HTTP 层仍只取既有白名单字段，不返回 token。
- `backend/app/knowledge_base/infrastructure/store.py`
  - 新增独立补偿 ledger（不改变冻结的 knowledge-document schema）。
  - `compensate_import_resource` 同时校验 ledger owner/token、document、stored name、source hash 和 dev/ino；任何不匹配 fail-closed，重复完成返回 `completed`，异常结果保持 `cleanup_pending`。
- `backend/app/knowledge_base/application.py`
  - immutable create 接收 attempt owner/token 并注册 capability；paper adapter 将失败补偿限制到该 capability。
  - vector deleter 结果未知时不清理 source/metadata，返回 `cleanup_pending`；隔离无 vector client 时仍兼容既有测试 seam。
- `backend/app/paper_discovery/application/paper_import.py`
  - request 携带下载 source hash；临时下载清理只允许 attempt root 内新建文件或显式 inode capability，预存路径和 caller 父目录不删除。
  - discovery result 保留内部 cleanup 状态/capability，但序列化不暴露 secret。
- `tests/test_import_compensation.py`
  - 临时目录契约覆盖同 owner/token 重试幂等、不同 owner/token/hash 拒绝、index/vector unknown 的 `cleanup_pending`、预存下载路径保留。

## 测试命令 / 退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py tests/test_paper_import.py tests/test_kb_immutable_create.py` | 0 | 28 passed |
| `.venv/bin/python -m pytest -q tests/test_paper_import.py tests/test_import_compensation.py tests/test_kb_immutable_create.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py tests/test_kb_services.py tests/test_kb_document_routes.py tests/test_kb_document_reindex.py` | 0 | 147 passed, 5 warnings |
| `.venv/bin/ruff check backend/app/platform/ports.py backend/app/knowledge_base/infrastructure/store.py backend/app/knowledge_base/application.py backend/app/paper_discovery/application/paper_import.py tests/test_import_compensation.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/platform/ports.py backend/app/knowledge_base/infrastructure/store.py backend/app/knowledge_base/application.py backend/app/paper_discovery/application/paper_import.py tests/test_import_compensation.py` | 0 | 编译通过 |
| `git diff --check` | 0 | 无空白/冲突标记问题 |

## 风险与阻塞

- compensation ledger 是本轮新增的本地 sidecar；batch retry/cancel/expired-lease 尚未接入该 seam，不能宣称跨重启 batch compensation 已完成。
- vector 删除结果由注入 deleter 或 marker-bound default 决定；异常/不确定结果保留资源并稳定返回 `cleanup_pending`，需要后续 retry/resume 驱动。
- 当前 closure matrix 仍由 matrix owner 维护为未验证；没有访问真实 data/kb、Qdrant、服务、网络或 `confirm-replace`。

## 主 Agent 后续动作

1. 复核本报告与代码 diff，确认 sidecar ledger 路径纳入允许的本地 artifact 范围。
2. 由独立 backend-reviewer / backend-tester 复跑本轮契约并检查 API 白名单不泄露 token。
3. 后续 batch/browser 任务分别接入 capability，但不要把本报告作为 batch 状态机或 browser boundary 的完成证明。

