# 技术评审：spec-015 安全顶会论文检索与知识库导入

- **评审者**：当前协作 Agent
- **角色**：独立开发主管（Tech Lead）
- **实际模型**：当前协作 Agent（调度器未暴露具体模型标识，不冒充 spec 中配置的本地模型）
- **分派方式**：主会话通过协作 Agent 独立分派
- **评审对象**：`docs/sdd/specs/015-security-paper-discovery.md` 与 `docs/sdd/plans/015/task-02-validate-baseline-and-sources.md` 至 `task-09-review-deploy-retro.md`
- **评审时间**：2026-09-04
- **评审方式**：读取真实 spec/task、当前 Git 基线、角色配置、知识库存储/路由与现有下载实现；未修改业务代码、未提交 Git

## 结论：打回

总体架构“DBLP 主召回 + OpenAlex 补全 + bge-m3 初排 + spec-014 批量 rerank + 服务端候选导入 + Playwright 合法登录续传”可实现，任务依赖无环，降级方向合理。但当前文档在 SSRF、跨介质一致性、SQLite 并发幂等和排序查询模型上仍缺少实现级契约；照现稿直接编码会产生安全漏洞或无法判定导入是否真正完成。完成下列必须修订项后再进行技术复审；复审通过前不得开始 Task 03–09 的业务代码。

## 代码事实核对

- 当前共同基线为 `main@e980cea`，工作树在评审开始时无未提交改动；spec-013 已记录为 `已完成`，但 `docs/sdd/specs/014-kb-reranker.md:5` 仍记录 `实施中`。Task 02 明确要求 spec-013/014 均完成，文档状态未对账前不能判定 Go。
- `backend/app/services/article_download.py` 当前使用 `follow_redirects=True`，并直接请求候选 URL；它只做大小与 `%PDF-` 检查，没有目标 IP 分类、每跳复核或 DNS rebinding 防护，不能被 Task 05 直接当作“安全下载器”复用。
- `backend/app/services/kb/store.py` 当前元数据为 `papers.json`、进程内 `RLock`，原件路径固定为 `{paper_id}.pdf`；`backend/app/api/routes.py` 的上传流程依次执行文件保存、JSON upsert、v1 同步索引和 v2 异步提交，文件、JSON 与 Qdrant 不存在跨介质事务。
- `PaperRecord` 当前没有 `stored_name` 和论文来源字段；删除、重建路由都直接拼接 `{paper_id}.pdf`。兼容路径层确有必要，但不能把可读文件名直接当可信路径。
- spec-014 已提供批量 rerank 客户端及失败回退，Task 04 复用它是正确方向；bge-m3 现有批处理也可复用，但论文搜索必须设独立候选文本上限与资源并发界限。
- `.codebuddy/agents/tech-lead.md:6` 与当前 `AGENTS.md` 均使用 `qwen3.8:27b-mlx`，而 spec-015 执行配置仍写 `qwen3.8:27b`，三处不一致。
- 前端仍是 `frontend/index.html` + `frontend/app.js` 的静态单页结构；Task 07 保持安全 DOM API、同步升级静态资源版本并做浏览器实测的拆分是可行的。

## 评审意见

