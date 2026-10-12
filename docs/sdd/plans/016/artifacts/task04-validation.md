# Task 04 validation evidence

Date: 2026-10-11 (Asia/Shanghai)

## Automated validation

Runtime: Python 3.9.25. All commands ran in `/workspace/ResearchAgent/.worktrees/spec-016`.

- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python -m unittest discover -s tests/sdd_tasks -v` — exit 0; 89 tests passed, 0 failed.
- `RUFF_CACHE_DIR=/tmp/spec016-preflight/ruff-cache /workspace/researchagent-cli-venv39/bin/python -m ruff check scripts/sdd_tasks tests/sdd_tasks` — exit 0; all checks passed.
- `PYTHONPYCACHEPREFIX=/tmp/spec016-preflight/pycache /workspace/researchagent-cli-venv39/bin/python -m compileall -q scripts/sdd_tasks tests/sdd_tasks` — exit 0.
- `PYTHONDONTWRITEBYTECODE=1 /workspace/researchagent-cli-venv39/bin/python docs/sdd/plans/016/artifacts/task04-smokes.py` — exit 0; eight archived smoke groups passed. The harness resolves the repository root from its own path.
- `PYTHONPYCACHEPREFIX=/tmp/spec016-preflight/pycache /workspace/researchagent-cli-venv39/bin/python -m py_compile docs/sdd/plans/016/artifacts/task04-smokes.py` — exit 0.

The archived smoke groups cover side-effect-free imports (including gates/status), registered canonical gate status, two-process SQLite initialization, concurrent real-Git rebuild and no-replace publication, WAL/lease/event preservation on refused rebuild, running-hash drift preservation, malformed Task/summary preservation, and raced-in DB symlink rejection. The canonical gate smoke also verifies passed evidence enables eligibility; failed or missing proof waits; main-worktree stale evidence cannot override canonical failure; invalid registry and canonical Task hash drift fail closed.

## Test evidence

The 89-test package includes schema/FK/WAL constraints and the active-Run partial unique index; document and prompt validation; safe reads, writes, symlink/FIFO/path checks; canonical versus stale worktree copies and three status mirrors; G1 canonical authority and gate registry checks; G2 positive/negative catalog status evidence; strict summary schema/binding and terminal-only import; and rebuild refusal preserving existing task, run, event, and lease rows. The expected `stale_task_copies_ignored` warnings occur in fixtures that intentionally compare a canonical linked worktree with stale main copies. The unknown-base test also prints Git’s expected invalid-object diagnostic while passing.

## Acceptance boundary

Automated Task 04 tests and checks pass. The user-confirmed CodeBuddy local acceptance is deferred and remains unverified; no CodeBuddy pass is claimed. This artifact does not claim an overall Spec016 Go. Task 05 and Task 06 are not implemented or accepted.
