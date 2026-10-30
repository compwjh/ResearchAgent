# Spec030 Task08 后端正文上下文 Builder

状态：可信上下文 helper 与自然语言 Agent WorkItem 的正文生成接缝已接入；Artifact 投递仍待独立实现。
日期：2026-10-29。

## 改动

- `backend/app/research/application/orchestrator.py` 新增 `_build_report_quality_context` 与 `ReportQualityContextUnavailable`。
- `tests/research/test_report_quality_context.py` 覆盖持久化 Evidence、冻结快照、全文来源校验及缺失依赖。

Builder 从当前 `ResearchWorkItem.input_params.report_version` 读取预留报告版本；校验 WorkItem 与当前任务/计划版本一致，且计划状态为 active 或 completed。候选 ID 必须是当前持久化选集的完整 5–64 篇，并通过既有 `_build_synthesis_matrix_context` 的来源搜索句柄、快照 ID 和选集相等校验。

维度只从当前计划 facets 派生，并与持久化矩阵维度逐项一致。证据来自 `EvidenceMatrixService.read_matrix` 当前 task/plan 投影；输出只保留 `evidence_id`、`paper_id`、真实 `evidence_level` 和安全片段。目录级使用匹配冻结快照的标题；摘要级要求 snapshot ID、`catalog:<paper_id>` 引用及摘要哈希匹配后才传摘要。不会用目录候选 ID 拼造 Evidence ID。

全文 Evidence 需要当前任务关联的 `EvidenceUpgrade(status=upgraded,to_level=fulltext)`，并通过现有全文 locator/chunk provenance 校验；正文只可能取当前计划矩阵中与该 Evidence ID 精确关联的安全 cell summary。Evidence locator 中的任何文本不会被转发。现有持久层没有全文 chunk 文本投影，因此无安全 cell summary 时省略该全文项；cell summary 是矩阵摘要，不是全文原文摘录。

上下文标记包含 `report-quality-v1`、阶段、修订次数、plan/report 版本、研究问题、唯一选集、批准维度和证据片段。可选 `prior_report_content` 仅在 targeted_revision 阶段校验 schema/安全字段/512 KiB 上限后带入；`failure_codes` 限 32 个稳定大写码。该 helper 不评估最终字数门槛。

## 缺失依赖与边界

若没有当前计划的持久化 Claim/Evidence 矩阵，helper 抛出 `ReportQualityContextUnavailable`，其 `dependency` 为 `persisted_current_plan_claim_evidence_matrix`，并保留稳定 `source_code`。当前代码没有从目录/摘要自动建立 baseline Claim 与 EvidenceID 的确定性机制；本 Task 不写入伪造 Claim/Evidence，也不声称上下文准备成功。若矩阵存在但没有任何可核对的安全文本片段，dependency 为 `verified_current_plan_evidence_excerpt_projection`。

