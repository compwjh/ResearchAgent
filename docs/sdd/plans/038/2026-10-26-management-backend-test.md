# Spec 038 管理复接 B01–B03 后端验收报告

> 当前收口状态：B01–B03 定向验收与后端全量已完成；历史 `103/1`、inventory 阻塞等过程证据保留。

## 范围与隔离

- 角色：backend-tester；本轮只验证 `backend/**` 与受影响后端测试，不修改业务代码。
- 候选：修复 backend review 指出的损坏目标 fail-open、global symlink 越界、非法 JSON 422 后的最终候选。
- 工作目录：`/Users/wjh/.codex/worktrees/memory-management-recovery/ResearchAgent`。
- Python：`/Users/wjh/ResearchAgent/.venv/bin/python`。
- 环境：`PYTHONPATH=.`、`PYTHON_DOTENV_DISABLED=1`、`LANGFUSE_ENABLED=false`。
- 隔离：pytest `tmp_path` fixture；独立 smoke 使用临时 `MEMORY_DIR` 与临时 SQLite；未读取或写入真实 `data/memory/`、`USER.md`、`MEMORY.md`，未启动服务、联网、调用模型或生产 POST。

## 最终精确测试集合

命令：

```text
PYTHONPATH=. PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
  tests/memory/test_memory_document_store.py \
  tests/memory/test_memory_markdown_store.py \
  tests/memory/test_memory_block_fixes.py \
  tests/memory/test_memory_compaction.py \
  tests/memory/test_memory_analysis_repair.py \
  tests/conversation/test_conversations_api.py
```

- 退出码：`0`
- 实际结果：`103 passed, 0 failed, 1 warning in 38.57s`
- warning：managed worktree 禁止写 `.pytest_cache`，不影响测试执行或结果。
- 覆盖重点：固定文档 GET/PUT seam、UTF-8 SHA-256 revision/OCC、65,536 code points、项目 owner/active 约束、project/global symlink、pending 显式 ID/幂等、保存失败保留 pending、决策消费精确 ID、`PENDING_UNLINKED` 不假成功、审计状态闭环。

## 独立最终边界 smoke

### 1. 损坏目标文件与待确认保存失败

- 退出码：`0`
- 临时 `MEMORY.md` 写入不可解码 bytes `b"\\xff\\x00preserve"`，随后执行同 ID `resolve_pending(save)`。
- 实际结果：抛出 `MemoryDocumentUnavailableError`；原始 bytes 未变化；PENDING 条目仍存在；未进入成功消费。

### 2. global 固定文件 symlink 越界

- 退出码：`0`
- 临时 `MEMORY.md -> outside.md`，调用 GET 与 PUT。
- 实际结果：两者均返回 HTTP `400`、错误码 `MEMORY_DOCUMENT_PATH_INVALID`；外部目标内容保持不变。

### 3. 非法 JSON body

- 退出码：`0`
- `PUT /api/memory-documents?scope=global`，`Content-Type: application/json`，body 为 `not-json`。
- 实际结果：HTTP `400`，错误码 `INVALID_MEMORY_DOCUMENT_REQUEST`，不再暴露 FastAPI 默认 `422`。

### 4. 完整隔离 HTTP API smoke

- 退出码：`0`
- 实际结果：global/project GET/PUT、空文件不创建、OCC stale revision `409 MEMORY_DOCUMENT_CONFLICT`、当前副本字段、同 owner active 项目、archived `409 PROJECT_NOT_ACTIVE`、foreign/unknown `404 PROJECT_NOT_FOUND`、非法 project selector、Unicode 65,537 上限 `400` 均通过。

## 其他门禁

- 受影响文件 Ruff（`ruff check --no-cache`）：退出码 `0`，`All checks passed!`。
- `scripts/check_test_naming.py`：退出码 `0`，无 spec/task 编号测试文件。
- 无字节码 backend import smoke：退出码 `0`，五个受影响 backend 模块导入成功。
- 包含 `backend/app/memory/repository.py` 的宽 Ruff：退出码 `1`，15 项既有 F401/SIM118/SIM102/F811；这些问题集中在既有 repository.py 重复定义/历史 lint，不是本轮新增功能问题，本轮未修改以清理无关债务。
- 普通 Ruff 首轮另有 managed worktree `.ruff_cache` 写权限退出码 `2`；使用 `--no-cache` 后已取得上述真实 lint 结论。

## 验收结论

**PASS（后端定向验收）**：最终候选 `103/103` 通过，三项复审边界与隔离 HTTP smoke 全部通过，无 P0/P1 功能阻塞。宽 Ruff 的既有 `repository.py` 静态债务继续保留记录，不影响本轮 B01–B03 定向功能验收。

## 可复核日志

- `.codebuddy/agent-logs/spec-038/task-00/backend-tester/20261026-092842.md`

## 最终冻结候选补充复跑

作者补充 pending global symlink 路径回归后，工作树按原六文件精确集合复跑：退出码 `0`，`104 passed, 0 failed, 1 warning in 38.86s`。该 `104/104` 是最终冻结候选的后端定向验收数量，warning 仍仅为 managed worktree 禁止写 `.pytest_cache`。

## 主目录集成复跑记录