| 维度 | 判定 | 说明 |
|---|---|---|
| 改动面与任务拆分 | 基本可行 | Task 02–09 依赖无环，后端、下载、任务、浏览器与 UI 已分阶段；编码分派仍须落实每次最多 2 文件、150 行，并避免多个分派同时修改 `routes.py`/`app.js`。 |
| 数据模型 | 打回 | 只列出了对象字段，未固定 SQLite 主键、外键、唯一约束、索引、schema 版本、时间格式与清理规则。搜索 TTL、并发领取、批次计数和幂等无法据此实现并验证。 |
| 接口契约 | 打回 | 请求/响应 schema、稳定错误体、HTTP 状态码和异步状态语义未固定；`/imports/{batch_id}` 与 `/imports/{item_id}/login` 共用同一路径层级，容易误用，需明确区分 batch/item 资源。 |
| SSRF 与下载安全 | 打回 | “先解析再校验、每跳复核”仍不足以抵御校验与连接之间的 DNS rebinding；现有 `follow_redirects=True` 也无法执行逐跳策略。必须固定手动重定向、地址规范化、公共 IP 连接约束和站点 allowlist。 |
| 一致性与恢复 | 打回 | SQLite、PDF 文件、JSON 元数据和 Qdrant 无法形成真实原子事务。需定义可恢复的状态机、补偿动作和启动对账，而不是笼统承诺“原子化交付”。 |
| 排序与模型 | 打回 | 检索顺序提出“本地查询模型生成关键词”，但没有模型配置、结构化输出、超时、`think:false`、词数/字符上限和失败回退；实现者会被迫自行补设计。 |
| 容错与降级 | 基本可行 | DBLP/OpenAlex/Reranker/Playwright 分别降级的方向正确；需给 warning/error code 建立固定枚举，避免向前端透传异常字符串。 |
| 登录与凭证边界 | 附条件可行 | 可见浏览器和持久化 profile 符合用户选择；仍需限定 ACM/IEEE 允许 origin、profile 权限/忽略规则、Cookie 使用范围、trace 禁用与进程所有权。 |
| 知识库兼容 | 打回 | 需要明确 v1 成功、v2 排队/失败时 PaperImportItem 与 Batch 的状态；否则“completed”与“可在知识库检索”无法一致判定。 |
| 模型与上下文预算 | 打回 | Tech Lead 模型名与现行 agent 配置不一致；须统一为真实已注册的 `qwen3.8:27b-mlx`，并保留 `ollama list` 证据。 |
| 回滚 | 基本可行 | 功能开关和“不删除已导入论文”正确；必须补充独立 SQLite schema 的前向兼容/备份策略以及中断导入的恢复规则。 |

## 必须修订项

