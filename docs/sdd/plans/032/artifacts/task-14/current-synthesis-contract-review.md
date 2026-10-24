# Spec032 Task14：普通 Synthesizer output contract 独立后端复审

- 复审角色：`backend-reviewer`（独立复审）
- 复审时间：2026-10-11 Asia/Shanghai
- 复审基线：HEAD `7d6834228b46496c96d951e2ba04280146f8d0cc`，审查当前未提交 diff
- 审查范围：`backend/app/research/application/agent_runtime.py` 与
  `tests/research/test_agent_runtime_contract.py` 的普通 `AGENT_OUTPUT_INVALID`
  结构化纠错反馈、固定诊断、retry/recovery 边界。
- 约束：未修改业务代码或测试、未部署、未调用真实 provider、未写生产数据库、未读取/修改
  env 或密钥、未运行全量回归、未 commit/push。

## 复审结论

**通过 / APPROVED（P0=0，P1=0，P2=0）**。

普通输出合同错误已能把有界结构化 `validation_feedback` 传入下一次 `_invoke()`，并且
schema、身份/source binding、hash、allowlist、matrix validator、四次尝试上限、资源 cap
和公开 `AgentRunOutput` 路径均未被放宽；固定诊断和脱敏也通过精准核对。取消屏障探针虽然
最终返回 `cancelled`，但第二次 `_invoke()` 已实际携带 feedback 并正常返回，因此
`feedback_sent=true` 符合既有定义：它记录 provider 调用成功返回，不代表 run 成功或结果已被
接受。未发现“没有发生 retry invoke 却标记 true”的路径，也未发现错误持久化/恢复影响。

## P0/P1/P2

### P0

无。

### P1

无。既有反馈定义明确将“发送事实”和 run 的终态分离。

### P2

无。

## 已通过的边界核对

| 门禁 | 证据 | 结论 |
|---|---|---|
| 普通错误 feedback 实际传下一次 invoke | generic output、provider-content 结构化测试；第二次调用 context 含 `validation_feedback.code=AGENT_OUTPUT_INVALID`、required fields、shape 和固定 failure | PASS |
| provider 异常不误报发送 | 普通合同错误后第二次 provider 抛 `MODEL_TIMEOUT`；最终 `feedback_sent=false`，但第二次 context 已携带 feedback | PASS |
| 取消终态与发送事实分离 | 第二次 provider 调用已收到 feedback 并正常返回，之后取消屏障返回 `cancelled`；`feedback_sent=true` 记录真实 provider 返回，不表示 run completed；取消发生在 retry invoke 前时保持 false | PASS |
| 四次 retry 与 cap | 普通无效输出耗尽探针固定 `4` 次调用、`4` model loops，diagnostics 为 `[true,true,true,false]`；既有预算/cap 控制流未变 | PASS |
| 固定诊断 | parse/provider content/required/safety/identity/source binding/structure 均映射到固定 rule/path；field path 经固定 allowlist 二次过滤 | PASS |
| schema/ID/hash/allowlist | `_validate_output()` 仍按 safe-scope、source refs、schema、identity/source binding、role fields 顺序校验，并在 server normalization 后计算 hash；Tool/Skill allowlist 在 invoke 前仍由既有 capability resolver 校验 | PASS |
| matrix 合同 | 缺失或非法 `evidence_matrix` 继续走 `MATRIX_NOT_READY` 与既有 matrix validator；普通 feedback 分支未绕过 matrix 分支 | PASS |
| 脱敏 | feedback/diagnostic 仅包含固定 code、rule、paths、required fields、shape；探针未见 raw model content、prompt、hidden reasoning、secret、URL 或动态错误文本进入诊断 | PASS |
| 公开 API | 未新增字段到公开输入/输出 schema；`AgentRunOutput`、checkpoint `runtime-v1`、恢复入口和资源 cap 未改变 | PASS |

## 精准验证与退出码

以下均使用项目 `.venv`，退出码均为 `0`：

| 命令/范围 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py -k 'generic_output_contract or provider_content_block' --tb=short --maxfail=1` | `4 passed, 57 deselected` |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py --tb=short --maxfail=1` | `61 passed` |
| `.venv/bin/python -m pytest -q tests/research/test_research_report_matrix_bridge.py --tb=short --maxfail=1` | `22 passed` |
| `.venv/bin/python -m pytest -q tests/research/test_work_item_output_recovery.py -k 'restart_hydrates_completed_outputs_for_downstream_workers or restart_rejects_persisted_synthesis_matrix_before_reuse' --tb=short --maxfail=1` | `2 passed, 11 deselected` |
| `.venv/bin/python -m ruff check backend/app/research/application/agent_runtime.py tests/research/test_agent_runtime_contract.py` | `All checks passed` |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py tests/research/test_agent_runtime_contract.py` | 通过 |
| `git diff --check -- backend/app/research/application/agent_runtime.py tests/research/test_agent_runtime_contract.py` | 通过 |
| 只读普通耗尽/provider 异常/取消后返回/安全与固定诊断探针 | 普通耗尽 4 次；provider 异常 false；取消后返回验证第二次调用确已成功返回 feedback；其余固定映射与脱敏通过 |

## 复审边界与接续

本报告只审查当前后端 diff，不把定向测试通过冒充真实 Ollama E2E、部署成功或 Spec032
收口。代码级复审已通过；真实 provider run、部署和 Spec032 全量验收仍由主会话按既有门禁
继续完成。发送事实（`feedback_sent`）与最终 run 终态（例如 `cancelled`）应在下游展示和
审计中分别解释，不应把前者当作模型理解或业务完成确认。

复审日志：`.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261011-193954-synthesis-contract-review.md`。
