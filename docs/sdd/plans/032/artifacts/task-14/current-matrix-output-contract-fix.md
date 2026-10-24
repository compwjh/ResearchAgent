# Spec032 Task14：matrix output contract fix

## 状态

`IMPLEMENTED / LIVE_RERUN_PENDING`。本轮只修复真实 synthesizer 在服务已经提供有效
`matrix_context` 时仍把内部 `evidence_matrix` 当作可选字段的问题。未部署、未重跑真实
任务、未写生产数据、未运行全量回归。

## 冻结的真实失败形状

来源：

- `docs/sdd/plans/032/artifacts/task-14/current-research-e2e-frozen-report.md`
- `docs/sdd/plans/032/artifacts/task-14/current-research-e2e-frozen-evidence.json`

真实运行 `659d5279ac4b5574ab317c6368a6527c` / session
`c129b90b6b2246258de471713ae0bf0b` 已完成 5/5 受控导入，候选 artifact 为 15,563 字，
但最终为 `partial/MATRIX_NOT_READY`，canonical report 未生成。synthesizer 的输入已经有：

- `matrix_context`：5 个 allowlisted paper、5 个候选、2 个 server-provided dimensions；
- `citation_allowlist`：5 个候选，与 matrix context 对齐；
- 每候选的真实目录快照范围由 server 输入冻结。

AgentRun 输出的顶层字段为
`artifact_ids, citation_manifest, output_hash, report_version, safe_summary, schema_version,
sections, source_refs`，没有 `evidence_matrix`。输出被现有 runtime 当作 completed，之后由
既有 matrix bridge 记录 `MATRIX_NOT_READY`。

## 根因

`_OllamaRunnerAdapter` 原先只把 `ROLE_OUTPUT_FIELDS["synthesizer"]` 的 candidate-level
字段放入 role prompt；没有把有效 `matrix_context` 变成条件必需项，也没有传入另一套
provider JSON schema。`_validate_output()` 只校验 candidate-level 必填字段，而严格的
`REPORT_SYNTHESIS_OUTPUT_SCHEMA` 属于公开 artifact envelope，且由既有
`_separate_synthesis_matrix()` 在 public validation 前剥离内部扩展，并不是本次模型输出
缺字段的拒绝点。解析器本身不会拒绝额外 JSON key。

因此本次修复没有放宽 locator、没有从 Markdown 反解析，也没有把内部字段加入公开
artifact schema；只在 server 已给出非空 matrix context 的这条路径补齐 producer/runtime
合同。

## 最小修复

### Runtime producer contract

`backend/app/research/application/agent_runtime.py`：

1. 新增有界 `_synthesis_matrix_required()`：仅当 synthesizer 的
   `work_item_input.matrix_context` 是非空 mapping 时开启要求；没有 context 的旧路径仍
   允许缺少 `evidence_matrix`。
2. `_OllamaRunnerAdapter` 在该条件下把 `evidence_matrix` 加入 role contract 字段，并向
   真实模型提示既有 `evidence-report-v1` 的具体 JSON shape：`dimensions/claims/evidence/cells`。
   示例只含 placeholder，要求模型替换为 server 提供的真实 dimension、allowlisted paper、
   `catalog_snapshot_id` 和原始 abstract SHA-256 locator；禁止 fulltext、URL、document ID、
   chunk、发明维度或证据。
3. `_validate_output()` 在该条件下要求 `evidence_matrix` 为 object；缺失或非 object 以
   稳定 `MATRIX_NOT_READY` 触发已有最多四次 model-loop/structured retry。
4. retry context 只追加 bounded `validation_feedback`，包含错误码、必需字段和字段 shape，
   不回传 provider hidden reasoning 或未净化文本。重试耗尽直接返回 `MATRIX_NOT_READY`，不
   走在线 fallback/全局换模型；上层沿用既有 partial/no-canonical-report 语义。
5. 内部 extension 仍在现有 bridge 处剥离，`ReportSynthesisOutput`、artifact envelope、
   API、数据库 schema、AgentRun identity 均未改变。

### Regression coverage

新增/补充定向合同：

- 有 context + 首轮缺 matrix：第二轮收到具体 `MATRIX_NOT_READY` feedback，合法
  `evidence-report-v1` matrix 被 runtime 接纳；
- 缺 matrix 连续四轮：终态为 `failed/MATRIX_NOT_READY`，model loop 恰为 4，不静默默认或
  伪造 matrix；
- 无 context：candidate-level synthesizer 仍单轮 completed；
- Ollama adapter 的 conditional prompt 含内部 shape；
- orchestrator 收到缺 matrix 的 candidate output 时仍为 `partial/MATRIX_NOT_READY`，且不
  创建 canonical `ResearchReport`。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py -k 'synthesizer_requires_matrix or matrix_requirement_exhausts or without_matrix_context or ollama_synthesizer_prompt' --maxfail=1`（修复前） | 1 | 红灯：首轮缺 matrix 被错误当作 completed |
| 同上（修复后） | 0 | `4 passed, 30 deselected` |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_research_report_matrix_bridge.py --maxfail=1` | 0 | `56 passed` |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_research_report_matrix_bridge.py tests/research/test_research_agent_approval_contract.py tests/research/test_report_synthesis_contract.py --maxfail=1` | 0 | `104 passed` |
| `.venv/bin/python -m ruff check backend/app/research/application/agent_runtime.py tests/research/test_agent_runtime_contract.py tests/research/test_research_report_matrix_bridge.py` | 0 | `All checks passed` |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py tests/research/test_agent_runtime_contract.py tests/research/test_research_report_matrix_bridge.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 结论与门禁

- P0：0。
- 本轮代码/定向测试范围内 P1：0；缺 matrix 不再被误报 completed，也不会由 runtime
  默认或伪造 evidence。
- 仍不能宣称真实 E2E 通过。必须在包含本修复的服务版本上重跑一次真实 5-candidate
  场景，确认 AgentRun 的输入含逐候选真实 snapshot context，模型在有支持 claim 时输出
  matrix，随后 validator → `build_matrix` → `ReportGenerationService` 以及 canonical
  report/artifact 正常完成。真实重跑前保持 `LIVE_RERUN_PENDING`。
