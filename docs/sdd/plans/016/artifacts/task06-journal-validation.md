# Task06 journal test validation

Baseline: `tests/sdd_tasks/test_completion_journal.py` was absent before this assignment.
First test slice: 131 added lines in that file; tests cover strict envelope round-trip, schema/time/hash/result/phase rejection, prepared-document preservation, and atomic fsync/replace faults.

## Validation

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_completion_journal` — exit 0; 5 tests passed.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_completion_journal.py` — exit 0.

## Remaining

J1/J2 cover journal primitives and document recovery; J3 covers Git index snapshots; J4 covers marker primitives, immutable expected-entry schema, owned-lock wrapper acquisition/replay/refusal against a real index, and expected-entry capture cases. Commit/ref CAS, reconciliation, ledger finalization, and the mandatory process-crash matrix remain untested. No commit was created.

## J2 document recovery

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_completion_journal` — exit 0; 12 tests passed (J1 + J2).
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_completion_journal.py` — exit 0.
- This expansion adds 141 test changes and 8 report changes (149 total); the next expansion awaits root readback.

## J3 Git index snapshot

- Baseline `tests/sdd_tasks/test_git_index.py` was absent; the current test file has 208 lines.
- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_git_index` — exit 0; 8 tests passed.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_git_index.py` — exit 0.
- Real Git fixtures cover staged outsider preservation, staged/unmerged refusal, special paths, unregistered roots, fake/symlink index paths, and HEAD/index races. Unmerged entries use `hash-object` and `update-index --index-info`; race wrappers execute real Git queries and mutate the fixture ref or index.

## J4 marker primitives, first slice

- Baseline `tests/sdd_tasks/test_git_index_lock.py` was absent; this slice adds 136 lines.
- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_git_index_lock` — exit 0; 3 tests passed.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_git_index_lock.py` — exit 0.
- A temporary Git index fixture verifies exact marker JSON, mode 0600, file fsync before hardlink, same-inode linking before temp unlink, and schema rejection. Refusal/fault windows remain for a later slice.

## J4 refusal and fault windows

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_git_index_lock` — exit 0; 7 tests passed (first slice plus this expansion).
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_git_index_lock.py` — exit 0.
- Actual temporary Git-index files verify foreign, malformed, and partial temp/lock bytes remain unchanged; injected short-write, link, unlink, and post-unlink directory-fsync failures preserve replayable state. Retry adopts the already-published lock, including when the temp name was removed.
- Publication assertions verify marker file fsync before hardlink, directory fsync before temp unlink, same-inode publication, and returned device/inode identity. These primitive tests do not exercise durable journal identity recording, the wrapper, or process-crash recovery.

## J4 expected Git-entry schema fixture

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_completion_journal` — exit 0; 13 tests passed (J1/J2 plus the expected-entry fixture).
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_completion_journal.py` — exit 0.
- The shared journal fixture now includes sorted expected entries; tests cover exact committed-path binding, ordering, permitted modes, 40/64-character blob IDs, paired deletion nulls, malformed entries, and immutability across journal updates. Blob-anchor generation, Git attribute/config refusal, and wrapper integration are not covered by this schema-only batch.

## J4 owned-lock wrapper with a real Git index

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_git_index_lock` — exit 0; 10 tests passed.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_git_index_lock.py` — exit 0.
- Registered temporary Git repositories use hash-object/update-index and commit-tree setup. The shape-only journal goes prepared → docs_writing → docs_written; wrapper tests cover durable marker/temp/identity replay, the temp-unlinked-before-journal-save window, late outsider-stage preservation, and target-stage drift refusal. Candidate expected blob anchors are not evidence in these wrapper-only fixtures.

## J4 wrapper identity-save and refusal windows

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_git_index_lock` — exit 0; 13 tests passed.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_git_index_lock.py` — exit 0.
- Real Git fixtures inject failure before the durable identity journal save and replay the published lock; they also preserve a foreign `index.lock` plus this run's temp marker, and refuse a valid third-party index replacement after marker identity was recorded. Assertions retain exact index/lock bytes and prior journal observation.
- These are deterministic filesystem fault simulations; they do not claim separate-process crash recovery, CAS, index reconciliation, or commit behavior.

## Expected Git-entry capture basics

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_git_expected_entries` — exit 0; 3 tests passed.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_git_expected_entries.py` — exit 0.
- Real Git fixtures verify raw symlink link-text blob identity (distinct from target bytes), expected-document UTF-8 content hashing, deletions, UTF-8 path ordering, tracked executable-mode preservation with `core.filemode=false`, new executable detection, and refusal of active conversion attributes or `core.autocrlf=true`.

## Expected Git-entry capture races

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_git_expected_entries` — exit 0; 6 tests passed.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_git_expected_entries.py` — exit 0.
- Actual Git/filesystem mutations between capture reads verify refusal for symlink link-text retargeting with identical resolved bytes, mode change, index replacement, HEAD advance, and config change. Disabled attributes are accepted; `core.autocrlf=input` and invalid boolean config fail closed. The injected races are deterministic in-process tests, not separate-process crash/CAS coverage.

