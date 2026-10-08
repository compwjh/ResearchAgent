# Spec032 Task14：自然语言研究矩阵/ResearchReport 接线复核

日期：2026-10-08（Asia/Shanghai）  
角色：backend-dev（临时 Luna max）  
分支：`codex/spec032-final-acceptance`  
范围：只核对并尝试把自然语言研究主链接入既有 Spec030 `evidence-report-v1`；不改候选级 artifact、不解析 Markdown、不新增 schema/表/API/AgentRun、不部署、不写生产数据。

## 结论

**BLOCKED_P1；P0=0；当前不能把该切片部署为“自然语言主链可生成 canonical Matrix/ResearchReport”。**

本轮没有修改业务代码或领域测试。定向红测确认当前真实 synthesizer producer 不是 Claim/Evidence/Dimension/Cell producer，而是候选级报告 producer：它只声明并输出 `report_version`、`sections`、`citation_manifest`、`artifact_ids`。现有真实代码中没有可安全传给 `EvidenceMatrixService.build_matrix()` 的结构化矩阵 payload，因此不能按要求接线；若从候选数量、citation、sections 或既有 Markdown 推导 Claim/Evidence，会违反“不可虚造 claim/不解析 Markdown”的边界。

候选级 artifact 链本身未被触碰，已有 artifact 仍保持不可变。若以后取得合法矩阵 payload，再调用现有 `ReportGenerationService.generate(..., report_version=None)`，由既有 `next_report_version()` 在 artifact v1 后分配 canonical v2；本轮没有伪造该版本。

## RED 证据

执行的定向红测（只读导入，不改文件）：

```text
.venv/bin/python -c 'from backend.app.research.application.agent_runtime import ROLE_OUTPUT_FIELDS, _role_contract_prompt; needed={"claims","evidence","dimensions","cells"}; actual=set(ROLE_OUTPUT_FIELDS["synthesizer"]); assert needed <= actual, f"synthesizer contract missing: {sorted(needed-actual)}"; assert "evidence-report-v1" in _role_contract_prompt("synthesizer", has_tool_results=True)'
```

退出码：`1`。实际失败：

```text
AssertionError: synthesizer contract missing: ['cells', 'claims', 'dimensions', 'evidence']
```

这不是 locator 数据偶发缺失，而是 producer 合同根本没有矩阵字段；prompt 同样没有 `evidence-report-v1` 结构化输出声明。

## 代码事实与安全阻塞

1. `backend/app/research/application/agent_runtime.py:92-97` 的 `ROLE_OUTPUT_FIELDS["synthesizer"]` 只有候选级四字段；`:124-133` 的 synthesizer prompt 明确要求 sections/citation，并要求只比较 supplied catalog metadata。
2. `backend/app/research/application/orchestrator.py:1616-1623` 只保存并绑定候选级 `synthesis_output`；`:1774-1795` 只调用 `validate_report_synthesis_output()`、`ReportSynthesizer.consume_validated_output()` 和已有真实 `ReportDeliveryService.deliver()`，没有矩阵 producer 或 `build_matrix()` 接缝。
3. `backend/app/research/application/report_synthesis.py:65-77,121-133` 的 `ReportSynthesisOutput` 使用 `extra="forbid"`。直接把 `claims`/`evidence`/`dimensions`/`cells` 塞进现有 artifact synthesis payload 会被既有输出合同拒绝；为此扩展模型或 role contract 将是新的/改变的 producer 合同，不是当前代码中已存在的可复用合同。
4. `EvidenceMatrixService.build_matrix()` 需要非空 Claim 和稳定比较 Dimension；`:113-122` 还要求 catalog locator 的 `catalog_snapshot_id`、abstract locator 的 digest，fulltext locator 的 document/chunk/page/hash/manifest/chunker 全部可验证。当前 `_catalog_evidence_view()` 与 synthesizer 输入只有候选 ID、`catalog:<id>` ref 和受限 metadata，不提供一套完整的 Claim/Evidence/Dimension/Cell payload，也没有由计划确认的 comparison-dimension 字段。
5. 仓库的 `build_matrix()` 调用仍只有显式 matrix API 路径；自然语言 Orchestrator、evaluator、auto-import 没有现成结构化 producer。把五个候选 ID 或五个引用计作 Claim/Evidence，或从 sections/Markdown 反向拼 locator，均不满足 Spec030 的可回查合同。

