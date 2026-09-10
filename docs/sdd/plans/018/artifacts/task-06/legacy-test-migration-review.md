# Spec018 Task06 历史测试迁移独立评审

## 结论

**GO（测试迁移范围）**。`tests/test_legacy_kb_integration.py` 中原先阻塞全量回归的 3 个历史测试已经切换到 canonical document/generation-bound API；没有恢复或调用已退休的 `routes.submit_index_task`、`routes.delete_paper`，也没有保留不带 `destination_collection` 的低层索引写入口。

本结论只覆盖历史测试迁移和离线回归，不代表 Spec018 Task06 的真实 Qdrant、跨进程锁、浏览器登录或生产索引切换门禁已经通过。

## 评审范围与证据

- 评审文件：`tests/test_legacy_kb_integration.py`、`docs/sdd/plans/018/artifacts/task-06/legacy-test-migration-report.md`。
- 迁移 diff：
  - 重建索引测试使用 `knowledge-document-v1` 记录，发布 `papers_rebuild_live` generation marker，并调用 `index_paper_chunker(..., destination_collection="papers_rebuild_live")`。
  - HTTP 重建断言使用 `POST /api/kb/documents/{document_id}/reindex` 和 `routes.submit_document_reindex`，断言 `202`、`queued` 和任务字段。
  - 缺失原件测试使用 canonical document route，并通过 `application.submit_document_reindex` 真实返回 `SOURCE_NOT_FOUND`。
  - 同名删除隔离测试使用 `DELETE /api/kb/documents/{document_id}`，通过 `application.delete_document(..., destination_collection="papers_rebuild_live")` 真实处理 metadata/source/manifests，验证 legacy 同名原件和记录不受影响。
- 静态搜索：目标测试文件未出现 `submit_index_task`、`delete_paper`；所有 `index_paper_chunker` 调用均带显式 `destination_collection`。

## 分级问题

### P0

无。

### P1

无。

### P2（不阻断本次迁移 GO）

1. HTTP 重建测试对 `routes.submit_document_reindex` 使用返回值替身，并对 `_require_generation` 使用 `None` 替身，因此该测试本身验证的是 canonical route 的请求/响应和分派契约，不是从真实临时 generation marker 走完整路由链路。相邻 canonical 测试已覆盖 generation gate 与 application seam；如需提升集成强度，可将路由级 fixtures 的 `KB_DIR` 也隔离到 `tmp_path`，移除 `_require_generation` patch。
2. 删除测试对 `GenerationBoundIndexPort.delete_document` 使用 no-op 替身，避免触碰真实 Qdrant；这保留了 metadata/source/tombstone 和同名隔离断言，但不验证真实向量删除。该边界符合本次离线测试约束，向量端已有独立删除/补偿测试覆盖。
3. 迁移报告把本次未提交工作树描述为“未提交独立 commit，由主 Agent 统一收口”，不是代码缺陷；收口时应将测试和报告与实现放入同一 Spec018 提交，避免验收文档游离。

上述替身没有绕过本次迁移要验证的关键事实：低层 generation-bound 写入已用临时 `FakeQdrant` 真实执行，缺失源文件和 canonical 删除的 application 逻辑已实际执行；但 P2 项应保留在 Task06 的测试边界记录中，不能把它们表述为真实 Qdrant/完整路由集成已验收。

## 全局状态与断言检查

- 每个测试通过 `_enter_patches` / `finally` / `_exit_patches` 成对管理模块常量 patch；未发现跨测试共享可变 fixture、模块级临时目录、持久化项目 metadata 或未恢复的 monkeypatch。
- `TestClient(app)` 只使用临时 metadata/source 路径；未访问项目 `data/kb`、真实 Qdrant、网络或 Ollama。
- 断言均针对可观察状态：HTTP status、稳定 `error_code`、任务状态、向量替身 upsert payload、源文件存在性、metadata 剩余记录；未发现通过弱化为“调用过即可”而掩盖错误状态的断言。删除测试中的 `delete.assert_called_once_with("new-001")` 与文件/metadata 断言共同保证目标是 canonical document 而非展示 `file_name`。
- 旧 API 名称未恢复；后端生产代码中仍存在基础设施层 `submit_index_task` / `delete_paper` 定义，但迁移测试没有直接依赖它们，不能据此判定旧测试链路已复活。

## 验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_legacy_kb_integration.py tests/test_kb_document_routes.py tests/test_kb_document_reindex.py tests/test_kb_document_delete.py` | 0 | 30 passed |
| `.venv/bin/python -m pytest -q` | 0 | 902 passed，5 warnings，38 subtests passed，约 132 秒 |
| `.venv/bin/ruff check tests/test_legacy_kb_integration.py` | 0 | 通过 |
| `.venv/bin/python -m py_compile tests/test_legacy_kb_integration.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| 冲突标记扫描 | 0 | 未发现 `<<<<<<<` / `=======` / `>>>>>>>` |

测试期间仅观察到已有的 PyMuPDF deprecation warning 与 Langfuse 本地 `127.0.0.1:3000` 导出失败重试；均未改变测试退出码。

## 后续动作

1. 主 Agent 可将 `legacy-test-migration-report.md` 的 3 个历史失败项从 `migration_unverified` 更新为“canonical 迁移已验证”，保留本报告的 P2 测试边界说明。
2. 将 `tests/test_legacy_kb_integration.py` 与本报告纳入 Task06 同一 Spec 分支提交，并在提交前再次确认未混入 Spec017/其他 Spec 文件。
3. Task06 仍须独立完成真实 Qdrant、跨进程租约/锁、真实浏览器登录和确认替换等生产门禁；本报告不改变其总体 NO-GO/实施中状态。

## 执行记录

- 角色：backend-reviewer（Luna high，本次临时分派）
- 评审状态：完成；只读评审，未修改实现和测试
- 报告路径：`docs/sdd/plans/018/artifacts/task-06/legacy-test-migration-review.md`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/legacy-test-migration-review/20260910-103431.md`
- 开始时间：2026-09-10 10:34（Asia/Shanghai）
- 结束时间：2026-09-10 10:38（Asia/Shanghai）
- 总耗时：约 4 分钟（含全量 pytest 约 132 秒）
- 模型、token、工具统计：模型为 Luna high；token 与工具调用统计未提供
