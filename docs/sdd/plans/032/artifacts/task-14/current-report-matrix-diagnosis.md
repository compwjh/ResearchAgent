# Spec032 真实研究 E2E：Matrix / ResearchReport 分裂诊断

日期：2026-10-08（Asia/Shanghai）  
角色：backend-reviewer / backend architecture diagnosis  
审计方式：只读对照 `current-research-e2e-reviewed-report.md`、脱敏 E2E evidence、Spec030/032 条款及现有 pipeline、matrix、report 代码；未修改业务代码、未写生产数据、未伪造 AgentRun、未运行全量测试。

## 结论

本次真实 E2E 的阻塞不是“5 篇评估结果不足”，而是自然语言研究主链与 Spec030 证据矩阵之间没有生产者接缝：候选评估只持久化选集并交给候选级报告合成，现有 `EvidenceMatrixService.build_matrix()` 没有被编排器调用，也没有任何现有代码把评估结果生成并持久化为 `ResearchClaim`、`ClaimEvidence`、`ComparisonDimension`、`PaperComparisonCell`。因此读取矩阵时得到 `MATRIX_NOT_READY`，随后 canonical `ResearchReport` 不会生成。

同时，artifact 报告与 `ResearchReport` 是两条有意分开的持久化链，当前没有“artifact → ResearchReport”的转换：

- 真实 E2E 的 7649 字、5 个 catalog 引用属于 Orchestrator 的候选级 `ReportDeliveryService` 链，产生 `ResearchArtifact`、会话消息和 notification；旧的单数 `/report` 端点还会把该 artifact 作为兼容报告返回，因此它能 HTTP 200。
- 版本化 `/reports/{version}` 属于 Spec030 的 `ReportGenerationService` 链，只读取已持久化的 Evidence Matrix，再 insert-only 保存 `ResearchReport`。没有矩阵行时，它正确返回 `REPORT_NOT_READY`/404，不应从 artifact 文本推导矩阵或伪造 canonical 报告。

静态诊断 P0=0；本切片有两个 P1 级接线缺口：

1. **确定 P1：主链缺少结构化矩阵生产/调用接缝。** 5 个候选、5 个 catalog 引用不等于 Claim/Evidence/Dimension/Cell，当前 E2E 无法进入 Spec030 报告链。
2. **确定但独立的 P1：批准计划自动导入是异步副作用，终态报告不等待导入。** E2E 中 2 项 `KB_IMPORT_FAILED`、3 项 `downloading`、全部没有 `paper_id/document_id`；这会阻塞全文 `EvidenceUpgrade`，但不是当前 `MATRIX_NOT_READY` 的直接根因。catalog/abstract 降级报告按 Spec030 可以不等待全文导入。

## 复核证据

真实运行 `spec032-task14-research-e2e-reviewed-20261008T000748Z` 的 task 为 `fc83662fd8f15748b57ed7f49ad32445`：

- 候选评估选择 5 篇，目标和计划预算均为 5。
- `GET /api/research-tasks/{task}/report` 返回 `artifact:8e1e792c014a442ca23a0c37925ba6fb`，`limitations.artifact_backed=true`，Markdown 7649 字、5 个 catalog 引用。
- 自动导入批次只有 5 项，但 2 项 `failed/KB_IMPORT_FAILED`、3 项 `downloading`；5 项均无 `paper_id/document_id`。
- `GET /api/research-tasks/{task}/evidence-matrix?plan_version=1` 返回 409 `MATRIX_NOT_READY`；`GET /api/research-tasks/{task}/reports/1?format=json` 返回 404 `REPORT_NOT_READY`。
- 脱敏 E2E evidence 中只有 matrix 的 GET 检查，没有成功的 `POST /evidence-matrix`；这与代码中 matrix writer 只有路由调用点相符。

## 具体根因

### 1. 候选评估只形成 selection，不形成 Spec030 matrix

现有自然语言 Orchestrator 在候选评估阶段通过 `_persist_agent_selections()` 写入 `research_paper_selections`，候选允许集合和 `catalog:<id>` 引用也被用于候选级合成。仓库中 `build_matrix()` 的调用点只有 `routes_research.py:1617-1631` 的显式 `POST /{task}/evidence-matrix`；`Orchestrator`、`ApprovedPlanAutoImporter`、导入服务没有调用它。

`EvidenceMatrixService.build_matrix()`（`backend/app/research/application/evidence_matrix.py:160-242`）的输入仍是显式 `dimensions`、`claims`、`evidence`、`cells`。它可以从已持久化的 selection 补出矩阵覆盖单元格，但不能凭 5 个候选 ID 创建 Claim 的 statement、stance 或比较维度；`read_matrix()`（`:244-271`）在没有 Claim 或 Dimension 时直接抛 `MATRIX_NOT_READY`。因此“5 篇评估完成”与“矩阵可读”在当前实现中不是同一状态。