1. **T1 基线对账**：在 Task 02 前把 spec-014 的 spec、README、task、验收和状态台账对齐真实完成状态与合并 commit `e980cea`；若证据不足则保持 No-Go。回填 spec-015 基线 commit、分支与干净工作树证据。
2. **T2 SQLite 契约**：在 spec 或 Task 03/06 固定 schema version、表字段、主外键、`ON DELETE`、唯一索引、UTC 时间格式、WAL、`foreign_keys=ON`、`busy_timeout`、显式事务和过期清理。幂等键必须由数据库唯一约束兜底，不能只靠进程锁或“先查再写”。
3. **T3 任务状态机**：列出 Batch/Item 允许的状态迁移、终态、重试条件和非法迁移响应；并发 `retry/resume` 使用条件更新或租约保证单一执行者。启动恢复只处理明确的非终态，并在执行前再次做知识库去重/对账。
4. **T4 SSRF 防线**：禁止自动跟随重定向；每跳限制为 HTTPS、限定端口与最大跳数，拒绝 URL 用户信息、非标准/混淆 IP、IPv4-mapped IPv6、loopback/private/link-local/multicast/reserved/unspecified。解析后必须让实际连接绑定到已校验的公共地址，或在连接后验证 peer IP；仅“DNS 预查 + 按 hostname 连接”不能通过。下载与 Playwright 分别维护最小域名/origin allowlist。
5. **T5 出站资源上限**：固定连接/读取/总超时、最大响应头、最大 PDF 字节数、并发数、重定向数和临时目录权限；流式下载使用唯一临时文件并以安全 rename 落盘。日志只留规范化域名和错误码，不留 query/fragment/Cookie/Authorization。
6. **T6 跨介质一致性**：把“原子化交付”改为可验证的 saga/补偿流程。明确文件保存、JSON 元数据、v1 Qdrant、v2 任务各阶段的 commit point、失败清理、孤儿文件/记录对账与恢复。禁止在持有全局锁时执行网络、PDF 解析、embedding 或 Qdrant 调用。
7. **T7 KB 完成语义**：明确 PaperImportItem 在 v1 索引成功后是 `completed` 还是仍为 `indexing`；v2 异步失败如何暴露但不撤销 v1 可用论文；Batch 聚合必须由持久化 item 状态计算，不能维护可漂移计数。旧 `{paper_id}.pdf` 与新 `stored_name` 都必须经 `resolve` 后校验仍位于 `KB_PAPERS_DIR`。
8. **T8 查询扩展契约**：为“本地查询模型”补充配置名、实测模型、`think:false`、temperature、结构化 schema、最大关键词数量/长度、调用超时与纯原查询回退；若它不是必要能力，应从检索顺序删除，避免额外模型依赖。不得让生成关键词改变年份/会议过滤条件。
9. **T9 API 契约**：为全部新增端点固定 Pydantic 请求/响应模型、HTTP 状态码和稳定错误结构。建议把 item 动作改为 `/api/papers/import-items/{item_id}/login|resume`，或在 spec 中明确为何沿用当前层级。所有客户端提供的 `conference_id/search_id/candidate_id/item_id` 均只作查找键，不形成路径或 URL。
10. **T10 浏览器边界**：固定 Playwright 版本与浏览器版本、headed 启动方式、单 profile 所有权/文件锁、目录权限和 Git 忽略；禁用或清理 trace/HAR/video/download 等可能含凭证的产物。用户取消、浏览器崩溃、站点跳出 allowlist、无权限下载都必须成为稳定可重试错误。
11. **T11 排序可重复性**：冻结集需落盘查询、候选快照、标签、冻结时间和 hash；定义标题/摘要截断、embedding 归一化、NaN/维度异常、rerank 分数映射及稳定 tie-break。并发资源需避免与 KB embedding/索引争抢导致 OOM。
12. **T12 模型配置统一**：将 spec-015 Tech Lead 改为 `qwen3.8:27b-mlx`，并核对 `MODEL_REGISTRY.md`、`AGENTS.md`、`.codebuddy/agents/*.md` 逐字一致；实现前重新执行 `ollama list` 留证。
13. **T13 Task 02 门禁分层**：Task 02 必须先验证 Playwright 安装、可见窗口、profile 持久化和站点 allowlist；真实 ACM/IEEE 合法账户下载可作为最终验收硬门禁。若仍坚持把真实登录设为编码前 Go 条件，则必须明确需要用户参与，用户暂不可提供合法样本时 Task 03–09 全部阻塞，不得伪造或绕过。

## 最低验证要求（修订后进入实现）

- SQLite：两个并发进程创建同一幂等任务只成功一次；崩溃/重启后无永久 running；删除或损坏状态库有明确恢复/失败策略。
- SSRF：覆盖 IPv4/IPv6、mapped IPv6、混淆 IP、恶意 DNS 变化、至少两跳重定向、跨协议、带凭证 URL与非默认端口；测试必须证明实际连接目标受约束。
- 导入：在文件保存、元数据写入、v1 索引、v2 提交每个故障点注入失败，均不出现“记录 completed 但不可检索”或目录外文件。
- API：功能关闭时零外部请求；所有异常返回固定 error code，不透传 traceback、原始 URL 或外部响应正文。
- 浏览器：ACM/IEEE origin 隔离，profile/HAR/trace/Cookie 不进入 Git 和日志；公开 PDF 路径在 Playwright 缺失时仍可用。
- 回归：全量测试不少于当前合并基线，覆盖率不低于 80%；前端 class/CSS 对齐、静态资源版本更新、冲突标记 0 命中。

## 风险定级：高

主要风险来自不受信任外部 URL、持久登录凭证，以及 SQLite/文件/JSON/Qdrant 四种状态的并发一致性。以上不是实现细节偏好，而是安全与数据正确性门禁；必须先由架构师把决策写回 spec/task，再复审。

## 阻塞项

- 当前技术评审结论为打回；T1–T13 未修订前禁止进入业务代码实现。
- spec-014 文档仍为 `实施中`，与 Task 02 的前置条件及用户口头状态不一致，须先基于真实合并/验收证据对账。
- ACM/IEEE 真实登录验收依赖用户提供合法账户与交互；无合法样本时不得声称该验收通过。