未修改 AgentRunner、模型输入、报告保存、Artifact、通知或发布代码；未调用模型、启动服务或部署。未来调用方可用当前任务、当前 synthesis WorkItem、服务器验证后的候选列表、stage 和 revision_count 调用 helper，并把返回值放入运行时的 `report_quality_context`；调用方需先确保 WorkItem 的 `report_version` 已绑定 reservation。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_quality_context.py` | 0 | 6 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/orchestrator.py tests/research/test_report_quality_context.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py tests/research/test_report_quality_context.py` | 0 | 通过，无输出 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | test layout: ok |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q tests/research/test_report_quality_context.py` | 0 | 收集 6 项，无收集错误 |

本次仅运行了 Task08 定向测试与指定静态检查，未运行全量回归；报告生成/发布集成及人工语义验收留待后续已授权 Task。

## 后续接入诊断：候选摘要到持久化 Evidence（2026-10-29）

本段为只读代码路径审查；没有查询数据库或运行模型，因此不能断言某个现存自然语言任务当前是否已有矩阵。

### 现有自然语言路径与矩阵缺口

默认 `ResearchService.create_task(review_plan_first=False)` 在 `research_service.py:192-196` 转入后台 `start()`；`_orchestrator()` 在 `:715-727` 将配置的 `agent_runner` 传给 Orchestrator。`Orchestrator._run_pipeline` 仅在 runner 和 ResearchSession 均存在时选择 Agent WorkItem 路径。该路径本身没有绕过矩阵；矩阵是否可生产取决于服务端快照上下文是否能建立。

合成前，`orchestrator.py:1888-1919` 生成最终验证候选集并通过 `_persist_agent_selections` 记录选择。`_build_synthesis_matrix_context`（`:3618-3761`）要求候选集合与持久选集完全相同，并逐篇解析 selection 的 `source_search_id`（兼容旧任务级句柄）、有效且未过期的 completed/partial SearchJob 以及精确 SearchResult snapshot；摘要摘要哈希、snapshot ID 和 `catalog:<paper_id>` 引用都由服务端构造。计划维度或目录快照依赖缺失、过期或不匹配时返回 `None`。

此时 `agent_runtime.py:603-628` 明确要求 synthesizer 不得自行发明矩阵；`_separate_synthesis_matrix`（`orchestrator.py:722-756`）对缺失矩阵返回空 payload。快照上下文存在时，输出则需通过 `matrix_contract.validate_synthesis_matrix_payload` 的计划版本、维度、选集、摘要 digest/locator 校验；`orchestrator.py:2368-2378` 再调用 `EvidenceMatrixService.build_matrix`。在 Memory delivery seam 开启时，矩阵缺失或构建失败会记为 `MATRIX_NOT_READY`（`:2355-2388`），并不会变成成功的持久化摘要 Evidence。

另一个接入阻塞是当前 `work_item_input["report_version"]` 在 `orchestrator.py:1957-1959` 被设为 `plan_version`，不是 Task07 reservation。Task08 builder 目前只检查这个字段是正整数，并不查询 reservation 存储，所以不能自行识别“正整数 plan_version 被误用为 report_version”；接入前必须由 reservation 逻辑写入真实预留版本，并继续让 WorkItem.task_id、WorkItem.plan_version、当前任务/批准计划和 helper 的 selected paper IDs 指向同一 task/plan/selection 快照。

### 可复用的持久化路径与覆盖边界

当前唯一可直接复用且语义完整的生产路径是：冻结 SearchResult 摘要 → synthesizer 在 `matrix_context` 下为论文输出实际 ClaimEvidence 行 → `_separate_synthesis_matrix`/`matrix_contract` 服务端验证 → `EvidenceMatrixService.build_matrix(task_id, owner_id, plan_version, ...)` 校验 Claim/Evidence 所属 task、plan、Claim、当前选集 Paper 及全文 EvidenceUpgrade → `ResearchStore.persist_evidence_matrix` 在一个事务中持久化 Claim、Evidence、dimension、cell → `EvidenceMatrixService.read_matrix` 给 helper 投影持久化 Evidence ID 和来源等级。

证据 ID 由现有矩阵输出提供，但只有其整行通过服务端校验并持久化后才是可读的 Evidence；目录候选 ID 或 `catalog:<paper_id>` 绝不能代替 Evidence ID。摘要 Evidence 必须是 `evidence_level=abstract`，定位器精确绑定冻结 snapshot、`catalog:<paper_id>` 与摘要 SHA-256。全文继续走 EvidenceUpgrade 校验，不能把摘要等级升级成 fulltext。

这个路径目前**不保证五篇摘要各有一条 Evidence**：矩阵校验要求至少有一个由支持性 Evidence 支持的 supported Claim（`matrix_contract.py:313-328`），但没有要求每个选中 paper 都有 abstract Evidence。`_build_report_quality_context` 会如实投影已存在的矩阵行，不补造缺失项。因此“至少五篇选集”不等于“至少五条摘要 Evidence”。

若产品契约要求每篇选中论文都无条件进入摘要证据上下文，最小改造应优先复用上述冻结快照、矩阵校验和 `EvidenceMatrixService`，并在 matrix contract 中加上所需 paper coverage 规则；但这仍要求模型对实际摘要提供可成立的 Claim/Evidence 关系，遇到无法成立的支持性主张应安全失败。现有 store 不提供脱离 Claim 的独立摘要 Evidence inventory；直接塞入通用 unresolved Claim 会进入 `ReportGenerationService` 的用户可见 Claim 投影。已有 Claim 主体不可改写，Evidence 的 task/plan/claim/paper/level/stance 身份不可变（状态与 locator 有受控更新路径）。除非主会话确认中性 Claim 的产品语义，否则不要用伪 Claim 做 baseline。若要无模型、无结论语义地保证摘要片段可读取，需要先由主会话决定是否扩展独立证据快照投影/数据模型；这超出当前 helper。

### 后续接入的精确生产接缝

1. **`backend/app/research/application/orchestrator.py`**：在 `_run_agent_work_items` 中先完成当前矩阵校验和 `EvidenceMatrixService.build_matrix`，再调用 `_build_report_quality_context`，并将结果交给 AgentRuntime 的 synthesizer quality-only 输入。当前 synthesis WorkItem 在矩阵构建前已于 `:2158-2165` 置为 completed；接第二次模型调用前，需由主会话决定是把 terminal commit 延后到整个报告阶段结束，还是创建另一个与同一 reservation 绑定的明确 report-quality WorkItem。不能在已完成 WorkItem 上假定恢复/续跑语义存在。
2. **`backend/app/research/application/agent_runtime.py`**：当前已验证 marker 的 schema、stage、revision，以及 report_version 与 WorkItem input、plan_version 与 matrix context 的绑定，并要求 synthesizer 返回 `report_content`（`:235-370`, `:2089-2126`）。task/owner/WorkItem 绑定由 builder 和 AgentRunInput 的服务端身份参数负责；marker 本身没有 task_id。接入时复用 allowlist 与安全输入，不把 raw snapshot、路径或 locator 转发到 quality-only prompt。是否需要代码改动取决于主会话选定的 WorkItem 两阶段生命周期方案。
3. **`backend/app/research/application/report_quality.py`**：已有 `validate_report_content` 对 selected paper、Evidence ID→paper、dimension、覆盖和早期/最终质量规则做确定性验证；复用它作为结构化正文的质量门禁。
4. **`backend/app/research/application/report_generation.py` 与 `report_synthesis.py`**：`render_report_payload`/`_render_validated_report_content` 已能从 validated `report_content` 和 `ReportQualityContext` 渲染内容及引用；但 `ReportGenerationService.generate` 目前从矩阵走 legacy renderer 并自行计算 report version。与此同时 `ReportSynthesizer.consume_validated_output` 仍按候选 envelope 渲染，`ReportDeliveryService.deliver` 保存该 `SynthesisResult` 的 markdown/html/activity。接入需让最终 `report_content` 进入正确的结构化 renderer，并统一绑定 reservation、不可变报告记录、Artifact 与最终 activity；不要只把 `report_content` 附在旧 candidate report envelope 上就宣称发布链已接通。
5. 若采用“每篇摘要全覆盖”而非现有模型矩阵语义，另需修改 **`matrix_contract.py`** 增加逐选中 Paper 的摘要 coverage 验证；只有当决定独立摘要 inventory 或新的中性 Claim 语义时，才继续修改 **`evidence_matrix.py` / `research_store.py`**。这些都需主会话先裁定数据与用户可见语义。

本轮没有更改生产代码/测试，没有运行测试或模型，没有读写数据库、Git 或部署服务；本报告中的测试表记录的是上一阶段 builder 的验证结果。

## Task08 纵向接入决策（2026-10-29 09:21:00 UTC）

依据本轮确认的最小实现范围，接入边界如下；本节记录决定，不扩展 Runtime、Store、API 或 Artifact 投递代码。

- 报告版本只由 \`ResearchStore.reserve_report_generation\` 原子分配；调用方用 task/owner/plan、稳定 request key、规范 request payload 和服务器构造的 WorkItem input 预留，并使用 reservation 返回的 report/work item。\`plan_version\` 与真实 \`report_version\` 分离。仅对当前 queued、未绑定 synthesis WorkItem 接 reservation；不把 terminal WorkItem 重开。
- 原始候选/矩阵阶段与结构化正文阶段是两个实际 AgentRun。矩阵阶段复用既有 synthesizer WorkItem/Runner，矩阵先通过 \`_separate_synthesis_matrix\` 与 \`EvidenceMatrixService.build_matrix\` 持久化；正文阶段在同一个仍处于运行态的 WorkItem 下用新的唯一 AgentRun ID 调用 Runtime \`report_quality_context\` 模式。两阶段不得让 matrix_context 误触发正文阶段的 required matrix 输出；完成状态仅在两阶段处理结束后提交。
- 每个报告 AgentRun 在 dispatch 前调用 \`claim_report_generation_budget\`，终态后调用 \`settle_report_generation_budget\`；运行时 allowance 取 claim grant，不能只信 session plan 的宽上限。revision_count 由 \`update_report_generation_state\` CAS 持久推进，最多两次 targeted revision；每轮都以真实上一版 report_content 和 validator failure codes 构造定向上下文。
- 正文输入只来自 \`_build_report_quality_context\` 的当前 task/approved plan/selected papers/\`EvidenceMatrixService.read_matrix\` 投影；至少五个不同选中 paper 必须各有可用的 verified Evidence 才调用正文 Runtime。目录条目不转写为摘要/全文证据，不能补造 Claim/Evidence ID。
- 对至少五篇可信 Evidence 的生成结果，调用 \`validate_report_content(ReportQualityContext(...))\` 计算机器质量并用 \`render_report_payload\` 生成规范报告视图；通过 \`save_report_generation_output\` 写 canonical \`report_content\`、\`quality_validation\` 与结构化 generation provenance。Runtime 的正文仍需满足既有 \`research-report-content-v1\` schema；最多两次 revision 后把 readable-but-failing 内容存为 draft/partial。
- 若没有五篇可信 Evidence，则不调用正文 Runtime，也不生成占位 Claim/body。当前 schema 要求每篇分析至少一个 supported block，无法表示没有正文的诚实 Evidence 诊断；按唯一状态表将无可读正文的 reservation 标为 \`failed\`/\`failed\` stage，并从 helper 返回稳定的缺证据诊断。\`update_report_generation_state\` 现有 API 不持久化 failure reason，因此该 reason 持久化仍是后续接缝。
- 本 slice 暂不调用 \`ReportDeliveryService\` 或创建 Artifacts/最终消息，也不推进 \`published=true\`。Canonical writer 只保存 JSON 正文和质量字段，不更新 \`ResearchReport.markdown/html\`；structured renderer 的 Markdown/HTML 结果可由 helper 返回给下一阶段，但确定性投影、三类 Artifact、最终 activity、通知和 publish CAS 留给后续 Artifact/发布接入。

已读并按 API handoff 复用 \`reserve_report_generation\`、\`get_report_generation_budget\`、\`claim_report_generation_budget\`、\`settle_report_generation_budget\`、\`update_report_generation_state\` 与 \`save_report_generation_output\`。Store writer 只接受已由 application 验证的正文/质量和 allowlisted generation 字段，并以 \`expected_revision\` CAS；调用方用 reservation 和预算查询返回的 revision，不自行递增。AgentRuntime 现有 marker validator/prompt/output 路径已支持 quality-only 正文运行。

## Task08 有界实现结果（2026-10-29）

在 `Orchestrator._generate_report_quality_body` 增加了可调用的应用 helper，入口要求调用方已取得 `reserve_report_generation` reservation，且同一合成 WorkItem 当前仍为 `running`。Helper 对照 reservation 的 report id/version/plan version/request key 和持久化 WorkItem，随后重新读取当前 plan Claim/Evidence matrix；缺少可信矩阵或当前 reservation 时返回稳定诊断并将无正文报告记为 `failed`，不会重开 WorkItem 或调用 Runner。

正文 marker 仍由 `_build_report_quality_context` 生成，再过滤为 `abstract`/已验证 `fulltext` Evidence 后传给 quality-only Runtime。至少五个不同 Paper 有可用可信 Evidence 才派发；目录级 Evidence 不进入正文输入或质量校验。每轮生成前 claim 有界预算，AgentRun 终态后必须 settle 成功；使用 Store 返回的 reservation `report_version`，不从 plan version 推导。质量门禁失败时最多进行两次 targeted revision，并附上已校验的上一版正文和稳定 failure codes。最终 readable content 经 `validate_report_content` 和 `render_report_payload`，再用 canonical CAS writer 保存；因为本切片不发布，报告状态保持 unpublished `partial`，即使机器质量通过也不声称已发布。

无五篇可信证据的测试确认 Runner 调用数为零，报告以 `failed` 状态结束，返回 `INSUFFICIENT_TRUSTED_EVIDENCE`、所需篇数和当前篇数。Store 当前状态接口没有 failure reason 字段，所以具体原因只由 helper 返回，持久化 reason 仍需独立的 Store/API 契约扩展。

本切片没有改动 `_run_agent_work_items` 的原始 synthesis/matrix 生命周期，也没有接通它的第二次 Runner 调用；生产调用方仍需在 queued WorkItem 阶段先 reservation，再在矩阵阶段 `EvidenceMatrixService.build_matrix` 成功后、WorkItem terminal 更新前调用此 helper，并在两次 AgentRun 后统一收束 WorkItem。Helper 返回 renderer 结果，但 canonical writer 不写 ResearchReport.markdown/html；Artifacts、最终 activity/通知、publish CAS 和投递依然是后续接点。当前 `research-report-content-v1` 仍要求每篇 paper analysis 至少一个 supported block，因此低于五篇可信证据时不能把诊断伪装成合法正文保存。

### 定向验证

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_quality_context.py`：退出码 0，9 passed；revision 覆盖 1 次与 2 次后通过。
- `/Users/wjh/ResearchAgent/.venv/bin/python -m ruff check backend/app/research/application/orchestrator.py tests/research/test_report_quality_context.py`：退出码 0，All checks passed。
- `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py tests/research/test_report_quality_context.py`：退出码 0。
- 没有运行模型、部署、全量回归或 Git 操作。