因此本轮不能安全写一个“看起来接通”的 adapter：它要么产生伪 Claim/Dimension，要么猜测 catalog/abstract locator，要么改动现有 synthesizer 输出 schema。三者都超出已确认范围或违反明确禁止项。

## 定向回归

既有矩阵、报告、候选级 synthesis 和 agent 合同保持通过：

```text
.venv/bin/python -m pytest -q tests/research/test_evidence_matrix.py tests/research/test_report_generation.py tests/research/test_report_synthesis_contract.py tests/research/test_agent_runtime_contract.py::test_fake_output_is_structured_and_checkpointed tests/research/test_research_agent_approval_contract.py::test_ollama_adapter_synthesizer_requires_bounded_delivery_shape
```

退出码：`0`；结果：`43 passed in 1.85s`。

范围核对：

```text
git diff --name-only -- backend/app/research backend/app/api/routes_research.py tests/research
git diff --check -- backend/app/research tests/research
```

两条命令均退出码 `0`；本轮没有业务源码/领域测试 diff。未运行全量、未启动服务、未写入生产数据。

## 解除阻塞所需的最小前置

需要架构师先确认一个**真实 producer 合同扩展**，再由 backend-dev 实现定向接线：

1. 让真实 synthesizer（或已存在且真实绑定的结构化 producer）在既有 `evidence-report-v1` 语义下提供 Claim/Evidence/Dimension/Cell；不要把候选级 sections 或 Markdown 当作矩阵来源。
2. producer 输入必须带服务端确认的 allowlist、计划版本和 comparison dimensions；每条 catalog/abstract/fulltext Evidence 必须带可验证 locator（包括 `catalog_snapshot_id`、digest 或既有 EvidenceUpgrade provenance），不能由模型/adapter 猜测。
3. 在 application 层先用 `EvidenceMatrixService.build_matrix()` 完整验证并持久化，再调用 `ReportGenerationService.generate()`；报告版本省略以复用 `next_report_version()`，旧 artifact/旧 `ResearchReport` 只读保留。
4. 补一条按功能命名的领域集成测试：无结构化 payload 时 `MATRIX_NOT_READY`/不写入；合法 payload 时验证 allowlist/locator、矩阵落库、canonical 新版本生成及旧 artifact hash 不变。不要新增公开请求 schema、表、状态机或伪造 AgentRun。

在该 producer 合同获确认并真实产出前，当前正确行为仍是 fail closed：候选级 artifact 可以存在，但 `GET evidence-matrix`/versioned `ResearchReport` 不应被冒充为已完成。

## 最新架构师决定：允许内部 producer 扩展（设计稿，待根 Agent 确认）

架构师已明确：上一节的“当前无 payload”是需要实施的内部接缝缺口，不再是永久范围阻塞。允许在已确认 Spec030/032 范围内扩展真实 synthesizer 的 prompt 和内部结果解析；允许给内部 `SynthesisResult` 增加向后兼容的可选矩阵字段。仍然禁止公开 API/request schema、数据库表、第二套状态机、Markdown 反解析、从候选数量/citation 拼 Claim，以及伪造 AgentRun。

本轮仍只做设计，未修改业务代码或测试。实施前请根 Agent 确认以下最小内部合同。

### 允许改动的路径

