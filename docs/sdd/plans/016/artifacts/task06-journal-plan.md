# Task06 completion journal / Git index slice plan

- Reviewer/planner: `protocol_review` (architect, gpt-6-luna xhigh)
- Basis: `docs/sdd/TASK-PROTOCOL.md` §6, with the root-approved private journal v1 byte/mode safety correction recorded below. This is a technical correction to the unreleased contract; user-visible scope is unchanged.
- Scope: completion journal, candidate commit construction, expected-old ref CAS, real index reconciliation, crash recovery. Prompt/result/event/metrics are prerequisites or separate Task06 slices, not included here.
- Safety gate: no automatic success commit until every crash-boundary test below passes in an isolated temporary Git repository.

## Frozen invariants to preserve

1. Validate result, Task/Prompt hashes, commands, artifacts, allowed diff and base before the first durable journal. Capture real index snapshot and write/fsync `prepared` journal before any Task/spec/README/DB mutation.
2. Journal updates and each document write use same-directory temp, file fsync, atomic replace, parent fsync. Advance phase durably before the corresponding side effect. Recovery accepts only exact before-hash or expected-after-hash; any third value blocks without overwrite.
3. Candidate commit uses a temporary `GIT_INDEX_FILE`; exact candidate paths, modes and blobs must equal immutable `expected_git_entries`, whose path set is exactly `committed_paths` (including every expected document). Never include unrelated staged entries in the candidate.
4. Durable candidate hash precedes `update-ref <branch> <candidate> <original_head>`. Ref mismatch blocks; never force update, push, merge, reset, stash, checkout or clean.
5. The real `index.lock` is created from a fully written/fsynced marker using no-replace publication. Journal records token and device/inode before replacing marker bytes. Unknown locks are never removed or overwritten.
6. While holding owned `index.lock`, snapshot the then-current real index. Target entries must still match the original snapshot and have no user staged/unmerged delta; non-target entries from this later snapshot are preserved. Build/index-after contains candidate entries only for target paths.
7. Install reconciled index atomically only after ref CAS and exact HEAD/index/lock checks. Commit TaskRun success and lease closure with owner/hash/state CAS in one SQLite transaction last; recovery is idempotent. Any uncertainty retains journal and returns recovery-required.

## Required private journal v1 byte/mode anchor

Before the first durable `prepared` journal, freeze `expected_git_entries` for every `committed_paths` path, sorted by UTF-8 path bytes. Each entry is exactly `{path, mode, object_id}`: created or modified blobs use mode `100644`, `100755` or `120000` and a full repository-format blob OID; deletion uses null mode and OID. Compute OIDs with `git hash-object --stdin` without `-w` or `--path`, from raw no-follow file bytes, symlink link-text bytes, or expected document UTF-8 bytes. Keep resolved artifact-content hashes separate from symlink blob hashes. Honor the original index mode for an already tracked path when effective `core.fileMode=false`; infer new-path mode from raw type/executable bit.

Refuse before journaling when a committed path has active `filter`, `working-tree-encoding`, `text`, `eol`, `crlf` or `ident` attributes, or effective `core.autocrlf`; allow unset/unspecified or explicitly disabled attributes and unset/false `core.autocrlf`. Do not edit Git configuration. Candidate tree, reconciliation index, replay and pre-CAS checks compare exact path/mode/blob OID to the immutable entries, so same resolved symlink target does not hide changed link text or mode. Extend the full journal schema and strict validator for the required field, with a follow-up fixture covering sorted exact entries, deletion, executable/symlink modes, conversion refusal, `core.fileMode=false`, and post-validation link-text/mode drift. This is a private, unreleased v1 technical correction, not new product scope.

## Assignment sequence

Every assignment changes at most two files and 150 added/deleted lines total; a test expansion gets its own follow-up assignment. Each handoff states the exact functions, changed-line count, command/exit code, and unresolved crash point.

