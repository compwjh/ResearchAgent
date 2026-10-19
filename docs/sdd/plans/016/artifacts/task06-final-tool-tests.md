# Task 06 final tool tests

## Scope and candidate

The Python software candidate identified for this QA pass is `c9ae563673109fdf747732686fa3f4a2d1add90e`. The shared branch advanced while verification was running. The unittest command began at `cf4cee150366e1c686504282a1c991d6bc5c1d34` and ended at `6c48f68a0c9ade908fcd0bd7d5d6f5b1911b4e90`; the concurrent changes were outside `scripts/sdd_tasks` and `tests/sdd_tasks`. A direct diff of those two directories from the candidate `c9ae563` to `6c48f68` was empty, so the tested Python sources and tests match the candidate.

The only worktree status entries observed around these commands were the branch position and two concurrent, untracked documentation artifacts:

- `docs/sdd/plans/016/artifacts/legacy-task-audit.md`
- `docs/sdd/reviews/016-task06-review.md`

## Results

| Command | Started / finished (UTC) | Elapsed | Exit | Result |
|---|---|---:|---:|---|
| `/workspace/researchagent-cli-venv39/bin/python -m unittest discover -s tests/sdd_tasks -t .` | 10:04:58 / 10:07:16 | 137.786 s | 1 | 377 tests; 4 failures and 1 error |
| `/workspace/researchagent-cli-venv39/bin/python -m ruff check scripts/sdd_tasks tests/sdd_tasks` | 10:07:16 / 10:07:16 | 0.022 s | 0 | `All checks passed!` (0 Ruff diagnostics) |
| `/workspace/researchagent-cli-venv39/bin/python -m compileall scripts/sdd_tasks tests/sdd_tasks` | 10:07:16 / 10:07:16 | 0.022 s | 0 | Both requested directories listed; no compile errors reported |

### unittest failures

1. **Error** — `tests.sdd_tasks.test_ledger_finalize.LedgerFinalizeBindingTests.test_complete_failed_result_stays_readable_during_new_claim_and_lease` failed while claiming `spec-016-task-04`. The raised error was `ClaimError: CLAIM_FAILED_SOURCE_INVALID`; its cause chain included `FailedRecoveryError: FAILED_RECOVERY_SOURCE_INVALID` and `WorkspaceObservationError: OBSERVATION_TASK_MISMATCH`.

2. **Four failing subtests** — `tests.sdd_tasks.test_recovery_claim.RecoveryClaimTests.test_malformed_recovery_classification_is_rejected_without_ledger_changes`, at assertion line 184, expected `CLAIM_RECOVERY_EVENT_INVALID` for each payload but received:

   - `{"schema":"sdd-run-recovery/v1","action":[],"decision":"unchanged"}` → `FAILED_RETRY_CONTEXT_INVALID`
   - `{"schema":"sdd-run-recovery/v1","action":"other","decision":"unchanged"}` → `OBSERVATION_HISTORY_DECISION_INVALID`
   - `{"schema":"sdd-run-recovery/v1","action":null,"decision":"unchanged"}` → `OBSERVATION_HISTORY_DECISION_INVALID`
   - `{"schema":"sdd-run-recovery/v1","action":"requeued","decision":NaN}` → `RECOVERY_EVENT_INVALID`

The run emitted `RuntimeWarning: stale_task_copies_ignored` messages from fixture worktrees. These are expected warnings and are not included in the 4 failures or 1 error.

## HEAD and status around commands

- **unittest:** HEAD before `cf4cee150366e1c686504282a1c991d6bc5c1d34`; HEAD after `6c48f68a0c9ade908fcd0bd7d5d6f5b1911b4e90`. Status changed from branch `ahead 2` to `ahead 3`; the two untracked documentation artifacts listed above were present before and after.
- **Ruff:** HEAD before/after `6c48f68a0c9ade908fcd0bd7d5d6f5b1911b4e90`; status was branch `ahead 3` with the same two documentation artifacts before and after.
- **compileall:** HEAD before/after `6c48f68a0c9ade908fcd0bd7d5d6f5b1911b4e90`; status was branch `ahead 3` with the same two documentation artifacts before and after.

No Python source or test files were changed by this QA run.

