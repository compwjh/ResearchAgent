# Spec017 Task02 评审：迁移清单与契约基线

> 评审对象：`docs/sdd/plans/017/migration-inventory.md`、`openapi-baseline.md`（backend-dev 产出，纯文档、无代码改动）。
> 结论用途：判断 Task02 是否满足「硬门禁」（全量、逐项可勾选、无未裁决文件阻塞 Task03）。

## 1. 文件数 vs spec 基线差异

| 维度 | spec 基线 | 实测（本盘点） | 差异 |
|---|---|---|---|
| 实现文件总数 | 基线章节逐行列出 44 + `core/`(2) + `observability/`(6) = 52 | **58** | 基线**未列 6 个**：`api/__init__.py`、`api/routes.py`、`api/schemas.py`、`main.py`、`backend/app/__init__.py`、`core/__init__.py` |
| 端点操作 | 表列 35 | OpenAPI 实测 **36** | 多 1 个根路径 `GET /`（非业务，spec 未列） |
| patch 点 | 提及需覆盖 | **85 行 / 341 次引用** | 已全部聚合到被测模块 |

**结论**：58 个实现文件中，52 个有 spec 基线归属；**6 个文件 spec 基线章节未逐行列出**，已登记为「待裁决」，**Task03 开工前须由架构师在基线表补充**，不得由实现 Agent 自行归类。

## 2. 待裁决清单（7 项，须架构师裁决）

1. `backend/app/__init__.py`：顶层包入口，保留/删除、归属 03 还是 07。
2. `backend/app/api/__init__.py`：子路由拆分包入口归属。
3. `backend/app/api/routes.py`：拆分子子路由的目标模块名与 operationId 映射（Task03 必改项 4 要求但未落表）。
4. `backend/app/api/schemas.py`：请求/响应模型集中 `api/` 还是随各上下文。
5. `backend/app/core/__init__.py`：是否删除。
6. `backend/app/main.py`：入口目标目录（`platform/bootstrap`？）与 deploy `main:app` 同步点。
7. `USENIXAcceptedSource` 别名：是否登记为清理白名单保留。
（附：`services/kb/__init__.py` 的 30+ facade 消费者完整枚举属 Task05 交付，Task02 仅标注。）

## 3. 风险 Top3

1. **OpenAPI 快照不含两类错误体与 SSE media type**：`components.schemas` 无 `retryable`/`code` 结构，3 个 SSE 端点在快照声明为 `application/json`。→ Task07 若只比 OpenAPI diff，会**漏掉「错误体不统一」与「SSE 退化为 JSON」两大破坏**。**必须为错误体结构与 SSE `text/event-stream`+响应头补运行时断言**。
2. **`backend.app.api.routes` patch 热点（139 次）+ `services.ollama`（30）+ `ollama_direct.httpx.stream`（16）**：routes 拆分与 platform 迁移若漏改 monkeypatch 字符串，将产生「测试通过但打错目标」的**假绿**，掩盖契约破坏。
3. **6 个文件待裁决未定归属**：`api/`、`main.py`、`__init__.py` 等无基线归属，Task03 composition root 无输入；且 `deploy/*.sh` 的 `uvicorn backend.app.main:app` 若入口路径变更将**静默启动失败**。

## 4. Task03 开工前必须注意的三件事

1. **先补基线**：架构师须为 6 个待裁决文件补归属并落表（基线章节现覆盖 `services/kb/domain/agents/graphs` 但未含 `api/main`），Task03 才有人可执行。
2. **先定义跨域 port 与 settings repository**：`paper_import.py` 直接依赖 `services.kb.*`，须 03 定义 KB port、05 实现、04 消费；`ArticleSettings` 拆分须 03 交付唯一 settings repository（read-modify-write 消除整文件覆盖缺陷），04/06 不得并行移动同一 repository/数据文件。
3. **composition root 给测试替换点**：消除 `routes.py` 模块级单例（`TaskStore`/`PaperDiscoveryStore`/`PaperImportBatchStore`/`PaperBrowserManager`）须 FastAPI dependency/provider 注入并暴露测试替换点；子路由拆分必须保持 36 端点全量（含 4 组别名）与 3 个 SSE 端点。

## 5. 与 spec 分类差异小结（登记，不修改 spec）

- `api/`（3 文件）+ `main.py` + 顶层 `__init__.py` + `core/__init__.py`：基线未列，待裁决。
- `observability/` 6 个文件全部 → `platform/`（03），无归属冲突。
- 端点 36 vs 35：根路径 `GET /` 差异，非业务。
- `openapi` 版本字段：spec 要求剔除但快照保留 `3.1.0`，Task07 比较策略需明确。
