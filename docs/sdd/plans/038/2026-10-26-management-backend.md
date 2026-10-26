# Spec 038 管理复接补充：后端实施报告

## 范围与状态

- **范围**：B01 Store seam → B02 audit/worker seam → B03 fixed document API/decision seam。
- **实现状态**：B01–B03 后端窄范围已完成；reviewer/tester GO/PASS，跨端验收已由 038 acceptance report 签收。
- **工作树**：隔离 worktree `codex/fix-file-memory-management`；未部署、未启动服务、未访问真实 `data/memory/`。
- **真实写入边界**：所有测试和 smoke 均使用临时 `MEMORY_DIR` 与临时 SQLite；未读写真实 `USER.md`、`MEMORY.md`、`PENDING.md`。

## 实施摘要

### B01 Store seam

- `MarkdownMemoryStore` 增加固定 `MEMORY.md` / `projects/<id>.md` strict read/write seam。
- revision 为 UTF-8 bytes 的 SHA-256；PUT 上限为 65,536 Unicode code points；读缺失文件返回空文档且不创建文件。
- 同路径 `RLock` 按 canonical absolute path 复用；项目白名单、realpath/commonpath 与 symlink 越界均拒绝。
- `add_pending(..., item_id=...)` 支持稳定 ID、同内容/项目幂等、冲突拒绝。
- `resolve_pending` 改为 append-first；append 失败保留 PENDING；正式 append 对规范化正文幂等；ignore 只消费 PENDING。

### B02 audit/worker seam

- 分析 worker 先预留 `memory_analysis_items.item_id`，再执行 MD 动作；pending 使用同一稳定 ID。
- 正式写入成功后才投影 `auto_saved`；PENDING 写入失败投影 `failed`；失败重试复用原 ID，并在成功后恢复 `pending_confirmation`。
- `update_memory_analysis_item` 允许 worker 对失败项进行稳定重试投影；没有新增 SQL 列或旧 SQLite CRUD。

### B03 API/decision seam

- 新增 `GET/PUT /api/memory-documents`，仅接受 `global|project` 固定 scope；服务端校验 owner、active project、revision、body extra fields、内容上限与稳定错误码。
- GET/PUT 不返回绝对路径；OCC stale revision 返回 409 并保留服务端副本字段；文件/解码/原子写失败返回 503。
- 分析保存/忽略必须调用精确 `resolve_pending(item_id, ...)`；缺失关联返回 `PENDING_UNLINKED`，已消费返回 `PENDING_ALREADY_CONSUMED`，文件动作成功后才更新审计状态。

## 可复核验证记录

所有命令均使用 `/Users/wjh/ResearchAgent/.venv/bin/python`、`PYTHONPATH` 指向本 worktree、`PYTHON_DOTENV_DISABLED=1`、`LANGFUSE_ENABLED=false`。

| 验证 | 退出码 | 实际结果 |
|---|---:|---|
| `python -m pytest -q tests/memory/test_memory_document_store.py` | 0 | 10 passed |
| `python -m pytest -q tests/memory/test_memory_document_store.py tests/memory/test_memory_markdown_store.py tests/memory/test_memory_block_fixes.py` | 0 | 56 passed |
| `python -m pytest -q tests/memory/test_memory_compaction.py tests/memory/test_memory_analysis_repair.py tests/memory/test_memory_block_fixes.py tests/conversation/test_conversations_api.py` | 0 | 58 passed |
| `scripts/check_test_naming.py` | 0 | no spec/task numbers under tests |
| targeted Ruff: `markdown_store.py`, `test_memory_document_store.py` | 0 | All checks passed |
| targeted Ruff: `conversation_service.py` | 0 | All checks passed |
| targeted Ruff: `schemas.py`, `routes_conversations.py` | 0 | All checks passed |
| `python -B -c 'import ...'` backend import smoke | 0 | all five changed backend modules imported successfully |
| isolated document API smoke | 0 | global/project GET/PUT, missing/archived/foreign project, OCC, invalid body/revision/path, 65,537 chars all passed |
| isolated pending decision API smoke | 0 | stable item ID, save→project MD→audit, duplicate consume 409, unlinked item 409 passed |

### Previous legacy-test mismatch (resolved below)

The previous combined affected suite reported **97 passed, 1 failed**: the existing
`test_analysis_decision_api_supports_single_and_batch` manually creates an audit item
without a matching PENDING entry and still expects 200 `auto_saved`. The frozen
Spec 038 contract explicitly requires `PENDING_UNLINKED` 409 for this case, so the
implementation keeps the contract rather than restoring text-guessing or audit-only
success. The acceptance test was updated below to seed a matching PENDING item and
assert the explicit `PENDING_UNLINKED` failure for the orphan case.

