> 关联：[spec-021 论文导入异步化与进度反馈](../../specs/021-paper-import-async-progress.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`进行中`

# Task03 后端：`KB_STORAGE_LOCKED` 语义、单条目重试路由与唯一索引冲突可读化

## 状态与一句话目标

`进行中`。①把"知识库存储被另一个实例独占"从无差别的 `KB_IMPORT_FAILED` 中区分出来，给出可行动错误；②新增单条目重试 API，复用既有 `service.retry_item`；③把"重复导入撞唯一索引"从 `IMPORT_BATCH_ERROR` 兜底改为可读、可行动的错误码。

## 背景与前置条件

- 实证：`data/kb/qdrant` 被另一个实例占用时，KB 写入/索引/查重全部失败并压成 `KB_IMPORT_FAILED`（`backend/app/knowledge_base/application.py:302-307,385`；`backend/app/paper_discovery/application/paper_import.py:47-56` 的错误码表）。
- 本机验证：另开 Qdrant 本地客户端直接抛 `RuntimeError: Storage folder data/kb/qdrant is already accessed by another instance of Qdrant client`；服务启动日志亦告警（`deploy/run-8123.log:5`）。
- 单条目重试能力已存在但无路由：`service.retry_item`（`paper_import_batch_service.py:441-446`）→ `store.retry_item`（`paper_import_batch_store.py:581`，仅 `failed → queued`）。
- 依赖任务 02：`retry_item` 也必须是"入队即返回"，不得在请求内等待。

## 数据、配置与接口

- **新增错误码** `KB_STORAGE_LOCKED`（可重试），文案："知识库存储被另一个实例占用，请关闭其他服务实例后重试"。
- 该码需同时进入：
  - `backend/app/paper_discovery/application/paper_import.py` 的 `_SAFE_IMPORT_ERROR_MESSAGES`（只能用固定文案，禁止把异常文本写进持久化状态或响应）；
  - 前端 `frontend/app.js` 的 `PAPER_ERROR_TEXT`（由 Task04 落地，需在本任务给出码名与文案）。
- **新增端点** `POST /api/papers/import-items/{item_id}/retry`：
  - 成功：200 + 所属批次负载，该 item 回到 `queued` 并提交后台执行；
  - 失败：404 `ITEM_NOT_FOUND`；400 `INVALID_STATE_TRANSITION`（仅 `failed` 可重试）；424 `IMPORT_BATCH_ERROR`。
- 其余 KB 失败仍为 `KB_IMPORT_FAILED` / `KB_INDEX_FAILED`，不得一刀切替换。

## 实施步骤与文件边界

**文件边界**：只改 `backend/**`（`paper_import.py`、`routes_paper.py`、`paper_import_batch_service.py`、`knowledge_base/application.py` 或其错误映射处）与后端测试。不得改 `frontend/**`。

1. **先写测试**（TDD）：
   - 存储占用场景→返回 `KB_STORAGE_LOCKED` 而非 `KB_IMPORT_FAILED`（用可控的假 indexer/假 client 触发 `RuntimeError`，不依赖真实多实例）；
   - 单条目重试：仅重跑目标 item，其他条目状态不变；非 `failed` 条目返回 400。
2. 错误归因：在 KB 导入/索引失败处识别"存储被占用"（异常类型为 `RuntimeError` 且消息含 `already accessed by another instance`），映射为 `KB_STORAGE_LOCKED`；**不得**用异常文本做响应或落库内容。
3. 新增路由 `retry_paper_import_item`，入队后调用既有的后台提交（与 Task02 的 `submit_batch` 语义一致），立即返回。
4. **唯一索引冲突可读化**：对 `sqlite3.IntegrityError`（`UNIQUE constraint failed: index 'import_item_title'`）映射专用错误码（建议 `DUPLICATE_IMPORT`，文案"该论文已在导入批次中，请在原批次重试"；若论文已入库则走 `PAPER_ALREADY_EXISTS` 语义），**禁止**再被 `except Exception` 兜底成 424 `IMPORT_BATCH_ERROR`。实测触发点：`routes_paper.py:707` → `store.py:364`。
5. 补充 API 注释与 docstring；保持 `/api/papers/import-batches/*` 别名路径不受影响。

> **不做**：不改 `import_item_title` 唯一索引本身，也不改失败/取消条目是否释放唯一性的语义（spec-021「明确不做」已圈定，另行评审）。

## 子代理分派

- 角色：`backend-dev`（`hy3`，32k）。
- 最小上下文：本文件 + spec-021 §端点/接口 第 5 行与 §边界 第 9 条 + `paper_import.py:33-67` + `routes_paper.py:755-796,849` + `paper_import_batch_service.py:434-446`。
- 单次范围：≤2 个代码文件、≤150 行。
- 回传：测试结果先行，日志路径必给。

## 边界与明确不做

- 不修改 qdrant 部署形态；不做自动关闭其他实例的动作。
- 不新增/改名既有错误码；不改 `_import_single_paper` 契约。
- 不在错误消息中回显路径/URL/凭据等异常原文（沿用 `safe_import_error_message` 的白名单策略）。
- 不做自动重试与退避次数策略。

## 验收、风险与回滚

**验收**：
1. `cd backend && python -m pytest -q` 全绿。
2. `ruff check .` 无新增告警。
3. 注入假 indexer 触发存储占用 → API/批次 item 的 `error_code` 为 `KB_STORAGE_LOCKED`。
4. `POST /api/papers/import-items/{failed_item_id}/retry` 返回 200，目标 item 回到 `queued` 并最终重跑；`completed` 条目不被重跑。
5. 非 `failed` 条目重试返回 400 `INVALID_STATE_TRANSITION`。

**风险**：把存储占用误判为其它 KB 失败会导致错误码失真 → 归因条件必须窄匹配，且失败时回落到原 `KB_IMPORT_FAILED`。

**回滚**：回退本次 commit，错误码表恢复原状，无数据迁移。

## 产出物、执行结果与变更日志

待执行后填写（真实命令、真实输出、改动文件与行数、日志路径）。
