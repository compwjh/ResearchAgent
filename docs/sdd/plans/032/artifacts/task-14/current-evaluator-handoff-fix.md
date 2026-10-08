# Spec032 Task14：evaluator handoff fix

状态：`LOCAL_FIX_VERIFIED / LIVE_RERUN_PENDING`

本轮按 backend-dev 范围处理 supported-effort 真实 E2E 的 evaluator handoff；只改
`backend/app/research/application/agent_runtime.py` 与对应 runtime 测试，未部署、未重跑旧 task、未写生产业务数据。

## 真实证据与根因

只读核对 `current-research-e2e-supported-effort-report.md`、其 evidence JSON 和
`data/research/research.sqlite3`（task `2761a22515d5509d8e846debd7a05df5`）得到：

1. 请求级模型是 `qwen3.5:9b`、`reasoning_effort=low`，Intake/plan 已批准
   `min=max=target=5`；5/5 acquisition import 完成。s1、s2 Search Worker 和 e1
   AgentRun 都记录为 `completed`。
2. s2 的冻结 WorkItem input 含 `source_ids=["usenix"]`、`sources=["usenix"]`，但其
   已持久化 search output 的 `source` 是
   `usenix-catalog-orchestration`（skill 名），不是批准的 source ID `usenix`。
   s1 的 source 为 `usenix`。
3. e1 WorkItem 行是 `completed`，`output_json` 为 `NULL`；对应
   `2761...:e1:run-1` AgentRun 是 `completed`，有非空 output hash、final checkpoint，
   checkpoint 中有真实 evaluator envelope：`candidate_id`、`evidence_refs`、`keep`、
   `relevance_score`、`reason`、`safe_summary`、`schema_version`、`source_refs`。
   candidate/ref 本身在 Search Worker 召回集合内；只读重放表明 allowlist 非空时该
   evaluator scope 可通过。
4. orchestrator 在 `orchestrator.py:1711-1732` 对非法 Search Worker source 清空
   evaluator candidate/ref/source allowlist，随后在 `:1981-1985` 将 e1 语义判为
   `EVALUATOR_EVIDENCE_OUT_OF_SCOPE`。这不是 low reasoning 的 JSON envelope/parser
   拒绝，也不是 SQLite 对合法 completed write-back 的一般性丢失。
5. AgentRunner 已先将 e1 WorkItem 置为 `completed`；orchestrator 后续在
   `orchestrator.py:2053-2061` 试图用 `completed -> failed` 写回结果。该转换被
   WorkItem 状态机拒绝，并被现有 `suppress(Exception)` 吞掉，故产生“completed 但
   output_json 缺失”。c1/syn 的 `UPSTREAM_WORK_ITEM_FAILED` 是正确的依赖阻断，未
   被本修复吞掉或改成硬继续。

另有一个独立观察：该真实请求的 AgentRun 行 `reasoning_effort` 是 `off`，而请求是
`low`；当前 orchestrator 构造 `AgentRunInput` 时仍在 `orchestrator.py:1909`
硬编码 `off`。本轮没有把这个独立 effort 传播契约误判为 evaluator handoff 根因，
也没有扩大范围修改模型/能力配置；它仍需单独的能力传播复核和真实 E2E 门禁。

## 先红灯，再最小修复

红灯（修复前）使用与真实形状一致的模型输出：`source=
usenix-catalog-orchestration`，WorkItem 唯一批准来源为 `usenix`：

```text
.venv/bin/python -m pytest -q tests/research/test_agent_runtime_search_handle.py -k 'approved_work_item_scope' --maxfail=1
退出码：1（实际 source 仍为 usenix-catalog-orchestration，断言期望 usenix）
```

修复位于 `ResearchAgentRunner._validate_output()`：

- 从 server-owned WorkItem 的 `source_ids` / `sources` / `source` 收集来源；仅当
  所有存在的字段解析为同一个严格 allowlist 值 `{usenix, dblp, all}` 时，才将
  search output 的展示/binding 字段规范化为该批准值。
- 未知、非字符串、冲突或多来源输入返回未绑定状态，交给既有 orchestrator
  allowlist 继续 fail-closed；不会猜来源。
