# Spec032 Task12/14：报告恢复剩余范围审计

日期：2026-10-08（Asia/Shanghai）  
角色：backend-reviewer  
审计方式：只读对照 `docs/sdd/specs/032-research-source-expansion.md`、Task12、Task14 与 `current-report-recovery-plan.md`；未修改业务代码、未运行全量测试、未执行部署。

## 核心结论

Spec032、Task12、Task14 的明确条款要求是：论文修复或新增全文证据后，由用户触发生成**新报告版本**，旧报告保持只读不可变，并能提供新旧版本链接。它们没有直接把 `ResearchArtifact`、Session `final_message_id` 或 notification 写成该功能的硬性验收字段。

因此，按当前已确认 Spec032 的字面范围：

- 既有 `ResearchReport` 版本行 + `POST /api/research-tasks/{task_id}/reports` + 版本化 `/reports/{version}` 读取，是可复用的最小后端报告契约。
- “修复后显式生成新版本”的前端按钮和既有 POST 调用仍未完成，是当前确定的 P1-A；上传接口返回的 `report_action` 只是下一步提示，不是已生成状态。
- `ResearchArtifact`/session message/notification 目前不能宣称已生成，但仅凭 Spec032/Task12/Task14 不能把它们判为本功能的明确硬阻塞；`current-report-recovery-plan.md` 已将其正确标为“若最终验收要求”的条件性 P1，需架构师明确选择。
- “新 PDF”在本范围内应理解为用户上传的论文 PDF 进入受验证的全文 Evidence；不是要求生成 PDF 格式的报告。当前报告读取契约只有 JSON/Markdown/HTML，报告 PDF 属于另一个接口与 artifact 范围。

## 条款核对

### Spec032 的直接要求

- 统一工作流第 6 条（`specs/032-research-source-expansion.md:43`）要求：用户可登录、重试或上传 PDF；修复仍在执行的任务可续跑受影响步骤；**已产出的报告不改写，只生成新版本**。
- 失败场景约束（`:126-127`）要求批次可恢复或明确可重试、不得重复报告版本，并再次要求“已生成报告不可变；修复论文后生成新版本并保留旧报告”。
- 验收方式（`:144-145`）要求人工修复后证据可续跑、报告保留旧版本，以及最终全量回归、真实端到端 smoke 和部署。
- 产品步骤 8（`:158-160`）要求候选修复或新增全文证据后生成新报告版本、旧版本只读不可变，记录新旧报告版本链接；没有出现 `ResearchArtifact`、`final_message_id` 或 notification 作为必需产物。

### Task12/Task14 的直接要求

- Task12 的一句话目标是来源/字段来源/待处理论文界面；其定向验收要求索引中不可冒充完成（`task-12-source-progress-issue-ui.md:8-18`），变更日志只记录“新报告版本提示”（`:27-30`），没有新增 artifact/session 投影契约。
- Task14 的最终验收 prompt（`task-14-review-regression-deploy.md:13-18`）要求人工修复、重启恢复、旧报告不可变、全量回归、真实 smoke、部署和可复现用户步骤；未把 artifact/session message/notification 单列为 Spec032/Task14 必需字段。

### 当前恢复方案的准确边界

`current-report-recovery-plan.md` 已给出两种语义并明确区分：

- `:18-23`：显式生成 `ResearchReport` 的既有接缝可复用；canonical artifact/session 投影仅在“最终验收要求”该能力时才成为条件性 backend P1。
- `:47`：既有 POST 已返回 `report_id`、`report_version`、`status`、`limitations`，旧版本可由同一版本 GET 读取。
- `:51-60`：`ReportDeliveryService` 才会创建 `ResearchArtifact`、activity、Session final message 和 notification，但当前 `/reports` POST 没有调用它；同时它消费的 `SynthesisResult` 与 `ReportGenerationService` 当前 deterministic evidence-report dict 不是同一契约。
- `:81-86`：推荐的首要修复是前端显式按钮；如果当前 POST 只有 `ResearchReport`，UI 必须显示“报告版本已生成/等待 artifact 投影”，不能把缺失 artifact 当成会话报告交付完成。
- `:104-115`：只有在验收明确要求 Session `artifacts[]`、final message、notification 时，application-level backend 接线才是 P1；是否必须同时写 canonical artifact 是当前唯一需要架构确认的界线。

## 当前未完成清单

### 已落在确认范围内的缺口

