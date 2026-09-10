# Task 06 历史知识库回归分析

## 结论

本次全量回归中 `tests/test_legacy_kb_integration.py` 的 5 个失败不是同一个业务回归：

* 首个失败发生在测试 setup：`routes_kb.KB_PAPERS_DIR` 已不再是路由实现依赖的模块成员，旧 fixture 因 `patch.object` 找不到名称而中止。
* 加回只读的模块级配置别名后，列表/问答历史兼容测试通过；剩余 3 个失败进入测试体后，暴露的是历史测试依赖的旧内部符号和旧索引契约，而不是新文档 API 的故障。

## 根因与处置

### 1. 配置别名

`routes_kb.py` 现在通过 `knowledge_base.application` 的受控入口实现文档操作，路由本身不应直接持有旧文件写入链。为了让离线 fixture 能继续表达临时原件目录，恢复了 `KB_PAPERS_DIR` 的模块级只读导入别名，并明确注释其用途。它没有被任何生产路径用于读写，也没有恢复第二套存储实现、隐式旧索引写链或真实 Qdrant 访问。

### 2. 仍失败的 3 项

* `test_reindex_uses_legacy_physical_path_and_real_pdf_with_fake_qdrant` 直接调用 `index.index_paper_chunker`，但当前索引边界要求显式且已提交的 `destination_collection`，防止写入未绑定代际；旧测试省略该门禁参数。
* `test_missing_legacy_file_returns_404_without_submitting_reindex` patch 已移除的 `routes.submit_index_task`。当前 `/api/kb/papers/{id}/reindex` 是兼容别名，转发到 `/api/kb/documents/{id}/reindex`，并由 `submit_document_reindex` 负责代际校验与提交。
* `test_deleting_legacy_same_name_does_not_remove_new_record` patch 已移除的 `routes.delete_paper`。当前删除兼容别名转发到受控的 `delete_document_route`，不再调用旧 `delete_paper` 符号。

这些符号若为让旧测试通过而重新导出，会重新扩大已收窄的应用边界，并会掩盖 Spec018 要求的 generation-bound index/delete 约束。因此没有添加它们，也没有修改测试断言来伪造通过。该测试文件应标记为 `legacy/migration_unverified`，后续迁移为 canonical document API 测试；旧索引调用应在测试中显式构造代际绑定端口或改用应用入口。

## 验证

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_legacy_kb_integration.py`（别名修复后） | 2 passed, 3 failed；失败均为上述已废弃符号/门禁契约 |
| `.venv/bin/python -m pytest -q tests/test_legacy_kb_integration.py::test_legacy_record_is_listed_and_ask_reads_legacy_qdrant_hit` | 1 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_document_routes.py tests/test_kb_document_reindex.py tests/test_kb_document_delete.py` | 25 passed |
| `git diff --check` | 通过 |

测试未访问公网、Ollama、真实项目 `data`、Qdrant 或生产文件；没有执行清理、回滚或修改历史测试。

## 架构影响

仅新增 `routes_kb.KB_PAPERS_DIR` 的测试/离线配置别名，生产代码仍走知识库受控应用入口。没有恢复旧 `submit_index_task`/`delete_paper` 导出，也没有改变 Spec018 的索引代际、删除补偿或不可变源约束。该修复可保留；历史测试不能作为 Task06 通过证据，直到完成 canonical API 迁移并重新验收。

## 执行记录

* 角色：backend-dev（Luna high，本次临时分派）
* 状态：已完成分析；未提交 commit
* 改动文件：`backend/app/api/routes_kb.py`、本报告
* 主 Agent 后续动作：将该文件记录为历史回归迁移项；不要把 3 项旧契约失败计入新文档 API 的通过证据；Task06 仍需按当前矩阵执行独立验收。
