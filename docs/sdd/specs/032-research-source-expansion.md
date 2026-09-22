# Spec 032 — Research Task 数据源与安全会议扩展

## 状态

**当前状态：实施中**（2026-09-20 用户确认新版 Spec032 并授权开始开发；从 Task06 统一来源合同实施）

## 一句话目标

让深度研究 Worker 按会议使用来源专用 Skill 和统一 Tool 契约，从 USENIX、IEEE S&P、ACM CCS、NDSS 官方目录发现论文，在已批准计划内自动取得可信全文；保留聚合来源补缺、增量缓存、字段 provenance、来源进度与失败论文人工修复闭环。

## 修订原因与确认边界

- 原 Spec032 的七来源管理、官方优先、增量缓存、字段来源、Research Task 进度、前端来源卡片及最终验收**全部保留**；新增多来源 Worker Skill、自动导入和“待处理论文”模块。
- Spec032.1 是本 Spec 的 USENIX 子规格。其已实现的详情摘要、编排 Skill、Tool 作为基线；未完成的 IDE 助手与会话 Skill 粘性移交本 Spec 的后续 Task。032.1 自身评审仍需真实完成，不能因移交而伪称完成。
- 本次事实审计见 [资产与缺口审计](../plans/032/asset-gap-audit.md)。审计区分已有代码、实际接线和真实年度验收；原 Task02–05 产出不删除，未闭环部分由新增 Task 承接。
- 用户已通过 Grilling 确认产品行为；本文件是需要再次确认的实施规格。确认前不修改业务代码，也不运行会改变项目状态的命令。

## 当前资产与未完成事实（2026-09-20）

| 资产 | 已存在 | 未完成、不能视为可用的部分 |
|---|---|---|
| OpenAlex/Crossref、IEEE S&P/CCS/NDSS Adapter 与固定样本 | 解析和部分真实抓取/下载证据已存在 | 三会议主要仍以 Crossref 枚举、OpenAlex 富化，不是官网目录优先；不同 Source 的输入/返回类型不统一 |
| USENIX 详情与产品 Skill/Tool | 官方摘要补抓、`fetch_paper_detail`、目录/下载 Skill 已实现 | 旧 `search()` 路径仍可能探测 PDF；新 Worker 未按统一来源策略调用；IDE 会话 Skill 待移交 |
| SQLite 缓存、来源记录、字段 provenance | 表和部分写入已存在 | 新会议未接入主图落库；字段来源主要仅 DBLP 路径写入；合并记录时的 provenance 迁移待验证 |
| Source Registry 与 `/api/papers/sources` | 初版注册表和路由已存在 | Registry 不是 Adapter 工厂，`/sync` 返回 queued 却不实际调度；启停仅进程内；ID/authority 与 Adapter 冲突 |
| PDF 下载、登录、批导入、知识库上传 | 单独入口已有安全下载、ACM/IEEE 登录与 retry/resume、PDF 上传 | Research Task 未桥接登录续跑，上传未绑定候选；批次重启恢复、身份存疑门禁和统一失败队列未闭环 |

当前 Graph 和 Tool 仍主要限制 USENIX/DBLP；`frontend/app.js` 来源进度也只枚举这两个来源。Task05 旧文档把部分落地写为“完成”，但当前定向回归仍有三条旧 authority 断言失败（审计时 `279 passed, 3 failed`）。**统一数值越小权威越高**仍是目标，但权威必须根据每个字段的真实取得来源判定：Crossref 枚举的会议论文不是会议官网字段。详见 [审计](../plans/032/asset-gap-audit.md)。

## 背景与依赖

- Spec027 首版只使用 USENIX Security 与 DBLP，无法覆盖更广泛科研主题。
- README 中已有 Crossref/OpenAlex 能力，但与 Spec015 全局论文目录和异步增量流程并非同一来源契约。
- 本 Spec 依赖 Spec027/034 的 Research Task、Spec015 的目录、Spec029 的全文获取和 Spec030 的不可变报告；不另建 Planner、报告合成器或知识库。

## 统一工作流与结构约束

