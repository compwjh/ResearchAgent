# Spec 017：后端限界上下文彻底重构

## 状态

**当前状态：`已确认`（2026-09-06；需求评审 4 项与技术评审 7 项打回意见已修订，architect 复审判定全部闭环，用户授权进入实现；按 `02 → 03 → 05 → 04 → 06 → 07 → 08` 顺序执行）**

## 一句话目标

在不改变现有 HTTP API、前端 JSON 契约、环境变量名称和用户数据位置的前提下，把后端一次性迁移为按业务能力组织、依赖方向清晰且不含旧内部兼容层的模块化结构。

## 背景与问题

- `backend/app/api/routes.py` 约 1470 行，同时承载系统、论文发现、知识库、文章助手与聊天接口，并直接装配大量基础设施对象。
- `backend/app/services/` 混放旧文章流程、论文发现、模型适配和知识库；同一论文发现能力又分散在 `domain/` 与 `services/`。
- `ArticleSettings` 同时承载旧文章助手和论文发现配置；应用生命周期直接依赖 KB 服务包的聚合导出。
- 当前目录使跨 IDE 或新 Agent 难以从路径判断职责边界，迁移时也容易引入跨功能耦合。

## 目标结构与依赖方向

```text
backend/app/
├── api/                    # 路由、请求/响应模型、总注册入口
├── paper_discovery/        # 论文发现、下载、导入、浏览器与安全
├── knowledge_base/         # RAG、Qdrant、重排与索引任务
├── article_assistant/      # 旧文章 Agent、搜索、下载与 Skill
├── chat/                   # 对话状态和图编排
└── platform/               # 配置、Ollama、观测、应用生命周期
```

每个业务模块按实际复杂度使用 `domain/`、`application/` 与 `infrastructure/` 子层。依赖方向固定为：`api → application → domain / infrastructure`；`domain` 不得依赖 FastAPI、HTTP 客户端、Playwright、Qdrant、Ollama 或环境变量。`platform` 是跨业务适配层，不得反向依赖业务模块。

**依赖规则（技术评审必改项 1，须机械可检，非文字承诺）**：

| 层 | 允许依赖 | 禁止 |
|---|---|---|
| `api` | 各上下文 `application` 公开入口、请求/响应 schema | import 任何 `infrastructure`、仓储、浏览器、Qdrant、HTTP 客户端；持有模块级单例 |
| `application` | 自身 `domain`；通过**构造函数注入的 port（Protocol）**获得外部能力；其它上下文 `application` 的 facade 与其 protocol/DTO | import 其它上下文的 `domain` / `infrastructure` |
| `infrastructure` | 实现本上下文声明的 port | 被 `api` 或其它上下文直接 import |
| `domain` | 标准库 + 本上下文领域模型 | FastAPI、httpx、Playwright、Qdrant、Ollama、环境变量 |
| `platform` | 横切适配与 composition-root 支持 | **import 任何业务模块**（反向依赖，直接判失败） |

## 数据模型与接口

| 项目 | 策略 |
|---|---|
| HTTP 路径、方法、状态码、JSON 字段、错误码 | 保持不变 |
| OpenAPI 表面 | 保持不变，路由拆分后以快照验证 |
| 环境变量与数据目录 | 保持不变；既有 `data/article_settings.json` 必须可读 |
| Python 内部 import | 一次性改为新路径；不保留 re-export 或兼容转发 |
| SQLite、Qdrant、KB 元数据 | 不做 schema 或数据迁移 |

`ArticleSettings` 拆为文章助手与论文发现的独立配置对象；读取时兼容现有 JSON 结构和环境变量，写入时保留不属于当前对象的字段，避免覆盖用户设置。

## 对外契约基线（HTTP 表面，验收附录）

> 需求评审必改项 1 的落地。以下为**冻结基线**：迁移前后必须逐项等价。「不保留兼容层」**仅适用于 Python 内部 import 与模块路径，不适用于 HTTP 表面**。

### 判定规则（Task07 逐项断言）

