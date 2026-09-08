# Spec 015 — 安全顶会论文检索与知识库导入

## 状态

**当前状态：`实施中`（2026-09-08；USENIX-only 阶段实现完成，外部扩展 deferred）**

> **本阶段范围已收口为 USENIX Security 官方目录优先、DBLP 辅助。** Task15–17 的实现、并发/恢复复审和 USENIX-only QA 已完成；Spec 仍保持 `实施中`，因为 ACM/IEEE 登录、自定义会议、A14 排序质量、真实公开 PDF 导入与 GUI/窄屏运行时证据被明确 deferred，待后续扩展阶段补齐后再转 `已完成`。
>
> **暂停代码实现的原因（用户既定顺序）**：先完成 Spec017 后端限界上下文重构与全量回归，再回来做 Task15/16（依据 `docs/sdd/retro/2026-09-06-spec015-task15-16-not-dispatched.md`）。恢复时必须先核对本表状态与 `.codebuddy/agent-logs/`，确认 Task15 是否已有分派记录。

> Task02–12 的真实实现与评审证据保留；Task13–17 需求/技术复审已通过（见 `docs/sdd/reviews/015-catalog-requirement-review.md`、`015-catalog-tech-review.md`），用户已授权进入实现。Task13/14 已落地，Task15–17 已完成 USENIX-only 实现与验收；不得通过回滚、stash、清理或覆盖现有成果。
> 状态变更须同步追加 `docs/sdd/spec-status-changelog.md`。

## 架构变更（待确认）

### 变更原因

Spec015 当前实现把论文发现相关领域模型放在 `backend/app/domain/`，把检索、数据源、下载、浏览器、批量导入和解析器分散放在 `backend/app/services/`。这些文件共同服务同一个论文发现能力，却没有显式的限界上下文，导致目录无法表达 Spec015 边界，且迁移、测试和跨 IDE 阅读时需要同时扫描多个目录。

### 目录决策

统一使用 `backend/app/paper_discovery/`，不使用过于泛化的 `backend/app/paper/`，避免与知识库既有 PaperRecord 和旧文章下载业务发生语义冲突。

目标结构如下（具体文件名以迁移前的 import 盘点为准）：

```text
backend/app/paper_discovery/
├── __init__.py
├── domain/                 # 领域模型与状态对象
├── repositories/           # discovery/import-batch SQLite 仓储
├── application/            # 搜索、导入、批量、重试/恢复用例
├── sources/                # DBLP、OpenAlex
├── parsers/                # ACM、IEEE
├── browser/                # Playwright profile、锁和认证请求
├── security/               # URL/SSRF、PDF、身份与安全错误
└── naming.py               # 规范文件名与论文身份
```

`backend/app/api/routes.py` 和 `backend/app/api/schemas.py` 保留为薄 API 适配层；`article_download.py`、`download_paper_skill.py` 等 Spec015 之外的旧文章流程不迁入，除非 import 盘点证明其仅服务本 Spec。

### 依赖方向与迁移约束

```text
API routes/schemas → application → repositories / sources / browser / security
                                  ↓
                                domain
```

`domain/` 不依赖 FastAPI、HTTP 客户端、Playwright、Qdrant 或环境变量；外部副作用由 application 层编排。先用 `rg` 建立 import/测试/脚本清单，再按层执行可回滚的 `git mv`；迁移只改变物理路径和 import，不改变 API、SQLite schema、状态机、错误码、安全策略、日志字段或行为。旧目录只保留明确不属于本 Spec 的模块或有记录的兼容转发。

### 架构重构验收

- `backend/app/paper_discovery/` 成为 Spec015 论文发现代码的唯一实现根目录。
- `rg` import 盘点无循环依赖；domain 层无外部副作用 import；API 路由只调用 application 用例。
- 现有论文、下载、批量、浏览器、安全、KB 兼容测试全量通过，服务健康接口和论文 API 行为不变。
- `git diff --check`、冲突标记和敏感产物扫描通过；不改变用户已有未提交文件。

## 现有实现复用与替换边界（实现硬约束）

> 本章是 Task13–17 的强制输入。任何执行 Agent 必须先完成复用审计，再写代码；不得因为旧模块路径不理想、接口不完全匹配或重写更方便，就建立第二套同类能力。Task 结果必须逐项说明“直接复用 / 参数化复用 / 有证据替换”。

### 必须原样复用的能力

| 能力 | 当前实现 | 本轮允许的调用方式 | 禁止事项 |
|---|---|---|---|
| PDF 安全下载与校验 | `backend/app/services/paper_download.py` | 仅在用户选择导入后调用；继续执行重定向、大小、魔数、页数、临时文件和校验和检查 | 搜索或目录同步阶段不得批量下载、HEAD/GET 探测 PDF；不得新建旁路下载器 |
| URL、DNS、重定向与 SSRF 防护 | `backend/app/services/paper_download_security.py` | USENIX 页面、PDF 和所有跳转继续经过同一安全策略 | 不得弱化 HTTPS、origin、端口、公共 IP 或逐跳校验 |
| 单篇知识库导入 | `backend/app/services/paper_import.py` | 从冻结搜索结果解析服务端目录论文标识后进入现有导入 saga | 不得让客户端提交任意 PDF URL；不得建立第二套 PDF 入库流程 |
| 批量导入与恢复 | `paper_import_batch_service.py`、`paper_import_batch_store.py`、`domain/paper_import_batch.py` | 保留状态机、CAS、租约、重试、恢复、幂等和逐项隔离 | 检索任务必须使用独立状态表，不得破坏导入任务语义 |
| 论文身份与命名 | `paper_import_identity.py`、`paper_discovery_normalization.py` | 复用 DOI、标题、作者、年份、会议和规范文件名规则；新增目录 ID 只能扩展而不能绕过这些规则 | 不得用来源 URL 或用户输入直接作为文件名/唯一身份 |
| Playwright 登录 | `paper_browser_manager.py` | 只用于 ACM/IEEE 等合法登录下载和既有导入等待流程 | 公开 USENIX 元数据同步与检索不得要求登录或读取浏览器凭证 |

### 必须参数化或扩展后复用的能力

- `usenix_paper_parser.py`：保留同源 URL、显式链接和可注入 fixture 解析边界；扩展列表论文块、详情摘要、官方关键词和 cycle/summer/fall 多种页面结构。
- `usenix_publication_source.py`：保留受控 HTTP 客户端、节流、安全校验和稳定错误；改为按来源抓取单元同步全量元数据，移除按用户关键词过滤、进程内权威缓存和搜索阶段 PDF 探测。
- `dblp_publication_source.py`：保留 stream/year、主会过滤、重试、稳定错误和去重；在新流程中只补 DOI、DBLP key 等缺失书目信息，绝不覆盖 USENIX 官方标题、作者、摘要和关键词。
- `paper_discovery_store.py`：保留 WAL、外键、busy timeout、显式事务、schema 迁移和服务端 ID；升级为全局目录、抓取单元、搜索任务、来源进度、事件和冻结结果模型。
- `paper_discovery_search.py`：保留输入校验、来源告警、规范化、合并和稳定排序思想；同步编排改为 LangGraph 异步工作流。
- `services/kb/embed.py`、`index.py`、`retrieve.py`：复用 BGE-M3 dense+sparse、Qdrant 初始化、RRF 和可选 reranker；必须把 collection、payload 映射和过滤器参数化，论文发现目录使用独立 collection，不能混入个人 PDF 分块。

### 必须替换的旧路径

- 同步 `POST /api/papers/search` 及前端一次请求等待全部来源完成的调用方式。
- 把同一论文按搜索会话重复复制到 `paper_candidates`、并以短期 TTL 作为唯一事实来源的数据方式。
- `UsenixAcceptedSource` 的进程内字典缓存，以及由单个 `cycle{n}` 模板决定所有年度页面的方式。
- USENIX 检索阶段逐篇下载或探测 PDF 的 `_get_pdf` / `_preferred_pdf` 路径；候选只记录页面显式提供的 URL，真正验证延迟到导入阶段。
- 前端把任何外部源错误统一显示为“论文服务暂时不可用”的行为；必须按来源展示缓存、抓取、完成、降级和错误。

### 复用审计与停止条件

