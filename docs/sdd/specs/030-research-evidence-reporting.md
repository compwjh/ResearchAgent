# Spec 030 — 跨论文证据矩阵与深度研究报告

## 状态

**当前状态：实施中（2026-10-29 内容充分性修订；用户已确认，独立需求/技术门禁GO；原交付记录保留）**

## 一句话目标

把 Research Task 已确认的目录、摘要和全文证据组织成可追溯的跨论文比较矩阵，并生成标明证据来源、冲突、局限和覆盖缺口的深度研究报告。

## 背景与依赖

- Spec027 只产出初步报告，Spec029 才能提供可定位全文证据。
- 长报告必须先形成结构化 Claim/Evidence，再合成正文，不能让模型凭长上下文一次生成不可追溯结论。
- 本 Spec 依赖 Spec027；全文能力启用时依赖 Spec029，但仍允许对仅有摘要的任务生成降级报告。

## 数据模型

| 实体 | 关键字段 | 约束 |
|---|---|---|
| ResearchClaim | claim_id、task_id、topic、statement、confidence、status | 每个结论独立记录 |
| ClaimEvidence | claim_id、paper_id、evidence_level、chunk_id/page、quote_digest、stance | supports / contradicts / contextual |
| ComparisonDimension | id、label、definition、order | 由计划确认，版本内稳定 |
| PaperComparisonCell | paper_id、dimension_id、summary、evidence_ids | 无证据时为空，不猜测 |
| ResearchReport | task_id、plan_version、report_version、markdown、status | 只读、版本不可覆盖 |
| CitationManifest | report_id、citation_no、paper_id、evidence_ids | 与报告编号一一对应 |

## 接口与产物

| 动作 | 输入 | 成功返回 | 失败 |
|---|---|---|---|
| POST /api/research-tasks/{id}/evidence-matrix | dimensions 可选 | 202 WorkItem | 409 证据不足/任务状态 |
| GET /api/research-tasks/{id}/evidence-matrix | plan_version | 结构化矩阵与缺口 | 404 |
| POST /api/research-tasks/{id}/reports | outline/profile | 202 报告生成 | 409 matrix 未就绪 |
| GET /api/research-tasks/{id}/reports/{version} | format=html/markdown/json | 只读报告或下载 | 404；406 |

- 报告语言默认跟随研究任务；标题和正式论文名称保留原文。
- Markdown 是权威可移植产物，HTML 由同一结构渲染，JSON 提供引用 manifest；不做富文本编辑。
- 每条主要结论至少引用一条 evidence；仅标题级候选不得进入方法/结果比较。

## 边界与失败场景

- 多论文互相矛盾、证据等级不同、同一切片支持多个 Claim、引用文档删除、报告生成中断。
- 模型输出必须通过 Claim/Evidence Schema 和 citation manifest 校验；不存在的论文、页码或 chunk 直接拒绝。
- 证据不足时保留空单元格并列入 limitations，不使用常识补齐论文事实。
- 新报告版本引用旧证据时保留来源；不得覆盖旧报告历史。

## 明确不做

- 不做多人协同编辑、富文本编辑、自动投稿或参考文献格式全集。
- 不重新实现全文检索、embedding 或 reranker。
- 不把报告全部自动写入长期记忆。

## 验收方式

- 固定相互支持/冲突/缺失证据样本生成矩阵，所有单元格可追溯。
- 报告每个主要 Claim 的 citation manifest 可回查论文与证据等级。
- Markdown、HTML、JSON 三种视图语义一致；恶意论文文本不能注入界面或改变 Agent 权限。
- 最终 Task 执行一次全量回归、浏览器验收、部署和复盘。

## 产品使用步骤

1. 在已完成候选评估的 Research Task 中打开“证据矩阵”，查看每篇论文与比较维度的支持、反驳或缺失状态。
2. 点击矩阵中的证据编号，展开论文、证据等级、页码或切片定位；缺失证据保持为空并显示覆盖缺口。
3. 矩阵校验通过后点击“生成报告”，系统创建不可覆盖的新报告版本；生成期间显示任务状态，失败可重试且不发布半份报告。
4. 报告完成后可查看 Markdown、HTML 和 JSON 三种只读视图，三种视图共享同一引用清单；需要迁移或复核时下载 Markdown/JSON。

