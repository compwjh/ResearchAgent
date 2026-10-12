# Task 06 Owner and Events Tests

Updated: 2026-10-12. This focused artifact records SQLite owner-resolution and Events API tests.

## Owner coverage

`tests/sdd_tasks/test_run_owner.py` uses a real claimed fixture, current UTC time, and a live child PID captured by `current_owner`. It checks that valid resolution returns the persisted identity and token without exposing the token in `repr`, and that the resolver leaves ledger rows unchanged.

Read-only rejection cases cover wrong executor, wrong PID, lease/run task binding, private owner token mismatch, remote host, dead process, process start mismatch (PID reuse), expired lease, terminal run, canonical Task hash drift, and mirror drift. Each case compares the complete ledger tables before and after resolution.

## Validation

| Command | Exit | Result |
|---|---:|---|
| `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_run_owner` | 0 | Python 3.9.25; both test methods and 11 refusal subcases passed. |
| `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_run_owner.py` | 0 | All checks passed. |
| `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_events` | 0 | Python 3.9.25; 3 test methods passed, including 11 invalid-input subcases. |
| `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_events.py` | 0 | All checks passed. |
| `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_run_owner tests.sdd_tasks.test_events tests.sdd_tasks.test_event_logs` | 0 | Python 3.9.25; all 8 methods passed, including 27 refusal subcases. |
| `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_run_owner.py tests/sdd_tasks/test_event_logs.py` | 0 | All checks passed. |

## Events API coverage

`tests/sdd_tasks/test_events.py` exercises all six public event types, contiguous sequence numbers after `workspace_snapshot`, the first transition to `running`, stable `started_at`, and the 120-minute lease refresh. Invalid private fields, exact owner token, credentials, reserved type, unserializable and non-object payloads, future time, wrong owner/token, expired lease, and nested transaction each preserve ledger rows. An injected event insert failure verifies run, lease, and event changes roll back together. JSONL replay is outside this SQLite test batch.

`tests/sdd_tasks/test_event_logs.py` checks prefix append and byte-stable replay; private directory/file modes; read-only rejection of foreign or malformed rows, symlinks, unsafe modes, and unignored paths; and SQLite-first recovery after an injected atomic-write failure. The fixture adds `.sdd/runtime/` to the main temporary repository's `.gitignore` after taking the canonical worktree snapshot, leaving that clean snapshot unchanged.

No production files were changed by this test batch.