1. 路径、HTTP 方法、路径参数名不变。
2. query / body 字段名、类型、必填性、默认值不变。
3. 响应 JSON 顶层字段名与类型不变；迁移不得新增或删除字段。
4. 状态码集合不变（含 422 参数校验、424 上游不可用）。
5. 错误**状态码、错误码与错误体结构**均只增不减。现有系统存在**两类错误体，迁移中禁止相互统一**：
   - `/papers/*`：`_paper_api_error()` 产出 `{code, message, retryable}`，如 `CONFERENCE_DISABLED`(400)、`PAPER_DISCOVERY_DISABLED`(503)、`USENIX_UNAVAILABLE`(424)、`INVALID_YEARS`(422)。
   - `/agent/*`、`/chat`、`/kb/*`：FastAPI `HTTPException` 产出 `{"detail": ...}`；部分 `detail` 是对象，如 `/agent/articles/download` 的 404 返回 `{"download_outcome", "user_message", "article_url"}`。
   - `/health`：**恒返回 200**，Ollama 不可达时降级为 `models: []` 而非报错（`backend/app/api/routes.py:280-291`），不得新增错误体。
   
   把后者改成前者（或反之）即视为破坏对外契约。
6. 响应媒体类型与响应头不变：三处 SSE（`/agent/run`、`/chat`、`/kb/ask`）保持 `text/event-stream` 及 `Cache-Control: no-cache`、`X-Accel-Buffering: no`。
   > **Task02 实测风险（必须处理）**：OpenAPI 快照把这三个端点声明为 `application/json`，且 `components.schemas` 不含 `code` / `message` / `retryable` 等错误字段。因此 **Task07 禁止只比对 OpenAPI diff**，必须对「SSE 的 `Content-Type`」与「两类错误体」分别补**运行时断言**，否则「SSE 退化成 JSON」「错误体被统一」这类破坏会被静默放过。
7. 下表标注「别名」的端点**全部保留**，即使当前前端不调用。

### 端点基线（35 个操作，源自 `backend/app/api/routes.py`）

| 方法 | 路径 | 归属上下文 | 备注 |
|---|---|---|---|
| GET | `/health` | platform | |
| GET | `/papers/conferences/search` | paper_discovery | |
| GET | `/papers/conferences` | paper_discovery | |
| PATCH | `/papers/conferences/{conference_id}` | paper_discovery | |
| DELETE | `/papers/conferences/{conference_id}` | paper_discovery | |
| POST | `/papers/search` | paper_discovery | |
| GET | `/papers/conferences/{conference_id}/accepted` | paper_discovery | |
| POST | `/papers/imports` | paper_discovery | **别名**（保留） |
| POST | `/papers/import-batches` | paper_discovery | 主路径 |
| GET | `/papers/imports/{batch_id}` | paper_discovery | **别名**（保留） |
| GET | `/papers/import-batches/{batch_id}` | paper_discovery | 主路径 |
| POST | `/papers/imports/{batch_id}/retry` | paper_discovery | **别名**（保留） |
| POST | `/papers/import-batches/{batch_id}/retry` | paper_discovery | 主路径 |
| POST | `/papers/import-batches/{batch_id}/cancel` | paper_discovery | |
| POST | `/papers/import-items/{item_id}/login` | paper_discovery | |
| POST | `/papers/import-items/{item_id}/resume` | paper_discovery | |
| GET | `/papers/browser/health` | paper_discovery | 主路径 |
| GET | `/papers/browser-health` | paper_discovery | **别名**（保留） |
| GET | `/agent/settings` | article_assistant | |
| PUT | `/agent/settings` | article_assistant | 见配置矩阵 |
| GET | `/agent/skills/download-paper` | article_assistant | |
| POST | `/agent/run` | article_assistant | SSE |
| GET | `/agent/tasks/{task_id}` | article_assistant | |
| POST | `/agent/articles/search` | article_assistant | |
| POST | `/agent/articles/download` | article_assistant | |
| POST | `/agent/articles/probe` | article_assistant | 下载探测 |
| POST | `/agent/articles/plan-download` | article_assistant | 下载计划 |
| POST | `/agent/tasks/{task_id}/human-actions/login-completed` | article_assistant | 人工登录恢复 |
| POST | `/chat` | chat | SSE |
| GET | `/kb/health` | knowledge_base | |
| GET | `/kb/papers` | knowledge_base | |
| POST | `/kb/upload` | knowledge_base | |
| POST | `/kb/papers/{paper_id}/reindex` | knowledge_base | |
| DELETE | `/kb/papers/{paper_id}` | knowledge_base | |
| POST | `/kb/ask` | knowledge_base | SSE |

