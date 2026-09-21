# Semantic Scholar 论文下载回退调研

> 调研范围：Spec032 Task14。本文检查现有下载链、来源注册、Skill/Tool 契约和测试，并核对 Semantic Scholar 官方公开资料；代码接入与验证结果记录在文末。

## 结论摘要

Semantic Scholar 适合作为“论文已被目录来源识别、官方 PDF 不可用时的受控开放获取回退来源”，不适合作为未经核验的任意 URL 下载器。

推荐接入顺序：

1. 现有官方/会议 PDF 链路；
2. 已有 arXiv 严格匹配回退；
3. Semantic Scholar Academic Graph API 通过 DOI 或 arXiv ID 查找论文；
4. 仅当 API 返回 `openAccessPdf.url`，且该 URL 经过既有 URL、DNS、重定向、PDF 魔数、大小和页数校验后，才交给现有导入链；
5. API 无开放 PDF、返回 401/403/429、匹配不确定或下载内容不是 PDF 时，保留结构化失败状态，转人工处理，不绕过登录、付费墙或验证码。

Semantic Scholar 页面和 Reader 页面可以作为用户人工核验入口，但不应作为后端主链路的 HTML 抓取协议。后端应使用 Academic Graph API 的结构化字段，并把 API 返回的 OA URL 当作“候选链接”，而不是信任决策。

## 外部资料核验

核验日期：2026-09-21。

官方资料：

- Academic Graph API 文档：<https://api.semanticscholar.org/api-docs>
- API 示例/字段说明：<https://api.semanticscholar.org/api-docs/snippets>
- 官方 API 教程：<https://www.semanticscholar.org/product/api/tutorial>
- API 产品说明：<https://www.semanticscholar.org/product/api>
- 用户提供的论文：<https://arxiv.org/abs/2403.11445>

官方文档明确支持：

- `GET /graph/v1/paper/autocomplete?query=...` 只用于交互式标题补全，返回最小候选（论文 ID、标题、作者/年份摘要）；查询文本最多取前 100 个字符。它不能替代会议目录检索，也不返回完整摘要、关键词或 PDF。
- `GET /graph/v1/paper/{paper_id}`，其中 `paper_id` 可使用 Semantic Scholar `paperId`、`CorpusId:<id>`、DOI 或 `ARXIV:<id>`等受支持的论文标识；实现优先使用服务端已有 DOI 或 arXiv ID，避免标题搜索误匹配。
- `GET /graph/v1/paper/search`，可返回相关度排序结果；可用 `year`、`publicationDateOrYear`、`openAccessPdf` 等过滤项。搜索最多返回 1000 个相关度结果，因此不能把它当作无限量目录。
- `GET /graph/v1/paper/search/bulk`，适合批量候选检索，支持年份、发表日期、venue、开放 PDF、引用数、出版类型、排序和 continuation token；应优先于资源消耗更高的 relevance search。
- `POST /recommendations/v1/papers`，可根据一个或多个正/负样本推荐相关论文；`/citations` 与 `/references` 可用于构建引用关系和研究覆盖补搜。
- `POST /graph/v1/paper/batch` 可批量补齐多个论文的详情字段；大规模长期同步才考虑 Datasets API，不纳入当前在线 Worker 主链路。
- `fields` 控制返回字段。对本项目有用的字段是 `paperId,title,abstract,authors,year,venue,publicationDate,publicationTypes,url,openAccessPdf,externalIds`。`openAccessPdf`通常包含 `url` 和 `status`；没有公开 PDF 时为 `null`。
- 大多数 Academic Graph API 端点可免 API key 使用，但仍受共享速率限制；官方建议有 key 时通过大小写敏感的 `x-api-key` header 传递。API key 不得写入候选、日志、Skill 或前端。
- API 可能返回 429；调用方应使用有限次数、指数退避和明确的 `retryable` 状态，不能无限重试。

### 用户给出的样本

arXiv 页面确认 `2403.11445` 的标题为 **Budget Recycling Differential Privacy**，页面提供公开 PDF；这是一条可用于现有 arXiv 回退链的强证据。

用户给出的 Semantic Scholar Reader 地址：

`https://www.semanticscholar.org/reader/42d506a59ab6db2b115449ce5520331c01ad8378`

以及对应 paper 页面中的可见标题是 **Noise-Augmented Privacy-Preserving Empirical Risk Minimization with Dual-purpose Regularizer and Privacy Budget Retrieval and Recycling**，与 `Budget Recycling Differential Privacy` 不是同一标题。实现不能把该 hash 作为目标论文的固定 ID；应通过 DOI 或 `ARXIV:2403.11445` 查找并再次核对标题、作者、年份。

