# Spec017 Task02：OpenAPI 契约基线（openapi-baseline）

> 生成：backend-dev ｜ 数据来源：`openapi-baseline.json`（已冻结快照，由 `.venv/bin/python` 统计，**禁止手数**）。
> 本文件只记录基线，不改代码、不改 spec。

## 1. 版本与冻结说明

| 项目 | 值 |
|---|---|
| FastAPI | 0.141.1 |
| Pydantic | 2.13.5 |
| openapi 版本字段 | 保留 `3.1.0`（顶层 `openapi` 字段） |
| 冻结时剔除的不稳定字段 | `servers`（server url）、以及含时间戳的 `description` |
| 剔除原因 | server url 随运行环境变化、description 含生成时间戳均非契约内容；剔除后快照可跨环境稳定比较 |

> 说明：本快照顶层仍含 `openapi: 3.1.0`。spec「基线来源与比较方式」要求剔除「`openapi` 版本号」—— 现快照保留该字段。**此为与 spec 文字的差异**，记录在此交架构师裁决是否需要在 Task07 比较时一并忽略该字段（见 `reviews/017-task02-inventory.md` 风险项）。

## 2. 端点总数（path × method，实测）

| 统计 | 值 |
|---|---:|
| distinct path 项 | 34 |
| 操作（path×method）总数 | **36** |
| 与 spec 端点表（35 操作）差异 | 快照多 1 个根路径 `GET /`（`Index`，返回 `{}`），非业务端点，spec 表未列 |

## 3. 公开别名（4 组，迁移后必须全部保留）

| # | 主路径 | 别名 | 方法 |
|---|---|---|---|
| 1 | `/papers/import-batches` | `/papers/imports` | POST |
| 2 | `/papers/import-batches/{batch_id}` | `/papers/imports/{batch_id}` | GET |
| 3 | `/papers/import-batches/{batch_id}/retry` | `/papers/imports/{batch_id}/retry` | POST |
| 4 | `/papers/browser/health` | `/papers/browser-health` | GET |

> 实测：4 组别名均在 `openapi-baseline.json` 的 34 个 path 中同时出现，迁移后须全部保留（即使前端不调用）。
> 注：任务描述「retry 两组」在快照中对应第 3 组的一对（`imports/{batch_id}/retry` ↔ `import-batches/{batch_id}/retry`）；快照中 retry 别名仅 1 对。

## 4. SSE 端点（3 个）

| 路径 | 方法 | OpenAPI 声明 media type | 真实运行 media type |
|---|---|---|---|
| `/api/agent/run` | POST | `application/json` | `text/event-stream`（+ `Cache-Control: no-cache`、`X-Accel-Buffering: no`） |
| `/api/chat` | POST | `application/json` | `text/event-stream`（同上） |
| `/api/kb/ask` | POST | `application/json` | `text/event-stream`（同上） |

> 重要：FastAPI 对 `StreamingResponse` 的 OpenAPI 声明为 `application/json`，**无法从 OpenAPI 快照区分 SSE**。SSE 的 `text/event-stream` 与响应头须由 Task07 的**运行时/响应断言**覆盖，不能仅靠 OpenAPI diff（见风险 Top3）。

## 5. 两类错误体（迁移禁止相互统一）

| 适用范围 | 错误体结构 | 产生方式 |
|---|---|---|
| `/papers/*` | `{code, message, retryable}` | `_paper_api_error()` 自定义响应 |
| `/agent/*`、`/chat`、`/kb/*` | `{"detail": ...}`（部分 `detail` 为对象，如 `/agent/articles/download` 404 → `{download_outcome, user_message, article_url}`） | FastAPI `HTTPException` |
| `/health` | **恒 200**，Ollama 不可达降级 `models: []`，不产生错误体 | 特例 |

> 关键：`openapi-baseline.json` 的 `components.schemas` 中 **不含**含 `retryable`/`code` 的自定义错误 schema，也**无 SSE 的 `text/event-stream`**。即：这两类对外契约**未体现在 OpenAPI 快照内**，仅能由 spec 基线 + 运行时断言保证。Task07 必须额外为「错误体结构」与「SSE media type/响应头」写运行时断言（不能只比 OpenAPI diff）。
> spec 错误码（须保持）：`CONFERENCE_DISABLED`(400)、`CONFERENCE_NOT_CONFIGURED`(400)、`CONFERENCE_NOT_FOUND`(404)、`BUILT_IN_CONFERENCE_PROTECTED`(409)、`PAPER_DISCOVERY_DISABLED`(503)、`PAPER_DISCOVERY_STORE_UNAVAILABLE`(503)、`ACCEPTED_ROUTE_NOT_CONFIGURED`(400)、`ACCEPTED_SEARCH_UNSUPPORTED`(424)、`USENIX_UNAVAILABLE`(424)、`INVALID_YEARS`(422)、`INVALID_ACCEPTED_YEAR`(422)、`INVALID_ACCEPTED_CYCLE`(422)、`INVALID_QUERY`(422)、`BROWSER_UNAVAILABLE`(503)、`BROWSER_SESSION_REQUIRED`(424)、`KB_IMPORT_FAILED`。

## 6. components schemas（16 个）

`ArticleSettings`、`Body_upload_kb_paper_api_kb_upload_post`、`ChatRequest`、`ConferenceUpdateRequest`、`HTTPValidationError`、`KBAskRequest`、`KBReindexRequest`、`PaperImportBatchRequest`、`PaperImportBatchResponse`、`PaperImportItemActionRequest`、`PaperImportItemLoginResponse`、`PaperImportRequest`、`PaperImportResponse`、`PaperSearchRequest`、`ValidationError`。
（其中 `HTTPValidationError`/`ValidationError` 为 422 参数校验体，均属 `{"detail": ...}` 体系。）
