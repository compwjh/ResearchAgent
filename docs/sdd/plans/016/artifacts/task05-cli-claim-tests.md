# Task 05 CLI claim tests

Date: 2026-10-12. Independent tester: Codex subagent. Module: `tests/sdd_tasks/test_cli_claim.py`.

## Baseline before test changes

- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_cli_claim -v` — exit 1; 4 methods ran, 2 failed in 6.229s.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_cli_claim.py` — exit 0; all checks passed.
- The two failures assert `NO_TASK` has `data=null`; current CLI returns the Task05 status reason matrix. The other two methods passed.
- `/tmp/spec016-preflight/test_cli_claim.before-A3.py` is 101 lines and byte-for-byte matches the test module before this work.

## Slice 1: no-task reason matrix

- Updated both stale `NO_TASK` assertions to verify returned matrix reasons for an active lease and an unclaimable Spec. Both cases also confirm no eligible tasks are reported.
- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_cli_claim -v` — exit 0; 4 methods passed in 3.879s.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_cli_claim.py` — exit 0; all checks passed.

## Slice 2: dirty, gate-blocked priority candidate

- Added a second real Git worktree on a separate Spec with a lower-priority eligible Task. The higher-priority canonical worktree has an unsatisfied gate and an unrelated dirty file.
- The real `next --claim` subprocess skips the blocked candidate, claims the lower-priority Task, and leaves the dirty file unchanged. The following `status --json` reports the higher-priority Task's `gate_unsatisfied` reason. SQLite contains only the lower-priority claim and lease.
- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_cli_claim -v` — exit 0; 5 methods passed in 4.552s.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_cli_claim.py` — exit 0; all checks passed.

## Slice 3: partial recovery resume

- Added a real CLI sequence that expires and recovers a partial run, then claims its recovery child. It checks the original base commit and workspace snapshot are retained, `recovery_of` points to the abandoned parent, and partial file bytes remain unchanged.
- A second `next --claim` while that recovery child is active returns the NO_TASK matrix with the active run/lease reason and leaves all ledger rows unchanged, proving the consumed older parent is not reused.
- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_cli_claim -v` — exit 0; 6 methods passed in 5.602s.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_cli_claim.py` — exit 0; all checks passed.

This report records Task05 CLI claim coverage only; it does not claim full Task05 acceptance.