## 纵向入口接入与评审修正（2026-10-29）

本节更新前文“尚未接入”与“通过质量后仍标为 partial”等阶段性结论；当前实现复用原合成 WorkItem 和 Runner，并且不重开任何终态 WorkItem。

- `_run_agent_work_items` 在合成 dispatch 前调用 `reserve_report_generation`，将 store 返回的真实 `report_version` 写入当前 WorkItem input。原始 synthesizer AgentRun 仍负责输出矩阵；只有矩阵契约校验及 `EvidenceMatrixService.build_matrix` 完成后，才调用 `_generate_report_quality_body`。
- 生命周期现在有真实的三个步骤：原始矩阵 AgentRun 在报告 `evidence_review` 状态运行；后续独立 AgentRun 使用 `report_quality_context.stage="comparison"`；再运行独立 `drafting` AgentRun，质量不通过时最多执行两轮 `targeted_revision`。每次都有唯一 AgentRun ID、budget claim 与 settle；每个 AgentRun 的 run-local counters 从 0 开始，task 累积值继续包含此前矩阵/正文使用量。
- 结构化正文通过 Runtime marker 绑定 reservation report version 与 approved plan/matrix，随后经 `validate_report_content` 和 `render_report_payload`。Canonical writer 保存最终正文、质量结果、所有正文 AgentRun ID 与 store-owned budget claims。
- 状态遵守报告质量合同：质量通过后保存 canonical 并保持 `generating`，等待投递；证据覆盖不足但有正文时为 `partial`；证据充分但字数门槛未达等非覆盖质量失败时为 `draft`；没有可读正文时为 `failed`。稳定原因码通过 `update_report_generation_state(reason_codes=...)` 持久化。读状态或写失败状态异常时，应用返回可恢复的 `generating` 诊断，并避免把 synthesis WorkItem 终态化。
- 当前 slice 故意不调用 `ReportDeliveryService`、不创建 Artifact、不发布 canonical 或写最终 activity；入口在质量通过后返回 `running/REPORT_DELIVERY_PENDING`。这保留了投递接点，不声称报告已交付。
- Store 的 AgentRun 行持久化 output hash、状态、预算计数；现有 Runtime 还会将校验后的完整输出写入 owner/task/WorkItem/AgentRun 绑定的不可变 `AgentCheckpoint`，并把 checkpoint ref/hash 记回 AgentRun。因此 comparison 正文通过现有 checkpoint 可审计读取，最终 canonical report writer另存 drafting/revision 采用的正文。fake-runner 集成测试模拟了 Runtime checkpoint 持久化并核对 comparison 输出。

