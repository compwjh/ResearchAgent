> 关联：[spec-037](../../specs/037-startup-readiness-gap-and-ux-bugs.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`

# 任务 06：v2 重建失败态——中文文案 + 启动自愈

## 一句话目标
让 v2 重建的失败态对用户可读、可自愈：失败卡片显示中文文案与重试入口，服务启动时对失败任务重排队一次。

## 背景与前置条件
- spec-037 Bug 3。
- **已核实（2026-09-16 实测）**：手动重试 3 篇文档全部成功（2 indexed、1 indexing、failed 归零），说明当前环境**可重建**；历史 failed 是环境故障期（Qdrant 本地锁冲突 / 代际门禁未 finalize）留下的陈旧状态。
- 原始错误：`索引任务异常终止：INDEX_FINALIZE_REQUIRED`（相关文案见 `backend/app/api/routes_kb.py:411-413`）。
- 端点：`POST /api/kb/documents/{document_id}/reindex`（`routes_kb.py:887`），202 queued 契约不变。

## 实施步骤
**前端（KB 列表渲染处）**
1. 失败态展示中文可读文案（如「索引代际尚未完成提交，请重试重建」），**不直接展示 `INDEX_FINALIZE_REQUIRED` 原文**。
2. 提供显式「重试」入口，点击走既有 reindex 端点。

**后端（`backend/app/api/routes_kb.py` / 启动恢复处，参考 `backend/app/main.py` 既有启动恢复范式）**
3. 服务启动时把 `status=failed` 的 chunker 任务自动重新排队，**每文档每 chunker 限 1 次**（用幂等标记，防重启风暴）。
4. 重试失败仍保留 failed 态，不再自动重试。

## 边界与明确不做
- **根因是环境故障遗留状态，不是切分/索引逻辑 bug**——不得重构 parser、chunker 或 `rebuild_index` 工具，必须在实现注释中写明这一点。
- 不重试成功态任务，不做无限重试，不引入队列框架/新调度依赖。
- 不改 reindex 端点路径与 202 契约。

## 验收
- 失败卡片显示中文文案，页面不出现 `INDEX_FINALIZE_REQUIRED` 原文。
- 点「重试」可重新触发重建。
- 重启服务后，failed 任务被重排队一次且仅一次（用日志/计数可验证）。
- 既有 KB 相关测试全绿。

## 产出物、执行结果与变更日志（backend-dev）

### 改动文件
- `backend/app/knowledge_base/infrastructure/store.py`
  - 新增常量 `AUTO_REQUEUED_CHUNKERS`（幂等标记顶层键，含「为何不用 chunker 状态内部字段」注释）。
  - 新增 `iter_failed_chunkers(meta_path)`：列出所有 `schema_version=knowledge-document-v1` 且状态为 `failed` 的 `(document_id, chunker)`（用宽松 `load_papers`，损坏/缺失返回空，不抛）。
  - 新增 `mark_chunker_auto_requeued(paper_id, chunker, meta_path)`：在文档顶层 `auto_requeued_chunkers` 字典写入 `{chunker: UTC 时间戳}`。
  - 新增 `is_chunker_auto_requeued(paper_id, chunker, meta_path)`。
- `backend/app/knowledge_base/application.py`
  - 新增 `recover_failed_reindexes(*, meta_path, papers_dir, client, destination_collection) -> int`：启动自愈，遍历失败 chunker，复用既有 `submit_document_reindex` 排队；每 `(document, chunker)` 仅一次（幂等标记）；单篇排队失败或整体异常只记日志、不抛出。
  - 从 store 导入 `is_chunker_auto_requeued / iter_failed_chunkers / mark_chunker_auto_requeued`。
- `backend/app/main.py`
  - 导入 `recover_failed_reindexes`，在 lifespan 启动流程中加入 try/except 调用（沿用既有范式，失败只 `print` 不阻塞启动）。
- `tests/test_kb_startup_reindex_recovery.py`（新增）：8 个用例。
- `tests/test_kb_upload_closure_matrix.py`：把 `recover_failed_reindexes` 加入闭包矩阵 `allowed` 集合。
- `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json`：随合法新增函数重算 `application.py` / `store.py` / `main.py` 的 sha256 与 `inventory_digest`（冻结清单更新）。

### 自愈逻辑幂等依据
- 幂等标记：`papers.json` 文档**顶层**字段 `auto_requeued_chunkers: { "<chunker>": "<UTC 时间戳>" }`，落盘持久化、跨进程重启保留。
- 为何用顶层而非 chunker 状态内部字段：既有 `ensure_chunkers()` 会把 chunker 状态归一化为固定 4 字段（status/chunk_count/progress/error），内部字段会在读取/写入时被抹掉；顶层字段不被该函数触碰，可稳定留存。
- 流程：启动遍历 `failed` chunker → `is_chunker_auto_requeued` 为真则跳过（防重启风暴/无限重试）→ 否则 `submit_document_reindex` 排队（复用既有能力，不另写一套）→ 成功则 `mark_chunker_auto_requeued`。重试后仍 `failed` 也因标记已存在而不再自动重排。

### 测试命令与结果
- `python -m pytest tests/test_kb_startup_reindex_recovery.py -q` → **8 passed**（含启动接线：lifespan 触发自愈一次且不因异常阻塞）。
- 定向回归（KB/reindex/启动相关，含闭包矩阵）：
  `python -m pytest tests/test_kb_upload_closure_matrix.py tests/test_kb_startup_reindex_recovery.py tests/test_kb_document_reindex.py tests/test_kb_tasks.py tests/test_kb_services.py tests/test_kb_document_routes.py tests/test_kb_routes.py tests/test_kb_startup_generation_gate.py tests/test_kb_application_boundary.py tests/test_kb_document_boundary.py -q` → **199 passed**。
- 收集校验：`python -m pytest tests/ --co -q --ignore=tests/test_online_model_dispatch.py` → **2402 collected**，无新增收集错误（`test_online_model_dispatch` 缺 `langchain_openai` 为环境既有问题，与本次无关）。
- 静态检查：`ruff check` 上述 5 个文件 → **All checks passed!**

### 复用的既有符号（禁止重复实现）
- `submit_document_reindex`：既有 reindex 排队能力（端点 `POST /api/kb/documents/{id}/reindex` 也走它；202 queued 契约未改）。
- `main.py` 既有启动恢复 try/except 范式（`recover_paper_catalog_searches` / `recover_research_tasks`）。
- store 新增函数仅做失败扫描与顶层标记读写，**未重构** `parser` / `chunker` / `rebuild_index.py`。

### 边界遵守（自检）
- 仅改 `backend/**` 与 `tests/`，未碰 `frontend/**`；未重构 parser/chunker/rebuild_index；未引入队列框架/新调度依赖；未改 reindex 端点路径与 202 契约；不重试成功/进行中任务；无无限重试。
- 关键注释已写明根因是**环境故障遗留状态**（Qdrant 本地锁冲突 / 代际门禁未 finalize），非切分/索引逻辑 bug。
