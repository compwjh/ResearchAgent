# Spec 030 Task 08 — canonical report store writer handoff

Date: 2026-10-29  
Role: backend-dev  
Status: bounded canonical writer implemented; application integration and independent review remain downstream.

## Scope

Changed only:

- `backend/app/research/infrastructure/research_store.py`
- `tests/research/test_report_canonical_persistence.py`

This slice adds no SQL schema, table, public API, queue, model call, service integration, deployment, or Git commit. `save_research_report` remains an insert-only writer for callers that create a new report row; the new method updates a row already created by `reserve_report_generation`.

## Store interface

```python
save_report_generation_output(
    research_task_id,
    owner_id,
    report_version,
    *,
    plan_version,
    expected_revision,
    report_content,
    quality_validation,
    generation_output,
) -> dict
```

`generation_output` accepts only structured trusted provenance fields: `path`, `output_disposition`, and optional `agent_run_ids`, `provider`, `model`, and `fallback_reason_code`. Path/disposition are required. Raw model text, prompts, and arbitrary output fields are rejected.

The store bounds and checks the canonical envelope: `report_content` has the exact top-level `research-report-content-v1` fields and is at most 512 KiB UTF-8; `quality_validation` has the exact `report-quality-v1` fields, bounded counts, and at most 32 unique failure codes of at most 64 characters; generation metadata is allowlisted and bounded. Evidence mapping, nested report-content schema semantics, and quality calculations remain the application validator's responsibility.

## CAS and identity guarantees

- Runs in one `BEGIN IMMEDIATE` transaction and updates the existing `research_reports` row in place.
- Validates task ownership, task/report association, row and canonical plan/report versions, and the reservation's bound synthesis WorkItem identity.
- Requires the supplied `expected_revision` to match `generation.store_state.revision` for a new write. A divergent stale or future revision raises `ResearchReportGenerationStateConflict`.
- A new write is allowed only while the report row is `generating`; it increments the store-state revision once.
- An exact replay of already persisted content, quality validation, and supplied generation fields returns `replayed=True` without a database write, including after terminalization. A divergent terminal write raises `ResearchReportGenerationStateConflict`.
- Preserves `generation.budget` and all `generation.store_state` ledger values (`stage`, `rewrite_count`, `claims`, and `limits`); only the revision increments on a new write.
- Leaves `status`, `published`, Markdown/HTML projections, Artifacts, and session messages to their existing lifecycle owners.

The returned mapping follows `_report_generation_write_result`: canonical `report`, current revision/stage/rewrite count, usage totals, and a `replayed` flag.

## Downstream integration

After application-level evidence validation and server-side quality calculation, call this writer with the reservation's task ID, owner, plan version, and report version. Use the current reservation revision from `get_report_generation_budget` (or a preceding state-write result) as `expected_revision`. On recovery, load the same reservation and replay the same canonical fields; do not create another report row or reset the budget ledger. Only after the separate Artifact/message completion steps should the caller use `update_report_generation_state` to publish a terminal status.

## Verification

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_canonical_persistence.py` — exit 0, **15 passed**.
- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_version_reservation.py` — exit 0, **17 passed**.
- `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/infrastructure/research_store.py tests/research/test_report_canonical_persistence.py` — exit 0.
- `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/infrastructure/research_store.py tests/research/test_report_canonical_persistence.py` — exit 0, all checks passed.
- `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` — exit 0, `test layout: ok`.
- `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` — exit 0, no spec/task numbers under tests.

Tests cover reservation-row reuse, ledger preservation, exact replay, divergent stale CAS, owner/task/plan/report-version mismatches, terminal immutability, strict envelope fields, and the report-content byte limit. No broader regression suite or runtime/API validation was run.

## Independent review response — reservation identity BLOCK

The review found that `save_report_generation_output` could accept WorkItem `input_json` whose duplicated identity values disagreed with the report reservation. The shared `_report_reservation_work_item` check now validates the canonical report row and generation against both the WorkItem's top-level input and its nested `report_generation` binding. It checks report ID, report version, plan version, request key, and request fingerprint; the fingerprint must be a 64-character lowercase SHA-256 hex string, and its top-level and nested copies must match. The reservation writer now stamps top-level `plan_version` and `request_fingerprint` from store-owned values, alongside the existing report ID/version/request key.

The reservation reader and canonical writer both use this shared check and fail closed before returning or writing when any duplicated identity differs. The check adds no schema or queue. Ten parameterized counterexamples mutate each top-level and nested identity field; the first run reproduced **7 failures** (the existing helper already rejected nested report ID/version/request key), then all ten passed after the repair. The full canonical persistence file passes with **15 passed**, and reservation behavior passes with **17 passed**. Budget-ledger preservation and exact replay remain covered by the canonical persistence tests.

## Agent log

`.codebuddy/agent-logs/spec-030/task-08/backend-dev/20261029-161859.md`
