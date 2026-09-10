# Task06 Generation-Bound 加固测试报告（v2）

## 结论

**通过（PASS）**。指定的 generation-bound 加固及直接后端回归全部通过：destination_collection 篡改拒绝、marker drift 后仍使用创建代次、缺少绑定时 fail-closed，以及代次漂移时不错误标记为 `indexed` 均有测试覆盖并通过。

## 命令

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `python -m pytest -q tests/test_import_compensation.py tests/test_paper_import.py tests/test_kb_immutable_create.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py` | 0 | `63 passed in 0.70s` |
| `.venv/bin/ruff check backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py backend/app/platform/ports.py tests/test_import_compensation.py tests/test_paper_import.py tests/test_kb_immutable_create.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py` | 0 | `All checks passed!`（ruff 0.16.6） |
| `python -m py_compile backend/app/knowledge_base/application.py backend/app/knowledge_base/infrastructure/store.py backend/app/platform/ports.py tests/test_import_compensation.py tests/test_paper_import.py tests/test_kb_immutable_create.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py` | 0 | 语法校验通过 |
| `git diff --check` | 0 | 空白/差异格式校验通过 |

## 数量

- 总计：63 个测试，63 通过，0 失败。
- `tests/test_import_compensation.py`：19 个
- `tests/test_paper_import.py`：10 个
- `tests/test_kb_immutable_create.py`：14 个
- `tests/test_kb_application_boundary.py`：6 个
- `tests/test_kb_document_boundary.py`：14 个

## 未覆盖的真实环境边界

- 未连接真实 Qdrant，也未验证真实 collection/alias、网络错误或服务端权限行为。
- 未启动 FastAPI/后台服务做端到端验证。
- 未执行 `confirm-replace` 或真实 finalize/切换流程。
- 未覆盖多进程/多实例并发导入、进程崩溃恢复、真实部署期间 marker 与 collection 同步异常。
- 本轮测试使用本地临时目录和测试替身；不代表生产数据迁移或既有 Qdrant 数据的完整性验证。

## 环境备注

项目 `.venv/bin/pytest` 的解释器链指向不存在的 `/Users/wjh/PyCharmMiscProject/.venv/bin/python`，因此 pytest 使用可用的 `python -m pytest` 执行；未修改虚拟环境或项目代码。项目内置 `.venv/bin/ruff` 可直接运行并通过。