---

## 技术复审（2026-09-04 11:03，Asia/Shanghai）

### 结论：打回

本次复审保留首次评审证据，并逐项核对架构师对 T1–T13 的修订。T4、T7、T12、T13 已关闭；T1、T3、T6、T10 部分关闭；T2、T5、T8、T9、T11 尚未形成实现级契约。当前改动主要把评审要求重新写成“实现时必须固定”，但没有给出部分关键结构和值，仍会把架构决策留给编码 Agent，因此技术门禁不能放行。

### T1–T13 关闭矩阵

| 项 | 复审状态 | 证据与结论 |
|---|---|---|
| T1 基线对账 | 部分关闭 | spec-015 已回填 `main@e980cea`，Task 02 也规定文档不一致即 No-Go；但 `spec-014` 仍为 `实施中`，其 README 中 Task 08/09 仍为待执行。合并 commit 已存在不等于状态文档、验收签字和复盘已对账。 |
| T2 SQLite 契约 | 未关闭 | Task 03 只写“固定 schema version、主外键、唯一索引……”的要求，没有给出 schema version 值、实际表、字段类型/非空约束、FK 指向、唯一键组合、索引、`busy_timeout` 值和迁移策略；仍不是可直接实现/测试的契约。 |
| T3 任务状态机 | 部分关闭 | Item 主路径、登录分支、失败重试和数据库条件更新已写入；Batch 各状态的聚合规则、所有失败边、`cancelled` 入口、租约字段/期限或 CAS 版本字段仍未固定。 |
| T4 SSRF 防线 | 已关闭 | 已明确禁止自动重定向、仅 HTTPS/默认端口/allowlist、拒绝危险 IP 类别、逐跳复核，并要求连接绑定已校验公共 IP或验证 peer IP；可据此编写实现与恶意 DNS 测试。 |
| T5 出站资源上限 | 未关闭 | 文档仍仅说“固定/限制”连接、读取、总超时、响应头、PDF 大小、并发和重定向，没有具体数值。现有 `PAPER_DISCOVERY_REQUEST_TIMEOUT_SECONDS=20` 也没有拆分各阶段或覆盖响应头/跳数/并发。 |
| T6 跨介质一致性 | 部分关闭 | 已正确否认跨介质原子事务并选择 saga，且禁止锁内网络调用；但没有逐阶段 commit point、失败补偿和启动对账表，无法判断文件已 rename、JSON 已写、v1 索引失败等每个注入点的期望终态。 |
| T7 KB 完成语义 | 已关闭 | 已明确 v1 同步索引成功即 Item `completed`，v2 事件独立且失败不撤销 v1；Batch 由 Item 状态聚合，符合现有 KB 双版本事实。实现时仍须保留路径 `resolve`/目录包含校验。 |
| T8 查询扩展契约 | 未关闭 | spec 的检索顺序仍要求“用本地查询模型”，修订又写“若启用/无法满足则不启用”，形成冲突；也没有配置名、具体模型、schema、temperature、关键词上限和超时。必须明确 v1 禁用，或完整固定启用契约，不能留到实现者选择。 |
| T9 API 契约 | 未关闭 | 端点仍使用 `/imports/{item_id}/login|resume`，未与 batch 路径分层；没有 Pydantic 模型名、HTTP 状态码映射、统一错误体结构和完整稳定错误码枚举。 |
| T10 浏览器边界 | 部分关闭 | headed、profile 锁、产物禁用和最小 ACM/IEEE allowlist 已写入；但 exact origin 列表、目录权限、锁失败语义、Playwright/浏览器版本冻结位置尚未给出。版本可由 Task 02 实测冻结，但应明确输出字段和后续依赖读取位置。 |
| T11 排序可重复性 | 未关闭 | 原 Task 04 仍只要求冻结查询/候选/标签，没有快照格式、冻结时间/hash、标题/摘要截断值、embedding 归一化公式、异常映射、最终 tie-break 完整顺序和资源并发规则。 |
| T12 模型配置统一 | 已关闭 | spec-015 与 Task 09 已改为 `qwen3.8:27b-mlx`，和 `.codebuddy/agents/tech-lead.md` 当前值一致；实现前仍按文档执行一次 `ollama list` 留证。 |
| T13 Task 02 分层 | 已关闭 | Task 02 已把安装、headed 窗口、profile/锁/allowlist 作为前置技术验证，把 ACM/IEEE 真实合法登录留作最终验收硬门禁，并明确无合法账户时记录阻塞。 |

