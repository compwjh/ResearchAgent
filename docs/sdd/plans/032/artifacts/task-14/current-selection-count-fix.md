# Spec032 Task14：候选数量收敛修复报告

## 结论

**已完成最小后端修复，未重新部署或重试生产任务。** 修复覆盖两处同范围缺陷：

1. 既有 `Planner` 将目标数量按 facet 拆分给每个 Search Worker；候选有重叠时，单次检索即使各返回 3 篇，合并也可能只有 4 篇。
2. 既有 `_promote_catalog_floor` 只把“尚未入选的剩余行”交给 `PaperEvaluator`，当已验证 4 篇、召回池还剩 1 篇时，评估器看见的是 1 行，无法触发它已有的 5 行最小报告 floor。

修复仍复用原有 fan-out、`PaperEvaluator`、Search Worker 召回白名单和 catalog metadata 回填；没有降低阈值、增加公开字段、创建新 search chain、下载论文或改变数据模型。

## 真实失败证据

来源：

- [`current-research-e2e-matrix-report.md`](./current-research-e2e-matrix-report.md)
- [`current-research-e2e-matrix-evidence.json`](./current-research-e2e-matrix-evidence.json)
- 本地只读查询 `data/research/research.sqlite3` 的 `research_work_items`（未输出任何环境变量、密钥或 Cookie）。

真实任务为 `e1591ee5833954e7a6e98221ff60cc01`，计划 `min=max=target=5`。旧计划实际写入：

- `s1.max_results=3`，候选为 `ef9e0846844e5b02834163586ea6ddc9`、`9793a4a35caad52ee99f926ae7c90810`、`4e6322a23b92a271dbec9906c51fe0ab`；
- `s2.max_results=3`，候选为 `ef9e0846844e5b02834163586ea6ddc9`、`9793a4a35caad52ee99f926ae7c90810`、`57e0402f82fe2ce354bea423b201fde3`；
- 两个 Search Worker 的真实召回白名单并集只有 4 个 ID。

Evaluator 的真实聚合输出也只保留上述 4 个 `catalog:<id>` 引用。任务终态为 `partial`、`selected_count=4`、`error_code=MATRIX_NOT_READY`；4 个已选条目均完成导入。这个旧 run 没有第五个合法召回候选，不能回填或假称为 5 篇；该部分行为保持为真实数量和既有 partial 语义。

## 改动

- [`backend/app/research/application/planner.py`](/Users/wjh/ResearchAgent/backend/app/research/application/planner.py)：每个既有 bounded facet Search Worker 请求全局 `target_paper_count`，而不是将目标数除以 Worker 数。默认最多 3 路、目标上限 20，因此仍在既有候选预算内；没有新增 Worker 或搜索路径。
- [`backend/app/research/application/orchestrator.py`](/Users/wjh/ResearchAgent/backend/app/research/application/orchestrator.py)：`_promote_catalog_floor` 评估完整的“已有 validated rows + 仍在 recall allowlist 内的 rows”，让原有 `PaperEvaluator` 在总召回池达到 5 时正常应用既有 floor；召回池总量不足时仍立即返回已有记录，不制造 ID。
- [`tests/research/test_selection_budget_convergence.py`](/Users/wjh/ResearchAgent/tests/research/test_selection_budget_convergence.py)：锁定目标 5 时两个 Search Worker 的计划形状为 `max_results=[5,5]`。
- [`tests/research/test_report_catalog_metadata.py`](/Users/wjh/ResearchAgent/tests/research/test_report_catalog_metadata.py)：锁定 4 个已验证候选 + 1 个同一召回池候选可被既有 floor 补足，以及召回池只有 4 个时不伪造第五个候选。

## 验证

先加红灯测试：

- `test_catalog_floor_counts_existing_records_when_evaluating_remaining_pool` 在修复前失败（实际返回 4、期望 5）；
- `test_search_workers_receive_global_target_budget_to_absorb_overlap` 在修复前失败（实际 `[3,3]`、期望 `[5,5]`）。

修复后：

- `.venv/bin/python -m pytest tests/research/test_selection_budget_convergence.py tests/research/test_report_catalog_metadata.py tests/research/test_catalog_search_worker_contract.py -q` → **24 passed，退出码 0**；
- `.venv/bin/python -m pytest tests/research/test_agent_selection_persistence.py tests/research/test_validated_evaluator_candidates.py tests/research/test_report_synthesis_contract.py -q` → **43 passed，退出码 0**；
- `.venv/bin/python -m pytest tests/research/test_research_backend_slice.py -q` → **57 passed、5 subtests passed，退出码 0**；
- `.venv/bin/ruff check backend/app/research/application/orchestrator.py backend/app/research/application/planner.py tests/research/test_report_catalog_metadata.py tests/research/test_selection_budget_convergence.py` → **通过，退出码 0**；
- `.venv/bin/python -m compileall -q backend/app/research/application/orchestrator.py backend/app/research/application/planner.py` → **通过，退出码 0**；
- `.venv/bin/python scripts/check_test_layout.py` → **`test layout: ok`，退出码 0**。

