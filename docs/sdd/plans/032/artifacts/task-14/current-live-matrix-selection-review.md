# Spec032 Task14：live matrix / selection-count 独立后端复审

## 复审结论

**结论：BLOCKED（P0=0，P1=1）**。本复审没有修改业务代码、测试、配置或部署；结论基于当前工作树的实际 diff、定向测试、只读语义探针，以及真实四篇候选 E2E 证据。`current-live-matrix-fix.md` 的 lazy store 接线和快照边界通过复审，但尚未在新部署上重跑；`current-selection-count-fix.md` 仍有一个会影响全局预算合同的 P1。

P1 是：新的 agent/runtime 选择路径没有把最终候选数统一夹到既有 `BUDGET_CAPS["max_selected"] == 20`。Planner 现在按每个 facet 请求完整目标数，最多三路，因此目标为 20 时最多可形成 60 个 union 候选；当前 evaluator、floor promotion、持久化选集、matrix context 和 terminal `selected_count` 之间没有共同的 20 上限。仅自动导入桥按目标数切片，不能替代最终选集预算门禁。

## 复审范围与证据

读取并逐项对照：

- `docs/sdd/plans/032/artifacts/task-14/current-live-matrix-fix.md`
- `docs/sdd/plans/032/artifacts/task-14/current-selection-count-fix.md`
- `docs/sdd/plans/032/artifacts/task-14/current-research-e2e-matrix-report.md`
- `docs/sdd/plans/032/artifacts/task-14/current-research-e2e-matrix-evidence.json`
- 实际 diff：`backend/app/research/application/orchestrator.py`、`backend/app/research/application/planner.py`、`tests/research/test_report_catalog_metadata.py`、`tests/research/test_research_report_matrix_bridge.py`、`tests/research/test_selection_budget_convergence.py`
- 既有预算与合同：`backend/app/research/domain/contracts.py`、`backend/app/research/domain/plan_validator.py`、`backend/app/research/application/search_catalog_adapter.py`、`backend/app/research/application/acquisition.py`

真实 E2E 证据为同一新 run：代码 `68315ba`，task `e1591ee5833954e7a6e98221ff60cc01`，session `3b74b17ca3b949f8919cab5db62e5f45`。自然语言计划的 `min=max=target=5` 已通过，但实际终态为 `partial`、`MATRIX_NOT_READY`、`selected_count=4`；四个 acquisition item 均完成。该证据没有被本复审冒充为成功，也没有重跑旧 batch。

## P0/P1 判定

| 编号 | 判定 | 证据与影响 |
|---|---|---|
| P0 | 无 | 未发现新的越权来源、快照绕过、伪造 candidate ID、下载扩大或公开 schema 变更。矩阵上下文仍以 Search Worker 冻结 snapshot 为唯一证据。 |
| P1-SEL-001 | 未修复 | agent 路径的最终候选集合可超过 `max_selected=20`；持久化 selections、matrix allowlist、报告候选集和 terminal `selected_count` 可能与既有全局预算合同不一致。 |

## 1. live matrix lazy-store 修复：通过（待 live rerun）

实际 diff 在 `Orchestrator._build_synthesis_matrix_context` 中仅增加了以下已有 provider 的 lazy fallback：当 `self._adapter._store` 为空时，在 `suppress(Exception)` 内导入并调用 `backend.app.api.common._paper_store()`。这复用了 `_catalog_metadata_resolver()` 使用的同一个配置目录 provider，没有创建第二个 cache/catalog，也没有从全局 catalog 行直接构造证据。

快照安全边界仍完整保留：

- selection 必须与 `validated_candidates` 的 candidate ID 集完全相等；
- 每个 selection 使用其 `source_search_id`，旧数据才回退到任务级句柄；
- search job 必须是 `completed`/`partial` 且未过期；
- result 必须同时匹配 `search_id` 与 candidate ID，并含 server snapshot；
- snapshot 的 candidate ID、非空 title、abstract 类型/长度和精确 SHA-256 digest 继续校验；
- 仍有候选数上限（matrix context 的 64）和 fail-closed 的不可用 provider 行为。

