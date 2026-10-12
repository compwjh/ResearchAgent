# Task 05 Status Consistency Tests

Updated: 2026-10-12. This is a focused independent status-check artifact, not Task 05 acceptance.

## Coverage

`tests/sdd_tasks/test_catalog_eligibility.py` adds five integration tests for `catalog_status.status`:

- consecutive failed attempts report `max_attempts_exhausted`; a non-failed run resets the count;
- missing and extra dependency index rows report `dependency_index_stale`;
- valid latest abandoned runs report informational `recovery_ready:unchanged` or `recovery_ready:partial` while remaining eligible;
- a workspace conflict waits with `recovery_workspace_conflict`, and a malformed recovery event waits with `recovery_invalid:RECOVERY_EVENT_INVALID`; neither query changes ledger rows;
- a latest active recovery claim is reported as running and does not expose its consumed abandoned parent as eligible or waiting.

## Validation

| Command | Exit | Result |
|---|---:|---|
| `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_catalog_eligibility` | 0 | Python 3.9.25; all 5 tests passed. |
| `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_catalog_eligibility.py` | 0 | All checks passed. |
| `python3 --version && python3 -m unittest tests.sdd_tasks.test_catalog_eligibility` | 0 | Python 3.12.14; all 5 tests passed. |

No production files were changed.
