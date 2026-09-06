# Spec017 Task02：迁移清单（migration-inventory）

> 生成：backend-dev ｜ 数据来源：`_raw-inventory.txt`（四段）+ `openapi-baseline.json` + spec「旧目录迁移分类与清理边界」章节。
> 本清单只做**盘点与落盘**，不移动代码、不改 spec。`_raw-inventory.txt` 在本任务结束后删除。
> 覆盖范围：58 个实现文件 + 85 行测试 patch 点 + scripts/deploy 模块路径 + 动态 import。

## 1. 实现文件全量清单（58 个，逐项可勾选）

列：文件路径 | 职责(一句话) | 目标目录 | 承接任务 | 删除时机 | 备注

### 1.1 `api/`（3 个）—— Task03 拆分范围

| 文件路径 | 职责 | 目标目录 | 承接任务 | 删除时机 | 备注 |
|---|---|---|---|---|---|
| `backend/app/api/__init__.py` | api 包入口 | `api/` | 03 | 07 校验旧路径清零后 | **spec 基线章节未逐行列出**，见 §4 待裁决 |
| `backend/app/api/routes.py` | 路由与全部端点实现（~1470 行） | `api/` 拆为各上下文子路由 | 03 | 07 | 拆分子路由后旧 `routes.py` 删除，无兼容转发 |
| `backend/app/api/schemas.py` | 请求/响应 Pydantic 模型 | `api/`（按上下文再分配） | 03 | 07 | **spec 基线章节未逐行列出**，见 §4 待裁决 |

### 1.2 `core/`（3 个）—— platform / Task03

| 文件路径 | 职责 | 目标目录 | 承接任务 | 删除时机 | 备注 |
|---|---|---|---|---|---|
| `backend/app/core/__init__.py` | core 包入口 | `platform/` | 03 | 07 | **spec 仅列 `config.py`/`article_settings.py`，未提 `__init__.py`**，见 §4 待裁决 |
| `backend/app/core/config.py` | 全局配置（`MODEL_NAME` 等） | `platform/` | 03 | 07 | spec 基线：→ platform |
| `backend/app/core/article_settings.py` | `ArticleSettings` 读写（整文件覆盖缺陷所在） | `platform/`（settings repository） | 03 | 07 | 拆为 `ArticleAssistantSettings`/`PaperDiscoverySettings`；read-modify-write |

### 1.3 `domain/`（5 个）

| 文件路径 | 职责 | 目标目录 | 承接任务 | 删除时机 | 备注 |
|---|---|---|---|---|---|
| `backend/app/domain/__init__.py` | domain 包入口 | — | 07 | 07 删除 | 移动后删除 |
| `backend/app/domain/article.py` | 文章助手领域模型 | `article_assistant/domain` | 06 | 07 | |
| `backend/app/domain/chat.py` | 聊天领域模型 | `chat/domain` | 06 | 07 | |
| `backend/app/domain/paper_discovery.py` | 论文发现领域模型 | `paper_discovery/domain` | 04 | 07 | |
| `backend/app/domain/paper_import_batch.py` | 导入批次领域模型 | `paper_discovery/domain` | 04 | 07 | |

### 1.4 `agents/`（2 个）

| 文件路径 | 职责 | 目标目录 | 承接任务 | 删除时机 | 备注 |
|---|---|---|---|---|---|
| `backend/app/agents/__init__.py` | agents 包入口 | — | 07 | 07 删除 | |
| `backend/app/agents/article_agent.py` | 文章 Agent 实现 | `article_assistant/application` | 06 | 07 | |

### 1.5 `graphs/`（2 个）

| 文件路径 | 职责 | 目标目录 | 承接任务 | 删除时机 | 备注 |
|---|---|---|---|---|---|
| `backend/app/graphs/__init__.py` | graphs 包入口 | — | 07 | 07 删除 | |
| `backend/app/graphs/chat.py` | 聊天图编排（`build_chat_graph`） | `chat/application` | 06 | 07 | patch 热点（12 次，见 §2） |

### 1.6 `observability/`（6 个）—— platform / Task03