### 定向验证（本次入口接入）

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_quality_context.py tests/research/test_research_report_matrix_bridge.py` | 0 | 36 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/orchestrator.py tests/research/test_report_quality_context.py tests/research/test_research_report_matrix_bridge.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py tests/research/test_report_quality_context.py tests/research/test_research_report_matrix_bridge.py` | 0 | 通过，无输出 |

Fake Runner 集成测试覆盖自然语言入口顺序、report_version 使用、五篇真实摘要 Evidence、同一 WorkItem 只在阶段结束后完成一次、独立 comparison/drafting AgentRun、budget counters 和 canonical claim。未调用真实模型、Artifact 投递、部署或全量回归。

## 正式 canonical 投递接入与定向复验（2026-10-29）

后续接入已在 `_run_agent_work_items` 的真实合成入口完成：质量通过后调用 `ReportDeliveryService.prepare_canonical`，在 Artifact 与待完成消息准备成功后，以相同 reservation/report version 做 canonical publish CAS，再调用 `finalize_canonical`。只有 durable report 为 `completed/published`、三类 Artifact 一致、最终 activity 为 `completed` 且通知已持久化时，才将原 synthesis WorkItem 和 task 收束为 `completed`。任一投递接点未完成时保留 `generating` 与运行态 WorkItem，供恢复路径重试；不重跑已完成 Runtime checkpoint，不重开 terminal WorkItem。

