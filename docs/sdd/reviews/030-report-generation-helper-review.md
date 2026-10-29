# Spec030 Task08 Orchestrator 正文 helper 后端评审

日期：2026-10-29  
范围：当前 `orchestrator.py` 正文 helper、`test_report_quality_context.py`、质量合同与 Task08 context handoff。只读评审；未修改业务代码或测试。

## 结论

**BLOCK** — 发现 2 项 HIGH 合同问题：正文 AgentRun 把同一报告的累计用量当作本次 run 的初始用量；报告状态不按唯一状态映射区分证据缺口与其他质量失败。另有 1 项 MEDIUM 失败收尾风险：读取进度异常可使 helper 抛出异常，reservation 仍停留在 `generating`。

可信来源与身份边界总体通过：helper 核对 task owner/id、report/plan 版本、request key 对应的持久 reservation、WorkItem 身份与运行态；正文上下文从冻结选集、当前 plan 和持久 Evidence matrix 生成，并将传入正文/质量校验的证据限制为摘要或已验证全文。每次正文/改写前 claim、AgentRun 终态后 settle，revision 由 CAS 推进并限制为最多两次；正文经过 `validate_report_content` 与 renderer，再由 canonical CAS writer 保存。

## 问题

### [HIGH] 前序报告用量被当作新 AgentRun 的本次计数

**文件：** [orchestrator.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4677)

helper 把 `report_totals.model_loops_used/tool_calls_used` 写入新 `BudgetSnapshot.model_loops/tool_calls`。但 AgentRuntime 把这两个字段当作当前 AgentRun 已用量：初始化循环计数和该 run 的持久计数时都会读取它们（[agent_runtime.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2299)），随后用它们与本次 claim grant 的上限比较（同文件 [agent_runtime.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2461)）。`report_totals` 是跨同一 report version 多个 AgentRun 的总和，合同要求它用于 report 累加；只有 `task_totals` 应进入 task 累计字段（[质量合同](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/docs/sdd/plans/030/2026-10-29-report-quality-contract.md:47)）。

独立临时库探针先持久化并结算了一个 40 loops 的矩阵阶段 run，再调用正文 helper。helper 给下一次 AgentRun 的快照为 `model_loops=40, max_model_loops=40`；Runtime 会在第一次模型调用前触发单次 cap。更小的前序值也会占掉新 run 的 grant，并被写入新 run 计数，导致跨 run 重复计数和预算提前耗尽。现有假 runner 用例创建的 AgentRun 计数均为 0，未覆盖此情况。

**修复方向：** 新 AgentRun 的 `model_loops/tool_calls` 应从零开始；只有恢复同一个 AgentRun 时才恢复其本次计数。跨 run 累计继续通过 reservation ledger 与 task 字段表达。增加非零前序矩阵 run 的测试，并让真实 AgentRuntime 接收该快照，确认新 run 能消耗完整 claim grant。

### [HIGH] `partial` 状态掩盖了非证据类质量失败

**文件：** [orchestrator.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4825)

helper 无论 `validation.status` 是 `pass` 还是 `fail`，都会将 report 写成 `status="partial"` 并返回 `partial`（[orchestrator.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4832)）。合同的唯一映射规定：可信论文或比较/综合发现证据覆盖不足才是 `partial`；证据覆盖满足但 CJK、schema、引用或质量门禁失败应为 `draft`。质量通过但 Artifact/消息投影仍待处理时应继续 `generating`；不可恢复地放弃投影则保存为 `draft`（[质量合同](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/docs/sdd/plans/030/2026-10-29-report-quality-contract.md:83)）。

独立探针使用五篇已验证摘要、有效 comparison 与 findings，仅令正文 CJK 数低于门槛。校验结果为 `fail/CJK_COUNT_BELOW_MINIMUM`，但 helper 和持久 report 状态仍是 `partial`，stage 为 `draft_saved`。这把质量草稿误报成证据不完整；通过机器门禁但尚未交付也被同一 `partial` 分支处理。Handoff 对本 slice 的“始终 partial”描述与质量合同中的唯一状态映射冲突，应以合同为准。

**修复方向：** 保存前按合同区分证据覆盖失败、其他质量门禁失败和待发布状态；只有证据覆盖不足才用 `partial`。保留发布链未完成的 `generating` 或明确终止后的 `draft` 语义，不要以 `partial` 代替所有未发布结果。

### [MEDIUM] 进度读取/终态写入失败可留下 generating reservation