这不是导入服务把 5 篇过滤掉：selection 已存在，matrix 的结构化行根本没有被生产。也不能把候选的 `evidence_refs` 直接当成 ClaimEvidence：Spec030 要求 evidence level、locator、stance、claim 归属可校验；catalog evidence 至少需要合法 `catalog_snapshot_id`，而当前 evaluator/report-synthesis 输出没有完整的 Claim/Evidence/Dimension/Cell 合同。

### 2. artifact 链和 canonical ResearchReport 链分开落库

自然语言 Orchestrator 的候选级合成路径：

1. 以 validated evaluator candidates 和 `catalog:<id>` allowlist 合成 `SynthesisResult`；
2. `ReportDeliveryService.deliver()` 写 Markdown/HTML/citation manifest `ResearchArtifact`，并更新 session final message、notification（`report_synthesis.py:563-674`）；
3. 旧兼容入口 `ResearchService.get_report()` 在没有 `PreliminaryReport`/`ResearchReport` 时，从 artifact fallback 返回 `artifact_backed=true`（`research_service.py:319-369`）。

Spec030 canonical 路径则是：

1. `/reports` POST 调 `ReportGenerationService.generate()`；
2. 先 `EvidenceUpgradeService.revalidate()`，再 `EvidenceMatrixService.read_matrix()`；
3. 调 `ReportSynthesizer.synthesize_evidence_report()`；
4. `ResearchStore.save_research_report()` insert-only 写 `research_reports`（`report_generation.py:217-257`）。

两个路径没有互相复制或转换。Store 也明确区分：`save_research_report()` 是不可覆盖的 `research_reports` 插入，而 `save_report()` 是旧 `preliminary_reports` 的同计划版本 upsert（`research_store.py:5927-6060`）。所以 artifact HTTP 200 不能证明 `ResearchReport` 行存在，`reports/1` 404 是当前数据链断裂的准确反映，不是报告下载路由缺失。

另外，`next_report_version()` 会联合查询 `research_reports` 和 `research_artifacts` 的最大版本（`research_store.py:5927-5941`）。以后若在已有 artifact v1 后直接生成 canonical report，服务端会分配 v2；不能无条件把 artifact v1 复制成 `ResearchReport` v1，更不能用不同内容共占一个版本号假装两条链已对齐。

### 3. 自动导入是异步副作用，不是 matrix producer 或终态门禁

批准计划后，`Orchestrator._auto_import_approved_selection()`（`orchestrator.py:1925-1957`）调用既有 `ApprovedPlanAutoImporter`。其 `run()` 经过 `ResearchAcquisitionService.confirm()`，最终由 `PaperImportBatchService.create_batch(auto_run=True)` 提交后台批次后立即返回（`acquisition.py:542-603`、`paper_import_batch_service.py:295-363`）。

agent 路径在候选级 artifact delivery 后再调用自动导入（`orchestrator.py:1778-1795,1866-1879`）；legacy 路径也只是在合成阶段调用一次并不等待后台索引（`:1049-1056`）。任务最终状态主要由 WorkItem/合成失败计算，不把导入批次终态作为 canonical matrix/report 的前置条件。这解释了“artifact 已有、导入仍 downloading/failed”的并存状态，但不能解释/修复 matrix 结构化行缺失。

## Spec030/032 的最小复用修复方案

### A. 先补现有矩阵生产者接缝，不造第二套报告链

1. 在已有研究 application 层增加一个**受控矩阵生产步骤/适配器**，复用 `EvidenceMatrixService.build_matrix()`；不新增表、不新增公开 endpoint、不修改 `EvidenceMatrixRequest` schema。
2. 该步骤只能消费已经通过 evaluator/worker allowlist 的、具备 Spec030 结构化字段的 Claim/Evidence/Dimension/Cell payload，然后调用现有 validator 和 store 写入。若当前候选级 evaluator 只有 candidate/citation，没有合法 claim statement、stance、locator 或 dimension，必须返回 `MATRIX_NOT_READY`/`EVIDENCE_INSUFFICIENT`，不能按候选数量填充伪 Claim、伪摘要或伪全文定位。
3. 要让自然语言主链产生 canonical 报告，需让现有真实 synthesizer/结构化 producer 输出**已有 Spec030 `evidence-report-v1` 形状**，或在用户明确的 matrix 步骤提交同一既有请求结构；这是接入现有合同，不是新 schema。当前不能把已有 7649 字 artifact Markdown 反解析为矩阵。
4. 结构化矩阵成功后调用现有 `ReportGenerationService.generate()`；它负责 `next_report_version()`、EvidenceUpgrade 重验证、safe Markdown/HTML/JSON 和 `ResearchReport` immutable insert。不要从 issue route 重跑 Orchestrator、重新搜索或重复导入。

