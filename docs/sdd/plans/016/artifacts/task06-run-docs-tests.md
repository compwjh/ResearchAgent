# Task 06 Run Summary Tests

## Scope

Added `tests/sdd_tasks/test_run_docs.py` with four tests for the summary builder and writer.
The builder coverage checks deterministic rendering, no filesystem changes, strict JSON marker
blocks, task and claim metadata binding, model preservation, unknown token metrics, sensitive
text, and actual private owner token rejection.

The writer coverage checks that a main-root argument resolves to the registered canonical
worktree path, refuses to create missing parent directories, and rejects a symlink parent
without touching its target. A written document is parsed by `scan_summaries`; the test also
checks that the main-root summary path and captured main-tree files remain unchanged.

## Validation

```text
/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_run_docs
Ran 4 tests in 2.480s — OK

/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_run_docs.py
All checks passed!
```

The fixture emits the expected `stale_task_copies_ignored` catalog warning while creating its
registered worktree. All filesystem and ledger fixtures are temporary.