**文件：** [orchestrator.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4522)

初次 `read_progress()` 在 `fail_report` 定义后直接执行，未捕获异常（[orchestrator.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4543)）；质量循环内再次读取进度和重建上下文也有未保护的调用点（[orchestrator.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4635)）。若这些调用发生暂时性存储异常，helper 抛出异常，reservation 保持 `generating`。此外，`fail_report` 会吞掉 failed 状态更新异常，却仍向调用方返回 `status=failed`（[orchestrator.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4536)），可能造成调用结果与持久状态不一致。

隔离探针在首次 progress read 注入一次异常，确认异常传播且 report 仍为 `generating`、stage 为 `None`。测试没有覆盖该失败切点。失效或未运行 WorkItem 的早期分支也直接返回 `failed`，不会更新 report；如果这是终止而非可重试前置条件，同样可能留下进行中 reservation。

**修复方向：** 对每个可恢复的状态读取/推进异常执行明确的失败或恢复收尾；如果存储不可用导致不能可靠终结，向调用方返回“仍在恢复/状态未知”的结果，不要返回已终结 `failed`。为状态读取、状态 CAS 与 canonical 保存分别覆盖故障注入。

## 阶段与测试边界

生产调用目前已接入：`_run_agent_work_items` 先将报告 stage 设为 `evidence_review`，调用原 synthesis/matrix AgentRun，持久化 Evidence matrix 后再调用正文 helper（[orchestrator.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:2107)、[orchestrator.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:2386)）。正文 helper 本身仍只执行 `drafting → quality_check → targeted_revision`，并允许 `stage=None` 直达 `drafting`；当前调用者正常路径传入的 stage 是 `evidence_review`。我没有在该调用链看到持久化 `comparison` stage 的独立推进。`test_report_quality_context.py` 仍直接调用 helper，矩阵由 fixture 预先构造，fake runner 只伪造 completed AgentRun，因此本次测试未覆盖两次真实 dispatch 和阶段交接。handoff 也明确调用者负责两次 AgentRun 与统一收束 WorkItem（[context handoff](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/docs/sdd/plans/030/2026-10-29-report-context-backend.md:93)）。

## 验证