新增的 `test_live_snapshot_context_resolves_shared_store_when_adapter_is_unbound` 建立了两个真实 Search snapshot，使用未绑定的 `CatalogSearchAdapter`，验证 provider fallback、来源 search ID 与 abstract digest；该测试通过。未发现 URL、网络抓取、SSRF、schema 或下载安全边界被放宽。当前缺少 provider 抛异常/返回不完整对象的专门回归，但现有 `suppress` + callable 检查会返回 `None`，不足以构成 P1。

## 2. selection-count 修复：P1 未闭合

### 已确认正确的部分

`Planner._build_work_items` 将每个 bounded facet 的 `max_results` 改为全局 `target_paper_count`，保留 2–3 路 fan-out。对本轮目标 5，这修复了每路 3 导致 union 只有 4 的真实失败形状；新增 planner 回归断言两个 facet 都请求 5。

`_promote_catalog_floor` 现在对“已有保留项 + 同一 Search Worker recall pool”做完整 evaluator floor，而不是只把最后一个缺口交给 evaluator；新增 4+1 和 recall pool 只有 4 的测试均通过。其输入仍只来自 recall allowlist，不能凭空扩大到本地目录中未被 Search Worker 返回的 ID。

### P1 复现与代码路径

既有合同明确规定：

```text
BUDGET_CAPS["max_selected"] == 20
```

但以下 agent/runtime 路径没有应用该 cap：

1. `PaperEvaluator.evaluate()` 对所有达到阈值的 rows 全部返回 `kept`；其 5-row minimum floor 也不做 max cap。
2. `_validated_evaluator_candidates()` 将 evaluator 的 kept rows 全量归一化。
3. `_promote_catalog_floor()` 只保证最小 5 篇，不限制最大篇数。
4. `_run_agent_work_items` 将该完整 `validated` 写入 synthesizer input，并在终态以 `len(validated_candidates)` 写 `selected_count`。
5. `_persist_agent_selections()` 只做 `allowed_candidates` 白名单和去重，不做 `max_selected` 截断；因此 durable `research_paper_selections` 也可能超过 20。
6. `_build_synthesis_matrix_context()` 要求 durable selection 集与 validated 集相等，所以会把超量集合继续带入 matrix allowlist，而不是替它执行全局上限。

只读语义探针构造 25 个均可保留的 recall rows，实际输出为：

```text
evaluator_kept 25 validated 25 promoted_result 25 global_max 20
```

这不是“搜索结果超过 20”本身的问题，而是最终选集和 terminal budget 字段没有执行合同上限。作为对照，旧的确定性 `_evaluate_papers()` 仍使用 `min(max(target, 5), BUDGET_CAPS["max_selected"])`，说明 agent path 与既有 deterministic path 的预算语义已分叉。

`ApprovedPlanAutoImporter.run()` 的 `selections[:target_paper_count]` 只限制自动导入副作用；它不会修正已落库 selections、matrix candidate set、报告输入或 `selected_count`，不能作为 P1 的闭合证据。

### 最小修复建议（交 backend-dev，不在本复审实施）

复用现有 `BUDGET_CAPS` 和已有稳定排序/候选顺序，在 agent path 的“validated + floor 完成”之后、同时用于以下所有消费者之前，集中形成一个不超过
`min(max(target_paper_count, _MIN_REPORT_CANDIDATES), BUDGET_CAPS["max_selected"])`（或项目既有等价合同）的 bounded list：

- `_persist_agent_selections`；
- synthesizer `validated_candidates` / citation allowlist；
- `_build_synthesis_matrix_context`；
- terminal `selected_count`；
- acquisition 读取的 durable selections。

保留 recall allowlist、per-selection snapshot 和现有 floor；不得通过放宽来源或重新查询补足。至少新增一个 >20 个全相关 recall 的 regression，断言持久化选集、synthesizer 输入/矩阵上下文和终态 count 都不超过 20；同时保留本轮 4→5 overlap floor 回归。

### “不得 promote 被拒不相关候选”边界

白名单安全复审通过：`_validated_evaluator_candidates`、`_promote_catalog_floor` 和 `_persist_agent_selections` 都只接受 Search Worker recall ID；未在 recall 中的模型自造 ID 即使本地 resolver 能查到也不会进入选集。该 fix 没有扩大来源或把 artifact metadata 当作 fulltext。