1. Task13 在实现前生成逐文件复用清单，记录当前符号、调用者、测试及拟采用方式。
2. 若旧接口不能满足要求，先增加参数或适配层；确需替换时，Task 结果必须给出无法安全复用的可复现证据、迁移范围和回归测试。
3. 发现第二套下载、安全、导入、批任务、身份规范化或 embedding 实现时立即停止，不得继续扩散。
4. Tech Lead 必须使用本章、实际 diff 和复用审计执行独立复核；聊天回复不能作为唯一评审材料。

## 一句话目标

新增独立“论文检索”Tab，让用户按研究方向检索安全四大顶会或自行添加的会议论文，结果按语义相关程度降序展示，并支持已发表论文与会议官网 accepted/prepublication 论文的单篇或批量 PDF 下载，按“年份-会议-标题”规范命名后直接导入个人知识库。

## 背景与实测证据

1. 当前 `backend/app/services/article_search.py` 已接入 Crossref/OpenAlex，但主要用标题字符串相似度排序，不适合“LLM Agent 安全”等研究方向式查询。
2. 当前文章下载与知识库上传是两条独立流程：下载结果不会自动进入知识库，用户需要再次选择本地 PDF。
3. 现有知识库已具备 PDF 校验、文本提取、切块、向量化、重建和删除能力；本功能应复用统一导入链路，不建立第二套索引系统。
4. DBLP Search API 已实测支持会议流和年份查询。四个默认主会流为 `conf/ccs`、`conf/uss`、`conf/sp`、`conf/ndss`；DBLP Venue Search 可用于搜索并新增会议。
5. DBLP 会议流可能混入 Workshop、Poster、Demo 等记录，必须结合出版物类型与主会名称白名单过滤，不能只判断 stream id。
6. OpenAlex 可补充 DOI、摘要、开放获取状态和 PDF 地址，并提供基础相关度信号。
7. spec-014 将提供统一的本地 rerank 能力。本功能只调用其内部服务，不直接把 `dengcao/Qwen3-Reranker-0.6B:Q8_0` 当聊天模型打分。
8. 当前环境没有可直接复用且经过验证的 `opencli` 浏览器登录桥接。用户已选择项目内 Playwright 持久化浏览器会话，并要求真实验收 ACM Digital Library 与 IEEE Xplore 登录续传。
9. spec-013、spec-014 正在开发或收口。本功能等待二者形成稳定提交后再开始，禁止复制半成品或清理当前工作树。

## USENIX 官方目录优先的增量检索流程（待确认）

### 数据源范围与权威顺序

本轮只实现 `USENIX Security`。USENIX 官方会议页面是论文发现与展示元数据的权威来源；DBLP 与其并行运行，但只用于补齐 DOI、DBLP key 和缺失书目信息。arXiv 不参与目录主召回，只保留为用户导入时官方 PDF 不可用的严格匹配兜底。其他安全会议官网适配器不在本轮实现。

字段合并顺序固定如下：

1. 标题、作者、摘要、关键词、会议、年份、presentation URL、官方 PDF/prepublication URL：USENIX 官方值优先。
2. DOI、DBLP key 和 USENIX 未提供的书目信息：DBLP 只填空值，不覆盖官方字段。
3. arXiv id/PDF：仅在用户触发导入且官方 PDF 链失败时，以规范标题、作者集合和年份严格匹配后补充。
4. 关键词仅保存官网明确提供的内容；官网没有关键词时保存空列表，禁止由 LLM 或规则推断。
5. DBLP-only 记录没有可核对的官方摘要时可保存在来源记录中，但不得进入本轮用户可见结果。

### 首批固定样本与自动页面发现

首批解析 fixture 必须覆盖用户提供的四个官方页面：

- `https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers`
- `https://www.usenix.org/conference/usenixsecurity25/cycle1-accepted-papers`
- `https://www.usenix.org/conference/usenixsecurity24/summer-accepted-papers`
- `https://www.usenix.org/conference/usenixsecurity24/fall-accepted-papers`

对用户请求的每个年份，服务端从受控的 USENIX Security 年度会议入口发现 accepted-papers 链接，只接受同源且路径满足该年度会议前缀的 `cycle*`、`summer`、`fall` accepted 页面。用户不能提交入口或列表 URL。发现失败时将该年份标记为来源错误，不猜测论文详情或 PDF 文件名；已配置的四个首批样本作为确定性种子和解析回归材料。

### 增量同步规则

- 最小缓存单元为 `source_kind + conference_id + year + unit_key`；USENIX 的 `unit_key` 是规范 accepted 页面路径，DBLP 的 `unit_key` 是主会 stream/year 分页游标。
- `completed` 且内容标识未变化的单元直接复用，搜索进度显示“已使用缓存”；`pending/failed/expired` 单元才进入抓取。
- 同一抓取单元只能有一个有效租约；并发搜索共享抓取结果，不能重复请求同一页面。
- HTTP `ETag`/`Last-Modified` 可用时发送条件请求；否则以规范化正文哈希判断变化。`304` 或哈希不变只更新时间，不重复向量化。
- 示例：目录已完整保存 2022 年，再搜索 2022–2024 年时，2022 显示缓存命中，只抓取 2023–2024 年缺失单元。
- 页面解析完成后先在同一 SQLite 事务内写来源记录和规范目录记录，再提交单元为 `completed`；部分详情失败时单元为 `partial`，成功论文可用，失败详情保留可重试事件。

### LangGraph 工作流

每次用户搜索创建持久化 `SearchJob`，HTTP 创建接口立即返回。LangGraph 使用固定节点，不让弱执行 Agent或运行时模型临时设计流程：

```text
validate_request
      ↓
plan_fetch_units
      ↓
┌──────────────────┬──────────────────┐
│ sync_usenix      │ sync_dblp        │  并行、分别写来源进度
└──────────────────┴──────────────────┘
      ↓
merge_catalog_metadata                USENIX 字段优先，DBLP 只补空值
      ↓
index_changed_catalog_papers          只索引新增或 metadata_hash 变化记录
      ↓
retrieve_and_rerank                   按研究方向召回，失败时保留可解释降级
      ↓
freeze_search_results                 固化名次、分数和展示快照
      ↓
finalize_job                          completed / partial / failed
```

节点开始、完成、缓存命中、重试、降级和失败均写 `SearchEvent`；事件只保存受控枚举、计数、年份、耗时和脱敏错误码，不保存 Cookie、Token、Authorization、完整查询参数或隐藏思维链。任一来源失败但目录仍有可召回论文时任务为 `partial`，只有两个来源均不可用且目录无可用记录时才为 `failed`。

### RAG 召回与分页

- 论文发现使用独立 Qdrant collection，payload 至少包含 `catalog_paper_id`、会议、年份、标题、摘要、关键词和 `metadata_hash`；不得写入个人 PDF 分块 collection。
- 检索文本固定为 `title + abstract + keywords`；复用 BGE-M3 dense+sparse 和 RRF。可用时调用既有 reranker；不可用时返回 `degraded=true`，不得伪造 rerank 分数。
- 会议和年份在向量召回时作为服务端过滤条件；候选只能来自已完成或 partial 的目录记录。
- 每次任务完成前把结果按稳定次序冻结：`final_score desc, retrieval_score desc, year desc, normalized_title asc, catalog_paper_id asc`。
- 页面大小固定为 10。首次只读取第 1 页；“下一页”读取同一冻结结果的第 N 页，不重新抓取、不重新向量化、不重新排序。

### 搜索与导入分界

目录同步只保存标题、作者、摘要、关键词、来源和页面显式给出的 PDF URL，不请求 PDF 内容，也不判定 PDF 是否有效。只有用户从冻结结果选择“添加到知识库”后，现有导入流程才按官方 PDF → prepublication PDF → 严格 arXiv 兜底执行安全下载和 PDF 验证。

项目级 Skill 也按该边界拆分：目录检索、增量缓存、LangGraph、RAG 和来源进度使用 `.agents/skills/usenix-paper-catalog-search/SKILL.md`；下载、PDF 验证、批量导入和登录续传使用 `.agents/skills/usenix-accepted-papers/SKILL.md`。Task13–17 的主 Skill 固定为目录版，Task17 的公开论文导入验收才额外调用下载版。

### 安全与合规边界

- 元数据同步仅允许服务端配置的 `www.usenix.org` 与 `dblp.org` HTTPS origin；arXiv 仅在导入兜底时访问 `arxiv.org`/`export.arxiv.org`。
- 尊重来源 robots、使用条款、条件请求、缓存和最小请求间隔；不通过并行图节点绕过同一来源的节流器。
- 不绕过登录、验证码、付费墙或访问控制；不猜测 PDF 文件名，不遍历站点目录，不接受客户端来源 URL。