1. Planner 从受控 Source Registry 选择会议与年份；批准的深度研究计划按现有 `target_paper_count` 预算，启动有界的逐来源 Worker。普通论文检索不自动下载。
2. 每个会议有来源专用的**产品运行时编排 Skill**（USENIX 已有目录/下载两份，其他会议按同一分层建立）。Skill 决定官网单元、详情补齐、可信回退和停止条件；确定性 Tool 执行 HTTP、解析、缓存、PDF 安全校验、导入及事件写回。LLM 不解析 HTML/PDF 字节，不逐篇设计工具调用 schema。
3. 各 Skill/Tool 返回同一版本化结构：`source_id`、`operation`、`status`、`scope/coverage`、候选/论文稳定 ID、实际字段来源、可重试错误码、产物/导入句柄与耗时；不以自由文本作为 Worker 间的唯一交接物。来源特有扩展放在受控扩展字段，不改变公共必填字段。
4. 官网目录字段优先；Crossref、OpenAlex、DBLP 按**字段真实 provenance**补缺。发现、详情、下载、导入分别持久化状态；目录阶段仅保存元数据，不发起 PDF GET/HEAD/Range。
5. 只有经评估选中的论文才尝试自动导入。公开官方 PDF → 可信开放版本 → 严格匹配 arXiv → Semantic Scholar Academic Graph API 提供的、且命中固定 allowlist 的 OA PDF → 现有受控 ACM/IEEE 登录能力；身份存疑或授权不可得则进入待处理，继续其他论文。禁止自动绕过登录/反爬和错误 PDF 静默入库。
6. 具体候选的失败汇总在“待处理论文”；用户可登录后续跑、有限重试或上传 PDF。上传复用个人知识库，关联原候选与研究任务。修复仍在执行的任务可续跑受影响步骤；已产出的报告不改写，只生成新版本。

## 来源与年度验收范围

- 首轮可宣称的年度覆盖：USENIX Security 2022–2026；IEEE S&P、ACM CCS、NDSS 各 2021–2025。每个来源×年份必须有固定样本、受控真实抓取、字段质量和导入结果记录；若某年份未通过，则只标“未验证”，不能凑数宣称覆盖。
- 超出已验证年份可在服务端边界内有界尝试；只有实际通过身份、字段和导入验收后才加入已验证范围。`MIN_YEAR`/`MAX_YEAR` 仅是参数校验，不是覆盖证明。
- 官方页面确无摘要/关键词时允许空值，分别记录 `missing`；不能由模型编造。若从开放聚合源或用户 PDF 补齐，应显示相应实际来源，不得写成官网提供。
- 整来源失败仍可保留其他来源结果，但 Research Task 显示 `partial`、实际覆盖范围及失败原因；不得把来源失败伪装为“该年没有论文”。

## Source Adapter 合同

| 字段/方法 | 约束 |
|---|---|
| source_id / source_kind | 稳定、全局唯一 |
| authority_rank | 数值越小越权威；按**实际字段来源**赋值，会议标签不自动抬高 Crossref/OpenAlex 字段 |
| discover_units(scope) | 返回年份/cycle/track 等持久化抓取单元 |
| fetch_unit(unit, conditional_headers) | 支持 ETag/Last-Modified/内容 hash 与超时 |
| parse_catalog(response) | 统一 `SourceResult`：标题、摘要状态、关键词、作者、年份、DOI、页面/PDF 候选地址及逐字段 provenance；缺失不编造 |
| normalize_identity(record) | 复用现有 DOI/标题规范化和去重 |
| health() | 安全、脱敏、无隐式网络请求与下载副作用；主动探测须明确调用 |
| download/import | 由通用 Tool 调用既有安全下载与个人 KB 导入，返回统一 `ImportResult`；来源 Skill 只选择策略 |

## 数据模型增量

