# Spec 030 Task 08 — report generation state and budget store handoff

Date: 2026-10-29
Role: backend-dev
Status: bounded store slice implemented; independent review belongs to the parent orchestration.

## Scope and files

This slice extends the previously committed atomic reservation in `ResearchStore`. It changes only:

- `backend/app/research/infrastructure/research_store.py`
- `tests/research/test_report_generation_state.py`

It adds no SQL column/table, API, AgentRunner, orchestrator, executor, model call, service integration, deployment, or Git commit. Tests use temporary research and memory SQLite databases.

## Frozen store interface

Existing reservation interfaces remain:

```python
reserve_report_generation(
    research_task_id, owner_id, *, plan_version, request_key,
    request_payload, work_item_input=None, report_version=None
) -> ReportGenerationReservation

get_report_generation_reservation(research_task_id, owner_id, *, request_key)
    -> ReportGenerationReservation | None
```

New interfaces:

```python
get_report_generation_budget(
    research_task_id, owner_id, report_version, *,
    approved_max_seconds=None,
    approved_task_model_loops=None, approved_task_tool_calls=None,
    approved_run_model_loops=None, approved_run_tool_calls=None,
    now=None,
) -> dict

update_report_generation_state(
    research_task_id, owner_id, report_version, *,
    expected_revision, stage, rewrite_count,
    status=None, published=None, reason_codes=None,
) -> dict

claim_report_generation_budget(
    research_task_id, owner_id, report_version, *,
    claim_id, agent_run_id, requested_model_loops,
    requested_tool_calls, requested_seconds,
    approved_max_seconds=None,
    approved_task_model_loops=None, approved_task_tool_calls=None,
    approved_run_model_loops=None, approved_run_tool_calls=None,
    now=None,
) -> dict

settle_report_generation_budget(
    research_task_id, owner_id, report_version, *, claim_id, now=None
) -> dict
```

`claim_id` is a UUID and identifies one run allowance. Retrying the same claim with the same fingerprint returns its original grant; reusing it for another run or limits raises `REPORT_GENERATION_STATE_CONFLICT`. A budget result contains `allowed`, the per-run `grant`, persisted `report_totals` and `task_totals`, held `reserved` amounts, effective `limits`, remaining amounts, exhausted dimensions, and current state revision.

## Persistence and invariants

All writes use the existing `research_reports.report_json` reservation under `BEGIN IMMEDIATE`; there is no second ledger or queue. The store-owned `generation.store_state` object has a strict local key allowlist for `revision`, `stage`, `rewrite_count`, `claims`, and `limits`. Claims have an allowlisted field set and a request fingerprint. The same reservation JSON write updates the contract `generation.budget` snapshot; a failed report update rolls back the claim.

State revisions are compare-and-swap values. Exact repeated state updates are idempotent; stale, divergent updates raise `REPORT_GENERATION_STATE_CONFLICT`. Stages are restricted to the Task 08 event vocabulary. Rewrite count is monotonic from 0 through 2; it increases by one only on entry to `targeted_revision`. Schema retries do not change this count. Terminal report rows cannot be rewritten or reopened.

Status choice remains the application quality validator's responsibility. The store guards lifecycle consistency: `completed` requires `published`, `quality_validation.status == "pass"`, `path == "agent_runner"`, `output_disposition == "accepted"`, and stage `published`; `draft`/`partial` require unpublished `draft_saved`; `failed` requires unpublished `failed`. The store cannot verify the session message in the separate memory database, so the caller must not request `completed` until all three versioned Artifacts and the final message are durable. The canonical quality/status classifier should remain in the application layer.

Budget reads include every `research_agent_runs` row for the task, including earlier research stages and earlier report versions, plus outstanding claims from every report reservation. A new request key/version therefore does not reset usage. Effective seconds are clamped to `min(5,400, profile cap, ResearchTask.soft_budget_seconds, any supplied lower approved-plan limit)`, with profile caps of 600/1,500/2,700 seconds. Loop/call limits are clamped to 160/640 total and 40/160 per run; caller-supplied approved limits can only lower them. The claim transaction serializes concurrent callers and never grants more than the durable remaining balance.

Settlement reads counters and timestamps only from the bound persisted `AgentRun`; it accepts no model-reported usage values. While the run is active, its unused claim remains held. If a claim has no durable run row, it remains fully reserved. A terminal run with missing/unparseable timestamps or `ended_at < started_at` consumes its entire seconds reservation. A historical terminal run without valid timestamps and without an earlier claim conservatively consumes the task seconds cap. Persisted report/task elapsed totals are monotonic floors: a later clock sample or repeated settlement cannot reduce them. These rules can exhaust a task when timing data is missing, but do not make unknown time available again.

## Integration contract and boundary

The future report-generation service should acquire a claim before model work using a stable UUID claim ID and AgentRun ID, pass the returned remaining/cap values into `BudgetSnapshot`, and persist AgentRun counters through the existing store APIs. After the AgentRun reaches terminal status, it should call `settle_report_generation_budget`; settlement derives values from the AgentRun row. On restart, it should reload the same reservation and claim rather than create a new claim or version. All report JSON writers must preserve `generation.store_state` while the reservation is active. Public JSON projection and strict schema validation must treat `store_state` as store-owned metadata, exclude it from model input, and expose only the contract's canonical fields. This internal extension is a deliberate integration seam and should be reviewed against the report JSON projection before the application layer ships.

