# Task06 journal test validation

Baseline: `tests/sdd_tasks/test_completion_journal.py` was absent before this assignment.
First test slice: 131 added lines in that file; tests cover strict envelope round-trip, schema/time/hash/result/phase rejection, prepared-document preservation, and atomic fsync/replace faults.

## Validation

- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_completion_journal` — exit 0; 5 tests passed.
- `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_completion_journal.py` — exit 0.

## Remaining

J1/J2 cover journal primitives and document recovery; J3 covers Git index snapshots; J4's first slices cover marker primitives and their refusal/fault windows, and its schema fixture covers immutable expected Git entries. Wrapper integration, blob-anchor generation/conversion checks, commit/ref CAS, reconciliation, ledger finalization, and the mandatory crash matrix remain untested. No commit was created.

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