### 本轮必须继续修订的最小集合

1. **关闭 T1**：对账并更新 spec-014 的 spec、README、Task 08/09、验收签字、复盘和状态台账；若无法证明完成，则 Task 02 必须真实 No-Go，不能以合并 commit 替代门禁。
2. **关闭 T2**：至少给出 `schema_meta`、`conference_sources`、`search_sessions`、`paper_candidates`、`import_batches`、`import_items`、`task_events`（若使用）的建模表，列明 PK/FK、必要字段类型与 NOT NULL、唯一键组合、索引、schema version、UTC 格式、WAL/foreign_keys/busy_timeout 的具体值及 v1 初始化/升级规则。
3. **关闭 T3**：补 Batch 状态聚合真值表；列出 Item 从每个活动态进入 `failed` 的规则、取消语义；在“租约或条件更新”中作出唯一选择，并固定相应字段/期限或 CAS 条件。
4. **关闭 T5**：给出 connect/read/total timeout、最大重定向、最大响应头、最大 PDF 字节、下载并发、批次 worker、临时目录权限的明确默认值与环境配置名。
5. **关闭 T6**：用表格固定 `downloaded_temp → file_committed → metadata_committed → v1_indexed → v2_queued` 各 commit point、失败补偿、可重试性和启动对账动作；明确何时允许生成/返回 `paper_id`。
6. **关闭 T8**：建议 v1 明确禁用查询扩展，删除检索顺序中的强制模型步骤，先以原始查询做 DBLP/embedding/rerank；若必须启用，则补齐模型与结构化调用所有具体参数。
7. **关闭 T9**：固定请求/响应模型与 `{error: {code, message, retryable}}` 或等价结构，列出主要 HTTP 状态映射；把 item 动作移到 `/api/papers/import-items/{item_id}/login|resume`，或给出现路径可避免资源混淆的明确约束。
8. **关闭 T10**：列出允许的 ACM/IEEE exact origins（含必要的下载/CDN 域与跳转策略）、profile 权限和锁失败错误；Task 02 回填的 Playwright/浏览器版本应有固定文档字段供 Task 06 使用。
9. **关闭 T11**：固定冻结集文件路径与 schema、快照 hash 算法、文本截断上限、向量归一化/有限值规则、完整稳定排序键，以及与现有 KB embedding/index 任务共享资源时的最大并发。

### 复审风险与阻塞

- 风险仍为高：未关闭项直接关系到并发重复导入、状态漂移、外部下载资源耗尽和 API 契约不一致。
- 当前无业务代码变更，本次仍处在 spec 修订阶段。
- 下一次复审只需核对上述 9 项最小集合；无需重写已关闭的 T4/T7/T12/T13。

---

## 第三次技术复审（2026-09-04 11:08，Asia/Shanghai）

### 结论：打回

本轮新增了 schema v1 的 PRAGMA/唯一约束、下载数值上限、手动重定向与连接 IP 约束、saga 阶段表、查询扩展开关、统一错误体、规范 item 路径，以及文本截断/L2/tie-break。相比第二次复审已达到接近可实施状态，T4、T5、T7、T12、T13 已关闭，T11 的运行时排序部分也已关闭。