## 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身 | 200k | 主会话 | Claim/Evidence 与报告边界 |
| 产品经理 | `qwen3.5:9b` | 32k | `Task(doc-updater)` | 报告阅读旅程 |
| 开发主管 | `qwen3.8:27b-mlx` | 32k | `Task(architect)` | 可追溯性与引用评审 |
| 初级开发 | `qwen3.8:27b-mlx` | 32k | 分端开发 Agent | 证据、报告和界面实现 |
| 测试 | `qwen3.5:9b` | 32k | 分端 tester + `Task(tester)` | 引用与导出验收 |

## 任务计划

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec030 | 本文件 | — | 完成 |
| 02 | 冻结 Claim/Evidence 与报告协议 | [`task-02-evidence-report-contract.md`](../plans/030/task-02-evidence-report-contract.md) | Spec027；全文场景依赖029 | 已完成（GO_FOR_TASK03） |
| 03 | 实现证据矩阵与校验 | [`task-03-evidence-matrix.md`](../plans/030/task-03-evidence-matrix.md) | 02 | 已完成 |
| 04 | 实现报告生成、版本和导出 | [`task-04-report-generation-export.md`](../plans/030/task-04-report-generation-export.md) | 03 | 已完成 |
| 05 | 实现报告工作台与引用交互 | [`task-05-report-workspace-ui.md`](../plans/030/task-05-report-workspace-ui.md) | 04 | 已完成 |
| 06 | 最终评审、回归、部署与复盘 | [`task-06-review-regression-deploy.md`](../plans/030/task-06-review-regression-deploy.md) | 02–05 | 已完成 |

| 07 | 内容质量合同与运行路径审计 | [Task07](../plans/030/task-07-quality-contract.md) | 本修订确认/独立评审 | 已完成（独立GO） |
| 08 | 后端实质报告生成与质量门禁 | [Task08](../plans/030/task-08-substantive-report-generation.md) | 07 | 实施中 |
| 09 | 前端报告质量与恢复反馈 | [Task09](../plans/030/task-09-report-quality-feedback.md) | 08接口冻结 | 待执行 |
| 10 | 内容质量最终验收与交付 | [Task10](../plans/030/task-10-quality-acceptance.md) | 08、09 | 待执行 |

## 评审记录

- 需求评审：`docs/sdd/reviews/030-requirement-review.md`（通过；Task02 合同门）
- 技术评审：`docs/sdd/reviews/030-tech-review.md`（通过；Task02 合同门）
- 验收评审：`docs/sdd/reviews/030-acceptance-review.md`（通过；P1 已修复并复验）

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-12 | 架构师（自身） | 创建证据矩阵和深度报告 Spec |
| 2026-09-17 | 架构师（自身） | 用户确认 Spec030，进入实施阶段；按 Task02–06 顺序开发，Task 阶段仅运行定向测试。 |
| 2026-09-17 | Task06 收口审计（Luna high） | 完成唯一全量回归、运行时与浏览器 smoke、固定矩阵/manifest/三格式/安全审计；发现 `EvidenceReportError.message` 缺失导致未知报告路由 500 的 P1，保持实施中并退回主 Agent 修复。 |
| 2026-09-17 | 主 Agent / Task06 | 修复报告错误响应与矩阵未就绪状态映射，补齐旧资源版本兼容标记；全量回归 2504 passed、1 skipped，部署 smoke 全部通过，Spec030 收口为已完成。 |


## 2026-10-29 修订：研究报告内容充分性

状态：待确认。用户已采用Grilling Q1–Q15推荐，待共同理解确认及本修订独立需求/技术评审；此前评审不自动覆盖本修订。仅文档规划，无代码、测试运行或部署。决策详见[Grilling记录](../plans/030/2026-10-29-report-quality-grilling.md)。Spec042是离线评测，不改变其目的；本次沿030修订并核对034生成接缝，不另起重复Spec。

### 目标

先实际交付一份至少5篇真实论文、有逐篇分析与跨论文比较的中文研究综述；正文至少1500中文字符，且有实质内容和可追溯引用。字符底线不能代替质量判断。现有源码允许空section summary、缺比较cell以及确定性目录降级，这些是审计风险；尚无具体失败任务ID，不将其认定为用户某份短报告的实测根因。