| 文件路径 | 职责 | 目标目录 | 承接任务 | 删除时机 | 备注 |
|---|---|---|---|---|---|
| `backend/app/observability/__init__.py` | observability 包入口（导出 `derive_metrics` 等） | `platform/` | 03 | 07 | scripts 引用 `backend.app.observability`，迁移需同步 |
| `backend/app/observability/client.py` | 观测客户端 | `platform/` | 03 | 07 | |
| `backend/app/observability/config.py` | 观测开关（`enabled`） | `platform/` | 03 | 07 | patch `observability.config.enabled` |
| `backend/app/observability/safe.py` | 安全降级工具 | `platform/` | 03 | 07 | |
| `backend/app/observability/spans.py` | span 处理 | `platform/` | 03 | 07 | |
| `backend/app/observability/trace.py` | trace/`start_trace`/`end_trace` | `platform/` | 03 | 07 | 被 routes 调用 |

### 1.7 `services/` 顶层（24 个）

| 文件路径 | 职责 | 目标目录 | 承接任务 | 删除时机 | 备注 |
|---|---|---|---|---|---|
| `backend/app/services/__init__.py` | services 包入口 | — | 07 | 07 删除 | |
| `backend/app/services/acm_paper_parser.py` | ACM 论文解析 | `paper_discovery/infrastructure` | 04 | 07 | |
| `backend/app/services/ieee_paper_parser.py` | IEEE 论文解析 | `paper_discovery/infrastructure` | 04 | 07 | |
| `backend/app/services/usenix_paper_parser.py` | USENIX 论文解析 | `paper_discovery/infrastructure` | 04 | 07 | `USENIXAcceptedSource` 别名见 §4 |
| `backend/app/services/usenix_publication_source.py` | USENIX accepted 来源 | `paper_discovery/infrastructure` | 04 | 07 | |
| `backend/app/services/dblp_publication_source.py` | DBLP 来源 | `paper_discovery/infrastructure` | 04 | 07 | |
| `backend/app/services/arxiv_adapter.py` | arXiv 适配 | `paper_discovery/infrastructure` | 04 | 07 | |
| `backend/app/services/openalex_enricher.py` | OpenAlex 富化 | `paper_discovery/infrastructure` | 04 | 07 | |
| `backend/app/services/paper_browser_manager.py` | 浏览器管理（含动态 `importlib.metadata`） | `paper_discovery/infrastructure` | 04 | 07 | 见 §3 动态 import |
| `backend/app/services/paper_download.py` | 论文下载 | `paper_discovery/infrastructure` | 04 | 07 | |
| `backend/app/services/paper_discovery_store.py` | 论文发现 SQLite 仓储 | `paper_discovery/infrastructure` | 04 | 07 | 模块级单例，03 需给测试替换点 |
| `backend/app/services/paper_import_batch_store.py` | 导入批次仓储 | `paper_discovery/infrastructure` | 04 | 07 | 同上 |
| `backend/app/services/paper_discovery_normalization.py` | 论文规范化 | `paper_discovery/domain` | 04 | 07 | |
| `backend/app/services/paper_import_identity.py` | 导入身份/幂等 | `paper_discovery/domain` | 04 | 07 | |
| `backend/app/services/paper_download_security.py` | 下载安全（host 白名单等） | `paper_discovery/domain` | 04 | 07 | spec 判定：仅 3 处引用，随 paper_discovery 而非 platform |
| `backend/app/services/paper_discovery_search.py` | 论文检索编排 | `paper_discovery/application` | 04 | 07 | |
| `backend/app/services/paper_import.py` | 导入编排（当前直接 import `services.kb.*`） | `paper_discovery/application` | 04 | 07 | **依赖 KB port**，须 03 定义、05 实现、04 消费 |
| `backend/app/services/paper_import_batch_service.py` | 导入批次服务 | `paper_discovery/application` | 04 | 07 | |
| `backend/app/services/article_download.py` | 文章下载（含 `httpx.stream`） | `article_assistant/infrastructure` | 06 | 07 | patch 热点 |
| `backend/app/services/article_search.py` | 文章检索（`httpx.get`） | `article_assistant/infrastructure` | 06 | 07 | |
| `backend/app/services/task_store.py` | 任务仓储（`/agent/tasks*`） | `article_assistant/infrastructure` | 06 | 07 | 仅 routes 使用，归文章助手 |
| `backend/app/services/download_paper_skill.py` | 下载 Skill（`create_chat_model`/`build_download_plan`） | `article_assistant/application` | 06 | 07 | patch 热点 |
| `backend/app/services/ollama.py` | Ollama 模型创建/调用 | `platform/` | 03 | 07 | patch 热点（30 次） |
| `backend/app/services/ollama_direct.py` | Ollama 直连流式（`httpx.stream`） | `platform/` | 03 | 07 | patch 热点（16 次 httpx.stream） |

### 1.8 `services/kb/`（11 个）—— `knowledge_base/`