| 实体 | 关键字段 | 约束 |
|---|---|---|
| SourceDefinition | source_id、kind、authority_rank、enabled、allowed_hosts | 服务端受控配置 |
| SourceFetchUnit | source_id、scope_key、etag、last_modified、content_hash、status | 复用/扩展 Spec015，不建平行缓存 |
| FieldProvenance | paper_id、field_name、source_id、source_record_id、observed_at | 高权威字段不能被低权威覆盖 |
| SourceCoverage | task_id、source_id、requested_units、cached/fetched/failed | 提供 Research Task 进度卡片 |
| SourceResult | schema_version、source_id、operation、status、coverage、papers、error、elapsed_ms | 所有 Worker Tool 共享结构化返回合同；单源失败可部分完成 |
| PaperCandidate | stable_id、title、authors、year、doi、abstract/status、keywords/status、official_page、pdf_candidates、field_provenance | title/year/source 与稳定身份必需；可选字段明确缺失 |
| ImportResult | schema_version、candidate_id、status、document_id、identity_verdict、attempts、error | 与 SourceResult 共用状态/错误外壳；成功须有可信文档句柄，失败不得伪装成功 |
| AcquisitionIssue | issue_id、candidate_id、关联 task_ids、reason_code、status、attempts、resolution | 仅具体论文问题；同一候选跨任务去重，保留历史 |
| ManualResolution | issue_id、方式（login/upload/retry）、user_document_id、identity_verdict、confirmed_at | 明确错论文禁止绑定；不存密码/Cookie；保留人工确认依据 |

## 来源范围

- 学术聚合：OpenAlex、Crossref；DBLP 继续作为辅助书目信息来源，不独立承担会议 PDF 下载。
- 安全会议官方目录：USENIX Security（既有）、IEEE Symposium on Security and Privacy、ACM CCS、NDSS。
- 三个新增会议必须补官网目录优先路径；现有 Crossref 枚举/OpenAlex 富化保留为降级路径。官方页面字段优先；聚合来源不能覆盖更高权威的标题、摘要、关键词和官方链接。
- 搜索阶段只保存目录元数据，不探测或下载 PDF；下载仍走 Spec029/既有安全链。
- Semantic Scholar 的下载阶段仍只作为 OA 回退查找器：优先 DOI/ArXiv ID，读取 `openAccessPdf.url`，不抓取搜索页/Reader HTML，不动态扩大 PDF 主机 allowlist；返回地址仍由既有安全下载器校验。元数据补全、候选池召回和图辅助按下方“Semantic Scholar 扩展确认”执行。

## Semantic Scholar 扩展确认（2026-09-21）

用户确认将 Semantic Scholar 的能力扩展为三层，但不改变官方会议来源的权威边界：

1. **元数据补全**：对官方目录或 DBLP 已识别、但缺摘要/作者/DOI 的候选，优先按 DOI、ArXiv ID 或 Semantic Scholar ID 使用详情/批量详情接口补缺；官方字段优先，每个字段记录真实 provenance。该阶段只读元数据，不下载 PDF。
2. **候选池辅助召回**：当官方目录与 DBLP 的候选不足时，使用 Academic Graph bulk search 做有界辅助召回；结果标记为聚合来源，必须经过标题、作者、年份和研究范围评估，不得仅凭 Semantic Scholar venue 字段宣称属于目标会议。
3. **研究扩展与交互辅助**：后续提供标题自动补全、引用/参考文献和相似论文扩展；autocomplete 只用于交互式最小候选，不能替代完整目录或 PDF 下载。

硬性约束：

- Semantic Scholar 不进入官方会议目录的权威来源集合，不覆盖官方标题、年份、关键词或官方页面。
- `openAccessPdf.url` 仍只能作为现有安全下载链的候选地址；不得动态扩大 host allowlist。
- 所有 Academic Graph 请求共用进程级 1 秒限流、缓存和有限退避；批量接口优先，API key 只在服务端环境变量中读取。
- 多进程/多机器部署暂不支持共享限流；当前单 Uvicorn worker 是前置条件。

## 接口