### B. 保持两类产物边界，避免伪对齐

- literal Spec030/032 收口可把 `ResearchReport` 作为 canonical versioned report，把现有 artifact 继续作为候选级/session 兼容产物；必须在 API/UI 上明确两者状态，不把 artifact-backed 200 宣称为 `reports/{version}` 已完成。
- 新运行若要同版本同时拥有 `ResearchReport` 与 session artifact，必须让两者由同一次结构化矩阵/报告 application 流程生成，并明确版本绑定；不能从 artifact 文本补写 `ResearchReport`，不能用未绑定字符串或新造的伪 AgentRun 绕过 `create_artifact()` 校验。
- 已有 artifact v1 的本次 task 不应被事后“回填”为 canonical v1。先得到合法矩阵，再按现有版本分配规则生成新 canonical 版本；若产品要求同一版本号/同一内容的双投影，需架构师另行确认 application-level delivery 组合，而不是在 route 层拼接。

### C. 将全文导入作为证据等级门禁，而不是 catalog matrix 的隐式前置

- catalog/abstract 报告可沿 Spec030 的降级语义使用合法 catalog/abstract locator，不等待所有 PDF 导入；报告 limitations 必须诚实标记未验证/缺全文。
- 需要全文结论时，复用现有 `ResearchDocumentLink` → `EvidenceUpgradeService.upgrade()` → `EvidenceUpgrade`/manifest/chunk provenance → `EvidenceMatrixService.build_matrix()` → `ReportGenerationService.generate()`，而不是把 `document_id` 直接塞进 artifact 或 selection。
- 当前 2 个失败和 3 个 downloading 项应继续由既有 issue/retry/upload/recovery 链处理；它们没有成功 document handle，不能用于 fulltext Evidence。若最终要求 task 终态等待导入，另加现有 acquisition status 的应用层收敛/验收，不新建状态机；这不是本诊断的 matrix writer 修复。

## 相关测试与验证范围

本轮未运行测试；以下是实现后应先跑的最小定向集合：

1. `tests/research/test_evidence_matrix.py`：已有测试证明必须显式 Claim/Evidence/Dimension，能生成 supports/contradicts/missing 单元格，并在非法 locator 前不写入。
2. `tests/research/test_report_generation.py`：验证 matrix→immutable `ResearchReport`、版本冲突、全文重验证降级和 `MATRIX_NOT_READY → REPORT_NOT_READY` 映射。
3. `tests/research/test_report_synthesis_contract.py`：验证 artifact 兼容入口与 `ReportDeliveryService` 的真实 owner/session/agent-run 绑定；不能拿它替代 canonical matrix 测试。
4. `tests/paper_discovery/test_approved_plan_auto_import.py`：验证批准计划预算、幂等和失败/重试边界；需要另补一个应用层断言，明确后台 import 非终态时不会伪称全文 Evidence 已可用。
5. 应新增按功能命名的研究接缝测试（例如 `test_research_report_matrix_bridge.py`）：固定 5 个 allowlisted candidates，断言没有结构化 matrix payload 时保持 `MATRIX_NOT_READY`；有合法既有 `evidence-report-v1` payload 时，matrix 持久化、canonical `ResearchReport` 生成且旧 artifact 不被改写。若同时要求 session artifact，则另测同一版本/owner/session 绑定，禁止 fake AgentRun。

## 不扩大范围的边界

- 不把候选级 Markdown 反解析成 Claim/Evidence，不把 5 个 citation 数量当作 5 个可比较 Claim。
- 不创建第二套 matrix/report/download/status machine，不新增 schema，不在 `/reports` route 拼接 artifact 内容。
- 不因 matrix 缺失而伪造 `ResearchReport`、versioned link、paper/document ID 或 AgentRun。
- 不把报告 PDF与论文 PDF/fulltext evidence混淆；本次只诊断现有 Markdown/HTML/JSON report 与论文导入证据链。
- 不把当前 artifact 200、任务 `completed` 或 selection 数量描述为 Spec030/032 canonical report 已通过。

## 架构师决策句

当前最小真实修复是：**先复用已有 Spec030 结构化 matrix contract，在研究 application 主链补“合法 matrix payload → `build_matrix()` → `ReportGenerationService.generate()`”接缝；没有合法 Claim/Evidence/Dimension/Cell 就继续 fail closed。** 现有 artifact 只作为独立候选级/session 产物，不能回填成 `ResearchReport`。若还要求同一版本的 artifact/session 投影，再在此结构化流程之上复用既有 delivery，并以真实绑定的 synthesizer run 为门禁；不伪造 AgentRun、不新 schema。
