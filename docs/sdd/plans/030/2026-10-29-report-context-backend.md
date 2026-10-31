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

## 自然语言 Intake 字数误判为论文数量（2026-10-31）

真实 API 样本位于 `docs/sdd/plans/030/artifacts/20261031-natural-e2e/request.json`。请求同时明确目标论文数 5、至少 5 篇，以及“正文至少 1500 个中文字符”。对应 `01-intake.sse` 正确抽到了 `target_paper_count:5` 和 `min_paper_count:5`，但又错误追加 `paper_count_constraint:unparsed`，使唯一缺项变成 `constraints` 并重复询问篇数。

根因在 `session_plan_generation.py` 的 `_COUNT_MARKER_RE`：数量前缀“至少”后以宽泛的 12 字符 lookahead 搜索“篇/论文/paper”，因此跨过“1500个中文字符”并把后面的“逐篇分析”识别为该数量的论文单位。现改为只有数字后立即跟论文单位（篇、论文、paper）时才将该数量标记为未解析。明确的 1–2 位篇数仍由现有 extractor 解析；超出支持位数但紧邻论文单位的数量仍产生 `paper_count_constraint:unparsed` 并走已有澄清，不更改 target/min/max 冲突处理、数量上限或 Intake 接口。

新增两项能力回归：直接验证目标/最小篇数与字符长度混写只提取篇数；真实 `ResearchIntakeCoordinator.handle_message` 接缝验证同类自然语言输入持久化 target/min 且不产生 missing 字段。新增样例先 RED（2 failed），修复后连同超范围篇数旧用例通过。

### 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py -q` | 0 | 27 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/session_plan_generation.py tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/session_plan_generation.py tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py` | 0 | 通过，无输出 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | test layout: ok |

本 slice 未部署、未调用模型、未修改真实 API 数据或提交 Git。主 Agent 后续应在同一会话通过自然语言补充后继续案例，验证 Intake 不再追问论文数且后续状态推进正常；该真实端到端续接尚未在此 slice 执行。

### 复审补充：文字数量仍需保守澄清（2026-10-31）

独立 review 指出，若数量单位是明确的论文单位，但数量本身写为文字（例如“至少五篇论文”“at least five papers”）或模糊表达（例如“至少几篇论文”“no fewer than several papers”），当前仅识别数字的抽取器会返回空列表，随后可能静默使用质量档位默认篇数。修复仅扩展未解析 marker：它能识别常见中文数词/模糊量词、英文 one–twenty 与 few/several/some 等数量词，但只在其后紧跟“篇/论文/paper”单位时追加既有 `paper_count_constraint:unparsed`，并由原 Intake 流程请求澄清；未把词数量转换成数字，也未增加新的公开字段或澄清机制。

原始字符数反例保持不变：`1500个中文字符` 后接 `逐篇分析` 不构成“数量词 + 紧邻论文单位”，不会触发论文数约束。对确切请求的 Intake coordinator 回归仍确认 target/min 两项都存储、`missing=[]`。文字数量回归覆盖中文“五篇”、英文“five papers”、中文“几篇/若干篇”、英文“several papers”，均要求澄清。新增测试先 RED（文字数量用例失败，字符数反例通过）；修复后两个 Intake 领域测试文件共 28 passed。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py -q` | 0 | 28 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/session_plan_generation.py tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/session_plan_generation.py tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py` | 0 | 通过，无输出 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | test layout: ok |

仍未部署/提交或执行自然语言 API 同会话续接；该续接步骤由主 Agent 后续完成。

### 复审补充：选择意图连接词（2026-10-31）

复审指出 `至少要选5篇论文` 中的“要选”未命中数值 parser，也未命中 unparsed marker，导致 Intake 丢失显式最小篇数。parser 的数字数量模式和未解析 marker 现都接受可选的中文 `要/需要` 前缀，仍要求数字后紧邻论文单位；没有增加词数解析或改变仅有最小值时的既有目标篇数策略。精确测试同时包含“正文至少1500个中文字符”，确认长度要求不被识别为论文数。TDD RED 时结果为空；修复后 `min_paper_count:5` 得到保留。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py -q` | 0 | 29 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/session_plan_generation.py tests/research/test_intake_plan_repair.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/session_plan_generation.py tests/research/test_intake_plan_repair.py` | 0 | 通过，无输出 |