自然语言入口 fixture 明确 `ResearchSession.current_plan_version=1`，与任务已批准 plan 对齐。该修正保留生产 plan binding 门禁；在此前 fixture 默认为 0 时，canonical writer 正确拒绝跨计划投递。入口集成测试现在验证同版本 canonical published、三类 Artifact、最终 activity message、通知及 completed 结果。相同 fixture 下，五篇可信摘要覆盖达标时的 matrix bridge 与 approved minimum 测试预期改为完成交付；证据不足仍按现有失败/partial 合同处理。

### 本轮定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_quality_context.py tests/research/test_research_report_matrix_bridge.py` | 0 | 42 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/orchestrator.py tests/research/test_report_quality_context.py tests/research/test_research_report_matrix_bridge.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py tests/research/test_report_quality_context.py tests/research/test_research_report_matrix_bridge.py` | 0 | 通过，无输出 |

验证使用 fake Runner 和真实 Runtime/ResearchStore/MemoryRepository 入口，不调用真实模型，不部署、不执行全量回归或 Git 操作。`report_synthesis.py` 的 canonical prepare/finalize 实现属于并行作者，本报告只记录它的调用契约与集成结果，不将其列为本角色改动。

## 启动恢复接续（2026-10-29）

启动审计仍把运行中的 ResearchTask 和 WorkItem 收敛到终态 `interrupted`。在此之后，`ResearchService.recover_interrupted` 只扫描同一 Task 下仍为 `generating` 的当前报告 reservation，并通过 Store CAS 为同一个 report version 绑定报告专用 successor WorkItem；旧 ResearchTask 和旧 WorkItem 都不会重开，报告 worker 使用现有 executor 独立运行。若上次恢复留下 queued successor，启动时直接接续；若 successor 在崩溃时仍 running，则先把这条 terminal Task 下的陈旧 running WorkItem 收敛为 interrupted，再继续 successor 链。

