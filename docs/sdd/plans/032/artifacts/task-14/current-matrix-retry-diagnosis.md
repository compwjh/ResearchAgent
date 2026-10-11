# Spec032 Task14：fresh matrix retry 诊断

## 结论

本次只读诊断确认：fresh run 的 synthesizer 输入已经包含完整的 server-owned
`matrix_context`，不是候选、维度、snapshot、digest、locator 或 allowlist 缺失，也没有
证据表明 server 与输入 ID 不一致。共享 validator 与 retry contract 的定向测试仍通过。

但是，公开持久化记录没有保存四次模型响应正文或 retry context，因此无法诚实地把每一次
`MATRIX_NOT_READY` 归因到某一个具体 output 字段，也无法从生产记录证明每次反馈已在线送达。
公开记录只能确认第一轮为 `AGENT_OUTPUT_INVALID`，随后三轮为
`MATRIX_NOT_READY`，总计四轮并耗尽。因而当前最小、可复核的判断是：这是五候选矩阵输出在
真实模型上的持续生成/结构化失败，现有证据不足以判定某个字段级 schema mismatch 或
validator bug；不应放宽合同、伪造 matrix 或全局换模型。

## 受检运行与公开记录

- run：`spec032-task14-fuzzing-supported-20261011T035216Z`
- task：`8fed1bc44a8158b59e3d48812ab4016b`
- syn WorkItem：`8fed1bc44a8158b59e3d48812ab4016b:syn`
- deployed commit：`e83fdd6f8a43484f42e06d69a0d57f29f408bf51`
- 上游：5 个 evaluator-selected 候选，5/5 acquisition/import 完成；没有重新搜索、补选或重试旧 task。

SQLite `data/research/research.sqlite3` 的 `research_agent_runs`、
`research_agent_checkpoints`、`research_work_items` 和 `research_events` 给出的 syn 记录为：

| attempt | resolved model | public status | public error | public checkpoint/output |
|---:|---|---|---|---|
| 1 | `qwen3.5:9b` | `limit_reached` | `AGENT_OUTPUT_INVALID` | checkpoint `output=null`, `tool_results=[]` |
| 2 | `qwen3.5:9b` | `limit_reached` | `MATRIX_NOT_READY` | checkpoint `output=null`, `tool_results=[]` |
| 3 | `qwen3.5:9b` | `limit_reached` | `MATRIX_NOT_READY` | checkpoint `output=null`, `tool_results=[]` |
| 4 | `qwen3.8:27b-q4_K_M` | `failed` | `MATRIX_NOT_READY` | no new non-null output/checkpoint |

四次 attempt 的公开持久化记录没有模型输出正文、字段列表、validator detail 或
`validation_feedback`。`research_events` 只公开 syn skill/agent 的最终错误码；没有隐藏思考、
原始 provider content 或可安全披露的逐轮 JSON。故本表中的“具体 invalid 字段”对四轮均为
**公开记录不可得**，不能用推测补写。

## 输入 contract 审计

从 syn WorkItem 的实际 `input_json` 读取到的 `matrix_context` 为完整非空 mapping：

- `schema_version=evidence-report-v1`、`plan_version=1`；
- `dimensions` 为 2 个 server 维度（`facet-1`、`facet-2`），含精确的
  `dimension_id/label/definition/display_order`；
- `allowed_paper_ids` 为 5 个实际 evaluator/import ID：
  `ef9e0846844e5b02834163586ea6ddc9`、`9793a4a35caad52ee99f926ae7c90810`、
  `bb826cac3486a295d93eb9b6cea0a6f8`、`57e0402f82fe2ce354bea423b201fde3`、
  `c74fdf1babb53a9cbcb6a6ac9fa5cd0e`；
- `candidates` 恰为 5 项，每项都有 `paper_id`、标题、完整 catalog abstract、
  64 位 `abstract_digest`、精确 `abstract_ref=catalog:<paper_id>`，以及真实
  `catalog_snapshot_id=a86edcca600c4e6ea6c304f1e6bb62b4`；