该窄切片只修改 intake 数量解析与能力测试；未部署、未写数据库、未运行全量。独立数量修复已冻结，主题查询/选集相关性修复仍是另一个切片。

## 自然语言认证主题查询与逐篇相关性门禁修复（2026-10-31）

修复对应上文只读诊断中的偏题自然任务。Spec030/027 的确认边界不变：至少五篇必须是真实相关且有证据的论文；不足时走现有 partial/有界流程，不能扩主题、降低相关性阈值或拿来源合法的候选凑数。本次没有新增公开 API/schema 或 semantic model checker。

### 实现

- `build_session_plan_output()` 将已确认 Intake 的 `topic` 作为独立 `query_topic` 传给确定性 Planner。只有搜索 WorkItem 查询使用 `topic + facet`；研究 objective、计划摘要、coverage goal、报告研究问题保持原 objective。没有 topic 的 legacy Planner 调用仍使用原 `goal + facet` 查询。
- Agent evaluator prompt 要求逐篇输出 `candidate_id`、`keep`、`relevance_score`、理由和该篇目录证据，并引用现有 `work_item_input.relevance_threshold`。aggregate 的 catalog refs 只证明来源，不代表论文相关性决策。
- durable Agent 路径中，`_validated_evaluator_candidates()` 和选集持久化只接受带单篇 ID、该篇 catalog ref、`keep=true`、通过已批准阈值的决策。评分也保留到持久 selection。allowlist 仍只限制来源范围，不能代替相关性判断。
- Agent 路径的 catalog 补充仍复用现有 `PaperEvaluator`，但只保留达到原 threshold 的结果；count floor 和既有 soft-floor 不会把阈值以下候选带进正式选集。候选不够时继续走现有不足处理。legacy 调用不传 strict threshold，保留旧输入兼容；未改其公开契约或原有 WorkItem/schema。

### 能力回归

- 新增 `test_plan_topic_search_queries.py`：用 Intake `topic=authentication security` 与单独中文 objective 构建批准计划，断言每条 search query 都含 topic，同时 objective 与 Critic goal 不变。
- evaluator 单测覆盖 aggregate refs 高分但没有逐篇决策、逐篇低于阈值、明确 reject、未在 Search recall allowlist 中、恰好达到阈值等情况；只有合法且达标的单篇决策进入候选。
- floor 测试覆盖无元数据/无分数、全部无关、只一篇达阈值和仅能通过 soft-floor 的场景；不得为了凑足五篇下调阈值。
- fake-runner Orchestrator 集成将历史 `candidate_id=null` 的 aggregate 作为唯一 evaluator 输出，验证不会持久化候选、不以报告下限启动 synthesis 成功，而是按不足情况收敛为 partial。单篇有效 decision 的既有 agent 集成仍通过。
- legacy `test_report_synthesis_contract.py` 与 matrix bridge 测试通过，确保缺少 strict threshold 的旧调用继续保留兼容行为。

### 定向验证

TDD RED 曾确认：计划 query 不含独立 topic；aggregate refs 被当成选择；低相关报告 floor 带入五篇；软阈值 0.1 带入低于已批准 0.2 的候选；无效 aggregate 会使 fake-runner synthesis 完成。以上回归修复后均转绿。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py tests/research/test_plan_topic_search_queries.py tests/research/test_validated_evaluator_candidates.py tests/research/test_report_catalog_metadata.py tests/research/test_agent_selection_persistence.py tests/research/test_agent_runtime_contract.py tests/research/test_research_report_matrix_bridge.py tests/research/test_report_synthesis_contract.py -q` | 0 | 184 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/planner.py backend/app/research/application/session_plan_generation.py backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_intake_plan_repair.py tests/research/test_research_intake_contract.py tests/research/test_plan_topic_search_queries.py tests/research/test_validated_evaluator_candidates.py tests/research/test_report_catalog_metadata.py tests/research/test_agent_selection_persistence.py tests/research/test_agent_runtime_contract.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/planner.py backend/app/research/application/session_plan_generation.py backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_plan_topic_search_queries.py` | 0 | 通过，无输出 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | test naming check passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | test layout: ok |
| `python -m pytest --collect-only -q` | 0 | 3,856 tests collected; no collection errors |

没有运行全量测试、真实模型、线上/本地 API、数据库写入、部署或 Git 提交。真实自然语言 E2E 需要主 Agent 在审查通过后以新任务执行；原已发布报告不在本 slice 中改写。Spec030 的正式缺陷记录由架构师另行维护。