### 基线来源与比较方式

- Task02 冻结 `GET /openapi.json` 快照，剔除不稳定字段（server url、`openapi` 版本号、含时间戳的描述），并记录 FastAPI / Pydantic 版本。
- Task07 比较：path、method、request/response schema、状态码、错误体。
- 内部模块名与 operationId 的变化**不算** API 不兼容，除非前端实际依赖（当前前端不依赖）。

## 环境与数据兼容性矩阵（需求评审必改项 2）

### 变量清单与归属

| 前缀 | 变量 | 归属上下文 | 默认 / 数据位置 |
|---|---|---|---|
| `ARTICLE_` | `ARTICLE_SETTINGS_JSON` | article_assistant | 整份 JSON 兜底（见优先级） |
| `ARTICLE_` | `ARTICLE_SEARCH_URLS`、`ARTICLE_DOWNLOAD_URLS` | article_assistant | 逗号分隔列表 |
| `ARTICLE_` | `ARTICLE_DOWNLOAD_DIR` | article_assistant | `data/articles` |
| `PAPER_DISCOVERY_` | `PAPER_DISCOVERY_DB_PATH` | paper_discovery | SQLite 路径 |
| `PAPER_DISCOVERY_` | `PAPER_DISCOVERY_DEFAULT_YEARS`、`SEARCH_LIMIT`、`MAX_SEARCH_LIMIT`、`CANDIDATE_POOL`、`SEARCH_TTL_SECONDS`、`REQUEST_TIMEOUT_SECONDS` | paper_discovery | 见 `ArticleSettings` |
| `PAPER_DISCOVERY_` | `PAPER_DISCOVERY_ALLOWED_HOSTS` | paper_discovery | 下载白名单 |
| `PAPER_DISCOVERY_` | `PAPER_DISCOVERY_BROWSER_PROFILE_DIR` | paper_discovery | 浏览器 profile |
| `OLLAMA_` | `OLLAMA_BASE_URL`、`OLLAMA_MODEL`、`OLLAMA_ROUTE` | platform | |
| `KB_` | `KB_DIR`、`KB_COLLECTION`、`KB_TOP_K`、`KB_RERANK_CANDIDATES`、`KB_CANDIDATE_POOL` | knowledge_base | |
| `KB_` | `KB_MAX_UPLOAD_MB`、`KB_EMBED_BATCH_SIZE`、`KB_EMBED_NUM_BATCH` | knowledge_base | |
| `CHUNK_V2_` | `CHUNK_V2_MAX_CHARS`、`CHUNK_V2_LLM_MODEL`、`CHUNK_V2_LLM_TIMEOUT`、`CHUNK_V2_LLM_BATCH` | knowledge_base | |
| — | `QDRANT_PATH` | knowledge_base | Qdrant 本地路径 |

> 注：`PAPER_DISCOVERY_DISABLED` / `PAPER_DISCOVERY_STORE_UNAVAILABLE` / `PAPER_DISCOVERY_UNAVAILABLE` / `KB_IMPORT_FAILED` 是**错误码**不是环境变量，迁移中按错误码常量处理，不得误当配置删除。

### 加载优先级（现行 `load_article_settings()` 行为，必须逐字保持）

1. `data/article_settings.json` 存在 → **文件优先**；此时 `ARTICLE_SETTINGS_JSON` **不生效**。
2. 否则 `ARTICLE_SETTINGS_JSON` 非空 → 解析该 JSON。
3. 否则 → 用 `ARTICLE_SEARCH_URLS` / `ARTICLE_DOWNLOAD_URLS` / `ARTICLE_DOWNLOAD_DIR` 构造默认值。
4. 最后 `PAPER_DISCOVERY_*`（8 个）**始终覆盖**以上结果（`model_dump() | overrides`）。

### 拆分后的读写规则

- 拆为 `ArticleAssistantSettings` 与 `PaperDiscoverySettings` 两个对象，读写统一由**一个 settings repository** 负责（归属 Task03）。
- **读取**：旧 JSON 按字段前缀映射到两个对象；未识别 key 原样保留在 raw 层，不得丢弃。
- **写入**：必须 **read-modify-write**——先读全文 → 合并本域字段 → 保留另一域字段与未知 key → 原子写（临时文件 + `os.replace`）。
  现行 `save_article_settings()` 是整文件 `model_dump_json()` 覆盖（`backend/app/core/article_settings.py:126-128`），拆分后若沿用该写法会静默丢失另一域配置，**这是本次必须消除的缺陷**。

