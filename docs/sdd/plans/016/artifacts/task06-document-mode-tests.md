# Task 06 Recovered Document Mode QA

## Scope

Verified recovery of journaled document modes and the atomic writer's file permissions. Test-only changes exercise `recover_expected_documents` and the public `atomic_write` helper; production changes were read back and approved by root.

## Coverage

- `test_completion_journal.py`: a synthetic prepared journal freezes Task and spec entries at Git mode `100755`. Replay writes both files as mode `0700`; a second replay leaves their execute bits intact. The fixture runs with `core.filemode` set to both `true` and `false`.
- `test_safety.py`: default atomic writes remain `0600`; `executable=True` writes `0700`; integer, null, and string values are rejected for the strict boolean option.
- Existing completion replay fault callbacks now accept and forward keyword arguments, so injected post-replace recovery cases remain compatible with `atomic_write(executable=...)`.

## Validation

```text
/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_completion_journal tests.sdd_tasks.test_safety
Ran 26 tests in 2.219s — OK (exit 0)

/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_completion_journal.py tests/sdd_tasks/test_safety.py
All checks passed (exit 0)
```

The first run of those 26 tests had two errors because existing patched writer callbacks did not accept the new `executable` keyword. The test callbacks were updated to forward keyword arguments, after which all 26 passed. This was a test wrapper compatibility issue.

## Limits and change accounting

The recovery test supplies synthetic frozen mode anchors. It checks that J2 honors `100755` entries under either repository `core.filemode` setting; J2 itself consumes those journal entries and does not inspect Git configuration. This does not verify real anchor creation by `prepare_completion_journal` or the separate source-anchor check.

Test edits were reviewed in two batches: +43/−2 (45 actual changes) for frozen-mode and atomic permission coverage, then +4/−4 (8 actual changes) for callback forwarding. Total: 47 additions and 6 deletions, or 53 actual changes. No broad suite was run.