- 命令：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_quality_context.py`
- 结果：退出码 0；`9 passed in 0.96s`。
- 预算独立探针：前序报告用量 40 loops；新 run 快照仍为 40/40，Runtime 首次调用前即达到 cap。结果 FAIL。
- 状态映射独立探针：5 篇可信论文且只有 CJK 门禁失败；质量校验为 fail，但 durable report status 为 `partial`。结果 FAIL。
- 故障收尾独立探针：首次进度读取抛出临时异常后，report 仍为 `generating`、stage=None。结果 FAIL。
- 未运行全量测试、模型调用、部署或 Git 操作。

## Review Summary

| Severity | Count | Status |
|----------|------:|--------|
| CRITICAL | 0 | pass |
| HIGH | 2 | block |
| MEDIUM | 1 | block |
| LOW | 0 | pass |

Verdict: **BLOCK** — 修正预算快照和状态映射问题，并明确失败恢复语义后，重新评审 helper；生产调用接线仍需单独验证。

## 最新入口与 helper 修复复审（2026-10-29 20:36 Asia/Shanghai）

本节更新当前快照结论，保留上文首轮 BLOCK 作为历史发现记录。旧的 helper 内 run-local 预算、质量状态映射和一般状态读写失败收尾已分别修正；stage 交接与 comparison AgentRun 已接入。当前仍 **BLOCK**，以下两项 HIGH 尚未闭环。

### 已闭环与当前行为

- comparison 与 drafting/targeted revision 是分开的 Runtime 调用；stage 在调用前后通过 Store revision CAS 推进。每个独立正文/改写 AgentRun 使用 `model_loops=0`、`tool_calls=0`，累计量只留在 task counters。最新代码把这些独立调用的 Runtime `attempt` 设为 1 且使用唯一 run ID，因此两轮 targeted revision 不再产生 attempt=5（[orchestrator.py:4871](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4871)、[agent_runtime.py:2220](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2220)）。
- quality `pass` 保存 canonical 正文并保持 report `generating`，调用方返回 `running/REPORT_DELIVERY_PENDING`；仅证据覆盖类 failure code 映射为 `partial`，其他有正文质量失败映射为 `draft`；无正文失败映射 `failed`。Artifact/旧 fallback 不会在这些结果后被执行（[orchestrator.py:2492](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:2492)、[orchestrator.py:5045](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:5045)）。
- 读取/终结状态写失败时 helper 返回可恢复 `generating`；调用方保留仍运行的 synthesis WorkItem，不写终态。WorkItem dispatch 仅处理 `queued`，恢复扫描保留 terminal WorkItem，不会重开它（[orchestrator.py:2436](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:2436)、[orchestrator.py:1787](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:1787)）。
- Evidence 继续取自当前 task/plan 的已持久化矩阵，给 Runtime 的正文上下文仅保留 `abstract`/已验证 `fulltext` Evidence；正文质量校验使用同一 filtered matrix（[orchestrator.py:4639](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4639)、[orchestrator.py:4650](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4650)）。
- 入口集成测试确认原 matrix run 后有独立 comparison 和 drafting 调用、同一 WorkItem 仅在处理完后终结，成功路径不创建 Artifact。该测试中的 fake Runner **手工写入** AgentRun/checkpoint，故它模拟而非直接测试真实 Runtime 的 checkpoint 写入；生产 Runtime 在校验输出后将完整输出持久化到绑定 owner/task/WorkItem/AgentRun 的 checkpoint，再标记 AgentRun completed（[agent_runtime.py:2866](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2866)）。

### 当前阻塞项

#### [HIGH] 恢复时 matrix AgentRun 把 report 累计用量当作 run-local 已用量

**位置：** [orchestrator.py:2148](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:2148)

首次 synthesis/matrix dispatch 仍将 `report_totals.model_loops_used/tool_calls_used` 放入本次 `BudgetSnapshot.model_loops/tool_calls`（2146–2151）。这些字段被 Runtime 作为当前 AgentRun 的本地计数初始化（[agent_runtime.py:2299](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2299)），并在首次模型调用前与本次 claim grant 比较（[agent_runtime.py:2461](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2461)）。所以同一 reservation 在 `evidence_review` 阶段恢复且已有 40 loops/160 calls 时，新 run 的本地计数也为 40/160；如果 grant 是 40/160，Runtime 直接返回 `MODEL_LOOP_LIMIT_REACHED`，不会发出第一次模型调用。合同要求重试/恢复保留历史消耗，但新 AgentRun 的本地计数不能继承其它 run 的消耗（[质量合同:47](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/docs/sdd/plans/030/2026-10-29-report-quality-contract.md:47)）。

独立 Runtime 反例使用 `BudgetSnapshot(model_loops=40, max_model_loops=40, tool_calls=160, max_tool_calls=160)`，得到 `limit_reached/MODEL_LOOP_LIMIT_REACHED`，usage 仍为 40/160。当前自然语言入口测试只断言 comparison/drafting 的本地计数为零，没有对原始 matrix run 注入非零历史 report usage（[test_research_report_matrix_bridge.py:809](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_research_report_matrix_bridge.py:809)）。

**修复方向：** matrix AgentRun 的 local counters 应恢复同一个 AgentRun 的持久 counters；为 successor/new AgentRun 从零开始。增加同 reservation 已有 matrix AgentRun 用量、由 successor 恢复 evidence_review 的入口测试，并断言能消耗完整新 claim grant。

#### [HIGH] 合法持久 stage `quality_check`/`targeted_revision` 无法恢复，会把 canonical reservation 错误终结

**位置：** [orchestrator.py:4682](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4682)

Store 将阶段变化逐次 CAS 提交。helper 在 AgentRun 返回后先持久化 `quality_check`（[orchestrator.py:4983](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4983)）；若需改写，再分别持久化 `targeted_revision` 和 `drafting`（[orchestrator.py:4995](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4995)）。但 helper 入口只接受 `None/evidence_review/comparison/drafting`，把 `quality_check` 或 `targeted_revision` 作为不支持 stage 交给 `fail_report`，后者会把仍为 `generating` 的 reservation 写成 `failed`（[orchestrator.py:4555](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4555)）。

这不只是理论上的 stage 误配：在任一 CAS 后进程退出，下一次同 reservation 恢复都会命中此分支。特别是 quality pass 的 canonical 输出已保存但 helper 尚未返回时，stage 仍为 `quality_check`；重试会把已保存的合格正文 report 标成 `failed`。这违反合同的同 reservation 恢复、复用已完成 AgentRun 输出并保留 revision/usage 要求（[质量合同:42](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/docs/sdd/plans/030/2026-10-29-report-quality-contract.md:42)、[质量合同:47](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/docs/sdd/plans/030/2026-10-29-report-quality-contract.md:47)）。目前 36 项定向测试覆盖顺利完成的 revision CAS 序列，但未覆盖 CAS 后的中断与恢复。

**修复方向：** 定义可恢复的 `quality_check`/`targeted_revision` 状态处理：按 reservation/run ledger 找到并复用已完成 AgentRun checkpoint/output，或安全继续该 revision；对 canonical 已保存的 quality pass 结果直接返回 delivery pending。不要把合法的未发布中间状态因重启而升级成 failed。

## 本次验证

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_quality_context.py tests/research/test_research_report_matrix_bridge.py`：退出码 0，36 passed in 2.88s。
- 独立 Runtime 预算反例：40/40 本地计数立即返回 `limit_reached/MODEL_LOOP_LIMIT_REACHED`；确认 matrix dispatch 传入累计量会提前耗尽。
- Runtime attempt 边界探针：`attempt=5` 被拒为 `AGENT_OUTPUT_INVALID`。当前 helper 已将 comparison=WorkItem attempt+1、各独立正文/改写 run attempt=1；本复审不再将 revision attempt 超界列为未修复问题。
- 未运行全量测试、模型调用、部署或 Git 操作。

