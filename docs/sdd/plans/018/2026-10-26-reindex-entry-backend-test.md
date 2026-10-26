# Spec018 KB 重建入口后端独立回归报告

> 当前收口状态：本次后端窄修定向回归已完成；本报告的隔离测试结果与真实 API 复验由追加验收报告合并判定，历史边界不删除。

日期：2026-10-26。角色：backend-tester。工作树：`/Users/wjh/ResearchAgent`；分支：`codex/fix-kb-reindex-contract`；HEAD：`70b1af1f6bc4417ae8d998f7eed77bc3fe7e3e1c`。

## 结论

**PASS（仅限 publicationfix 后端精确范围）**。

- publication contract：`5 passed`，退出码 0。
- 目标集合：`50 passed`、`0 failed`、`0 skipped`，退出码 0。
- services/boundaries：`99 passed`、`0 failed`、`0 skipped`，另有 `4 subtests passed`，退出码 0。
- 默认 pytest conftest 当前可正常收集；不需要伪造 `--noconftest` 环境。此前 review 记录的 `--noconftest` 命令也已复跑通过，但本报告最终计数以当前默认 conftest 的绝对解释器结果为准。
- 未运行全仓 pytest、生产 Qdrant、真实 reindex、网络/模型调用、产品 POST、部署或 Git 写操作。

## 范围与指纹

本轮只核对：

- `backend/app/knowledge_base/infrastructure/index.py`
- `tests/kb/test_kb_index_publication_contract.py`
- 受影响回归集合：
  - `tests/kb/test_kb_index_publication_contract.py`
  - `tests/kb/test_kb_tasks.py`
  - `tests/kb/test_kb_pdf_safety_publication.py`
  - `tests/kb/test_kb_document_reindex.py`
  - `tests/kb/test_kb_services.py`
  - `tests/kb/test_kb_application_boundary.py`
  - `tests/kb/test_kb_document_boundary.py`

当前目标文件 SHA-256：

```text
536ef36bd0493e52b37c842331379f75a59765e3a7a3e4859bab0bff7b0919e1  backend/app/knowledge_base/infrastructure/index.py
06f53a2c38168a0ade31b7ed9dfe1b90778add6ed0648b8cead4ccb776e8fe12  tests/kb/test_kb_index_publication_contract.py
```

所有命令均使用绝对解释器 `/Users/wjh/ResearchAgent/.venv/bin/python`，并设置：

```text
PYTHON_DOTENV_DISABLED=1
LANGFUSE_ENABLED=false
OTEL_SDK_DISABLED=true
PYTHONDONTWRITEBYTECODE=1
PYTHONPYCACHEPREFIX=/private/tmp/spec018-backend-pycache
```

`OTEL_SDK_DISABLED=true` 用于避免测试观测器向 localhost 导出；没有产品网络请求。当前 `langchain_ollama` 导入可用，默认根 `conftest.py` 的 collection 通过，因此没有把 `--noconftest` 当作隐藏收集错误的前提。

## 精确测试结果

### 1. Publication contract（5 项）

```text
PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false OTEL_SDK_DISABLED=true \
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest \
  tests/kb/test_kb_index_publication_contract.py -q
```

结果：`5 passed in 1.19s`，退出码 0。

五项实际覆盖：

- 5→3 缩容清理当前文档+v2 尾点，并保留其他文档与同文档 v1；
- 删除失败时 `0 upsert`、`0 manifest publication`，错误为 `QDRANT_UNAVAILABLE`；
- upsert 后额外 point 使 ready/partial 发布前 fail-closed，错误为 `INDEX_FINALIZE_REQUIRED`；
- payload 文本漂移使发布前 fail-closed；
- 合法 unmapped partial bundle 仍到达 publication seam。

### 2. 目标集合（50 项）

```text
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest \
  tests/kb/test_kb_index_publication_contract.py \
  tests/kb/test_kb_tasks.py \
  tests/kb/test_kb_pdf_safety_publication.py \
  tests/kb/test_kb_document_reindex.py -q
```