## 回滚点（Rollback Baseline）

| 项 | 值 |
|---|---|
| 仓库起点 | `feature/spec-015-security-paper-discovery@c17c7f4`（Spec 013、014 已合入的历史起点） |
| 本轮 Spec015 成果检查点 | **待创建**。用户要求本轮先只落盘文档，故不得伪造 commit hash；创建时必须纳入当前 Spec015 代码/测试/评审/Skill，并明确排除 `docs/sdd/specs/017-*`、`docs/sdd/plans/017/**`、`docs/sdd/reviews/017-*` |
| 检查点验证证据 | 当前成果全量回归 `552 passed, 5 warnings, 38 subtests`；`git diff --check` 在机械空白修复后通过。创建 commit 前必须再次核对暂存文件和敏感产物 |
| 目标分支 | `feature/spec-015-security-paper-discovery`（实现前创建并记录分支快照） |
| 完整关闭 | `PAPER_DISCOVERY_ENABLED=false`，隐藏 Tab 并关闭新增 API |
| 运行时降级 | OpenAlex 或 Reranker 异常时返回可用的降级结果；Playwright 异常不影响公开 PDF |
| 数据回滚 | 不删除已成功导入的知识库论文；新增元数据字段保持向后兼容 |

> 创建分支前必须记录当前 commit、工作树状态和 spec-013/014 验收结果。禁止 `git reset --hard`、`git clean`、`git stash`、覆盖式 checkout 或批量复制。

## 数据模型与配置

### 配置项

| 配置 | 类型 | 默认值 | 约束 |
|---|---|---|---|
| `PAPER_DISCOVERY_ENABLED` | bool | `true` | `false` 时不展示入口，不执行检索或导入 |
| `PAPER_DISCOVERY_DB_PATH` | str | `data/paper_search/state.sqlite3` | 保存会议配置、全局论文目录、抓取单元、搜索任务与导入状态 |
| `PAPER_DISCOVERY_DEFAULT_YEARS` | int | `5` | 最近五个完整发表年份 |
| `PAPER_DISCOVERY_PAGE_SIZE` | int | `10` | 冻结搜索结果的固定页面大小；客户端不可覆盖 |
| `PAPER_DISCOVERY_CANDIDATE_POOL` | int | `200` | rerank 前候选上限 |
| `PAPER_DISCOVERY_BATCH_LIMIT` | int | `20` | 单次批量导入上限 |
| `PAPER_DISCOVERY_SEARCH_TTL_SECONDS` | int | `86400` | 搜索任务与冻结结果有效期；被导入任务引用的快照不得清除 |
| `PAPER_DISCOVERY_FETCH_LEASE_SECONDS` | int | `300` | 单个来源抓取单元租约；过期后允许恢复 |
| `PAPER_DISCOVERY_ACTIVE_YEAR_REVALIDATE_SECONDS` | int | `86400` | 当前会议年份的页面发现和条件请求间隔；历史 completed 年份默认永久缓存 |
| `PAPER_DISCOVERY_QDRANT_COLLECTION` | str | `paper-discovery-catalog` | 论文发现元数据专用 collection，不得与个人 PDF 分块共用 |
| `PAPER_DISCOVERY_REQUEST_TIMEOUT_SECONDS` | float | `20` | 单个外部源请求超时 |
| `PAPER_DISCOVERY_BROWSER_PROFILE_DIR` | str | `data/browser-profile/security-papers` | Playwright 本地会话目录，不进 Git；单 profile 文件锁与目录权限必须校验 |
| `PAPER_DISCOVERY_FILENAME_MAX_LENGTH` | int | `180` | 文件名最大长度 |

当前时间为 2026 年时，默认完整年份范围为 2021—2025，不自动包含尚未结束的 2026 年。

### 会议配置 `ConferenceSource`

| 字段 | 类型 | 含义 |
|---|---|---|
| `conference_id` | str | 稳定内部标识 |
| `name` | str | 会议全称 |
| `short_name` | str | 界面和文件名简称 |
| `dblp_stream` | str | 经 DBLP Venue Search 验证的会议流 |
| `venue_aliases` | list[str] | 主会出版物名称白名单 |
| `built_in` | bool | 是否内置会议 |
| `enabled` | bool | 是否进入默认选择 |
| `created_at` / `updated_at` | datetime | 创建与更新时间 |

`ConferenceSource` 还可配置 `discovery_routes`：`dblp_published`、`usenix_accepted`、`arxiv_fallback`；每条路线保存服务端受控年度入口、确定性种子页面、启用状态和最小请求间隔。客户端不能提供模板或 URL；单个 cycle 模板不再作为年度完整性的依据。

内置会议为 CCS、USENIX Security、IEEE S&P、NDSS。用户可搜索并新增会议；内置会议只能停用，不能删除。

### 旧搜索候选 `PaperCandidate`（schema v1 迁移输入）

下表是 Task03/11 已实现的旧会话候选。Task13 迁移时保留可读取能力，但 Task15 新异步搜索不得继续写入；新权威模型为本节后述的 `CatalogPaper + SearchResult`。

| 字段 | 类型 | 含义 |
|---|---|---|
| `search_id` / `candidate_id` | str | 搜索会话与服务端候选标识 |
| `dblp_key` | str / null | DBLP 记录标识 |
| `title` / `authors` / `year` | str / list / int | 基础元数据 |
| `conference_id` / `conference_name` | str | 会议标识与简称 |
| `doi` / `abstract` | str / null | DOI 与摘要 |
| `article_url` / `pdf_url` | str / null | 详情页和已解析 PDF 地址 |
| `publication_stage` | enum | `published` / `accepted` / `prepublication`，默认 `published` |
| `source_kind` | enum | `dblp` / `usenix_accepted` / `arxiv` |
| `source_page_url` / `arxiv_id` | str / null | 受控详情页与严格匹配的 arXiv 标识 |
| `source_links` | list | 受控来源规范 URL 与类型 |
| `pdf_access` | enum | `public` / `login_required` / `unavailable` / `unknown` |
| `retrieval_score` | float | 初排分数 |
| `rerank_score` | float / null | spec-014 返回的分数 |
| `final_score` / `rank` | float / int | 最终分数与名次 |
| `existing_paper_id` | str / null | 已在知识库时的论文标识 |

### 导入任务

`PaperImportBatch` 保存 `batch_id`、`search_id`、状态、总数、成功数、失败数、等待登录数和时间戳。状态为 `queued/running/waiting_login/partial_success/completed/failed/cancelled`。

`PaperImportItem` 保存 `item_id`、`batch_id`、`candidate_id`、状态、规范文件名、`paper_id`、稳定错误码、错误说明、尝试次数和时间戳。状态为 `queued/downloading/waiting_login/validating/indexing/completed/failed`。

批次与条目状态迁移由数据库条件更新约束：`queued → downloading → validating → indexing → completed`，登录分支为 `downloading → waiting_login → downloading`；`failed` 只能由显式 retry/resume 回到 `queued`。非法迁移返回稳定错误码。批次状态由持久化条目聚合计算，禁止维护可漂移的成功/失败计数。v1 同步索引成功即可将条目标记 `completed`；v2 异步索引单独记录事件，失败不得撤销 v1 已可检索论文。

### SQLite 实现级契约（schema v1）

- 数据库启动时执行 `PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;`，所有写入使用显式事务；时间统一 RFC3339 UTC（含 `Z`）。`schema_meta(version INTEGER NOT NULL)` 必须存在且当前版本为 `1`。
- 所有业务 ID 使用 TEXT 主键；`paper_candidates` → `search_sessions` 可级联删除，`paper_import_batches/items` 对搜索和候选只允许 `RESTRICT`/保留快照，禁止 TTL 清理删除已有导入历史。`conference_sources` 对 `dblp_stream` 建唯一索引；`search_sessions` 对 `search_id` 建唯一索引并保存 `expires_at`；`paper_candidates` 对 `(search_id,candidate_id)`、`(search_id,dblp_key)`（非空）建唯一索引；`paper_import_items` 对 `(batch_id,candidate_id)` 建唯一索引；DOI/DBLP key/规范标题组合键建可空唯一索引。
- `paper_import_batches` 与 `paper_import_items` 的状态、`attempt_count`、`lease_owner`、`lease_expires_at` 和 `updated_at` 必须在同一事务更新；条目租约默认 15 分钟，续租不超过 5 分钟一次；批次统计只能由条目状态聚合查询得到。搜索 TTL 清理只删除已过期会话及未被导入引用的候选，不删除已导入论文或批次历史。
- 并发创建、retry、resume 必须使用唯一约束加条件 `UPDATE ... WHERE state IN (...)`；禁止“先查后写”作为唯一幂等保障。启动恢复只将 `downloading/validating/indexing` 且租约过期的条目转为 `failed`（错误码 `IMPORT_INTERRUPTED`）。`cancel` 只允许 `queued/waiting_login/failed`，转入 `cancelled` 后不得自动重试；已进入 `indexing/completed` 的条目不可取消。