## 自然语言认证安全报告召回偏题诊断（2026-10-31，只读）

检查任务 `387a5090b27550c59de86adb415eb26e`、会话 `eb423a0ae279472d9709cda75e957da3` 及 `docs/sdd/plans/030/artifacts/20261031-natural-e2e/` 中的请求、批准计划、最终报告，并只读查询本地 Research/Paper Discovery SQLite。没有改代码、数据库、选集或已发布报告，也没有重跑模型。

### 观察到的结果

- 用户主题字段是 `authentication security`。请求目标还要求比较 USENIX Security 2022 的认证安全论文，并列出密码凭证、网页风险认证、指针认证、TLS 服务器身份和生物活体认证等方向。
- 已批准计划的 `objective` 是中文比较目标；scope facets 只有“研究方法”“安全问题”“主要发现与证据边界”。三条搜索 query 全部重复完整 objective 加一个 facet，均未包含 Intake 中独立保存的英文 topic，也没有保留上述五类认证方向。
- 三路实际检索都限定了 USENIX Security 2022，每路请求 5 个结果。返回候选集中出现 ML 安全评估、Web Cache Deception、LGBTQ+ 安全建议、Linux 内核堆利用可靠性和 RPKI 降级攻击；它们不是用户要比较的认证机制主题。Search Worker 的安全摘要记为从 catalog tool results 恢复候选 ID，因为其结构化输出格式失败。候选 ID 仍绑定到真实目录检索结果；没有证据显示系统在空结果后另行伪造或切换到未请求来源。
- Evaluator 的持久化 aggregate decision 明确说明，可见标题/摘要不能直接建立 authentication-security 相关性，却以低置信度和缺少详情为理由保留了 catalog 引用集合。该 aggregate 的 `candidate_id` 为空，`keep=true`，`relevance_score=0.2`；候选被展开后，最终 selection 投影中的每条 relevance 为 `0.0`、facets 为空。
- 报告最终以 `completed` / `published=true` 保存，quality validation 为 `pass`，包含 5 篇和 2,920 个中文字符。正文诚实标明这些论文是跨域或相邻类比，不能据此推断认证论文的方法分布。因此结构、引用和篇数门槛通过了，但用户的主题覆盖目标没有实现。

### 最短根因链

1. `session_plan_generation.build_session_plan_output()` 同时读取 Intake `topic` 与 `objective`，但创建计划时只把 `objective` 传给 `Planner.build_plan(goal=...)`。主题字段没有传到 Planner。Planner `_split_facets()` 仅按标点拆分 objective；`_build_work_items()` 对每个 facet 生成 `query=f"{goal} {facet}"`，因此长中文目标重复进入每次检索，主题和用户给出的认证子方向没有进入计划查询。
2. `CatalogSearchAdapter` 复用本地目录和既有 RAG 排序返回 top-N，不在返回前要求最小相关性分数。当前跨语言词表有“身份认证”映射，但这里的计划查询没有该词，也没有原 Intake 英文 topic `authentication security`。实际 search snapshots 的 rerank score 为空，retrieval score 较低；成功返回 top-N 只证明来源、年份和目录身份，不证明命中用户主题。
3. Search Worker 格式恢复只保留真实 catalog tool result 中的候选 ID，绕过的是 Worker 的结构化输出缺陷，不是空结果后的新检索路径。Evaluator 随后的 aggregate refs 通过 `_validate_evaluator_scope()` 的来源/引用 allowlist 检查；该检查不计算或强制每篇的 relevance threshold。`_validated_evaluator_candidates()` 又会将 aggregate 中已在 recall allowlist 的 `catalog:<id>` 展开为候选，没有要求逐篇 `keep=true` 或 relevance 达标。因此该路径直接得到足够候选，不会调用 `_promote_catalog_floor()`；后者在候选不足时从同一 recall pool 凑到最低 5 篇，是另一个会掩盖相关性不足的风险，但不是本次直接触发点。
4. 报告质量门禁确认了正文结构、真实 Evidence 引用、覆盖形状和最低篇数/字数等要求，没有核验每篇 selected paper 是否真正回答 `research_question`。正文自己指出跨域范围，但该说明不阻止以 `pass` 发布。

所以这不是“无结果之后退化为无关论文”，而是**主题没有进入搜索 query → 本地 top-N 召回低相关项 → aggregate evaluator 引用绑定被当成相关性确认 → selection/report gate 没有阻止偏题候选发布**。Search Worker formatting recovery是放大风险的一环，不是根因。