未执行全量回归、服务重启、真实 API 重试或任何生产数据变更。当前运行证据仍应按 4 篇/`partial` 处理，不能据此宣称 Spec032 E2E 已通过。

## 风险与下一步

- 新计划会让每个既有 facet 查询最多返回目标数量，增加有限的目录检索量；默认上限为 3 路 × 20 篇，仍低于现有 `max_candidates=100`，且最终选择仍由原有评估器和预算上限控制。
- 只有 Search Worker 真实召回的 ID 可以补足。若新运行的白名单并集仍少于 5，系统必须保持实际 `selected_count` 并沿既有 `partial`/`MATRIX_NOT_READY`（或矩阵自身已有错误码）结束，不能生成第五篇、不能把参数范围当作覆盖证据。
- 最小后续动作：由主 agent 在下一次受控服务重启后的新任务中确认两个 Search Worker 的计划 `max_results=5`、真实白名单并集、`selected_count` 和导入数；若并集达到 5，再验证现有矩阵/canonical 报告接线。旧 task 不重试、不回填。

## 耗时与日志

本轮从 `2026-10-08T18:57:45Z` 开始到 `2026-10-08T18:59:53Z` 完成，约 **2 分 08 秒**（测试执行约 0.9 秒、1.9 秒、4.1 秒）。进度日志：

`.codebuddy/agent-logs/spec-032/task-14/backend-dev/20261008-185745.md`

## 后续 P1：agent selection 统一收敛（2026-10-09）

### 触发证据

独立复审 `current-live-matrix-selection-review.md` 的语义探针发现：25 个合法召回候选在 `PaperEvaluator`、validated 列表和 agent 终态路径中仍保持 25 个，而既有 `BUDGET_CAPS["max_selected"]` 是 20。原实现只在 acquisition 读取时执行 `selections[:target_paper_count]`，因此无法约束 durable selection、synthesizer 输入、matrix allowlist 或 terminal `selected_count`。

先加红灯测试：

- `test_persist_agent_selections_enforces_global_selection_cap`：25 个候选、target=20、首项重复；修复前 `_persist_agent_selections` 不接受目标预算，调用直接失败。
- `test_agent_selection_budget_is_shared_by_persistence_report_matrix_and_terminal`：25 个候选、approved target=5、首项重复；修复前 durable selection 仍有 25 行，且 agent fan-out 没有统一的最终集合。

### 最小修复

- [`backend/app/research/application/orchestrator.py`](/Users/wjh/ResearchAgent/backend/app/research/application/orchestrator.py)：新增仅复用既有 `BUDGET_CAPS` 的 agent selection limit：`min(max(target_paper_count, 5), BUDGET_CAPS["max_selected"])`，并以稳定顺序去重、截断为单一最终集合。
- evaluator 完成后的 durable selection 写入、报告 synthesizer 输入/matrix context、最终报告重建及 terminal `selected_count` 均使用同一预算接缝；持久化在 `replace_selections` 前截断，避免等 acquisition 才发现超预算。
- [`tests/research/test_agent_selection_persistence.py`](/Users/wjh/ResearchAgent/tests/research/test_agent_selection_persistence.py)：覆盖 target=5、target=20、25 候选、重复候选，并断言 selection ID、synthesizer validated ID、matrix allowlist ID 三者相同；不足 5 个合法候选时不新增候选，仍保留真实 partial 语义。

本轮没有修改 matrix 安全校验、公开 schema、下载/搜索链、数据库模型、部署或生产数据。

### 验证

- `.venv/bin/python -m pytest tests/research/test_agent_selection_persistence.py tests/research/test_validated_evaluator_candidates.py tests/research/test_report_synthesis_contract.py tests/research/test_selection_budget_convergence.py tests/research/test_report_catalog_metadata.py tests/research/test_catalog_search_worker_contract.py -q` → **69 passed，退出码 0**。
- `.venv/bin/python -m pytest tests/research/test_research_backend_slice.py tests/research/test_research_report_matrix_bridge.py -q` → **73 passed、5 subtests passed，退出码 0**。
- `.venv/bin/ruff check backend/app/research/application/orchestrator.py tests/research/test_agent_selection_persistence.py` → **通过，退出码 0**。
- `.venv/bin/python -m compileall -q backend/app/research/application/orchestrator.py tests/research/test_agent_selection_persistence.py` → **通过，退出码 0**。

### 风险、下一步与耗时

- 风险：本轮只证明本地受控 runner 的预算接缝；没有重新启动服务、重试真实 task 或宣称生产 E2E 已通过。Search Worker 真实合法召回不足时仍只能返回实际数量并进入既有 partial/degraded 路径，不会因 target 或 max 参数伪造覆盖。
- 下一项最小 backend-dev 工作：主 agent 在候选复审通过并重新启动当前版本后，运行一次受控真实任务，记录 durable selections、synthesizer/matrix allowlist、terminal `selected_count` 和导入数量的同一 ID 集合；不重试旧生产数据、不做全量同步。
- 本轮从 `2026-10-09T03:18:41+0800` 到 `2026-10-09T03:21:23+0800`，约 **2 分 42 秒**。进度日志继续记录于 [20261008-185745.md](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-dev/20261008-185745.md)。

