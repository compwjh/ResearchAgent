# Spec032 Task14：ResearchReport 矩阵接线独立后端复审

日期：2026-10-09（Asia/Shanghai）  
角色：backend-reviewer（临时 Luna max）  
分支：`codex/spec032-final-acceptance`  
复审对象：`current-report-matrix-fix.md`、`backend/app/research/application/agent_runtime.py`、`backend/app/research/application/orchestrator.py`、`backend/app/research/application/report_synthesis.py` 及新增 `tests/research/test_research_report_matrix_bridge.py`。  
日志：`.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261009-005921.md`

## 结论

**BLOCKED_P1；P0=0；本切片暂不通过独立后端复审，不能以“矩阵/Canonical ResearchReport 已完成”部署。**

矩阵字段级校验本身方向正确：producer 只在服务端构造的 `matrix_context` 存在时被提示输出内部 `evidence_matrix`；候选必须落在服务端 allowlist；维度必须逐项等于已批准 facets；Evidence 只能是 `catalog`/`abstract`，并检查 frozen search snapshot 成员、`catalog_snapshot_id` 和服务端计算的 `abstract_digest`；矩阵字段也没有进入候选 artifact payload。因此未发现越权 fulltext、旧 artifact 内容被直接改写或公开 schema 被新增的问题。

但有两个 P1 使终态不安全：

1. 矩阵缺失、矩阵校验/落库失败以及 Canonical Report 生成失败都被当作可选降级记录日志，未设置 `synthesis_error` 或失败计数；后续任务仍可能以 `completed` 收口，而 versioned ResearchReport 实际不存在。这样会把“只有候选级 artifact”或“矩阵失败”展示成研究任务成功。
2. `EvidenceMatrixService.build_matrix()` 在候选级 report envelope 完整校验之前执行；矩阵 service 的 Claim、Evidence、Dimension、Cell 写入又分成多个独立事务。若后续候选 envelope 校验、artifact delivery 或某次矩阵写入失败，前置矩阵行可能已持久化，随后仍走候选 artifact fallback，形成孤立/半落库矩阵。

## 逐项核对

### 1. Snapshot 成员与摘要 digest：基本通过，存在精度风险

- `orchestrator.py:3286-3400` 优先取每条 selection 的 `source_search_id`；旧 NULL 行才回落到 task-level handle。
- 每个 handle 必须对应 `completed`/`partial` 且未过期的 SearchJob，并通过 `get_search_results(handle)` 找到同一 `catalog_paper_id`；没有用全局 catalog 行替代 frozen snapshot。
- `orchestrator.py:3366-3388` 从该 snapshot 取 title/abstract，并计算 SHA-256；`orchestrator.py:642-680,734-751` 再要求 payload locator 与服务端 context 完全匹配。
- 风险（P2）：实现先对 snapshot abstract 做 `.strip()` 再计算 digest（`:3375-3381`），而设计稿要求对原始 snapshot UTF-8 内容计算 digest。当前上游通常已规范化摘要，未形成已复现 P1，但应补 whitespace fixture，明确摘要规范化是否属于快照内容。

### 2. Allowlist 与 facets：字段级通过，持久化投影缺端到端断言

- `orchestrator.py:3255-3284` 只从当前 plan 的 `facets_json` 生成稳定 `facet-N` dimension；payload dimensions 采用严格对象相等比较（`:628-640`）。
- `orchestrator.py:642-680,719-725,770-791` 要求 context candidates、`allowed_paper_ids`、Evidence、Cell 的 paper/claim/dimension 引用闭合；越界 paper、digest 错误、fulltext、catalog 非 contextual、dimension drift 均 fail closed。
- 现有 `EvidenceMatrixService.build_matrix()` 会按 `ResearchStore.list_selections()` 展开所有 durable selection 的 missing cells（`evidence_matrix.py:180-232`），而新 context 的 allowlist来自 `validated_candidates`。正常路径两者应一致，但 selection 写入失败/旧 selection 与本次 evaluator 子集不一致时，没有在接缝处断言二者相等；应加入集一致性测试，避免 canonical projection 暂时出现 context 外的 Paper cell。

