# Spec 030 研究报告内容充分性合同

状态：Gate 2 修订中；按 2026-10-29 独立评审 BLOCK 项修订，待同评审者复审；不替代 Spec 030 用户确认。
日期：2026-10-29。

## 已确认的产品决定

- 本次沿 Spec 030 修订，不扩展 Spec 042，也不自动重跑旧任务。Task 02–06 与它们的完成记录保持历史状态。
- 首个正式交付必须基于当前任务范围内至少 5 篇已选、已验证且有可用证据的真实论文。摘要级证据允许形成报告，但每条结论必须明确受摘要证据限制；不能把目录元数据写成方法或实验结论。
- 报告需含研究问题、证据范围、逐篇方法/发现/局限、跨论文比较、综合发现、研究缺口、引用。至少 3 条综合发现必须有证据支持；证据不支持时标记缺口，不补造结论。
- 正文至少 1,500 个 CJK 汉字表意字符。字符数只是必要条件，不能以重复文本、目录卡片、标题或引用清单凑数。
- 先整理逐篇证据，再比较与综合，再分节写作，最后统一校验和发布。缺项可以定向补写，最多 2 轮；仍不合格时保存诊断草稿，不发布正式报告。
- 复用当前 ResearchTask、ResearchWorkItem、AgentRunner、模型选择/回退、Claim/Evidence/Comparison、ResearchReport、ResearchArtifact 和会话通知链；不建第二套报告/作业/模型配置系统。
- 不覆盖旧报告。目录元数据确定性 fallback 可保留作诊断草稿，但无论其字数或结构如何，都不能冒充正式研究报告。

## 正文字符计数

计数方法版本固定为 report-quality-v1，字符集冻结为 CJK 统一/兼容表意文字范围：3400–4DBF、4E00–9FFF、F900–FAFF、20000–2A6DF、2A700–2B73F、2B740–2B81F、2B820–2CEAF、2CEB0–2EE5F、2F800–2FA1F、30000–3134F、31350–323AF。每个落在范围内的 Unicode 码点计 1 个字符；新扩展区只有新版本计数方法才能增加。不计 CJK 标点、拉丁字母、数字、空白、Markdown/HTML 标记、标题、目录、引用/参考文献、附录、论文/Evidence/Artifact ID、页码、链接和代码块。只把结构化正文文本字段交给计数器，因此格式标记与引用编号不可能增加结果。报告 JSON 同时保存字符数与计数方法版本，以便复算。

正文包括研究问题的解释、证据范围说明、逐篇分析、跨论文比较、综合发现及研究缺口的可读文本。来源未陈述的方法/结果必须标为“来源未说明”或等价的结构化未知值；该说明不算作方法/结果发现。

## 同一规范报告的最小增量字段

沿用 `ResearchReport.report_json` 作 canonical JSON，新增可选 `report_content`、`quality_validation`、`generation`；不加 SQL 列/表或公开端点。所有模型输入/输出都用以下有界 schema，超过上限按 schema 错误处理：

