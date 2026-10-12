# Task 05 recovery validation — backend-dev (Luna xhigh)

## Scope and result

Implemented frozen `recover_expired(conn, run_id: str, observed_owner_alive: bool, decision: RecoveryDecision, *, now: str) -> RecoveryReport` in `scripts/sdd_tasks/leases.py`. The caller must hold the common maintenance lock. The helper obtains the fixed main root from `PRAGMA database_list`, re-parses the canonical registered Task, then under `BEGIN IMMEDIATE` verifies owner death on this host, lease/run/task/token/hash/status bindings, expiry, event integrity, original workspace snapshot, and the recomputed decision. Success atomically sets the run to `abandoned`, records `ended_at` and `OWNER_DEAD_LEASE_EXPIRED`, deletes the lease, and appends `recovery_decision` with the exact `sdd-run-recovery/v1` payload. `RecoveryReport` is frozen. Task documents/status and worktree files are not modified.

W3c updated `recovery_snapshots.py` to locate the unique canonical Task file by validated Task ID/spec inside the registered worktree. Its API is unchanged and it still checks canonical Task/hash drift and the original clean baseline. R2 makes recovery-event JSON reject non-standard `NaN`/`Infinity` constants.

## Code change counts

- Recovery transaction R1, against saved 110-line `leases.py`: 136 additions, 1 deletion (137 changed lines).
- Strict event JSON R2: 5 additions, 1 deletion (6 changed lines); final `leases.py` is 249 lines. Cumulative diff against R1 pre-snapshot: 140 additions, 1 deletion (141 changed lines).
- Frozen API typing T1: annotated `decision` as `RecoveryDecision`; 2 additions, 2 deletions (4 changed lines), no runtime behavior change.
- Canonical loader W3c, against saved 160-line `recovery_snapshots.py`: 10 additions, 1 deletion (11 changed lines); final module is 169 lines.
- The independent recovery test file is restore_workspace's change: 81 additions, 4 deletions from its saved baseline (85 changed lines). No test file was edited in this implementation slice.

## Verification (actual results)

- Python 3.9.25 `py_compile` for `leases.py` and `recovery_snapshots.py`: exit 0.
- Ruff for both production modules and both recovery test modules: exit 0, all checks passed.
- `unittest tests.sdd_tasks.test_lease_recovery`: 5/5 passed, exit 0; includes real exited-child owner, partial preservation, forged decision, corrupted bindings/baseline/task/event, exact expiry, and NaN payload cases. Independent report: `/tmp/spec016-preflight/task05-tests-lease-recovery-expansion.md`.
- `unittest tests.sdd_tasks.test_recovery_snapshots`: 7/7 passed, exit 0; independent report: `/tmp/spec016-preflight/task05-tests-recovery-snapshots.md`.
- `unittest tests.sdd_tasks.test_leases`: 4/4 passed, exit 0; independent report: `/tmp/spec016-preflight/task05-tests-leases.md`.
- A real temporary Git/SQLite smoke kept a child owner alive (recovery refused with no row changes), reaped it, then recovered the expired unchanged run; asserted abandoned state, removed lease, UTC end time, error code, and exact event payload. Exit 0.
- A temporary canonical-worktree smoke passed a main-tree TaskDefinition to `load_recovery_snapshot` and verified exact baseline return. A strict JSON smoke rejected `NaN` as `RECOVERY_EVENT_INVALID`. Both exit 0.

Root has read back the recovery implementation, W3c and R2. T1 only adds the frozen API type annotation and awaits readback. This report records slice evidence only; final Task 05 GO remains pending.