### 3. Producer prompt/parser：主要字段一致，但上界不一致

- `agent_runtime.py:124-146` 明确告知 synthesizer 只有在 `matrix_context` 存在时才可输出内部 `evidence_matrix`，并禁止 fulltext、URL、document/chunk 和自造 dimension。
- `_validate_synthesis_matrix_payload()` 的 required keys、枚举、locator、支持性 Claim 和 Cell 闭合校验与上述语义一致。
- 但通用 `validate_safe_scope()` 仍对任意嵌套 list 施加 64 项上限，而矩阵 parser 在 `orchestrator.py:690` 允许 claims/evidence/cells 各至多 256；例如 5 个候选 × 16 个批准 facets 的合法 cell 数可超过 64，运行时会在矩阵 parser 前拒绝 producer 输出。应统一上界并在 prompt 中明确，或为内部矩阵使用同等安全的有界规则。

### 4. 缺矩阵与错误终态：P1

- `orchestrator.py:2070-2095` 对 invalid/缺失矩阵只写 warning；`synthesis_matrix_error` 不会进入 `synthesis_error`。
- `orchestrator.py:2112-2126` 对 `ReportGenerationService.generate(report_version=None)` 的任意异常也只写 warning，不改变任务状态。
- `orchestrator.py:2177-2209` 的最终状态只看 `failures`/`synthesis_error`。因此候选级 `ReportDeliveryService.deliver()` 成功、但 matrix 未建或 canonical report 失败时，仍可能 `final_status="completed"`，返回 artifact ID，却没有可读的 versioned ResearchReport。
- 这是“缺矩阵不伪造”和“错误不假 completed”的直接违反；当前测试没有覆盖该路径。

### 5. 半落库顺序：P1

- 新接线在 `orchestrator.py:2077-2088` 先调用 `EvidenceMatrixService.build_matrix()`，直到 `:2096` 才调用 `validate_report_synthesis_output()`，随后才 `consume_validated_output()`/artifact delivery。
- `EvidenceMatrixService` 虽然在 `:235` 前完成内存校验，但 `ResearchStore.save_claim()`、`save_claim_evidence()`、`replace_comparison_dimensions()`、`replace_comparison_cells()` 分别打开并提交事务（`research_store.py:5763-5904`）；不是一笔跨表事务。
- 因此后续候选 envelope、artifact 或 canonical report 失败时，前置 Claim/Evidence/Dimension/Cell 可能留在库中，而外层把错误降级为候选 artifact fallback；下一次显式 report 读取可能把这份孤立矩阵当作可生成报告的事实。
- 最小修复方向：先完成候选 envelope 的全部语义校验，再执行矩阵构建；矩阵多表写入需复用一个原子 store transaction（或等价可验证补偿），任何 build/report 异常都必须阻止 `completed` 并保留稳定错误码。不要靠扩大 catch 或只清 UI 状态解决。

### 6. 旧 artifact hash 与新 report version：实现路径通过

