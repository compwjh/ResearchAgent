# Spec032 Task14：synthesizer output 修复独立后端复审

## 复审结论

结论：`P0=0，P1=0，代码级复审 PASS；真实 E2E 仍为 LIVE_RERUN_PENDING`。

本复审只覆盖 `current-synthesis-output-fix.md` 所述范围和当前工作树中的后端
diff，不把定向测试通过冒充生产自然语言 E2E 或 Spec032 全量验收。复审没有修改
业务代码、没有部署、没有创建或批准研究任务，也没有运行全量测试。

复审基线为 `git HEAD=00cdb6b3d6d56379881e7d4db04f0e76c19f9119`；工作树中实际审查
的修改为：

- `backend/app/research/application/orchestrator.py`
- `backend/app/research/application/agent_runtime.py`
- `tests/research/test_research_report_matrix_bridge.py`

## 逐项核对

| 门禁 | 复核证据 | 结论 |
|---|---|---|
| 冻结集合不能被模型或收尾 floor 扩张/替换 | synthesizer dispatch 前保存 `synthesis_validated_candidates`；模型输入的 `validated_candidates` 与 `citation_allowlist` 来自同一集合；收尾在独立 floor 计算后恢复冻结集合，并再次写入既有 selection projection。`test_synthesis_keeps_the_same_candidate_allowlist_after_final_projection_changes` 通过。 | PASS |
| approved budget 与 minimum 不被混用 | `_agent_selection_limit()` 对 target 使用既有全局上限（`max_selected`），并做去重后的有界前缀；`_approved_minimum_paper_count()` 只读取批准 scope 的显式 `min_count`，明确不把 target 当 minimum。25→5/20 上限、以及 minimum 5 下选 1/4 为 partial、minimum 1 下选 4 和 minimum 5 下选 5 为 completed 的契约均通过。 | PASS |
| selection、matrix、delivery 使用同一最终集合 | `_persist_agent_selections()` 严格按 allowlist、去重、全局 cap 持久化；最终矩阵 context 要求 durable selections 与冻结 candidate IDs 集合完全相等，并按每条 selection 的 `source_search_id` 解析对应 search snapshot；收尾 delivery 使用同一恢复后的集合。预算共享测试、live snapshot context 测试和集合漂移回归测试均通过。 | PASS |
| `source_search_id` provenance 保留 | synthesizer 前从 Search Worker 输出建立 candidate→search 映射，传入既有 `_persist_agent_selections()`；矩阵桥只接受该 selection provenance（旧数据才回落任务级 search handle），并检查 search 状态、未过期时间、结果行、snapshot ID 和摘要 digest。 | PASS |
| 越界 citation 仍拒绝 | `ReportSynthesizer.consume_validated_output()` 继续以 evaluator allowlist 校验 citation/source refs；矩阵 validator 继续要求 paper、snapshot、dimension、evidence locator 全部落在 server context。越界 candidate/citation、快照 digest 漂移和 fulltext/非法 stance 定向测试通过。 | PASS |
| 缺失或非法 matrix 不冒充完成 | `evidence_matrix` 是内部可选扩展；缺 context/缺 matrix/矩阵构建失败保持 `MATRIX_NOT_READY`，canonical report 不作为成功门禁，安全 candidate artifact 只能降级交付，终态不会因空矩阵标记 completed。matrix build failure、canonical generation failure 和内部 matrix 隔离测试通过。 | PASS |
| 合法 matrix prompt 不要求模型造证据 | synthesizer prompt 在存在 `matrix_context` 且 supplied snapshot 足以支撑 claim 时要求 internal-only `evidence_matrix`；无可支持 claim 时要求省略并记录 `MATRIX_NOT_READY`。prompt 明确禁止发明 claim/dimension/locator、URL/document/chunk/fulltext。matrix validator 还只接受 server dimensions、allowlisted IDs、catalog contextual 或摘要 digest 对齐的 evidence，并要求至少一个真实 supported claim。 | PASS |

上述判断基于实际控制流与测试，不依赖模型自行声明“已完成”。尤其是模型不能借由
新增 paper ID、citation ref 或 matrix locator 扩大 frozen set；所有这些字段仍在服务端
allowlist/snapshot validator 之后才会进入报告路径。

## 定向验证

所有命令均使用项目 `.venv`，退出码均为 `0`：

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py` | `21 passed in 2.28s` |
| `.venv/bin/python -m pytest -q tests/research/test_agent_selection_persistence.py` | `10 passed in 1.32s` |
| `.venv/bin/python -m pytest -q tests/research/test_report_synthesis_contract.py tests/research/test_agent_runtime_contract.py` | `58 passed in 1.93s` |
| `.venv/bin/ruff check backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_research_report_matrix_bridge.py` | `All checks passed` |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py backend/app/research/application/orchestrator.py tests/research/test_research_report_matrix_bridge.py` | 通过 |
| `git diff --check -- <上述三个文件>` | 通过 |

另对 `_role_contract_prompt("synthesizer", has_tool_results=True)` 做只读检查，确认输出
包含 `matrix_context`、`evidence_matrix`、`internal-only`、`MATRIX_NOT_READY` 和
明确的 no-fabrication 约束。

## 仍未完成的运行时门禁

修复说明中的真实 run 仍是 `partial/AGENT_OUTPUT_INVALID`，且当时没有 acquisition
batch/items、matrix 或 canonical report。此次复审没有重启服务、重试旧任务或创建新任务，
因此不能证明真实 Ollama 产出会在当前部署中生成合法 matrix，也不能证明最终 acquisition、
canonical report 和下载链已完成。下游应在包含该修复且经过独立 review 的重启版本上创建
新的自然语言 run，确认：

1. synthesizer 输入含逐候选真实 search snapshot context；
2. 合法摘要支持时 matrix 通过服务端 validator/build；
3. selection、matrix、delivery 和 terminal selected count 保持同一集合；
4. canonical report 及其版本化查看/下载路径实际存在；
5. 缺 matrix 或越界 citation 时仍保持 partial/明确错误，而不是伪成功。

在上述 live rerun 前，本修复只能标记为代码级复审通过，不能作为 Spec032 E2E
验收通过或 `已完成` 的依据。

## 复审边界

- 未改动 `backend/` 业务代码或测试；本文件是独立 review 交接物。
- 未改动模型、阈值、环境变量、下载安全、公开 schema/API、数据库迁移或全局配置。
- 未运行全项目扫描、全量 pytest、部署或生产数据操作。

