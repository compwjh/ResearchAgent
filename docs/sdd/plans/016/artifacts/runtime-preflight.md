# Spec 016 Task 02 runtime preflight

Date: 2026-10-11 11:34 CST (Asia/Shanghai)
Scope: isolated preflight evidence only. Harness: [`runtime_preflight.py`](./runtime_preflight.py), 76 lines. It created and removed its SQLite database, Markdown fixtures and Git fixture under a temporary directory; it did not alter a real worktree. This is not production implementation acceptance.

## Result

- **Cloud runtime preflight: GO for checks executed (7/7 passed on each Python version).** WAL and serialized atomic claims worked; duplicate active lease was rejected and an expired lease was reclaimable; Markdown restored task state/dependencies and a run summary after database deletion; linked worktree shared common-dir/runtime location and preserved the main worktree's dirty file.
- **Full Task 02 / dual IDE gate: deferred, incomplete.** CodeBuddy was not run, as locally confirmed by the user. No CodeBuddy pass is claimed. The shared CLI JSON/Prompt/result-schema smoke across both IDEs and independent tech-lead review remain outstanding. Codex executor I/O/shell access was smoke-tested, but that does not satisfy the dual-IDE protocol gate.
- **Actual Python 3.9 run: passed.** The provided environment is `/workspace/researchagent-cli-venv39/bin/python` (Python 3.9.25, SQLite 3.50.4, JSON1 available). `pytest` and `ruff` are installed there; neither was needed or run for this standalone harness.

## Commands and environment

All listed commands exited 0. The original isolated run recorded eight setup/environment/execution commands; the Python 3.9 environment probe and repository-worktree execution below add two commands.

| Command | Result |
|---|---|
| `python3 --version` | Python 3.12.14 |
| `python3 -c 'import sqlite3; print(sqlite3.sqlite_version); print(sqlite3.connect(":memory:").execute("select json_valid(\"{}\")").fetchone()[0])'` | SQLite 3.53.1; JSON1 returned `1` |
| `git --version` | Git 2.52.0 |
| Python 3.12 module probe (`find_spec` for pytest/ruff) | Both unavailable in that interpreter; nothing installed |
| `python3 /tmp/spec016-preflight/runtime/runtime_preflight.py` | Exit 0; 7 passed, 0 failed |
| `/workspace/researchagent-cli-venv39/bin/python -c 'import importlib.util,sys,sqlite3; print(sys.executable); print(sys.version.split()[0]); print(sqlite3.sqlite_version); print(sqlite3.connect(":memory:").execute("select json_valid(\"{}\")").fetchone()[0]); print(bool(importlib.util.find_spec("pytest"))); print(bool(importlib.util.find_spec("ruff")))'` | Exit 0; Python 3.9.25, SQLite 3.50.4, JSON1 `1`, pytest/ruff installed |
| `/workspace/researchagent-cli-venv39/bin/python docs/sdd/plans/016/artifacts/runtime_preflight.py` | Exit 0; 7 passed, 0 failed |

## Evidence

- Each Python run reported SQLite journal mode `wal`. Two independent subprocesses raced on one task under `BEGIN IMMEDIATE`: one returned `claimed`, the other `rejected`, with no database error.
- A second active lease insert raised `sqlite3.IntegrityError` through the partial unique index. Setting the winning lease expiry to zero allowed a new claim.
- After database deletion, rebuilding from Markdown restored `(A, ready, B)`, `(B, done, -)` and run `(R1, A, ok)`.
- In the temporary Git repository, main and linked worktree resolved the same `.git` common directory and `.sdd/runtime` location. `.worktrees/` and `.sdd/runtime/` were ignored; the main worktree's uncommitted `dirty.txt` retained `preserve me`.
- The actual Codex child agent read the plan through the GitHub connector, wrote and read the harness/report through `exec_command`, and ran shell commands. An explicit temporary file read/write/shell probe passed. This verifies executor access, not the target CLI protocol.

## Limits and next gate

The harness did not test duplicate Markdown IDs, dependency cycles, malformed JSON, state-mirror mismatch, CodeBuddy, or the shared CLI protocol in both IDEs. Full Task 02 remains incomplete pending the locally deferred CodeBuddy complement and independent review. The current user authorization to complete cloud CLI/tests remains in force. In the default workflow, work outside that authorization should wait for the full Task 02 gate before Task 03; this preflight does not create a new blocker for already authorized work.