### 最小修复边界与临时输入约束

1. 计划生成应保留独立的 Intake topic，并将 topic 与用户批准的细粒度认证 facets 明确带入搜索 WorkItem；搜索 query 用精简的 topic/facet 术语，长 objective 继续作为研究目标和报告上下文，不要在每条 query 里重复整段自然语言。优先复用现有 Planner、Search WorkItem 和 catalog RAG，不引入新检索系统。
2. Evaluator 的 aggregate catalog refs 只能证明候选来自本轮受限召回，不能替代逐篇相关性判定。进入正式 selection 前，应对每篇候选要求与主题相符的 decision/score；不达标时返回真实短缺或请求用户扩大范围，禁止为满足五篇下限从不相关候选中凑数。相关性规则仍以用户批准范围为准，不按单个关键词把 RPKI 的 validation 或 Web 页面认证门背景视作用户认证研究。
3. 报告质量通过前加一道基于已批准 research question/facets 的选集一致性校验；不能仅因为正文诚实称作“跨域类比”就把偏题研究作为用户请求的正式报告发布。
4. 当前版本临时使用时，可把英文主题和关键认证子类直接写进 objective/facets，并在批准前逐条检查 plan preview 的 query 是否实际含有这些术语；若 query 缺主题词或召回候选只是相邻背景，应拒绝该计划/结果并调整范围，而不要批准后期待报告生成阶段自行纠偏。这只能降低风险，不替代上面两个服务器端门禁。

### 只读范围与未做事项

证据限于上述自然语言 E2E artifacts、指定 task/session 的 WorkItem/selection/search metadata、安全的 evaluator aggregate 摘要，以及 `session_plan_generation.py`、`planner.py`、`search_catalog_adapter.py`、`catalog_search_graph.py`、`agent_runtime.py` 和 `orchestrator.py` 的相关实现。没有读取隐藏思维链、凭据或原始模型拒绝正文，没有写数据库/重跑/部署，也没有执行测试；本段只记录诊断和修复边界。

## Memory-backed Agent 选集后置重入修复（2026-10-31）

独立复审发现 `_run_agent_work_items()` 的 memory-backed post-run 路径会重新展开 evaluator aggregate refs，并在候选不足时用默认软 floor 补足；这可能把主 synthesizer 逐篇相关性门禁已拒绝的候选重新计入 `selected_count` 或持久选集。此前相关 fake-runner 测试使用 `memory_repository=None`，未覆盖此分支。

### 修复与边界

- 后置路径现在只通过 `_validated_evaluator_candidates(..., relevance_threshold=...)` 构建候选；catalog floor 复用 `_promote_catalog_floor()` 且传入同一已批准阈值；持久选集 `_persist_agent_selections()` 也传入相同阈值并保留逐篇 relevance score。
- 阈值来自现有 paper-evaluator WorkItem 的 `relevance_threshold`（缺失或无效时沿用既有默认 0.2）。post-run 不再用 aggregate refs 独立扩充选择集合。主 Agent synthesis 入口的验证、floor 和持久化也已核对为传同一阈值。
- 受影响 Agent 入口逐项核对：`_validated_evaluator_candidates` 调用（主 synthesis 与 post-run）、`_promote_catalog_floor` 调用、`_persist_agent_selections` 的 evaluator/post-run/synthesis 调用均显式传入阈值。`PaperEvaluator(threshold=0.2, soft_floor=0.1)` 的独立非-Agent legacy 路径未改。
- 集成回归使用真实 `MemoryRepository` 实例驱动 `Orchestrator.run()`，分别注入高分 aggregate refs 和低于阈值的逐篇 decisions；断言最终 `selected_count == 0` 且 ResearchStore 持久 selections 为空。修复前两种情况都能在 post-run 变成 5 篇，测试先红后绿。

### 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest 'tests/research/test_agent_selection_persistence.py::test_memory_backed_post_run_does_not_repromote_rejected_decisions' -q`（修复前） | 1 | 2 failed；两组 `selected_count` 均错误变为 5 |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_agent_selection_persistence.py tests/research/test_report_catalog_metadata.py tests/research/test_validated_evaluator_candidates.py tests/research/test_report_synthesis_contract.py tests/research/test_research_report_matrix_bridge.py -q` | 0 | 95 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/orchestrator.py tests/research/test_agent_selection_persistence.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py tests/research/test_agent_selection_persistence.py` | 0 | 通过，无输出 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | test layout: ok |

