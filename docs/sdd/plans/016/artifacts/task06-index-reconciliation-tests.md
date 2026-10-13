# Task 06 J6 Git Index Reconciliation QA

## Scope

Verified the recovered `test_git_reconciliation_index.py` draft against the public index preparation, owned-lock write, candidate creation, branch CAS, committed-journal, and index installation path. This QA turn did not edit test or production source.

The fixture used by the public install tests prepares the target index image, writes it into the owned lock, creates the candidate commit, performs `reconcile_candidate_ref`, and persists `committed` / `ref_committed` before calling `install_reconciled_index`.

## Coverage

The module has nine test methods:

1. Private target-image preparation preserves HEAD, the live index, the owned lock marker, and staged `outsider.txt`.
2. Injected image publish and journal-write faults preserve state and allow replay.
3. Foreign, symlink, and hard-linked target images are refused without state changes.
4. Partial owned-lock writes recover through the same inode and replay stage four.
5. Owned-lock fsync failure replays the exact image without replacing the inode.
6. Foreign lock inode and foreign lock content are refused.
7. Installation consumes the owned image, preserves the staged outsider, and is idempotent.
8. Injected post-rename faults at rename return, directory fsync, and journal phase write replay with the index installed and lock absent.
9. Unknown live index and foreign lock states are refused without changing the ref or saved image.

The injected failures exercise exception recovery in the running process. They do not kill and restart a process, so this report does not treat them as OS-crash tests. This module does not include install-time competing-ref or branch-mismatch refusal cases.

## Validation

```text
/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_git_reconciliation_index
Ran 9 tests in 100.401s — OK (exit 0)

/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_git_reconciliation_index.py
All checks passed (exit 0)
```

## Change accounting

The recovered test draft is 415 lines and was not modified during this verification turn. No saved copy of the earlier 284-line draft was found in `/tmp` or the worktree, so the earlier recovery's exact added/deleted line count cannot be established. This turn added this report and its progress log only; no production files were changed by this QA work.

## Follow-up: ledger-finalizing installed-state replay

The module now has ten test methods. The added `test_ledger_finalizing_replay_proves_installed_index_without_writes` starts from a real committed candidate, installs the index, advances the journal to `ledger_finalizing`, and verifies two installer replays preserve the exact installed index bytes and inode, candidate HEAD, missing lock, and journal bytes. It then changes the staged outsider entry and confirms replay refuses with `GIT_RECONCILIATION_INSTALLED_STATE_CHANGED` while preserving the altered index, candidate HEAD, absent lock, journal, and saved image. This exercises the installer boundary; the fixture has no ledger database and makes no claim about SQLite finalization.

The isolated phase regression passed 1/1 in 9.441 seconds. The full updated module passed 10/10 in 219.997 seconds. Ruff passed. The prior accepted-source run of the original nine methods also passed 9/9 in 74.963 seconds with Ruff passing. The new test batch added 33 actual lines. The module does not add install-time competing-ref or branch-mismatch refusal cases, and its injected replay faults are not OS process-crash tests.