## P1-SEL-002：批准 minimum 与软 target 的终态接缝（2026-10-09）

### 结果

独立复审的有效矩阵探针确认旧接缝只按 `failures == 0` 收口：批准 `min_paper_count=5` 时，合法 selection 为 1 或 4、矩阵和 canonical report 均有效，仍会返回 `completed`/无 error。该行为已修复：

- agent 路径只从已批准 session plan 的 `scope_json.constraints` 解析显式 `min_paper_count`，复用既有 `resolve_paper_count_constraints`；`target_paper_count` 单独存在时不被当作 minimum。
- `selected_count < approved minimum` 时保留真实数量，设置既有 `EVIDENCE_INSUFFICIENT` 错误契约，并沿现有 partial/degraded 路径结束；不补造候选、不降低全局预算、不改变 matrix allowlist。
- 同一短缺原因 `approved minimum paper count not met: selected N of M` 已进入 task/result、terminal `reason`、activity Markdown、candidate artifact safe summary/Markdown、partial/failed notifications，以及 canonical immutable `ResearchReport.limitations_json`。
- `min=1,target=5,selected=4` 及 `min=5,target=5,selected=5` 不触发短缺；仍按有效 matrix/canonical 事实返回 `completed`。

### 精确改动路径

- [`backend/app/research/application/orchestrator.py`](/Users/wjh/ResearchAgent/backend/app/research/application/orchestrator.py)：approved minimum 解析、短缺原因/错误门禁、candidate artifact 限制、terminal/notification 接线。
- [`backend/app/research/application/report_generation.py`](/Users/wjh/ResearchAgent/backend/app/research/application/report_generation.py)：仅增加内部 `additional_limitations` 参数，把已验证的短缺原因并入现有 matrix-derived immutable report limitations；无 schema、表、公开 API 或版本变更。
- [`backend/app/research/application/report_synthesis.py`](/Users/wjh/ResearchAgent/backend/app/research/application/report_synthesis.py)：主 delivery notification 从已验证 safe limitation 传播同一 reason；不改变 artifact schema 或幂等键（短缺报告自身的 Markdown/hash 按新 limitation 正常派生）。
- [`tests/research/test_research_report_matrix_bridge.py`](/Users/wjh/ResearchAgent/tests/research/test_research_report_matrix_bridge.py)：新增有效 matrix 下的 1/4/4/5 候选边界，并断言 task、terminal、activity、notification、artifact 与 canonical report limitations 一致。

### 验证

- `.venv/bin/python -m pytest tests/research/test_research_report_matrix_bridge.py::test_approved_minimum_controls_agent_completion_and_surface_reason -q` → **4 passed，退出码 0**。
- `.venv/bin/python -m pytest tests/research/test_agent_selection_persistence.py tests/research/test_validated_evaluator_candidates.py tests/research/test_report_synthesis_contract.py tests/research/test_research_report_matrix_bridge.py tests/research/test_report_generation.py -q` → **75 passed，退出码 0**。
- `.venv/bin/python -m pytest tests/research/test_research_backend_slice.py -q` → **57 passed、5 subtests passed，退出码 0**。
- `.venv/bin/ruff check backend/app/research/application/orchestrator.py backend/app/research/application/report_generation.py backend/app/research/application/report_synthesis.py tests/research/test_research_report_matrix_bridge.py` → **通过，退出码 0**。
- `.venv/bin/python -m compileall -q backend/app/research/application/orchestrator.py backend/app/research/application/report_generation.py backend/app/research/application/report_synthesis.py tests/research/test_research_report_matrix_bridge.py` → **通过，退出码 0**。
- `git diff --check -- backend/app/research/application/orchestrator.py backend/app/research/application/report_generation.py backend/app/research/application/report_synthesis.py tests/research/test_research_report_matrix_bridge.py` → **通过，退出码 0**。

### 风险与下一步

- 本轮未部署、未重启 8000、未重试生产 task、未运行全量回归；不能以本地夹具结果宣称真实 E2E 已通过。
- 语义依赖 approved session plan 的显式 minimum；历史任务若没有该约束，仍按“无 minimum”处理，target 不会被错误升级为 hard minimum。这保持 target/min 的批准语义分离，但主 agent 仍需在新真实任务中核对计划落盘的 constraints。
- 下一项最小工作：经独立复审后，在受控新服务版本执行一次真实 task，记录 approved min/target、实际 selection 数、task/terminal/activity/notification/report limitations 五处相同 reason；若合法 selection 不足，验收应保持 partial，不能把 target 参数或 parser 能力写成覆盖成功。

### 耗时与日志

本轮约 **20 分钟**（从 2026-10-09 03:22 左右至 03:42 +0800，含红灯、定向回归和静态检查）。过程日志：

`.codebuddy/agent-logs/spec-032/task-14/backend-dev/20261008-185745.md`