但现有 `PaperEvaluator` 合同明确允许在 recall pool 至少 5 行时，用稳定排名保留低于 relevance threshold 的 catalog 行，原因标记为 `retained to satisfy minimum report candidate floor`；既有测试和新增 4+1 测试都依赖此语义。因此本复审没有把“recall 内的 floor retention”错误判成来源越权。若验收语义中的“被拒”特指 evaluator 已明确 `candidate_id` + `keep=false` 的逐条拒绝，则当前 floor helper 没有携带显式拒绝集合，backend-dev 在补 max cap 时必须保留 `_persist_agent_selections` 对显式逐条拒绝与批量容器 `keep=false` 的区分，并补一条回归；本报告将其列为边界核对项，不另造第二套筛选系统。

## 定向验证

以下均使用项目 `.venv`，未运行全量回归、未启动/重启服务：

1. `.venv/bin/python -m pytest tests/research/test_selection_budget_convergence.py tests/research/test_report_catalog_metadata.py tests/research/test_catalog_search_worker_contract.py -q`：退出码 0，24 passed。
2. `.venv/bin/python -m pytest tests/research/test_research_report_matrix_bridge.py tests/research/test_report_catalog_metadata.py tests/research/test_selection_budget_convergence.py tests/research/test_catalog_search_worker_contract.py tests/research/test_agent_selection_persistence.py tests/research/test_validated_evaluator_candidates.py tests/research/test_report_synthesis_contract.py -q`：退出码 0，83 passed。
3. `.venv/bin/python -m pytest tests/research/test_research_backend_slice.py -q`：退出码 0，57 passed、5 subtests passed。
4. `.venv/bin/ruff check backend/app/research/application/orchestrator.py backend/app/research/application/planner.py tests/research/test_report_catalog_metadata.py tests/research/test_research_report_matrix_bridge.py tests/research/test_selection_budget_convergence.py`，再对相同 Python 文件执行 `py_compile`：退出码 0，`All checks passed!`。
5. 只读语义预算探针：退出码 0，复现 25 → 25，未修改数据库或服务状态。

## 复审收口

- P0：0。
- P1：1（`P1-SEL-001`，agent/runtime 最终选集未统一执行 `max_selected=20`）。
- live matrix lazy-store fallback：代码与定向回归通过，等待独立 review 后部署并重跑真实 E2E；本报告不把当前 4 篇 `MATRIX_NOT_READY` 运行改写为成功。
- 当前不能签字为 Spec032 全 E2E 通过，也不能交付 `READY_FOR_USER`。修复后应在新部署、新 run 中重新确认：selection count、非空 matrix、canonical ResearchReport 版本化读取及下载路径。

## 最终复审：上次 P1 修复核验（2026-10-09）

### P1-SEL-001：全局选择上限已闭合

最新实际 diff 新增 `_agent_selection_limit()` 与 `_bound_agent_selection()`，只复用既有
`BUDGET_CAPS["max_selected"]` 和 `_MIN_REPORT_CANDIDATES`，对 candidate ID 稳定去重后取稳定前缀。复审确认：

- 25 个合法 recall/evaluator candidates 在 target=20 时得到 20 个唯一 ID；
- approved target=5 时得到 5 个唯一 ID；
- `_persist_agent_selections` 在 `replace_selections` 前使用同一 limit；
- synthesizer `validated_candidates`、citation allowlist、matrix context 输入和 terminal `selected_count` 使用同一 bounded list；
- `source_search_id` 仍在构造 `ResearchPaperSelection` 时按 `candidate_sources` 绑定，截断只裁掉候选行，不覆盖来源句柄；5 个候选的交替 `search-0/search-1` 绑定探针保持不变；
- 没有修改 `PaperEvaluator` 的阈值、soft floor 或全局 threshold；没有新增搜索、下载、schema 或公开字段。

新增的共享集合测试通过，且独立只读探针输出 `target5=5 target20=20 stable_unique=20`。因此原复审的
`P1-SEL-001` 判定为 **PASS/CLOSED**。

### 新发现 P1-SEL-002：目标/最小篇数不足仍可能被标记 completed

