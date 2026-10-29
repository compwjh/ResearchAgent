# Spec 030 Task 08 report_content Output Contract Review

> Current status: narrow re-review PASS; the first-review P2 is resolved. The original finding and verdict remain below.

- Reviewer: `/root/quality_foundation_review`
- Role: Backend Reviewer
- Model: Luna xhigh (temporary dispatch setting)
- Dispatch: native subagent
- Base: `8b486c29`
- Scope: only the diff for `backend/app/research/application/report_synthesis.py` and `tests/research/test_report_content_synthesis.py`, against the output-contract plan. Renderer/store dirty changes were not reviewed.

## First-review Verdict: PASS with one P2 follow-up

### [P2] Raw ID length can exceed the declared 200-character bound

**Location:** `backend/app/research/application/report_synthesis.py:50-53, 198-205`; delegated shape check at `backend/app/research/application/report_quality.py:133-136`.

The JSON Schema declares `maxLength: 200`, but the Python validator delegates to `_id()`, which checks `len(value.strip())`. A whitespace-padded ID whose raw value exceeds 200 code points is therefore accepted by `validate_report_synthesis_output()` and returned unchanged. I reproduced acceptance of a 201-code-point paper ID (`" " + "p" * 200`) after recomputing the envelope hash. `_walk_safe()` also allows strings up to 12,000 characters, so it does not close this discrepancy. The authoritative Python boundary does not enforce the declared field bound.

**Minimal fix:** Check the raw string length against 200 before trimming in the shared shape validator (or add an equivalent raw-length check at this boundary), then normalize only after it passes. Add a regression case for a padded ID over 200 code points.

## Contract checks that passed

- `report_content` stays optional; omitted legacy output retains the old serialized shape and hash, while present content participates in `output_hash`.
- Present content is shape-validated and total-size-capped at the Python boundary; `consume_validated_output()` preserves it and still enforces the existing citation-manifest allowlist. The P2 finding above is the remaining per-ID raw-length mismatch.
- This slice adds no quality result or publication-success fields. Evidence/task/plan/provenance validation is explicitly deferred to the later trusted-context gate; shape acceptance here is not evidence validation or a semantic quality verdict.

## Verification

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --confcutdir=tests/research tests/research/test_report_synthesis_contract.py tests/research/test_report_content_synthesis.py -q --tb=short`: exit 0, **41 passed**.
- Read-only reproduction with the same absolute interpreter confirmed acceptance of a 201-code-point padded ID.
- `git diff --check 8b486c29 -- backend/app/research/application/report_synthesis.py tests/research/test_report_content_synthesis.py`: exit 0.

| Severity | Count | Result |
|---|---:|---|
| P0/P1 | 0 | none |
| P2 | 1 | follow-up |
| P3 | 0 | none |

No quality PASS or publication behavior is claimed by this review. The output slice is acceptable to continue with the P2 bounds discrepancy tracked for correction before relying on this validator as the exact contract boundary.

## Narrow Re-review (2026-10-29)

**Re-review result: PASS; P2 resolved.**

- `ReportSynthesisOutput._bounded_report_content()` now checks raw ID lengths after shape validation but before returning normalized output. The guard covers IDs in scope, paper analyses and blocks, comparisons, findings, and gaps; it rejects raw length over 200 without changing the shared `report_quality.py` validator.
- Added a parameterized regression test for both leading-space and trailing-space 201-code-point IDs whose trimmed length is 200; both must be rejected.
- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --confcutdir=tests/research tests/research/test_report_synthesis_contract.py tests/research/test_report_content_synthesis.py -q --tb=short`: exit 0, **43 passed**.

**Current Verdict: PASS — the raw ID bound discrepancy is closed.**