## 最新复审结论

| Severity | Count | Status |
|----------|------:|--------|
| CRITICAL | 0 | pass |
| HIGH | 2 | block |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **BLOCK** — 修复首次 matrix dispatch 的 run-local counter 恢复边界，并让持久中间 stage 能够幂等恢复后，再复审。

## 最新独立复审（2026-10-29）

### 原 BLOCK 项复核

- **run-local 预算计数：已修复。** 新 AgentRun 的 `model_loops/tool_calls` 从 0 开始，任务累计保留在 `task_*` 字段。`test_synthesis_dispatch_uses_run_local_budget_after_prior_matrix_run` 先持久化一个已消耗 40 loops/160 calls 的 matrix run，再走真实 `ResearchAgentRunner`；后续 run 获得完整 grant、实际调用模型并完成发布。
- **stage/checkpoint 恢复：已修复。** helper 接受持久化的 `quality_check`/`targeted_revision`，按同一 reservation 的 claim 找到 completed AgentRun，并校验 owner/task/session/WorkItem、checkpoint hash 与 output hash 后复用。定向用例覆盖 completed comparison checkpoint 重用、quality_check 中断后从 body checkpoint 校验/保存并再次重放不重新调用模型，以及 targeted revision 从已验证的上一稿 checkpoint 构造上下文。
- **质量状态和 revision 上限：已修复。** CJK 等非证据质量失败保存为 `draft`，通过校验但投递待恢复保持 `generating`，证据覆盖失败码走 `partial` 分支；最多两轮定向改写，第二轮仍失败时保存 `draft`，`revision_count=2`，并保留 settled claims。
- **同版本正式投递与终态门禁：已修复。** 自然语言入口用同一个 reservation report_version 持久化 report、三类 Artifact、completed Activity、通知和 WorkItem；canonical body 保存后重放的入口用例断言不再调用模型且完成同版本发布。质量/投递待恢复时 WorkItem 保持 running；只有 delivery 完成后才提交其 completed 状态。

### 当前阻塞项

#### [P1] Startup audit 将进行中 reservation 终结化后没有同版本 successor/rebind 恢复路径

质量合同明确要求：若 startup/task recovery 已把 reservation 绑定的 WorkItem 置为不可逆 `interrupted`，应新建同 task_type 的 successor 并回绑原 reservation；不得重开旧 row、分配新 report_version 或重置预算（[质量合同第 41–42 行](../plans/030/2026-10-29-report-quality-contract.md)）。当前 `ResearchService.recover_interrupted()` 调用 `mark_running_interrupted()`，后者将 running task 与其 running WorkItem 都收敛到终态 `interrupted`（`research_service.py:688–695`、`research_store.py:7880–7929`）。

新恢复 helper 只接受 reservation WorkItem 仍为 `running`（`orchestrator.py:4693`）；正常入口也要求返回的 reservation WorkItem 与当前 WorkItem 是同一 row 且为 `queued`，否则以 mismatch 失败（`orchestrator.py:2058–2071`）。`reserve_report_generation` 只将 reservation 绑定到当前可复用的 unbound queued item，或创建新的 reservation/report row；未发现任何将 generating reservation 的 work_item_id 在同 report_version 下 CAS 迁移到 successor 的 Store 操作（`research_store.py:6410–6457`）。因此完成 checkpoint 或 canonical `report_content` 后若进程重启并先经 startup audit，旧 row 终态化，恢复 helper 无法执行；当前同版本也无法继续完整 Artifact/message 投影，和第 42 行要求冲突。

