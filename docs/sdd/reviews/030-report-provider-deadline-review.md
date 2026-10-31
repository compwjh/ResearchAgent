# Spec 030 Task 08 Provider Deadline Review

日期：2026-10-29  
角色：Backend Reviewer  
范围：`backend/app/research/application/agent_runtime.py`、`backend/app/platform/ollama.py`、`tests/research/test_agent_runtime_request_timeout.py` 及既有模型分发/Runtime 合同测试。

## 结论

**PASS（当前 ResearchService 线程池执行路径）；有 2 项 MEDIUM 边界问题待收敛。** 没有发现总预算可被普通异步 provider 调用或 SDK 自动重试突破的路径。ResearchService 的 orchestration 与恢复由其线程池执行，符合当前同步 Runtime/adapter 的调用契约。两个边界反例分别涉及直接从 asyncio callback 同步调用 adapter、以及 provider 无视取消并迟到到整个 run cap 后的终态投影。

## 发现

### [MEDIUM] 纯 asyncio loop callback 未被识别为运行中的事件循环

文件：[agent_runtime.py:1265](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:1265)、[test_agent_runtime_request_timeout.py:194](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_agent_runtime_request_timeout.py:194)

adapter 只调用 `sniffio.current_async_library()` 判断是否已位于异步上下文。sniffio token 在 async task 内存在，但普通 `asyncio` loop callback 不一定有该 token。独立探针通过 `loop.call_soon(adapter.invoke)` 复现：代码随后调用 `anyio.run(...)`，抛出裸 `RuntimeError: Cannot run the event loop while another loop is running`，并产生 `invoke_with_deadline` 与 `shutdown_asyncgens` 未 await 警告；provider 没有被调用。现有测试只在 `anyio.run(async_fn)` 的 task 上下文中调用同步入口，未覆盖 loop callback。

建议在创建 deadline coroutine 之前通过 `asyncio.get_running_loop()` 做线程级检测，并统一抛 `AgentRuntimeError("MODEL_EXECUTION_CONTEXT_INVALID")`。当前 `ResearchService` 线程池路径不触发此问题；若 Runtime/adapter 被其他 async 服务直接调用，该路径会暴露不稳定错误和 coroutine 警告。

### [MEDIUM] late return 耗尽 cap 后仍把未调用的 fallback 投影为实际 provider

文件：[agent_runtime.py:2680](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2680)、[agent_runtime.py:2688](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2688)、[agent_runtime.py:2704](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2704)

Runtime 在 provider 返回后识别到请求超时，会抛 `MODEL_TIMEOUT`。异常分支先构建并选中 online fallback、设置 `fallback_attempted=True`，之后才在下一轮检查 run 的剩余预算。独立探针让本地 provider 在 90 秒请求 grant 后迟到至 120 秒 run cap：Runtime 返回 `limit_reached/TASK_TIME_LIMIT_REACHED`，且没有发起 fallback 请求，但 metadata 显示 `provider=deepseek`、`fallback_attempted=true`；model loop 计数为 1。总预算没有超出，不过结果把未运行的 provider 报成实际 provider。

建议在构建或切换 fallback 前先检查累计剩余预算，并只在 fallback provider 调用真正开始后报告其实际 provider/attempt 状态。正常 `anyio.fail_after` 会在 90 秒 grant 处取消合作式异步请求，因此反例要求底层调用无视取消或处于不受 adapter deadline 控制的同步注入路径；该修正可让防御性 late-return 分支的审计投影保持准确。

## 通过证据