### 冲突验收样例（Task03/07 必须可执行）

| 样例 | 输入 | 期望 |
|---|---|---|
| 旧 JSON 双域字段 | 原文含 article 与 paper_discovery 两组字段 | 两个对象各自读到自己的字段 |
| 保存文章设置 | 改 `article_download_dir` 后保存 | paper_discovery 字段与未知 key 原样保留 |
| 环境变量覆写 | JSON 有值且 `PAPER_DISCOVERY_SEARCH_LIMIT` 有值 | 环境变量生效，文章设置不受影响 |
| 未知 key | JSON 含未来版本字段 | 保存后仍存在 |

## 边界

- 任何路由模块只调用所属业务模块公开 application 入口，不直接访问仓储、浏览器、Qdrant 或 HTTP 客户端。
- `main.py` 仅装配应用、静态资源、总路由和生命周期；启动恢复由对应模块提供接口。
- 迁移完成后，旧 `services/`、顶层 `domain/`、`agents/`、`graphs/` 中迁移范围内的业务实现与项目内 import 均为零。
- Spec015 的 Task10 由本 Spec 承接；不能同时在两个 Task 中移动相同文件。

## 旧目录迁移分类与清理边界（需求评审必改项 4）

> 每个现有业务文件**恰好归属一个任务**；分类以本表为基线，Task02 盘点时逐项校验，偏差须在此表更新后方可执行。禁止实现 Agent 自行决定归属。

### `services/`（顶层，24 个文件）

| 文件 | 分类 | 目标 | 任务 |
|---|---|---|---|
| `__init__.py` | 删除 | — | 07 |
| `acm_paper_parser.py`、`ieee_paper_parser.py`、`usenix_paper_parser.py` | 移动 | `paper_discovery/infrastructure` | 04 |
| `usenix_publication_source.py`、`dblp_publication_source.py`、`arxiv_adapter.py`、`openalex_enricher.py` | 移动 | `paper_discovery/infrastructure` | 04 |
| `paper_browser_manager.py`、`paper_download.py`、`paper_discovery_store.py`、`paper_import_batch_store.py` | 移动 | `paper_discovery/infrastructure` | 04 |
| `paper_discovery_normalization.py`、`paper_import_identity.py`、`paper_download_security.py` | 移动 | `paper_discovery/domain` | 04 |
| `paper_discovery_search.py`、`paper_import.py`、`paper_import_batch_service.py` | 移动 | `paper_discovery/application` | 04 |
| `article_download.py`、`article_search.py`、`task_store.py` | 移动 | `article_assistant/infrastructure` | 06 |
| `download_paper_skill.py` | 移动 | `article_assistant/application` | 06 |
| `ollama.py`、`ollama_direct.py` | 移动 | `platform/` | 03 |

分类依据（代码事实）：`paper_download_security` 当前仅被 `paper_browser_manager`、`usenix_publication_source`、`paper_download` 三处引用，故随论文发现迁移而非 `platform`；`task_store` 仅被 `routes.py` 的 `/agent/tasks*` 使用，归文章助手。

### `services/kb/`（11 个文件）→ `knowledge_base/`

| 文件 | 分类 | 目标 | 任务 |
|---|---|---|---|
| `__init__.py` | 删除 | 现有 facade re-export 30+ 成员，Task05 必须先固定替代入口 | 05 |
| `chunkers.py`、`embed.py`、`index.py`、`normalize.py`、`parse.py`、`prompts.py`、`reranker.py`、`retrieve.py`、`store.py`、`tasks.py` | 移动 | `knowledge_base/infrastructure`（`tasks.py` 提供 application 入口，按 Task05 契约定稿） | 05 |

### 顶层 `domain/`（5 个文件）

| 文件 | 分类 | 目标 | 任务 |
|---|---|---|---|
| `__init__.py` | 删除 | — | 07 |
| `article.py` | 移动 | `article_assistant/domain` | 06 |
| `chat.py` | 移动 | `chat/domain` | 06 |
| `paper_discovery.py`、`paper_import_batch.py` | 移动 | `paper_discovery/domain` | 04 |

