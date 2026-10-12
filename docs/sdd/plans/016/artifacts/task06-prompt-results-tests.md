# Task06 Prompt and results tests

Date: 2026-10-12. Independent tester: Codex subagent. Runtime: Python 3.9.25.

## Baseline before test changes

- No `tests/sdd_tasks/test_prompts.py` existed. Saved the production Prompt renderer at `/tmp/spec016-preflight/prompts.before-task06-test.py` before test work.
- `RUFF_CACHE_DIR=/tmp/spec016-preflight/ruff-cache /workspace/researchagent-cli-venv39/bin/python -m ruff check scripts/sdd_tasks/prompts.py` — exit 0; all checks passed.
- `PYTHONPYCACHEPREFIX=/tmp/spec016-preflight/pycache /workspace/researchagent-cli-venv39/bin/python -m py_compile scripts/sdd_tasks/prompts.py` — exit 0.

## Slice 1: real claim and canonical rendering

- Added a real Git/SQLite fixture that updates both Task copies, rebuilds the ledger, makes a persistent-owner claim, and renders from the canonical worktree snapshot.
- The test checks all five approved substitutions, template/render hashes, exact private run path, 0700 run-directory and 0600 file modes, and that a sentinel environment value is absent.
- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_prompts -v` — exit 0; 1 test passed in 0.870s.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_prompts.py` — exit 0; all checks passed.

## Slice 2: refusal paths and environment isolation

- Saved the prior test and report as `/tmp/spec016-preflight/test_prompts.slice2.before.py` and `/tmp/spec016-preflight/task06-prompt-results-tests.slice2.before.md` before editing.
- Moved the environment sentinel patch around the actual renderer call. Added refusal checks for forged claim/snapshot bindings, a stale canonical Task, an outside runtime root, a symlinked private run parent, unknown and unresolved variables, and a sensitive template string.
- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_prompts -v` — exit 0; 4 tests passed in 3.241s.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_prompts.py` — exit 0; all checks passed.

## Slice 3: partial recovery and post-claim Spec drift

- Saved the prior test and report as `/tmp/spec016-preflight/test_prompts.slice3.before.py` and `/tmp/spec016-preflight/task06-prompt-results-tests.slice3.before.md` before editing.
- Added real-ledger partial recovery coverage: rendering uses the original baseline head, the child snapshot event carries the original snapshot and parent run ID, and the dirty allowed-file contents remain intact.
- Added a paused Spec-after-claim check. It is refused with `CLAIM_SNAPSHOT_STALE` before `.sdd/runtime/runs` is created; the observed guard is snapshot freshness.
- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_prompts -v` — exit 0; 6 tests passed in 9.704s.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_prompts.py` — exit 0; all checks passed.

## Results slice 1: real claim, changed artifact, and command receipt

- No prior `tests/sdd_tasks/test_results.py` existed. Saved the current renderer at `/tmp/spec016-preflight/results.before-task06-tests.py` before test work.
- Added a real Git/SQLite claim with a committed expected-artifact Task definition, then changed the actual allowed artifact and validated its file hash, result hash, canonical claim fields, and declared validation-command record.
- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_results -v` — exit 0; 1 test passed in 1.221s.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_results.py` — exit 0; all checks passed.

## Results slice 4: stale authority and symlinked artifacts

- Saved the prior test and report as `/tmp/spec016-preflight/test_results.slice4.before.py` and `/tmp/spec016-preflight/task06-prompt-results-tests.slice4.before.md` before editing.
- Added stale baseline, after-snapshot, and canonical Task checks, invalid hash-shape and input checks, plus end-to-end safe artifact-symlink hashing and outside-target rejection.
- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_results -v` — exit 0; 9 tests passed in 13.230s.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_results.py` — exit 0; all checks passed.

## Results slice 3: failed artifacts and exact change classification

- Saved the prior test and report as `/tmp/spec016-preflight/test_results.slice3.before.py` and `/tmp/spec016-preflight/task06-prompt-results-tests.slice3.before.md` before editing.
- Added failed-result handling for a missing expected artifact with a matching blocker; rejected a missing blocker and a skipped required command on success.
- Added real filesystem coverage for modified, added, deleted, renamed, and ignored-but-allowed file changes, with path kinds and hashes checked against snapshots.
- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_results -v` — exit 0; 6 tests passed in 5.220s.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_results.py` — exit 0; all checks passed.

## Results slice 2: forged bindings and unsafe claims

- Saved the prior test and report as `/tmp/spec016-preflight/test_results.slice2.before.py` and `/tmp/spec016-preflight/task06-prompt-results-tests.slice2.before.md` before editing.
- Added checks for forged run and Task hashes, changed-file and artifact hash mismatches, out-of-scope edits, missing artifacts on success, sensitive content, and a future completion timestamp.
- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_results -v` — exit 0; 4 tests passed in 3.271s.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_results.py` — exit 0; all checks passed.

## Workspace snapshot slice 1: safe and escaping symlinks

- Saved the prior report as `/tmp/spec016-preflight/task06-prompt-results-tests.workspace.before.md` before this report update.
- Updated the former `outside.txt` refusal case to point outside the worktree, while checking an in-root file symlink hashes its target. Added directory and broken symlink refusals plus a FIFO rejection guarded by a three-second alarm.
- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_workspace -v` — exit 0; 5 tests passed in 1.062s.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_workspace.py` — exit 0; all checks passed.

## Prompt renderer guard followup

- Saved the prior prompt test and report as `/tmp/spec016-preflight/test_prompts.before-renderer-guard-tests.py` and `/tmp/spec016-preflight/task06-prompt-results-tests.before-renderer-guard-tests.md` before adding guard coverage.
- Added focused no-publication assertions for nonclaimable Spec status and unsatisfied required gates, alongside the real changed-Spec snapshot-stale case.
- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_prompts -v` — exit 0; 7 tests passed in 5.321s.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_prompts.py` — exit 0; all checks passed.
