# Candidate evaluation → approved plan → auto-import evidence

## Audit result

The existing narrow seam is sufficient and was not changed:

1. `Orchestrator._persist_agent_selections` accepts only evaluator IDs from the
   Search Worker whitelist and stores the task's frozen selection projection.
2. `PlanApprovalService` persists the approved plan and materializes the
   Research task.
3. `ApprovedPlanAutoImporter` delegates to `ResearchAcquisitionService`, which
   creates the existing `PaperImportBatchService` batch with the task-scoped
   issue recorder.
4. The batch CAS transition invokes that recorder after an item reaches
   `waiting_login`/`failed`; the issue store retains the candidate and task
   handles without introducing a second import state machine.

## Deterministic regression

`tests/research/test_candidate_acquisition_integration.py` wires those real
components with fixed SQLite stores and two local `PaperCandidate` fixtures.
The injected importer returns one indexed result and raises the stable
`LOGIN_REQUIRED` error for the other candidate. No external URL is requested.

Observed assertions:

- both evaluator-kept IDs become the durable Research selection;
- the approved task starts exactly one automatic import batch;
- the successful candidate reaches `completed`;
- the login-limited candidate reaches `waiting_login`;
- exactly one open issue is projected, for `paper-login`, with
  `task_ids == [task_id]`, `reason_code == LOGIN_REQUIRED`, and the batch ID.

## Verification

- `.venv/bin/python -m pytest -q tests/research/test_candidate_acquisition_integration.py` — exit 0, `1 passed`.
- `.venv/bin/python -m pytest -q tests/research/test_candidate_acquisition_integration.py tests/paper_discovery/test_approved_plan_auto_import.py tests/research/test_acquisition_bridge.py tests/research/test_plan_approval_contract_backend.py` — exit 0, `26 passed`.
- `.venv/bin/ruff check tests/research/test_candidate_acquisition_integration.py` — exit 0, all checks passed.
- `.venv/bin/python scripts/check_test_layout.py` — exit 0, `test layout: ok`.
- `git diff --check -- tests/research/test_candidate_acquisition_integration.py docs/sdd/plans/032/artifacts/task-14/candidate-import-integration.md` — exit 0.

## Scope and limitations

This is an offline integration regression. It does not claim real PDF download,
browser login, or external catalog availability; those remain covered by the
existing controlled smoke evidence and deployment-environment checks.