- `orchestrator.py:806-832` 会先从模型 envelope 分离 `evidence_matrix`，再重算候选级 `output_hash`；`SynthesisResult.evidence_matrix`（`report_synthesis.py:321-330`）没有进入 `ReportSynthesisOutput`、Markdown、HTML、citation manifest 或 artifact envelope。
- `ReportDeliveryService` 仍按原候选 `report_version=plan_version` 查 immutable artifact；因此旧 artifact content hash 不因矩阵字段改变。
- `ReportGenerationService.generate(report_version=None)`（`report_generation.py:217-257`）复用 `next_report_version()`，而 store 版本计算同时考虑已有 report 和 artifact（`research_store.py:5927-5941`），再由唯一约束拒绝覆盖；已有 artifact v1 时正常新 canonical report 应为 v2。该点通过既有定向测试，但没有新接缝的真实 Orchestrator 版本/哈希集成测试。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py` | 0 | `8 passed in 0.75s` |
| `.venv/bin/python -m pytest -q tests/research/test_evidence_matrix.py tests/research/test_report_generation.py tests/research/test_report_synthesis_contract.py tests/research/test_agent_runtime_contract.py::test_fake_output_is_structured_and_checkpointed tests/research/test_research_agent_approval_contract.py::test_ollama_adapter_synthesizer_requires_bounded_delivery_shape` | 0 | `43 passed in 1.89s` |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_report_catalog_metadata.py tests/research/test_research_runtime_contract.py tests/research/test_search_id_bridge.py` | 0 | `79 passed in 1.28s` |
| `.venv/bin/ruff check backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py backend/app/research/application/report_synthesis.py tests/research/test_research_report_matrix_bridge.py` | 0 | `All checks passed` |
| `git diff --check -- backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py backend/app/research/application/report_synthesis.py` | 0 | 通过；无冲突标记 |

这些通过结果只证明字段级 validator、既有 matrix/report service 和运行时基础合同未回归；新增测试没有覆盖真实 Orchestrator producer→matrix→artifact→canonical report，也没有覆盖失败注入、跨表原子性、任务终态或旧 hash/version 的接缝。

## 最小 backend-dev 修复与测试建议

1. 在 `orchestrator.py` 先执行 `validate_report_synthesis_output()`/candidate semantic consume 的纯内存校验，再调用矩阵 build；矩阵 build 失败、Canonical Report 失败或矩阵 extension 缺失时设置稳定 `synthesis_error`/degraded 状态，禁止任务以 `completed` 收口。保留候选 artifact fallback，但明确它不是 Canonical ResearchReport。
2. 为矩阵写入提供单事务/可验证补偿边界；至少用故障注入证明 Claim/Evidence/Dimension/Cell 任一写入失败后不会留下可被 `read_matrix()` 读取的半成品。
3. 在现有 `tests/research/test_research_report_matrix_bridge.py`（按功能命名）补接缝测试：真实 frozen snapshot 成员与 whitespace digest、selection allowlist 集不一致、65+ cells 上界、invalid candidate envelope、build 抛错、report generation 抛错；分别断言没有 canonical report、旧 artifact hash 不变、旧 report 不覆盖、任务不是 `completed`。
4. 修复后只需重跑本报告列出的矩阵/报告/运行时定向集合和 ruff；无需全量回归或部署，待 P1 复审通过再进入 Spec032 收口门禁。

## 复审范围与风险

- 本轮未修改任何业务代码、既有测试或其他 agent 文件；只新增本复审报告和 reviewer 日志。
- 未部署、未启动服务、未读写生产数据、未读取或输出 `.env`/密钥，未运行全量回归。
- 风险保留：当前定向测试全绿不能抵消 P1；在错误终态、半落库和 canonical report 失败传播修复并补真实接缝测试前，生产环境可能出现“任务 completed + 只有候选 artifact/孤立矩阵”的状态。

## 最新矩阵 P1 修复独立复审（2026-10-09 02:07 CST）

**结论：BLOCKED_P1；P0=0；本轮新增残余 P1=1。** 本轮没有修改业务代码、测试或其他 agent 文件；只追加本报告与 reviewer 日志。此前报告中的“候选 envelope 早于矩阵写入”“四表独立事务”“矩阵/报告异常仍可 completed”三项实现缺陷，经实际 diff 与定向测试核对已基本修复，但 Canonical Report 失败仍会先发出 completed 事实，尚不能以“失败不会假 completed”通过。

### 已验证通过