| 路径 | 最小职责 | 明确不做 |
|---|---|---|
| `backend/app/research/application/agent_runtime.py` | 仅扩展 synthesizer 的可选输出说明：有 `matrix_context` 时可输出 `evidence_matrix`；保留原有候选级必填字段和向后兼容行为 | 不把矩阵字段加入所有角色的强制字段，不改公开 schema、工具白名单或 AgentRun 状态机 |
| `backend/app/research/application/orchestrator.py` | 从既有 server-owned search snapshot、已批准 plan facets 和 evaluator allowlist 构造内部 context；拆出并校验可选矩阵；调用既有 `EvidenceMatrixService.build_matrix()` 和 `ReportGenerationService.generate()` | 不从 `sections`/Markdown 解析，不用全局目录回填快照证据，不创建新检索/下载/导入路径 |
| `backend/app/research/application/report_synthesis.py` | `SynthesisResult` 增加默认值为 `None` 的 `evidence_matrix` 内部字段；`ReportDeliveryService` 忽略该字段，保持 artifact 内容/hash 合同不变 | 不把矩阵放入 `ReportSynthesisOutput` 持久化 payload；不改变候选 artifact markdown/html/citation manifest |
| `tests/research/test_research_report_matrix_bridge.py` | 新增按功能命名的 producer/context/allowlist/locator/版本接缝测试 | 不改旧测试命名，不写生产数据，不做全量回归 |

`backend/app/research/application/evidence_matrix.py`、`report_generation.py`、`routes_research.py`、`research_store.py` 原则上不需要改：它们分别继续负责既有矩阵验证/持久化、`next_report_version()` + immutable `ResearchReport` 和原公开接口。若实施中必须改这些文件，应先回到范围确认。

### 内部 producer envelope（不成为公开 API）

真实 synthesizer 继续输出现有候选级 envelope，并在有 context 时附加一个可选顶层字段：

```json
{
  "schema_version": "runtime-v1",
  "report_version": 1,
  "sections": [],
  "citation_manifest": [],
  "artifact_ids": [],
  "safe_summary": {},
  "source_refs": [],
  "evidence_matrix": {
    "schema_version": "evidence-report-v1",
    "plan_version": 1,
    "dimensions": [],
    "claims": [],
    "evidence": [],
    "cells": []
  }
}
```

`evidence_matrix` 是内部 runtime extension，不加入现有 `ReportSynthesisOutput`（该模型继续 `extra="forbid"`）。解析器先以现有安全边界校验扩展，再把它从候选 artifact envelope 中分离；候选 artifact 的 `output_hash` 在分离后按现有 helper 重新计算，矩阵 payload 不进入 artifact JSON、markdown、HTML 或 citation manifest。模型没有输出 `evidence_matrix` 时，候选级 artifact 仍按旧路径工作，但不生成 canonical `ResearchReport`，不作默认/伪造补全。

矩阵字段语义固定为既有 Spec030 合同：

- `dimensions` 必须逐项复制 server-provided plan dimensions，`dimension_id`、label、definition、order 不得由模型改写；
- `claims` 必须带 `claim_id/topic/statement/confidence/status/evidence_ids`，`supported`/`contested` Claim 至少有真实可用 Evidence；无 Evidence 的 Claim 只能是 `unresolved`；
- `evidence` 的 `paper_id`、`claim_id`、`evidence_level`、`stance`、`status` 和 locator 必须逐项通过既有矩阵服务；自然语言主链只允许 `catalog`/`abstract`，不允许模型声称 `fulltext`；
- `cells` 必须引用已声明 Claim、Paper、Dimension 和 Evidence。允许既有 `build_matrix()` 只为未提供组合生成显式 `missing` cell，但不能把缺失 cell 变成支持性事实。

### Context 的真实来源与 snapshot 阻塞

当前代码已有可复用但尚未接到 synthesizer 的 server-owned 字段：

1. `ResearchPaperSelection.source_search_id` 是每个候选来源搜索快照的 opaque handle；旧 selection 可能为 `NULL`。任务级 `ResearchTask.search_id` 只是首个搜索句柄，不能无条件代替每个候选的来源。
2. `PaperDiscoveryStore.get_search_results(source_search_id)` 返回冻结 `SearchResult.snapshot`，其中含 `candidate_id/catalog_paper_id`、`search_id`、实际 `title`、实际 `abstract`、keywords 和 rank；它才是 producer 的标题/摘要事实来源。不得用 `_catalog_metadata_resolver()` 的全局目录行替代该候选快照来证明 Evidence。
3. 当前 `_catalog_evidence_view()` 只传 candidate IDs、`catalog:<id>` refs 和受限 metadata，丢掉了 `search_id`；因此现状确实缺 `catalog_snapshot_id`。旧行若没有 `source_search_id`，只有在任务级 handle 的冻结结果明确包含该 candidate 且 search job 未过期时，才可安全回退；否则该候选只允许保留 artifact metadata，不能进入可引用 Matrix Evidence。
4. 对每个候选，Orchestrator 应从冻结 snapshot 构造内部 context：`paper_id`、snapshot 的 title、snapshot 的 abstract（有界展示）、`catalog_snapshot_id=source_search_id`，以及服务端计算的 `abstract_digest=sha256(原始 snapshot abstract UTF-8)`。context 不含 URL、PDF、document/chunk 或未验证的模型文本。