- `report_content.schema_version="research-report-content-v1"`；必需字段：`research_question:{text:1..2000}`、`evidence_scope:{text:1..4000,paper_ids:5..64}`、`paper_analyses:5..64`、`cross_paper_comparisons:1..16`、`synthesis_findings:3..16`、`research_gaps:0..32`。paper_ids 唯一且属于批准选集。文本长度均按 Unicode code point；ID 长度 ≤200。整体 JSON UTF-8 ≤512 KiB。
- 每个 `paper_analyses` 元素为 `{paper_id,method,findings,limitations}`，`paper_id` 是 1..200 字符且唯一、属于当前批准选集。三个分析字段均为 `{status:"supported"|"not_stated"|"unavailable",text:0..4000,evidence_ids:0..32}`；`supported` 要求非空文本和至少一个有效 Evidence ID；另两种状态要求空文本/空 ID，由 renderer 用固定短标签呈现，不计正文。每篇至少一个字段为 supported。所有 Evidence/paper/dimension/finding IDs 为 1..200 字符、字符串数组去重。
- 比较元素为 `{dimension_id,paper_ids:2..64,statement:1..3000,evidence_ids:2..32}`；发现元素为 `{finding_id,statement:1..3000,paper_ids:2..64,evidence_ids:2..32}`；缺口元素为 `{statement:1..2000,evidence_ids:0..32}`。paper_ids/evidence_ids 去重。比较和发现的每个 Evidence ID 必须映射到该元素声明的至少两个不同 paper_id；dimension 必须属于当前批准计划，finding_id 唯一。
- 服务端从当前 `research_claim_evidence` 的 `ClaimEvidence`（task_id、plan_version、paper_id、status、evidence_level、locator）解析 ID→paper、来源等级及 provenance；只接受当前 plan 的 available（并通过既有验证） 项，不接受模型自报映射。摘要/目录与全文等级从 Evidence 对象派生，绝不把 catalog 字段升级为摘要/全文结论。fulltext 引用必须再经 `EvidenceMatrixService` 检查 locator，并匹配同一 claim/task 的 `EvidenceUpgrade` document/chunk provenance；不以 candidate_id 与 KB document_id 相等作为关联条件，也不扩建全文检索路径。AgentRuntime synthesis input 从这个已校验证据集合构建，允许其真实 evidence_level，移除“全文定位符一律禁止”的冲突约束；无有效 fulltext Evidence ID 时就按摘要/目录等级写，不声称报告消费了全文。
- `quality_validation` 固定为 `{schema_version:"report-quality-v1",status:"pass"|"fail",cjk_count:integer>=0,count_method:"report-quality-v1",paper_count:0..64,comparison_count:0..16,supported_finding_count:0..16,invalid_evidence_count:integer>=0,failure_codes:0..32,revision_count:0..2}`；paper_count 只计当前选集中至少一项 supported block 且其 Evidence 全有效的逐篇记录；comparison_count/supported_finding_count 只计映射通过的比较/发现。每个 failure_code 为 1..64 字符。数值全部由服务端基于批准选集、Evidence 映射和最终 renderer 正文计算；只描述机器可判的结构/来源/计数门禁，不声称证明语义质量。
- `generation` 固定为 `{report_version:integer>=1,plan_version:integer>=1,path,output_disposition,published:boolean,request_key:UUID,work_item_id:ID,agent_run_ids:0..32,provider:string|null,model:string|null,fallback_reason_code:string|null,budget}`；provider/model ≤128 字符、reason ≤64 字符，path 仅 `agent_runner|deterministic_fallback|matrix_api`，`output_disposition` 为 `accepted|rejected|not_run`。`budget` 固定为 `{runs:list[0..32],report_totals,task_totals,tokens:integer|null,cost:number|null}`；每个 run 条目 `{agent_run_id,model_loops_used:0..40,model_loops_limit:40,tool_calls_used:0..160,tool_calls_limit:160,elapsed_seconds:number>=0}`；`report_totals` 为 `{model_loops_used,tool_calls_used,elapsed_seconds}` 的关联 run 求和；`task_totals` 为 `{model_loops_used:0..160,model_loops_limit:160,tool_calls_used:0..640,tool_calls_limit:640,elapsed_seconds,max_seconds:5400}`，代表 AgentRuntime 的 ResearchTask 累计。不可得的 tokens/cost 为 null。provider/model/reason 无事实时为 null，不推断。实际 path 和 output disposition 必须由 AgentRunner 的结构化结果字段记录，不能从 run ID、Artifact 或 completed 事件推断。GET/POST 的 `quality_status` 来源为 quality_validation.status（未运行时 pending、旧版/matrix 为 unvalidated）；`published` 直接反映 generation.published，且仅当 report status=completed、三类 Artifact 与最终消息已持久时可为 true；`reason_codes` 是服务端稳定 failure_codes 与 fallback_reason_code 的去重集合。