**修复方向：** 增加有界 Store CAS：只允许同 owner/task/plan/request_key/report_version 的 generating reservation 从 terminal interrupted WorkItem 绑定到一个新的 queued successor；旧 WorkItem 保持终态，generation ledger、revision_count 和已有 AgentRun/checkpoint 原样保留。恢复入口随后复用同版已完成 checkpoint/canonical 输出，并走既有 publication 幂等接缝。

### 独立验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_quality_context.py tests/research/test_research_report_matrix_bridge.py` | 0 | 42 passed in 3.80s |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/orchestrator.py tests/research/test_report_quality_context.py tests/research/test_research_report_matrix_bridge.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py tests/research/test_report_quality_context.py tests/research/test_research_report_matrix_bridge.py` | 0 | 通过，无输出 |

Verdict: **BLOCK** — 原预算/阶段恢复/质量状态/改写与同版发布问题已闭环；上述 startup interrupted successor/rebind P1 尚未实现。未修改 Orchestrator 或 Store；本轮仅独立评审。

## Startup audit successor / 同版投递独立复审（2026-10-29）

**当前结论：PASS；上一节 P1 已关闭。** 本轮复审最新 `ResearchService` startup recovery、Orchestrator report-only resume/finalize 路径及其调用契约。原 BLOCK 章节作为修复前记录保留。未改生产代码或测试。

### 复核结果

- Startup audit 仍先将 running ResearchTask/WorkItem 转为终态 interrupted；之后只为 owner/task/current-plan/report-version/request-key 一致且仍为 `generating` 的 canonical reservation 安排 report-only 恢复。WorkItem 类型/role/task/plan 必须匹配 synthesizer reservation。原 task 不转回 running/completed。
- 原 reservation 仍指向 terminal `interrupted`/`completed` WorkItem 时，通过 Store CAS 创建同 report version 的确定性 successor；若 successor 已 queued 则重用，若上次 report-only worker 遗留 running，则先终结旧 successor 再接链。旧 WorkItem 不重开，Store ledger/claims 不重置。关键接缝见 [ResearchService.recover_interrupted 与 successor 调度](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/research_service.py:694) 和 [report-only worker dispatch](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/research_service.py:882)。
- 对同 reservation 的历史 Runtime claim，恢复 helper 从 claim 自带的旧 WorkItem ID 定位 AgentRun/checkpoint；只接受匹配 owner、task、session、work item、run、schema、hash 和 report version 的 completed checkpoint。历史 comparison checkpoint 实际被复用时，只为 successor 新建 drafting run；comparison claim 仍绑定旧 WorkItem，新的 claim 绑定 successor。相应检查见 [Orchestrator checkpoint recovery](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:5289)。
- 如果 canonical report_content 已保存但尚未完成投递，恢复会重新核验当前 Evidence/quality、确定性渲染并完成同版本投递；没有新增 Runtime/model 调用或 budget claim。已经 published 的 completed canonical 则走独立 finalize 路径，不创建 successor；WorkItem 保持 terminal，Task 保持 interrupted。[Orchestrator resume/finalize](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4630) [published canonical finalizer](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4710) [canonical body resume](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4847)。

### 验证

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_quality_context.py` — 退出码 0，**23 passed in 3.19s**。
- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_research_backend_slice.py::StartupAuditTests::test_recover_interrupted_converges_running_only` — 退出码 0，**1 passed in 1.04s**。
- 独立 checkpoint 恢复探针：先用真实 `ResearchAgentRunner` 和临时 SQLite 完成原 WorkItem 的 comparison run/checkpoint，再执行 startup audit。恢复保留 report version 1 和 Task `interrupted`；旧 WorkItem 保持 interrupted；新 successor 完成发布。恢复阶段只产生一个 drafting AgentRun，没有重跑 comparison；旧 claim 继续绑定旧 WorkItem，新 claim 绑定 successor。结果 PASS。
- 独立 canonical-only 投递探针：在原 WorkItem 上完成 comparison/drafting 并保存 canonical 正文后执行 startup audit。恢复把同版 reservation 绑定到 successor 并完成三类 Artifact 投递；旧 WorkItem 保持 interrupted，Task 保持 interrupted；模型调用 **2→2**、claim 数 **2→2**，没有新 Runtime 调用或预算 claim。结果 PASS。
- 精确测试内另覆盖 published canonical 的 terminal WorkItem 恢复：直接 finalize，不创建 successor，模型调用数不变（[test_startup_recovery_finalizes_published_canonical_from_terminal_work_item](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_report_quality_context.py:1096)）。
- 未运行全量测试、部署或真实模型。本轮没有修改业务代码或测试。

