# Task03 交付：API 模块清单与端点归属

> 关联：[Spec017](../../specs/017-backend-bounded-context-modularization.md) ｜ [Task03](./task-03-api-platform.md)
> 满足必改项 4 要求的「每个子路由模块清单、端点归属、路由前缀保持方式、请求/响应 schema 的最终位置」与「应用生命周期 hook 的注册方式」。
> 迁移清单 §待裁决 曾记录「需 03 出子路由清单（spec 必改项 4 已要求，但未落表）」，本文件补齐该表。

## 生成与校验方式（可复现，勿手写维护）

枚举各子路由模块自身的 `router.routes`，并与运行时 `app.openapi()` 交叉核对：

```python
import sys, backend.app.api.routes   # 必须先导入 routes，否则 routes_paper 循环导入
mods = ["routes_system","routes_chat","routes_kb","routes_paper","routes_article"]
for m in mods:
    mod = sys.modules[f"backend.app.api.{m}"]
    for r in mod.router.routes: ...   # 取 path / methods / endpoint.__name__
```

核对结果：**子模块枚举 35 个 `/api` 操作**，`app.openapi()` 共 36 个操作，差值仅为 `main.py` 的 `GET /`（前端首页，非 `/api`）。两者 `/api` 部分**完全一致，无差异**。

> 注：FastAPI 0.141 用 `_IncludedRouter` 做延迟装配，`app.routes` 顶层只有 7 条且不展平子路由，因此**不能**靠遍历 `app.routes` 枚举端点，必须按上述方式逐模块取。

## 总览

| 子路由模块 | 归属上下文 | 操作数 |
|---|---|---|
| `backend/app/api/routes_system.py` | platform / 系统 | 1 |
| `backend/app/api/routes_chat.py` | article | 1 |
| `backend/app/api/routes_kb.py` | knowledge_base | 6 |
| `backend/app/api/routes_paper.py` | paper_discovery | 17 |
| `backend/app/api/routes_article.py` | article | 10 |
| **合计** | | **35** |

## 路由前缀保持方式

- `backend/app/api/routes.py` 现只保留 `router = APIRouter(prefix="/api")` 与 5 个 `include_router`，**0 个路由装饰器**（37 行），仅作总注册入口。
- 各子模块声明 `router = APIRouter()`（**自带无前缀**），最终路径 = `/api` + 子模块内声明路径。
- `backend/app/main.py` 只负责装配：`include_router(router)`、挂载 `/assets`、注册 `RequestValidationError` handler 与 `lifespan`，不含业务路由。

## 端点归属

### `backend/app/api/routes_system.py` — 1 个操作

| 方法 | 路径 | 处理函数 |
|---|---|---|
| `GET` | `/api/health` | `health` |

### `backend/app/api/routes_chat.py` — 1 个操作

| 方法 | 路径 | 处理函数 |
|---|---|---|
| `POST` | `/api/chat` | `chat` |

### `backend/app/api/routes_kb.py` — 6 个操作

| 方法 | 路径 | 处理函数 |
|---|---|---|
| `POST` | `/api/kb/ask` | `kb_ask` |
| `GET` | `/api/kb/health` | `kb_health` |
| `GET` | `/api/kb/papers` | `list_kb_papers` |
| `DELETE` | `/api/kb/papers/{paper_id}` | `delete_kb_paper` |
| `POST` | `/api/kb/papers/{paper_id}/reindex` | `reindex_kb_paper` |
| `POST` | `/api/kb/upload` | `upload_kb_paper` |

### `backend/app/api/routes_paper.py` — 17 个操作

| 方法 | 路径 | 处理函数 |
|---|---|---|
| `GET` | `/api/papers/browser-health` | `paper_browser_health` |
| `GET` | `/api/papers/browser/health` | `paper_browser_health` |
| `GET` | `/api/papers/conferences` | `list_paper_conferences` |
| `GET` | `/api/papers/conferences/search` | `search_paper_conferences` |
| `DELETE` | `/api/papers/conferences/{conference_id}` | `delete_paper_conference` |
| `PATCH` | `/api/papers/conferences/{conference_id}` | `update_paper_conference` |
| `GET` | `/api/papers/conferences/{conference_id}/accepted` | `list_accepted_papers` |
| `POST` | `/api/papers/import-batches` | `create_paper_import_batch` |
| `GET` | `/api/papers/import-batches/{batch_id}` | `get_paper_import_batch` |
| `POST` | `/api/papers/import-batches/{batch_id}/cancel` | `cancel_paper_import_batch` |
| `POST` | `/api/papers/import-batches/{batch_id}/retry` | `retry_paper_import_batch` |
| `POST` | `/api/papers/import-items/{item_id}/login` | `login_paper_import_item` |
| `POST` | `/api/papers/import-items/{item_id}/resume` | `resume_paper_import_item` |
| `POST` | `/api/papers/imports` | `import_paper` |
| `GET` | `/api/papers/imports/{batch_id}` | `get_paper_import_batch` |
| `POST` | `/api/papers/imports/{batch_id}/retry` | `retry_paper_import_batch` |
| `POST` | `/api/papers/search` | `search_papers` |