- `citation_allowlist` 与 `validated_candidates` 都覆盖同一组 5 个 ID，evidence refs
  为对应的 `catalog:<paper_id>`；
- 输入没有 document ID、全文 chunk 或 URL 作为矩阵证据来源。

因此，要求模型所需的 snapshot、dimension、locator 模板和 paper ID 均已给足；没有发现
“context 缺失”或“server 传入 allowlist/聚合来源与模型输入不一致”。这些结论只基于实际
持久化输入，不延伸到未保存的模型正文。

## Prompt、validator 与模型能力区分

### Prompt/运行时 contract

`backend/app/research/application/agent_runtime.py` 的 synthesizer contract 明确要求：

- 非空 `matrix_context` 时必须输出顶层 `evidence_matrix`；
- 使用 `evidence-report-v1`、批准 `plan_version` 和完全相等的 server dimensions；
- claims/evidence/cells 只能使用 allowlist 与 supplied abstract snapshot locator；
- 禁止 URL、document ID、全文和发明维度；
- 每个 cell 的 evidence 必须同时匹配 claim、paper 和 stance。

`MATRIX_NOT_READY` retry 会把 bounded `validation_feedback` 加入下一轮 context，包含
`code`、`required_fields=["evidence_matrix"]`、shape 要求，以及 validator 公开的
`matrix_error_code`/detail（若该轮已有 detail）。代码路径没有把 hidden reasoning 或未净化
provider 文本放进反馈。

### 四轮反馈是否实际送达

静态代码路径和 fake-model 合同测试证明：当 `_validate_output()` 抛出
`MATRIX_NOT_READY` 时，下一次 `_invoke()` 收到 `validation_feedback`；耗尽后直接失败，不
走 online fallback。可是本次真实 run 没有持久化每轮 request context，且 checkpoint 在
失败/续接时固定保存 `output=null`，所以**无法由公开证据确认 attempts 2–4 的 wire-level
feedback 内容或送达结果**。这是观测缺口，不应伪称为真实模型已读取了某条具体 detail。

### Field/schema mismatch 与真实模型能力

现有公开记录只给出 `AGENT_OUTPUT_INVALID`/`MATRIX_NOT_READY`，无法区分：

1. 第一轮是否是非 JSON/顶层 schema 解析失败；
2. 后三轮是否缺少 `evidence_matrix`，或 matrix 存在但命中了
   `REPORT_SCHEMA_INVALID`、`EVIDENCE_LOCATOR_INVALID`、`EVIDENCE_INSUFFICIENT` 等具体
   validator 分支。

共享 validator、合法 payload、跨论文证据、snapshot/digest/维度/allowlist 和 restart
 hydration 定向测试均通过；因此目前没有代码级 schema mismatch 证据。相反，本 run 在
 5-candidate、2-dimension、完整 abstract 输入下连续四轮失败，而公开记录没有任何成功的
 matrix output；结合无法取得 response body，最保守结论是“真实模型的该次大上下文结构化
 输出能力/生成稳定性不足或不可观测”，不是 validator 应放宽。此前单候选 probe 通过不能
 推导五候选场景必然通过。

## 最小后续建议

1. 保持现有 allowlist、snapshot/digest/locator、dimension、cell/claim/evidence 约束和
   最多四轮 `MATRIX_NOT_READY` 语义不变；不补 candidate、不造证据、不把 artifact 当 matrix。
2. 若要让下一次诊断能回答“具体字段/反馈是否送达”，只增加 provider-safe、无原文的逐轮
   telemetry：attempt、error code、`matrix_error_code`、bounded detail 字段名/长度、
   feedback code/hash/长度和 sent boolean；不要记录模型正文或 hidden reasoning。此项属于
   观测增强，当前没有足够证据在本轮修改业务逻辑。
