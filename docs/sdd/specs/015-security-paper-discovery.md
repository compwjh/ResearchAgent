# Spec 015 — 安全顶会论文检索与知识库导入

## 状态

**当前状态：`待确认`（2026-09-03）**

> 本轮只完成 spec 与任务计划落盘，不执行任务、不修改业务代码。进入实施前必须等待 spec-013、spec-014 完成并形成明确稳定基线；不得通过回滚、stash、清理或覆盖工作树损坏现有未提交成果。
> 状态变更须同步追加 `docs/sdd/spec-status-changelog.md`。

## 一句话目标

新增独立“论文检索”Tab，让用户按研究方向检索安全四大顶会或自行添加的会议论文，结果按语义相关程度降序展示，并支持单篇或批量实际下载 PDF、按“年份-会议-标题”规范命名后直接导入个人知识库。

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

## 回滚点（Rollback Baseline）

| 项 | 值 |
|---|---|
| 基线 commit | 待 spec-013、spec-014 完成并形成稳定提交后回填 |
| 目标分支 | `feature/spec-015-security-paper-discovery` |
| 完整关闭 | `PAPER_DISCOVERY_ENABLED=false`，隐藏 Tab 并关闭新增 API |
| 运行时降级 | OpenAlex 或 Reranker 异常时返回可用的降级结果；Playwright 异常不影响公开 PDF |
| 数据回滚 | 不删除已成功导入的知识库论文；新增元数据字段保持向后兼容 |

> 创建分支前必须记录当前 commit、工作树状态和 spec-013/014 验收结果。禁止 `git reset --hard`、`git clean`、`git stash`、覆盖式 checkout 或批量复制。

## 数据模型与配置

### 配置项

| 配置 | 类型 | 默认值 | 约束 |
|---|---|---|---|
| `PAPER_DISCOVERY_ENABLED` | bool | `true` | `false` 时不展示入口，不执行检索或导入 |
| `PAPER_DISCOVERY_DB_PATH` | str | `data/paper_search/state.sqlite3` | 保存会议配置、搜索会话与导入状态 |
| `PAPER_DISCOVERY_DEFAULT_YEARS` | int | `5` | 最近五个完整发表年份 |
| `PAPER_DISCOVERY_SEARCH_LIMIT` | int | `20` | 默认返回数量 |
| `PAPER_DISCOVERY_MAX_SEARCH_LIMIT` | int | `100` | 单次硬上限 |
| `PAPER_DISCOVERY_CANDIDATE_POOL` | int | `200` | rerank 前候选上限 |
| `PAPER_DISCOVERY_BATCH_LIMIT` | int | `20` | 单次批量导入上限 |
| `PAPER_DISCOVERY_SEARCH_TTL_SECONDS` | int | `86400` | 搜索候选有效期 |
| `PAPER_DISCOVERY_REQUEST_TIMEOUT_SECONDS` | float | `20` | 单个外部源请求超时 |
| `PAPER_DISCOVERY_BROWSER_PROFILE_DIR` | str | `data/browser-profile/security-papers` | Playwright 本地会话目录，不进 Git |
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

内置会议为 CCS、USENIX Security、IEEE S&P、NDSS。用户可搜索并新增会议；内置会议只能停用，不能删除。

### 搜索候选 `PaperCandidate`

| 字段 | 类型 | 含义 |
|---|---|---|
| `search_id` / `candidate_id` | str | 搜索会话与服务端候选标识 |
| `dblp_key` | str / null | DBLP 记录标识 |
| `title` / `authors` / `year` | str / list / int | 基础元数据 |
| `conference_id` / `conference_name` | str | 会议标识与简称 |
| `doi` / `abstract` | str / null | DOI 与摘要 |
| `article_url` / `pdf_url` | str / null | 详情页和已解析 PDF 地址 |
| `pdf_access` | enum | `public` / `login_required` / `unavailable` / `unknown` |
| `retrieval_score` | float | 初排分数 |
| `rerank_score` | float / null | spec-014 返回的分数 |
| `final_score` / `rank` | float / int | 最终分数与名次 |
| `existing_paper_id` | str / null | 已在知识库时的论文标识 |

### 导入任务

`PaperImportBatch` 保存 `batch_id`、`search_id`、状态、总数、成功数、失败数、等待登录数和时间戳。状态为 `queued/running/waiting_login/partial_success/completed/failed/cancelled`。