真正可追溯的 locator 约束应在 `build_matrix()` 之前额外执行：

- `catalog_snapshot_id` 必须等于该 `paper_id` 的 server-selected search handle，并且 `get_search_results(handle)` 中存在同一 candidate；
- `abstract` Evidence 必须有非空 snapshot abstract，`abstract_digest` 必须等于服务端 digest，`abstract_ref` 必须只指向该 candidate 的既有 catalog/abstract ref；
- `catalog` Evidence 只能作为 contextual/background 证据，不能把标题级事实升级为方法或结果支持/反驳；
- `fulltext` Evidence 一律拒绝，除非未来显式 recovery 路径提供并验证现有 `EvidenceUpgrade` provenance；本 producer 不猜 document/chunk/page/hash。

若任一候选缺真实 snapshot handle、snapshot membership、实际 abstract 或 digest，parser 应拒绝该 Evidence/Claim；若没有任何仍可验证的 supported Claim，则整个矩阵 payload 不提交，沿既有 `MATRIX_NOT_READY`/降级语义结束。不能用空 locator、`catalog:<id>` 字符串或全局目录 metadata 冒充 snapshot。

### Dimensions 的最小来源

当前已批准 `ResearchPlan.facets_json` 是已有计划版本内的稳定服务器事实，而 `ResearchSessionPlan.report_structure_json.sections` 不是比较维度。最小实现建议只把当前 plan 的 facets 映射成 server-provided dimensions（稳定的 `facet-<order>` ID、原 facet label、受界定的计划定义），并在 prompt 中要求模型原样复制；parser 拒绝模型新增/改写 dimension。若架构师不认可“已批准 facets = comparison dimensions”的语义，则当前仍缺少合法 Dimension producer，必须先扩展 plan 内部合同再实现，不能让模型自行发明维度。

### 调用顺序、版本与失败语义

1. Orchestrator 对真实 synthesizer 输出拆分并校验候选 envelope 与可选 `evidence_matrix`；先不触碰旧 artifact。
2. 有合法矩阵 payload 时调用 `EvidenceMatrixService.build_matrix(task_id, owner_id, plan_version=..., dimensions=..., claims=..., evidence=..., cells=...)`。其事务前置校验失败时不写任何矩阵行。
3. 复用现有候选级 `ReportDeliveryService.deliver()` 生成 plan-version artifact；`SynthesisResult.evidence_matrix` 不参与 artifact 内容，真实 `synthesis_run_id` 继续作为 artifact provenance。
4. 在 artifact 已占用旧版本后调用 `ReportGenerationService.generate(task_id, owner_id, plan_version=..., report_version=None)`。省略 report version，强制复用 `next_report_version()`；因此已有 artifact v1 后 canonical `ResearchReport` 应为 v2，旧 artifact/hash 和旧 `ResearchReport` 均不覆盖。
5. 矩阵或 canonical report 任一步失败时，保留已有候选 artifact，绝不从失败结果写半份 `ResearchReport`，也不伪造 AgentRun。缺失/非法 extension 不得静默回退成 Matrix；现有候选级向后兼容路径仍可返回 artifact-backed 报告，但 versioned `/reports/{version}` 继续 `REPORT_NOT_READY`，直到合法 matrix 存在。

### 实施前必须固定的定向测试

`test_research_report_matrix_bridge.py` 至少覆盖：