本环境直接访问 `api.semanticscholar.org` 时 DNS 无法解析，未伪造 API 成功响应。网页/API 结构和字段结论来自上述官方文档；真实运行时仍需在部署环境执行一次受控 API probe。

## 当前代码资产与可复用边界

### 已有统一下载/导入链

现有 `backend/app/paper_discovery/infrastructure/paper_download.py` 已负责：

- 固定 host allowlist 后的 URL 校验；
- DNS/peer IP 与逐跳重定向校验；
- 连接、读取、总超时；
- 响应头、文件大小、PDF 魔数、Content-Type、页数和临时文件清理；
- 稳定错误码：`DOWNLOAD_BLOCKED`、`DOWNLOAD_TIMEOUT`、`LOGIN_REQUIRED`、`PDF_NOT_FOUND`、`INVALID_PDF` 等。

Semantic Scholar 不应新增下载器，`openAccessPdf.url` 只能转换为现有 `candidate.pdf_url` 后调用该链。

### 已有来源注册与 Worker Tool

- `backend/app/paper_discovery/infrastructure/source_registry.py` 是来源和固定主机的权威注册表。
- `builtin_allowed_hosts()` 当前对未知来源 fail-closed；已有 arXiv fallback 主机声明。
- `backend/app/paper_discovery/application/worker_tool.py` 提供统一 `discover/import` envelope、候选来源一致性校验、固定 allowlist 和结构化错误。
- `backend/app/paper_discovery/domain/source_contract.py` 提供统一 `SourceResult` / `ImportResult`，应继续复用，不能为 Semantic Scholar 创建另一套返回格式。
- 当前候选模型已经有 `doi`、`arxiv_id`、`article_url`、`pdf_url`、`source_links`、`source_kind` 等字段；优先补这些字段的 provenance，而不是改变现有论文身份模型。

### 已有 Skill 边界

- `.agents/skills/usenix-download-orchestration/SKILL.md` 已规定官方 PDF → prepublication PDF → 严格匹配 arXiv，并要求工具执行 URL/PDF 校验。
- `.agents/skills/usenix-accepted-papers/SKILL.md` 是 legacy 兼容文档，不应再发展成第二套下载协议。
- Semantic Scholar 最适合补充为下载编排层的 OA 回退决策，执行仍由 `download_and_import_paper` / `paper_discovery` Tool 负责。

## 推荐的最小接入设计

### 1. 角色定位

建议新增一个内部受控的 `semantic_scholar` lookup/fallback adapter，定位为“元数据查找 + OA 候选链接发现”，而不是新的论文主目录。

- 不把 Semantic Scholar 作为官方会议字段权威来源；
- 不覆盖官方标题、摘要、关键词、作者、会议年份；
- 只在缺失 PDF 或既有下载失败后查找 OA PDF；
- 只把 `openAccessPdf.url` 作为候选下载地址；
- API 的 `url`（Semantic Scholar paper 页面）只保存为 provenance/article page，不直接当 PDF；
- `openAccessPdf.status` 记录为可解释的 OA 证据，例如 `GOLD`、`GREEN` 等，但不替代实际 PDF 校验。

### 2. 查询优先级

使用固定标识符，优先级如下：

1. `ARXIV:<arxiv_id>`（已有候选有 arXiv ID 时）；
2. `DOI:<normalized_doi>`（已有 DOI 时）；
3. 只有两者都缺失时才使用标题 + 作者 + 年份搜索，并要求严格匹配；
4. 若候选来自 IEEE/ACM/NDSS 等会议，应先以原候选的 DOI、标题、作者和年份核对 S2 结果，不能只按相似标题接受。

搜索结果应限制数量（例如最多 5 或 10），并采用：

- 标题规范化后的相似度达到现有身份匹配阈值；
- 作者集合有足够交集；
- 年份一致或满足明确的预印本偏差规则；
- DOI/arXiv ID一致时才视为强匹配；
- 不能证明匹配时返回 `SEMANTIC_SCHOLAR_MATCH_UNCERTAIN`，不下载、不导入。

### 3. 统一候选字段映射

建议将 API 响应映射到现有候选快照，字段如下：