### `agents/`（2 个）与 `graphs/`（2 个）

| 文件 | 分类 | 目标 | 任务 |
|---|---|---|---|
| `agents/__init__.py`、`graphs/__init__.py` | 删除 | — | 07 |
| `agents/article_agent.py` | 移动 | `article_assistant/application` | 06 |
| `graphs/chat.py` | 移动 | `chat/application` | 06 |

### 补充：`core/` 与 `observability/`

`core/config.py`、`core/article_settings.py`、`observability/` → `platform/`（任务 03）。设置拆分按上文「环境与数据兼容性矩阵」执行。

### import 检查范围（清理判定）

必须扫描以下四类，**逐类给出清零证据**：

1. `backend/**/*.py` 的 `from backend.app...` / `import backend.app...`。
2. `tests/**/*.py` 的 import 与 **monkeypatch 字符串**（如 `backend.app.services.kb.store`、`backend.app.api.routes`）——测试 patch 点漏改会造成「测试通过但打错目标」的假绿。
3. `scripts/**/*.py`、`deploy/**/*.sh` 中的模块路径字符串。
4. **动态 import 字符串**：`importlib.import_module(...)`、`getattr(module, "...")`、配置里的点分路径。此类无法用 AST 判定，必须按字符串 grep。

### 清理判定与例外

- 判定命令（Task07）：在上述四类范围内 grep `backend.app.services.`、`backend.app.domain.`、`backend.app.agents.`、`backend.app.graphs.` 结果为空。
- **白名单例外**：`USENIXAcceptedSource = UsenixAcceptedSource` 这类**对外类名别名**若被外部脚本引用，须在本表登记为白名单并注明理由；未登记的一律视为未清理。
- 无法判定归属的文件：默认留在原位，在 Task02 清单标注「待裁决」，由架构师裁决后才可移动；**不允许以「迁移范围内」为由跳过检查**。

### 补充归属（架构师裁决，Task02 盘点后补齐）

Task02 实测 58 个实现文件，本表补齐此前未归类的 6 个：

| 文件 | 分类 | 目标 | 任务 |
|---|---|---|---|
| `backend/app/__init__.py` | 保留原位 | 包标记，不移动 | — |
| `backend/app/main.py` | **保留原位**（仅装配） | 只保留应用装配、静态资源、总路由与生命周期注册 | 03 |
| `backend/app/api/__init__.py` | 保留 | `api/` 包标记 | — |
| `backend/app/api/routes.py` | 拆分后删除 | 按业务拆为 `api/` 下子路由模块，原文件在 Task07 删除 | 03 拆分 / 07 删除 |
| `backend/app/api/schemas.py` | 保留（可按端点拆分） | 请求/响应模型留在 `api/` | 03 |
| `backend/app/core/__init__.py` | 随 `core/` 迁 `platform/` | Task07 确认无引用后删除 | 03 |

> **部署约束**：`deploy/start.sh` 与 `deploy/stop.sh` 以 `uvicorn backend.app.main:app` 为入口。**`main.py` 的路径与 ASGI 应用对象名必须保持不变**，否则服务会静默启动失败；Task07 完成后必须实际启动一次验证。

## 跨上下文端口契约与装配（技术评审必改项 2、3、4）

### 论文导入 → 知识库端口（必改项 2）

**代码事实**：`backend/app/services/paper_import.py` 当前直接 import `services.kb.index`、`services.kb.store`、`services.kb.tasks`。这与「论文发现只能经 KB application 入口协作」冲突，**无法靠移动文件解决**，必须先定义端口。

契约（Task03 定义，Task05 实现，Task04 消费）：

- 输入：候选快照 + **受信任的本地 PDF 路径**（不得把 URL 交给 KB 自行下载）。
- 输出：稳定 `paper_id`、索引状态、稳定错误码。
- **不暴露**：Qdrant 客户端、store、task 对象、内部集合名。
- 幂等：同一候选重复导入不得产生重复论文或重复索引任务（沿用现有 upsert 语义）。
- v1 / v2 索引完成语义沿用现有行为，不得因迁移改变 `index_status` 取值与流转。

