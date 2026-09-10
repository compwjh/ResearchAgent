# Spec018 Task06：历史知识库回归测试迁移报告

## 结论

完成 `tests/test_legacy_kb_integration.py` 中 3 个历史失败测试的最小迁移，未恢复已退休的 `submit_index_task`、`delete_paper` 或无代际绑定的 `index_paper_chunker` 调用。该文件现有 5 项测试全部通过，验证对象已切换到当前 canonical document/generation-bound API。

## 迁移内容

### 重建索引

- 历史测试中的低层索引调用增加显式 `destination_collection="papers_rebuild_live"`，保留真实临时 PDF 与 `FakeQdrant` seam。
- 测试夹具改为 `knowledge-document-v1` 记录，写入源文件摘要，并发布受控 generation marker。
- HTTP 断言从历史 `/api/kb/papers/{id}/reindex` 及旧 `submit_index_task` patch，迁移到 canonical `/api/kb/documents/{id}/reindex` 和 `submit_document_reindex` 入口。
- 断言当前 202 queued 响应及任务字段，不依赖已删除的旧内部提交函数。

### 缺失原件

- 使用 canonical 文档记录与 `/api/kb/documents/{id}/reindex` 路由。
- 通过 canonical `application.submit_document_reindex` 在隔离的临时 metadata/source 路径上返回 `SOURCE_NOT_FOUND`。
- 断言 404 稳定错误码，并确认 canonical 应用入口被调用；没有 patch 或调用旧 helper。

### 删除同名文件隔离

- 使用一个 legacy `paper_id` 记录和一个 canonical `document_id` 记录，它们共享展示用 `file_name`，但使用不同的 server-owned `stored_name`。
- 通过 canonical `DELETE /api/kb/documents/{id}` 路由及 `application.delete_document`，显式绑定 `papers_rebuild_live`。
- 断言 canonical 源文件被删除、legacy 同名源文件仍存在、metadata 中 legacy 记录仍保留。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_legacy_kb_integration.py` | 0 | 5 passed |
| `.venv/bin/python -m pytest -q tests/test_legacy_kb_integration.py tests/test_kb_document_routes.py tests/test_kb_document_reindex.py tests/test_kb_document_delete.py` | 0 | 30 passed |
| `.venv/bin/python -m pytest -q` | 0 | 902 passed，38 subtests passed |
| `.venv/bin/ruff check tests/test_legacy_kb_integration.py` | 0 | 通过 |
| `.venv/bin/python -m py_compile tests/test_legacy_kb_integration.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

测试只使用临时 metadata、临时原件和内存 `FakeQdrant`，未访问真实 Qdrant、网络、Ollama 或项目 `data/kb`。

## 决策依据与边界

- 当前 application 层要求索引写入携带 generation-bound collection；因此测试显式构造并绑定 `papers_rebuild_live`。
- canonical document API 只接受 `knowledge-document-v1` 文档；历史记录仍由列表/问答兼容测试覆盖，但不再伪装成 canonical 文档参与重建。
- 删除必须按 document id 与 `stored_name` 定位，不能按展示 `file_name` 删除；同名隔离测试直接验证该约束。
- 本报告不代表真实 Qdrant、跨进程锁、真实浏览器登录或生产索引切换已经验收；这些仍由 Task06 的生产门禁控制。

## 执行记录

- 角色：backend-dev（Luna high，本次临时分派）
- 状态：完成；未提交独立 commit，由主 Agent 在同一 Spec 分支统一收口
- 改动文件：`tests/test_legacy_kb_integration.py`、本报告
- 风险/阻塞：无本次迁移阻塞；生产级索引切换仍按 Task06 总体状态保持独立门禁
- 主 Agent 后续动作：读取本报告，将历史回归从 `migration_unverified` 更新为 canonical 测试通过证据；与浏览器生命周期等 Task06 变更一起审阅、提交。
- 开始时间：2026-09-10（具体时刻未由编排器提供）
- 结束时间：2026-09-10（具体时刻未由编排器提供）
- 总耗时：约 3 分钟（含全量 pytest 156.15 秒）
- 模型、token、工具统计：模型为 Luna high；token 与工具调用统计未提供。