历史 report_json 无这些字段时仍可读，统一显示“旧版，未按本质量合同核验”；缺字段不等于 pass。

## 状态、发布与版本身份

- 自然语言完整流程和 POST 重生成都调用同一 `ResearchStore.reserve_report_generation` 逻辑。自然语言路径在 `Orchestrator` dispatch synthesizer WorkItem 前调用，服务器生成 request_key 并把原 WorkItem 的旧 plan-derived report_version 替换为 reservation version；POST 将已批准 selection 附到现有 synthesis WorkItem，或创建同 task_type 新 row。所有模型报告都先 reservation 再调用 AgentRunner。
- 现有 `POST /api/research-tasks/{id}/reports` 保留原请求体 `{plan_version?,report_version?,title}`、路径、现有 202、422 参数错误及既有服务错误映射。对有 ResearchSession 的任务，`routes_research.py → ReportGenerationService.generate → ResearchStore reservation + ResearchWorkItem(task_type=synthesize_preliminary_report) → ResearchService 现有 ThreadPoolExecutor → Orchestrator report-only 分支 → AgentRunner → ReportSynthesisService` 只受理并继续既有执行链，不同步声称生成完成。每个 report_version 有独立 WorkItem row，但复用相同 task_type/role/ResearchStore/Orchestrator/AgentRunner；初次自然语言执行使用其已有 queued/running synthesis item，completed item 不回退，后续重生成新增相同 task_type 的 row。report-only worker 不重开或改变已 completed/partial 的 ResearchTask。响应保留旧字段 `report_id,research_task_id,plan_version,report_version,status,limitations`，并增加 `quality_status,published,reason_codes,report_url`；report_url 固定为 `/api/research-tasks/{task_id}/reports/{report_version}?format=json`。初始为 `status=generating,quality_status=pending,published=false`。POST 接受可选 UUID `Idempotency-Key` 请求头；前端对一次主动重试生成新 key，同一网络重试复用旧 key。服务端持久化 key；同 key 查询/恢复同一个版本与 WorkItem。若另一个 key 到达时该 task 已有 generating 版本，返回 409 `REPORT_GENERATION_IN_PROGRESS` 并给现有 report_url，不并发生成。为兼容不带 header 的旧客户端，若相同 task/plan/title 已有 generating 版本则加入该版本；无活动版本时视为新请求。传入 `report_version` 仅可与已预留版本相同，否则 409 `REPORT_VERSION_CONFLICT`。
- 无 ResearchSession 的旧矩阵调用保留同步 renderer 和既有请求/响应键，路径记 `matrix_api`，结果标 `draft`、`published=false`、`quality_status=unvalidated`；它不进入实质报告质量门禁，也不冒充正式 Artifact。GET `/api/research-tasks/{id}/reports/{version}?format=json|markdown|html` 保留路径和格式，可读 generating/draft/partial/failed/completed 版本并返回真实状态；缺版仍为 404，非法 format 仍为 406。JSON 草稿包含 `published=false` 和 reason codes；Markdown/HTML 草稿只作为版本化读取内容。旧版下载语义不改变。现有 `GET /api/research-sessions/{session_id}/artifacts` 与 artifact download 只列出/下载 published 版本；该过滤不能影响其他已发布版本。
- 对 session-backed 报告，报告行是 canonical 版本预留槽：在单个 SQLite `BEGIN IMMEDIATE` 写事务内读出该 task 的 reports 并解析已有 `generation.request_key`；命中则返回原 report_id/version/work_item_id，未命中则在同事务中读取 ResearchReport 与 Artifact 最大版本并插入 `status=generating` 的 ResearchReport 行，同时复用已有 active synthesis WorkItem 或创建一条 queued 的同类型 `synthesize_preliminary_report` row，并将 reservation ID/key/version 写入其 input。现有 `UNIQUE(research_task_id,report_version)` 是并发最终仲裁；冲突时回读已胜版本，不得盲目递增重试。`next_report_version()` 单独读取不是原子分配，不可用于该路径。新增 store 方法只允许 `status=generating` 的行原位推进；终态 draft/partial/failed/completed 后不可再改。现有 report/workitem schema 与唯一约束足够，无 schema migration。
- report_version 预留后写入该版本 WorkItem input，覆盖当前把 `plan_version` 填给 report_version 的接缝；plan_version 独立不变。该版本贯穿其 AgentRun 输入/输出、canonical ResearchReport、Artifact、消息幂等键 `research-report:{task}:{version}`、通知、POST 与 GET。`request_key`、report_version、当前 work_item_id 随 report row/WorkItem 持久化；同 report_version 通常复用同一 WorkItem。若现有 task-recovery 已将旧 WorkItem 推到不可逆的 interrupted 终态，则仅新建同类型 successor row 绑定原 report reservation；不回退终态、不增 report_version、不重置历史 AgentRun/counters。用户主动新版本才分配新 reservation。
- 重启恢复：启动恢复扫描复用现有 ResearchStore/ResearchService executor；提交 generating reservation 对应的 queued WorkItem。stale running 行先由现有 lease/retry 状态处理；若 task-recovery 已将 WorkItem 标为不可逆 interrupted，则创建同 task_type 的 successor row 并回绑原 reservation，绝不回退 terminal state。AgentRun 已有完成输出则复用该输出，不再调用模型；canonical report 已落库则重跑确定性 renderer，并按 task/version/type 比较现有 Artifact hash 后补齐；消息先按 `research-report:{task}:{version}` 创建 pending 幂等记录。`published=false` 期间 artifact 列表/下载隐藏该版本，pending message 不是完成通知。三类 Artifact 与 pending 会话消息均已持久后，才将 report 原位推进到 completed+published；随后将同一消息标 completed，再幂等补发 completed 通知。若发布标记后消息状态/通知失败，按同 key 补齐；若任一先前写入失败，保留 generating 并记录稳定恢复原因。草稿/失败从同版本恢复，不增加 version 或重置 revision/call/elapsed；用户重新发起质量重试才创建新版本。
- 只有 AgentRunner 模型候选经现有 output/evidence validation、机器门禁 pass，且正式交付链可幂等完成，才发布。缺 5 篇、1 项比较、3 项受支持综合发现或 1,500 CJK 时按下方唯一状态表保存结果与原因码；fallback 不发布。通过门禁的结构化 report_content 用固定 renderer 生成 Markdown/HTML 属正常路径。