1. 无 `evidence_matrix` 的旧 synthesizer output：artifact 合同仍通过，matrix/report 不凭空产生；
2. 五个 allowlisted candidates + 每条真实 `source_search_id` snapshot：合法 abstract Evidence 通过，`build_matrix()` 后生成 canonical v2，artifact v1 hash 不变；
3. unallowlisted paper、错误 snapshot handle、snapshot 中不存在 candidate、错误 abstract digest、catalog supports/contradicts、fulltext 无 EvidenceUpgrade、dimension drift、Claim 无支持 Evidence：均 fail closed，且失败前无矩阵写入；
4. 旧 candidate-level `ReportSynthesisOutput` 仍无 `evidence_matrix` 字段，`SynthesisResult.evidence_matrix` 默认 `None`；新增内部字段不改变 artifact payload/hash；
5. `ReportGenerationService.generate(report_version=None)` 的调用顺序和版本断言：已有 artifact v1 时只允许新 canonical v2，不允许复用/覆盖 v1，不创建新 AgentRun。

本设计状态：`DESIGN_READY / IMPLEMENTATION_PENDING_ROOT_CONFIRMATION`；P1 只有在真实 producer、snapshot locator、allowlist、matrix→report 定向集成测试全部通过后才能关闭。

## 实施记录（架构师确认后）

架构师已确认上述最小设计并授权实施。本轮已完成真实 backend producer 接缝，未改公开 API/request schema、数据库表、AgentRun 状态机、候选 artifact 内容或第二套报告路径。

### 实际改动

1. `agent_runtime.py` 保留 synthesizer 原有必填四字段，只在 `matrix_context` 存在时提示可选的内部 `evidence_matrix`；没有 context 时模型不会获得矩阵授权。
2. `orchestrator.py` 从当前已批准计划的 `facets_json` 生成稳定 `facet-<order>` comparison dimensions，definition 固定为“已批准研究范围维度：<facet>”。缺 facet、计划不完整或候选没有可验证快照时不提供 context，模型不能自行发明 dimension。
3. context 对每个候选优先使用 `ResearchPaperSelection.source_search_id`，旧 NULL 行仅在任务级 search id 的冻结 `SearchJob` 未过期且 `get_search_results(search_id)` 明确包含该 candidate 时回退；不调用全局 catalog 行替代 snapshot。context 仅携带真实 title/abstract、snapshot handle 和服务端 SHA-256 abstract digest，不带 URL/PDF/fulltext。
4. 可选矩阵在候选 artifact 校验前拆出：严格校验 schema、plan version、facet dimensions、allowlist、snapshot locator/digest、Claim/Evidence/Cell 归属；只接受 `catalog`/`abstract`，catalog 只能 contextual，fulltext、catalog supports/contradicts、错误 digest、越界 paper 或 dimension drift 均 fail closed。缺失/非法扩展只记录 warning 并沿旧候选 artifact 路径降级。
5. 合法 payload 先调用现有 `EvidenceMatrixService.build_matrix()`，再复用现有 `ReportDeliveryService.deliver()` 写候选级 artifact，最后调用现有 `ReportGenerationService.generate(report_version=None)` 生成下一个 immutable `ResearchReport` 版本；`SynthesisResult.evidence_matrix` 是默认 `None` 的内部字段，未进入 `ReportSynthesisOutput`、markdown/html/citation manifest 或 artifact envelope。旧 artifact 不改。

### 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py` | 0 | `8 passed`；覆盖 allowlist、facet dimension、fulltext/catalog stance、digest、内部字段隔离及既有 build_matrix 复用 |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py tests/research/test_evidence_matrix.py tests/research/test_report_generation.py tests/research/test_report_synthesis_contract.py tests/research/test_agent_runtime_contract.py::test_fake_output_is_structured_and_checkpointed tests/research/test_research_agent_approval_contract.py::test_ollama_adapter_synthesizer_requires_bounded_delivery_shape tests/research/test_agent_selection_persistence.py tests/research/test_agent_work_item_failure_visibility.py` | 0 | `61 passed` |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_report_catalog_metadata.py tests/research/test_research_runtime_contract.py tests/research/test_search_id_bridge.py` | 0 | `79 passed` |
| `.venv/bin/ruff check backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py backend/app/research/application/report_synthesis.py tests/research/test_research_report_matrix_bridge.py` | 0 | `All checks passed` |
| `git diff --check -- backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py backend/app/research/application/report_synthesis.py tests/research/test_research_report_matrix_bridge.py` | 0 | 无 whitespace/error marker |