顺序（硬约束）：`03 定义 port 与注入位置 → 05 实现 KB adapter → 04 切换论文发现调用`。**Task04 不得早于 Task05 的 KB application contract 可用**；若 04/05 并行，必须在 Task03 先冻结 protocol/DTO 与 platform 临时 wiring，且**不得借此保留旧 `services.kb` 转发**。

### 设置拆分与持久化（必改项 3）

`ArticleAssistantSettings`、`PaperDiscoverySettings` 与**唯一的 settings repository 归属 Task03 前置交付**，供 Task04/06 消费；规则见上文「环境与数据兼容性矩阵」。**Task04 与 Task06 不得并行移动同一个 settings repository 或数据文件**。

### API composition root（必改项 4）

Task03 必须产出并落盘：

- 每个子路由模块清单、端点归属、路由前缀保持方式、请求/响应 schema 的最终位置；
- 应用生命周期 hook 的注册方式；
- application service 的创建地点（统一 factory，推荐 `platform.bootstrap`）；
- FastAPI dependency / provider 的**测试替换点**——用于消除当前 `routes.py` 的模块级单例（`TaskStore`、`PaperDiscoveryStore`、`PaperImportBatchStore`、`PaperBrowserManager` 等）。

## 静态边界检查规则（技术评审必改项 6）

Task07 必须提供**可执行的 architecture test**，而非文字承诺。规则与允许表：

| 规则 | 判定 |
|---|---|
| `api` import `*.infrastructure.*` | 禁止 |
| `domain` import FastAPI / httpx / Playwright / Qdrant / Ollama / 环境配置 | 禁止 |
| 业务模块之间循环依赖 | 禁止 |
| `platform` import 业务模块 | 禁止 |
| 业务模块 import 其它上下文的 `domain` / `infrastructure` | 禁止 |
| `application` import 其它上下文 `application` 的 protocol / DTO | **允许** |

无法用 import 判定的运行时装配规则（如「路由不得自建仓储/浏览器/HTTP 客户端」），同样写成 architecture test 断言，不得只写在文档里。

## 明确不做

- 不新增业务能力、前端功能、微服务、数据库 schema 迁移或数据搬迁。
- 不改动外部 API 契约、模型选择、论文下载安全策略或 RAG 召回逻辑。
- 不保留旧 Python 导入路径、长期兼容层或双实现。
- 不执行 reset、stash、clean、自动 push、合并 main 或覆盖现有未提交改动。

## 产品使用步骤

1. **进入论文发现**：打开论文检索页，看到会议列表与检索入口（会议可查询、停用与启用）。
2. **检索与导入**：
   - 输入关键词、选定会议与年份后检索，查看返回的候选论文列表；
   - 只想看已接收论文时选择「已接收（accepted）」范围；该范围仅对服务端配置了 accepted 来源的会议生效（当前为 USENIX Security）；
   - 需要批量获取时勾选候选并提交批量导入，在进度页查看批次状态，失败可重试、进行中可取消。
3. **下载与人工登录**：
   - 对需要权限的论文点击下载；若站点要求登录，任务进入「等待人工登录」状态；
   - 用户完成登录后点击「登录已完成」，任务继续下载。
4. **入库知识库**：已下载的 PDF 进入知识库；用户也可自行上传 PDF、查看论文列表、对单篇重建索引或删除。
5. **问答与聊天**：
   - 在知识库问答框输入问题，答案以流式（SSE）逐段返回并给出引用出处；
   - 或在聊天页发送消息，同样以流式接收回复。

### 验收场景表