1. **候选 envelope 全校验先于矩阵写库。** `orchestrator.py:2067-2081` 先检查 synthesizer run、调用 `validate_report_synthesis_output()` 和 `consume_validated_output()`，`EvidenceMatrixService.build_matrix()` 仅在 `:2096-2107` 之后执行；矩阵 extension 本身则在 producer 回写时由 `_separate_synthesis_matrix()` 完成服务端 context/allowlist/facet/locator 校验。未见 envelope 失败后遗留矩阵行的路径。
2. **矩阵四表写入已经是单事务。** `evidence_matrix.py:234-249` 只调用 `ResearchStore.persist_evidence_matrix()`；`research_store.py:5762-5890` 在同一个 `BEGIN IMMEDIATE` 中写 Claim、Evidence、Dimension、Cell，并统一 rollback。故障注入 `test_matrix_rows_roll_back_as_one_unit_when_store_write_fails` 在首轮写入后抛错，四个 projection 列表均为空。
3. **缺矩阵与矩阵 build 失败不再以任务 completed 收口。** `orchestrator.py:2083-2117` 将缺失/非法/build 异常归一为 `MATRIX_NOT_READY`；`test_matrix_build_failure_cannot_close_agent_task_as_completed` 实际断言 task 为 `partial`、无 `ResearchReport`，且临时探查 notification 仅为 `partial/failed/partial`，未出现 completed。
4. **原始 abstract digest 通过。** context 构造 `orchestrator.py:3423-3437` 对 frozen snapshot 的未 trim UTF-8 内容计算 SHA-256；validator `:657-668,749-756` 按同一原始字符串校验 digest/locator。空白前后缀 fixture `test_matrix_bridge_hashes_exact_snapshot_abstract_bytes` 通过。
5. **64 上限一致。** parser 的 `_MATRIX_MAX_ITEMS=64` 与 claims/evidence/cells 检查在 `orchestrator.py:682-696`，producer prompt `agent_runtime.py:133-138` 同样明确 64，通用 runtime `plan_authoring.py:101-105` 也以 64 拦截嵌套列表；65 项 fixture `test_matrix_bridge_uses_same_bounded_array_limit_as_runtime` 通过。矩阵内没有遗留 256 上限。

### 残余 P1：Canonical Report 失败仍产生 completed 事实

`orchestrator.py:2118-2126` 在 `matrix_built=True` 时先调用 `ReportDeliveryService.deliver(... notification_kind="completed")`，而 Canonical `ReportGenerationService.generate(report_version=None)` 直到 `:2127-2142` 才调用。若 generate 抛出，代码只设置 `synthesis_error="REPORT_NOT_READY"`，最终 task 确实是 `partial` 且无 `ResearchReport`，但已持久化候选 artifact、completed activity message，并已发出 completed notification；随后才追加 failed/partial notification。

实际临时探查（复用新增故障注入 helper，未写项目文件/生产库）得到：

```text
partial REPORT_NOT_READY
[('completed', 'research-report:task-matrix-terminal:1'),
 ('failed', 'research-report:task-matrix-terminal:1:failed'),
 ('partial', 'research-report:task-matrix-terminal:1:partial')]
```

这与本任务要求的“report 失败不假 completed”不一致：任务状态虽正确降级，但用户可见的完成事实先于 canonical report 成功证明。`ReportDeliveryService.deliver()` 还在 `report_synthesis.py:661-673` 将 activity message 持久为 `completed`，所以只把 notification_kind 改成 `partial` 不能单独消除该信号。

**最小修复建议：** 将 Canonical `ReportGenerationService.generate()` 的成功作为 completed delivery/notification 的前置门禁；失败时只保留候选 artifact 的明确 partial/fallback 语义，并避免创建/更新 completed activity message。若必须保留候选 artifact，增加不改变公开 schema 的降级 delivery 分支，且其 notification/message 状态必须与 partial 一致。补一个真实 Orchestrator 故障注入断言：report generation 抛错时 `list_research_reports()` 为空、task/status/terminal 为 partial、所有通知不含 completed、activity message 不为 completed。