`PaperImportItem` 保存 `item_id`、`batch_id`、`candidate_id`、状态、规范文件名、`paper_id`、稳定错误码、错误说明、尝试次数和时间戳。状态为 `queued/downloading/waiting_login/validating/indexing/completed/failed`。

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
| `POST /api/papers/search` | 查询、会议、年份、limit | `search_id`、降序候选、降级信息 | 所有召回源失败才整体失败 |
| `POST /api/papers/imports` | `search_id`、候选 id 列表 | 批次和逐项状态 | 拒绝过期或伪造候选 |
| `GET /api/papers/imports/{batch_id}` | — | 批次进度与逐项结果 | 不存在返回 404 |
| `POST /api/papers/imports/{batch_id}/retry` | — | 重试后的任务状态 | 已成功项不重复执行 |
| `GET /api/papers/browser/health` | — | Playwright 和支持站点状态 | 不返回 Cookie 或登录内容 |
| `POST /api/papers/imports/{item_id}/login` | — | 打开受控登录会话 | 浏览器不可用返回稳定错误 |
| `POST /api/papers/imports/{item_id}/resume` | — | 续传后的任务状态 | 未登录或无权限保持可重试失败 |

### 检索顺序

1. 校验查询、年份和会议；用本地查询模型生成有限的检索关键词与同义表达。
2. 使用 DBLP 按会议流和年份召回，并按别名与类型严格过滤主会论文。
3. 使用 DOI、DBLP key、规范化标题合并重复记录。
4. 通过 OpenAlex 补充摘要、开放获取状态与 PDF 地址。
5. 以标题、摘要、查询词、会议和年份计算初排，只取候选池上限。
6. 调用 spec-014 批量 rerank，按最终分数降序；同分使用初排顺序、年份、标题做稳定排序。
7. Reranker 失败时保留初排并返回明确降级标志，不阻断搜索。

### 导入顺序

1. 只从服务端搜索会话读取候选，拒绝客户端自带下载 URL。
2. 下载前以 DOI、DBLP key、标题组合键检查重复。
3. 优先使用公开 PDF；否则解析出版商页面；需要登录时进入 `waiting_login`，不阻塞批次其他项。
4. 下载至临时文件，校验 HTTPS、重定向目标、大小、PDF 魔数和可读取页数。
5. 生成规范文件名，再调用统一知识库导入服务。
6. 写入前再次去重，完成 PDF 保存、元数据落盘和现有索引流程。
7. 成功后删除临时文件并返回 `paper_id`；失败记录稳定错误码并允许重试。

## 边界（每条之后会变成一条测试）

- 查询去除空白后不能为空，最长 500 字符；至少选择一个已启用会议。
- 年份范围必须合法且不超过配置上限；默认取最近五个完整年份。
- DBLP 或 OpenAlex 单源失败时尽量返回可用结果并标记降级；全部召回失败才整体失败。
- Workshop、Poster、Demo、Tutorial、Doctoral Consortium 不得混入主会结果。
- DOI、DBLP key 或规范标题相同的论文只展示一次。
- 搜索会话过期后不得继续导入；客户端不得提交任意 URL。
- 单次批量最多 20 篇；一项失败或等待登录不阻塞其他项。
- 服务重启后运行中的任务恢复为可重试状态，不永久停在 `running`。
- 下载前和写入前均去重；重复点击不得创建第二份有效论文。
- 只允许 HTTPS；每次重定向后重新校验目标，禁止 loopback、内网、链路本地、本地文件协议和非 HTTP(S) 协议。
- 非 PDF、伪 PDF、超限文件或不可读取 PDF 不得进入知识库。
- 文件名不得为空、逃逸目录或覆盖不同论文。
- 登录由用户在真实浏览器完成；密码、Cookie、Authorization 和 profile 内容不得进入日志、API 或 Git。
- Playwright 不可用时公开 PDF 仍可检索和导入；spec-014 不可用时降级初排。
- 知识库 v1 同步与 v2 异步流程均返回真实状态；旧记录仍可列出、重建和删除。
- 用户离开 Tab 后导入继续运行；重复提交采用幂等键防重。
- 日志只记录阶段、域名、任务标识、耗时和错误码，不记录完整查询、摘要、URL 查询参数或认证信息。

## 明确不做（划出范围，防 AI 自由发挥）

- 不抓取 Google Scholar，不默认检索所有安全会议。
- 不把 Workshop、Poster、Demo 或 Tutorial 当主会论文。
- 不下载补充材料、数据集、代码仓库或视频。
- 不发起第三方文献互助，不绕过验证码、付费墙、机构授权或出版商访问控制。
- 不收集用户密码，不把 Cookie、profile 或搜索历史上传云端。
- 不新增云端向量库、云端 embedding 或另一套 Reranker。
- 不重做现有聊天页文章下载流程，只允许抽取共用安全下载能力。
- 不实现引用网络、作者画像、订阅提醒或自动追踪新论文。
- 不自动删除已导入知识库的论文。
- 不在 spec-013、spec-014 稳定基线前开始实现，不通过回滚或清理保护现场。