| 文件路径 | 职责 | 目标目录 | 承接任务 | 删除时机 | 备注 |
|---|---|---|---|---|---|
| `backend/app/services/kb/__init__.py` | KB facade re-export（30+ 成员） | — | 05→07 | 07 | 05 必须先固定替代入口，再删 |
| `backend/app/services/kb/chunkers.py` | 分块器 | `knowledge_base/infrastructure` | 05 | 07 | |
| `backend/app/services/kb/embed.py` | 向量化 | `knowledge_base/infrastructure` | 05 | 07 | |
| `backend/app/services/kb/index.py` | 索引 | `knowledge_base/infrastructure` | 05 | 07 | `paper_import` 依赖，经 KB port |
| `backend/app/services/kb/normalize.py` | 规范化 | `knowledge_base/infrastructure` | 05 | 07 | |
| `backend/app/services/kb/parse.py` | 解析 | `knowledge_base/infrastructure` | 05 | 07 | |
| `backend/app/services/kb/prompts.py` | 提示词 | `knowledge_base/infrastructure` | 05 | 07 | |
| `backend/app/services/kb/reranker.py` | 重排 | `knowledge_base/infrastructure` | 05 | 07 | |
| `backend/app/services/kb/retrieve.py` | 检索 | `knowledge_base/infrastructure` | 05 | 07 | |
| `backend/app/services/kb/store.py` | KB 元数据仓储 | `knowledge_base/infrastructure` | 05 | 07 | patch `services.kb.store` |
| `backend/app/services/kb/tasks.py` | 索引任务（application 入口） | `knowledge_base/infrastructure`（提供 application 入口，按 05 契约） | 05 | 07 | |

### 1.9 应用入口（1 个）

| 文件路径 | 职责 | 目标目录 | 承接任务 | 删除时机 | 备注 |
|---|---|---|---|---|---|
| `backend/app/__init__.py` | 顶层包入口 | — | 03/07 | 07 视情况 | **spec 基线章节未提及**，见 §4 待裁决 |
| `backend/app/main.py` | 应用装配（路由、静态、生命周期） | `platform/`（composition root，推荐 `platform.bootstrap`） | 03 | 07 | deploy 脚本引用 `backend.app.main:app`，迁移需同步 |

## 2. 测试 patch 点（85 行，按被测模块聚合；漏改即假绿）

> `patch` 数字为 `_raw-inventory.txt` 的引用次数汇总（同模块多符号求和）。**高危 = 次数 ≥10**。

| 被测模块（归一到 import 前缀） | 涉及测试 patch 次数 | 涉及测试文件（示例） |
|---|---:|---|
| `backend.app.api.routes`（含各函数 `get_available_models`/`search_articles`/`hybrid_search`/`record_ollama_generation`/`probe_pdf_url`/`load_papers`/`get_paper`/`end_trace` 等） | **139**（含 `routes.` 残缺前缀 5） | `tests/test_api_routes_coverage.py` 等 |
| `backend.app.services.ollama`（+`create_chat_model`/`run_chat`/`chat_direct_stream`） | **30** | ollama/直连相关测试 |
| `backend.app.services`（顶层聚合，含 ollama_direct/httpx.stream 16、kb 17、download_paper_skill 7、article_search 等） | **73** | 多测试文件 |
| `backend.app.domain`（`article` 11、`paper_discovery` 8、`paper_import_batch` 2） | **21** | domain 测试 |
| `backend.app.graphs.chat`（`build_chat_graph` 10 + `graphs` 2） | **12** | 聊天图测试 |
| `backend.app.main` | **8** | 应用装配测试 |
| `backend.app.observability`（含 `trace`/`spans`/`config.enabled`） | **5** | 观测测试 |
| `backend.app.agents`（`article_agent` 2） | **2** | agent 测试 |
| `backend.app.api`（残缺前缀） | **1** | — |

**patch 热点 Top3（必须首先修正，否则「测试通过但打错目标」假绿）**：
1. `backend.app.api.routes` —— 139 次，随 routes 拆分（Task03）必须逐端点改到子路由模块。
2. `backend.app.services.ollama` —— 30 次（含 `create_chat_model` 28），随 platform 迁移（Task03）。
3. `backend.app.services.ollama_direct.httpx.stream` —— 16 次，随 platform 迁移（Task03）。

## 3. scripts / deploy 引用 与 动态 import

### 3.1 scripts（`scripts/**/*.py`）

