# Report v3 budget and AgentRun diagnosis

Date: 2026-10-30  
Scope: read-only diagnosis of report v3 (`report_id=558d1fc6-5128-495b-942f-378b7d15e118`, Task `bdcd7fc185425e0f8443599e9cdbe8ec`, report version 3). No model call, database write, deployment, or budget change was made.

## Finding

The report did **not** exhaust its ResearchTask time budget. Its canonical failure projection records `task_totals.elapsed_seconds=380`, `max_seconds=1500`, `model_loops_used=12/160`, and `tool_calls_used=2/640`, leaving **1,120 seconds** at failure. The canonical row is `failed`, `published=false`, `output_disposition=not_run`, with `TASK_TIME_LIMIT_REACHED`; its persisted Markdown/HTML lengths are both zero and `report_content` is absent.

The failure happened inside the report stage's separate 120-second AgentRun grant. The report's persisted `store_state.claims` shows one comparison claim, requested and granted at 120 seconds. Comparison consumed that full grant; it never proceeded to drafting.

## Primary AgentRun evidence

Read directly from `/Users/wjh/ResearchAgent/data/research/research.sqlite3` through SQLite read-only mode. Only stable metadata, timestamps, usage counts, checkpoint key names, and safe validation diagnostic codes were selected; checkpoint output/body values were not inspected or emitted.

| Report version / stage | AgentRun provider and model | Elapsed | Result |
|---|---|---:|---|
| v2 comparison | `ollama` / `qwen3.5:9b` | 88 s | completed; a `MODEL_TIMEOUT` event was recorded after 30 s, then the stage completed |
| v2 drafting | `ollama` / `qwen3.5:9b` | 99 s | completed; a `MODEL_TIMEOUT` event was recorded after 30 s, then the stage completed |
| v3 comparison, original run | `ollama` / `qwen3.5:9b` | 108 s | `limit_reached`, stable code `AGENT_OUTPUT_INVALID`; safe diagnostic was `agent.output.structure` at `report_content` |
| v3 comparison, continuation attempt 3 | `ollama` / `qwen3.5:9b` | 12 s | `limit_reached`, `TASK_TIME_LIMIT_REACHED` |

For v3, a `MODEL_TIMEOUT` event occurs exactly 30 seconds after comparison started. The two persisted v3 run intervals total 108 + 12 = **120 seconds**, matching the claim. The recorded evidence establishes a client/runtime timeout followed by an invalid report-content structure and then exhaustion of the stage grant; it does not establish an upstream provider outage or HTTP failure. All observed v3 runs used the local Ollama provider and Qwen model, and no alternate-provider run is recorded. Canonical `generation.provider/model` remain null because no output was accepted.

There is no v3 drafting AgentRun. The prior v2 stage durations provide a same-task reference: comparison took 88 seconds and drafting 99 seconds, each completing after an initial 30-second timeout event. This shows the fixed 120-second stage grant leaves little margin for retries on the observed path.

## Contract and code check

The confirmed quality contract's effective time ceiling is `min(5400, ResearchTask.soft_budget_seconds)` and the balanced profile is 1,500 seconds. It requires the aggregate task usage to include historical and report-only AgentRuns; before a run, its duration must not exceed the remaining task budget. Per-run caps are 40 model loops and 160 tool calls. Neither this contract nor Task08/Task10 specifies a fixed 120-second allowance per comparison or drafting stage.

The report-only branches in `backend/app/research/application/orchestrator.py` request `min(120, int(progress["limits"]["max_seconds"]))` at comparison (line 6148) and drafting/revision (line 6346). The older natural-language synthesis grant uses the same 120-second request at line 2285. The store's atomic claim then clamps a requested grant by actual `remaining.seconds` and the task limit (`backend/app/research/infrastructure/research_store.py`, `claim_report_generation_budget`, around line 7854); the Orchestrator passes the resulting grant into `BudgetSnapshot.max_seconds`. Thus the 120-second value is an implementation policy, while the store remains the task-cap enforcement boundary.

## Minimal in-contract adjustment proposal

For comparison and drafting/revision, request a bounded stage allowance of `min(300, progress["remaining"]["seconds"])` after the existing exhausted-budget check. Keep the existing atomic store claim and use only its returned grant to construct `BudgetSnapshot`. This would request up to 300 seconds for a stage when available, but a smaller actual task remainder still wins; it neither clears prior usage nor raises the task's 1,500-second ceiling. It is compatible with the contract because each run remains below the durable remaining budget and the existing 40/160 per-run and 160/640 task loop/call caps stay unchanged.

The proposed 300-second stage cap is an implementation choice, not a contract requirement. It gives the observed 88–99 second successful stages room for retries while still preserving the shared task budget. No production change is included in this diagnosis.
