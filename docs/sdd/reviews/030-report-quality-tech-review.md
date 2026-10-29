# Spec 030 报告质量修订：技术评审

- 评审者：独立评审 Agent
- 角色：Architect — Technical Review
- 模型：GPT-6 Luna（xhigh）
- 分派方式：原生多 Agent 子代理委派
- 评审范围：仅 2026-10-29 内容充分性修订与 Task07–10 技术合同；不替代或覆盖历史评审
- 评审日期：2026-10-29

## 结论：打回（BLOCK）

最小数据扩展方向可行：`ResearchReport.report_json` 是既有 JSON 文本，报告状态枚举已有 draft/generating/completed/partial/failed，报告和 Artifact 都有 task/version 唯一约束；因此新增 versioned JSON 子对象原则上不需要新表或 SQL 列（`models.py:950–1001`；`research_store.py:716–728, 1105–1113`）。但当前合同还没有冻结一条从真实 AgentRunner 生成、失败恢复到 canonical 报告及正式交付的一致执行路径。下列前置项须先落到质量合同/Task08/Task10，再进入后端实现分派。

## 阻塞项与解除条件

1. **冻结现有 API 的确切语义与内部执行路径。** 当前 `POST /api/research-tasks/{id}/reports` 的严格请求只接受 `plan_version`、`report_version`、`title`；路由标注 202，但处理器直接同步调用 `ReportGenerationService.generate` 并返回已生成报告的 `report_id/versions/status/limitations`。该服务从矩阵固定渲染，不启动或继续 AgentRunner（`routes_research.py:196–203,1655–1680`；`report_generation.py:217–269`）。Task08 却把它定义为 session-backed 的 synthesizer WorkItem/AgentRunner 重生成及恢复入口（Task08 第 21–24 行）。请冻结同一公开路径的请求字段、202 的“已受理”响应字段、异步/继续执行语义、状态转换、错误码/HTTP 状态、草稿读取方式，以及与现有同步矩阵调用的兼容策略；GET `/reports/{version}?format=json|markdown|html` 现为直接返回一个 ResearchReport，未就 `published` 或草稿定义行为（`routes_research.py:1683–1714`）。不得让 202、生成完成和正式发布互相混用。

2. **冻结跨所有产物的 report_version 身份、原子预留及幂等恢复。** AgentRunner 当前在 WorkItem 输入中把 `report_version` 设为 `plan_version`（`orchestrator.py:1945–1948`），合成 Artifact/会话消息沿用 Agent 输出版本，消息幂等键也是 task+version（`report_synthesis.py:612–674`）；而 canonical report 调用 `next_report_version` 另行取“当前最大 report/artifact 版本 + 1”（`report_generation.py:246–260`；`research_store.py:6058–6072`）。这与合同要求的 plan_version 独立、一次分配并贯穿 Run/ResearchReport/Artifact/消息/通知相冲突。`next_report_version` 的读取与 `save_research_report` 的唯一插入不在一个事务中；并发 POST 可竞争同一版本。请规定一个可持久化且抗并发的版本预留点，并让所有写入复用该版本；同时写清重复 POST、进程重启、模型调用后/报告保存后/Artifact 或消息写入后的恢复行为。用户主动的质量重试应新开版本；同一请求的网络重试/后台恢复应复用或查询原运行，不能额外创建版本、重复消息或重置 revision_count。现有 conversation idempotency key 不覆盖 POST 的请求幂等语义。

3. **消除全文证据承诺与 AgentRuntime 来源边界的冲突。** Spec030 承诺摘要级可合格、全文可用时补强（第 130 行），而当前 synthesizer prompt 的 matrix_context 明确只允许 catalog/abstract 证据，并禁止 fulltext/document/chunk 定位符（`agent_runtime.py:331–355`）。请在已批准范围内明确全文证据如何以当前有效 Evidence ID 进入 `report_content` 并保持正确证据等级；若本修订不消费已有全文证据，则删除“全文可用时补强”的承诺。runtime audit 的两份样本没有 candidate→KB document 映射，不能用它们证明具体报告有或没有全文（runtime audit 第 34–36 行）。

4. **冻结可校验的 report_content 与质量字段 schema。** 当前合同规定了字段名称、部分最低数量和关系，但没有冻结各文本块/引用项的对象类型、必填字段、未知值表示、唯一性、最大数量/长度，以及 `quality_validation`/`generation` 与旧版 JSON 的精确嵌套形状；Task08 还要求结构化输出与既有 `ReportSynthesisOutput` 对接（质量合同第 24–33 行；Task08 第 19–30 行）。请在实现前给出一个有界、版本化 schema，包含服务端如何验证论文 selection、evidence→paper 映射、comparison dimension 和 CJK 计数的来源。机器可判的结构门禁与人工语义评审应分开报告。