> `/api/papers/imports*` 是 spec-017 明确保留的**别名**（与 `/api/papers/import-batches*` 指向同一处理函数），因此 `/api/papers/browser/health` 与 `/api/papers/browser-health` 一样会产生重复 `operationId` 告警——**该告警在 Task02 冻结的 OpenAPI 基线中已存在**，非拆分引入。

### `backend/app/api/routes_article.py` — 10 个操作

| 方法 | 路径 | 处理函数 |
|---|---|---|
| `POST` | `/api/agent/articles/download` | `download_article_endpoint` |
| `POST` | `/api/agent/articles/plan-download` | `plan_article_download` |
| `POST` | `/api/agent/articles/probe` | `probe_article_endpoint` |
| `POST` | `/api/agent/articles/search` | `search_articles_endpoint` |
| `POST` | `/api/agent/run` | `run_agent` |
| `GET` | `/api/agent/settings` | `get_agent_settings` |
| `PUT` | `/api/agent/settings` | `update_agent_settings` |
| `GET` | `/api/agent/skills/download-paper` | `get_download_paper_skill` |
| `GET` | `/api/agent/tasks/{task_id}` | `get_agent_task` |
| `POST` | `/api/agent/tasks/{task_id}/human-actions/login-completed` | `login_completed` |

## 请求 / 响应 schema 的最终位置

- **统一保留在 `backend/app/api/schemas.py`**，未随路由拆分移动。
- 校验错误体由 `backend/app/api/common.py` 的 `paper_request_validation_error_response` 统一产出，经 `main.py` 的 `RequestValidationError` handler 接入，用于保持论文检索接口的错误体契约、同时不改变其他接口行为。
- 跨域契约另见 `backend/app/platform/ports.py`（`PaperImportRequest` / `PaperImportResult` 等 DTO）。

## 应用生命周期 hook 的注册方式

- 注册点：`backend/app/main.py` 的 `lifespan` 异步上下文管理器，通过 `FastAPI(title="Research Agent", lifespan=lifespan)` 接入。
- 启动阶段做两件收尾工作（spec-012），**任一失败只记录、不阻塞服务启动**：
  1. `mark_interrupted_on_startup()` —— 把上次运行残留为 `indexing` 的切分版本标记为 `failed`（异步任务无法跨进程存活）；
  2. `backfill_chunker_defaults()` —— 为 spec-011 遗留索引点补齐 `chunker` 等字段。

## composition root 与依赖解析

- `backend/app/platform/bootstrap.py`：`ProviderRegistry`（register / get / clear_cache / override / reset_overrides），`override` 支持嵌套与异常安全恢复，是测试替换点。
- `backend/app/platform/ports.py`：「论文导入 → 知识库」跨域 port（Protocol + 只读 DTO），**只定义不实现**，实现留给 Task05、由 Task04 消费。
- `backend/app/api/common.py`：`article_tasks()` 与 `_paper_store()` / `_paper_search_service()` / `_paper_batch_service()` / `_paper_browser_manager()` 均委托 `get_provider(...)`；4 个 `_build_*` 构造器以 `singleton=False` 注册（保留其内部缓存与 db 路径变化重建语义）。
- 路由模块**不再持有** `TaskStore` / `PaperDiscoveryStore` / `PaperImportBatchStore` / `PaperBrowserManager` 模块级单例。

## 验收证据

| 验收项 | 证据 |
|---|---|
| 不再存在单一业务聚合 `routes.py` | `routes.py` 37 行、0 个路由装饰器 |
| 路由 / OpenAPI 基线无差异 | 与 `openapi-baseline.json` 比对：35 个 `/api` 操作，0 缺失 / 0 新增 / 0 operationId 变化 / 0 schema 差异 |
| 健康与应用启动测试通过 | 全量 `628 passed` |
| 设置拆分 | `platform/settings/`（`article_assistant_settings.py`、`paper_discovery_settings.py`、`settings_repository.py`），原子读写 |
| 装配：无模块级单例、可测试替换 | 架构测试 `tests/test_api_module_boundaries.py`（2 条 AST 断言） |
| port 落盘 | `platform/ports.py`，无任何业务模块实现 |