Application code owns evidence/quality validation, unique public status classification, AgentRunner hooks, safe ResearchEvent emission, API response projection, artifact/message completion, and recovery submission. This slice does not claim that a user's report is fixed.

## Verification

Using the actual project interpreter `/Users/wjh/ResearchAgent/.venv/bin/python` (default pytest conftest loaded; no `--confcutdir` bypass):

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_generation_state.py` — exit 0, **17 passed**.
- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q tests/research/test_report_generation_state.py` — exit 0, **17 collected**, no collection errors.
- `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/infrastructure/research_store.py tests/research/test_report_generation_state.py` — exit 0.
- `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/infrastructure/research_store.py tests/research/test_report_generation_state.py` — exit 0, all checks passed.
- `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` — exit 0, `test layout: ok`.
- `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` — exit 0, naming passed.
- `git diff --check` — exit 0.

Coverage includes profile/soft/lower-plan caps, task-cap exhaustion and concurrent reservations, duplicate/mismatched claims, history across report versions and earlier AgentRuns, unknown lost-run reservation, DB-derived idempotent settlement, stale CAS, restart stage recovery, rewrite bounds, status gates, terminal immutability, and transaction rollback.

## P1 review response — terminal timing

The independent review found that the running-time fallback to `now` was also being used for terminal runs, and negative duration was clamped to zero. Terminal duration now requires two parseable timestamps with `ended_at >= started_at`; otherwise a claimed run consumes its full reserved seconds and an unclaimed historical terminal run consumes the effective task seconds cap. The `now` fallback is limited to running rows. Persisted `budget.task_totals` and the target report's per-run/report totals are retained as monotonic floors so settlement and duplicate settlement cannot lower previously recorded cumulative time.

New regression cases cover a terminal claimed AgentRun with missing `ended_at`, a reversed timestamp pair, an unclaimed historical terminal AgentRun with missing `ended_at`, a valid 90-second end-time control against a 300-second claim, and settlement after a previously persisted 120-second running sample whose terminal timestamp is earlier. All are isolated to temporary databases.

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_generation_state.py -k 'unknown_timestamps or missing_end_consumes or valid_terminal_end or do_not_reduce_persisted'` — initial RED: exit 1, 4 failed and 1 passed; demonstrated the missing-end, reversed-time, unclaimed-history, and monotonic-floor defects.
- Same command after repair — exit 0, 5 passed.
- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_generation_state.py` — exit 0, **22 passed**.
- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q tests/research/test_report_generation_state.py` — exit 0, **22 collected**.
- `py_compile`, targeted Ruff, `scripts/check_test_layout.py`, and `scripts/check_test_naming.py` — all exit 0.

## Remaining boundary

No whole-suite, live API, model/provider, runtime restoration, final artifact/message, or deployment validation was run; these belong to later Task 08 integration and acceptance. Store-owned `generation.store_state` must be reconciled with the strict public generation projection during that integration. The shared worktree also contains other agents' active changes; this handoff covers only the two code files named above and does not commit or alter the other work.

## Follow-up — failed report diagnostic persistence

The context handoff identified a no-body failure path (`INSUFFICIENT_TRUSTED_EVIDENCE`) that correctly terminalized the reserved report as `failed`, but the state CAS could not persist its safe reason code. `update_report_generation_state` now accepts optional `reason_codes: list[str] | tuple[str, ...] | None` and stores supplied codes in the existing report JSON top-level `reason_codes` field. `None` preserves legacy call behavior and existing codes; an explicit empty list clears them.

Input is limited to 32 stable ASCII uppercase codes matching `[A-Z][A-Z0-9_]{0,63}`. Duplicate codes are deduplicated in order; natural-language text, prompt/body strings, malformed types, overlong codes, and oversized lists are rejected before entering the transaction. The CAS treats reason codes as part of the requested state: exact terminal replay returns without writing, while changing terminal reasons conflicts. The update retains `generation.store_state` and the budget ledger unchanged except for the normal revision increment.

State and budget result projections expose a deduplicated `reason_codes` list from safe persisted codes, `quality_validation.failure_codes`, and `generation.fallback_reason_code`. Old reservations with no reason field project an empty list when no other code source exists. This is JSON persistence/projection only; no SQL column, API, or queue was added. The application remains responsible for choosing the appropriate stable diagnosis, such as `INSUFFICIENT_TRUSTED_EVIDENCE`.

### Follow-up verification

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_generation_state.py` — exit 0, **31 passed**.
- `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/infrastructure/research_store.py tests/research/test_report_generation_state.py` — exit 0.
- `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/infrastructure/research_store.py tests/research/test_report_generation_state.py` — exit 0, all checks passed.
- `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` and `scripts/check_test_naming.py` — exit 0.

No full suite, service startup, API integration, model, deployment, or Git operation was run.
