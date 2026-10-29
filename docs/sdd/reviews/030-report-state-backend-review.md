# Spec 030 Task 08 Report State and Budget Store Review

> Current status: narrow re-review PASS; the original P1 is resolved. The initial BLOCK finding and evidence are retained below.

- Reviewer: `/root/quality_foundation_review`
- Role: Backend Reviewer
- Model: Luna xhigh (temporary dispatch setting)
- Scope: `backend/app/research/infrastructure/research_store.py`, `tests/research/test_report_generation_state.py`, and `docs/sdd/plans/030/2026-10-29-report-state-backend.md` only. Other concurrent renderer/output/store edits were not reviewed.
- Verdict: **BLOCK — one P1 budget-accounting defect.**

## Contract checks

- Effective time limits are clamped by the task soft budget, profile cap (`speed` 600s, `balanced` 1,500s, `quality` 2,700s), 5,400s absolute ceiling, and supplied lower plan limit. Task loop/call caps and per-run caps are likewise clamped, and persisted lower limits cannot be raised by later claims.
- Usage collection reads all task-bound `AgentRun` rows and claims from all report versions. Missing `AgentRun` rows keep their full claims reserved; new report versions do not reset prior task usage.
- Claims are written with the reservation JSON under `BEGIN IMMEDIATE`; the rollback test checks that a failed report-row update does not persist the claim. Claim fingerprints, retry handling, owner/task lookup, and stale state revisions are enforced in the reviewed paths.
- The state update enforces monotonic revision/rewrite count and terminal report immutability. The completed status gate requires a passing machine-validation marker and accepted `agent_runner` output. This store slice does not integrate those gates with the runner or publish path; this review does not claim end-to-end enforcement or publication readiness.
- `generation.store_state` remains store-owned metadata. Its public projection/preservation contract and caller integration remain later work as the plan states.

## Finding

### [P1] Terminal runs with incomplete or reversed timestamps release reserved time

**Location:** `backend/app/research/infrastructure/research_store.py:6652-6661, 6792-6805`

`_report_generation_elapsed()` substitutes `now_seconds` when `ended_at` is absent and clamps a negative end-minus-start delta to `0.0`. The terminal-run branch then treats either result as known elapsed time instead of consuming the entire claim reservation (or task cap for an unclaimed historical run). This makes corrupt/incomplete terminal timing data available for later report runs, contrary to the plan's conservative unknown-time rule.

I reproduced both cases with temporary SQLite databases and the test fixture helpers: a terminal run with a 300-second claim, `started_at=00:00:00Z`, `ended_at=None`, and `now=00:00:10Z` counted only 10 seconds and left 1,490 seconds available; a terminal run with `started_at=00:02:00Z` and `ended_at=00:00:00Z` counted 0 seconds and left the full 1,500-second task budget available.

**Minimal fix:** For terminal runs, require both timestamps to parse and require `ended_at >= started_at`. If either check fails, charge the full claim reservation; for an unclaimed historical terminal run, charge the full effective task seconds cap. Keep the `now` fallback only for nonterminal/running runs. Add regressions for missing `ended_at` and reversed timestamps, including the unclaimed historical fallback.

## Verification

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_generation_state.py` — exit 0, **17 passed**.
- Two additional read-only reproductions against temporary databases confirmed the incomplete-end and reversed-clock accounting described above.

| Severity | Count | Result |
|---|---:|---|
| P0 | 0 | none |
| P1 | 1 | block |
| P2/P3 | 0 | none |

**Verdict: BLOCK — fix conservative terminal timestamp accounting and rerun the 17 targeted tests.**

## Narrow Re-review (2026-10-29)

**Re-review result: PASS; the original P1 is resolved.**

- `_report_generation_elapsed()` now returns unknown unless both timestamps parse and the end is at or after the start. The `now` sample is substituted only for a running AgentRun with no end timestamp.
- Unknown terminal duration now consumes the full persisted claim reservation, or the effective task seconds cap for an unclaimed historical run. Valid terminal durations still count the observed elapsed value and release only the unused claim remainder.
- Regression cases cover claimed terminal runs with a missing end or reversed clock, an unclaimed historical terminal run with a missing end, valid terminal elapsed time, and nondecreasing persisted elapsed totals after settlement/replay.
- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_generation_state.py` — exit 0, **22 passed**.

**Current narrow re-review verdict: PASS — the terminal timestamp budget defect is closed. This does not validate runner/app integration or publication behavior.**

## Reason-code state update re-review (2026-10-29)

**Narrow re-review result: PASS.** The `update_report_generation_state(reason_codes=...)` addition safely validates, deduplicates, CAS-persists, and projects report reason codes while preserving the existing budget ledger.

- `_canonical_report_reason_codes` accepts only a list/tuple of at most 32 strings matching the stable uppercase code pattern; each code is 1–64 characters. Duplicate input codes are collapsed in first-seen order. The read projection unions quality failure codes, persisted reason codes, and fallback reason code, filtering malformed values and deduplicating them.
- The state transaction writes `reason_codes`, generation state, and report status together. Exact replay compares the normalized reason set; stale updates that change it conflict. Terminal reports allow only exact same-state replay.
- A state update without `reason_codes` preserves existing values for legacy callers; `reason_codes=[]` explicitly clears them while the report remains generating. The state JSON rewrite preserves `generation.budget` and the `store_state` claims/limits arrays.
- Independent temporary-store probe: a 64-character uppercase code was accepted and deduplicated; budget, claims, and limits matched byte-for-byte before/after the terminal transition; exact terminal replay returned `replayed=True` with unchanged revision. A 65-character code, newline/prompt-like value, lowercase/hyphenated value, empty string, and non-ASCII value were rejected without changing revision or report status.
- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_generation_state.py` — exit 0, **31 passed**.

**Current narrow re-review verdict: PASS — the reason-code state update, safe projection, CAS replay, terminal immutability, and ledger preservation meet the reviewed contract.** The earlier terminal-time accounting re-review remains PASS; this does not validate caller/UI integration.