| 动作 | 输入 | 成功返回 | 失败 |
|---|---|---|---|
| GET /api/papers/sources | filter | 来源、实际能力、健康、已验证年份及缓存范围 | 503 store |
| PATCH /api/papers/sources/{id} | enabled | 更新受控启停，响应说明重启后是否保留 | 404 未知；409 内置约束 |
| POST /api/papers/sources/{id}/sync | 受控年份/scope | 202 + 可查询同步 ID，真实启动或入队 | 400 范围；409 不支持；503 调度失败，禁止假 queued |
| GET /api/papers/sources/{id}/sync/{sync_id} | 同步 ID | 实际进度、缓存命中、成功/失败单元与终态 | 404 不存在；503 store |
| Research Task Planner source 参数 | source_ids/scope | 只接受已注册启用来源及受控年份；来源 Worker 按计划运行 | 422 未知/禁用来源 |
| GET /api/papers/issues | task/source/reason/status 游标筛选 | 按候选去重的待处理论文、可行动作、关联任务 | 400 筛选非法；503 store |
| POST /api/papers/issues/{id}/upload | PDF、身份确认（仅不确定情形） | 复用 KB 上传/索引并关联候选，返回 task/document 句柄 | 400 非 PDF/身份明确冲突；404；413 超限；503 |
| 待处理项登录/继续/重试 | issue_id → 服务端 import-item 快照 | 复用既有 `/api/papers/import-items/{item_id}/login\|resume\|retry`，同步研究证据状态 | 400 状态不允许；404；424 会话过期/需授权 |
| GET /api/papers/{paper_id}/provenance | 受控论文 ID | 逐字段实际来源、观察时间及置信/缺失状态 | 404；503 store |
| GET /api/papers/semantic-scholar/autocomplete | query、limit（1–20） | 去重后的 paper_id/title 短候选 | 400 参数；503/429 脱敏 provider 错误 |
| GET /api/papers/semantic-scholar/{paper_id}/{citations\|references} | 受控 paper_id、limit（1–100）、offset | metadata-only 图边页及 next_offset/total | 400 关系/分页；503/429 脱敏 provider 错误 |

## 边界与失败场景

- 页面结构变化、周期页拆分、摘要/关键词缺失、限流、ETag 异常、重复 DOI、同名论文和来源冲突。
- 单源失败不得清空旧缓存；页面内容未变化不重复向量化。
- URL、DNS、重定向与 SSRF 规则继续复用既有平台能力；Planner 不能传任意根 URL。
- 新来源必须具备固定 HTML/JSON 样本和 provenance 测试后才能启用。
- PDF 校验分“有效文件”与“确为目标论文”；明确错链或身份冲突不得自动入库/引用。无法判定时可由用户确认，并持久化确认记录。
- 登录仅在服务所在电脑复用既有 ACM/IEEE headed browser；远程设备可改为上传 PDF。不转发密码/Cookie、不自动绕过反爬。浏览器会话失效须可重开，`waiting_login` 不能错误地走仅支持 `failed` 的 retry。
- 研究导入批次进程重启后必须能从持久快照恢复或明确转为可重试，不能永远停在 queued；重复恢复/上传不得创建重复 KB 文件或重复报告版本。
- 已生成报告不可变；修复论文后生成新版本并保留旧报告，研究任务仍在等待时只续跑受影响步骤。

## 明确不做

- 不让用户添加任意网站或自定义爬虫。
- 不在搜索阶段下载/验证 PDF，不绕过登录或反爬。
- 不把 Semantic Scholar 作为官方会议字段来源；不抓取其搜索页/Reader，不根据 API 返回地址动态信任未知主机。
- 不改模型路由和报告合成语义，不另建个人知识库 Collection、第二套 PDF 仓库/下载器或任意 URL 输入。
- 不做远程浏览器登录/凭证转发，不让来源 Skill 存放研发 Task/Git 分派规则，不由 LLM 解析 HTML/PDF 字节。

## 验收方式

