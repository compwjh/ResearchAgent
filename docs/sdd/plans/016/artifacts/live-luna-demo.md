# Spec 016 Task 09 live Luna demo

**Date:** 2026-10-15 UTC  
**Run:** `5cbcf851-add2-4558-a0ed-acdc5041332c`  
**Task:** `spec-016-task-09` · **Role:** `backend-dev` · **Attempt:** 1

## Isolated claim

The run used a disposable Git fixture with a main worktree and canonical linked worktree on `feature/spec-016-live-luna-demo`. The real CLI `doctor` returned `healthy: true`; its only diagnostic was `stale_task_copies_ignored` for duplicate fixture Task copies. The initial `rebuild` found two Tasks, deduplicated two copies, and imported no runs. Real `next --claim` claimed Task 09 from base commit `54dba5f1d3bea9879b7d636e558312c62c3bad41` and rendered the seven-label prompt.

The source CLI checkout HEAD recorded immediately before completion was `6c48f68a0c9ade908fcd0bd7d5d6f5b1911b4e90`.

## Actor result and completion

The live `gpt-6-luna` actor changed only `scripts/sdd_tasks/allowed.txt` to `spec-016-task-09: completed by Luna` followed by a newline. Its SHA-256 is `562c8db7ed88e191a5aa4e040710e91fd3c72f7fe9ce2313e10aad20cce91081`.

The actor's result draft used `sdd-run-result/v1`, with unknown token and tool counts set to `null`. The real CLI `complete` accepted it, reran the registered exact-content validation, and returned `OK`. The validation exited 0 (`validation passed`, 16 ms). The completed result records `outcome: succeeded`, `state: succeeded`, start `2026-10-15T10:03:32.585472Z`, end `2026-10-15T10:08:46.312697Z`, and server duration 313727 ms. The canonical run summary was written at `docs/sdd/runs/016/task-09/5cbcf851-add2-4558-a0ed-acdc5041332c.md` in the fixture worktree.

The real `result --json` and `metrics --format json` queries returned the same run ID, hashes, outcome, one changed file, model, and null token/tool metrics. Metrics identify the run state as `succeeded`, with one addition and one deletion.

## Rebuild evidence

After completion, CLI `status` showed Task 03 and Task 09 completed, with no eligible, waiting, blocked, or running Tasks. `rebuild` returned two Tasks, one run, and two deduplicated copies; the following `next --claim` returned `NO_TASK`.

To check persistence, the fixture database was renamed to `.sdd/runtime/task-ledger.sqlite3.before-rebuild`, then the real CLI rebuilt a fresh database from the fixture documents and canonical run summary. The new ledger again contained two Tasks and one run. Subsequent `status`, `result`, and `metrics` matched the pre-deletion state, and `next --claim` again returned `NO_TASK`. No run or lease rows were fabricated.

Fixture paths are relative; this report contains no absolute private filesystem paths.
