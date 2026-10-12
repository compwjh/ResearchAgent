# Task 05 recover CLI tests

Date: 2026-10-11. Independent tester: restore_workspace. Test module: `tests/sdd_tasks/test_cli_recover.py` (138 lines).

## Commands and results

- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_cli_recover -v` — exit 0; 2 test methods passed in 5.062s.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_cli_recover.py` — exit 0; all checks passed.

## Coverage

The tests launch the real `python -m scripts.sdd_tasks ... recover --run-id ...` CLI in subprocesses using temporary Git worktrees and SQLite ledgers. A real owner child process is reaped before successful recovery. Unchanged and partial cases check the JSON success envelope, abandoned run, closed lease, exact recovery-decision event, and unchanged worktree contents (including preservation of partial edits).

Refusal cases exercise a live owner, a remote owner with unknown liveness, a malformed baseline event, and out-of-scope worktree changes. Each checks for a non-success JSON response and verifies ledger rows and watched file bytes remain unchanged. No owner token or absolute repository path is emitted on success.

Temporary fixture setup emitted `stale_task_copies_ignored` RuntimeWarnings during catalog rebuild; all assertions passed. This report records only the CLI recovery tests and does not claim full Task 05 acceptance.

## Claim CLI canonical gate precheck smoke — backend-dev

Date: 2026-10-12. Change: `scripts/sdd_tasks/newcli_claim.py` now checks claimable Spec status and required gate evidence from an already registered canonical worktree before calling `prepare_worktree`. The existing post-preparation gate load and transactional canonical revalidation remain in place.

### Commands and results

- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python - <<'PY' ... PY` — exit 0; focused temporary smoke built an in-memory task ledger, stubbed a registered canonical worktree path, and asserted an unsatisfied-gate high-priority candidate did not reach `prepare_worktree`; the lower eligible candidate reached the mocked `claim_next` seam. Git registration and lease creation were mocked, and no repository files or persistent ledger were modified.
- `/workspace/researchagent-cli-venv39/bin/python -m py_compile scripts/sdd_tasks/newcli_claim.py` — exit 0.
- `/workspace/researchagent-cli-venv39/bin/ruff check scripts/sdd_tasks/newcli_claim.py` — exit 0; all checks passed.
- `git diff --check -- scripts/sdd_tasks/newcli_claim.py` — exit 0.

The implementation slice changed one Python file by 9 additions and 0 deletions against the saved pre-edit baseline. This focused smoke is not a business-test-suite result or Task 05 acceptance.