### SQLite schema v2：全局目录与异步检索

schema v2 以迁移方式保留 v1 的会议和导入历史；旧 `search_sessions/paper_candidates` 只用于读取并迁移尚未过期的服务端候选，不再是新搜索的权威来源。迁移必须可在已有 v1 数据库上重复执行，失败回滚整个迁移事务。

| 模型 / 表 | 关键字段与约束 |
|---|---|
| `SourceFetchUnit` / `source_fetch_units` | `fetch_unit_id`、`source_kind`、`conference_id`、`year`、`unit_key`、`source_url`、`status(pending/fetching/completed/partial/failed)`、`etag`、`last_modified`、`content_hash`、`paper_count`、`error_code`、`lease_owner`、`lease_expires_at`、`last_attempt_at`、`last_success_at`、`created_at`、`updated_at`；唯一约束 `(source_kind,conference_id,year,unit_key)` |
| `CatalogPaper` / `catalog_papers` | `catalog_paper_id`、`conference_id`、`year`、`title`、`normalized_title`、`authors_json`、`abstract`、`keywords_json`、`doi`、`dblp_key`、`publication_stage`、`official_page_url`、`official_pdf_url`、`prepublication_pdf_url`、`arxiv_id`、`metadata_hash`、`index_status(pending/indexed/failed)`、`index_version`、`created_at`、`updated_at`；DOI 和规范标题+作者+年份+会议建立可空唯一身份约束 |
| `CatalogSourceRecord` / `catalog_source_records` | `source_record_id`、`catalog_paper_id`、`fetch_unit_id`、`source_kind`、`source_key`、`raw_metadata_json`、`observed_at`；唯一约束 `(source_kind,source_key)`，外键删除采用 `RESTRICT`，保留来源证据 |
| `SearchJob` / `search_jobs` | `search_id`、`query`、`conference_ids_json`、`years_json`、`status(queued/running/completed/partial/failed)`、`graph_version`、`degraded`、`error_code`、`total_results`、`created_at`、`started_at`、`completed_at`、`expires_at`、`updated_at` |
| `SearchSourceProgress` / `search_source_progress` | `search_id`、`source_kind(usenix/dblp)`、`status(queued/checking_cache/fetching/merging/completed/cached/failed)`、`cached_units_json`、`fetching_units_json`、`completed_units_json`、`paper_count`、`error_code`、`message_code`、`updated_at`；主键 `(search_id,source_kind)` |
| `SearchEvent` / `search_events` | 单调 `event_id`、`search_id`、`node_name`、`source_kind`、`event_type`、`status`、`safe_payload_json`、`created_at`；只允许预定义字段和脱敏值 |
| `SearchResult` / `search_results` | `search_id`、`catalog_paper_id`、`rank`、`retrieval_score`、`rerank_score`、`final_score`、`snapshot_json`、`created_at`；唯一约束 `(search_id,catalog_paper_id)` 与 `(search_id,rank)`，冻结后不可更新 |

所有 JSON 写入前使用 Pydantic/领域类型校验。目录字段更新采用 `metadata_hash` 比较：哈希不变不更新 `updated_at`、不重复 embedding；哈希变化时先写目录并置 `index_status=pending`，索引成功后再条件更新为 `indexed`。搜索结果只引用 `indexed` 记录；单条索引失败写事件并从本次可见结果排除，不删除其目录元数据。

### 下载资源与 SSRF 固定上限

- 连接超时 10 秒、单次读取超时 30 秒、总下载超时 120 秒；最多 5 次重定向；响应头上限 64 KiB；PDF 最大 64 MiB；同时最多 3 个下载 worker；临时目录权限 `0700`，临时文件使用随机名并以同目录原子 rename。
- 禁止自动跟随重定向。每一跳仅允许 HTTPS、443 端口和站点 allowlist；URL 不得包含 userinfo、fragment 或认证参数。DNS 解析结果必须筛除 IPv4/IPv6 的 loopback、private、link-local、multicast、reserved、unspecified、IPv4-mapped IPv6 和混淆表示；实际连接绑定已校验公共 IP，或连接后复核 peer IP，防 DNS rebinding。

### 导入 saga 与补偿点

| 阶段 | commit point | 失败补偿 |
|---|---|---|
| `downloaded` | 受控临时 PDF 通过大小、魔数和页数校验 | 删除临时文件 |
| `metadata_recorded` | SQLite/PaperRecord 写入且状态为 `indexing` | 回滚该事务或标记 `failed`，不删除旧记录 |
| `v1_indexed` | Qdrant v1 写入成功 | 删除本次向量；失败则保留 `indexing` 并可重试 |
| `completed` | 文件安全 rename、元数据和 v1 索引均可对账 | 任一缺失均不得标记完成；启动对账修复孤儿文件/记录 |
| `v2_queued` | 异步任务事件持久化 | 记录 `V2_INDEX_FAILED`，不撤销 v1 可检索结果 |

网络、PDF 解析、embedding、Qdrant 调用不得在全局锁内执行；启动对账必须幂等。

### 知识库元数据扩展

现有 `PaperRecord` 增加可选的 `title`、`authors`、`year`、`conference_id`、`conference_name`、`doi`、`source_url`、`import_source`、`stored_name`。旧记录缺少这些字段时仍可正常列出、检索、重建和删除。

### 文件命名

默认格式为 `{年份}-{会议简称}-{规范化标题}.pdf`，例如 `2025-CCS-Short-Paper-Title.pdf`。年份未知时用 `UnknownYear`；会议简称只取服务端配置；非法字符和连续分隔符统一清洗；超长时只截断标题；同名但 DOI 不同的论文追加稳定短标识。物理文件名可读，但数据库唯一身份仍为 `paper_id`。

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败与降级 |
|---|---|---|---|
| `GET /api/papers/conferences` | — | 内置与用户会议配置 | 功能关闭返回明确错误 |
| `GET /api/papers/conferences/search` | `q` | DBLP 会议候选 | DBLP 超时返回稳定错误 |
| `POST /api/papers/conferences` | 服务端候选标识、简称与别名 | 新会议配置 | 拒绝任意未验证抓取 URL |
| `PATCH /api/papers/conferences/{id}` | 简称、别名、启用状态 | 更新后的配置 | 不允许改写内置源身份 |
| `DELETE /api/papers/conferences/{id}` | — | 删除结果 | 内置会议只能停用 |
| `POST /api/papers/searches` | `query`、`conference_ids`、`years` | HTTP 202；`search_id`、任务状态、USENIX/DBLP 初始进度 | 400 参数错误；409 幂等冲突；503 工作流依赖不可用 |
| `GET /api/papers/searches/{search_id}` | 服务端 `search_id` | 任务状态、两个来源进度、事件游标、总结果数、降级信息 | 404 不存在；410 已过期 |
| `GET /api/papers/searches/{search_id}/results?page=N` | `page>=1` | 固定 10 条冻结结果、`total`、`total_pages`、`has_next` | 400 页码非法；404 不存在；409 任务尚未产生可读快照；410 已过期 |
| `GET /api/papers/conferences/{conference_id}/accepted` | `year`、可选分页 | 只读全局目录中的 USENIX accepted/prepublication 记录 | 不触发网络；目录未同步返回空结果与明确缓存状态 |
| `POST /api/papers/imports` | `search_id`、候选 id 列表 | 批次和逐项状态 | 拒绝过期或伪造候选 |
| `GET /api/papers/imports/{batch_id}` | — | 批次进度与逐项结果 | 不存在返回 404 |
| `POST /api/papers/imports/{batch_id}/retry` | — | 重试后的任务状态 | 已成功项不重复执行 |
| `GET /api/papers/browser/health` | — | Playwright 和支持站点状态 | 不返回 Cookie 或登录内容 |
| `POST /api/papers/import-items/{item_id}/login` | — | 打开受控登录会话 | 浏览器不可用返回稳定错误 |
| `POST /api/papers/import-items/{item_id}/resume` | — | 续传后的任务状态 | 未登录或无权限保持可重试失败 |