### 定向验证与范围

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py` | 0 | `13 passed in 1.46s` |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py tests/research/test_evidence_matrix.py tests/research/test_report_generation.py tests/research/test_report_synthesis_contract.py tests/research/test_agent_selection_persistence.py` | 0 | `62 passed in 2.33s` |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_report_catalog_metadata.py tests/research/test_research_runtime_contract.py tests/research/test_search_id_bridge.py` | 0 | `79 passed in 1.29s` |
| `.venv/bin/ruff check backend/app/research/application/agent_runtime.py backend/app/research/application/evidence_matrix.py backend/app/research/application/orchestrator.py backend/app/research/application/report_synthesis.py backend/app/research/infrastructure/research_store.py tests/research/test_research_report_matrix_bridge.py` | 0 | `All checks passed` |
| `git diff --check --`（仅上述相关路径） | 0 | 通过 |

未运行全量回归、未启动/部署服务、未写生产数据；唯一需要 backend-dev 的下一步是修复上述 delivery 顺序/降级消息状态并补定向故障注入测试，之后再由 backend-reviewer 复审。

## 最终矩阵接线复审（2026-10-09）

**结论：PASS（P0=0，P1=0）；上一轮残余 P1 已关闭。** 本轮只追加本复审报告与 reviewer 日志，未修改业务代码、测试或其他 agent 文件，未部署、未写生产数据、未运行全量回归。

### 逐项证据

1. **Canonical generate 已成为 completed delivery 的前置门禁。** `orchestrator.py:2118-2145` 在 `matrix_built` 后先调用 `ReportGenerationService.generate(report_version=None)`，成功后才调用 `ReportDeliveryService.deliver()`；delivery 的 notification kind 由 `synthesis_error`/failure 状态决定。Canonical 失败不会先创建 completed activity/notification。
2. **失败事实全部降级且不发 completed。** `ReportDeliveryService` 的 `report_synthesis.py:661-681` 将 `notification_kind="partial"` 映射为 activity message `partial`；真实故障注入得到 task/result `partial/REPORT_NOT_READY`、terminal `partial`、activity `partial`、通知序列 `partial, failed, partial`，其中没有 completed。`failed` 是现有失败审计事实，主 delivery 事实仍为 partial；不存在 completed 信号。
3. **真实 AgentRun 与 artifact immutable 保留。** 失败场景的三个 artifact 均绑定实际 synthesizer AgentRun，AgentRun 可由 store 读取，三个 content hash 均等于内容 SHA-256；candidate artifact fallback 没有伪造 AgentRun，也没有覆盖 immutable 内容。
4. **动态 report version 正确。** 无旧 artifact 场景生成 ResearchReport v1、artifact v1；已有 artifact v1 场景生成 ResearchReport v2，原有三个 v1 artifact 的 ID、版本和内容 hash 保持不变。`research_store.py:6056-6070` 的 `next_report_version()` 同时读取已有 report/artifact，未发现硬编码版本。
5. **此前已通过的矩阵安全项保持不回归。** envelope 校验顺序、四表单事务 rollback、原始 abstract digest、64 上限及 allowlist/facet/locator 校验在本轮定向集合中继续通过。

### 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py` | 0 | `15 passed in 1.66s` |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py tests/research/test_evidence_matrix.py tests/research/test_report_generation.py tests/research/test_report_synthesis_contract.py tests/research/test_agent_selection_persistence.py` | 0 | `64 passed in 2.56s` |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_report_catalog_metadata.py tests/research/test_research_runtime_contract.py tests/research/test_search_id_bridge.py` | 0 | `79 passed in 1.31s` |
| `.venv/bin/ruff check backend/app/research/application/agent_runtime.py backend/app/research/application/evidence_matrix.py backend/app/research/application/orchestrator.py backend/app/research/application/report_generation.py backend/app/research/application/report_synthesis.py backend/app/research/infrastructure/research_store.py tests/research/test_research_report_matrix_bridge.py` | 0 | `All checks passed` |
| `git diff --check --`（上述相关路径） | 0 | 通过 |

**交接结论：** 矩阵接线本轮 P0/P1 清零，可交给架构师/Spec032 收口门禁；仍不等同于全量回归或真实 API/E2E 部署验收。