结果：`50 passed, 5 warnings in 4.41s`，退出码 0；无 failed/skip。warnings 是既有依赖的 DeprecationWarning，不影响结果。

### 3. Services/boundaries（99 项 + 4 subtests）

```text
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest \
  tests/kb/test_kb_services.py \
  tests/kb/test_kb_application_boundary.py \
  tests/kb/test_kb_document_boundary.py -q
```

结果：`99 passed, 8 warnings, 4 subtests passed in 2.08s`，退出码 0；无 failed/skip。

### 4. Collection 门禁

默认 conftest 下分别执行 `pytest --collect-only -q`：

- 目标集合：`50 tests collected`，退出码 0；
- services/boundaries：`99 tests collected`，退出码 0；
- publication contract：`5 tests collected`，退出码 0。

因此当前环境不需要以 `--noconftest` 绕过依赖；另行按 review 命令使用 `--noconftest` 的 5/50/99 集合也均通过，但未把两套计数相加。

## 真实临时 Qdrant 缩容探针

为验证“实际临时 Qdrant 5→3”而非只依赖 fake client，使用 `QdrantClient(path=<临时目录>)`，集合名 `spec018_shrink`，目录 `/private/tmp/spec018-qdrant-2s7ky50z`：

```text
TEMP_QDRANT_SHRINK_BEFORE= [0, 1, 2, 3, 4]
TEMP_QDRANT_SHRINK_AFTER= [0, 1, 2]
TEMP_QDRANT_UNRELATED= [0]
TEMP_QDRANT_OTHER_VERSION= [0]
```

探针调用实际 `index_module.delete_paper_chunker("doc-1", "v2", client=client, destination_collection="spec018_shrink")`，随后仅在同一临时集合重新 upsert 3 个 v2 点；验证结果证明旧尾点被清除，其他文档和同文档另一 chunker 未被删除。没有使用生产 `QDRANT_PATH`，没有 embedding、网络或模型调用。

## 静态与完整性门禁

| 检查 | 结果 |
|---|---:|
| `python -m py_compile backend/app/knowledge_base/infrastructure/index.py tests/kb/test_kb_index_publication_contract.py` | 退出码 0 |
| `ruff check` 两个目标文件 | `All checks passed!`，退出码 0 |
| `scripts/check_test_naming.py` | 通过，无 spec/task 编号测试名 |
| `scripts/check_test_layout.py` | `test layout: ok` |
| `python -c "import backend.app.knowledge_base.infrastructure.index"` | `IMPORT_OK`，退出码 0 |
| 目标文件冲突标记扫描 | 无命中 |
| 目标 Python 文件 secret/console scoped scan | 无硬编码 token 或 `console.log` 命中 |
| `git diff --check`（tracked 目标生产文件） | 退出码 0 |

## Verification report

```text
Build:    PASS（本 Task 无独立构建产物；py_compile/import smoke 通过）
Types:    N/A（未配置独立类型检查；未扩大到全仓）
Lint:     PASS（Ruff 目标文件）
Tests:    PASS（5/5 contract；50/50 target；99/99 boundary；4 subtests；0 skip）
Security: PASS（目标范围无硬编码 token/console.log；点集/身份/payload fail-closed 契约通过）
Diff:     PASS（目标生产文件 diff-check、冲突标记核对通过）

Overall:  READY for scoped Spec018 backend acceptance
```

本结论不代表 Spec018 已收口。root 仍需执行计划要求的单文档真实 API E2E，记录请求、响应、实体 ID、任务终态、v1/v2 结果及产物路径；不得把本地临时 Qdrant 探针或隔离测试替代真实生产验收。

## 交接日志

- 进展日志：`.codebuddy/agent-logs/spec-018/task-00/backend-tester/20261026-091930.md`
- 本报告：`docs/sdd/plans/018/2026-10-26-reindex-entry-backend-test.md`