1. **显式用户动作（确定的 P1-A）**：upload/recovery 路径当前只返回 `report_action="generate_new_version"`。仍需在 `frontend/research-tasks.js`（必要时配套 HTML/样式）渲染按钮，单飞调用现有 `/reports` POST；不得在 upload/login/retry 中自动生成报告。
2. **全文证据前置**：上传只形成 document link/event，不自动创建 ClaimEvidence。要让论文 PDF 内容进入新报告，仍需沿既有 `EvidenceUpgradeService → ClaimEvidence/Cell → EvidenceMatrix → /reports` 路径；没有可验证 EvidenceUpgrade 时不能把上传成功显示为全文已进入报告。
3. **版本读取与用户提示**：按钮成功后应使用返回的 `report_version` 刷新现有 JSON/Markdown/HTML 读取和版本选择器；失败时保留旧版本和原提示。验收材料应记录新旧报告版本链接。
4. **Task14 收口门禁**：上述代码接线不替代 Spec032 要求的真实任务 E2E、人工修复/重启恢复、唯一全量回归、部署和逐步人工验收；Task14 当前仍为实施中。

### 只有架构确认后才成立的条件性缺口

若架构师确认本次最终验收必须把研究会话的 canonical 交付也算作“新报告完成”，则当前 `/reports` 路径缺少 `ResearchArtifact`、Session `final_message_id`、activity/notification 写回，属于 backend P1。该判断来自当前方案的条件分支，不是 Spec032/Task12/Task14 已明确写死的字段。

## 可复用的最小接线路径

### 解释 A：按已确认 Spec032 的明确范围收口（推荐先采用）

1. 保留 upload/recovery 只更新已有 link/event 并返回 `report_action`。
2. 用户点击前端“生成报告新版本”按钮；请求只传既有 `plan_version`，不新增 `document_id`、`evidence_upgrade_id`、异步 job 或 report version 请求字段。
3. 后端复用现有 `ReportGenerationService.generate()`：先执行当前 EvidenceUpgrade 重验证和矩阵读取，再由 `next_report_version()` 分配一次新版本，insert-only 保存 `ResearchReport`；旧版本按原版本读取。
4. 前端显示“报告版本已生成”，并刷新已有报告版本读取；若没有 canonical artifact，只能显示等待/未接通状态，不能显示“会话报告交付完成”。

该路径不需要新增 schema、公开 API、outbox、下载器、报告 PDF renderer 或第二套状态机。

### 解释 B：若架构师确认 canonical artifact 是硬门槛

1. 先修订/再次确认 Spec032 或新增明确的验收条款，不把条件性能力默认为既定范围。
2. 在既有 application service 内复用 `EvidenceMatrixService`、`ReportGenerationService`、`ReportSynthesizer`、`ReportDeliveryService` 和 owner/task/session 绑定；`next_report_version()` 只分配一次，并把 ResearchReport 与同版本 artifact/message/notification 绑定。
3. 必须由现有 `ResearchAgentRunner` 产生真实、同 task/session 绑定的 synthesizer `AgentRun`，再交给 `ReportDeliveryService.deliver()`；禁止用字符串、旧 run、`_synthesis_run_id()` 或 deterministic renderer 伪造 AgentRun/artifact。
4. 先解决 deterministic evidence-report dict 与 `SynthesisResult` 的契约差异；若无法为终态 task 安全复用 durable WorkItem/runner，应报告阻塞，而不是 reopen 终态或新建第二套报告链。
5. 补同一 task 的集成验收：旧版本 hash 不变、新版本号唯一、ResearchReport/artifact/message/notification 同版本且 owner/session 绑定一致，再做真实 API E2E。

## 必须保持的负边界

- 不把论文 PDF（全文证据）与报告 PDF（新 artifact 类型）混为一谈；后者需独立修订接口、媒体类型、renderer、下载路由和 schema。
- 不在 issue route 自动调用完整 Orchestrator，不重新搜索、扩大候选或重复导入；终态 task 不 reopen。
- 不新增 `/reports` 请求字段或第二套状态机，不把一个上传文档无界映射到所有 Claim/question。
- 没有明确的 canonical artifact 硬性验收条款前，不把当前 ResearchReport-only 实现描述为“Session artifact 已完成”；反之，一旦确认该条款，也不能把 ResearchReport-only 当作收口通过。

## 给架构师的最终决策句

请在收口记录中明确选择：

1. **ResearchReport 版本契约足够**：按 Spec032/Task12/Task14 现有文字，完成前端显式按钮与报告版本 E2E；canonical artifact/session message/notification 记录为未纳入本次确认范围的后续能力。
2. **Canonical session 投影也是硬门槛**：先补充/确认 spec 与验收条款，再按真实 AgentRun + 既有 `ReportDeliveryService` 接线；在接线和同版本集成证据完成前，Spec032 不得收口。

本审计没有把“报告 PDF”误写成用户请求，也没有扩大业务范围；结论仅用于消除当前 Spec032/Task12/Task14 与条件性 artifact 要求之间的边界歧义。