- `anyio.fail_after` 包围底层 `ainvoke`；到期后在同一事件循环清理每次调用的 async client。无限 token stream 探针确认请求被取消、local 与 fallback client 各关闭一次。
- local Ollama 每次请求以本次 grant 重建 client，timeout 同时传给 async/sync/client 配置。已注册 online alias 使用 `ChatOpenAI(timeout=grant, max_retries=0)`，避免 SDK 内部重试放大 Runtime grant。
- fallback 可用时 local 请求预留 `min(30s, 25%)`；fake-clock late-return 探针确认主调用迟到 0.01 秒后被拒，fallback 只执行一次并获得剩余 29.99 秒，耗时从原 run 累计，provider metadata 投影为 `deepseek`。
- fallback 自身耗尽 grant 的测试返回 `TASK_TIME_LIMIT_REACHED`；已有 elapsed 达 cap 的测试在调用模型前直接停止。
- 定向测试、静态检查与编译结果见下表。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_agent_runtime_request_timeout.py tests/research/test_online_model_dispatch.py tests/research/test_research_agent_approval_contract.py tests/research/test_agent_runtime_contract.py` | 0 | `106 passed in 2.39s` |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/agent_runtime.py backend/app/platform/ollama.py tests/research/test_agent_runtime_request_timeout.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py backend/app/platform/ollama.py tests/research/test_agent_runtime_request_timeout.py` | 0 | 通过 |
| 独立 fake-clock late-return / cap probe | 0 | 超时拒绝、单次 fallback 与总预算通过；cap 耗尽时复现 fallback 投影误报 |
| 独立 asyncio loop-callback probe | 0（探针成功复现） | 观测到裸 RuntimeError 和未 await coroutine 警告；provider 未调用 |

## Review Summary

| Severity | Count | Status |
|----------|------:|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 2 | follow-up |
| LOW | 0 | note |

**Verdict: PASS with two MEDIUM follow-ups for the supported worker-pool path.**

进展日志：[20261029-provider-deadline-review.md](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/.codebuddy/agent-logs/spec-030/task-08/backend-reviewer/20261029-provider-deadline-review.md)

## Follow-up review — 2026-10-30

**Current verdict: PASS.** Both MEDIUM findings from the 2026-10-29 review are resolved in the frozen implementation; no remaining blocker was found in the requested deadline boundary.

- **Asyncio callback guard:** [agent_runtime.py:1268](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:1268) calls `asyncio.get_running_loop()` before defining or creating the deadline coroutine, and raises `MODEL_EXECUTION_CONTEXT_INVALID` when a loop is active. The regression at [test_agent_runtime_request_timeout.py:216](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_agent_runtime_request_timeout.py:216) invokes the synchronous adapter from `loop.call_soon`, then verifies the stable error, zero provider calls, and no unawaited-coroutine warning.
- **Full-cap late return:** [agent_runtime.py:2693](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2693) checks the exhausted run budget before building an online fallback. The regression at [test_agent_runtime_request_timeout.py:248](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_agent_runtime_request_timeout.py:248) verifies no fallback factory call, no `fallback_attempted` metadata, and the original Ollama provider/model projection. An independent probe also intercepted `_fallback_event`; it observed no event, no fallback factory call, `limit_reached/TASK_TIME_LIMIT_REACHED`, and retained `provider=ollama`.

| Command | Exit code | Result |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_agent_runtime_request_timeout.py::test_adapter_rejects_asyncio_loop_callback_before_creating_coroutine tests/research/test_agent_runtime_request_timeout.py::test_provider_return_after_full_grant_does_not_construct_fallback` | 0 | `2 passed in 0.61s` |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_agent_runtime_request_timeout.py tests/research/test_online_model_dispatch.py tests/research/test_research_agent_approval_contract.py tests/research/test_agent_runtime_contract.py` | 0 | `108 passed in 2.54s` |

本次只复核上述两个边界和受影响的定向测试；未运行全量测试、部署或真实报告生成。

## Follow-up review — 2026-10-30 fallback reserve ratio

**Current verdict: PASS.** The fallback reserve change preserves the run's existing total grant. It reserves up to 90 seconds or 75% of the *currently remaining* time only when fallback is configured and resolvable; without fallback, the local provider retains the full remaining allowance. The 120-second case now gets local 30s + online 90s, matching the requested priority.

- [agent_runtime.py:57](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:57) and [agent_runtime.py:58](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:58) set the reserve maximum/ratio to 90s/75%. At [agent_runtime.py:2667](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2667), request timeout starts as the full remaining run grant; only a viable fallback path subtracts the reserve at [agent_runtime.py:2676](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2676).
- Exact regressions verify 120s → local 30s + online 90s, an 80s remainder → local 20s + online 60s, and disabled/unconfigured fallback → local 120s. The primary+fallback timeout case sums to the same 120s cap. A separate 8s-grant probe produced local 2s + online 6s; the actual fake-clock runtime elapsed 3s and remained below its cap.
- The full-cap late-return regression still verifies that a result arriving after the run grant is rejected before fallback construction; model output is not accepted and provider metadata remains the original local model.