### 异步检索 JSON 契约

创建请求只接受以下字段，多余字段由 Pydantic 拒绝：

```json
{
  "query": "LLM agent security",
  "conference_ids": ["usenix-security"],
  "years": [2024, 2025, 2026]
}
```

`conference_ids` v1 必须且只能为去重后的 `usenix-security`；`years` 为升序去重整数数组。创建成功返回 HTTP 202：

```json
{
  "search_id": "server-generated-id",
  "status": "queued",
  "degraded": false,
  "source_progress": [
    {"source_kind": "usenix", "status": "queued", "cached_units": [], "fetching_units": [], "completed_units": [], "paper_count": 0, "error_code": null, "message_code": "SOURCE_QUEUED"},
    {"source_kind": "dblp", "status": "queued", "cached_units": [], "fetching_units": [], "completed_units": [], "paper_count": 0, "error_code": null, "message_code": "SOURCE_QUEUED"}
  ]
}
```

状态接口返回同一 `search_id`、`status`、`degraded`、`total_results`、`source_progress`、`next_event_cursor` 和增量 `events`。`events` 每项固定为 `event_id,node_name,source_kind,event_type,status,safe_payload,created_at`；客户端传上次 `next_event_cursor` 获取后续事件，省略时返回最近受控数量，不能请求无限事件。

结果页固定响应：

```json
{
  "search_id": "server-generated-id",
  "status": "completed",
  "page": 1,
  "page_size": 10,
  "total": 21,
  "total_pages": 3,
  "has_next": true,
  "items": [
    {
      "catalog_paper_id": "server-generated-id",
      "rank": 1,
      "title": "Paper title",
      "authors": ["Author"],
      "year": 2025,
      "conference_id": "usenix-security",
      "conference_name": "USENIX Security",
      "abstract": "Official abstract",
      "keywords": [],
      "doi": null,
      "publication_stage": "accepted",
      "source_page_url": "https://www.usenix.org/conference/.../presentation/...",
      "source_kinds": ["usenix", "dblp"],
      "retrieval_score": 0.0,
      "rerank_score": null,
      "final_score": 0.0,
      "existing_paper_id": null
    }
  ]
}
```

URL 字段只返回经过服务端 allowlist 验证的规范来源地址；结果响应不直接返回可由客户端替换的下载地址。冻结 `snapshot_json` 保存上述展示字段和受控来源引用，导入时由服务端以 `search_id + catalog_paper_id` 重新解析当前允许的下载链。

来源进度 `message_code` 只允许：`SOURCE_QUEUED`、`CHECKING_CACHE`、`CACHE_HIT`、`FETCHING_SOURCE`、`MERGING_METADATA`、`SOURCE_COMPLETED`、`SOURCE_PARTIAL`、`SOURCE_FAILED`。前端维护对应中文文案；未知 code 显示通用安全文案，不显示 raw error。

所有新增接口使用 Pydantic 请求/响应模型。错误体固定为 `{code,message,retryable,request_id}`，状态码映射为 400（参数/状态）、404（资源）、409（幂等冲突）、424（外部依赖降级不可用）、502（外部源协议错误）、503（功能依赖不可用）。条目动作的规范路径为 `/api/papers/import-items/{item_id}/login` 与 `/api/papers/import-items/{item_id}/resume`；客户端 ID 仅作查找键，不拼接 URL。

Task16 切换前端后删除旧同步 `POST /api/papers/search` 路由，不保留会绕过全局目录的双写或兼容实现。导入请求中的候选 id 解释为对应 `search_id` 下冻结结果里的 `catalog_paper_id`；服务端从 `snapshot_json` 与当前目录记录交叉验证来源，客户端仍不能提交 URL。

### 检索顺序

1. 校验查询、年份和会议。本轮只允许 `USENIX Security`；查询去空白后作为 RAG 检索文本，不用于决定官网哪些论文入库。
2. 创建 `SearchJob` 和 USENIX/DBLP 两条初始进度记录，提交 LangGraph 后立即返回 HTTP 202。
3. `plan_fetch_units` 在短事务中计算缓存命中和缺失单元；网络请求、解析、embedding 和 rerank 均在事务及全局锁外执行。
4. USENIX 与 DBLP 并行：USENIX发现并同步请求年份的官方 accepted 页面和详情元数据；DBLP 按主会 stream/year 分页补充书目信息。两个来源分别写状态事件。
5. 以 DOI、DBLP key 或规范化标题+作者+年份+会议合并；USENIX 官方字段优先，DBLP 只填空值，来源原始记录保留用于审计。
6. 只对新增或 `metadata_hash` 变化的目录论文生成 BGE-M3 dense+sparse 向量并写独立 collection；索引失败逐项隔离。
7. 在会议和年份过滤下，以用户研究方向从目录召回候选池，通过 RRF 融合；可用时复用 spec-014 reranker，失败时保留初排并标记降级。
8. 按稳定 tie-break 冻结结果后更新 `total_results`，有可见结果但任一来源失败记 `partial`，全部成功记 `completed`，两个来源均不可用且目录没有可见记录才记 `failed`。

### 导入顺序

1. 只从服务端搜索会话读取候选，拒绝客户端自带下载 URL。
2. 下载前以 DOI、DBLP key、标题组合键检查重复。
3. 优先使用公开 PDF；否则解析出版商页面；需要登录时进入 `waiting_login`，不阻塞批次其他项。
4. 下载至临时文件，校验 HTTPS、重定向目标、大小、PDF 魔数和可读取页数。
5. 生成规范文件名，再调用统一知识库导入服务。
6. 写入前再次去重，完成 PDF 保存、元数据落盘和现有索引流程。
7. 成功后删除临时文件并返回 `paper_id`；失败记录稳定错误码并允许重试。

跨文件、JSON 与 Qdrant 不承诺跨介质原子事务，采用可恢复 saga：每阶段写入持久状态和事件；后续阶段失败时执行幂等补偿（删除临时文件、移除未提交元数据或标记索引待重试），启动时扫描孤儿文件/记录并恢复非终态。网络、PDF 解析、embedding、Qdrant 调用不得在全局锁内执行。

## 边界（每条之后会变成一条测试）

- 查询去除空白后不能为空，最长 500 字符；至少选择一个已启用会议。
- 年份范围必须合法且不超过配置上限；默认取最近五个完整年份。
- 本轮搜索请求只接受 USENIX Security；选择其他会议返回可理解的“来源尚未支持”，不得静默改走 DBLP-only 旧路径。
- 同一 USENIX 年份可能有多个 cycle/summer/fall 页面；缓存和完成状态按页面单元记录，不能以“该年份抓过一个页面”误判整年完成。
- 两个并发搜索命中同一缺失抓取单元时只有一个执行网络请求，另一个等待或复用结果；租约过期后可恢复。
- 历史 completed 单元默认永久使用缓存；当前会议年份超过 24 小时后只做条件重验证，`304` 或内容哈希不变不得重复 embedding。
- 页面只提供标题、摘要而没有关键词时结果正常显示空关键词；禁止生成关键词。
- 搜索任务完成后分页顺序必须稳定；翻页不得重新访问来源、重新召回或改变前页名次。
- 搜索阶段不得请求 PDF 响应体；目录中的 PDF URL 只有在用户导入后才进入安全下载验证。
- DBLP 或 OpenAlex 单源失败时尽量返回可用结果并标记降级；全部召回失败才整体失败。
- Workshop、Poster、Demo、Tutorial、Doctoral Consortium 不得混入主会结果。
- DOI、DBLP key 或规范标题相同的论文只展示一次。
- accepted/prepublication 论文不得标记为 published；`publication_stage` 必须在列表、导入任务和知识库元数据中保持一致。
- USENIX accepted 路线只能从服务端配置的年份/cycle 列表页开始；详情页和 PDF 链接必须来自 allowlist。
- arXiv 仅接受标题、作者集合和年份达到严格匹配阈值的结果；匹配不确定时返回稳定错误，不自动导入。
- 搜索会话过期后不得继续导入；客户端不得提交任意 URL。
- 单次批量最多 20 篇；一项失败或等待登录不阻塞其他项。
- 服务重启后运行中的任务恢复为可重试状态，不永久停在 `running`。
- 下载前和写入前均去重；重复点击不得创建第二份有效论文。
- 只允许 HTTPS；每次重定向后重新校验目标，禁止 loopback、内网、链路本地、本地文件协议和非 HTTP(S) 协议。
- 下载器禁止自动跟随重定向；每跳限制最大次数、仅允许 HTTPS 和站点 allowlist，拒绝用户信息、混淆/非标准 IP、IPv4-mapped IPv6、loopback/private/link-local/multicast/reserved/unspecified 地址。解析后的公共 IP 必须绑定到实际连接或在连接后复核 peer IP，防止 DNS rebinding；每次跳转重新执行校验。
- 下载固定连接/读取/总超时、响应头上限、最大 PDF 字节数、并发数与临时目录权限；流式写入唯一临时文件后安全 rename。日志只记录规范化域名、阶段、耗时和稳定错误码。
- 非 PDF、伪 PDF、超限文件或不可读取 PDF 不得进入知识库。
- 文件名不得为空、逃逸目录或覆盖不同论文。
- 登录由用户在真实浏览器完成；密码、Cookie、Authorization 和 profile 内容不得进入日志、API 或 Git。
- Playwright 不可用时公开 PDF 仍可检索和导入；spec-014 不可用时降级初排。
- 知识库 v1 同步与 v2 异步流程均返回真实状态；旧记录仍可列出、重建和删除。
- 用户离开 Tab 后导入继续运行；重复提交采用幂等键防重。
- 日志只记录阶段、域名、任务标识、耗时和错误码，不记录完整查询、摘要、URL 查询参数或认证信息。
- Playwright 仅允许 ACM/IEEE 最小 origin allowlist；公开 accepted 路线另受 USENIX/arXiv allowlist、robots、节流和缓存约束。单 profile 具备文件锁和所有权；禁用 trace、HAR、video、下载录制等可能含凭证的产物，用户取消、浏览器崩溃、跳出 allowlist 和无权限下载均返回稳定可重试错误。