**当前 helper 与 startup recovery 评审：PASS。** 原 BLOCK 中的 startup interrupted successor/rebind P1 已闭环，没有新增 HIGH/P1 阻塞。

## Context field text-safety follow-up review — 2026-10-30

**当前窄审结论：PASS。** 该修复只在 `Orchestrator` 的 server-built report context 中使用 `_safe_report_context_text`；共享的 `report_synthesis._safe_text_input` 和 `_FORBIDDEN_PARTS` 未放宽。合法 facet `password authentication login security`、研究问题 `password authentication` / `token-based login` 可通过 builder、Runtime marker 校验，以及 model JSON → `report_content` 输出解析/schema/runtime 校验。

### 安全与兼容核对

- [orchestrator.py:106](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:106) 的上下文校验仍限制最大长度、文件路径/文件名、URL、控制字符，并拒绝凭据赋值与常见 secret 格式。测试覆盖合法 password/token 主题、`password=hunter2`、API key JSON、Bearer JWT、`sk-proj-...`；敏感值不会出现在对外诊断中。
- 该专用函数没有更改通用 artifact/report text guard；独立调用 `_safe_text_input("password authentication login security", ...)` 仍会按原策略拒绝，因此 title/最终渲染器等既有边界没有全局放开。
- 从真实 fixture 构建的 marker 经 `_validate_report_quality_context` 接受：包含 5 个 selected paper、5 条 evidence、2 个 approved dimensions；marker 仍使用 `report-quality-v1` 字段和版本绑定，没有 schema 放宽。
- 完整 JSON report envelope 经 `_parse_json_mapping`、`validate_report_synthesis_output`、Runtime `_validate_output("synthesizer", ...)` 顺序验证通过。`research_question`、5 篇分析的 method/finding、comparison statement 中的合法 “password authentication” / “token-based login” 均被保留，未被输出 schema 拒绝。
- **边界说明（非阻塞）：** 专用 builder 文本检查本身会接受非 JWT 形态的裸 `Bearer <opaque-value>`；Runtime marker 的现有 `validate_safe_scope` 仍会在构造模型输入前以 `REPORT_CONTEXT_INVALID` 拒绝该内容。独立探针确认 provider 不会被调用，因此未发现凭据进入模型的路径；若未来有绕过 Runtime marker 的新消费者，应将 Bearer 检测并入其信任边界。

### 定向验证

| 命令 / 探针 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_quality_context.py` | 0 | `29 passed in 3.36s` |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_content_runtime.py` | 0 | `19 passed in 0.65s` |
| 独立 builder → Runtime marker probe | 0 | 学术词通过，5 papers/5 evidence；共享通用 text guard 仍严格 |
| 独立 JSON parse → synthesis schema → Runtime output validation probe | 0 | 学术 password/token 文本完整保留，5 篇分析全部通过结构/引用校验 |
| 独立 opaque Bearer marker probe | 0 | 专用 builder 接受，Runtime marker 以稳定码拒绝，provider 未调用 |

本轮只审查上下文文本安全、marker 与 report_content 输出兼容；未修改业务代码/测试，未运行全量测试、模型或部署。

## Claim/Evidence ID namespace collision follow-up review（2026-10-30）

**当前窄审结论：PASS。** 本节仅复核模型局部矩阵 ID 的 task/plan namespacing、引用重写、持久化隔离和正文上下文读取。前文已经解决的 startup recovery BLOCK 保留为历史修复记录；本轮没有生产代码或测试修改。

### 独立核对