最新 fix 报告声称“合法候选不足 5 篇时保持真实 partial”，但最终 agent/runtime 状态机没有把这个约束落实到完成门禁。`_bound_agent_selection` 在只有 4（甚至 1）个合法 recall 时会诚实返回 4（或 1），但 `_run_agent_work_items` 收尾处仍使用：

```python
final_status = "completed" if items and failures == 0 else "partial"
```

该条件只看 WorkItem/报告错误，没有比较 `selected_count` 与 approved `task.target_paper_count`，也没有以已有 partial/degraded 路径记录“目标未满足”。只读语义探针把现有 matrix-agent fixture 的 task target 从 1 替换为 5、保留唯一合法 candidate 并提供有效 matrix payload，结果为：

```text
target=5 selected=1 status=completed error=None
```

这证明即使 matrix/canonical producer 成功，1/5 仍可能作为 `completed` 返回；因此“min 不足诚实 partial”尚未闭合。该探针只使用临时目录和测试 fixture，没有写入项目数据库或服务。

最小后端建议交 backend-dev：在最终完成判定前复用既有 target/min 约束，将 `selected_count < approved target/min` 的任务保留实际 count，并沿既有 partial/limitations/failure 记录路径结束；不要补造 candidate，不要把目标参数当证据，不要为此新增第二套预算系统。若需要稳定错误码，应先复用项目已有契约或另行走 schema/接口评审，不能在本复审擅加字段。补一条 target=5、合法 recall 仅 4、matrix payload 有效的回归，断言 `status=partial` 且 `selected_count=4`。

### lazy matrix store 回退复查

最新 diff 未回退 lazy fallback：`_build_synthesis_matrix_context` 仍只在 adapter `_store` 未绑定时复用既有
`_paper_store()`，之后继续走 per-selection `source_search_id`、job status/expiry、result membership、snapshot title/abstract/digest 和 allowlist equality 校验。matrix bridge 新测试及相关 77-test 定向集均通过；未见安全边界放宽。

### 最终复审结论

- P0：0。
- 上次 P1-SEL-001：**已修复并通过复审**（25→20、target5→5、稳定去重、消费者共享最终集合）。
- 新 P1-SEL-002：**仍阻塞**（目标/最小篇数不足时无条件完成门禁）。
- 当前总 verdict：**BLOCKED**。不能把旧的四篇 `MATRIX_NOT_READY` E2E 改写为成功；也不能在新部署前签字为 Spec032 全 E2E 通过。

### 本轮最终验证

以下均使用项目 `.venv`，未部署、未重启服务、未运行全量回归：

1. `.venv/bin/python -m pytest tests/research/test_agent_selection_persistence.py tests/research/test_validated_evaluator_candidates.py tests/research/test_report_synthesis_contract.py tests/research/test_selection_budget_convergence.py tests/research/test_report_catalog_metadata.py tests/research/test_catalog_search_worker_contract.py -q`：退出码 0，69 passed。
2. `.venv/bin/python -m pytest tests/research/test_research_backend_slice.py tests/research/test_research_report_matrix_bridge.py tests/research/test_search_id_bridge.py -q`：退出码 0，77 passed、5 subtests passed。
3. `.venv/bin/ruff check backend/app/research/application/orchestrator.py backend/app/research/application/planner.py tests/research/test_agent_selection_persistence.py tests/research/test_report_catalog_metadata.py tests/research/test_research_report_matrix_bridge.py tests/research/test_selection_budget_convergence.py`：退出码 0，`All checks passed!`。
4. 对上述 Python 文件执行 `.venv/bin/python -m py_compile`：退出码 0；`.venv/bin/python scripts/check_test_layout.py`：退出码 0，`test layout: ok`。
5. 只读预算探针：target5=5、target20=20、stable_unique=20；只读 source_search_id 探针保留 5 个候选的原始 search handle。

## 最终复审：P1-SEL-002 修复（2026-10-09）

### 结论

**P1-SEL-002 已通过独立复审（P0=0、P1=0）。** 最新修复把“approved minimum”与软 target 分开：只从已批准 session plan 的 `scope_json.constraints` 解析显式 `min_paper_count`，不把 `target_paper_count` 擅自升级为 minimum；短缺时保留真实选择数并使用既有 `EVIDENCE_INSUFFICIENT`，不制造候选、不降低 threshold、不改变 matrix allowlist。