仍有 4 组相互关联的硬问题未关闭：Spec 014 文档基线未对账；SQLite 外键生命周期和租约/批次状态仍有歧义；查询扩展声明了可启用却没有完整启用契约；接口表与规范路径自相矛盾。它们会直接导致 Task 02 No-Go、历史任务被 TTL 级联删除、配置开启后行为未定义或前后端调用不同路径，故本轮仍不能放行代码实现。

### 第三次复审关闭矩阵

| 项 | 状态 | 第三次复审结论 |
|---|---|---|
| T1 基线对账 | 未关闭 | `main@e980cea` 已固定，但 `docs/sdd/specs/014-kb-reranker.md:5` 仍为 `实施中`，`docs/sdd/plans/014/README.md:24-25` 的 Task 08/09 仍为待执行。按 Task 02 自身规则只能 No-Go。 |
| T2 SQLite 契约 | 部分关闭 | schema v1、WAL、FK、5 秒 busy timeout、UTC、若干唯一索引和条件更新已明确；但“所有外键 ON DELETE CASCADE”与“TTL 删除 search session/candidate、保留导入状态”存在数据生命周期冲突。若 import item/batch 级联到候选/会话，搜索过期会删除持久导入历史和等待登录任务。需固定 FK 图：导入任务保存候选快照，且不得随搜索 TTL 级联删除。 |
| T3 任务状态机 | 部分关闭 | Item 主路径和租约字段已给出，但未固定租约期限/续租规则；Batch 的 `queued/running/waiting_login/partial_success/completed/failed/cancelled` 仍没有聚合真值表，`cancelled` 的触发和 Item 处理也未定义。 |
| T4 SSRF 防线 | 已关闭 | 手动逐跳、HTTPS:443、危险地址拒绝、allowlist 与实际连接 IP 约束均已固定。 |
| T5 出站资源上限 | 已关闭 | 10/30/120 秒、5 跳、64 KiB、64 MiB、3 workers、0700 与随机临时文件均明确，可测试。 |
| T6 saga/补偿 | 部分关闭 | 阶段与 commit point 已给出；但 `metadata_recorded` 把 SQLite 与 JSON PaperRecord 合写成一个 commit point，而它们不是同一事务；`v1_indexed` 行把“已成功”与“失败删除本次向量”混在一起。需拆成 SQLite task event、JSON PaperRecord、文件 rename、Qdrant v1 四个可独立失败点，并明确只删除本次新记录/向量，不触碰既有论文。 |
| T7 v1/v2 语义 | 已关闭 | v1 成功即完成、v2 独立事件且失败不撤销 v1 已固定。 |
| T8 查询扩展 | 未关闭 | 默认关闭是正确默认；但配置允许开启，文档仍没有具体模型、`think:false`、temperature、JSON schema、关键词数量/长度和超时。应明确 v1 “不实现查询扩展并移除配置”，或给出完整启用契约。不能保留一个开启后行为未定义的开关。 |
| T9 API 契约 | 未关闭 | 第 145–146 行接口表仍写 `/api/papers/imports/{item_id}/login|resume`，第 148 行又规定 `/api/papers/import-items/{item_id}/...`，存在直接冲突。错误体与状态码已固定，但还需列出至少本 spec 使用的稳定 code 枚举，避免实现时透传任意异常名。 |
| T10 Playwright 边界 | 条件关闭 | headed/profile 锁/产物禁用/allowlist 原则已足以进入 Task 02；exact origins、Playwright/浏览器版本、profile 权限与锁失败错误必须由 Task 02 回填到固定字段，未通过则不得进入 Task 06。 |
| T11 排序可重复性 | 条件关闭 | 标题 500、摘要 4000、L2、有限值降级和完整 tie-break 已固定。冻结集路径、schema、SHA-256 和时间仍须在 Task 04 第一次查看 rerank 输出前落盘；这是执行门禁，不再阻塞技术方案确认。 |
| T12 模型统一 | 已关闭 | Tech Lead 已统一为 `qwen3.8:27b-mlx`。 |
| T13 Task 02 分层 | 已关闭 | 浏览器能力探针与最终真实登录验收已分层。 |