## 进度、预算与恢复

- 所有初稿、AgentRuntime schema 重试、最多 2 轮质量定向改写、请求重试与进程恢复沿用同一 reservation 和 ResearchTask 已消耗预算。每 run 上限 40 loops/160 tool calls；ResearchTask 合计 loops/calls 上限不得超过现有160 loops/640 calls，活跃秒上限按下方有效预算规则计算，包含本任务此前 AgentRuns，质量路径不请求 extension、不提高 cap。`report_totals` 是同 report_version 的 AgentRun usage 求和；`task_totals` 是 AgentRuntime 从 ResearchTask 持久计数得出的全任务累计。revision_count 只计定向质量改写；schema retry 不计 revision，但照常消耗 loops/calls/time。恢复时将持久 counters 传回 BudgetSnapshot，不清零。到任一 task cap 或 revision_count=2 停止并按下方唯一状态表落终态与稳定 reason code；无法取得 token/cost 时为 null。
- report 事件沿用 ResearchEvent，payload 只允许阶段、report_version、revision_count、累计与上限字段、elapsed、reason_code、AgentRun ID、request_key；禁止 prompt、模型长输出、思维链和敏感数据。阶段：evidence_review、comparison、drafting、quality_check、targeted_revision、published、draft_saved、failed。
- 页面离开不取消 ResearchTask；SSE 用现有游标恢复显示状态。session-detail GET 和 events GET 有协调/重试副作用，不作为无写探测。UI 不显示无测量依据的倒计时。

## 兼容性与影响面

