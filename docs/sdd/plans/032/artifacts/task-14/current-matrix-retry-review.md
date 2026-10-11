# Spec032 Task14：matrix retry 诊断复审

- 复审角色：backend-reviewer（独立复审；临时 Luna max）
- 复审时间：2026-10-11 Asia/Shanghai
- 复审基线：HEAD `e83fdd6`，审查当前未提交 diff
- 复审范围：`matrix_validation_diagnostic` 纯函数、runtime retry、retry checkpoint、validation event、最终 `AgentRunOutput`、event safe envelope；不审查或修改无关前端/业务范围。
- 约束：仅读代码与精准验证；未修改业务代码，未部署，未运行全量，未写生产数据库，未读取/修改 env 或密钥，未 commit/push。

## 审查结论

**不通过 / REQUEST CHANGES（P1 阻塞）**。

新增诊断的固定枚举、固定字段路径、脱敏边界、错误映射、四轮正常 retry、recovery 和公共 envelope 在正常路径均通过精准验证；但 `feedback_sent` 在真实发送前被按“将要重试”置为 `True`，无法证明 feedback 已实际进入下一次 provider 调用，且取消/预算耗尽/重试创建失败等路径会产生假阳性。该问题直接违背本轮“feedback_sent 不是仅构造就标发送”的验收条件，需修复后复审。

## P0/P1/P2

### P0

无。

### P1

#### P1-1：feedback_sent 在 provider 调用前提前为真

- 位置：`backend/app/research/application/agent_runtime.py:2238-2256`；retry context 直到 `:2272-2279` 才加入 `validation_feedback`，下一次 `_invoke` 尚未执行。
- 证据：实现使用 `feedback_sent = will_retry and validation_error.code == "MATRIX_NOT_READY"`，随后立即把该诊断写入 validation event 和 retry checkpoint。独立取消探针在第一次 malformed matrix 校验后触发取消，实际模型调用数为 1，但 validation event 已记录 `feedback_sent=True` / `feedback_classification=matrix_validation`。
- 影响：持久化遥测会把“待发送/已构造”误报成“已发送”；原诊断所要解决的 provider feedback wire-level 可观测缺口仍未闭合。若下一轮在 cancellation、budget gate、retry checkpoint 创建异常或 provider 调用前失败，诊断仍是假阳性。
- 最小修复建议：首次诊断先记录 `feedback_sent=False`；只有下一轮实际进入包含 `validation_feedback` 的 `_invoke` 后，追加/更新同 attempt 的发送事实（调用未发生或调用异常保持 false），并让最终 `AgentRunOutput` 与可复核 event 反映该事实。不要把 validator 合同、四轮上限或 schema/API 扩大。

### P2

无新增 P2。

## 已确认的安全与兼容边界

- `matrix_validation_diagnostic()` 只输出固定 `matrix_error_code`、`rule_id`、`field_paths`；已核对当前 matrix validator 的 45 个静态错误消息均命中固定映射，未知枚举回退到 `MATRIX_NOT_READY`/`matrix.contract`。
- runtime `error_code` 仅允许 `AGENT_OUTPUT_INVALID`、`MATRIX_NOT_READY`，未知值回退 `AGENT_OUTPUT_INVALID`；attempt 被夹在 1–4；分类值为固定枚举。
- 诊断实际生成路径不包含模型正文、prompt、hidden reasoning、摘要、locator 内容或动态 secret；`_safe_event_payload` 对实际生成诊断保留的仅是固定字段。
- 没有新增表、列、公开 API 或 validator；checkpoint 仍使用 `runtime-v1`，event envelope 仅做兼容性扩展。
- 正常路径四次 retry、`MATRIX_NOT_READY` 终止、search recovery 和 restart hydration 未观察到行为变化。

## 精准验证与退出码

以下全部使用绝对解释器 `/Users/wjh/ResearchAgent/.venv/bin/python`：

| 命令/范围 | 退出码 | 结果 |
|---|---:|---|
| `-c 'import sys, fastapi, langchain_ollama; ...'` | 0 | 实际解释器为 `.venv/bin/python`；`fastapi=0.141.1`、`langchain_ollama` 导入成功 |
| `pytest -q tests/research/test_agent_runtime_contract.py::test_matrix_validation_diagnostics_survive_retry_chain_and_persist_safely --tb=short --maxfail=1` | 0 | 1 passed |
| `pytest -q tests/research/test_agent_runtime_contract.py --tb=short --maxfail=1` | 0 | 53 passed |
| `pytest -q tests/research/test_research_report_matrix_bridge.py --tb=short --maxfail=1` | 0 | 22 passed |
| `pytest -q tests/research/test_work_item_output_recovery.py -k 'restart_hydrates_completed_outputs_for_downstream_workers or restart_rejects_persisted_synthesis_matrix_before_reuse' --tb=short --maxfail=1` | 0 | 2 passed，11 deselected |
| `ruff check`（3 个生产文件及 2 个受影响测试） | 0 | All checks passed |
| `python -m py_compile`（同上） | 0 | 通过 |
| `python scripts/check_test_layout.py` | 0 | test layout: ok |
| `git diff --check` | 0 | 通过 |
| 纯函数探针（45 个静态 validator 错误、未知 enum、动态敏感文本） | 0 | 固定 rule/path、枚举 fallback、脱敏有界 |
| 实际生成诊断经 `_safe_event_payload` 探针 | 0 | 未保留 prompt/secret/token/abstract/summary |
| `feedback_sent` 取消时序探针 | 0 | 复现 P1：model calls=1，validation event `feedback_sent=True` |