- 正常验证与 search recovery 验证都走同一边界。候选 ID、`source_refs`、
  `evidence_refs`、claim/allowlist 校验没有放宽；没有从 Markdown、全局目录或模型
  输出补造证据。
- 未改变公开 JSON schema、数据库表、AgentRun 状态机、依赖失败传播、下载/报告
  第二套实现。

新增测试：

- `test_runtime_binds_search_source_to_approved_work_item_scope`：真实 skill-name
  形状绑定到唯一批准 source。
- `test_runtime_keeps_source_unbound_when_work_item_scope_conflicts`：冲突来源仍
  fail-closed。

## 定向验证（最终代码）

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_search_handle.py tests/research/test_agent_runtime_contract.py tests/research/test_agent_work_item_failure_visibility.py tests/research/test_agent_selection_persistence.py tests/research/test_research_agent_approval_contract.py tests/research/test_research_report_matrix_bridge.py --maxfail=1` | 0 | 93 passed |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_search_handle.py --maxfail=1` | 0 | 5 passed |
| `.venv/bin/ruff check backend/app/research/application/agent_runtime.py tests/research/test_agent_runtime_search_handle.py` | 0 | All checks passed |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| 冲突标记扫描（改动源码/测试/本报告） | 0 | 未发现 `<<<<<<<` / `=======` / `>>>>>>>` |
| 只读 SQLite 形状查询（`sqlite3 -readonly`） | 0 | 复核 s2 source、e1 NULL output、AgentRun checkpoint/hash |

未运行全量 pytest、未启动/部署服务、未执行新生产 E2E；因此必须用含本修复的
全新服务运行验证 s2 durable output source、e1 output_json、c1/syn 正常派发及最终
report/matrix，不能把本地定向测试当作 E2E 成功。

## P0/P1 与部署结论

- P0：`0`。
- P1（本轮根因）：Search Worker 将 skill 名泄漏为 source，导致真实 evaluator
  allowlist 被清空并触发 completed→failed 写回冲突；已在本地以红灯/绿灯修复，
  但 live rerun 尚未完成。
- P1（独立未结项）：请求 `low` 与 AgentRun 持久化 `off` 的 effort 传播差异未在
  本轮修改或证明与 handoff 失败有因果关系。
- 结论：代码定向验证通过，但当前不能宣称 Spec032 E2E 可部署/可验收；须先由
  独立 reviewer 复审，再在新 run 中验证真实 WorkItem output_json、依赖阶段和
  matrix/report 产物。不得重试或改写旧 task 以冒充成功。

交接日志：`.codebuddy/agent-logs/spec-032/task-14/backend-dev/20261009-live-matrix-fix.md`

## Independent review remediation — source binding and terminal handoff (2026-10-09 05:50 +0800)

The independent review identified two P1s in the preceding local fix. Both were
reproduced with focused red tests before changing the implementation:

```text
.venv/bin/python -m pytest -q tests/research/test_agent_runtime_search_handle.py -k 'approved_work_item_scope or unbound_search_source' --maxfail=1
exit 1  # dblp/unknown were previously overwritten to usenix

.venv/bin/python -m pytest -q tests/research/test_agent_work_item_completion.py --maxfail=1
exit 1  # completed+NULL, semantic failure hidden, and terminal write failure suppressed
```

### P1-1: fail-closed source provenance

`ResearchAgentRunner._validate_output()` now accepts a search source only when it
is the exact unique server-owned source ID from the WorkItem scope, or the exact
registered skill alias for that approved source. The only current alias is
`usenix-catalog-orchestration -> usenix`; the alias must also equal the actual
bound skill snapshot name. `dblp`, `unknown`, arbitrary labels, invalid source
types, and conflicting/ambiguous WorkItem source fields raise the existing
`AGENT_OUTPUT_INVALID` path. No candidate, source-reference, locator, or
evaluator allowlist was widened, and the sourceagent's recovery hydration was
left untouched.

### P1-2: terminal output persistence invariant