**Non-blocking scheduling precision limit:** the existing 1ms minimum request-timeout floor can exceed a remaining allowance below 4ms when the 75% reserve is active. A controlled 1s-run probe with 0.5ms remaining configured a 1ms local request and returned `limit_reached` at 1.0005s. This is a sub-millisecond wall-clock overrun; the late result was rejected, its elapsed time counted, and no fallback was constructed or invoked. Per root's acceptance, this is recorded as a scheduling-precision limitation and does not block the report-generation deployment.

| Command | Exit code | Result |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_agent_runtime_request_timeout.py::test_provider_timeout_uses_run_grant_and_reserves_existing_fallback_time tests/research/test_agent_runtime_request_timeout.py::test_shorter_remaining_grant_splits_proportionally_without_exceeding_cap tests/research/test_agent_runtime_request_timeout.py::test_disabled_fallback_gets_all_remaining_run_time tests/research/test_agent_runtime_request_timeout.py::test_primary_and_fallback_timeout_stop_at_the_same_run_grant tests/research/test_agent_runtime_request_timeout.py::test_provider_return_after_full_grant_does_not_construct_fallback` | 0 | `5 passed in 0.55s` |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_agent_runtime_request_timeout.py tests/research/test_online_model_dispatch.py tests/research/test_research_agent_approval_contract.py tests/research/test_agent_runtime_contract.py` | 0 | `110 passed in 2.39s` |
| Independent 8s-grant split probe | 0 | 2s local + 6s fallback; configured grants sum to 8s |
| Independent sub-4ms remainder probe | 0 | 0.5ms remainder rounded to 1ms request; late output rejected at 1.0005s; no fallback |

本次仅复核 reserve 比例、无 fallback 兼容、预算守恒和小 grant 行为；未重审其它已通过实现，也未运行全量测试、部署或真实报告生成。

## Follow-up review — 2026-10-30 report-stage grant and schema-retry deadline

**Current verdict: PASS.** The report stages now request up to 300 seconds, bounded by the reservation's remaining seconds; this is a per-stage claim request, not a new task cap. The confirmed quality contract limits cumulative seconds by the task's effective soft/profile budget and carries prior AgentRun usage forward; it does not impose a 120-second per-stage ceiling. The store independently clamps each claim against the durable remaining amount and existing task limit.

- [orchestrator.py:6140](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:6140) and [orchestrator.py:6340](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:6340) request `min(300, int(remaining_seconds))` for comparison and drafting/revision. A zero-second result stops before creating a claim. Each subsequent stage re-reads durable progress, so spent time reduces the next request.
- [research_store.py:7854](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/infrastructure/research_store.py:7854) clamps granted seconds to requested seconds, durable remaining seconds, and the effective task cap. `_collect_report_generation_usage` includes settled AgentRun durations, active claims, and preserved prior totals when computing remaining time.
- [agent_runtime.py:2670](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2670) recomputes remaining run time before each model invocation. Schema retries stay inside the same AgentRun loop and use the same `start` and granted `max_seconds`; an output that arrives after the grant is rejected.
- When an online fallback is available, the existing split uses `min(30s, remaining * 25%)` for the primary and leaves the rest for the one fallback. Tests cover 300s → 30s + 270s, 120s → 30s + 90s, and 80s → 20s + 60s; with fallback disabled the primary receives all remaining time. The budget regression seeds a durable 87s remainder and asserts successive claim requests of 87s and 86s as one-second fake AgentRuns settle, with 85s remaining afterward.
- No new budget extension, task cap increase, or claim per schema retry was found. Sub-second integer rounding is conservative at the stage-claim boundary; the prior non-blocking provider scheduling precision note remains applicable to sub-millisecond request timeout floors.