### 数据模型与接口

复用ResearchClaim、ClaimEvidence、ComparisonDimension、PaperComparisonCell、ResearchReport和CitationManifest；沿既有ResearchTask/Session、WorkItem及既有执行器、作业进度与不可变Artifact，不新建第二报告框架。

本修订要求报告保留质量核验结果：正文字符计数、逐篇/比较/综合发现覆盖、引用有效性、证据等级、缺项、补写次数，以及可取得的实际模型/回退原因/用量。优先复用现有持久化字段；具体schema与事件契约在实施前技术门禁冻结，不能仅依赖内存状态。

沿既有030的evidence-matrix、reports创建/查询/三格式导出及034会话入口，保持历史版本可读；不另建公开API。报告生成受理不等于成功，正式报告只在质量/引用校验通过后发布。失败草稿独立于正式版本展示，具体响应/状态增量在技术评审冻结后实现。

### 生成流程与边界

1. 当前任务已选证据→逐篇结构化整理→跨论文比较及综合结论→分节写作→统一校验→发布新正式版本。保留现有证据安全渲染，不直接把未验证模型长文作为最终成果。
2. 至少5篇真实、相关、有可用证据的论文；不足时仅在批准范围/预算内有界补搜，不能扩主题或无关凑数；仍不足明确部分完成，不能假报达标。
3. 摘要级可以形成合格综述，明确标识证据与局限；全文可用时补强。无全文不应退化为只能列目录，也不得声称摘要支持全文实验细节。
4. 结构包含研究问题、证据范围、逐篇方法/结论/局限、跨论文比较、综合发现、研究缺口及引用。至少3条有证据支持的综合发现；不足则明确缺口并判内容不充分，不强凑。
5. 正文至少1500中文字符，目录/引用清单/附录不计。技术门禁须冻结可复现计数口径；重复段落/标题堆砌不算实质分析。每项主要事实/比较/综合发现绑定有效论文和证据，未知明确未知，分歧如实并列。
6. 缺项定向补写最多两轮，且服从任务总预算与阶段调用/超时上限。失败保留草稿和诊断并提供重试，不发布半份或截断正文。目录元数据fallback可以保留为降级资料，但不能冒充正式研究报告成功。
7. 沿任务选择模型及已有回退链，记录实际模型与回退原因，不新建独立模型设置。用量不可取得则显示未知，不捏造计量。
8. 显示整理证据/跨论文比较/生成章节/校验报告/完成或失败、已用时间和下一步操作；后台继续、离页不取消，沿既有恢复机制。固定倒计时须有实测依据，本次不承诺。
9. 旧报告不覆盖，重生成创建新版本，不自动重跑所有历史任务；正文、HTML、JSON仍共享同一引用/版本事实。

### 产品步骤与核心验收

Agent先固定可复现真实主题，从自然语言入口完成Intake、计划审批、搜集、证据整理和报告生成，观察阶段状态，直到新正式报告可查看和下载。检查至少5篇、1500中文字符及上述全部内容/引用门禁，再把实体ID、模型、原始请求响应、字数/质量核验及产物路径落盘。验收主题在可行性阶段实测选择，不用mock或内部函数替代。

仅Agent真实E2E成功后提供人工案例：逐步点击/输入、实际反馈、等待/进度提示、下一步、失败恢复、正文/下载位置；准备度至少9/10且无核心阻塞，不能把READY_FOR_USER等同用户已验收。回归覆盖短报告、字数够无比较、引用无效、证据不足、模型失败/预算耗尽/补写上限及历史版本保留。Task仅定向测试，最终候选全量、独立验收/签字、实际部署成功后收口。

### 任务拆分方向与执行边界

先核实真实任务/实际运行路径并冻结质量/状态/预算合同；后端实现证据整理、分节生成、校验及恢复；前端展示阶段、草稿/正式版本与错误指引；最后真实E2E、分端/全量、独立评审/部署和人工材料。各任务细节在共同理解后、实施前补入现有030任务体系，不复用旧评审结论。