复审日志：`.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261011-123937-matrix-retry-review.md`。

## P1 修复独立复审结论（2026-10-11）

### 审查结论

**通过 / APPROVED（无 P0/P1/P2）**。

本次独立复审确认原 P1 已按最小范围修复：首次 validation 诊断和 retry handoff checkpoint
明确落 `feedback_sent=false`；仅当携带 `validation_feedback` 的下一次 `_invoke()` 正常返回后，
才在内存最终元数据中更新为 `true/matrix_validation`，并追加独立的 `validation_feedback`
事件。取消门、预算门、retry checkpoint 创建失败和 provider 调用终止异常均未产生成功标记，
没有把该标记解释成 wire receipt 或模型已理解反馈。

### P0/P1/P2

- P0：无。
- P1：无。旧 P1（provider 调用前提前把 `feedback_sent` 置真）已闭环。
- P2：无新增问题。

### 事实一致性与边界核对

- 正常 retry：实际第二次模型调用的 context 含 `validation_feedback`；事件顺序为首次诊断
  `false`，provider 返回后追加 `validation_feedback=true`；最终 `AgentRunOutput.model_metadata`
  与该事实一致。
- 取消/预算/checkpoint/provider 异常：分别确认取消和预算只发生 1 次模型调用、checkpoint
  失败只发生 1 次调用、provider 终止异常发生 2 次调用且第二次 context 含 feedback；上述终止
  输出均保持 `feedback_sent=false`，不追加成功事件。
- 四轮耗尽：最终诊断的发送事实为 `[true, true, true, false]`；前三个 retry handoff
  checkpoint 保留创建时的 `false`，对应 validation event 的最新记录为前三个 `true`、第四个
  `false`。四次调用、最终 `MATRIX_NOT_READY` 和四轮上限行为未改变。
- recovery/公开合同：matrix bridge 及 restart recovery 精准测试通过；未改变 validator、
  allowlist、snapshot/digest/locator、`runtime-v1` checkpoint schema 或公开 `AgentRunOutput`
  envelope。搜索 worker 的既有 catalog recovery 路径未被诊断分支拦截。
- 脱敏与有界性：67 个固定 validator 规则均只映射固定 rule/path；未知 code/message 回退到
  固定 `MATRIX_NOT_READY`/`matrix.contract`。安全事件 envelope 过滤 prompt、hidden reasoning、
  secret、token、API key 和 URL；诊断不包含模型正文、候选摘要或动态 validator 文本。

### 精准验证与退出码

以下均使用绝对解释器 `/Users/wjh/ResearchAgent/.venv/bin/python`，未部署、未调用真实 provider、
未写生产数据库、未改变 env、未重试旧 task、未 commit/push：

| 命令/范围 | 退出码 | 结果 |
|---|---:|---|
| `pytest -q tests/research/test_agent_runtime_contract.py -k 'feedback_sent or matrix_validation_diagnostics_survive_retry_chain_and_persist_safely or synthesizer_requires_matrix_when_context_is_present_and_retries_with_feedback' --tb=short --maxfail=1` | 0 | 6 passed，51 deselected |
| `pytest -q tests/research/test_agent_runtime_contract.py --tb=short --maxfail=1` | 0 | 57 passed |
| `pytest -q tests/research/test_research_report_matrix_bridge.py --tb=short --maxfail=1` | 0 | 22 passed |
| `pytest -q tests/research/test_work_item_output_recovery.py -k 'restart_hydrates_completed_outputs_for_downstream_workers or restart_rejects_persisted_synthesis_matrix_before_reuse' --tb=short --maxfail=1` | 0 | 2 passed，11 deselected |
| `ruff check`（3 个生产文件及 2 个受影响测试） | 0 | All checks passed |
| `py_compile`（同上） | 0 | 通过 |
| `scripts/check_test_layout.py` | 0 | test layout: ok |
| `git diff --check` | 0 | 通过 |
| 固定诊断 67 规则、未知枚举、安全 event envelope、事件顺序只读探针 | 0 | 规则/路径固定、脱敏有界、false→true 时序一致 |

复审日志：`.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261011-191424.md`。

