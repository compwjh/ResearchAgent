# Spec018 Task06：generation binding 独立测试报告

## 测试身份与边界

```text
role=backend-tester
model=Luna high（本次分派）
task=T-GENERATION-BINDING
result=PASS（隔离门）
production_cutover=NO-GO
real_data_or_kb_touched=false
qdrant_or_service_touched=false
network_or_confirm_replace=false
business_code_modified=false
```

本报告针对当前工作树中未提交的 generation binding 变更执行独立验证。测试只使用临时目录、固定样本和现有测试 fixture，没有连接真实知识库、Qdrant、服务或外部网络。`destination_collection` 的 capability 序列化探针使用 `to_internal_dict()` 后重建 DTO，再走既有补偿入口；补偿返回 `cleanup_pending` 是当前 fail-closed 语义，不代表测试失败。

## 命令结果

| 命令 | 退出码 | 耗时 | 结果 |
|---|---:|---:|---|
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py tests/test_paper_import.py tests/test_kb_immutable_create.py tests/test_kb_application_boundary.py` | 0 | 0.49s | 44 passed |
| `.venv/bin/python -m pytest -q tests/test_paper_import.py tests/test_paper_import_batch.py` | 0 | 0.46s | 14 passed |
| `.venv/bin/python -m pytest -q tests/test_paper_import.py tests/test_paper_import_batch.py -k compensation` | 0 | 0.43s | 1 passed，13 deselected |
| `.venv/bin/python -m pytest -q tests/test_kb_immutable_create.py tests/test_kb_document_routes.py tests/test_paper_import.py -k 'immutable or dedupe or same_name or concurrent'` | 0 | 0.87s | 15 passed，27 deselected |
| `.venv/bin/ruff check backend/app/knowledge_base/application.py backend/app/platform/ports.py tests/test_import_compensation.py` | 0 | <0.1s | All checks passed |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/application.py backend/app/platform/ports.py tests/test_import_compensation.py` | 0 | <0.1s | 通过 |
| `git diff --check` | 0 | <0.1s | 通过 |

## 新增定向探针

| 探针 | 命令/方式 | 结果 |
|---|---|---|
| marker drift | `tests/test_import_compensation.py::test_default_deleter_uses_creation_generation_after_marker_drift` | 1 passed；marker 切换后仍使用创建时 collection，0.38s |
| 缺 marker 零写 | `tests/test_import_compensation.py::test_default_paper_import_without_generation_marker_fails_before_create` | 1 passed；返回失败且 source、metadata 均不存在，0.37s |
| capability 序列化与补偿 | 临时目录中创建带 `destination_collection= papers_rebuild_one` 的 capability，经 `to_internal_dict()`/`ImportResourceCapability(**payload)` 重建后调用 `compensate_import_resource` | PASS；collection 保留，补偿返回 `cleanup_pending`，metadata 记录保留 |

## 覆盖范围

- 论文导入 adapter 在创建 immutable source 前捕获 generation marker；缺失 marker 时 fail-closed，未产生 source 或 metadata 写入。
- capability 保存创建时的 `destination_collection`，而不是在补偿/删除时重新读取当前 marker。
- marker 发生 drift 后，默认 deleter 仍绑定创建 generation。
- capability 的内部字典序列化不会丢失 collection；反序列化后的 capability 仍可进入同一补偿 seam。
- immutable create、论文导入、导入补偿、应用边界及批量导入回归均通过；本轮未宣称批处理、browser boundary 或 Task06 整体闭合。

## 结论与后续动作

结论为 **PASS（generation binding 隔离门）**。当前变更满足本报告覆盖的 marker binding、缺 marker 零写和 capability 序列化探针；未发现回归失败。

该结论不等价于 Task06 生产 GO。主 Agent 仍需汇总 batch compensation 与 browser boundary 的独立证据，最终重算 closure matrix inventory hash/digest，并在所有 required test 与 reviewer 门禁闭合前保持真实 Qdrant、索引切换和 `confirm-replace` 禁止。

## 变更与敏感信息检查

- 测试期间未修改业务代码、未修改真实数据、未执行 commit/push/deploy。
- `git diff --check` 通过；报告和测试输出不含密码、Cookie、Token 或敏感命令。测试中的 token 仅为临时 fixture，不写入 HTTP 响应。