## J5 candidate blob, tree, and commit

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_git_candidate` — exit 0; 2 tests passed.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_git_candidate.py` — exit 0.
- Real journal fixtures capture expected blobs before `prepared`, recover documents through `docs_written`, and acquire the owned index lock. Verified blob storage, isolated candidate tree construction, and unreferenced candidate commit preserve HEAD, real index bytes, and lock bytes while excluding a pre-staged outsider. Retargeted symlink text with identical resolved bytes, mode drift, document drift, and active filter attributes refuse.
- The `index_after_prepared` input is a shape-only J6 fixture derived from target anchors; reconciliation image creation/install, ref CAS, and process-crash recovery are not covered.

## J5 candidate path and race refusals

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_git_candidate` — exit 0; 5 tests passed.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_git_candidate.py` — exit 0.
- Real alternate-index replacements with target staged or unmerged entries refuse without changing index/lock bytes. Candidate trees verify new, deleted, and rename-shaped paths containing spaces, newline, and shell metacharacters; a malformed `index_after` anchor refuses.
- A deterministic HEAD advance after temporary tree construction makes candidate creation refuse before publishing a candidate ref. This tests refusal around movement; it is not a CAS or separate-process crash test.

## J5 post-CAS source-anchor checks

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_git_candidate` — exit 0; 6 tests passed.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_git_candidate.py` — exit 0.
- After fixture code moves HEAD manually to the candidate while the real index retains its original bytes, `check_source_anchors` passes; symlink text, source bytes, mode, or expected-document drift then refuses. Deleted tree paths are checked from parsed `ls-tree` output. This verifies source-anchor behavior only, not ref CAS.

## J5 expected-old ref CAS and replay

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_git_candidate_cas` — exit 0; 2 tests passed.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_git_candidate_cas.py` — exit 0.
- The real J6 fixture prepares `index-after`, writes those exact bytes into the identity-pinned owned lock, and durably journals `lock_index_durable` plus `commit_pending`. CAS moves the validated feature branch once; replay at `HEAD=candidate` performs no second `update-ref`. Both calls preserve the old real-index bytes and lock image/identity; a reference-transaction hook marker remains absent.
- Unexpected HEAD refuses without changing the competitor ref, real index, or lock image. These deterministic tests do not cover process death between CAS and journal advancement.

## J5 update-ref race and public lock-image writer

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_git_candidate_cas` — exit 0; 3 tests passed.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_git_candidate_cas.py` — exit 0.
- The fixture now uses public `write_owned_index_image` and verifies the exact `index_after` hash in the lock. A real competing `update-ref` immediately before expected-old CAS wins; candidate CAS returns refusal and preserves that ref, the old real index, and the owned lock image/identity with journal phase still `commit_pending`.

## J5 CAS lock, branch, root, and partial-journal refusals

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_git_candidate_cas` — exit 0; 7 tests passed (42.477s).
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_git_candidate_cas.py` — exit 0.
- The actual Git fixture verifies refusal for altered owned-lock bytes, a same-bytes replacement lock inode, a mismatched task branch, a nested non-root path, and an omitted worktree-registry entry. The registry response is deterministically injected at the Git wrapper boundary; no real registry files are modified.
- A partial in-memory journal derived from `read_journal` with `index_after=None` fails schema validation before Git mutation. Each refusal compares actual refs, index bytes, lock bytes and inode, and persisted journal bytes before and after.

## Task06 context, prepare, and end-to-end lifecycle QA

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_lifecycle_context` — exit 0; 2 tests passed in 4.350s. Ruff on `tests/sdd_tasks/test_lifecycle_context.py` — exit 0.
- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_completion_prepare` — exit 0; 2 tests passed in 5.291s. Ruff on `tests/sdd_tasks/test_completion_prepare.py` — exit 0. The pure builder is checked against actual `validate_result` reports and captured Git/workspace state; failed/blocked receipts are explicitly skipped and not described as executed validation.
- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_completion_lifecycle tests.sdd_tasks.test_completion_prepare` — exit 0; 3 tests passed in 17.644s. Ruff on both files — exit 0.
- The end-to-end fixture runs the declared command through `run_validations`, records the actual runner snapshot, validates a report using server end time and measured Git diff counts, durably publishes a prepared journal, then runs the dispatcher through CAS, index installation, and terminal SQLite finalization. It checks complete-phase replay, the candidate branch/HEAD, index tree and clean worktree, the committed source bytes, lease removal, result query, and catalog rebuild/result query. The fixture intentionally leaves the main-worktree Task copy stale after canonical status publication; catalog rebuild reports and the test asserts `stale_task_copies_ignored`.
- These are lifecycle success and prepare-boundary results; no separate-process crash-recovery case has yet been run.