## 评审强制约束（实现必须遵守）

> 当前尚未执行需求/技术评审。评审完成后，将真实通过意见固化到本节并同步受影响 task；在此之前以下为架构约束。

- 以 DBLP 为主召回，OpenAlex 做摘要、OA 与 PDF 补全；会议配置必须保存经验证的 stream 与主会别名。
- 导入接口只接受服务端生成的候选标识；下载链路必须防 SSRF 并逐次校验重定向。
- 排序必须组合语义初排与 spec-014 rerank，禁止只用标题字符串相似度；降级不得伪造 rerank 分数。
- 下载、校验、命名、元数据和知识库索引形成统一任务状态；索引失败不得显示成功。
- `paper_id` 是唯一身份；可读文件名不得破坏旧 `{paper_id}.pdf` 记录兼容性。
- 去重在下载前、写入前各执行一次；批量任务必须持久化、逐项隔离、幂等和可重试。
- 登录续传使用本地 Playwright profile；ACM Digital Library、IEEE Xplore 均需合法账户下真实验收。
- spec-013 观测覆盖召回、补全、rerank、下载、登录等待、校验和索引，且不记录敏感内容。
- 排序质量采用首次查看最终排名前冻结的标注集，不允许验收时删题或修改标签。
- 所有代码实现先分派 `junior-dev`；每次最多 2 文件、150 行；评审与验收由规定角色真实执行。

## 验收方式

| 验收点 | 验证方法 |
|---|---|
| A1 独立入口 | 出现“论文检索”Tab，关闭功能开关后入口消失，其他 Tab 正常 |
| A2 默认范围 | 默认选中 CCS、USENIX Security、IEEE S&P、NDSS 和最近五个完整年份 |
| A3 自定义会议 | 能搜索 DBLP 会议并新增、修改、停用；内置会议不可删除 |
| A4 语义检索 | 标题查询与研究方向查询均能返回论文，结果严格按最终分数降序 |
| A5 主会过滤 | 四个默认会议的样本均排除 Workshop、Poster、Demo 等记录 |
| A6 降级 | OpenAlex、Reranker 或 Playwright 分别故障时保留仍可用的能力并显示原因 |
| A7 单篇导入 | 实际下载有效 PDF，以规范文件名保存并可在知识库检索 |
| A8 批量导入 | 多篇任务逐项显示状态，单项失败/等待登录不阻塞其他项，失败可重试 |
| A9 去重幂等 | 已导入结果显示状态，重复点击、并发提交不会生成第二份记录 |
| A10 ACM 登录 | 用户自行登录 ACM 后续传并在具有合法权限时成功导入，不泄露凭证 |
| A11 IEEE 登录 | 用户自行登录 IEEE 后续传并在具有合法权限时成功导入，不泄露凭证 |
| A12 命名兼容 | 非法字符、Unicode、超长与同名标题均安全处理，旧记录仍可重建/删除 |
| A13 安全异常 | 任意 URL、内网地址、伪 PDF、超大文件、无权限下载均被正确拒绝 |
| A14 排序质量 | 冻结不少于 12 条查询及人工标签；最终 nDCG@10 不低于初排且无灾难性退化 |
| A15 回归交付 | 全量测试、覆盖率门禁、实际启动、健康检查和完整检索导入链路均通过 |

## 产品使用步骤（PM 补充）

> 当前为架构师根据用户已确认交互写入的初稿。spec 确认后由产品经理独立复核并补充，不将本段视为已执行 PM 分派。

1. 用户打开“论文检索”Tab，输入研究方向，确认默认四大顶会和最近五年范围后搜索。（A1、A2、A4）
2. 用户查看按相关程度排列的标题、作者、年份、会议、摘要和 PDF 状态，并可调整会议或年份重新搜索。（A4、A5）
3. 用户在会议设置中搜索 DBLP 会议、选中候选并保存为自定义会议。（A3）
4. 用户点击单篇“添加到知识库”，看到下载、校验、索引进度；成功后可跳转知识库。（A7）
5. 用户勾选多篇批量导入，公开论文继续处理，需要登录的论文单独进入等待状态。（A8）
6. 用户对 ACM 或 IEEE 等待项打开受控浏览器，自行登录后返回并继续原任务。（A10、A11）
7. 已存在论文显示“已在知识库”，重复操作不会产生副本。（A9）
8. 无 PDF、无权限、PDF 无效或服务降级时，页面显示可理解原因及可执行的重试/登录动作。（A6、A13）