| Command | Exit code | Result |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_agent_runtime_request_timeout.py tests/research/test_report_quality_context.py -q` | 0 | `55 passed in 6.11s` |

本轮只复核阶段预算请求、store 夹限、fallback 分配和同一 run 的 schema 重试 deadline；未运行全量测试、部署或真实报告生成。

## Follow-up review — 2026-10-30 paper ID feedback, fallback metadata, and settlement snapshot

**Current verdict: PASS.** No high-confidence blocker found in the frozen backend implementation. Scope was limited to `backend/app/research/application/agent_runtime.py`, `backend/app/research/infrastructure/research_store.py`, and the three changed backend tests.

- **Synthesis finding paper IDs:** the prompt states that each `synthesis_findings[].paper_ids` must be a 2–64 item array of distinct IDs copied from `selected_paper_ids`, and forbids evidence IDs/titles ([agent_runtime.py:471](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:471)). Runtime still passes output through the existing shape validator and selected-paper reference validator ([agent_runtime.py:2344](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2344), [agent_runtime.py:2364](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2364)); the unchanged `_id_array` continues to enforce array bounds and uniqueness, and findings must remain within the selected set. Retry feedback is constructed from the fixed field path, fixed rule text, and validated selected IDs only ([agent_runtime.py:638](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:638)); the regression confirms the rejected ID and source excerpt are absent ([test_report_content_runtime.py:221](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_report_content_runtime.py:221)).
- **Fallback provider/model metadata:** each fallback transition records the instantiated model's provider, model name, and reasoning effort through the running-generation CAS helper ([agent_runtime.py:1865](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:1865), [agent_runtime.py:2829](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2829), [agent_runtime.py:3121](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:3121)). Regressions cover successful fallback and a fallback chain that ultimately fails output validation while retaining DeepSeek metadata ([test_agent_runtime_request_timeout.py:123](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_agent_runtime_request_timeout.py:123), [test_agent_runtime_request_timeout.py:159](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_agent_runtime_request_timeout.py:159)).
- **Settlement and published immutability:** settlement uses `BEGIN IMMEDIATE`, marks the claim settled at most once, derives usage from persisted AgentRun rows, and writes the claim state plus budget snapshot under one transaction ([research_store.py:7940](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/infrastructure/research_store.py:7940), [research_store.py:7981](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/infrastructure/research_store.py:7981), [research_store.py:7992](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/infrastructure/research_store.py:7992)). Non-generating reports return without a report write ([research_store.py:7975](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/infrastructure/research_store.py:7975)); concurrent duplicate, failed replay, and published Artifact/terminal Task preservation are covered ([test_report_generation_state.py:418](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_report_generation_state.py:418), [test_report_generation_state.py:488](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_report_generation_state.py:488)).

### Verification evidence

The implementation author recorded these results after the final candidate; this reviewer did not rerun them:

| Command | Exit code | Result |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/research/test_report_content_runtime.py tests/research/test_agent_runtime_request_timeout.py tests/research/test_report_generation_state.py tests/research/test_report_generation_budget_recovery.py -q` | 0 | 75 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/agent_runtime.py backend/app/research/infrastructure/research_store.py tests/research/test_report_content_runtime.py tests/research/test_agent_runtime_request_timeout.py tests/research/test_report_generation_state.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py backend/app/research/infrastructure/research_store.py tests/research/test_report_content_runtime.py tests/research/test_agent_runtime_request_timeout.py tests/research/test_report_generation_state.py` | 0 | Passed |

No full regression, model call, database mutation, deployment, or Git operation was performed in this review.

## Follow-up review — 2026-10-31 natural-language count marker narrowing

**Current verdict: BLOCK — one HIGH regression requires a narrow correction and re-review.** Scope was limited to `session_plan_generation.py`, `test_intake_plan_repair.py`, `test_research_intake_contract.py`, and the supplied natural-language Intake artifact.

### [HIGH] Unsupported explicit paper counts can now disappear and use the default

File: [session_plan_generation.py:61](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/session_plan_generation.py:61)

The narrowed `_COUNT_QUANTITY_MARKER` requires an Arabic digit immediately after its recognized optional words, followed by a paper unit ([session_plan_generation.py:64](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/session_plan_generation.py:64)). The supported count patterns likewise parse only Arabic digits and do not include the common connector `要` ([session_plan_generation.py:33](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/session_plan_generation.py:33), [session_plan_generation.py:47](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/session_plan_generation.py:47)). Consequently, explicit forms such as `最多五篇论文` and `至少要选5篇论文` match neither a count pattern nor an unresolved marker. `extract_paper_count_constraints` then returns no constraint, so the planner can apply the default of 12 ([test_intake_plan_repair.py:90](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_intake_plan_repair.py:90)).

The pre-change broad marker would route these unsupported explicit quantities to clarification. The new change correctly fixes the observed false positive where `至少1500个中文字符，逐篇分析` was misread as a paper-count marker, but it must retain fail-closed clarification for explicit quantities the parser does not support. This also follows the function contract that an unparseable count marker must not silently fall back to the profile default ([session_plan_generation.py:99](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/session_plan_generation.py:99)). Add narrow regressions for unsupported explicit count forms and retain the character-length regression; no Chinese-number parser is required if they instead remain in clarification.

The supplied pre-fix request and Intake event confirm the original defect: the request includes target/minimum 5 and a 1,500-character body; the event persists `paper_count_constraint:unparsed` and asks for paper-count clarification despite both explicit paper-count values ([request.json](</Users/wjh/.codex/worktrees/map-usability/ResearchAgent/docs/sdd/plans/030/artifacts/20261031-natural-e2e/request.json>), [01-intake.sse:5](</Users/wjh/.codex/worktrees/map-usability/ResearchAgent/docs/sdd/plans/030/artifacts/20261031-natural-e2e/01-intake.sse:5>)). The new tests cover that false positive through both extraction and Intake, plus the existing oversize and conflicting-count paths, but do not cover the unsupported explicit forms above ([test_intake_plan_repair.py:114](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_intake_plan_repair.py:114), [test_research_intake_contract.py:140](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_research_intake_contract.py:140)).

### Verification evidence

The author reported `2 RED → 27 GREEN`, Ruff, compile, and test-layout checks passing for the candidate; this reviewer did not rerun them. Those results validate the intended regression fix but do not cover the HIGH edge above. No model, deployment, or full regression was run in this review.

### Re-review — 2026-10-31 explicit count connector correction

**Current verdict: PASS.** This re-review supersedes the preceding BLOCK for the frozen count-parser slice. Both the numeric count parser and unresolved marker now accept the optional Chinese `要/需要` connector before the selection verb ([session_plan_generation.py:40](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/session_plan_generation.py:40), [session_plan_generation.py:48](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/session_plan_generation.py:48), [session_plan_generation.py:72](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/session_plan_generation.py:72)). The exact regression `至少要选5篇论文` resolves to `min_paper_count:5`, while retaining the 1,500-character phrase without a false paper-count marker ([test_intake_plan_repair.py:144](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_intake_plan_repair.py:144)). Unsupported Chinese and English word counts still produce the existing `paper_count_constraint:unparsed` clarification marker ([test_intake_plan_repair.py:126](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_intake_plan_repair.py:126)). No regression was found in the previously reviewed character-length boundary or word-count clarification cases.

The author recorded `29 passed` for the two focused Intake test files, with Ruff and compile checks passing; this reviewer did not rerun those checks. `git diff --check` passed for the reviewed changes. No full regression, model call, or deployment was performed.

## Follow-up review — 2026-10-31 topic-aware search and evaluator selection

**Current verdict: BLOCK — one HIGH durable-selection bypass remains.** Scope was limited to the frozen four application files and five specified evaluator/selection tests. The query/objective split is correctly implemented: Intake topic is passed separately and used only as the search seed, while the plan goal remains the original objective ([session_plan_generation.py:225](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/session_plan_generation.py:225), [planner.py:208](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/planner.py:208), [planner.py:222](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/planner.py:222)); the new plan test verifies both sides of that contract ([test_plan_topic_search_queries.py:18](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_plan_topic_search_queries.py:18)). The strict candidate normalizer also requires an individual keep/score decision, threshold passage, recall membership, and that candidate's own catalog reference ([orchestrator.py:377](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:377), [orchestrator.py:390](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:390)).

### [HIGH] Memory-backed post-run selection re-expands aggregate refs without the strict threshold

Files: [orchestrator.py:2163](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:2163), [orchestrator.py:2868](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:2868)

The synthesizer path correctly calls `_validated_evaluator_candidates(..., relevance_threshold=evaluator_threshold)`. If that rejects every aggregate-only response, it marks `NO_VALIDATED_EVIDENCE` and continues before assigning `synthesis_validated_candidates` ([orchestrator.py:2187](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:2187)). Later, when `_memory_repository` is present, the post-run projection reconstructs candidates from raw `evaluator_outputs` without passing `relevance_threshold` ([orchestrator.py:2850](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:2850), [orchestrator.py:2868](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:2868)). That legacy mode expands aggregate `catalog:<id>` refs. With five recalled IDs, the report-floor branch then persists them without a strict threshold ([orchestrator.py:2945](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:2945)).

Shortest repro: run a session-backed orchestrator with a memory repository; have Search return five allowlisted IDs; have the evaluator return only `candidate_id=null` plus those five catalog refs and no per-paper decisions. The strict synthesis selection rejects the output, but the later memory-backed projection can persist all five IDs as selections. The current aggregate-only integration test sets `memory_repository=None`, so it verifies the strict failure/partial result while bypassing this projection ([test_agent_selection_persistence.py:314](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_agent_selection_persistence.py:314), [test_agent_selection_persistence.py:319](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_agent_selection_persistence.py:319)). This violates the frozen requirement that aggregate refs prove provenance only and cannot satisfy the five-paper floor. The legacy fallback should remain available only for genuinely legacy inputs; a strict session plan must not be re-expanded after its per-paper gate rejects the set.

### Verification evidence

The implementation author reported 184 focused tests passing, plus Ruff, compile, naming, layout, and 3,856-test collection checks. This reviewer did not rerun them. `git diff --check` passed for the reviewed files. No full regression, model call, database mutation, or deployment was performed.

### Re-review — 2026-10-31 memory-backed evaluator-selection projection

**Current verdict: PASS.** This re-review supersedes the preceding HIGH/BLOCK for the memory-backed post-run selection bypass. The raw-output post-run projection now invokes `_validated_evaluator_candidates` with the approved evaluator threshold, and its catalog supplement receives that same threshold ([orchestrator.py:2871](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:2871), [orchestrator.py:2880](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:2880), [orchestrator.py:2887](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:2887)). Any promoted row must itself carry a finite, in-range per-paper score, `keep=true`, and meet the threshold; the report floor cannot promote an unscored or below-threshold row ([orchestrator.py:306](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:306), [orchestrator.py:547](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:547), [orchestrator.py:554](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:554)). Strict persistence also requires a direct per-paper ID, passing score, that paper's own catalog ref, and recall allowlisting; it no longer expands refs in strict mode ([orchestrator.py:3358](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:3358), [orchestrator.py:3364](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:3364), [orchestrator.py:3398](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:3398)). The normal planner and replan path each create one evaluator WorkItem, so the applied threshold is that WorkItem's persisted threshold ([planner.py:236](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/planner.py:236), [orchestrator.py:3728](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:3728)). Legacy calls that omit a threshold retain their prior aggregate behavior.

The new memory-backed fake-runner regression exercises both aggregate-only high-score refs and five explicit per-paper `.19` scores against the `.2` threshold. With a non-null `MemoryRepository`, both cases now finish partial with `selected_count == 0` and no durable selections ([test_agent_selection_persistence.py:335](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_agent_selection_persistence.py:335), [test_agent_selection_persistence.py:392](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_agent_selection_persistence.py:392), [test_agent_selection_persistence.py:400](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_agent_selection_persistence.py:400)). Existing query/objective separation and strict candidate allowlist coverage remain intact in the scoped changed tests.

### Verification evidence

| Command | Exit code | Result |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_agent_selection_persistence.py tests/research/test_report_catalog_metadata.py tests/research/test_validated_evaluator_candidates.py tests/research/test_plan_topic_search_queries.py` | 0 | 34 passed in 1.33s (independently rerun) |
| `git diff --check -- backend/app/research/application/orchestrator.py backend/app/research/application/planner.py tests/research/test_agent_selection_persistence.py tests/research/test_report_catalog_metadata.py tests/research/test_validated_evaluator_candidates.py tests/research/test_plan_topic_search_queries.py` | 0 | Passed |
| Author's scoped backend domain suite | 0 (reported) | 95 passed; Ruff, compile, and test-layout checks reported passing; not rerun here |