## 明确不做（划出范围，防 AI 自由发挥）

- 不抓取 Google Scholar，不默认检索所有安全会议。
- 不把 Workshop、Poster、Demo 或 Tutorial 当主会论文。
- 不下载补充材料、数据集、代码仓库或视频。
- 不发起第三方文献互助，不绕过验证码、付费墙、机构授权或出版商访问控制。
- 不收集用户密码，不把 Cookie、profile 或搜索历史上传云端。
- 不新增云端向量库、云端 embedding 或另一套 Reranker。
- 不重做现有聊天页文章下载流程，只允许抽取共用安全下载能力。
- 不实现引用网络、作者画像、订阅提醒或自动追踪新论文。
- 不实现通用会议官网爬虫；本轮只试点 USENIX Security accepted-papers 页面，其他会议另行增加受控路线。
- 不在本轮实现 CCS、IEEE S&P、NDSS 或其他会议官网适配器；UI 可以保留配置但异步新流程必须明确提示尚未支持。
- 不让 DBLP-only 且缺少可核对官方摘要的记录进入本轮用户可见结果。
- 不用 LLM 生成摘要、关键词、作者或出版状态，不保存模型隐藏思维链。
- 不为目录同步下载 PDF，不以 PDF 可用性决定元数据是否入库。
- 不保留会绕过全局目录的旧同步搜索兼容路径，不进行新旧数据库双写。
- 不把论文发现元数据向量写进个人知识库 collection，不因删除搜索任务而删除已导入论文。
- 不把 accepted/prepublication 论文伪装成已发表论文；不根据低于严格阈值的 arXiv 标题相似度自动导入。
- 不自动删除已导入知识库的论文。
- 不在 spec-013、spec-014 稳定基线前开始实现，不通过回滚或清理保护现场。

## 评审强制约束（实现必须遵守）

> 原 Spec015 的需求/技术评审已通过，但本次增量目录、异步接口和 LangGraph 属于范围变化。Task13–17 在新的需求复审、技术复审与用户再次确认前均保持 `待执行`。以下约束均为实现硬门禁。

- 已发表路线以 DBLP 为主召回，accepted 路线使用服务端配置的 USENIX accepted 页面；OpenAlex 做已发表候选摘要、OA 与 PDF 补全，accepted 候选不因 OpenAlex 失败丢弃。
- 导入接口只接受服务端生成的候选标识；下载链路必须防 SSRF 并逐次校验重定向。
- 排序必须组合语义初排与 spec-014 rerank，禁止只用标题字符串相似度；降级不得伪造 rerank 分数。
- v1 不实现查询扩展模型；后续若单独引入，必须另立 spec 固定模型、`think:false`、结构化输出、资源上限和回退契约，不得改变年份/会议过滤条件。
- SQLite 必须固定 schema version、UTC 时间、主外键、唯一索引、`ON DELETE`、WAL、`foreign_keys=ON`、`busy_timeout`、显式事务和过期清理；幂等由数据库唯一约束兜底。
- 下载、校验、命名、元数据和知识库索引形成统一任务状态；索引失败不得显示成功。
- `paper_id` 是唯一身份；可读文件名不得破坏旧 `{paper_id}.pdf` 记录兼容性。
- 去重在下载前、写入前各执行一次；批量任务必须持久化、逐项隔离、幂等和可重试。
- 登录续传使用本地 Playwright profile；ACM Digital Library、IEEE Xplore 均需合法账户下真实验收。
- spec-013 观测覆盖召回、补全、rerank、下载、登录等待、校验和索引，且不记录敏感内容。
- 排序质量采用首次查看最终排名前冻结的标注集，不允许验收时删题或修改标签。
- 所有代码实现先分派 `junior-dev`；使用本地 Ollama 模型时每次最多 2 个代码文件、150 行，线上模型不受该数量上限约束；评审与验收由规定角色真实执行。
- Tech Lead 必须用“现有实现复用与替换边界”、Task13 复用审计和实际 diff 做逐项核对；未解释的新下载器、安全校验、导入器、任务状态机、身份规范化或 embedding 实现一律打回。
- 弱调度 Agent只能原样执行 Task 中的固定 Prompt；若接口、迁移或文件边界与真实代码不一致，必须标记阻塞，不得自行补设计。

## 验收方式

| 验收点 | 验证方法 |
|---|---|
| A1 独立入口 | 出现“论文检索”Tab，关闭功能开关后入口消失，其他 Tab 正常 |
| A2 默认范围 | 新异步流程默认选中 USENIX Security 和最近五个完整年份；其他会议清晰标为尚未接入官网来源 |
| A3 会议配置回归 | 既有会议新增、修改、停用接口保持可用，但本轮新搜索对非USENIX会议返回明确未支持，不静默走旧路径 |
| A4 语义检索 | 标题查询与研究方向查询均能返回论文，结果严格按最终分数降序 |
| A5 主会过滤 | USENIX/DBLP样本排除Workshop、Poster、Demo等非主会论文，DBLP-only无官方摘要记录不展示 |
| A6 降级 | USENIX、DBLP或Reranker分别故障时保留缓存/其他来源结果并在对应来源卡说明原因 |
| A7 单篇导入 | 实际下载有效 PDF，以规范文件名保存并可在知识库检索 |
| A7b USENIX accepted 导入 | 从 USENIX Security accepted-papers 列表发现 accepted/prepublication 论文，优先下载 USENIX PDF；官方 PDF 不可用时，严格匹配 arXiv 版本并导入，候选保留 accepted/prepublication 状态 |
| A8 批量导入 | 多篇任务逐项显示状态，单项失败/等待登录不阻塞其他项，失败可重试 |
| A9 去重幂等 | 已导入结果显示状态，重复点击、并发提交不会生成第二份记录 |
| A10 ACM 登录 | 用户自行登录 ACM 后续传并在具有合法权限时成功导入，不泄露凭证 |
| A11 IEEE 登录 | 用户自行登录 IEEE 后续传并在具有合法权限时成功导入，不泄露凭证 |
| A12 命名兼容 | 非法字符、Unicode、超长与同名标题均安全处理，旧记录仍可重建/删除 |
| A13 安全异常 | 任意 URL、内网地址、伪 PDF、超大文件、无权限下载均被正确拒绝 |
| A14 排序质量 | 冻结不少于 12 条查询及人工标签；最终 nDCG@10 不低于初排且无灾难性退化 |
| A15 回归交付 | 全量测试、覆盖率门禁、实际启动、健康检查和完整检索导入链路均通过 |
| A16 增量目录 | 先同步 2022，再搜索 2022–2024；2022 明确显示缓存命中且不重复抓取，只获取 2023–2024 缺失单元 |
| A17 来源进度 | 点击检索后立即看到 USENIX 与 DBLP 两张独立状态卡，能够区分检查缓存、正在获取、完成、部分失败和降级 |
| A18 RAG 与分页 | 标题+摘要+官网关键词进入独立目录 collection；结果每页固定 10 条，下一页不触发重新检索且顺序不变 |
| A19 恢复与并发 | 两个请求不能重复领取同一抓取单元；服务中断及租约过期后可恢复，不留下永久 fetching 状态 |
| A20 复用审计 | 下载、安全、导入、批任务、身份和 BGE-M3 走既有实现；不存在未解释的第二套实现，搜索期间无 PDF 请求 |