## Follow-up targeted run on the post-fix candidate

Root reviewed and committed the failed-history fixture and production canonicalization work before authorizing this run. The targeted command started at `f620887dbbdca7fd47f2431fd0cdfe72185f7524`. HEAD moved during the run to `8982e6eb9de2e10860957b06f616131db09d36e1`; the only difference between these commits under `scripts/sdd_tasks` and `tests/sdd_tasks` is none, while `docs/sdd/TASK-PROTOCOL.md` changed. The source and test trees therefore remained unchanged during this run.

| Command | Started / finished (UTC) | Elapsed | Exit | Result |
|---|---|---:|---:|---|
| `/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_ledger_finalize tests.sdd_tasks.test_recovery_claim tests.sdd_tasks.test_catalog_eligibility tests.sdd_tasks.test_failed_recovery_status tests.sdd_tasks.test_failed_retry_crash` | 02:16:06.633 / 02:16:21.441 | 14.808 s | 1 | 30 tests; 2 errors |

The complete verbose output is `/tmp/spec016_task06_targeted_20261017.out`. The two errors were:

1. `test_complete_failed_result_stays_readable_during_new_claim_and_lease`, `tests/sdd_tasks/test_ledger_finalize.py:146`: `IndexError: list index out of range` when the test reads `journal["expected_result"]["artifacts"][0]["path"]`; the actual `artifacts` list is empty after the real `fail_run` fixture.
2. `test_attempt_limit_waits_and_resets_after_nonfailed_run`, `tests/sdd_tasks/test_catalog_eligibility.py:70`: `StopIteration` because `_status(database)["eligible"]` does not contain the task.

The other 28 tests passed, including both `test_failed_recovery_status` cases and `test_failed_retry_crash`. Fixture runs emitted expected `stale_task_copies_ignored` warnings. HEAD before/after was `f620887dbbdca7fd47f2431fd0cdfe72185f7524` / `8982e6eb9de2e10860957b06f616131db09d36e1`; porcelain status before/after listed the same four untracked artifacts (`legacy-task-audit.md`, `live-luna-demo.md`, this report, and `016-task06-review.md`). The targeted errors blocked the requested full-domain, Ruff, and compileall follow-up; none was run in this pass.

## Closure QA after fixture correction

The Luna xhigh implementation agent fixed the new fixture's `current_owner` call; root reviewed it, committed it, and froze candidate `281e93373aa328b47d289662919f991646d12773`. The run sequence below preserves the first failed attempt and its focused retry.

| Command | Started / finished (UTC) | Elapsed | Exit | Result |
|---|---|---:|---:|---|
| Five targeted modules on `c74579b7892945eb0903fe2c36d1051c21459951` | 00:52:05.427 / 00:52:16.300 | 10.873 s | 1 | 30 tests; 1 error |
| `... unittest -v tests.sdd_tasks.test_ledger_finalize.LedgerFinalizeBindingTests.test_complete_failed_result_stays_readable_during_new_claim_and_lease` | 00:54:41.806 / 00:54:43.570 | 1.763 s | 0 | 1 test passed (unittest reported 1.688 s) |
| Five targeted modules on `281e93373aa328b47d289662919f991646d12773` | 00:54:53.879 / 00:55:06.606 | 12.727 s | 0 | 30 tests passed (unittest reported 12.660 s) |
| `/workspace/researchagent-cli-venv39/bin/python -m unittest discover -s tests/sdd_tasks -t .` | 00:55:14.424 / 00:57:37.363 | 142.939 s | 0 | 379 tests passed (unittest reported 142.850 s) |
| `/workspace/researchagent-cli-venv39/bin/python -m ruff check scripts/sdd_tasks tests/sdd_tasks` | 00:57:49.626 / 00:57:49.654 | 0.028 s | 0 | `All checks passed!` |
| `/workspace/researchagent-cli-venv39/bin/python -m compileall scripts/sdd_tasks tests/sdd_tasks` | 00:57:49.946 / 00:57:49.971 | 0.024 s | 0 | Both directories listed; no compile errors |