`ResearchAgentRunner` still durably completes the AgentRun, but leaves the
WorkItem running when the AgentRun status is `completed`; the orchestrator now
owns the WorkItem terminal commit. It performs the existing role/provenance
semantic checks first, rejects a non-mapping completed output, serializes the
bounded AgentRun envelope, and then calls the existing store transaction to
write the terminal WorkItem status and `output_json`. Semantic-invalid output
therefore transitions directly from running to failed with a durable completed
AgentRun envelope; it never performs completed-to-failed reopening. Terminal
serialization/store failures are no longer wrapped in broad `suppress(Exception)`
and remain observable. No public schema/API/table or second state machine was
introduced.

The completion regression suite covers:

- AgentRunner completed result leaves WorkItem `running` with no output until
  orchestrator write-back;
- evaluator scope failure yields WorkItem `failed` with
  `EVALUATOR_EVIDENCE_OUT_OF_SCOPE` and a durable envelope;
- terminal output persistence failure propagates and leaves the WorkItem
  non-terminal with no payload;
- exact approved source, registered skill alias, conflicting scope, `dblp`, and
  `unknown` source shapes.

Final focused verification:

| Command | Exit | Result |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_work_item_completion.py --maxfail=1` | 0 | 3 passed |
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_search_handle.py tests/research/test_agent_runtime_contract.py tests/research/test_agent_work_item_completion.py tests/research/test_work_item_output_recovery.py tests/research/test_agent_work_item_failure_visibility.py --maxfail=1` | 0 | 51 passed |
| `.venv/bin/python -m pytest -q tests/research/test_agent_selection_persistence.py tests/research/test_research_agent_approval_contract.py tests/research/test_research_report_matrix_bridge.py --maxfail=1` | 0 | 52 passed |
| `.venv/bin/ruff check` on changed runtime/orchestrator and focused tests | 0 | All checks passed |
| `.venv/bin/python -m py_compile` on changed runtime/orchestrator and focused tests | 0 | Passed |
| `git diff --check` | 0 | Passed |

P0 remains `0`. The two reviewed local P1s are fixed and the focused backend
checks pass. This is still `LOCAL_FIX_VERIFIED / LIVE_RERUN_PENDING`: no service
was deployed, no old task was retried or rewritten, and the real runtime must
still verify fresh WorkItem output, dependency propagation, matrix, and report
artifacts before any deployment/acceptance claim.

## Completion review follow-up — invalid AgentRun cannot be promoted by recovery (2026-10-09 06:08 +0800)

The latest completion review found a remaining path after the earlier fix:
`AgentRunOutput(status="completed", output_json=None)` was first converted to
the failed branch, but the orchestrator then called its adapter recovery helper,
changed the WorkItem back to `completed`, and serialized the original result.
The resulting row was `completed` with an inner `output_json=null`. A focused
probe reproduced this before the change:

```text
.venv/bin/python -m pytest -q tests/research/test_agent_work_item_completion.py -k 'search_recovery or terminal_output' --maxfail=1
exit 1  # null completed result was promoted by a non-null controlled recovery
```

The orchestrator no longer promotes a separate adapter result. Search recovery
is a valid success only inside `ResearchAgentRunner`, where the same controlled
tool result is output-validated, provenance-bound, hashed, checkpointed, and
persisted against the real AgentRun before that AgentRun can complete. Once an
`AgentRunOutput` reaches the orchestrator, it must use that exact result for the
WorkItem envelope. If its output is absent/invalid, or its status is failed,
the WorkItem remains failed with the existing failure envelope; no synthetic
successful AgentRun, hash, source handle, or completed WorkItem is created.
This also covers all fallback branches and does not reopen a terminal row. The
sourceagent's hydration hash/AgentRun checks remain unchanged and therefore
continue to accept only genuinely persisted runtime output.

New regression coverage includes:

- a non-null controlled recovery returned beside an original null completed
  result, which must end as `failed/AGENT_OUTPUT_INVALID` with no completed
  WorkItem;
- a valid non-null completed Search AgentRun, which must not invoke the
  orchestrator recovery helper and must persist the returned output unchanged;
- the existing terminal store failure probe, which verifies the WorkItem stays
  non-terminal with no payload when the terminal transaction fails.

Final focused verification:

| Command | Exit | Result |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_work_item_completion.py -k 'search_recovery or terminal_output' --maxfail=1` | 0 | 2 passed |
| `.venv/bin/python -m pytest -q tests/research/test_agent_work_item_completion.py --maxfail=1` | 0 | 5 passed |
| `.venv/bin/python -m pytest -q tests/research/test_agent_work_item_completion.py tests/research/test_agent_runtime_search_handle.py tests/research/test_agent_runtime_contract.py tests/research/test_work_item_output_recovery.py tests/research/test_agent_work_item_failure_visibility.py --maxfail=1` | 0 | 59 passed |
| `.venv/bin/python -m pytest -q tests/research/test_agent_selection_persistence.py tests/research/test_research_agent_approval_contract.py tests/research/test_research_report_matrix_bridge.py --maxfail=1` | 0 | 52 passed |
| `.venv/bin/ruff check` on changed runtime/orchestrator and focused tests | 0 | All checks passed |
| `.venv/bin/python -m py_compile` on changed runtime/orchestrator and focused tests | 0 | Passed |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `git diff --check` | 0 | Passed |

P0 remains `0`; the residual completion P1 is locally fixed. This remains
`LOCAL_FIX_VERIFIED / LIVE_RERUN_PENDING`: no deployment, full regression,
production write, or retry of the historical task was performed. Fresh runtime
E2E and independent review are still required before deployment/acceptance.

## Completion review follow-up — server WorkItem identity before runtime persistence (2026-10-09 06:30 +0800)

The next completion review found that Search output identity was still being
canonicalized only in orchestrator memory. A model response containing
`work_item_id="modelowned"` could therefore reach a completed AgentRun with a
non-canonical inner identity, while the orchestrator's old temporary rewrite
made the current WorkItem appear correct. That breaks the durable hash,
checkpoint, AgentRun, and restart-hydration binding invariant.

The focused runtime probe was red before the change:

```text
.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py \
  -k 'binds_server_work_item_id or conflicting_task_identity' --maxfail=1
exit 1  # completed output retained modelowned / non-search roles lacked the binding
```

The runtime boundary now receives the server-owned identities explicitly. For
every non-planner role, it binds `work_item_id` to the `AgentRunInput` value
before role normalization, output hash, checkpoint creation, and AgentRun
counter persistence. Optional `research_task_id`, `research_session_id`, and
`owner_id` claims are never rewritten: if present and conflicting with the
server input, validation returns `AGENT_OUTPUT_INVALID`. The system prompt
also gives the model the exact server `work_item_id` and instructs it to return
that value unchanged. Search handle/degradation normalization refreshes the
inner output digest once more before the checkpoint, so inner output hash,
returned hash, checkpoint, and persisted AgentRun agree.

The orchestrator no longer performs a temporary Search identity rewrite. Its
restart hydration passes the expected server identities to the same runtime
validator; it accepts only a genuinely persisted canonical envelope and real
owner/session/task/work-item-bound AgentRun. No new hash algorithm, AgentRun,
schema, API, table, or recovery state machine was introduced.

The fresh-to-restart regression performs the complete local shape: an actual
`ResearchAgentRunner` sees model-owned identity, persists a completed AgentRun
with canonical WorkItem ID and matching output hash, the existing store writes
the terminal WorkItem envelope, and a new Orchestrator instance hydrates it
without invoking the runner again. The positive restart path and conflict
fail-closed paths are now covered for all runtime roles.

Final focused verification:

| Command | Exit | Result |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py tests/research/test_agent_runtime_search_handle.py tests/research/test_agent_work_item_completion.py tests/research/test_work_item_output_recovery.py tests/research/test_agent_work_item_failure_visibility.py tests/research/test_research_agent_approval_contract.py tests/research/test_agent_selection_persistence.py tests/research/test_research_report_matrix_bridge.py --maxfail=1` | 0 | 120 passed |
| `.venv/bin/ruff check` on changed runtime/orchestrator and focused tests | 0 | All checks passed |
| `.venv/bin/python -m py_compile` on changed runtime/orchestrator and focused tests | 0 | Passed |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `git diff --check` | 0 | Passed |

P0 remains `0`; the identity-binding completion P1 is locally fixed. This is
still `LOCAL_FIX_VERIFIED / LIVE_RERUN_PENDING`: no deployment, full regression,
production write, or historical-task retry was performed. Fresh real service
E2E and independent review remain required before deployment/acceptance.