5. **让总调用/预算及恢复计数可审计。** 初稿加最多两轮定向改写已明确，但既有 AgentRuntime 自身的 attempt/model-loop/tool-call/max_seconds 重试如何与两轮改写相加、由谁持久累计，以及 soft-budget 耗尽后停在哪个状态，仍未有精确运行账本。请冻结不扩大现有上限的总量规则，并证明恢复不会重置 revision/call/elapsed 计数；不可取得的 token/cost 继续为 null（质量合同第 43–47 行；Task08 第 21–22 行）。

## 实施前提判断

在上述合同冻结后，建议沿同一 AgentRunner synthesizer WorkItem、既有 ResearchReport JSON、ResearchEvent、ResearchArtifact 和会话通知链完成最小增量；不新增公开 API、第二队列或模型设置体系。当前失败分支会用固定 candidate renderer 写入 Artifact/会话消息，通知可为 partial/completed（`orchestrator.py:2418–2458`），而计划规定 deterministic fallback 不能冒充正式成功；Task08 必须把该分支纳入 fail-closed 的行为与测试要求。

## 主要依据

- [质量合同](../plans/030/2026-10-29-report-quality-contract.md) 第 16–60 行。
- [Task07](../plans/030/task-07-quality-contract.md) 第 12–32 行；[Task08](../plans/030/task-08-substantive-report-generation.md) 第 17–36 行；[Task09](../plans/030/task-09-report-quality-feedback.md) 第 10–24 行；[Task10](../plans/030/task-10-quality-acceptance.md) 第 10–28 行。
- [运行时审计](../plans/030/2026-10-29-report-runtime-audit.md) 第 19–46 行及其 [结构化摘要](../plans/030/artifacts/20261029-runtime-audit/summary.json)。
- [API 路由](../../../backend/app/api/routes_research.py:196)；[报告生成器](../../../backend/app/research/application/report_generation.py:217)；[AgentRuntime 合同](../../../backend/app/research/application/agent_runtime.py:331)；[Orchestrator](../../../backend/app/research/application/orchestrator.py:1945)；[持久化版本分配](../../../backend/app/research/infrastructure/research_store.py:6058)；[领域模型](../../../backend/app/research/domain/models.py:950)。

## 二轮窄复审（2026-10-29）

- 复审者：同一独立评审 Agent / Architect — Technical Review
- 模型：GPT-6 Luna（xhigh）
- 分派方式：原生多 Agent 子代理委派
- 复审范围：仅首轮 TECH-01..05 与本次补充的实现准入事实
- 结论：打回（BLOCK；仍有 2 项 P1 合同缺口）

### 首轮问题复核

- **TECH-01 API：基本解除。** 已冻结 session-backed POST 只受理、初始返回 generating/pending/false、新增质量/发布/URL 字段、无 session 的同步 matrix draft、GET 可读草稿和 Artifact 未发布过滤（质量合同第 37–40 行；Task08 第 21 行；Task09 第 14–16 行）。
- **TECH-02 版本/幂等/终态：解除。** 已给出 task+UUID key reservation、`BEGIN IMMEDIATE` 内版本分配、唯一约束竞争处理、同版本恢复、terminal WorkItem successor 且不重开 ResearchTask。源码的 WorkItem 表仅以 `work_item_id` 为主键、没有 task_type 唯一约束，允许同类型新行（`research_store.py:477–499,2289–2337`）。
- **TECH-03 证据范围：Gate 2 合同要求已解除。** 合同和 Task08 已规定当前 task/plan 的 ClaimEvidence ID、来源等级及同一 claim/task 的 EvidenceUpgrade provenance（质量合同第 29 行；Task08 第 19–20 行）。实现时需让定向测试覆盖 `task_id` 与 `to_level=fulltext` 绑定：当前 `EvidenceMatrixService._fulltext_upgrade_matches` helper 本身不检查这两项（`evidence_matrix.py:280–293`），但该实现核对不构成新增产品/架构决策，也不单独阻止分派。质量合同用 `available/validated` 描述状态，而源码只有 `available/unavailable/revalidation_required`；Task08 已将可接纳状态写成 `available`，建议合同把“validated”写成通过验证的条件而非额外枚举值。
- **TECH-04 schema 与语义验收：REQ rubric 已解除首轮阻塞。** 子对象字段/范围/字节上限与机器计算来源已冻结（质量合同第 26–33 行）；Task10 第 18–28 行要求独立人工逐项复核，机器 PASS 不冒充语义 PASS。
- **TECH-05 loops/calls：大体解除；elapsed 上限与 ResearchTask 当前 soft budget 的关系仍未冻结，见 P1-1。** 固定 loops/calls 和恢复累计已明确（质量合同第 47 行；Task08 第 24 行）。

### P1 阻塞项与最小解除条件