The first targeted attempt's single error was `TypeError: current_owner() missing 1 required keyword-only argument: 'pid'` at `tests/sdd_tasks/test_ledger_finalize.py:70`; the Luna xhigh implementation agent fixed the fixture and root committed `281e933`, and the isolated test plus the five-module rerun then passed. The first run began at `c74579b7892945eb0903fe2c36d1051c21459951` and ended at `05b78c0a8c2a188e2dfa31c7cdc0f1901e06a312`. It emitted expected `stale_task_copies_ignored` warnings; these are not test failures.

Verbose outputs and command metadata are retained as regular files under `.sdd/runtime/closure-qa/`: `targeted-20261019.out/.json`, `fixture-method-20261019.out/.json`, `targeted-after-pidfix-20261019.out/.json`, `domain-20261019.out/.json`, `ruff-20261019.out/.json`, and `compileall-20261019.out/.json`. The successful fixture-only and five-module runs started and ended on `281e933` with clean status. The domain run also used HEAD `281e933`; a concurrent documentation-only edit left `docs/sdd/plans/016/task-07-cross-ide-skills.md` modified after it. That same documentation status remained before/after Ruff and compileall. No Python source or test file changed during these successful runs. No global pytest/conftest command was run.

## Mirrors patch targeted QA

Root read the 63-line mirrors diff and froze the working candidate at `429e82b66b0bebabb185085bee22c49ae5c3f2cc`, with only `scripts/sdd_tasks/mirrors.py` and `tests/sdd_tasks/test_mirrors.py` modified. Before commit, the authorized targeted command passed:

| Command | Started / finished (UTC) | Elapsed | Exit | Result |
|---|---|---:|---:|---|
| `/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_mirrors` | 01:13:32.289 / 01:13:32.339 | 0.050 s | 0 | 10 tests passed (unittest reported 0.015 s) |

HEAD remained `429e82b66b0bebabb185085bee22c49ae5c3f2cc`; status before/after still showed only the two uncommitted mirrors files. Output and command metadata are in `.sdd/runtime/closure-qa/mirrors-20261019.out` and `.json`. Full-domain verification is pending root commit, per the QA sequence.

## Mirrors patch post-commit closure run

After root committed the mirrors patch as `37bb056ed5f61c357cbdfba78eced21076154013`, the full domain and static checks passed. HEAD advanced during the full run to `83fadbe049b41b0d1478a071a847b20ab0b52fe8`; `git diff --name-only 37bb056ed5f61c357cbdfba78eced21076154013 83fadbe049b41b0d1478a071a847b20ab0b52fe8 -- scripts/sdd_tasks tests/sdd_tasks` returned no paths, so the Python source and test trees were unchanged across the commit movement.

| Command | Started / finished (UTC) | Elapsed | Exit | Result |
|---|---|---:|---:|---|
| `/workspace/researchagent-cli-venv39/bin/python -m unittest discover -s tests/sdd_tasks -t .` | 01:13:56.128 / 01:16:29.666 | 153.538 s | 0 | 382 tests passed (unittest reported 153.440 s) |
| `/workspace/researchagent-cli-venv39/bin/python -m ruff check scripts/sdd_tasks tests/sdd_tasks` | 01:16:43.759 / 01:16:43.779 | 0.020 s | 0 | `All checks passed!` |
| `/workspace/researchagent-cli-venv39/bin/python -m compileall scripts/sdd_tasks tests/sdd_tasks` | 01:16:44.042 / 01:16:44.063 | 0.021 s | 0 | Both directories listed; no compile errors |

The full run started on HEAD `37bb056ed5f61c357cbdfba78eced21076154013` and ended on `83fadbe049b41b0d1478a071a847b20ab0b52fe8`. Its before/after status showed only concurrent documentation migrations in `docs/sdd/plans/015`, `docs/sdd/plans/016`, and `docs/sdd/specs/015`; the Python trees had no changes. Ruff and compileall ran on HEAD `83fadbe` with the same documentation-only status before and after. Expected `stale_task_copies_ignored` fixture warnings appeared during unittest and were not failures.

Regular-file outputs and command metadata are retained under `.sdd/runtime/closure-qa/`: `domain-after-mirrors-20261019.out/.json`, `ruff-after-mirrors-20261019.out/.json`, and `compileall-after-mirrors-20261019.out/.json`.