- 每个来源使用固定样本验证列表发现、详情解析、缺失字段、分页/年度单元和字段 provenance。
- 重复范围只抓取新增/变化/失败/过期单元；服务重启和目录索引重建后缓存仍成立。
- 来源冲突按 authority_rank 合并，低权威来源不能覆盖官方字段。
- 四会议首轮逐年验证（USENIX 2022–2026；其余 2021–2025），记录论文数、摘要/关键词缺失比例、PDF 可得/正确/导入比例；未通过年份不标已覆盖。
- 两个不同来源 Skill 的 Worker 调用相同版本的 Tool 返回 schema；真实任务中来源选择、候选评估、自动导入、字段来源、进度和失败队列贯通。
- 模拟 ACM/IEEE 需登录、无 PDF、错链、上传错文件、用户上传正确文件、进程中断与重启；人工修复后证据可续跑、报告保留旧版本。
- 单源失败时 Research Task 显示对应状态并使用其他来源；普通搜索不自动下载；最终 Task 一次全量回归、真实端到端 smoke 和部署。

## 产品使用步骤

以下步骤是 Task12/Task14 的核心人工验收旅程；页面上的状态、错误码和恢复按钮必须与这些步骤保持一致。

1. **选择来源与范围**：进入论文检索，选择 `USENIX`、`DBLP`、`IEEE S&P`、`CCS`、`NDSS` 或聚合补充源，并填写年份范围和研究方向。未知来源或未允许的 URL 直接提示“来源不支持”，不能开始任务。
2. **查看同步进度**：点击开始检索后，每个来源显示独立状态卡：缓存范围、正在获取范围、完成数量、降级或错误。已有缓存显示“使用缓存”，只有缺失、失败、过期或内容变化的单元显示“正在获取”。
3. **查看候选并评估**：同步完成后进入候选列表，查看标题、摘要、关键词、来源和字段来源；候选评估只保留批准研究范围内的论文，并显示保留/淘汰理由。单源失败时仍显示其他来源结果，并在失败卡片给出重试入口。
4. **批准研究计划**：输入自然语言研究主题和目标，确认时间范围后查看计划，点击“批准计划”。页面先显示“计划已批准，正在执行”，随后按 Worker 阶段追加事件，不显示虚假的已完成状态。
5. **确认导入**：在论文选集中勾选候选并确认导入。搜索阶段不下载 PDF；导入阶段显示每篇论文的排队、下载、校验、入库和索引状态，重复论文复用已有身份和文档，不创建重复文件。
6. **处理失败论文**：`waiting_login` 显示“打开登录/登录完成后继续”，`failed` 显示“重试”，无法自动下载时显示“上传 PDF”。用户只在本机浏览器完成 ACM/IEEE 登录或上传目标文件，不提交密码、Cookie，也不允许任意 URL。
7. **恢复与重启**：服务重启后重新打开任务，已完成单元保持完成，排队或租约过期单元恢复或明确变为可重试；页面显示恢复事件和下一步，不允许任务永久停在 `queued`。
8. **查看报告版本**：候选修复或新增全文证据后生成新报告版本；旧版本保持只读不可变。报告中展示标题、摘要、关键词、引用来源和字段 provenance，失败或未验证来源明确标注 `degraded/NO-GO`。

验收记录至少包含：来源选择、缓存/获取进度、候选评估、批准计划、导入结果、失败恢复、服务重启后的状态和新旧报告版本链接；对应证据分别写入 `artifacts/task-12/` 与 `artifacts/task-14/`。

## 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身 | 200k | 主会话 | 来源权威和复用边界 |
| 产品经理 | `qwen3.5:9b` | 32k | `Task(doc-updater)` | 来源选择与进度旅程 |
| 开发主管 | `qwen3.8:27b-mlx` | 32k | `Task(architect)` | Adapter、安全和去重评审 |
| 初级开发 | `qwen3.8:27b-mlx` | 32k | 分端开发 Agent | 来源适配器和界面实现 |
| 测试 | `qwen3.5:9b` | 32k | 分端 tester + `Task(tester)` | 固定样本和集成验收 |