Store 的 successor 接口允许 reservation 原先绑定的旧 synthesis WorkItem 为 `interrupted` 或 `completed`，但报告本身必须仍是 `generating`，且 owner/task/plan/report version/request key/fingerprint 与旧输入完全一致。它保留旧行、报告版本、预算和 claims，不把旧 WorkItem 放入 successor 的依赖。Runtime checkpoint 的读取按 claim 自带的历史 WorkItem ID 查 AgentRun 与 checkpoint，并要求历史行仍满足同一 reservation identity、task/session/plan/role 绑定；因此 successor 可以复用已完成的 comparison/drafting/revision 输出，不会把旧 claim 错绑到新 ID 或重跑已完成模型调用。

若 canonical 已完成 publish CAS、但交付收尾尚未完成，启动路径读取同一 reservation 和 terminal WorkItem，重新用当前选择/矩阵核验 canonical quality，再幂等补完 Artifact 与 final activity；不创建新 WorkItem、不调用 Runtime。报告质量失败也会收束 successor：无可读正文时 report 持久为 `failed` 并保留稳定 reason code；有可读 draft/partial 时保留对应报告状态。以上 report-only 恢复不改变 ResearchTask 的 `interrupted` 状态，调用结果也如实返回该终态。

### 定向验证（启动恢复）

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_report_quality_context.py -q` | 0 | 23 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_research_backend_slice.py::StartupAuditTests::test_recover_interrupted_converges_running_only -q` | 0 | 1 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m ruff check backend/app/research/application/orchestrator.py backend/app/research/application/research_service.py tests/research/test_report_quality_context.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py backend/app/research/application/research_service.py tests/research/test_report_quality_context.py` | 0 | 通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | 命名门禁通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q tests/research/test_report_quality_context.py` | 0 | 23 tests collected，无收集错误 |

新增入口测试覆盖可信证据不足不调用 Runtime 且失败原因持久化、同一 reservation successor 使用真实 Runtime 完成交付并保留 Task `interrupted`、历史 completed checkpoint 复用，以及已发布 canonical 从 terminal WorkItem 幂等完成 Artifact/message。未调用真实模型、部署或全量回归。

## v3 正文预算与 provider deadline 修正（2026-10-30）

本次只读实际运行记录及合同核对见 [report v3 budget/AgentRun diagnosis](./artifacts/20261030-report-v3/03-budget-diagnosis.md)。报告 v3 的 Task 累计耗时为 380/1500 秒，仍有 1120 秒；失败发生在 comparison 单个 120 秒 grant 内，未进入 drafting。该固定 120 秒是代码策略，不是报告合同上限。

- comparison、drafting 与 targeted revision 现在分别按 `min(300, int(progress["remaining"]["seconds"]))` 申请 grant。剩余不足 1 秒时在 claim 前以 `REPORT_BUDGET_EXHAUSTED` 收束；既有 Store 事务继续按真实余额和 per-run/task cap 原子裁剪。矩阵准备阶段仍保持原有申请，不属于此次正文改动。
- 启用现有 online fallback 时，primary provider 的每次同步请求 deadline 设为 `min(30, remaining_seconds * 0.25)`，同一 run grant 的其余时间留给既有 fallback；因此 300 秒分配为 30+270，120 秒为 30+90，80 秒为 20+60。fallback 未启用或不可用时 primary 保留全部剩余 grant。
- Schema retry 仍使用同一 AgentRun deadline；Runtime 按已耗 wall time 递减剩余时间，不能通过 retry 重置。Task 1500 秒上限、per-run 40 loops/160 calls 和 task 160 loops/640 calls 均未提高；claims 仍由 Store 原子处理。

### 本轮定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_agent_runtime_request_timeout.py tests/research/test_report_quality_context.py -q` | 0 | 55 passed |

另新增精确反例：300 秒 grant 的 primary/fallback 为 30/270 秒；报告 stage 剩余 87 秒后按 87、86 秒申请；禁用 fallback 的既有路径不变；schema retry 在 1 秒总 grant 下使用递减的 1.0/0.6/0.2 秒请求并于预算耗尽停止。未调用线上模型、修改部署或运行全量回归。

## 报告结构错误安全反馈与比较稿续用（2026-10-30）