- [orchestrator.py:772](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:772) 对模型给出的原始矩阵先调用共享 `validate_synthesis_matrix_payload`，再以 `research_task_id + plan_version + ID kind + 原模型 ID` 的 SHA-256 生成确定性 Claim/Evidence ID，并再次执行同一 schema/context 验证（[orchestrator.py:914](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:914)）。计划版本、task ID、ID 格式和数量/重复项都先经既有校验；unknown Evidence refs 在映射前失败关闭。
- 改写覆盖 claim ID、claim 的 Evidence refs、Evidence ID/owner Claim ID、cell Claim ID 和 cell Evidence refs；计划维度 ID 保持服务端批准值，研究陈述/摘要/定位信息原样保留。后置验证再次确认重写后的 ownership 和 paper/snapshot/digest 绑定。hash ID 仍在既有 200 字符矩阵 ID 上限内。
- 新增矩阵测试验证两个 task 使用相同模型局部 `claim-1`/`evidence-1` 可并存、同 task/plan 重放得到相同映射且不覆盖另一 task；同一测试核对 claim/evidence/cell 关联及 statement 原样保留。unknown ref 用例要求固定 `REPORT_SCHEMA_INVALID`/field path 且不泄漏原始值；claim/evidence 持久化碰撞诊断仅落固定 reason/rule/path。
- 独立临时 SQLite 反例先保存旧 task 的未命名空间 `claim-1`/`evidence-1`，再让新 task 提交相同模型局部 IDs；旧行内容与引用未变，新 task 读回 task 专属 IDs。另一独立探针确认同一 task 的 plan 1 与 plan 2 生成不同 namespace。
- 独立上下文探针从 `persist_matrix=False` 的真实五篇已选论文/已验证摘要 fixture 出发，构建并持久化 5 条 namespaced Evidence；`read_matrix` 返回 5 条，`_build_report_quality_context` 也读回相同 5 个 namespaced IDs 和对应冻结摘要 excerpt。
- 另按上一轮补充要求，model JSON envelope 中的研究问题、逐篇 findings、comparison 和 synthesis finding 使用正常学术短语 `password authentication` / `token-based login`；`validate_report_synthesis_output` 和真实 `ResearchAgentRunner` 的 `evidence_review` report_content schema 路径均通过并保留文本。该探针仅覆盖 `report_content` 字段；标题/legacy section summary 的通用 `_safe_text_input` 保护保持原样。

### 定向验证

| 命令 / 探针 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_research_report_matrix_bridge.py tests/research/test_report_quality_context.py -q` | 0 | `57 passed in 5.29s` |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_report_content_runtime.py -q` | 0 | `19 passed in 0.61s` |
| 独立临时 SQLite 跨 task/legacy ID 碰撞探针 | 0 | 旧 task 行不变；新 task 使用不同 IDs |
| 独立 task/plan namespace 与五 Evidence context 探针 | 0 | plan 改变时 IDs 改变；builder 读回 5 条 namespaced Evidence/excerpt |
| 独立 academic password/token → synthesis schema → Runtime report_content probe | 0 | 正常学术文本通过并完整保留 |

**当前 ID namespacing 与 report_content 字段兼容窄审：PASS。** 未运行全量测试、部署、模型或 Git 操作。


## Report-only wrapper 与 terminal startup recovery follow-up（2026-10-30）

**当前窄审结论：PASS。** 本节复核 `run_report_only_generation`、session POST 的幂等提交、启动恢复和同版本 successor Store CAS；不重审前文已 PASS 的矩阵 ID namespace、Runtime/content schema、预算或 canonical publisher 实现。

### 复核结论