| 场景 | 操作 | 成功可观察结果 | 失败场景与应保持不变的错误 |
|---|---|---|---|
| 1. 健康检查 | `GET /health` | HTTP 200，返回 `{status: "ok", model, models, paper_discovery_enabled}` | Ollama 不可达时**仍返回 200 且 `models: []`**，不得新增错误体（见 `routes.py:280-291`） |
| 2. 文章设置读取 | `GET /agent/settings` | HTTP 200，返回当前配置（含 `article_*` 字段） | Ollama 不可达 → 503，且保持 `{"detail": ...}` |
| 3. 文章设置保存（跨上下文不丢配置） | `PUT /agent/settings` 仅改 `article_download_dir` → `GET /agent/settings` → 执行一次论文检索 | 200；文章配置已更新，且 **`paper_discovery_*` 与未知字段未丢失**，论文检索仍可用 | 参数非法时沿用原 4xx 与 `{"detail": ...}`；**禁止整文件覆盖导致另一上下文配置丢失** |
| 4. 文章任务创建 | `POST /agent/run` | 200，以 SSE（`text/event-stream`）返回任务与进度 | 问题为空 → 400 `{"detail": "问题不能为空"}`；Ollama 不可达 → 502 `{"detail": ...}` |
| 5. 文章任务轮询 | `GET /agent/tasks/{task_id}`（多次） | 200，状态推进至完成 | 任务不存在 → 404 `{"detail": "任务不存在"}` |
| 6. 人工登录恢复 | `POST /agent/tasks/{task_id}/human-actions/login-completed` | 200，任务离开「等待登录」状态并继续 | 任务不在等待登录 → 400 `{"detail": "任务当前不在等待登录状态"}`；候选不存在 → 404 |
| 7. 会议查询与启停 | `GET /papers/conferences/search` → `PATCH /papers/conferences/{conference_id}` 停用 → 再用该会议检索 | 列表正常返回；停用后针对该会议的检索被拒绝 | `CONFERENCE_DISABLED`(400)、`CONFERENCE_NOT_CONFIGURED`(400)、`CONFERENCE_NOT_FOUND`(404)、`BUILT_IN_CONFERENCE_PROTECTED`(409)、`PAPER_DISCOVERY_DISABLED`(503)、`PAPER_DISCOVERY_STORE_UNAVAILABLE`(503)，均保持 `{code, message, retryable}` |
| 8. 论文检索（含 publication_scope=accepted 的 USENIX 路线） | POST `/papers/search` 传入 `{publication_scope: "accepted"}` → GET `/papers/conferences/{id}/accepted` | 仅返回已接收论文列表；USENIX 若不可用则拒绝并返回 `USENIX_UNAVAILABLE`(424) | 当配置中无 accepted route 时返回 `ACCEPTED_ROUTE_NOT_CONFIGURED`(400)；搜索不支持该 scope 时返回 `ACCEPTED_SEARCH_UNSUPPORTED`(424)；年份等参数非法时返回 `INVALID_YEARS`(422)、`INVALID_ACCEPTED_YEAR`(422)、`INVALID_ACCEPTED_CYCLE`(422)、`INVALID_QUERY`(422) |
| 9. 批量导入与重试（体现别名 `/papers/imports` 仍可用） | POST `/papers/import-batches` → GET `/papers/import-batches/{batch_id}` → 失败后 POST `/papers/import-batches/{batch_id}/retry` / `cancel`；同样访问 `/papers/imports/...` | 初始导入返回 batch_id；重试前状态为 `queued/failing`；取消后无残留条目 | 导入整体失败时返回 `KB_IMPORT_FAILED` |
| 10. 浏览器健康检查与登录恢复（别名 `/papers/browser-health` 仍可用） | `GET /papers/browser/health` → `POST /papers/import-items/{item_id}/login` → `POST /papers/import-items/{item_id}/resume` | 健康状态返回；登录后条目可继续下载/导入 | `BROWSER_UNAVAILABLE`(503)、`BROWSER_SESSION_REQUIRED`(424)、`PAPER_DISCOVERY_DISABLED`(503)，均保持 `{code, message, retryable}` |
| 11. 知识库上传、列表、重建、删除 | `POST /kb/upload` → `GET /kb/papers` → `POST /kb/papers/{paper_id}/reindex` → `DELETE /kb/papers/{paper_id}` | 上传后列表更新；重建索引任务完成；删除返回确认 | 非 PDF → 400 `{"detail": "只支持上传 PDF 文件"}`；超过 `KB_MAX_UPLOAD_MB` → 400；论文不存在 → 404 `{"detail": "论文不存在"}`；原件丢失 → 404 `{"detail": "论文原件已丢失，无法重建索引"}` |
| 12. 知识库 SSE 问答 | `POST /kb/ask` | 200，`Content-Type: text/event-stream`，答案分块流式返回 | 问题为空或超长 → 400 `{"detail": ...}`；Ollama 不可达 → 502 `{"detail": ...}` |
| 13. 聊天 SSE | `POST /chat` | 200，回复以 SSE 流式返回，媒体类型不变 | 问题为空/超长 → 400；模型不存在 → 400；Ollama 不可达 → 502，均保持 `{"detail": ...}` |