3. 新建 fresh run 时继续使用完整 server context，记录实际 resolved model、每轮公开错误和
   最终 validator/canonical 状态；不重试本旧 task、不修改全局模型/阈值/env。

## 当前验证与未验证项

本轮只运行受影响的后端精准验证，没有部署、全量回归、生产写入或旧 task 重试：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py -k 'synthesizer_requires_matrix or matrix_requirement_exhausts or without_matrix_context or ollama_synthesizer_prompt' --maxfail=1` | 0 | 4 passed，48 deselected |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py --maxfail=1` | 0 | 22 passed |
| `.venv/bin/python -m ruff check backend/app/research/application/agent_runtime.py backend/app/research/application/matrix_contract.py backend/app/research/application/orchestrator.py tests/research/test_agent_runtime_contract.py tests/research/test_research_report_matrix_bridge.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py backend/app/research/application/matrix_contract.py backend/app/research/application/orchestrator.py tests/research/test_agent_runtime_contract.py tests/research/test_research_report_matrix_bridge.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

未验证：四次 provider 原始 output 正文、逐轮 wire-level feedback、五候选场景新的真实
matrix/canonical report；这些需要新的受控 run 或新增安全 telemetry，不能从旧 task 的
空 checkpoint 推断。

## 观测缺口修复追加（2026-10-11）

上面的“当前没有足够证据在本轮修改业务逻辑”是修复前结论，现已纠正为：本轮在不改变
matrix 合同、allowlist、证据校验或最多四次 retry 语义的前提下，补齐了现有错误 metadata
载荷中的 provider-safe validator 诊断。它只记录 `attempt`、`error_code`、固定
`matrix_error_code`、固定 `rule_id`/`field_paths`、`feedback_classification` 和
`feedback_sent`；不记录 validator 原文、模型输出、prompt、hidden reasoning、候选摘要或
敏感值。

### 实施边界

- `backend/app/research/application/matrix_contract.py` 新增纯函数
  `matrix_validation_diagnostic()`，复用既有 `EvidenceMatrixError`，把固定 validator
  分支映射成稳定规则标识和字段路径；缺失 `evidence_matrix` 也固定映射到
  `matrix.evidence_matrix.required`/`evidence_matrix`。没有第二套校验器，也没有修改任何
  合法输出或证据归属规则。
- `backend/app/research/application/agent_runtime.py` 在既有 retry 分支记录有界诊断：前三个
  可发送 `MATRIX_NOT_READY` 反馈的尝试分类为 `matrix_validation`，第四次耗尽分类为
  `not_sent`；最终 `AgentRunOutput.model_metadata`、retry handoff checkpoint 和 validation
  event 使用同一结构化诊断。反馈正文仍仅作为下一轮模型的瞬时上下文，不写入诊断载荷。
- `backend/app/research/infrastructure/research_store.py` 只扩展既有 event safe-key 白名单，
  没有新增数据库表、列、公开 API 或日志框架。
- `tests/research/test_agent_runtime_contract.py` 新增持久化边界测试，证明四轮 malformed
  matrix 的具体 `REPORT_SCHEMA_INVALID`/cell ownership 路径、重试反馈发送状态、checkpoint
  链、AgentRun 的 `limit_reached`/`failed` 状态与错误码、以及 event metadata 都保留；同时检查诊断长度及 prompt/reasoning/secret/token/API key/
  abstract 等敏感内容不泄露。合法 matrix 与既有 restart hydration 测试继续通过。

### 红灯与修复后验证

先运行新增测试证明缺口：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py::test_matrix_validation_diagnostics_survive_retry_chain_and_persist_safely --maxfail=1`（修复前） | 1 | `KeyError: validation_diagnostics`；四轮失败仍只有错误码，未形成结构化诊断 |
| 同一测试（修复后） | 0 | 1 passed |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py --tb=short --maxfail=1` | 0 | 53 passed |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py --tb=short --maxfail=1` | 0 | 22 passed |
| `.venv/bin/python -m pytest -q tests/research/test_work_item_output_recovery.py -k 'restart_hydrates_completed_outputs_for_downstream_workers or restart_rejects_persisted_synthesis_matrix_before_reuse' --tb=short --maxfail=1` | 0 | 2 passed，11 deselected |
| `.venv/bin/python -m ruff check backend/app/research/application/agent_runtime.py backend/app/research/application/matrix_contract.py backend/app/research/infrastructure/research_store.py tests/research/test_agent_runtime_contract.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py backend/app/research/application/matrix_contract.py backend/app/research/infrastructure/research_store.py tests/research/test_agent_runtime_contract.py` | 0 | 通过 |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | test layout: ok |
| `git diff --check` | 0 | 通过 |

