# Spec018 Task06：immutable create implementation report

## 结论

```text
task=T-IMMUTABLE-CREATE (step 1: immutable create contract)
result=IMPLEMENTED-IN-ISOLATION
real_data_or_kb_touched=false
qdrant_or_service_touched=false
network_or_confirm_replace=false
```

本轮只实现 source/metadata 创建 seam，不更新 closure matrix 或 spec 状态，也未执行真实 data/kb、Qdrant、服务启动、网络访问或 `--confirm-replace`。

## 实际改动

- `backend/app/knowledge_base/application.py`
  - 新增 `create_immutable_document`：统一 upload bytes 与 paper trusted source path 的 server-owned UUID、独占 source 写、sha256+media 去重、同名安全 basename 冲突处理、metadata append 与 source hash/ETag 一致性。
  - `create_uploaded_document` 降为唯一 seam 的兼容包装；不触碰 generation-bound index 行为。
  - `KnowledgeBasePaperImportAdapter.import_paper` 改为调用该 seam；hash/media 命中已有 canonical source 时返回 existing，不再自行 copy/build/write。
  - metadata writer 写入后异常时，仅按本次 server-generated document ID 做安全清理，避免选择既有文档。
- `backend/app/knowledge_base/infrastructure/store.py`
  - `save_upload` 保留 legacy 调用形状但改为 `xb` 独占写、目录 fsync、ID 格式校验；同 ID 已存在返回 `SOURCE_ID_CONFLICT`，绝不覆盖已有 source。
- `tests/test_kb_immutable_create.py`
  - 新增临时目录契约：同 ID 冲突保持原 bytes、hash/media 去重与 ETag/source 一致、同名不同 bytes 生成新 ID、8 线程并发只创建一个 canonical record，以及 paper adapter 的跨 identity hash 去重/同名不同 bytes。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_immutable_create.py` | 0 | 4 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_immutable_create.py tests/test_paper_import.py` | 0 | 16 passed |
| `.venv/bin/python -m pytest -q tests/test_paper_import.py tests/test_kb_application_boundary.py tests/test_kb_document_routes.py tests/test_kb_services.py` | 0 | 111 passed, 5 warnings |
| `.venv/bin/ruff check backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py tests/test_kb_immutable_create.py tests/test_paper_import.py tests/test_kb_application_boundary.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py backend/app/paper_discovery/application/paper_import.py tests/test_kb_immutable_create.py` | 0 | 编译通过 |
| `git diff --check` | 0 | 无空白/冲突标记问题 |

## 明确未覆盖与后续 owner/token

- 本轮没有伪造 compensation 完成：paper/batch 的 attempt owner/token、resource capability、`cleanup_pending` 持久化、失败/取消/过期 lease 的幂等补偿仍由后续 T-IMPORT-COMPENSATION owner 实现。
- batch retry/resume、真实 adapter batch 集成、browser login/resume 的 session owner/token 与零持久化边界仍是后续 T-PAPER-IMPORT/T-BROWSER-BOUNDARY 阻塞；matrix required tests 仍 pending。
- 论文导入已有 candidate identity 的下载前去重行为保持不变；下载后所有新 source 创建/全局 hash+media 去重均进入本 seam。
- `save_upload` 仍作为 legacy infrastructure 符号存在，生产调用方应继续迁移到 application seam；本轮不恢复任何固定 collection 或索引旁路。

## 交接

- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910-immutable-create.md`
- 主 Agent 后续：先由独立 backend-reviewer 审查本实现和测试，再由 backend-tester 复跑契约；随后分派 compensation、batch/browser boundary，最后由 matrix owner 汇总 closure 证据。不得因本报告通过而更新 matrix 为 verified 或进入真实切换。