No full regression, model call, deployment, or Git operation was performed in this review.

## Follow-up review — 2026-10-31 bounded safety diagnostics

**Current verdict: PASS for the diagnostic-plumbing slice.** The original safety rejection conditions remain intact: forbidden/prompt/URL/executable key checks, URL and credential-value checks, 32 top-level scope fields, 64 nested fields/list entries, depth limit 6, and 4,000-character string limit are unchanged. The new `PlanOutputInvalid` metadata contains only a closed classification and schema-derived path segments; unsupported/dynamic keys collapse to `unknown`, arrays to `[]`, and generated paths are limited to 256 characters ([plan_authoring.py:42](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/plan_authoring.py:42), [plan_authoring.py:97](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/plan_authoring.py:97), [plan_authoring.py:119](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/plan_authoring.py:119), [plan_authoring.py:124](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/plan_authoring.py:124), [plan_authoring.py:146](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/plan_authoring.py:146)). Existing rejection messages remain fixed strings; the runtime catches the safety error without chaining it and revalidates both path and classification against its own allowlists before exposing diagnostic or retry feedback ([agent_runtime.py:577](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:577), [agent_runtime.py:591](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:591), [agent_runtime.py:2310](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:2310), [agent_runtime.py:654](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:654), [agent_runtime.py:713](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:713)).