结构校验现在保留稳定 `ReportQualityError.code` 和受限的 `field_path`。Runtime 将这些值映射到安全错误诊断和具体 JSON 字段路径（例如 `report_content.paper_analyses[].method.status`），下一次模型请求只收到错误码、固定规则 ID 与安全字段路径，不包含拒绝正文或原始异常文本。retry checkpoint 持久化相同的安全 `failure_code` 与字段路径，正文数据不会作为校验诊断内容写入。

drafting 会读取当前 reservation 下已接受的 comparison AgentRun checkpoint，并仅把其结构化 `report_content` 作为 `prior_report_content` 输入；prompt 明确它不是质量通过。此种子在 drafting 上下文校验时允许覆盖不足以便模型修订，但新生成正文仍由 Runtime 完整检查证据归属与跨论文覆盖，并继续经过 canonical report quality gate。没有 comparison checkpoint 时仍按原流程生成正文。

### 本轮定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_report_quality_context.py tests/research/test_report_quality.py tests/research/test_agent_runtime_contract.py -q` | 0 | 125 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/report_quality.py backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py` | 0 | 通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m ruff check --ignore SIM102 backend/app/research/application/report_quality.py backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_report_quality_context.py` | 0 | All checks passed |

未忽略 `SIM102` 的 Ruff 检查在 `report_quality.py` 两处未改动的既有嵌套条件处报告问题；本轮未扩展修复范围。验证未调用真实模型、未部署、未访问生产数据库且未运行全量回归。

## v6 comparison 失败诊断（2026-10-30，只读）

只读检查 `/Users/wjh/ResearchAgent/data/research/research.sqlite3` 与 `artifacts/20261030-report-v6/06-report.json`。未读取模型拒绝正文、思维链或凭据；未修改数据库/预算，也未改代码。

### 根因

- 报告 v6 的 comparison AgentRun 链在 15:20:11–15:23:53 UTC 结束。安全 checkpoint 和 `research_events` 给出的错误一致：`AGENT_OUTPUT_INVALID`，`REPORT_SCHEMA_INVALID`，规则 `agent.output.structure`，字段路径 `report_content.synthesis_findings[].paper_ids`。这是结构校验路径，不是论文选择/引用范围失败：`validate_report_content` 先在 `report_quality.py` `_validate_report_shape` 的 `_id_array(..., minimum=2, maximum=64)` 检查该数组；选择范围错误在后续阶段会报 `INVALID_PAPER_SELECTION`。
- `paper_ids` 的当前结构约束是：列表包含 2–64 个不同 ID；每个 ID 是 trim 后非空、最多 200 字符的字符串。已持久安全诊断只保留字段路径，没有保留是哪一项约束失败；retry checkpoint 的 `output` 为 `null`。因此不能再区分字段缺失、非列表、数量不符、无效 ID 或重复 ID，也不能据此推测模型输出的具体值。
- 三条 AgentRun 对应同一 comparison WorkItem：初始 run 2 model loops、两条 continuation 各 1 loop，共 4 loops/0 tool calls；状态依次 `limit_reached`、`limit_reached`、`failed`，错误码都为 `AGENT_OUTPUT_INVALID`。这不是 timeout 被误归类：唯一 timeout 是首次本地请求的 `MODEL_TIMEOUT`，见下一节；最终失败由 schema validator 抛出。

### Retry、fallback 与候选 ID

- 事件 seq 64 在 15:20:41 明确记录 `PROVIDER_FALLBACK`：`ollama/qwen3.5:9b` 因 `MODEL_TIMEOUT` 切换到 `deepseek/deepseek-flash`。online fallback 实际被调用。第一次结构错误后，同一 retry 链继续使用已切换的 model；`fallback_attempted` 已为 true，结构错误不会再触发第二次 fallback。两次后续验证反馈在 seq 66、68 记为 `feedback_sent=true`。
- `research_agent_runs.provider/resolved_model` 三行仍显示初始 Ollama/Qwen，不能代表后续实际 provider。fallback 切换时 Runtime 没有更新这些 AgentRun 元数据；事件才记录实际 provider 变化。这是独立的运行元数据投影缺口。
- durable WorkItem 有 5 个 `validated_candidates` 与 5 项 `citation_allowlist`，候选 ID 唯一。retry 会保留原 `work_item_input.report_quality_context`，其 `selected_paper_ids` 来源于当前批准选择；运行时把整个 context JSON 发给模型。因此合法候选 ID 在后续请求上下文中，且验证反馈确实发送；但反馈对象本身只列校验规则/字段路径，并不再次列出 ID。未读取真实模型请求正文。

### 预算核对