未运行全量、部署、真实模型或数据库写入；未修改 legacy 独立入口。

## Agent 输出 safety 拒绝的安全诊断（2026-10-31）

为调查自然语言 E2E 中 `agent.output.safety` 的重复拒绝，本 slice 为现有递归安全校验增加固定原因分类和 schema 白名单路径。拒绝谓词、阈值和执行顺序保持原意；不保存、回显或日志记录命中值、URL、未知原始键名或模型输出正文。classification 只通过既有 `validation_diagnostic` / retry feedback 传递，不增加 endpoint 或业务 schema。

### 实现

- `_walk_safe()` 的原拒绝分支附加闭集分类：`forbidden_key`、`url_value`、`credential_pattern`、`size_limit`、`depth_limit`；`validate_safe_scope()` 根值形状错误标为 `shape_invalid`。字符串长度、URL、credential marker、敏感/可执行键、对象/数组大小及深度限制均保持拒绝。
- 安全路径只允许静态 schema 字段名与 `[]`；不在白名单的字段名统一折叠为 `unknown`。`PlanOutputInvalid` 的 message 保持固定安全字符串，不携带 offending key/value。AgentRuntime 再次校验路径与 classification 后，写入当前 `agent.output.safety` 的 field_paths/classification，并把相同信息传给下一次有界 retry；checkpoint/event 只存这些清理后元数据。
- ResearchStore 的 event 安全键白名单只增加 `safety_classification`，保留诊断分类；没有改变事件顶层形状或公开请求/响应 schema。
- evaluator 仍要求逐篇 `candidate_id`、`keep`、`relevance_score` 与本篇 catalog refs 并达到既有阈值；补回提示：title-only decision 属于 metadata-only，不代表 abstract/full-text evidence。`Do not invent abstract/content claims` 保留。

### 回归与验收

- 新增 runtime contract 覆盖 forbidden dynamic key、URL、credential assignment、超长值、超长列表和超深对象；断言拒绝依旧发生，classification/path 落在闭集内，未知键折叠成 `unknown`，value/URL/key marker 不进入 exception、feedback、checkpoint 或事件 JSON。
- 集成 fake model 先返回安全拒绝输出、再返回合法输出，验证 retry feedback 接收安全分类与白名单路径；使用临时 ResearchStore 验证事件投影保存分类和安全路径，不含 URL 原文。
- 原 `test_ollama_adapter_evaluator_allows_title_only_catalog_evidence` 的 `metadata-only` 断言保持，未删除或放宽逐篇评分要求。
- RED 阶段新安全诊断用例与既有 metadata-only 用例共 8 项失败；实现后定向领域测试通过。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_agent_runtime_contract.py tests/research/test_research_agent_approval_contract.py tests/research/test_research_plan_approval_contract.py tests/research/test_intake_plan_repair.py -q` | 0 | 114 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/plan_authoring.py backend/app/research/application/agent_runtime.py backend/app/research/infrastructure/research_store.py tests/research/test_agent_runtime_contract.py tests/research/test_research_agent_approval_contract.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/plan_authoring.py backend/app/research/application/agent_runtime.py backend/app/research/infrastructure/research_store.py tests/research/test_agent_runtime_contract.py tests/research/test_research_agent_approval_contract.py` | 0 | 通过，无输出 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | test layout: ok |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | test naming check passed |

未运行全量、真实模型、线上 E2E、生产/本机主数据库写入、部署或 Git 操作。安全分类只能定位拒绝类型及安全路径；要确定自然语言 E2E 中具体命中的值类型，仍需下次运行版本产生该闭集诊断。

## R3 Intake reasoning effort 拒绝诊断（2026-10-31，只读）

检查 `docs/sdd/plans/030/artifacts/20261031-natural-e2e-r3/`、部署 commit `44752b60` 的事件、当前代码能力解析路径，以及主目录 `data/model_capabilities.sqlite3` 中 `qwen3.8:27b` 的单行 capability metadata。数据库连接使用 SQLite `mode=ro`；未读取环境变量/密钥、未重探测模型、未改配置或发起 API/model/approval 请求。

### 观察