## 任务计划

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec032 | 本文件 | — | 完成 |
| 02 | 原 Adapter/provenance/增量合同资产 | [`task-02-source-adapter-contract.md`](../plans/032/task-02-source-adapter-contract.md) | Spec027/015 | 历史资产；独立门禁未闭环，由 06 复核 |
| 03 | 原 OpenAlex/Crossref Adapter 资产 | [`task-03-openalex-crossref-adapters.md`](../plans/032/task-03-openalex-crossref-adapters.md) | 02 | 代码已产出；主流程接线由 08 完成 |
| 04 | 原 IEEE S&P/CCS/NDSS Adapter 资产 | [`task-04-security-conference-adapters.md`](../plans/032/task-04-security-conference-adapters.md) | 02 | 代码/样本已产出；官网优先与逐年验收由 07 完成 |
| 05 | 原来源注册/API/provenance 阶段交付审计 | [`task-05-source-merge-progress-ui.md`](../plans/032/task-05-source-merge-progress-ui.md) | 03、04 | 部分完成；存在假 queued、provenance/接线缺口 |
| 06 | 统一来源 ID、权威、返回合同与旧回归 | [`task-06-unified-source-contract.md`](../plans/032/task-06-unified-source-contract.md) | 02–05；新版确认 | 已完成（定向验证通过） |
| 07 | 官网目录优先、聚合兜底和逐年字段覆盖 | [`task-07-official-catalog-coverage.md`](../plans/032/task-07-official-catalog-coverage.md) | 06 | 部分完成（IEEE S&P/NDSS 2024 固定样本；CCS 2021–25 bounded NO-GO） |
| 08 | 来源注册、增量同步、Graph/Store/Planner 接线 | [`task-08-catalog-runtime-integration.md`](../plans/032/task-08-catalog-runtime-integration.md) | 06、07 | 已完成（新来源 Worker bridge 定向验证通过；真实 smoke 留 Task14） |
| 09 | 多来源 Worker Skill 与统一 Python Tool | [`task-09-source-worker-skills-tools.md`](../plans/032/task-09-source-worker-skills-tools.md) | 06–08 | 已完成（worker-tool-v1；未验证来源保持 blocked） |
| 10 | 计划内自动导入、身份校验与恢复 | [`task-10-approved-plan-auto-import.md`](../plans/032/task-10-approved-plan-auto-import.md) | 08、09 | 已完成（定向验证通过） |
| 11 | 待处理论文、登录/上传/重试与版本衔接 | [`task-11-paper-issue-recovery.md`](../plans/032/task-11-paper-issue-recovery.md) | 10 | 已完成（后端定向验证通过；前端留 Task12） |
| 12 | 来源进度、字段来源与人工修复 UI | [`task-12-source-progress-issue-ui.md`](../plans/032/task-12-source-progress-issue-ui.md) | 08、11 | 已完成（前端定向验证通过；真实 smoke 留 Task14） |
| 13 | 032.1 余项移交：IDE 助手与会话 Skill 粘性 | [`task-13-spec0321-carryover.md`](../plans/032/task-13-spec0321-carryover.md) | 09；032.1 本地评审 | 部分完成（Task08 真实检索→导入通过；Task10 sticky intent 已实测，精确下载工具调用待补证） |
| 14 | 最终评审、全量回归、部署和复盘 | [`task-14-review-regression-deploy.md`](../plans/032/task-14-review-regression-deploy.md) | 06–17 | 实施中 |
| 15 | Semantic Scholar 元数据补全与字段 provenance | [`task-15-semantic-scholar-metadata-enrichment.md`](../plans/032/task-15-semantic-scholar-metadata-enrichment.md) | 06、08、14 | 最小实现完成；待 Task14 真实 key/重启验收 |
| 16 | Semantic Scholar 候选池辅助召回 | [`task-16-semantic-scholar-bulk-recall.md`](../plans/032/task-16-semantic-scholar-bulk-recall.md) | 07、08、15 | 最小实现完成；待 Task14 真实候选/重启验收 |
| 17 | Semantic Scholar 自动补全与引用图辅助 | [`task-17-semantic-scholar-graph-assistance.md`](../plans/032/task-17-semantic-scholar-graph-assistance.md) | 15、16 | 最小实现完成；待 Task14 真实 key/部署验收 |

### 历史 Task05 的部分交付（不得误标为整项完成）