## Readback / hygiene

- `git diff --check` passed after B01–B03 edits.
- All modified production files were read back at the changed seams before testing.
- A direct `compileall` attempt exited 1 only because the managed worktree denies writes to existing `__pycache__`; the no-bytecode backend import smoke exited 0.
- The worktree contains no generated files under `data/memory/`.
- Full repository Ruff remains blocked by pre-existing `repository.py` findings (unused import, duplicate processing-step definitions, and unrelated SIM rules); no unrelated cleanup was included in this task.

## 本轮测试合同修复（2026-10-26）

上一轮唯一失败来自过时的 `test_analysis_decision_api_supports_single_and_batch`：它手工创建了没有同 ID `PENDING.md` 的审计项，却断言 audit-only save 成功。本轮仅修改该测试，未改变合同或生产范围：

- 为正常 save/ignore 路径显式写入匹配 `item_id` 的临时 `PENDING.md` 条目，并验证 save 后项目 Markdown 有正文、ignore 后 pending 被消费。
- 新增旧 audit-only 项断言：返回 409 `PENDING_UNLINKED`，审计状态仍为 `pending_confirmation`。
- 测试使用显式 `tmp_path / "memory"`，不构造默认生产记忆目录。

复跑同一受影响集合：

```text
python -m pytest -q \
  tests/memory/test_memory_document_store.py \
  tests/memory/test_memory_markdown_store.py \
  tests/memory/test_memory_block_fixes.py \
  tests/memory/test_memory_compaction.py \
  tests/memory/test_memory_analysis_repair.py \
  tests/conversation/test_conversations_api.py
退出码：0；98 passed；0 failed；41.51s
```

本轮附加门禁：目标测试 Ruff 退出码 0；`scripts/check_test_naming.py` 退出码 0；`git diff --check` 退出码 0。

## 独立后端复审修复（2026-10-26）

按 `2026-10-26-management-backend-review.md` 仅修复三项冻结范围内缺陷，并先补回归再改实现：

- `resolve_pending(save)` 通过 strict UTF-8/IO 读取目标文件；损坏或读取失败时返回不可用错误，正式旧文件与同 ID PENDING 均保留，API 审计项保持 `pending_confirmation`，不报告成功。
- 全局固定 `MEMORY.md` 同样执行 symlink/realpath 边界校验；越界 symlink 的 GET/PUT 均为 `MEMORY_DOCUMENT_PATH_INVALID` 400，外部目标不被触碰。
- `PUT /api/memory-documents` 改为在路由边界手动解析 JSON；非法 JSON 统一返回 `INVALID_MEMORY_DOCUMENT_REQUEST` 400，不再落到默认 422。

复审新增回归先以红灯确认缺陷（退出码 1，4 failed），修复后复跑：

```text
python -m pytest -q \
  tests/memory/test_memory_document_store.py \
  tests/memory/test_memory_markdown_store.py \
  tests/memory/test_memory_block_fixes.py \
  tests/memory/test_memory_analysis_repair.py \
  tests/conversation/test_conversations_api.py
退出码：0；89 passed；0 failed；39.24s
```

包含记忆压缩回归的最终受影响集合：

```text
python -m pytest -q \
  tests/memory/test_memory_document_store.py \
  tests/memory/test_memory_markdown_store.py \
  tests/memory/test_memory_block_fixes.py \
  tests/memory/test_memory_compaction.py \
  tests/memory/test_memory_analysis_repair.py \
  tests/conversation/test_conversations_api.py
退出码：0；104 passed；0 failed；39.80s
```

复审附加门禁：`RUFF_CACHE_DIR=/tmp/spec038-ruff-cache python -m ruff check` 目标文件退出码 0；`scripts/check_test_naming.py` 退出码 0；`git diff --check` 退出码 0；目标集合 `pytest --collect-only -q` 退出码 0，最终集合新增回归后为 89 tests collected；后端 no-bytecode import smoke 退出码 0。pytest 仅报告受管工作树无法写 `.pytest_cache` 的 warning，不影响测试退出码。

全部复审测试仍仅使用 `tmp_path`/临时 `MEMORY_DIR`/临时 SQLite；未读写真实 `USER.md`、`MEMORY.md`、`PENDING.md`，未部署或执行 Git 操作。

## 窄范围收口

B01–B03 已由后端 reviewer `GO`、backend-tester 定向 `104/104 PASS` 与全量后端 `3121 passed, 0 failed, 3 skipped` 支持；本报告的后端实施范围完成。真实运行时、前端与跨端签字见 [`2026-10-26-management-runtime.md`](./2026-10-26-management-runtime.md) 和 [`../../reviews/038-acceptance-review.md`](../../reviews/038-acceptance-review.md)。