- R3 三次本地 Intake SSE 都在 skill activation/plan 之前返回 `REASONING_EFFORT_UNSUPPORTED`，meta 所选模型均为 `qwen3.8:27b`。第一次 `request.json` 未带 reasoning effort，走会话默认档位；后两次 `retry-request.json` 显式设为 `off`，结果仍相同。没有创建 session/task，因而不是 Intake 内容或 plan 校验拒绝。
- 同目录 `models.json` 标记 `qwen3.8:27b` 为 current，且给所有本地模型静态列出 `off/low/medium/high/xhigh`。但 `routes_models._build_local_models()` 只是直接返回 `list(REASONING_EFFORTS)`，不调用 Ollama 能力探测，因此该值是 UI 展示清单，不是当前模型的实测能力。
- 入口 `_start_message()` 使用 `_resolve_request_effort()`，随后走 `resolve_reasoning_effort()` → `get_reasoning_capabilities()`。该路径先读进程内 300 秒缓存，之后读 24 小时 SQLite 能力记录，最后才进行 Ollama 实测。与 `/api/models` 的静态清单是两套来源。
- 主目录 SQLite 中当前 `qwen3.8:27b` 记录为 `supported_efforts=[off,low,medium,xhigh]`、`default=xhigh`、`source=ollama_probe`，`probed_at=2026-10-30T16:56:49.103745Z`；该时间比第三次失败 SSE 的 `16:57:12.614Z` 早约 23 秒。数据库记录不支持 `high`，也不与 `/api/models` 展示完全一致；当前持久记录支持 `off`，与第三次入口拒绝不一致。
- 当前 `capability_scheduler.run_capability_sweep()` 探测后只 upsert SQLite；`get_reasoning_capabilities()` 对有效内存缓存优先返回，且内存缓存 TTL 为 300 秒。代码因此允许同一服务进程保留旧内存能力集，即使共享 SQLite 已更新；三次请求在约 82 秒内发生，符合这一陈旧缓存窗口。事件不包含所命中缓存的 `source/cached_at`，故这是强推断，不能凭现有材料确认具体 worker 的内存状态。
- 后续 `04-online-intake.sse` 明确选用 `deepseek:deepseek-flash` 与 `off`，成功输出 plan/intake，session 为 `9ff213128bd14ea8841e7bd65b7ace13`。`models.json` 仍将本地 Qwen 标为 current；线上模型 `capabilities.reasoning_efforts=null`。这符合现有逻辑：能力未知的线上模型允许 `off` 映射为 `think=false`。当前 plan 尚待审批。

### 诊断结论与证据边界

已确认的是两个 API 的能力来源不一致：`/api/models` 对本地模型宣称全档位支持；Intake 则按实测/缓存能力做严格校验。`models.json` 的支持清单不能作为实际解析结果的证据。主目录 DB 的新记录支持 `off`，但第三次 Intake 仍拒绝，最符合“处理该请求的进程仍使用旧内存 capability cache”；后台 sweep 写 SQLite 时没有同步失效进程缓存。当前资料没有每个 SSE 请求的 worker id、capability source/cache timestamp，也没有该服务实际 `OLLAMA_BASE_URL` 指纹，无法排除另一个 worker/环境持有不同旧记录；不应把它定论为部署了错误 env，也未发现需要改 Ollama LAN 配置的证据。

### 最小修复范围

1. `/api/models` 不应把所有 effort 静态宣称为本地模型已支持。最小做法是读与入口相同的已探测/缓存能力状态；记录缺失或不新鲜时显示 unknown/null，而不是虚报五档齐全。保持线上模型 capabilities unknown 的现状。
2. 消除进程内缓存与共享 SQLite 的更新不一致：能力写入/后台 sweep 后失效当前进程的相关内存项；并为多 worker 情况增加读取时以 SQLite `probed_at` 对比缓存时间的检查，或采取等价的版本化失效机制。这样支持档位变化可在 300 秒内反映到入口解析，且不会清空数据库或改 Ollama 配置。
3. 增加不含凭据的诊断字段/日志，仅记录 `capability_source`、安全模型 ID、requested effort、结果码和探测时间；对 SSE 返回继续保持既有错误码。用 fake resolver 测试“SQLite 新记录比 worker 缓存新”及 models API 与入口看到同一已知能力集。是否把该 telemetry 暴露到产品 API 不在本次只读诊断范围。

本次只读 artifact、代码和能力数据库；未写代码/数据库，未读取 credentials，未切换或修改长期模型设置，也未重复调用 Intake、模型或审批。