- 数据库：research_reports.report_json 已是 JSON 文本，status 已含 draft/generating/completed/partial/failed；research_events、ResearchWorkItem、AgentRun counters 和 research_artifacts 已存在。按此合同无需 SQL schema migration；落地时先核实目标 checkout 的真实 schema。
- API：POST session-backed 接入现有 WorkItem/executor 并异步继续；保留 body/path/旧响应字段，新增响应字段与可选 Idempotency-Key header；GET 可读草稿但明确 published。artifact list/download 对未发布版本隐藏。保留既有错误码；版本冲突/已有生成分别新增 409 `REPORT_VERSION_CONFLICT`、`REPORT_GENERATION_IN_PROGRESS`。无需 migration，旧 JSON 仍读。
- Artifact/会话：复用三类 ResearchArtifact 与消息/通知幂等键。正式 Artifact 内容必须由同一 canonical ResearchReport 确定性渲染；发布标志前 UI/下载不暴露其为正式件。草稿通过 GET 的 JSON/Markdown 视图读取。
- 主要源码接缝：`routes_research.py` 的 POST/GET 与 session artifact list/download；`ReportGenerationService.generate/read`；`orchestrator.py::_build_synthesis_matrix_context` 的现有 synthesizer WorkItem 输入与恢复；`EvidenceMatrixService.read_matrix` 对 ClaimEvidence/EvidenceUpgrade provenance 的既有校验；`AgentRuntime` 的 synthesizer prompt/output schema/budget 及结构化实际分支记录；`ReportSynthesisService` 的 canonical→Artifact→message 投影；`ResearchStore` 的原子 reservation/条件状态推进及 report events。对应文件为 backend/app/api/routes_research.py、backend/app/research/application/{agent_runtime,report_synthesis,report_generation,orchestrator,evidence_matrix,research_service}.py、backend/app/research/infrastructure/research_store.py；Skill 同步更新 `.agents/skills/research-report-synthesis/SKILL.md`。

## 已有证据与技术风险

2026-10-29 的 [运行时报告审计](./2026-10-29-report-runtime-audit.md)只抽样了两份已完成任务，不是全量统计。两份各有 5 篇 citation manifest 与 Markdown/HTML/manifest 三类 Artifact；正文为 1,435 和 7,649 个 Unicode 字符（不是本合同定义的 CJK 字数）。较长样本仍是目录卡片，未见显式跨论文比较；两条 canonical /reports/1 均返回 404。两条 Artifact 的 run IDs 属实际 AgentRun 形状，但 Artifact 元数据不能区分模型输出被接受还是后续 deterministic fallback。审计明确指出 51 条已索引 KB 文档无法仅凭 candidate_id 与 document_id 的不相等判断有无全文映射。

因此，本次可确认的是两份样本的正式 Artifact 缺少可读取 canonical report，以及现有暴露信息不能归因生成分支；不能声称这就是某个未绑定 run_id 的短报告根因。最高技术风险是 canonical row、Artifact、消息与版本号分裂。通过同一 report_version、同一规范正文、显式 generation.path 和仅通过后发布来解决；在本次已确认范围内没有需要用户新增决策的产品分支。若 Task07 发现此方案必须新增公开 API 或第二持久化体系，停止 Task08 并回报架构阻塞。

## Gate 2 修订对照与验收底线

- REQ-01：Task10 增加独立人工语义 PASS/FAIL rubric 和逐项 E2E 证据；重复/空泛文本是拒绝条件。机器 `quality_validation` 只报告结构门禁。
- TECH-01：上文冻结 POST/GET 请求、202 响应、session-backed WorkItem 路径、矩阵兼容草稿路径、GET 草稿读法、状态与错误码。
- TECH-02：`BEGIN IMMEDIATE` 内查 key/计算最大版本/插入 generating reservation；同版本贯穿所有产物；明确并发仲裁、重复 POST、模型输出已存/未存、Artifact/消息之后崩溃恢复顺序。
- TECH-03：Evidence ID 只由当前已批准 Evidence 对象映射；全文需已验证 document/chunk provenance，AgentRuntime 传入真实等级，禁止根据候选 ID 猜测全文存在或缺失。
- TECH-04：冻结 `report_content`、`quality_validation`、`generation` 类型/必填/范围/最大长度和服务端计算来源；机器和人工质量结论分开。
- TECH-05：冻结 loops/calls/elapsed 默认上限及跨 AgentRun 累加；最多 2 轮 revision 与 schema retry 不增加总预算，恢复不能重置计数，token/cost 无值为 null。

