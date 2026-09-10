# Spec018 Task06：batch compensation durable implementation report

## 状态摘要

```text
task=T-IMPORT-COMPENSATION / batch durable seam
result=IMPLEMENTED-IN-ISOLATION
lease_owner_separate_from_resource_token=true
snapshot_recovery=sqlite-json-hash
unknown_result=cleanup_pending
completed_reexecution=false
real_data_or_kb_touched=false
qdrant_or_service_touched=false
network_or_confirm_replace=false
```

本轮只改批次状态、批次 API 白名单和隔离测试。每次 claim/resume 都在
`paper_import_attempts` 留下 durable attempt 记录，并在 item 上保存当前 attempt
的 lease/resource 关联。resource capability 只接受 owner/token、document/stored
name、source SHA-256、dev/ino、destination collection 等有限字段的 JSON；token
和 lease owner 均不进入 `to_dict()` 或 HTTP payload。

失败、取消、过期 lease 的 item 若拥有 capability 会保持 `cleanup_pending`。retry
和 resume 只有在注入的 compensation seam 以同一个 persisted owner/token 返回
`completed` 后才继续；未知/无 compensator 结果不会被猜测为成功。completed item
仍不能被 claim 或 process 重跑。

批次创建时将 server candidate snapshot 以 canonical JSON 和 SHA-256 持久化，并
保存搜索过期时间。新 service 进程优先从 SQLite 重建 snapshot；缺失、篡改、
search_id 不一致、重复 candidate 或过期状态分别稳定返回错误，不依赖
`self._snapshots` 猜测。

## 改动文件

- `backend/app/paper_discovery/infrastructure/paper_import_batch_store.py`
  - 加入 additive schema migration、attempt history、snapshot/hash、capability
    JSON 和 cleanup 状态。
  - claim/resume 产生新 attempt；resource compensation 严格校验 owner/token
    及完整 capability，幂等完成；cancel/expired 进入 pending。
- `backend/app/paper_discovery/application/paper_import_batch_service.py`
  - SQLite snapshot/hash 恢复和 search expiry 校验；失败结果携带 capability；
    retry/resume/cancel/expired 驱动可注入 compensation seam。
- `backend/app/paper_discovery/domain/paper_import_batch.py`
  - 增加内部 attempt/resource/snapshot 字段；`to_dict()` 明确排除 owner/token
    和 snapshot JSON。
- `backend/app/api/routes_paper.py`
  - 增加稳定错误映射、cleanup_status 白名单字段及 canonical cancel alias；
    不暴露 token、capability、inode 或 lease owner。
- `tests/test_paper_import_batch.py`
  - 新增 batch compensation contract：重启快照、capability 持久化、失败重试、
    completed 防重跑、cancel/expired pending、snapshot tamper rebuild。

## 验证命令 / 退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_import_batch.py` | 0 | 4 passed |
| `.venv/bin/python -m pytest -q tests/test_paper_import_batch_store.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py tests/test_paper_import.py tests/test_import_compensation.py` | 0 | 54 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py tests/test_kb_services.py tests/test_kb_document_routes.py tests/test_kb_document_reindex.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py tests/test_paper_import_batch_store.py tests/test_paper_import_batch.py` | 0 | 152 passed, 5 warnings, 4 subtests passed |
| `.venv/bin/ruff check`（四个实现文件 + batch contract test） | 0 | All checks passed |
| `.venv/bin/python -m py_compile`（四个实现文件 + batch contract test） | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 风险、阻塞与明确 deferred

- 本轮 compensation seam 通过 service constructor 注入；默认 production
  composition root 尚未把真实 KB adapter compensation provider 绑定到 batch
  service，因此不能宣称真实 source/metadata/vector cleanup 已闭合。
- generation binding、browser session token/login UI、browser profile persistence
  和 generation marker 仍 deferred；本轮没有改 browser、真实 data/kb、Qdrant、
  服务、网络或 `confirm-replace`。
- capability 的 vector `destination_collection` 会持久化并参与 equality
  校验，但真正 collection topology 的验证仍由 generation-bound adapter 负责。
- 旧数据库的缺失 snapshot/expiry 不会静默重建，服务稳定返回
  `SNAPSHOT_REBUILD_REQUIRED`；需要上游重新提交 server snapshot。

## 主 Agent 后续动作

1. 复核本报告和 diff，并由独立 backend-reviewer/backend-tester 运行
   `T-PAPER-IMPORT`、`T-IMPORT-COMPENSATION` exact matrix 命令。
2. 将真实 paper import adapter 的 compensation callable 与 generation-bound
   deleter 绑定，补真实 adapter 单篇/混合 batch、owner/token mismatch 和
   vector unknown contract（仍只在隔离环境）。
3. 验收通过后由 matrix owner 更新 closure evidence；browser/generation binding
   和真实生产门继续 deferred/NO-GO。

进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910-063435.md`