The path and classification propagated to model feedback and checkpoint/event diagnostics remain bounded metadata only. Event persistence now permits the nested classification field while retaining the existing key filter, depth limit, 64-entry list cap, and 1,000-character string cap ([research_store.py:116](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/infrastructure/research_store.py:116), [research_store.py:133](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/infrastructure/research_store.py:133)). Regressions cover forbidden dynamic keys, URL and credential values, oversized and deep input, and marker absence from exceptions, retry feedback, checkpoint metadata, and persisted event payloads ([test_agent_runtime_contract.py:740](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_agent_runtime_contract.py:740), [test_agent_runtime_contract.py:764](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_agent_runtime_contract.py:764), [test_agent_runtime_contract.py:779](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_agent_runtime_contract.py:779), [test_agent_runtime_contract.py:806](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_agent_runtime_contract.py:806), [test_agent_runtime_contract.py:836](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_agent_runtime_contract.py:836)). The evaluator prompt still requires individual `keep`/score decisions at the WorkItem threshold and explicitly describes a title-only decision as metadata-only, not abstract/full-text evidence ([agent_runtime.py:759](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:759), [test_research_agent_approval_contract.py:97](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_research_agent_approval_contract.py:97)). No new endpoint or persisted schema version was introduced ([research_store.py:101](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/infrastructure/research_store.py:101)).