固定机器用例含：1,499/1,500 CJK；标题/目录/引用/ID/附录不计数；错误 schema/超长/重复 ID/越界 Evidence；证据映射与摘要/全文等级；5 篇无比较、字数达标无 3 条受支持发现；两轮 revision 与预算停机；重复 key、并发版本争用、各持久化切点重启恢复；正式产物同版本/同 hash；旧报告与旧下载不变。Task10 另用人工 rubric 评真实自然语言 API E2E 最终报告，不得以机器结构检查替代。

## 二轮P1最小修订（主会话代行纯文档）

本节为唯一预算/终态定义，替代上文旧的无条件5400秒和partial/draft择一表述；不改代码。

**有效预算：** `effective_max_seconds = min(5400, ResearchTask.soft_budget_seconds)`；当前profile给定600/1500/2700秒，如已批准计划有更小的有效任务预算，再取其较小值，不能提高任务上限。`generation.budget.task_totals.max_seconds`记录这一实际值。loops/calls同样取现有任务有效上限与160/640的较小值，per-run不超过现有有效上限与40/160的较小值。

任务已消耗秒数为当前task所有历史AgentRun（含失败/schema retry、其它研究阶段及report-only）的持久累计有效活跃耗时，不仅是当前report或当前进程。`remaining_seconds = max(0,effective_max_seconds-task_used_seconds)`；开始run或改写前检查，单run超时不得超过剩余预算。report-only、新request_key/新report_version不重置task用量。恢复读取所有持久运行计数及当前run已耗时，先结算失联run已确定的活跃时间，再计算剩余；时间使用现有持久started/finished及heartbeat计量语义，负差归零但不得扣减已累计消耗。无法确定失联run耗时则保守占满该run预留时间，不以未知作为0释放预算。预算检查与计数更新服从同一任务级CAS/事务，防止并发报告重复花同一余额。任何一种任务额度耗尽都不得请求extension，按下表结束，并记录BUDGET_EXHAUSTED。Token/cost不可得仍为null。

**唯一状态映射（ResearchReport.status、POST与GET共用；按优先级判断）：**

1. 尚在执行/恢复正式交付链：`generating`，quality_status=pending或已有核验结果，published=false；202是已受理而非完成。
2. 模型/执行终止后无可读正文（仅错误信息、空字段、无内容占位不算正文）：`failed`，published=false。
3. 有可读正文，但已选有证据论文不足5篇，或有效证据不足以支持规定比较/三条综合发现：`partial`，quality_status=fail，published=false，明确证据缺口。
4. 有可读正文且证据覆盖条件满足，但CJK计数、schema、引用、重复/质量门禁或预算/运行失败未能达标：`draft`，quality_status=fail，published=false。fallback最多是partial或draft，不得completed。
5. 所有机器门禁通过且canonical/Artifact/消息正式交付链按合同持久完成：`completed`，quality_status=pass，published=true。无模型矩阵兼容调用只产draft，即使结构通过也不发布。

证据不足优先于其它质量缺项，故可同时保存多种reason_codes但仅一个公开status。预算耗尽/模型失败有正文时再按证据覆盖选择partial或draft；无正文failed。质量通过但投影写入待恢复继续generating；若不可恢复地放弃，保存可读正文为draft并附交付失败原因。旧版本按旧合同读取，不追溯改状态。

修订留痕：2026-10-29，主会话代行（仅文档，无代码）修复独立评审P1-1/P1-2；交原独立architect复审，不自签。