| Slice | Small implementation boundary | Required evidence before next slice |
|---|---|---|
| J1 journal primitives | `completion_journal.py` atomic envelope read/write, exact schema/phase allowlist, monotonic phase validation; separate focused test assignment | Round-trip, duplicate/unknown field rejection, fsync/replace fault semantics; no writes outside temp fixture |
| J2 transition recovery | Add one recovery decision helper in `completion_journal.py`; focused tests | `prepared/docs_writing/docs_written` recovers each document from before/after hashes, blocks third hash; kill between doc replace and phase update |
| J3 index snapshot | `git_index.py` parse `ls-files --stage -z`, deterministic target/non-target entries and hashes; focused tests | Preserve stage/mode/object IDs, path bytes with spaces/newlines, unmerged entries detected; independent pre-staged outsider remains outside candidate |
| J4 owned lock | `git_index.py` marker temp, fsync, no-replace hard-link publication, durable identity checks; separate fault tests | Fault before/after each marker fsync/link/unlink; recognize only journal token/inode; existing/unknown lock byte-identical after refusal |
| J5 candidate and ref CAS | `completion_git.py` temporary-index candidate tree, exact path/blob check, durable candidate handoff, expected-old `update-ref`; separate fixture tests | Candidate excludes outsider stage; target stage drift/unmerged stage/HEAD race refuses; candidate creation without CAS never changes branch |
| J6 index reconciliation | `git_index.py` preserve non-target snapshot entries, prepare `index_after`, write owned lock contents in place, atomic install after CAS; separate recovery tests | Crash before/after lock write, after ref CAS, after index rename; detect HEAD=candidate + index_after without double-writing; retain outsider stage |
| J7 ledger finalization | `completion_journal.py`/lifecycle helper owner/hash/state CAS + terminal phase; isolated DB tests | Crash after DB commit before `complete` replays idempotently; mismatched owner/hash/state leaves run non-succeeded and journal intact |

J1–J7 rows are planning boundaries, not permission to exceed the per-assignment line limit. Split any row into implementation and tests, or smaller test batches, as needed. Module names may follow existing Task06 layout if each handoff keeps the boundary and public Task-protocol API unchanged.

## Mandatory crash matrix

- Journal `prepared` durable, then process death before first document write: recovery sees all original hashes and resumes.
- Each expected document atomic replace succeeds, process dies before phase advance; repeat for a partial multi-document write. Recovery recognizes exact after-hash and continues without duplicate/partial content.
- Temporary candidate commit object exists but its hash was not durably journaled: branch and real index stay unchanged; do not infer/commit the object.
- `commit_pending` durable before ref CAS: death before CAS resumes only if HEAD is `original_head`; death after successful CAS but before `committed` record recognizes `HEAD=candidate` and continues.
- Marker temp/`index.lock` publication and identity journal windows: recover only a complete exact token marker or durable device/inode match; malformed/foreign lock remains untouched.
- `index_after_prepared`/lock contents partial: real index remains `index_observed_before`; recover may reconstruct only the owned lock from durable `index_after`.
- Death after `os.replace(index.lock, index)` but before phase write: accept completion only when HEAD=candidate and the entire real index equals `index_after`, including non-target entries.
- Death after SQLite terminal transaction but before journal `complete`: verify DB row/lease exact terminal values, then mark journal complete idempotently; otherwise block.

## Isolated fixture and exit criteria

Use a temporary bare remote-free Git repository with one branch/worktree, a pending fixture Task, and a pre-staged unrelated path. Inject faults at each listed syscall/phase boundary. Assert branch ref, real index entries, Task/spec/README bytes, DB run/lease state, and journal phase after every restart. Add races for concurrent ref movement and user index mutation between initial snapshot and lock acquisition. Refuse unsupported no-replace filesystem behavior without touching existing index.lock. Run Python 3.9 stdlib tests plus Ruff/compileall; record exact commands and exit codes. Do not claim macOS/CodeBuddy coverage absent real execution.

Only after the complete matrix passes may the CLI wire `complete` to the lifecycle module. Keep Task06 `fail` and report-only `recover` paths from invoking the success commit transition. A failure preserves allowed partial work for the established Task05 recovery protocol.