### 放行前最小修订（仅 4 组）

1. **基线**：先把 Spec 014 的 spec、README、Task 08/09、验收签字、复盘和状态台账对齐 `e980cea`；否则 Spec 015 Task 02 只能记录 No-Go。
2. **SQLite/状态**：明确 FK 图，规定搜索 TTL 不删除任何 import batch/item/event；导入项持久保存候选快照。固定 lease 时长与续租/过期 CAS，补 Batch 聚合真值表和取消语义。
3. **查询扩展**：优先在 v1 明确不实现并删除两个 QUERY 配置和条件分支；若保留，则补齐具体模型与所有结构化调用参数。
4. **API**：把接口表统一为 `/api/papers/import-items/{item_id}/login|resume`，并列出稳定错误码集合；不允许同一评审文档内存在两套规范路径。

### 非阻塞但必须在对应 Task 关闭

- Task 05 实现前把 saga 表拆成 SQLite、JSON、文件和 Qdrant 四个独立失败点，测试逐点故障注入。
- Task 02 回填 exact origins、Playwright/浏览器版本、profile 权限与锁失败错误码；未通过保持 No-Go。
- Task 04 在第一次查看 rerank 输出前创建冻结集文件，记录 schema、冻结 UTC 时间和 SHA-256；Task 08 只消费该冻结版本。

### 风险定级：高

SSRF 主防线已清楚，剩余高风险集中在数据保留和文档单一真相：TTL 不能删除导入历史，API 不能同时声明两条 item 路径。完成上述四组最小修订后可进行快速复审。

---

## 第四次（最终基线）技术复审（2026-09-04 11:12，Asia/Shanghai）

### 结论：打回

本轮 Spec 015 的技术设计缺口已基本关闭：查询扩展从 v1 移除，API item 路径统一，SQLite FK 生命周期、候选快照、15 分钟租约/5 分钟续租和取消语义均已明确。T2、T3、T6、T8、T9 可放行；T10、T11 可按 Task 02/04 的冻结产物条件放行。

当前只剩 **T1 基线对账** 一个硬阻塞。新落盘的 `docs/sdd/reviews/014-acceptance-review.md` 明确结论为“**不通过（阻塞收口）**”：Task 08/09 尚未执行，缺少 Langfuse × Reranker 四组合、当前联合部署、真实运行健康、Tech Lead 签字和 Spec 014 复盘。因此，虽然实现代码已经合并为 `main@e980cea` 且全量测试 `346 passed`，它仍不是符合本项目 SDD 规则的“Spec 014 已完成稳定基线”。Spec 015 的 Task 02 按自身规则必须保持 No-Go。

### 指定项目最终判定

| 项 | 最终状态 | 判定依据 |
|---|---|---|
| T1 Spec 013/014 基线 | **未关闭，唯一硬阻塞** | Spec 013 已完成；Spec 014 spec 仍为实施中、Task 08/09 待执行，最新验收结论不通过。先完成 014 收口再进入 015 Task 02。 |
| T2 SQLite schema/FK/幂等 | 已关闭 | schema v1、PRAGMA、UTC、唯一约束、条件更新和恢复已固定；候选可随 session 清理，import batch/item 保留快照且不随 TTL 删除。 |
| T3 状态机/租约/取消 | 已关闭 | Item 主路径、登录、失败重试、15 分钟租约、最多每 5 分钟续租、过期恢复和不可取消 indexing/completed 已固定。Batch 状态必须继续由 Item 聚合，并在测试中覆盖混合状态。 |
| T6 saga/补偿 | 条件关闭 | 阶段、commit point、补偿和启动对账足以指导实现。Task 05 必须把 SQLite event、JSON PaperRecord、文件 rename、Qdrant 写入作为独立故障注入点，只清理本次新产物，不触碰既有论文。 |
| T8 查询扩展 | 已关闭 | v1 明确只用原查询，QUERY 配置已删除；未来查询扩展另立 spec。 |
| T9 API | 已关闭 | 表格和正文均统一为 `/api/papers/import-items/{item_id}/login|resume`，Pydantic、错误体和状态码边界已固定。实现时稳定 code 取 spec 已列错误码及各状态机错误，不透传异常名。 |
| T10 Playwright | 条件关闭 | headed、origin allowlist、profile 锁、凭证和 trace/HAR/video/download 边界已固定；exact origins、版本与权限由 Task 02 实测回填，失败即 No-Go。 |
| T11 排序可重复性 | 条件关闭 | 500/4000 截断、L2、异常降级、完整 tie-break 已固定；冻结集路径/schema/UTC/SHA-256 必须在 Task 04 首次查看 rerank 输出前落盘。 |