`source_authority.py`、三会议解析器常量、`source_registry.py`、SQLite schema v3/v4、DBLP provenance 路径和来源 API 已写入工作树；但这些仅是**阶段资产**。Adapter ID/authority 冲突、3 个旧测试失败、其他来源 provenance 未写入、Planner 校验未接线、`POST /sync` 假排队等缺口由 Task06–08 承接。旧 Task05 记录保留在任务文档和审计中，不能把新增任务说成重复开发。

## 评审记录

- 需求评审：`docs/sdd/reviews/032-requirement-review.md`（打回，收口阻塞）
- 技术评审：`docs/sdd/reviews/032-tech-review.md`（历史打回，P1 已修复；仍待最终复评）
- 验收评审：`docs/sdd/reviews/032-acceptance-review.md`（不通过，来源覆盖与真实导入/恢复证据不足）

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-12 | 架构师（自身） | 创建聚合来源和四大安全会议扩展 Spec |
| 2026-09-19 | 架构师（自身） | 复核现状：Adapter 与三会议源已落地（Task02/03/04 实现完成），新增「现状盘点」与「权威级别冲突」两节；把原 Task05 拆为后端（05）与跨端（06），任务编号顺延；用户授权后状态改为「已确认」，进入实施。 |
| 2026-09-20 | 架构师（自身） | 经 Grilling 多轮确认多来源 Worker Skill、统一 Tool、官网优先、计划内自动导入与待处理论文人工修复。审计发现原 Task05/README 完成记录高估实际接线，新增 Task06–14、032.1 余项移交并退回待确认；仅落盘文档，等待新版确认。 |
| 2026-09-20 | 架构师（自身） | Task06 完成：统一七来源 canonical ID、authority 方向、SourceResult/ImportResult v1、旧 SQLite 别名迁移和薄适配层；定向测试与静态检查通过，Task07 官网目录优先实现尚未开始。 |
| 2026-09-20 | 架构师（自身） | Task07 首轮部分完成：IEEE S&P 2024 官方目录固定样本可验证；摘要、关键词、PDF 未由官网伪造，CCS/NDSS 和其余年度仍标记未验证/NO-GO。仅允许 Task08 在该已验证范围内接线。 |
| 2026-09-20 | 架构师（自身） | Task08 首轮部分完成：七来源 Registry 工厂、受控同步 API、真实 search_jobs/source_progress 终态和 SQLite 重启读取已验证；Graph/Planner 全量 source_ids 接线仍待补齐。 |
| 2026-09-20 | 架构师（自身） | Task08 follow-up 完成：非 `usenix/dblp/all` 来源经统一 `PaperDiscoveryToolFacade` 接入 Research Worker，并复用既有 CatalogPaper、SourceRecord、field provenance 与 SearchJob/SearchResult 冻结契约；23 项 Task08/09/Spec034 合同测试、215 项相关回归及静态检查通过。真实外部目录与部署 smoke 留 Task14。 |
| 2026-09-20 | 架构师（自身） | Task09 完成：统一 `paper_discovery` Worker Tool 使用 `worker-tool-v1`，来源 Skill 只负责编排，注册入口可实际执行并对未知来源/任意 URL fail-closed；未验证会议来源保持 blocked。 |
| 2026-09-20 | 架构师（自身） | Task08/Task13 真实 smoke 追加：当前 18080 服务的 USENIX 2024 检索返回 `partial` 与 3 个候选；一篇新候选通过既有安全导入链返回 `indexed`，重复/失败候选分别返回 409/424。会话第二轮“继续搜索第一篇吧”返回 `source=sticky` 的 Skill intent；模型生成收口慢，精确“就下载第一篇吧”工具调用仍待无副作用 seam 或明确授权，Spec032 保持实施中。 |
| 2026-09-22 | 架构师（自身） | 修复导入批次页面刷新后不恢复的前端缺陷，并将深度研究中的下载失败人工恢复路径明确为任务内登录/登录后继续/重试/PDF 上传；不要求重新检索论文。18081 真实 API 返回既有 `waiting_login` 批次，浏览器论文检索页可见“需要登录后继续”。 |