> 所有上述路径均沿用迁移前端点与行为，用户无需更改前端调用、环境变量或数据位置。

## 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---:|---|---|
| 架构师 | 自身 | 200k | 主会话 | 结构决策、编排、落地校验 |
| 产品经理 | `qwen3.5:9b` | 32k | 子 Agent | 使用步骤与验收场景 |
| 开发主管 | `qwen3.8:27b-mlx` | 32k | 子 Agent | 需求、技术、验收评审与裁决 |
| 初级开发 | `qwen3.8:27b-mlx` | 32k | 子 Agent | 范围内代码迁移与自测 |
| 测试 | `qwen3.5:9b` | 32k | 子 Agent | 契约、边界与运行时验收 |

## 任务计划

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec017 | 本文件 | — | 完成 |
| 02 | 建立迁移清单与契约基线 | [Task 02](../plans/017/task-02-contract-baseline.md) | 01 | 待执行 |
| 03 | 拆分 API 与平台装配（含设置拆分、composition root、跨域 port 定义） | [Task 03](../plans/017/task-03-api-platform.md) | 02 | 待执行 |
| 05 | 迁移知识库限界上下文（先提供 KB application facade） | [Task 05](../plans/017/task-05-knowledge-base.md) | 03 | 待执行 |
| 04 | 迁移论文发现限界上下文（消费 KB port） | [Task 04](../plans/017/task-04-paper-discovery.md) | 05 | 待执行 |
| 06 | 迁移文章助手与聊天（消费已拆分的设置与 platform） | [Task 06](../plans/017/task-06-article-chat.md) | 03 | 待执行 |

**执行顺序**：`02 → 03 → 05 → 04 → 06 → 07 → 08`。Task04 **不得早于** Task05 的 KB application contract 可用；Task06 依赖 Task03 的 settings repository，在目录不重叠时可与 Task04 并行；Task04 与 Task06 不得同时移动同一个 settings repository 或数据文件。

**Task02 硬门禁（技术评审必改项 5）**：Task02 产物必须是**逐项可勾选的全量迁移清单**，每行包含：文件路径 → 目标目录 → 承接任务 → 删除时机。必须覆盖：全部 `.py` 实现、测试（含 monkeypatch 字符串与 patch 点，如 `tests/test_api_routes_coverage.py`）、启动/部署脚本（`scripts/`、`deploy/`）、`observability/`、`core/config.py`、`core/article_settings.py`、`services/kb/__init__.py` 的**全部 facade 消费者**、以及动态 import 字符串。**同一文件只能归属一个任务**；清单未覆盖的文件一律视为「待裁决」，不得由实现 Agent 自行处理。
| 07 | 删除旧结构并验证模块边界 | [Task 07](../plans/017/task-07-remove-legacy-boundaries.md) | 04, 05, 06 | 待执行 |
| 08 | 评审、部署与复盘 | [Task 08](../plans/017/task-08-review-deploy-retro.md) | 07 | 待执行 |

## 评审记录

- 需求评审：`docs/sdd/reviews/017-requirement-review.md`（**打回** → 4 项必改已于 2026-09-06 修订，待复审）
- 技术评审：`docs/sdd/reviews/017-tech-review.md`（**打回** → 7 项必改已于 2026-09-06 修订，待复审）
- 验收评审：`docs/sdd/reviews/017-acceptance-review.md`（测试报告 + 开发主管签字；待评审（未执行））

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-05 | 架构师（自身） | 根据用户确认建立全后端彻底重构 Spec；初始状态为待确认，等待评审与状态门禁。 |
| 2026-09-06 | 架构师（自身） | 需求评审（打回）与技术评审（打回）后修订：新增「对外契约基线」（35 个端点、4 组公开别名、三类 SSE、**两类错误体**）、「环境与数据兼容性矩阵」（含 `load_article_settings` 四级优先级与 read-modify-write 要求）、「旧目录迁移分类与清理边界」（逐文件归属 + 四类 import 检查范围）、「跨上下文端口契约与装配」、「静态边界检查规则」；补齐产品使用步骤与 13 项验收场景；任务顺序改为 `02→03→05→04→06→07→08`。状态仍为 `待确认`，待复审。 |