This review verifies diagnostic plumbing only. The root cause of the reported real R2 safety rejection remains unknown; this change does not establish that the R2 false positive is fixed.

### Verification evidence

| Command | Exit code | Result |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_agent_runtime_contract.py::test_nested_unsafe_output_is_rejected_before_checkpoint tests/research/test_agent_runtime_contract.py::test_safe_scope_rejections_have_closed_classification_and_schema_paths tests/research/test_agent_runtime_contract.py::test_safe_scope_depth_rejection_uses_unknown_path_segments_without_echoing_keys tests/research/test_agent_runtime_contract.py::test_safety_classification_flows_to_retry_feedback_and_checkpoint_without_values tests/research/test_agent_runtime_contract.py::test_forbidden_dynamic_key_is_redacted_in_retry_feedback_and_checkpoint tests/research/test_agent_runtime_contract.py::test_safety_classification_persists_in_safe_event_projection tests/research/test_research_agent_approval_contract.py::test_ollama_adapter_evaluator_allows_title_only_catalog_evidence` | 0 | 11 passed in 0.77s (independently rerun) |
| `git diff --check -- backend/app/research/application/plan_authoring.py backend/app/research/application/agent_runtime.py backend/app/research/infrastructure/research_store.py tests/research/test_agent_runtime_contract.py` | 0 | Passed |
| Author's scoped suite and static checks | 0 (reported) | 114 tests; Ruff, compile, test-layout, and naming checks reported passing; not rerun here |

No full regression, model call, deployment, or Git operation was performed in this review.

## Follow-up review — 2026-10-31 test-only lint cleanup

**Current verdict: PASS.** The frozen diff is limited to `tests/research/test_report_content_rendering.py` and `tests/research/test_report_quality.py`. The two `zip` calls now state `strict=False` explicitly ([test_report_content_rendering.py:27](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_report_content_rendering.py:27), [test_report_content_rendering.py:105](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_report_content_rendering.py:105)); this preserves Python's prior default truncation behavior. No assertion, fixture data, import, or production code changed. The remaining edits only remove excess blank lines. No baseline route lint or frontend file was touched in this slice.

| Command | Exit code | Result |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_content_rendering.py tests/research/test_report_quality.py` | 0 | 30 passed in 0.80s (independently rerun) |
| `git diff --check -- tests/research/test_report_content_rendering.py tests/research/test_report_quality.py` | 0 | Passed |
| Author's two-file Ruff and test-layout/naming checks | 0 (reported) | Passed; not rerun here |

No production change, full regression, model call, or deployment was part of this review.