在已整合候选的 `/Users/wjh/ResearchAgent` 主目录用相同命令复跑，退出码 `1`，`103 passed, 1 failed`。唯一失败为 `tests/memory/test_memory_block_fixes.py::test_concurrent_resolve_preserves_unrelated_pending`：主目录 race monkeypatch 的 `_append_with_race` 仍只接收 `scope/project_id/content`，而最终生产调用传入 `strict_read=True`，触发夹具 `TypeError`。工作树测试夹具已同步该参数并通过 `104/104`；主目录测试夹具同步前不应宣称集成通过。

## 当前交接结论

- 工作树最终冻结候选：后端定向验收 `PASS`（104/104）。
- 主目录集成候选：测试夹具尚未同步，当前为 `BLOCK`；阻塞点已精确定位到上述单个测试函数，不涉及新增业务断言失败。

## 主目录夹具同步后的最终复跑

主目录已按工作树原样同步 `strict_read` 参数透传夹具，随后仅复跑同一六文件精确集合：

- 命令退出码：`0`
- 实际结果：`104 passed in 37.72s`
- warning：无
- 结果：此前 `103 passed, 1 failed` 的唯一夹具同步阻塞已消除；该集合无其余漏同步测试文件或失败项。

### 最终交接结论

主目录最终冻结候选后端定向验收 **PASS（104/104）**。此前 `103/1` 结果作为历史记录保留，不再代表当前候选状态。

## Spec038 收口：后端全量回归（排除前端）

### 隔离确认

- 主目录 `conftest.py` 的 autouse fixture 将每个用例的 `backend.app.memory.markdown_store.MEMORY_DIR` 指向 `tmp_path/memory`，并隔离 capability SQLite、清理缓存 worker；因此未设置全局 `MEMORY_DIR`，以保留既有配置默认值断言 `config.MEMORY_DIR == BASE_DIR/data/memory`，实际文件记忆写入仍由 fixture 隔离。
- 本次额外将 `MEMORY_DB_PATH`、`KB_DIR`、`QDRANT_PATH`、`LITERATURE_MAP_DB_PATH` 指向 `/private/tmp/spec038-full-A67Sxu/` 下临时路径；`PYTHON_DOTENV_DISABLED=1`、`LANGFUSE_ENABLED=false`、`PYTHONPATH=.`。
- 未访问真实记忆、数据库或 KB 产物，未联网、未调用真实模型、未启动服务。

### 命令与结果

```text
MEMORY_DB_PATH=/private/tmp/spec038-full-A67Sxu/memory.sqlite3 \
KB_DIR=/private/tmp/spec038-full-A67Sxu/kb \
QDRANT_PATH=/private/tmp/spec038-full-A67Sxu/kb/qdrant \
LITERATURE_MAP_DB_PATH=/private/tmp/spec038-full-A67Sxu/literature-maps.sqlite3 \
PYTHONPATH=. PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests --ignore=tests/frontend
```

- 退出码：`1`
- 实际结果：`3120 passed, 3 skipped, 1 failed, 5 warnings, 67 subtests passed in 208.34s`
- 唯一实质失败：`tests/kb/test_kb_upload_closure_matrix.py::test_inventory_hashes_are_stable_and_write_entrypoints_are_registered`
- 失败原因：冻结矩阵要求 `backend/app/api/routes_paper.py` SHA-256 为 `44f3448f...0607508af`，实际为 `1525df74...c837ca99f4333f`。主目录该文件存在既有未提交的 3 行变更（`_paper_snapshot_for_item` 增加 durable snapshot 分支）；tester 未修改该文件，失败与 Spec038 记忆管理无关。
- skips：`3` 个，均为测试自身条件跳过；未执行 `tests/frontend`。
- warnings：5 个底层依赖/SwigPy 类型弃用 warning 及末尾 Python warning，不是失败原因。

### 全量回归结论

后端 Spec038 定向验收仍为 `104/104 PASS`；Spec 收口全量门禁当前因上述知识库冻结哈希与既有 `routes_paper.py` 工作树变更不一致而为 `BLOCK`。应由对应知识库变更负责人处理矩阵/基线一致性后，再重跑全量回归；本 tester 不代改无关业务或矩阵。

## Spec038 收口全量最终复跑

知识库 inventory 门禁完成最小修复并经独立 review GO 后，使用上一轮完全相同的主目录、隔离路径、环境变量与命令再次执行：

- 命令退出码：`0`
- 实际结果：`3121 passed, 3 skipped, 5 warnings, 67 subtests passed in 286.81s (0:04:46)`
- 失败：`0`
- skips：`3`。其中 2 个来自 `tests/e2e/test_research_lifecycle_e2e.py`，需显式 `RUN_E2E=1`、浏览器和已启动服务；1 个来自 `tests/research/test_ollama_direct.py` 的真实 Ollama 流测试，因 Ollama 不可达或无可用模型而按测试门控跳过。
- warnings：5 个底层依赖/SwigPy 类型弃用 warning，不影响通过结果。
- 与首轮差异：首轮 `3120 passed, 3 skipped, 1 failed` 的 `routes_paper.py` inventory SHA-256 阻塞已消除；本次无失败。

### 最终全量交接结论

Spec038 后端定向验收 `104/104 PASS`，排除前端的后端全量回归 `3121/3121 PASS`（3 个有明确环境门控的 skip），最终收口门禁 **PASS**。首轮 `3120/1` 失败历史保留在上方，不再代表当前候选状态。