未运行全量回归、未启动服务、未部署、未写生产数据。新增实现待独立 backend review；在该 review 和 Spec032 收口门禁完成前，不宣称可部署。

当前状态：`IMPLEMENTED / REVIEW_PENDING`；P0=0。实现层 P1 已按 fail-closed 语义覆盖，但真实环境仍需用有效 frozen snapshot、已批准 facets 和真实 producer 输出完成 API/E2E 验证，才能关闭 Spec032 的最终部署门禁。

## 独立复审 BLOCKED_P1 后的最小修复（2026-10-09）

独立 backend review 发现候选 envelope 校验顺序、矩阵跨表原子性、错误终态、原始摘要 digest 与 producer/parser 数量上限仍有缺口。本轮按已确认 Spec030/032 范围修复，未改公开 API/request schema、数据库表、AgentRun 状态机或其他 agent 文件。

### 修复内容

1. `orchestrator.py` 现在先执行现有 `validate_report_synthesis_output()` 与 `consume_validated_output()` 的候选级纯内存校验，再允许 `EvidenceMatrixService.build_matrix()` 写入；因此候选 envelope 失败不会先留下矩阵行。
2. `ResearchStore.persist_evidence_matrix()` 复用既有四张矩阵 projection 表，在单个 `BEGIN IMMEDIATE` 事务中写入 Claim、Evidence、Dimension、Cell；`EvidenceMatrixService` 不再对真实 store 回退到四个独立写事务。故障注入覆盖了首轮写入后抛错，四类列表均保持为空。
3. 矩阵缺失/非法、矩阵 build 失败统一写入稳定 `MATRIX_NOT_READY`；Canonical `ReportGenerationService.generate(report_version=None)` 失败写入 `REPORT_NOT_READY`。候选 artifact 仍可作为降级产物保留，但任务终态为 `partial`，不会以 `completed` 冒充已有 canonical `ResearchReport`，并沿现有失败/partial notification 语义记录原因。
4. context 与 validator 均以 frozen snapshot abstract 的原始 UTF-8 内容计算 SHA-256，不在 digest 前 `strip()`；新增 whitespace fixture 锁定该合同。
5. producer prompt 与 parser 统一 matrix `claims`/`evidence`/`cells` 每项最多 64，和 runtime `validate_safe_scope()` 的列表上限一致；65 项 fixture 明确拒绝。
6. context 构造增加 durable `ResearchPaperSelection` ID 与 evaluator allowlist 的集合一致性门禁，避免矩阵自动补全出 context 外的 Paper cell。

### 先红灯后修复

| 故障注入 | 修复前退出码/现象 | 修复后断言 |
|---|---:|---|
| store 在第一轮矩阵写入后抛错 | 1：`ResearchStore` 尚无原子写入 seam | Claim/Evidence/Dimension/Cell 全部回滚，测试通过 |
| `EvidenceMatrixService.build_matrix()` 抛错 | 1：任务错误收口为 `completed` | 任务 `partial`，`error_code=MATRIX_NOT_READY`，无 `ResearchReport` |
| `ReportGenerationService.generate()` 抛错 | 修复前未覆盖 | 任务 `partial`，`error_code=REPORT_NOT_READY`，候选 artifact 可保留但无新 `ResearchReport` |