- `run_report_only_generation` 对 task owner/status、session owner/task/conversation、report id/version/plan、当前 synthesis WorkItem、reservation 的 report/version/work_item_id/request_key/fingerprint 做重复读取与绑定核验；候选必须是 5..64 个唯一项，citation allowlist 必须与每个候选的冻结 Evidence refs 完全相等。非法候选或 citation 在可信 reservation 绑定后通过状态 CAS 记为 failed；失败 CAS 未持久时只把 successor 收束到 interrupted 并返回稳定码，不声称失败已保存。入口只调用 report quality body helper 和同一 canonical publisher，不调用 Search/Evaluator，也不调用 `EvidenceMatrixService.build_matrix`。报告上下文从持久化选集与 matrix 读取；`comparison`、`drafting` 和最多两轮 targeted revision 仍走原 Runtime/checkpoint/budget claim 与 settle。[Orchestrator report-only wrapper](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:4815)
- wrapper 从不改 ResearchTask 状态。WorkItem 收束前重新读取并且只允许当前行仍为 `running` 时执行一次状态更新：质量失败按 report 状态映射为 failed；canonical 发布完成才 completed；投递待恢复保留 generating report 并将当前 WorkItem 标为 interrupted。参数化测试覆盖五种 terminal Task，另以 `EvidenceMatrixService.build_matrix` 必须失败的 monkeypatch 验证不重建矩阵，并断言只跑 comparison/drafting、报告走同一发布接点。[report-only wrapper tests](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_report_quality_context.py:1498)
- POST 同一 Idempotency-Key 先读回原 reservation，同一个 report_version/WorkItem 继续提交；若前一 WorkItem 已是 interrupted/completed 且报告仍 generating，则以 Store CAS 创建同版本 queued successor。不同 key 遇到 active generating report 时，在 matrix preflight 前返回 `409 REPORT_GENERATION_IN_PROGRESS` 与现有 report URL；该路径的回归测试将 matrix read 替换为抛错函数，确认不触发 preflight。same-key projection 也包含已持久化的 stable reason_codes，并与 quality failure/fallback codes 去重。[same-key reservation replay](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/report_generation.py:563) [durable reason-code projection](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/report_generation.py:692) [different-key conflict test](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_report_only_submission.py:261)
- 启动审计扫描所有 `TASK_TERMINAL` 状态；提交与恢复共享 `(task_id, report_version)` in-flight guard。只有 report 仍为 generating 且 reservation 身份、当前 plan、同 task synthesis WorkItem 均匹配时才恢复。Store 仅允许 task running/terminal、当前 active/completed plan、generating report，以及 predecessor 为 interrupted/completed 时绑定 successor；旧 WorkItem 不改写，report version、generation store_state/budget ledger 和历史 claim WorkItem IDs 不重置。[ResearchService startup selector](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/research_service.py:699) [shared recovery/submission guard](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/research_service.py:82) [Store successor CAS](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/infrastructure/research_store.py:6612)
- 我在合并快照中发现一个高置信 P1：Service 已让任意 terminal Task 的 `completed/published` canonical 进入 finalize，但 finalizer 原先只接收 `task.status == "interrupted"`。独立临时 SQLite 反例以 Task=`completed`、report=`completed/published`、Artifact/message 已准备但 completed notification 未落库为起点；startup audit 后 notification 仍 `0→0`，WorkItem 留在 interrupted，Runtime 模型调用保持 `2→2`。该问题已修复：finalizer 现在接受 `TASK_TERMINAL` 并在所有返回分支保留传入 Task 的实际状态。冻结测试覆盖 completed/partial/failed/cancelled/interrupted 五种状态。[terminal canonical finalizer](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:5285) [published canonical recovery test](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_report_quality_context.py:1244)
- 修复后的独立 completed-Task 探针两次执行 startup recovery：Task 保持 completed，report 保持 completed/published，completed notification 数量为 `0→1→1`，Runtime 模型调用为 `2→2`，reservation 仍绑定原 terminal WorkItem ID，没有新 successor。published canonical 直接做确定性验据复核与幂等 finalize，不重跑 Runtime。

### 定向验证

| 命令 / 探针 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_only_submission.py tests/research/test_report_generation.py tests/research/test_report_canonical_persistence.py tests/research/test_report_version_reservation.py` | 0 | `84 passed in 2.59s` |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_quality_context.py -k 'startup_recovery_finalizes_published_canonical_from_terminal_work_item'` | 0 | `5 passed, 36 deselected in 2.31s` |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_only_submission.py -k 'different_key_conflicts_with_active_generation_and_returns_existing_url or startup_recovery_rebinds_pending_report_for_any_terminal_task or same_key_replay_rebinds_pending_terminal_work_item_without_new_report_version'` | 0 | `13 passed, 14 deselected in 1.54s` |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_only_submission.py -k 'same_idempotency_key_replays_one_report_and_does_not_duplicate_executor_submission or different_key_conflicts_with_active_generation_and_returns_existing_url'` | 0 | `2 passed, 25 deselected in 1.04s`（durable reason-code projection 与 active 409 冻结后的复验） |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_canonical_persistence.py -k terminal_task_status` | 0 | `4 passed, 26 deselected in 0.28s` |
| 独立 terminal published canonical → 两次 startup recovery 探针 | 0 | Task 状态不变；notification `0→1→1`；Runtime calls `2→2`；原 WorkItem ID 保持、无 successor |

**当前 report-only wrapper 与终态恢复窄审：PASS。** 原先发现的 finalizer P1 已修复；没有剩余 P0/P1。未运行全量测试、部署、真实模型或 Git 操作。此前 helper review 的 startup successor、budget/checkpoint、evidence、quality 和 publisher 结论均保留为历史记录。