- 报告 claim 为 `settled=true`，requested/granted 均为 267 秒；comparison run 链端到端 222 秒。Task 运行记录合计 1455 秒、32 loops、2 tool calls，低于既有 1500 秒/160 loops 上限；v6 comparison 链占 222 秒/4 loops。不是因任务预算耗尽而失败，也没有发现超额使用。
- v6 JSON 中的 `task_totals=1233s/28 loops`、`report_totals=0/runs=[]` 是未结算前的旧快照：1233 秒正好是之前 18 条 AgentRun 记录总时长，少了本次 3 条 continuation。Store 的 claim 阶段会持久预算快照，但 `settle_report_generation_budget` 仅持久 `settled` claim 并返回重算 usage，没有调用 `_write_report_generation_budget`；后续失败状态写入也未刷新 summary。数据库 AgentRun 行保留真实计数，Store 动态预算查询可从这些行重算；但最终 JSON 展示的 report/task totals 陈旧。该问题不解释本次结构失败，仍应单独修预算投影。

### 最小修复建议（未实施）

1. 不放宽 `_id_array` 或论文引用范围校验。针对 `synthesis_findings[].paper_ids` 在通用 prompt 和 retry feedback 中明确“每条 finding 的 `paper_ids` 必须是至少两个、互不重复的批准 Paper ID；不能填 Evidence ID/标题”，并可加结构示例。feedback 最好从已验证 `report_quality_context.selected_paper_ids` 限定可用值，避免模型再次猜 ID。
2. 为 ID-array schema 错误加受限的稳定子码（如 missing/type/count/duplicate/invalid-id），checkpoint 只保存子码、现有安全路径，不保存拒绝值或正文。这样下次才可从持久记录识别具体失败约束。
3. fallback 切换后同步更新 AgentRun provider/model metadata；在 claim settle 和终态状态落盘时写回重算后的 `generation.budget` summary。两项都是观测准确性修复，不改变模型/schema 接受标准或预算上限。

### 只读证据范围

检查的实体限于 report v6 JSON、指定 WorkItem、三条 comparison AgentRun、它们的安全 checkpoint 元数据、该 task 的安全 worker/validation/fallback 事件、报告候选计数，以及相关 validator/runtime/store 实现。未运行测试、模型、部署或任何写库操作。

## v6 paper_ids、fallback 元数据与预算快照修复（2026-10-30）

按上节诊断实施以下有界修复，未改 report schema/validator 接受标准，也未更改任何既有 task 或 report budget：

- 通用 report-quality prompt 明确每条 `synthesis_findings[].paper_ids` 是 2–64 项、无重复的 JSON 数组，且值必须来自已验证 `selected_paper_ids`；明确禁止 Evidence ID 和论文标题，并给仅展示形状的占位示例。仅在该安全字段路径校验失败时，retry feedback 才携带同一结构约束和已验证选集 ID。未使用模型拒绝值、原始正文或隐藏推理作为反馈。
- Runtime 选择 online fallback 后，在后续调用前通过当前 AgentRun generation CAS 更新 provider、model 与 reasoning metadata。成功输出和 fallback 后仍失败的 run 都保留实际 DeepSeek 投影；不 fallback 的原 provider 路径保持原样。
- `settle_report_generation_budget` 在同一 `BEGIN IMMEDIATE` 事务内结算 claim、按持久 AgentRun 计数重算 usage，并写入 report JSON 的 budget snapshot。report 仍为 generating 时重复 settlement 只刷新同一事实快照，不新增累计；失败状态已有快照不变。report 已 published/terminal 时不写 report JSON，因此 canonical Artifact 内容、terminal task 状态及其报告 JSON保持不可变。

### 精确验证

TDD RED 阶段，以下新增能力反例曾全部按预期失败：安全 paper_ids retry 反馈、prompt 数组契约、fallback 成功与失败 run 元数据、结算后的 JSON budget snapshot。最终候选的定向验证如下：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_report_content_runtime.py tests/research/test_agent_runtime_request_timeout.py tests/research/test_report_generation_state.py tests/research/test_report_generation_budget_recovery.py -q` | 0 | 75 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/agent_runtime.py backend/app/research/infrastructure/research_store.py tests/research/test_report_content_runtime.py tests/research/test_agent_runtime_request_timeout.py tests/research/test_report_generation_state.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py backend/app/research/infrastructure/research_store.py tests/research/test_report_content_runtime.py tests/research/test_agent_runtime_request_timeout.py tests/research/test_report_generation_state.py` | 0 | 通过，无输出 |

结算用例用两个并发调用竞争同一 claim，并核对只有一个首次结算、二次读取一致的 report/task totals 与 AgentRun list；失败终态的重放不能增加 usage；已发布状态后重复 settlement 不改 report JSON、Artifact 列表或 terminal Task 状态。该用例通过 Store 的 published 状态和 Artifact fixture 验证不可变边界，没有执行真实 canonical 投递。没有运行全量回归、部署、真实模型或生产数据库操作；v6 已用预算未重置。
