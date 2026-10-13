# Task 06 Validation Runner Tests

Updated: 2026-10-13. This report records independent tests of the frozen real-process helper and public validation runner.

## Process helper slice 1

`tests/sdd_tasks/test_validation_process.py` launches real Python subprocesses. It covers successful and nonzero exits, missing executable, private 0600 logs, secret isolation from the parent process output and record, refusal to overwrite an existing log, hard timeout with process-group grandchild termination, and 1 MiB output prefixes with full-stream hashes.

| Command | Exit | Result |
|---|---:|---|
| `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_validation_process` | 0 | 2 real-subprocess tests passed under Python 3.9.25. |
| `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_validation_process.py` | 0 | All checks passed after import cleanup. |

## Process helper slice 2

Added invalid argument/timeout checks, injected second-reader startup failure after a real grandchild PID is observed alive, then checked delayed grandchild write prevention. A log-write failure returns only a fixed error code. The symlink-parent error-code case is held for the pending stable error mapping.

| Command | Exit | Result |
|---|---:|---|
| `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_validation_process` | 0 | 4 real-subprocess tests passed under Python 3.9.25. |
| `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_validation_process.py` | 0 | All checks passed. |

## Process helper slice 3

Added a real symlinked log-parent refusal case. It checks the fixed `VALIDATION_LOG_UNSAFE` error, confirms the validation command never starts, and confirms neither stream log is created through or beside the link.

| Command | Exit | Result |
|---|---:|---|
| `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_validation_process` | 0 | 5 tests passed under Python 3.9.25. |
| `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_validation_process.py` | 0 | All checks passed. |

## Active context slice 1

`tests/sdd_tasks/test_validation_runner.py` uses a current-time live claim from the real Git/SQLite fixture. `_active_context` success compares all ledger rows before and after and closes its returned connection. Refusal cases cover forged branch/base/attempt, task prompt, owner PID/token, missing-ledger non-recreation, paused Spec, and unsatisfied gate. These tests exercise context resolution only; they do not execute validation commands.

| Command | Exit | Result |
|---|---:|---|
| `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_validation_runner` | 0 | 4 tests passed under Python 3.9.25. |
| `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_validation_runner.py` | 0 | All checks passed. |

## Public runner slices 1–2

Added six real `run_validations` tests using live Git/SQLite claims and declared `python3` argv commands. They cover successful execution and the exact command-list/receipt SHA-256 bindings; mode 0700 invocation directories and mode 0600 receipt/log files; full stream hashes and output retained only in the private log; nonzero exit 7 with a later command still attempted; out-of-scope workspace changes producing `receipt.valid=false`; and repeated invocations retaining separate logs while `receipt.json` points to the latest receipt.

The timeout case uses a one-second hard timeout. It observes the spawned child’s start marker, confirms the timed-out parent exits with a signal status, waits beyond the child’s scheduled delayed write and confirms it never occurs, checks the timeout stream log/hash, and confirms the following declared command ran.

The symlinked `.sdd/runtime/runs` refusal is caught by the earlier ignore-path check as `VALIDATION_RUNTIME_NOT_IGNORED`; command execution, receipt creation, escaped writes, and ledger changes are absent. This verifies fail-closed behavior at that check, not the deeper `VALIDATION_RUNTIME_UNSAFE` path check.

| Command | Exit | Result |
|---|---:|---|
| `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_validation_runner -k run_validations` | 0 | 6 public runner tests passed under Python 3.9.25 across the two bounded slices. |
| `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_validation_process tests.sdd_tasks.test_validation_runner` | 0 | 15 tests passed under Python 3.9.25: 5 process helper, 4 active-context, and 6 public runner tests. |
| `/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_validation_process.py tests/sdd_tasks/test_validation_runner.py` | 0 | All checks passed. |