主会话承担架构与编排；doc-updater负责使用步骤，backend-dev/frontend-dev分端编码，backend-reviewer/frontend-reviewer分端评审，backend-tester/frontend-tester分端验证，tester总验收及architect独立签字。模型按当次用户指派，不固化长期配置；不分派不存在的角色。

### 明确不做

不以凑字数替代分析，不放宽来源/引用/全文安全门禁，不自动扩大研究范围，不重写历史成果，不引入第二执行器/聊天框架/模型配置体系，不扩展Spec042评测平台，不自动push或合并main。

变更记录：2026-10-29｜架构师（自身）｜沿既有Spec030追加内容充分性修订草案，待共同理解及独立评审，不实现代码。

### 2026-10-29 用户确认与执行配置

用户明确“共同理解”，本修订产品范围已获授权，无须再次重复确认；独立需求/技术门禁通过前保持待确认，不修改业务代码。门禁通过后转已确认并实施；若仅发现范围内实现问题，修复复审，不重新询问用户。

本轮角色配置已现场读取：architect/doc-updater/backend-dev/frontend-dev/tester的长期model字段均为Deepseek-V4.1-Flash。本轮沿用户最近明确指定，子Agent临时覆盖为Luna xhigh，不改角色配置文件；上述历史执行配置仅保留为当时记录。

| 角色 | 本轮选用模型 | 上下文上限 | 分派 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身 | 200k | 主会话 | 决策/编排/文档同步 |
| 文档更新 doc-updater | 用户临时Luna xhigh | 32k | 独立子Agent | 使用步骤与验收案例 |
| 独立评审 architect | 用户临时Luna xhigh | 32k | 独立子Agent | 需求/技术门禁及最终签字 |
| 后端开发 backend-dev、前端开发 frontend-dev | 用户临时Luna xhigh | 各32k | 分端子Agent | 仅修改各自端及测试 |
| 回归 backend-tester/frontend-tester、总验收tester | 用户临时Luna xhigh | 各32k | 分端/独立子Agent | 定向/最终回归、真实验收裁决 |

新修订评审与历史记录分开落盘：需求`030-report-quality-requirement-review.md`、技术`030-report-quality-tech-review.md`、最终验收`030-report-quality-acceptance-review.md`（均位于reviews；当前未产出的文件不得视为已通过）。

本轮技术候选详见[质量合同](../plans/030/2026-10-29-report-quality-contract.md)，待独立评审，不宣告已通过。

2026-10-29独立首轮门禁：本修订[需求评审](../reviews/030-report-quality-requirement-review.md)与[技术评审](../reviews/030-report-quality-tech-review.md)均BLOCK；待补语义验收rubric、API/版本原子预留/恢复、全文证据和有界schema预算合同。用户范围确认继续有效，不重复请求确认；修订后独立复审前不进入代码实现。

2026-10-29门禁最终：需求二轮GO、技术三轮GO，历史BLOCK保留。修订由待确认转已确认并进入实施中；Task07合同门通过，Task08从独立质量校验模块开始分步实现，非宣告报告已能生成。

### 2026-10-31 范围内缺陷与复验条件

真实自然语言案例 `387a5090b27550c59de86adb415eb26e` 已发布 2,920 CJK 正文及三个校验哈希一致的产物，但独立内容评审因认证主题选集偏题判 FAIL；机器结构 PASS 不代表本 Spec 验收通过。证据见 [案例与内容评审](../plans/030/artifacts/20261031-natural-e2e/content-review.md)。

本次按既有“相关论文、不用无关论文凑数”边界修复，不新增产品目标、公开接口或语义判定服务：

- 查询必须保留用户独立研究主题；报告目标仍保持用户原文，不能以查询修正覆盖目标。
- 来源与 ID 合法仅说明可引用，不能代替逐篇保留决定及既有相关度阈值；聚合引用和数量补足不能绕过相关性评估。
- 不足五篇时保留真实短缺，仅沿既有批准范围和预算恢复，不降低阈值或扩大主题冒充完成。
- 自然语言字数要求不得被解析为论文篇数；未支持的显式论文数量继续澄清，不静默采用默认值。

复验须覆盖主题进入查询、低相关聚合引用/补足被拒绝、数量与字数区别，以及部署后新自然语言案例的真实报告内容评审。既有产物和失败证据保留；Spec 继续实施中。
