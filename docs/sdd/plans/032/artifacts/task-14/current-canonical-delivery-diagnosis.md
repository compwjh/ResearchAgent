# Spec032 Task14：Canonical Report Delivery 精准诊断

## 结论

真实 task `6184c29c7f32577e8c44e4eeb4a3b4c4` 的 synthesizer attempt-2 已产出结构化结果；`evidence_matrix` 直接通过共享 `validate_synthesis_matrix_payload`，但 candidate report 消费边界失败，导致矩阵持久化与 canonical `ResearchReport` 生成均未执行。失败不是模型“没有输出 matrix”，也不是 task/session/owner/version 绑定不一致。

第一处红灯是 `_separate_synthesis_matrix()` 将 runtime-owned `work_item_id` 带入 candidate-level report envelope。`ReportSynthesisOutput` 使用 `extra="forbid"`，因此 `validate_report_synthesis_output()` 返回固定 `AGENT_OUTPUT_INVALID`（Pydantic `extra_forbidden`）；随后编排进入安全的 deterministic artifact fallback，只留下 partial artifacts，最终 API 暴露 `MATRIX_NOT_READY` / `REPORT_NOT_READY`。

## 脱敏真实证据

- task 状态为 `partial`，`current_plan_version=1`，`target_paper_count=5`，owner/session/conversation/task 绑定一致。
- synthesizer WorkItem 为 `completed`；AgentRun attempt-1 为 `limit_reached/MATRIX_NOT_READY`，attempt-2 为 `completed`，且 attempt-2 output hash 已与 envelope 一致。
- attempt-2 结构化输出包含 5 个 citation manifest 条目、5 个 candidate、2 个 dimensions、5 个 claims、10 个 evidence、10 个 cells；只检查字段、数量、枚举和稳定 ID，不落盘或回传模型原文、prompt、hidden reasoning、动态错误文本或 secrets。
- 直接对该真实 output 执行共享 matrix validator：通过；matrix 的 `schema_version=evidence-report-v1`、`plan_version=1`，candidate allowlist、snapshot digest、evidence locator 与 cell ownership 均通过。
- 只读查询显示 `research_claims`、`research_claim_evidence`、`research_comparison_dimensions`、`research_comparison_cells` 和 `research_reports` 均无该 task 行；说明失败发生在 `build_matrix` 之前，而不是 store transaction 中途吞错。
- 只读查询显示 markdown/html/citation_manifest 三个 artifact 均由 attempt-2 产生，符合 candidate artifact fallback 事实；它们不是 canonical report。

## 最小修复

在 `backend/app/research/application/orchestrator.py` 的 `_separate_synthesis_matrix()` 中，仅剥离已由 Agent runner 绑定并校验的固定 runtime 字段 `work_item_id`，并重算剥离后的 candidate envelope hash；不剥离任意未知字段，不修改 `ReportSynthesisOutput` schema，不放宽 matrix validator，不创建 claims/evidence，也不改旧 task 回填或新 API。

新增回归测试 `test_separate_synthesis_matrix_strips_runtime_work_item_binding`：确认 matrix 保留、artifact 不含 runtime binding、重算 hash 可验证。既有 matrix bridge 测试覆盖 matrix transaction、缺 matrix、build failure、report generation failure 与选择集一致性。

## 验证

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py::test_separate_synthesis_matrix_strips_runtime_work_item_binding` | 1 passed |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py` | 23 passed |
| `.venv/bin/python -m py_compile backend/app/research/application/orchestrator.py backend/app/research/application/report_synthesis.py tests/research/test_research_report_matrix_bridge.py` | 通过 |
| `git diff --check` | 通过 |

未执行全量回归、部署或重新跑旧 task；修复后的真实 E2E 应使用新的 run_id，由上游验收流程执行。