### 唯一放行动作

先完成 Spec 014 Task 08/09，并由 tester 形成“通过”验收、Tech Lead 签字、联合部署与复盘落盘；随后把 Spec 014 spec、README、task 和状态台账统一为 `已完成`。完成后只需对 T1 做一次证据复核，不需要再次改动 Spec 015 技术设计。

### 风险定级：中

Spec 015 设计风险已经通过四轮修订收敛。当前风险不是 015 技术方案，而是依赖基线尚未满足项目自身的完成定义；不得用“代码已合并/测试已通过”替代缺失的 Spec 014 观测、部署和验收门禁。

## 第五次（T1 证据复核）技术复审（2026-09-04）

### 结论：通过

第四次复审指定的**唯一放行动作**已全部完成。本次仅对 T1 做证据复核，按该次复审约定**不改动 Spec 015 技术设计**。

| 放行动作 | 完成情况 | 证据 |
|---|---|---|
| 完成 Spec 014 Task 08/09 | 已完成 | Task 08 转「完成（tester 验收通过）」；Task 09 转「完成」，含最终执行结果与变更日志 |
| tester 形成「通过」验收 | 已完成 | `docs/sdd/reviews/014-acceptance-review.md` 结论「通过」；四组合真实 KB ask 均完整收口至 `done` |
| Tech Lead 签字 | 已完成 | 同上报告末尾「Tech Lead 签字」栏，结论通过（主会话代行，已标注非独立评审） |
| 联合部署与复盘落盘 | 已完成 | `docs/sdd/retro/2026-09-04-spec-014-reranker-retro.md` |
| Spec 014 spec / README / task / 状态台账 统一为已完成 | 已完成 | spec 状态转 `已完成`；README 与 spec 任务表 Task 08/09 均转完成；`spec-status-changelog.md` 已追加流转记录 |

### T1 基线对账复核

| 对账项 | 复核结果 |
|---|---|
| Spec 014 spec 状态 | `已完成` |
| Spec 014 Task 08 / Task 09 | 均 `完成` |
| Spec 014 验收结论 | 通过（tester） |
| Tech Lead 签字 | 已填（代行，已标注） |
| Spec 014 复盘 | 已落盘 |
| 联合部署证据 | 四组合真实 KB ask + 停服降级/恢复闭环 |

补充：本轮 Spec 014 收口还修复了一个由 `8c1c3ae` 引入的回归（`create_chat_model` 默认 `reasoning=True` 导致强制下发 `think=true`，`6daa498` 已改回默认 `None`），并以 `deepseek-coder-v2:16b` 复测 KB ask 与普通聊天均完整收口，全量回归 `351 passed`。基线质量优于第四次复审时的状态。

**T1 关闭。** Spec 015 Task 02 的基线前置已满足，可进入 Go/No-Go 验证。

### 遗留提示（不阻塞基线）

- Spec 014 验收签字为主会话代行（非独立评审），已如实标注；若后续要求严格独立性，应重跑该签字环节。
- `run_chat` 默认 `think=True` 在 `OLLAMA_ROUTE=direct` 下仍会使不支持 thinking 的模型返回 HTTP 400；默认路由为 `langchain`（该路径已修复）。已记为 Spec 014 复盘遗留项，不影响 Spec 015 基线。

### 风险定级：低
