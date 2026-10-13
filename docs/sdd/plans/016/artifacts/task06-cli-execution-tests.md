# Task 06 CLI Event and Prompt Claim QA

## Scope

Independent QA of the CLI event path, prompt claim output, and claim behavior when prompt rendering fails. Changes were limited to tests and this report. The live event tests use the public CLI with a persistent owner process; the renderer failure test calls the CLI router with an injected `PromptError` while a separate live child owns the run.

## Coverage

- `test_cli_claim.py`: claim output keeps the template `prompt_hash`, reports the main-root-relative prompt path and SHA-256 of rendered bytes, and omits the rendered body and absolute path from stdout. The renderer failure case checks exit 6, `CLAIM_PROMPT_RENDER_FAILED`, null data, no error sentinel/path echo, a persisted `claimed` run and active lease, no prompt file, and visibility in status with `run_state:claimed` and `active_lease`.
- `test_cli_event.py`: a persistent live owner appends all six frozen event types. The test checks the first event changes the run to `running`, sets `started_at`, advances exact SQLite/JSONL sequence and payload state, refreshes the lease, and returns metadata only. Refusal cases cover a foreign executor, duplicate keys, NaN, a nonobject, credential and owner fields, and an absolute private path; the ledger and existing log remain unchanged and sensitive values are not echoed.
- `test_cli_event.py`: with the ledger absent, duplicate-key, NaN, and nonobject payloads fail as `EVENT_PAYLOAD_INVALID` before database lookup. A valid object returns `CATALOG_NOT_REBUILT`; neither the database, SQLite sidecars, nor run directory is created.
- `test_prompts.py`: the existing seven prompt rendering and refusal tests were included in focused verification.

## Validation

```text
/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_cli_event tests.sdd_tasks.test_cli_claim tests.sdd_tasks.test_prompts
Ran 17 tests in 32.468s — OK (exit 0)

/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_cli_event.py tests/sdd_tasks/test_cli_claim.py tests/sdd_tasks/test_prompts.py
All checks passed (exit 0)
```

## Draft and fixture corrections

The first event test draft had a missing closing parenthesis. Its initial unittest import and Ruff check failed on syntax before any test body ran; the syntax was corrected. The first event execution then exposed a fixture issue: runtime JSONL synchronization correctly refused the temporary repository because `.sdd/runtime/` was not ignored. The successful event fixture now adds that ignore entry; production synchronization checks were not changed. The initial claim assertion also expected a null prompt path and was updated to verify the frozen prompt path and rendered hash.

## Change accounting

Reviewed test-edit batches used actual additions plus deletions, not net size: claim prompt assertions +8/−2; initial event module +126/−0; event syntax repair +1/−1; event fixture ignore correction +2/−1; final renderer-failure and missing-database batch +79/−1 (event +38/−0, claim +41/−1). Across those batches the recorded total is 216 additions and 5 deletions (221 actual line changes). The final batch was 80 actual changes across two files.

The renderer failure is an injected exception-path test, not a process termination or restart test. No broad test suite was run; verification was limited to the 17 focused tests and Ruff command above.