本轮没有重新调用 provider、没有写生产记录、没有部署、没有改变 env/模型/allowlist，也没有
重试旧 task。未验证项仍是原 fresh run 的 provider 原文和 wire-level 反馈；新增诊断会在
后续受控运行中提供固定字段级证据，不能回填旧 run 的空 checkpoint。

## P1 复审修复追加：feedback_sent 时序（2026-10-11）

复审指出此前实现把“将要重试”误记为 `feedback_sent=true`：validation event 和 retry
checkpoint 在下一次 provider 调用前就写入了 true，取消/预算门/checkpoint 创建失败/provider
异常都会形成假阳性。复审报告中的取消时序探针已以退出码 0 复现该 P1（实际 model calls=1，
事件却为 true）。

### 最小修复

- validation 失败时先生成并持久化 `feedback_sent=false`；retry checkpoint 保留这一创建时
  事实，不声称 wire receipt。
- 只有 retry context 确实含 `validation_feedback` 且下一次 `_invoke()` 正常返回后，才更新
  同一内存诊断项为 `true/matrix_validation`，并追加一个固定字段的
  `validation_feedback` event（独立 node key，避免覆盖 append-only event）。这表示“带反馈的
  provider 调用已返回”，不是网络/模型已理解反馈的证明。
- `_invoke()` 抛错、retry checkpoint 创建失败、取消门或预算门在下一次调用前触发时不更新；
  所有可达的取消/预算/异常 `AgentRunOutput` 也复用同一 `validation_metadata()`，不会丢失
  false 事实。validator、四次上限、checkpoint schema、公开 API 与脱敏规则均未改变。

### P1 回归验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py -k 'feedback_sent or matrix_validation_diagnostics_survive_retry_chain_and_persist_safely or synthesizer_requires_matrix_when_context_is_present_and_retries_with_feedback' --tb=short --maxfail=1` | 0 | 6 passed，51 deselected |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py --tb=short --maxfail=1` | 0 | 57 passed |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py --tb=short --maxfail=1` | 0 | 22 passed |
| `.venv/bin/python -m pytest -q tests/research/test_work_item_output_recovery.py -k 'restart_hydrates_completed_outputs_for_downstream_workers or restart_rejects_persisted_synthesis_matrix_before_reuse' --tb=short --maxfail=1` | 0 | 2 passed，11 deselected |
| `.venv/bin/python -m ruff check backend/app/research/application/agent_runtime.py tests/research/test_agent_runtime_contract.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py backend/app/research/application/matrix_contract.py backend/app/research/infrastructure/research_store.py tests/research/test_agent_runtime_contract.py` | 0 | 通过 |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | test layout: ok |
| `git diff --check` | 0 | 通过 |

新增场景覆盖正常重试、取消后未调用、预算阻断、retry checkpoint 失败和 provider 调用异常；
均验证诊断不泄露模型正文/敏感值，且原 matrix 合同与四次 retry 行为保持不变。未部署、未调用
真实 provider、未写生产、未改 env、未重试旧 task、未 commit/push；独立复审待进行。