本结论只表示当前代码与定向测试的复审通过。最新修复尚未部署，也未重跑真实 API；因此 Spec032 的 live E2E 仍是 `LIVE_RERUN_PENDING`，不能签字为最终用户验收通过。

### 有效 matrix 四边界

独立运行 `test_approved_minimum_controls_agent_completion_and_surface_reason` 的四个参数化案例均通过：

| approved min | target | 合法 selected | 结果 | error |
|---:|---:|---:|---|---|
| 5 | 5 | 1 | `partial` | `EVIDENCE_INSUFFICIENT` |
| 5 | 5 | 4 | `partial` | `EVIDENCE_INSUFFICIENT` |
| 1 | 5 | 4 | `completed` | 无 |
| 5 | 5 | 5 | `completed` | 无 |

短缺 reason 保持同一安全字符串：`approved minimum paper count not met: selected N of M`。测试逐项核对了 task 状态、terminal `status/selected_count/error_code/reason`、activity 状态和正文、Markdown candidate artifact、canonical `ResearchReport.limitations_json`，以及 partial/failed 或 completed notification 的 reason/类型；代码路径还使 HTML artifact 从同一带 limitation 的 Markdown 派生。有效 matrix 下 min=1,target=5,selected=4 不触发短缺，证明 target 没有被错误当作硬 minimum。

### 真实 diff 与边界核对

- `Orchestrator` 在最终 validated selection 之后计算短缺；`ReportDeliveryService`、`ReportGenerationService` 和 failure notification 都复用同一 reason。
- candidate artifact 的 `safe_summary.limitations` 重新计算 `output_hash`，canonical report 通过 `additional_limitations` 写入同一 limitation；未添加公开字段、表或第二套报告链。
- `EVIDENCE_INSUFFICIENT` 沿现有矩阵错误语义使用；短缺仍执行自动导入的已有路径，但不补足伪候选，`selected_count` 保持真实值。
- 上次 P1-SEL-001 的 25→20、target5→5、稳定去重和 `source_search_id` 绑定未回退；lazy matrix `_paper_store()` fallback 仍在 snapshot membership/status/expiry/title/abstract/digest/allowlist 校验之前提供同一 store，不读取全局行替代 snapshot。
- 未发现 `PaperEvaluator` threshold/soft_floor 或全局 threshold 改动，也未发现下载、搜索、schema、来源安全放宽。

### 本轮验证

全部使用项目 `.venv`，未部署、未重启服务、未写生产数据、未运行全量回归：

1. `.venv/bin/python -m pytest tests/research/test_research_report_matrix_bridge.py::test_approved_minimum_controls_agent_completion_and_surface_reason -q`：退出码 0，4 passed。
2. `.venv/bin/python -m pytest tests/research/test_agent_selection_persistence.py tests/research/test_validated_evaluator_candidates.py tests/research/test_report_synthesis_contract.py tests/research/test_research_report_matrix_bridge.py tests/research/test_report_generation.py tests/research/test_selection_budget_convergence.py tests/research/test_report_catalog_metadata.py tests/research/test_catalog_search_worker_contract.py tests/research/test_search_id_bridge.py -q`：退出码 0，103 passed。
3. `.venv/bin/python -m pytest tests/research/test_research_backend_slice.py -q`：退出码 0，57 passed、5 subtests passed。
4. 相关 orchestrator/planner/report generation/report synthesis 与研究测试执行 `.venv/bin/ruff check`：退出码 0，`All checks passed!`；执行 `.venv/bin/python -m py_compile`：退出码 0；`scripts/check_test_layout.py`：退出码 0，`test layout: ok`。
5. 只读预算探针仍输出 `target5=5 target20=20 stable_unique=20`；source snapshot handle 探针保留原始交替 `source_search_id`。

### 最终复审状态

- P0：0。
- P1-SEL-001：已关闭。
- P1-SEL-002：已关闭。
- 代码复审 verdict：**PASS**。
- 运行时验收 verdict：**LIVE_RERUN_PENDING**；必须由主 agent 在包含全部修复的新部署上新建 run，真实确认 approved constraints、selection count、matrix、canonical report、artifact 与旧/新版本读取，不能用本地 fixture 替代。