## 执行配置（由架构师填写，落盘可查）

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | spec、接口与安全边界、编排和落地校验 |
| 产品经理 | `qwen3.5:9b`（本地 Ollama） | 32k | `Task(pm)` | 复核产品步骤、用户旅程和验收场景 |
| 开发主管 | `qwen3.8:27b`（本地 Ollama） | 32k | `Task(tech-lead)` | 需求/技术/验收评审、任务与合并裁决 |
| 初级开发 | `qwen3.8:27b-mlx`（本地 Ollama） | 32k | `Task(junior-dev)` | 按 task 小步实现代码，每次最多 2 文件、150 行 |
| 测试 | `qwen3.5:9b`（本地 Ollama） | 32k | `Task(tester)` | 接口、安全、排序质量、真实登录与回归验收 |

> 2026-09-03 已用 `ollama list` 实测以上本地模型存在。业务 embedding 复用 `bge-m3`；业务 rerank 复用 spec-014 运行时，不把角色模型写入业务配置。

## 任务计划

> 任务 01 = 本 spec 的编写，不单独建任务文件。任务 02 起一任务一文件；详细步骤只写在任务文件中。索引见 [`plans/015/README.md`](../plans/015/README.md)。

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-015 | 本文件 | — | 完成 |
| 02 | 验证稳定基线、数据源与浏览器桥接（Go/No-Go） | [`task-02-validate-baseline-and-sources.md`](../plans/015/task-02-validate-baseline-and-sources.md) | 01，且 spec-013/014 完成 | 待执行 |
| 03 | 建立会议配置与论文召回 | [`task-03-conference-registry-and-retrieval.md`](../plans/015/task-03-conference-registry-and-retrieval.md) | 02 | 待执行 |
| 04 | 实现语义排序与 Reranker 集成 | [`task-04-semantic-ranking-and-rerank.md`](../plans/015/task-04-semantic-ranking-and-rerank.md) | 03，且 spec-014 可用 | 待执行 |
| 05 | 实现安全下载、规范命名与知识库导入 | [`task-05-secure-download-and-kb-import.md`](../plans/015/task-05-secure-download-and-kb-import.md) | 03 | 待执行 |
| 06 | 实现批量任务与登录续传 | [`task-06-batch-import-and-login-resume.md`](../plans/015/task-06-batch-import-and-login-resume.md) | 05 | 待执行 |
| 07 | 新增论文检索 Tab 与完整交互 | [`task-07-paper-discovery-tab.md`](../plans/015/task-07-paper-discovery-tab.md) | 03, 04, 05, 06 | 待执行 |
| 08 | 执行测试、排序基准与安全回归 | [`task-08-tests-ranking-and-security.md`](../plans/015/task-08-tests-ranking-and-security.md) | 04, 05, 06, 07 | 待执行 |
| 09 | 评审、部署与复盘 | [`task-09-review-deploy-retro.md`](../plans/015/task-09-review-deploy-retro.md) | 08 | 待执行 |

## 评审记录

> 初始不引用尚未生成的评审文件，下游只认真实落盘文档。

- 需求评审：`docs/sdd/reviews/015-requirement-review.md`（待评审（未执行））
- 技术评审：`docs/sdd/reviews/015-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/015-acceptance-review.md`（测试报告 + 开发主管签字；待评审（未执行））

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 用户 | 提出新增安全顶会论文检索 Tab，按研究方向相关度排序并直接下载、规范命名后加入知识库 |
| 2026-09-03 | 用户 | 确定会议范围可配置、默认最近五年、支持单篇与批量导入，命名采用“年份-会议-标题” |
| 2026-09-03 | 用户 | 确定通过会议搜索新增来源，采用项目内 Playwright，并要求真实验收 ACM 与 IEEE 登录续传 |
| 2026-09-03 | 用户 | 要求等待 spec-013/014 稳定后再实施，并按 spec-014 格式落盘 spec 与全部详细 task；当前不执行 |
| 2026-09-03 | 架构师(自身) | 实测本地模型并创建本 spec、任务索引及任务 02–09，状态保持待确认/待执行 |

---
**六条自检**：①边界均可转为测试；②spec 说明需求、task 承载实施细节；③task 链接真实且依赖无环；④明确不做已划死范围；⑤执行配置五行齐全；⑥产品步骤可映射 A1–A15。
**收口自检**：见 `docs/sdd/SDD-GATE-CHECKLIST.md` §3；三份评审、验收签字、changelog、复盘、运行时部署全部完成后才能转 `已完成`。
