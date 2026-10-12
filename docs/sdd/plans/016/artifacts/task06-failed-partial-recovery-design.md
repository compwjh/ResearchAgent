# Task06 failed/partial recovery design

- Owner: protocol_review (architect, gpt-6-luna xhigh)
- State: design accepted in principle and frozen into [`TASK-PROTOCOL.md`](../../../TASK-PROTOCOL.md) §§5–6; root readback of the exact protocol diff is pending before Task06 production.
- Source: current Spec016 fail/retry and max-attempt requirements plus frozen TASK-PROTOCOL §§5–6.

## Existing mismatch

Task05's `recover_expired` represents a dead owner with an expired lease and transitions that active run to `abandoned`. Task06 `fail` represents a completed unsuccessful attempt; its run must stay terminal `failed` (or a validated `blocked` outcome), while a partial worktree remains available to the next attempt. A selector limited to abandoned runs cannot resume a terminal failed partial attempt. Treating failed as abandoned would falsify run history.

## Recommended contract

1. Keep the TaskRun state graph and SQLite tables unchanged. `recover_expired` alone creates `abandoned`; `fail` never does. `failed` remains terminal, and every retry creates a new run/attempt.
2. Use the already frozen `recovery_decision` event and exact action/decision pairs. A retryable `fail` records `requeued/unchanged` when baseline comparison is clean, or `preserved_for_recovery/partial` only when the allowed partial diff is verified recoverable. Run terminal state, lease closure, and this classification are one `BEGIN IMMEDIATE` transaction.
3. Add one local-only event type, with no new table/column: `workspace_observation`, payload exactly `{"schema":"sdd-workspace-observation/v1","snapshot":<WorkspaceSnapshot JSON>}`. It stores the final observed snapshot for that failed run, on the same run ID as its initial before snapshot. The observation is durable before failure-doc publication; finalization verifies it before writing the recovery decision. It contains no owner/token and is never exported to Git/result/summary.
4. `claim_next` may use only the Task's latest, unconsumed attempt as recovery source. Existing `abandoned + preserved_for_recovery/partial` stays valid. A `failed` source additionally requires a valid partial decision, its durable workspace observation, a closed lease, matching Task/prompt/base/worktree identity, and current workspace still equal to the recorded observation after discounting the verified documentation commits below. A failed run without this evidence is not silently treated as clean or abandoned.
5. For a partial failed source, the new Claim's `recovery_of` and `workspace_snapshot.source_run_id` point to the immediately previous failed run; copy its original before snapshot byte-for-byte. `load_recovery_snapshot` follows each source edge through failed/abandoned runs to the fresh `source_run_id=null` baseline and verifies full snapshot equality and all identity/hash bindings. A recovery_claim consumes its parent permanently; never select an older consumed attempt.
6. For `failed + requeued/unchanged`, verify the current workspace still matches the recorded clean observation, then create an ordinary fresh Claim with `recovery_of=null` and `source_run_id=null`. Any third-state hash/path/ref mismatch blocks without cleanup or overwrite.
7. Count consecutive failed outcomes against metadata `max_attempts` (default 3). The third failure leaves that Run `failed`, changes Task.status to `blocked`, and updates its three mirrors; preserve the worktree, but do not auto-claim past the cap. A blocked outcome also remains blocked. No failure is rewritten as success or abandonment.
8. A safe failed/blocked result publishes a documentation-only local commit through the existing completion journal, temporary index, ref CAS, and real-index reconciliation. `committed_paths` contain only that run summary and, when status changes to blocked, the Task/spec/README mirrors. No source/code path is committed; unrelated and pre-existing staged entries are preserved exactly. Never unstage/reset/clean them.
9. The journal's validated full `sdd-run-result/v1` object and matching `terminal_outcome` determine terminal state during replay: final DB CAS writes `failed` or `blocked`, closes the lease, and never writes `succeeded`. If result sensitivity checks, path checks, publication, or CAS fails, retain the journal and files and return a blocker; do not claim fail/commit success prematurely.
10. A documentation-only failure commit advances HEAD while `WorkspaceSnapshot.head/base_commit` remains the original baseline. Recovery may accept this difference only when every intervening commit is a contiguous first-parent chain of completed local journals for this Task's failed/blocked runs, each candidate has the recorded parent and tree diff exactly equals its summary/status-document allowlist and expected hashes. Any unreceipted commit, code-path commit, merge, wrong parent, or unexpected current document content is a base conflict. Compare source changes against the original snapshot; exclude only those verified journal-owned documentation commits. Preserve the original `base_commit` and all code hashes.

## Frozen protocol location

The public APIs, owner-authenticated CLI commands, event allowlist, exact workspace observation payload, failed-source eligibility, failure journal terminal-state rules, and first-parent documentation-commit receipts are frozen in the linked `TASK-PROTOCOL.md` section. That section is authoritative for implementation; this design artifact records the rationale and acceptance matrix without duplicating its signatures.

## Required acceptance cases before implementation approval

- Live-owner fail with unchanged, allowed partial, out-of-scope, and unknown baseline; only the first two get valid retry classification.
- Crash after observation but before docs commit; after docs commit/ref CAS but before DB failure finalization; after DB finalization but before journal complete. Replay must never create succeeded.
- Recovered failed partial keeps original hashes through at least two failed recovery generations; each `recovery_of/source_run_id` points to its immediate parent and consumed parents cannot be selected again.
- Exact documentation-only HEAD chain is accepted; injected source-code commit, unreceipted commit, user branch advance, content mutation after observation, or missing journal is rejected while preserving code and index state.
- First/second failed outcomes retry within cap; third updates blocked mirrors and stops scheduling. Pre-existing user staged paths remain byte-for-byte unchanged and are never included in failure commit.