| Semantic Scholar | 现有候选字段 | 处理规则 |
|---|---|---|
| `paperId` | `source_links` / provenance | 保存为外部证据 ID，不替换 DOI/arXiv 主身份 |
| `title` | `title` | 仅用于匹配核验；官方字段非空时不得覆盖 |
| `abstract` | `abstract` | 只在目标字段缺失时补缺，并记录来源 |
| `authors[].name` | `authors` | 只用于匹配或补缺 |
| `year` / `publicationDate` | `year` | 用于匹配，不擅自改变会议年份 |
| `externalIds.DOI` | `doi` | 规范化后核对已有 DOI |
| `externalIds.ArXiv` | `arxiv_id` | 规范化后核对已有 arXiv ID |
| `url` | `article_url` / source link | 只作 Semantic Scholar 证据页，不下载 |
| `openAccessPdf.url` | `pdf_url`（回退候选） | 仍须通过固定 host allowlist 和下载安全链 |
| `openAccessPdf.status` | provenance / `pdf_access` | 记录 OA 声明，不等于下载成功 |

### 4. 固定 host 与安全

最小设计不应直接把 `semanticscholar.org` 加入 PDF 下载 host allowlist，因为 Semantic Scholar API 返回的 `openAccessPdf.url` 很可能指向 arXiv、机构仓储或出版社，真正需要允许的是已注册且安全审查过的目标 host。

推荐两级处理：

- API 请求固定到 `api.semanticscholar.org`，作为元数据 API host；
- API 返回的 PDF host 不从响应动态加入 allowlist。使用一份服务端固定的“受支持开放来源 host 注册表”（至少已有 `arxiv.org` / `export.arxiv.org`；之后按实际来源逐个登记），未知 host 返回 `SEMANTIC_SCHOLAR_UNSUPPORTED_PDF_HOST`，交人工处理。

这样既支持 Semantic Scholar 帮忙发现 arXiv PDF，也不会把任意第三方 URL 变成可信下载来源。

### 5. 统一错误码建议

- `SEMANTIC_SCHOLAR_UNAVAILABLE`：DNS、连接或 5xx；可重试；
- `SEMANTIC_SCHOLAR_RATE_LIMITED`：429；可重试，带退避；
- `SEMANTIC_SCHOLAR_AUTH_FAILED`：API key 无效；不可由 Worker 猜测修复；
- `SEMANTIC_SCHOLAR_NOT_FOUND`：按 DOI/arXiv ID无结果；可转下一回退；
- `SEMANTIC_SCHOLAR_MATCH_UNCERTAIN`：找到候选但身份未达阈值；不可自动导入；
- `SEMANTIC_SCHOLAR_NO_OPEN_PDF`：无 `openAccessPdf.url`；可转人工下载；
- `SEMANTIC_SCHOLAR_UNSUPPORTED_PDF_HOST`：OA URL host 未登记；转人工或后续配置；
- `SEMANTIC_SCHOLAR_PDF_FAILED`：已进入现有下载器但下载/校验失败；保留底层稳定错误码和候选 ID。

## API key 与限流建议

- v1 可以先支持无 key 请求进行低频单篇回退；不要把“免 key 可用”当作稳定 SLA。
- 若配置 key，应只从服务端环境变量读取，例如 `SEMANTIC_SCHOLAR_API_KEY`，仅通过 `x-api-key` header 发送。
- 不把 key 写进 `.env.example` 的真实值、候选 JSON、事件、进度消息或 Skill Prompt；日志只记录是否配置，不记录 key。
- 统一客户端应设置 connect/read/total timeout、单次请求字段白名单、有限重试和指数退避；429 和网络错误才可重试，401/403/匹配不确定不得盲目重试。
- API 搜索/详情结果应做短 TTL 缓存，避免重复查同一 DOI/arXiv ID；缓存属于元数据缓存，不等价于 PDF 已下载。

### 本次限流修订

`paper_import` 的回退入口会按候选创建适配器实例；如果把计时器放在实例内，连续导入会重置计时器并突破 API key 的 1 RPS 配额。现已改为：

- `SemanticScholarRequestLimiter` 作为进程内共享限流器，所有适配器实例和重试请求共用同一个 1 秒窗口；
- 429、网络错误等重试也必须重新取得限流槽位；
- 生产部署继续保持单 Uvicorn worker（项目本地 Qdrant 也要求单进程），因此进程内共享限流器覆盖当前部署模型；
- 多进程或多机器部署时，必须把该限流器迁移到共享队列/SQLite 租约，再提高并发，不能简单增加 Worker 数量；
- 定向测试覆盖“两个独立适配器实例连续调用仍等待 1 秒”的场景。

## 需要补充的测试

新增测试文件应按功能命名，放到 `tests/paper_discovery/` 或 `tests/integration/`，不能放在 `tests/` 根目录，也不能在文件名中使用 spec/task 编号。

最低测试集：

