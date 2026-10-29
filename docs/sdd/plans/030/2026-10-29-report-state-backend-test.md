# Spec 030 Task 08 — report state and budget backend test report

Date: 2026-10-29  
Role: backend-tester  
Scope: `ResearchStore` report-generation state and budget slice; targeted tests only.

## Verdict

**PASS for the bounded store slice.** The requested state and reservation tests pass, and independent probes confirm conservative settlement of terminal timing anomalies, serialized concurrent claims, restart recovery, cross-version historical usage, and stale revision rejection. No production code was changed by this test task.

## Verification commands

| Command | Exit | Result |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_generation_state.py` | 0 | 22 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_version_reservation.py` | 0 | 17 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_generation_budget_recovery.py` | 0 | 5 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q tests/research/test_report_generation_state.py tests/research/test_report_version_reservation.py tests/research/test_report_generation_budget_recovery.py` | 0 | 44 collected; no collection errors |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | Naming passed |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/infrastructure/research_store.py tests/research/test_report_generation_budget_recovery.py` | 0 | All checks passed |

The three executed pytest files total 44 passing tests. An initial run of the new probe file had 4 passing and 1 failing because the probe expected a `state` key that the store result does not expose. The probe was corrected to inspect the documented top-level `revision` and `stage` fields; the final run passed 5/5. This was a test assertion issue, not a production failure.

## Independent probe evidence

- **Terminal timing anomalies across restart:** for both a missing terminal `ended_at` and an end earlier than `started_at`, settlement charged the full 300-second claim, recorded 300 seconds in report/task totals, left no held reservation, and reduced the 1,500-second task balance to 1,200 seconds.
- **Concurrent budget claims:** five simultaneous 500-second requests produced three allowed claims totaling exactly 1,500 seconds; no further time remained available.
- **Historical totals after restart and new version:** report version 2 retained version 1's 17 model loops, 29 tool calls, and 120 seconds. Its next claim saw only the remaining task budget.
- **State CAS after restart:** a second store instance using stale revision 0 received `ResearchReportGenerationStateConflict`; persisted revision 1 and stage `evidence_review` remained intact.

## Scope boundary

This verifies the store-level persistence and budget accounting only. It does not validate AgentRunner/application integration, public JSON projection of store-owned metadata, report publication/artifact/message recovery, full regression, live API behavior, or deployment. These remain outside this bounded test task.