| 文件 | 引用的模块路径 | 动作 |
|---|---|---|
| `scripts/bench_ollama_routes.py` | `backend.app.services.ollama`、`backend.app.core.config.MODEL_NAME`、`backend.app.observability.derive_metrics` | 随 03 迁移同步改；注释声明可 patch `services.ollama.run_chat` |
| `scripts/gen_observability_samples.py` | `backend.app.core.config`、`backend.app.observability`、`backend.app.services.kb`（`CHUNKER_V1`/`build_prompt`/`hybrid_search`）、`backend.app.services.ollama`、`backend.app.services.ollama_direct` | 随 03/05 迁移同步改 |
| `scripts/__pycache__/*.pyc` | 二进制缓存 | 07 清理时一并删除 |

### 3.2 deploy（`deploy/**/*.sh`）

| 文件 | 引用的模块路径 | 动作 |
|---|---|---|
| `deploy/start.sh` | `uvicorn backend.app.main:app`（2 处） | `main:app` 若移到 `platform.bootstrap` 需同步 |
| `deploy/stop.sh` | 匹配 `uvicorn backend.app.main:app` | 同上 |

### 3.3 动态 import（无法 AST 判定，按字符串 grep）

| 位置 | 形式 | 备注 |
|---|---|---|
| `backend/app/services/paper_browser_manager.py:10,94,95` | `import importlib.metadata` / `importlib.metadata.version("playwright")` / 捕获 `PackageNotFoundError` | 非模块路径迁移，但随 `paper_discovery/infrastructure` 移动，保留逻辑不变 |

> spec 白名单：`USENIXAcceptedSource = UsenixAcceptedSource` 这类对外类名别名若被外部脚本引用，须在 spec 基线表登记并注理由；未登记视为未清理。本盘点仅登记事实，**不裁决是否保留**（见 §4）。

## 4. 待裁决（spec 基线章节未逐行列出 / 有歧义，交架构师裁决，本盘点不自行归类）

| 文件 | 现状 | 歧义点 |
|---|---|---|
| `backend/app/__init__.py` | spec 基线「旧目录迁移分类与清理边界」未提及顶层包 `__init__` | 保留空包 / 删除？归属 03 还是 07？ |
| `backend/app/api/__init__.py` | 基线章节只覆盖 `services/`/`kb/`/`domain/`/`agents/`/`graphs/`/`core/`/`observability/`，未列 `api/` 包 `__init__` | 子路由拆分的包入口归属 |
| `backend/app/api/routes.py` | 拆分到各上下文子路由是 Task03 主旨，但基线表未逐行列出目标子模块名与 operationId 映射 | 需 03 出子路由清单（spec 必改项 4 已要求，但未落表） |
| `backend/app/api/schemas.py` | 请求/响应模型目标位置（集中 `api/` 还是随各上下文）未定 | 需 03 定稿 |
| `backend/app/core/__init__.py` | 基线只列 `core/config.py`、`core/article_settings.py`，未提 `__init__.py` | 是否删除 |
| `backend/app/main.py` | spec 说 `main.py` 仅装配、生命周期由模块提供，但目标目录（`platform/bootstrap` 与否）与 deploy `main:app` 同步点未在基线逐行写明 | 入口路径是否变更影响 deploy 脚本 |
| `USENIXAcceptedSource` 别名（涉 `usenix_paper_parser.py`/`usenix_publication_source.py`） | 是否登记为白名单保留 | 需架构师裁决 |
| `services/kb/__init__.py` facade 消费者 | 30+ 成员的全量消费者清单需 05 固定替代入口后再核 | 盘点已标注，但完整消费者枚举属 05 交付 |

## 5. 与 spec 分类的差异（偏差登记）

| 项 | spec 基线 | 本盘点实测 | 处理 |
|---|---|---|---|
| `api/`（3 文件）、`main.py`、顶层 `backend/app/__init__.py` | 基线章节**未列** | 实现存在，共 5 文件 | 列入 §4 待裁决，归 Task03 但需基线补充 |
| `observability/` 文件数 | spec 记为「`observability/`」未计数 | 实测 6 个含 `__init__.py` | 全部 → `platform/`（03），无归属冲突 |
| `core/__init__.py` | 基线只列 2 个文件 | 实测 3 个含 `__init__.py` | `__init__` 待裁决 |
| 端点总数 | spec 表列 35 操作 | OpenAPI 实测 36 操作（多 1 个根路径 `GET /`） | 见 `openapi-baseline.md`；根路径非业务端点，spec 表未列 |

> 本盘点**不修改 spec**，仅登记差异，待架构师在基线表补充确认后执行。