1. DOI/arXiv ID 查询参数构造不接受用户任意 URL；
2. API 响应字段解析：完整字段、缺少 `abstract`、`openAccessPdf=null`、缺少作者和 malformed payload；
3. 标题/作者/年份严格匹配；不匹配返回 `SEMANTIC_SCHOLAR_MATCH_UNCERTAIN`；
4. 429、401、403、404、5xx 和 DNS/超时映射为稳定错误码；
5. API 返回 arXiv PDF 时，复用既有 arXiv host allowlist 并进入既有下载器；
6. API 返回未知机构/出版社 host 时拒绝，不动态扩展 allowlist；
7. 重定向到未知 host、HTML 登录页、伪造 `%PDF-`、超大 PDF 和加密 PDF均复用既有失败语义；
8. 成功下载后仍复用既有去重、身份、索引和补偿；
9. 不存在 API key 时仍能低频工作；配置 key 时只验证 header 是否注入，不把值写入日志；
10. 现有 USENIX/IEEE/ACM/NDSS/arXiv 下载链回归不受影响。

## 实现建议与范围控制

建议分成两个最小 Task，避免重写 Spec032 当前框架：

- Task A：Semantic Scholar 元数据/OA 查找适配器和统一错误/重试契约；只读 API，不下载、不导入。
- Task B：将该适配器接入现有下载编排的最后回退；只复用现有 `paper_download.py`、`paper_import.py`、Worker Tool 和 source host registry。

本轮不建议：

- 抓取 Semantic Scholar 搜索页或 Reader 页面 HTML；
- 直接把所有 `openAccessPdf.url` host 加入白名单；
- 新建第二套 PDF 下载器、PDF 校验器、导入器或索引器；
- 将 Semantic Scholar 作为官方会议目录或官方字段权威；
- 批量下载 Semantic Scholar 数据集；
- 在 API 失败时自动改用未登记的任意第三方链接。

## 当前阻塞与用户可提供的人工途径

本次只读调研环境无法解析 `api.semanticscholar.org`，因此未执行真实 Semantic Scholar API 下载成功验证。用户提供的 arXiv 页面已经足够作为该论文的合法开放获取入口：

`https://arxiv.org/pdf/2403.11445`

如果后续真实下载链仍无法访问 IEEE 官方链接，可以先使用该 arXiv PDF 作为人工确认的下载途径。若 Semantic Scholar 页面显示了另一个可下载的 OA PDF，用户可提供页面中实际的 PDF 来源或下载后的本地 PDF；系统仍需经过既有 PDF 安全校验和导入，不接受把用户提供的 URL 直接加入服务端信任列表。

## 建议的下一步

1. 先用 `ARXIV:2403.11445` 在部署环境做一次 API probe，记录字段和 `openAccessPdf`，不依赖用户给出的 Reader hash。
2. 为 Semantic Scholar 建立只读 adapter，接入 `SourceResult`/`ImportResult` 统一 envelope。
3. 先只支持 DOI/arXiv ID查询；标题搜索作为后续补充并严格标记不确定匹配。
4. 仅允许已登记开放来源 host；首个可验证路径为 Semantic Scholar → arXiv → 现有安全下载/导入链。
5. API probe、下载、导入和重启后的状态都成功后，再让用户进行人工验收。

## 最小接入结果（2026-09-21）

本轮已按上述边界完成代码接入：

- `backend/app/paper_discovery/infrastructure/semantic_scholar_adapter.py` 提供统一的
  DOI/ArXiv ID 查询、字段解析、标题/作者/年份核对、有限退避、API key header 注入和
  稳定错误码；不实现下载。
- 既有 `paper_import.import_candidate` 在主下载失败后调用该适配器；只有返回的 OA URL
  命中既有固定 host（含已登记的 arXiv fallback）才替换 `pdf_url` 并再次进入同一导入
  函数。Worker Tool 和直接 `download_and_import_paper` 入口因此共享同一回退，不会出现
  两套实现。PDF 安全校验、去重、索引和补偿没有复制。
- `.agents/skills/semantic-scholar-download-orchestration/SKILL.md` 固化了顺序、输入、
  安全和失败语义；USENIX 下载 Skill 已把 Semantic Scholar 放在 arXiv 之后。
- 定向验证：`tests/paper_discovery/test_semantic_scholar_adapter.py`、
  `tests/paper_discovery/test_semantic_scholar_import_fallback.py` 与
  `tests/skills/test_paper_worker_tools.py` 共 12 项通过；ruff/compileall 通过。

当前仍未宣称真实外部成功：本环境访问 `api.semanticscholar.org` DNS 失败。部署环境需
用 `ARXIV:2403.11445` 或已知 DOI 进行一次 API probe；失败时应显示稳定错误并保留人工
下载/上传入口，而不是伪造导入成功。