## 产品使用步骤（PM 补充）

> 当前为架构师根据用户已确认交互写入的初稿。spec 确认后由产品经理独立复核并补充，不将本段视为已执行 PM 分派。

1. 用户打开“论文检索”Tab，选择 USENIX Security 和年份范围，输入研究方向后开始检索；接口立即返回任务，不要求等待所有来源完成。（A1、A2、A4）
2. 页面立即显示 USENIX 与 DBLP 两张来源卡片；每张卡片分别展示哪些年份/页面已缓存、哪些正在获取、已发现论文数和失败原因。（A16、A17）
3. 来源同步完成后，系统把官网标题、摘要及官网明确提供的关键词写入全局目录，DBLP 只补缺失书目信息，再按用户研究方向执行 RAG 召回。（A4、A18）
4. 用户先看到最相关的 10 篇论文；点击下一页读取同一次搜索冻结的后 10 篇，结果不重新抓取或重排。（A18）
5. 用户点击单篇“添加到知识库”后，系统才验证并下载 PDF；成功后可跳转知识库。（A7、A7b）
6. 用户勾选多篇批量导入，公开论文继续处理，需要登录的论文单独进入等待状态。（A8）
7. 用户对 ACM 或 IEEE 等待项打开受控浏览器，自行登录后返回并继续原任务；此能力不参与 USENIX 元数据检索。（A10、A11）
8. 已存在论文显示“已在知识库”，重复操作不会产生副本。（A9）
9. 来源部分失败时仍展示缓存或另一来源的可用结果，并在对应卡片显示原因；只有无来源且无缓存时才显示整体失败。（A6、A13、A17）
10. 后续搜索覆盖已同步年份时直接展示缓存命中，仅抓取缺少年份或当前年份发生变化的页面。（A16、A19）

## 执行配置（由架构师填写，落盘可查）

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | spec、接口与安全边界、编排和落地校验 |
| 产品经理 | `qwen3.5:9b`（本地 Ollama） | 32k | `Task(pm)` | 复核产品步骤、用户旅程和验收场景 |
| 开发主管 | `qwen3.8:27b-mlx`（本地 Ollama） | 32k | `Task(tech-lead)` | 需求/技术/验收评审、任务与合并裁决 |
| 初级开发 | `qwen3.8:27b-mlx`（本地 Ollama） | 32k | `Task(junior-dev)` | 按 task 小步实现；仅使用本地 Ollama 时每次最多 2 个代码文件、约 150 行，线上模型不受该数量限制 |
| 测试 | `qwen3.5:9b`（本地 Ollama） | 32k | `Task(tester)` | 接口、安全、排序质量、真实登录与回归验收 |

> 2026-09-05 已再次用 `ollama list` 实测 `qwen3.5:9b`、`qwen3.8:27b-mlx` 与 `bge-m3` 存在。业务 embedding 复用 `bge-m3`；业务 rerank 复用 spec-014 运行时，不把临时会话模型或角色模型写入业务配置。

## 任务计划

> 任务 01 = 本 spec 的编写，不单独建任务文件。任务 02 起一任务一文件；详细步骤只写在任务文件中。索引见 [`plans/015/README.md`](../plans/015/README.md)。

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-015 | 本文件 | — | 完成 |
| 02 | 验证数据源与浏览器桥接（Go/No-Go） | [`task-02-validate-baseline-and-sources.md`](../plans/015/task-02-validate-baseline-and-sources.md) | 01 | 条件放行（内置会议；Venue Search blocked） |
| 03 | 建立会议配置与论文召回 | [`task-03-conference-registry-and-retrieval.md`](../plans/015/task-03-conference-registry-and-retrieval.md) | 02（条件放行） | 已完成（内置会议与 OpenAlex 收窄范围） |
| 04 | 实现语义排序与 Reranker 集成 | [`task-04-semantic-ranking-and-rerank.md`](../plans/015/task-04-semantic-ranking-and-rerank.md) | 03，且 spec-014 可用 | 待执行 |
| 05 | 实现安全下载、规范命名与知识库导入 | [`task-05-secure-download-and-kb-import.md`](../plans/015/task-05-secure-download-and-kb-import.md) | 03 | 已完成（单篇下载与导入闭环） |
| 06 | 实现批量任务与登录续传 | [`task-06-batch-import-and-login-resume.md`](../plans/015/task-06-batch-import-and-login-resume.md) | 05 | 实施中（离线安全复核通过；真实登录环境阻塞） |
| 07 | 新增论文检索 Tab 与完整交互 | [`task-07-paper-discovery-tab.md`](../plans/015/task-07-paper-discovery-tab.md) | 03, 04, 05, 06 | 实施中（离线通过；A3/真实环境阻塞） |
| 08 | 执行测试、排序基准与安全回归 | [`task-08-tests-ranking-and-security.md`](../plans/015/task-08-tests-ranking-and-security.md) | 04, 05, 06, 07 | 实施中（离线安全/回归通过；排序质量与真实环境阻塞） |
| 09 | 评审、部署与复盘 | [`task-09-review-deploy-retro.md`](../plans/015/task-09-review-deploy-retro.md) | 08 | 实施中（离线回归与本地部署通过；外部验收阻塞） |
| 10 | 论文发现限界上下文目录重构 | [`task-10-paper-discovery-package-migration.md`](../plans/015/task-10-paper-discovery-package-migration.md) | 03, 05, 06, 07, 08 | 待确认 |
| 11 | USENIX accepted papers 与 arXiv 兜底来源 | [`task-11-usenix-accepted-and-arxiv-fallback.md`](../plans/015/task-11-usenix-accepted-and-arxiv-fallback.md) | 03, 05, 08 | 已完成 |
| 12 | USENIX 双 Skill 与跨 IDE 使用协议 | [`task-12-usenix-paper-skill.md`](../plans/015/task-12-usenix-paper-skill.md) | 11 | 已完成（下载版/目录版） |
| 13 | 固化全局目录协议与复用审计 | [`task-13-catalog-contract-and-reuse-audit.md`](../plans/015/task-13-catalog-contract-and-reuse-audit.md) | 03, 05, 11, 12 | 实施中（约 60%；`search_source_progress`、`search_results` 表与 `get_search_results_page()` 已落地，见 `reviews/015-task13-store-implementation.md`；协议固化与复用审计未收口） |
| 14 | 实现 USENIX 增量目录同步 | [`task-14-usenix-incremental-catalog.md`](../plans/015/task-14-usenix-incremental-catalog.md) | 13 | 已完成（USENIX 增量目录同步与 `/accepted` 只读端点已落地；按年份解析 slug 修复经 `reviews/015-backend-review.md` 评审，结论 WARNING） |
| 15 | 实现 LangGraph、目录 RAG 与冻结结果 | [`task-15-langgraph-catalog-rag.md`](../plans/015/task-15-langgraph-catalog-rag.md) | 14 | 待执行 |
| 16 | 实现来源进度与十条分页交互 | [`task-16-search-progress-and-pagination.md`](../plans/015/task-16-search-progress-and-pagination.md) | 15 | 待执行 |
| 17 | 执行复用审计、验收、部署与复盘 | [`task-17-review-acceptance-deploy-retro.md`](../plans/015/task-17-review-acceptance-deploy-retro.md) | 13, 14, 15, 16 | 待执行 |

## 评审记录

> 初始不引用尚未生成的评审文件，下游只认真实落盘文档。