1. **P1-1：`5,400s` 上限没有尊重当前 ResearchTask 的 profile soft budget。** 合同把 `generation.budget.task_totals.max_seconds` 固定为 5,400，并称任务累计；但 `ResearchTask.soft_budget_seconds` 是既有任务级预算，质量档位分别为 600/1,500/2,700 秒（`domain/contracts.py:159–164`；`ResearchTask` 字段见 `domain/models.py:15–31`；session plan 也记录 `soft_budget_seconds`，见 `session_plan_generation.py:246–250`）。AgentRuntime 的 `BudgetSnapshot.from_value` 只接受 `seconds/max_seconds`，不会读取 `soft_budget_seconds`，默认 `max_seconds=5,400`（`agent_runtime.py:432–445,500–531`）。因此照当前合同实现可越过用户任务预算。最小解除：冻结有效上限不超过 ResearchTask/profile soft budget 与 5,400 秒两者中较小值；定义此前 AgentRun 用量及 report-only 重试如何扣减/恢复该上限；`generation.task_totals.max_seconds` 必须记录实际生效上限而非无条件写 5,400。不能用报告重试重置计时。
2. **P1-2：失败结果的公开 `status` 缺少唯一映射。** 质量合同第 43 行和 Task08 第 21 行对机器门禁失败使用“partial/draft”，但没有规定可用正文、证据不足、质量字段失败、模型无正文/运行失败分别映射到 `ResearchReport.status` 的哪个终态。POST/GET 又承诺返回该状态，Task09 按正式/partial/draft 区分 UI（质量合同第 38–39 行；Task09 第 13–16 行）。最小解除：冻结一个明确状态表，例如 `generating`=受理/进行中；`partial`=有可读报告但证据覆盖不足；`draft`=有可读正文但机器质量门禁未过；`failed`=无可恢复正文；`completed`=机器门禁与正式交付链均完成，并让 POST/GET 复用同一映射。

上述两项只需修订质量合同与 Task08 的具体字段/边界定义，不改变已确认产品范围，无需再次询问用户。P1 消除后可复审技术 Gate 2；当前不建议把 Task08 交给 backend-dev 开始编码。

### 二轮依据

- 修订合同：[质量合同](../plans/030/2026-10-29-report-quality-contract.md) 第 26–48、64–73 行；[Task07](../plans/030/task-07-quality-contract.md) 第 12–35 行；[Task08](../plans/030/task-08-substantive-report-generation.md) 第 19–37 行；[Task09](../plans/030/task-09-report-quality-feedback.md) 第 12–25 行；[Task10](../plans/030/task-10-quality-acceptance.md) 第 18–28 行。
- 预算源码：[`contracts.py`](../../../backend/app/research/domain/contracts.py:159)、[`models.py`](../../../backend/app/research/domain/models.py:15)、[`session_plan_generation.py`](../../../backend/app/research/application/session_plan_generation.py:246)、[`agent_runtime.py`](../../../backend/app/research/application/agent_runtime.py:432)。
- Evidence 源码：[`evidence_matrix.py`](../../../backend/app/research/application/evidence_matrix.py:23)、[`evidence_upgrade.py`](../../../backend/app/research/application/evidence_upgrade.py:230)。

## 三轮窄复审（2026-10-29）

- 复审者：原独立评审 Agent / Architect — Technical Review
- 模型：GPT-6 Luna（xhigh）
- 分派方式：原生多 Agent 子代理委派
- 复审范围：仅 P1-1 有效任务预算与 P1-2 公开终态映射
- 修订作者：主会话代行纯文档修改；本结论由原独立评审者出具，不是作者自签
- 结论：通过（GO；P1-1/P1-2 已解除）

质量合同末节“二轮P1最小修订”（第 75–93 行）已给出唯一预算公式和优先级状态表；Task08 第 43 行明确将其设为预算与 POST/GET/恢复行为的唯一规则，并为两项增加定向验证条件。范围仍限已确认的报告质量修订。

- **P1-1 已解除：** 有效秒数取 5,400 秒、ResearchTask profile soft budget 与更小批准任务预算中的最小值；历史各阶段 AgentRun 活跃用时计入同一 task 余额，report-only 和新版本不重置。恢复时失联耗时未知则保守扣满该 run 预留，预算检查/更新通过 task 级 CAS/事务避免并发重复花费；耗尽不申请 extension。合同也规定 loops/calls 使用现有有效上限与固定上限的较小值，且字段记录生效预算。
- **P1-2 已解除：** 唯一状态表明确了 `generating`、无正文 `failed`、证据不足 `partial`、其它未达标 `draft`、正式链完成 `completed` 的优先级；证据不足优先于其它质量缺项。POST/GET 与恢复共用此映射，Task08 要求对预算耗尽有/无正文、证据不足与其它缺项并存等情形做定向验证。

上一轮提及的 EvidenceUpgrade task/level 绑定仍按已确认合同作为实现与定向测试检查，不构成本轮 Gate 2 的额外阻塞。Task08 当前已明确该映射属于实现范围；其测试在代码阶段验证。此次结论是技术合同门禁 GO，不替代编码后的后端评审、定向测试或 Task10 最终验收。

### 三轮依据

- [质量合同](../plans/030/2026-10-29-report-quality-contract.md) 第 75–93 行。
- [Task08](../plans/030/task-08-substantive-report-generation.md) 第 41–43 行。