实现归属保持既有 Spec026/035 reasoning-capability 范围；先让 Spec030 自然语言主案例继续通过线上入口完成，不在报告验收前并行扩散配置变更。最小可复现应使用 fake capability store/prober 而不实际发请求：预置 worker 内存缓存缺少 `off`、SQLite 返回更新且含 `off` 的新记录，验证入口解析是否仍误拒；再模拟 sweep/upsert 后内存项失效，并验证 models listing 与入口解析读取相同能力投影。此诊断没有调用 capability probe 或模型，未实现、部署或审批。

## R3 evaluator safety feedback 与终态复核（2026-10-31，只读）

复查 `docs/sdd/plans/030/artifacts/20261031-natural-e2e-r3/09-events.sse` 与最终 `11-events.sse`，并对照 evaluator prompt、batch normalizer 和 runtime output validator。未读取模型原始输出/隐藏推理，未调用模型/API，未改代码或数据库。

### 复核结果

- 第一次观察到的 E1 `attempt=3` 拒绝是 `agent.output.safety`，安全诊断为 `forbidden_key`、路径 `output.safe_summary.unknown`。未知对象键按诊断契约被折叠为 `unknown`；因此事件能确认拒绝发生在 `safe_summary` 子树，但不能还原触发的具体键，也不能据此认定是 evaluation/CoT、`kept` 位置或某个特定字段导致。不得从隐藏输出猜测。
- 最终事件显示该拒绝后的安全反馈恢复了生成：E1 以 DeepSeek 完成，后续 critic 与 synthesizer 也完成。报告最终为 `partial` / `EVIDENCE_INSUFFICIENT`，仅选中 2/5；当前结果不是持续 safety failure，而是已批准最低论文数未满足。
- `agent_runtime.py::_role_contract_prompt()` 的 evaluator 指令要求对每篇候选分别输出 `candidate_id`、`keep`、`relevance_score`、理由和该篇 catalog refs，并称批量结果“may put ... decisions in a kept array”，但没有明确 `kept` 是顶层键，也没有给出完整 JSON 例子。生产 normalizer `orchestrator.py::_validated_evaluator_candidates()` 实际只在每个 output 的顶层读取 `output.get("kept")`，并逐项校验 ID、refs、keep 和既有相关性阈值。因此 prompt 对当前 parser 的关键容器位置表达不够精确。
- 通用 prompt 要求 `safe_summary` 是 object；`AgentRuntime._validate_output()` 确认它是 `Mapping`，再对整个输出递归调用 `validate_safe_scope()`。两边在外层类型上相符；validator 对 `safe_summary` 内层没有额外的业务字段 schema，而是继续执行既有 forbidden-key pattern、URL/credential、大小及深度安全规则。`forbidden_key` 说明安全门禁按既有规则拒绝了一个子键，不是放宽规则或改变 validator 的理由。

### 最小建议及范围

本次反馈已经让 evaluator 继续完成，故不因这条事件额外修改 prompt 或安全规则。若后续复现同一类 evaluator 容器错误，最小 prompt 澄清应明确批量 JSON 将逐篇决策放在**顶层** `kept` 数组，并给出一个不带额外 summary 字段的形状示例；仍保留每篇单独打分、选集 allowlist、既有阈值和安全 validator。若只需单条决策，继续支持现有单对象形状。`safe_summary` 如需示例，只用通用、无链接及凭据语义的普通字段；不得为了未知键而全局允许额外键。

后续可行性案例按已授权的“安全研究中的实证评估方法”主题继续；认证主题若真实相关且通过阈值的论文不足 5 篇，应保留 `partial` 并说明缺口，不用不相关论文补数、不降低相关性门槛。本次复核未执行该后续案例、未做模型调用、审批、数据库写入或部署。

## 最终静态检查清理（2026-10-31）

仅整理 `tests/research/test_report_content_rendering.py` 与 `tests/research/test_report_quality.py`：移除 imports 后多余空行以通过 Ruff `I001`；在 rendering 测试两处 `zip()` 上显式指定 `strict=False`，保持既有长度不一致时的截断语义并通过 `B905`。未改断言、生产代码或选集/质量行为。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_report_content_rendering.py tests/research/test_report_quality.py -q` | 0 | 30 passed in 1.13s |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check tests/research/test_report_content_rendering.py tests/research/test_report_quality.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | test layout: ok |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | no spec/task numbers under tests |

未运行全量测试、部署或模型/API调用，未执行 Git 操作。