- 原范围需求评审：[`docs/sdd/reviews/015-requirement-review.md`](../reviews/015-requirement-review.md)（结论：**通过**；历史证据保留）
- 原范围技术评审：[`docs/sdd/reviews/015-tech-review.md`](../reviews/015-tech-review.md)（结论：**通过**；历史证据保留）
- Task13–17 需求复审：[`docs/sdd/reviews/015-catalog-requirement-review.md`](../reviews/015-catalog-requirement-review.md)（结论：**通过**）
- Task13–17 技术复审与复用审计：[`docs/sdd/reviews/015-catalog-tech-review.md`](../reviews/015-catalog-tech-review.md)（结论：**通过**，附意见；继承 Task13 审计 C-1~C-6 / G-1~G-4）
- 验收评审（Task09）：[`docs/sdd/reviews/015-acceptance-review.md`](../reviews/015-acceptance-review.md)（结论：**整体验收不通过（阻塞）**；QA 已签字，开发主管（Tech Lead）**待签字**。该报告要求「阻塞解除并由 Tech Lead 签字前，Spec015 必须保持 `实施中`，不得标记 `已完成`」）
- Task14 slug 修复后端评审：[`docs/sdd/reviews/015-backend-review.md`](../reviews/015-backend-review.md)（结论：**WARNING**；1 项 HIGH：`_listing_for` 新正则路径无回归测试，列为下一提交强制项）

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 用户 | 提出新增安全顶会论文检索 Tab，按研究方向相关度排序并直接下载、规范命名后加入知识库 |
| 2026-09-03 | 用户 | 确定会议范围可配置、默认最近五年、支持单篇与批量导入，命名采用“年份-会议-标题” |
| 2026-09-03 | 用户 | 确定通过会议搜索新增来源，采用项目内 Playwright，并要求真实验收 ACM 与 IEEE 登录续传 |
| 2026-09-03 | 用户 | 要求等待 spec-013/014 稳定后再实施，并按 spec-014 格式落盘 spec 与全部详细 task；当前不执行 |
| 2026-09-03 | 架构师(自身) | 实测本地模型并创建本 spec、任务索引及任务 02–09，状态保持待确认/待执行 |
| 2026-09-04 | PM | 完成需求评审，结论通过；评审文件已落盘 |
| 2026-09-04 | Tech Lead | 技术评审打回，提出 T1–T13 安全、并发、一致性、模型与基线修订项；未进入业务代码 |
| 2026-09-04 | 架构师(自身) | 将 T1–T13 转为本 spec 与 Task 02–09 的实现级门禁，统一 Tech Lead 模型为 `qwen3.8:27b-mlx`；等待复审与用户确认 |
| 2026-09-04 | Tech Lead | 多轮复审后确认 Spec 015 设计约束基本通过；唯一硬阻塞为 Spec 014 Task 08/09、验收签字、联合部署和复盘尚未收口 |
| 2026-09-04 | 架构师(主会话) | 完成 Spec 014 全部收口（Task 08/09、tester 通过验收、Tech Lead 签字、复盘、状态与 README 统一为 `已完成`），并修复 `8c1c3ae` 引入的 `create_chat_model` 默认 `reasoning=True` 回归（`6daa498`），全量 `351 passed` |
| 2026-09-04 | 架构师(主会话) | 将 Spec 014 收口快进合并至 `main`（`e980cea` → `c17c7f4`）。Task 02 原定基线 `main@e980cea` **不含** `6daa498` 回归修复，按更安全的 `main@c17c7f4` 执行并记录偏差 |
| 2026-09-04 | Tech Lead | 第五次（T1 证据复核）技术复审：唯一放行动作全部完成，T1 关闭，结论由打回转**通过**，风险降为低 |
| 2026-09-04 | 用户 | 确认启动 Spec 015 开发 |
| 2026-09-04 | 架构师(主会话) | Spec 015 转 `实施中`；创建分支 `feature/spec-015-security-paper-discovery`，启动 Task 02 Go/No-Go |
| 2026-09-05 | 架构师(自身) | 根据用户反馈暂停实现，新增 `backend/app/paper_discovery/` 限界上下文目录重构方案；Spec015 退回 `待确认`，等待架构变更确认 |
| 2026-09-04 | 用户 | 明确要求跳过 Spec013/014 基线核对与 Reranker 模型判断，优先执行 DBLP/OpenAlex 数据源和 Playwright 浏览器桥接验证 |
| 2026-09-04 | tester / tech-lead | Task02 条件放行内置会议 publication search + OpenAlex 补全；DBLP Venue Search/自定义会议新增保持 blocked；启动 Task03 收窄实现 |
| 2026-09-04 | tester / tech-lead | Task03 内置会议召回、OpenAlex 补全、SQLite 持久化及 API 验收通过，最终技术签核通过；定向测试 41 passed。Venue Search/custom conference blocked，导入 FK/TTL 移交 Task05 |
| 2026-09-04 | tester / Tech Lead | Task05 安全修复复验与签核通过：定向回归 150 passed，修复项精确回归 11 passed，并发幂等 10/10 轮；批量与登录续传移交 Task06 |
| 2026-09-05 | 用户 | 提出补充 USENIX Security accepted-papers 官网检索，并以 USENIX PDF、prepublication PDF 和 arXiv 作为第二下载途径；明确先试点 USENIX，再扩展其他会议 |
| 2026-09-05 | 架构师（自身） | 调研 USENIX accepted 列表/详情页媒体链接与 arXiv 官方 API，补充 `publication_scope`、来源路由、accepted/prepublication 状态和严格 arXiv 匹配设计；新增 Task11–12，等待用户确认 |
| 2026-09-05 | 用户 | 确认按补充后的 Spec015 执行；Task11/12 进入实现 |
| 2026-09-05 | 架构师（自身） | Task11 完成 USENIX/arXiv 来源、候选字段、SQLite 路线配置、搜索/API 接线及安全修订；Task12 创建项目级下载版/目录版 Skill 与 CodeBuddy 适配器 |
| 2026-09-05 | 用户 | 将检索流程调整为 USENIX 官网优先、DBLP 辅助、增量目录缓存、LangGraph 并行编排、RAG 召回、来源进度卡片和每页 10 篇；要求先完整落盘文档，后续执行另行安排 |
| 2026-09-05 | 架构师（自身） | 根据真实代码盘点新增“现有实现复用与替换边界”，固定原样复用、参数化复用、必须替换和禁止重复开发的模块；新增 Task13–17，状态退回待确认并暂停代码实现 |
| 2026-09-04 | tester / Tech Lead | Task05 安全修复复验与签核通过：定向回归 150 passed，修复项精确回归 11 passed，并发幂等 10/10 轮；批量与登录续传移交 Task06 |
| 2026-09-06 | 架构师（自身） | Task13 部分落地（`search_source_progress`、`search_results` 表与 `get_search_results_page()`）、Task14 落地（USENIX 增量目录同步与 `/accepted` 只读端点）；本次收口时回填任务表状态，修正「代码已落地但任务表仍写待执行」的长期脱节 |
| 2026-09-06 | 架构师（自身，主会话代行） | USENIX slug 按年份解析修复的后端评审落盘 `reviews/015-backend-review.md`，结论 WARNING；1 项 HIGH：`_listing_for` 新正则路径无回归测试，列为下一提交强制项 |
| 2026-09-06 | 架构师（自身） | 复盘 Task15–17 从未分派（`retro/2026-09-06-spec015-task15-16-not-dispatched.md`），确立任务链推进、状态与代码同批提交、已确认 spec 优先、交接检查点四条规则；用户确定顺序：先 017 后端重构 → 全量回归 → 再 015 Task15/16 |
| 2026-09-07 | 架构师（自身） | 收口核对：验收报告结论为「不通过（阻塞）」且 Tech Lead 未签字，Task15–17 未实现，故**状态保持 `实施中`**；回填评审记录为真实结论（消除「待评审（未执行）」占位）并同步 changelog |
| 2026-09-07 | 架构师（自身） | 引入 ruff（`ruff.toml` + `requirements-dev.txt`，显式固定 select 因 ruff 0.16 默认规则集过宽）；导入排序修复 58 处、删除确认无引用的死导入 18 处，全量回归 626 passed 无回归 |

---
**六条自检**：①边界均可转为测试；②spec 说明需求、task 承载实施细节；③task 链接真实且依赖无环；④明确不做已划死范围；⑤执行配置五行齐全；⑥产品步骤可映射 A1–A15。
**收口自检**：见 `docs/sdd/SDD-GATE-CHECKLIST.md` §3；三份评审、验收签字、changelog、复盘、运行时部署全部完成后才能转 `已完成`。