### 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py::test_matrix_rows_roll_back_as_one_unit_when_store_write_fails tests/research/test_research_report_matrix_bridge.py::test_matrix_build_failure_cannot_close_agent_task_as_completed tests/research/test_research_report_matrix_bridge.py::test_canonical_report_generation_failure_cannot_close_agent_task_as_completed` | 0 | `3 passed`；矩阵写入、矩阵 build、canonical generation 故障注入均先红后绿 |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py` | 0 | `13 passed` |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py tests/research/test_evidence_matrix.py tests/research/test_report_generation.py tests/research/test_report_synthesis_contract.py tests/research/test_agent_selection_persistence.py` | 0 | `62 passed` |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_report_catalog_metadata.py tests/research/test_research_runtime_contract.py tests/research/test_search_id_bridge.py` | 0 | `79 passed` |
| `.venv/bin/ruff check backend/app/research/application/agent_runtime.py backend/app/research/application/evidence_matrix.py backend/app/research/application/orchestrator.py backend/app/research/infrastructure/research_store.py tests/research/test_research_report_matrix_bridge.py` | 0 | `All checks passed` |
| `git diff --check -- backend/app/research/application/agent_runtime.py backend/app/research/application/evidence_matrix.py backend/app/research/application/orchestrator.py backend/app/research/infrastructure/research_store.py tests/research/test_research_report_matrix_bridge.py` | 0 | 通过 |

本轮未运行全量回归、未启动/部署服务、未写生产数据。状态保持 `IMPLEMENTED / REVIEW_PENDING`；P0=0，待独立 backend reviewer 复审后再判断是否可部署。

## 残余 P1：Canonical Report 失败不得先发 completed（2026-10-09）

独立复审进一步发现：矩阵成功后原实现先调用 `ReportDeliveryService.deliver(notification_kind="completed")`，再调用 `ReportGenerationService.generate(report_version=None)`。Canonical 生成失败虽会把任务改为 `partial`，但此前已创建 completed artifact/activity/notification。本轮只在既有应用服务接缝内修复，未新增 schema/API/表/状态机/AgentRun。

### 先红灯后修复

先为真实 Orchestrator 故障注入补充断言：`ReportGenerationService.generate()` 抛错时，要求无 `ResearchReport`、任务与 terminal 为 `partial/REPORT_NOT_READY`、所有通知不得为 `completed`、activity message 不得为 `completed`。修复前该测试失败于已有 `completed` notification，随后才实施排序调整。

### 最小修复

1. 合法矩阵写入后先调用既有 `ReportGenerationService.generate(report_version=None)`；只有该调用成功，才允许候选 delivery 使用 `completed` 语义。
2. Canonical 失败仍保留真实 AgentRun 绑定的候选 artifact，但 delivery 使用 `partial` notification；`ReportDeliveryService` 将该状态同步到 activity message，避免先写 completed message。任何后续 delivery 异常也沿 partial/failure 语义，不清除错误。
3. 未硬编码 canonical 版本：无既有 artifact 时 `next_report_version()` 产生 v1；已有 artifact v1 时产生 v2。两种场景均验证旧 artifact 不覆盖、真实 AgentRun 约束不绕过。

### 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py::test_canonical_report_generation_failure_cannot_close_agent_task_as_completed` | 0 | 修复后通过；无 completed notification/activity，task/terminal 为 partial |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py::test_canonical_generation_uses_first_available_version_without_artifact tests/research/test_research_report_matrix_bridge.py::test_canonical_generation_uses_next_available_version_after_existing_artifact` | 0 | `2 passed`；版本按 `next_report_version()` 动态分配 |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py` | 0 | `15 passed` |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py tests/research/test_evidence_matrix.py tests/research/test_report_generation.py tests/research/test_report_synthesis_contract.py tests/research/test_agent_selection_persistence.py` | 0 | `64 passed` |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_report_catalog_metadata.py tests/research/test_research_runtime_contract.py tests/research/test_search_id_bridge.py` | 0 | `79 passed` |
| `.venv/bin/ruff check backend/app/research/application/agent_runtime.py backend/app/research/application/evidence_matrix.py backend/app/research/application/orchestrator.py backend/app/research/application/report_generation.py backend/app/research/application/report_synthesis.py backend/app/research/infrastructure/research_store.py tests/research/test_research_report_matrix_bridge.py` | 0 | `All checks passed` |
| `git diff --check --`（上述相关路径） | 0 | 通过 |

本轮未部署、未运行全量回归、未写生产数据；状态保持 `IMPLEMENTED / REVIEW_PENDING`，P0=0，等待独立 backend reviewer 复审。
