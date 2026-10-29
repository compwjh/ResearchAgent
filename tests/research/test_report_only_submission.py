from __future__ import annotations

import json
from contextlib import ExitStack
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.api import routes_research
from backend.app.main import app
from backend.app.memory.repository import OWNER_ID, MemoryRepository
from backend.app.platform.bootstrap import override_provider
from backend.app.research.application.evidence_matrix import EvidenceMatrixService
from backend.app.research.application.research_service import ResearchService
from backend.app.research.domain.models import (
    ResearchPaperSelection,
    ResearchPlan,
    ResearchSession,
    ResearchTask,
    ResearchWorkItem,
)
from backend.app.research.infrastructure.research_store import ResearchStore


class _RecordingExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, function, *args, **kwargs):
        self.calls.append((function, args, kwargs))
        return object()


def _matrix(task_id: str) -> dict:
    return {
        "schema_version": "evidence-report-v1",
        "task_id": task_id,
        "research_task_id": task_id,
        "plan_version": 1,
        "claims": [{"claim_id": "claim-1", "task_id": task_id, "topic": "methods", "statement": "bounded", "status": "supported", "evidence_ids": ["evidence-1"]}],
        "evidence": [{"evidence_id": "evidence-1", "claim_id": "claim-1", "task_id": task_id, "paper_id": "paper-1", "evidence_level": "abstract", "stance": "supports", "status": "available"}],
        "dimensions": [{"dimension_id": "dimension-1", "label": "Method", "definition": "method"}],
        "cells": [{"claim_id": "claim-1", "paper_id": "paper-1", "dimension_id": "dimension-1", "relation": "supports", "summary": "bounded", "evidence_ids": ["evidence-1"]}],
        "limitations": [],
    }


def _seed(tmp_path, monkeypatch, *, task_status: str = "completed", candidates: bool = True, with_session: bool = True):
    task_id = f"report-only-{uuid4().hex}"
    memory = MemoryRepository(tmp_path / f"memory-{task_id}.sqlite3")
    conversation, user, _activity = memory.create_conversation_messages(
        OWNER_ID, "compare evidence", None, "user-message", "normal"
    )
    store = ResearchStore(tmp_path / f"research-{task_id}.sqlite3")
    task = ResearchTask(
        task_id, OWNER_ID, conversation.conversation_id, "compare evidence", "en", "balanced", False,
        5, 900, task_status, 1, "2026-10-30T00:00:00Z", "2026-10-30T00:00:00Z",
    )
    store.create_task(task)
    store.create_plan(ResearchPlan(
        task_id, 1, "approved", '["methods"]', "completed", "2026-10-30T00:00:00Z", "test-model",
    ))
    session = ResearchSession(
        f"session-{task_id}", OWNER_ID, conversation.conversation_id, user.message_id,
        f"intake-{task_id}", "completed", current_plan_version=1, research_task_id=task_id,
    )
    if with_session:
        store.create_session(session, memory_repository=memory)
    store.replace_selections(task_id, [
        ResearchPaperSelection(task_id, "paper-1", 1.0, "[]", "abstract", "", "search-1"),
    ])
    work_input = {}
    if candidates:
        work_input = {
            "validated_candidates": [{
                "candidate_id": "paper-1", "title": "Paper one", "abstract": "Frozen abstract.",
                "evidence_refs": ["ref-1"],
            }],
            "citation_allowlist": [{"citation_ref": "ref-1", "candidate_id": "paper-1"}],
        }
    store.create_work_items(task_id, [ResearchWorkItem(
        f"source-synth-{task_id}", task_id, 1, "synthesize_preliminary_report", "synthesizer",
        "[]", json.dumps(work_input), "completed", 1,
        "2026-10-30T00:00:00Z", "2026-10-30T00:00:00Z",
    )])
    monkeypatch.setattr(
        EvidenceMatrixService, "read_matrix", lambda self, *_args, **_kwargs: _matrix(task_id),
    )
    return store, task, session


def _post_report(store, executor, task_id, *, title="深度研究报告", key=None, report_version=None, orchestrator=None):
    service = ResearchService(store=store, executor=executor, orchestrator=orchestrator or object())
    body = {"title": title}
    if report_version is not None:
        body["report_version"] = report_version
    headers = {"Idempotency-Key": key} if key else {}
    with ExitStack() as stack:
        stack.enter_context(override_provider("research_store", store))
        stack.enter_context(override_provider("research_service", service))
        stack.enter_context(override_provider("research_report_generation_service", routes_research.ReportGenerationService(store)))
        return TestClient(app).post(f"/api/research-tasks/{task_id}/reports", json=body, headers=headers)


def test_session_report_post_reserves_and_dispatches_without_reopening_terminal_task(tmp_path, monkeypatch):
    store, task, _session = _seed(tmp_path, monkeypatch)
    executor = _RecordingExecutor()
    key = str(uuid4())

    response = _post_report(store, executor, task.research_task_id, key=key)

    assert response.status_code == 202
    body = response.json()
    assert body["report_id"]
    assert body["research_task_id"] == task.research_task_id
    assert body["plan_version"] == 1
    assert body["report_version"] == 1
    assert body["status"] == "generating"
    assert body["quality_status"] == "pending"
    assert body["published"] is False
    assert body["reason_codes"] == []
    assert body["report_url"] == f"/api/research-tasks/{task.research_task_id}/reports/1?format=json"
    reservation = store.get_report_generation_reservation(task.research_task_id, OWNER_ID, request_key=key)
    assert reservation is not None
    assert reservation.work_item.status == "queued"
    assert reservation.work_item.task_type == "synthesize_preliminary_report"
    assert reservation.work_item.role == "synthesizer"
    assert reservation.work_item.input_params["report_title"] == "深度研究报告"
    assert reservation.work_item.input_params["validated_candidates"][0]["candidate_id"] == "paper-1"
    assert len(executor.calls) == 1
    assert store.get_task(task.research_task_id, OWNER_ID).status == "completed"


def test_executor_worker_cas_starts_report_only_wrapper_with_fresh_reservation(tmp_path, monkeypatch):
    store, task, session = _seed(tmp_path, monkeypatch)
    executor = _RecordingExecutor()

    class _ReportOnlyOrchestrator:
        def __init__(self):
            self.call = None

        def run_report_only_generation(self, **kwargs):
            self.call = kwargs

    orchestrator = _ReportOnlyOrchestrator()
    response = _post_report(
        store, executor, task.research_task_id, title="Methods", key=str(uuid4()), orchestrator=orchestrator,
    )
    worker, worker_args, worker_kwargs = executor.calls[0]
    worker(*worker_args, **worker_kwargs)

    assert response.status_code == 202
    assert orchestrator.call is not None
    assert orchestrator.call["task"].status == "completed"
    assert orchestrator.call["session"].research_session_id == session.research_session_id
    assert orchestrator.call["work_item"].status == "running"
    assert orchestrator.call["reservation"].work_item.status == "running"
    assert orchestrator.call["work_item"].input_params["report_title"] == "Methods"
    assert store.get_task(task.research_task_id, OWNER_ID).status == "completed"


@pytest.mark.parametrize("predecessor_status", ["interrupted", "completed"])
def test_same_key_replay_rebinds_pending_terminal_work_item_without_new_report_version(
    tmp_path, monkeypatch, predecessor_status,
):
    store, task, _session = _seed(tmp_path, monkeypatch)
    executor = _RecordingExecutor()
    key = str(uuid4())

    class _ReportOnlyOrchestrator:
        def run_report_only_generation(self, **_kwargs):
            return None

    first = _post_report(
        store, executor, task.research_task_id, title="Methods", key=key,
        orchestrator=_ReportOnlyOrchestrator(),
    )
    store.update_report_generation_state(
        task.research_task_id, OWNER_ID, 1,
        expected_revision=0, stage="drafting", rewrite_count=0,
    )
    claim = store.claim_report_generation_budget(
        task.research_task_id, OWNER_ID, 1,
        claim_id=str(uuid4()), agent_run_id="report-only-replay-run",
        requested_model_loops=2, requested_tool_calls=4, requested_seconds=10,
    )
    assert claim["allowed"] is True
    first_worker, first_args, first_kwargs = executor.calls[0]
    first_worker(*first_args, **first_kwargs)
    original = store.get_report_generation_reservation(
        task.research_task_id, OWNER_ID, request_key=key,
    ).work_item
    if predecessor_status == "interrupted":
        original = store.update_work_item_status(
            original.work_item_id, "interrupted", error_code="STARTUP_AUDIT_INTERRUPTED",
        )
    else:
        original = store.update_work_item_status(
            original.work_item_id, "completed", output_json=json.dumps({"checkpoint_saved": True}),
        )
    before_report = store.get_research_report(task.research_task_id, OWNER_ID, report_version=1)
    before_payload = json.loads(before_report.report_json)

    replay = _post_report(
        store, executor, task.research_task_id, title="Methods", key=key,
    )

    rebound = store.get_report_generation_reservation(
        task.research_task_id, OWNER_ID, request_key=key,
    )
    after_payload = json.loads(rebound.report.report_json)
    assert first.status_code == replay.status_code == 202
    assert replay.json()["report_id"] == first.json()["report_id"]
    assert replay.json()["report_version"] == first.json()["report_version"] == 1
    assert replay.json()["status"] == "generating"
    assert rebound.work_item.work_item_id != original.work_item_id
    assert rebound.work_item.status == "queued"
    assert store.get_work_item(original.work_item_id).status == predecessor_status
    assert after_payload["generation"]["store_state"] == before_payload["generation"]["store_state"]
    assert after_payload["generation"]["budget"] == before_payload["generation"]["budget"]
    assert len(store.list_research_reports(task.research_task_id, OWNER_ID)) == 1
    assert len(executor.calls) == 2
    assert store.get_task(task.research_task_id, OWNER_ID).status == "completed"


def test_same_idempotency_key_replays_one_report_and_does_not_duplicate_executor_submission(tmp_path, monkeypatch):
    store, task, _session = _seed(tmp_path, monkeypatch)
    executor = _RecordingExecutor()
    key = str(uuid4())

    first = _post_report(store, executor, task.research_task_id, title="Methods", key=key)
    store.update_report_generation_state(
        task.research_task_id, OWNER_ID, 1,
        expected_revision=0, stage="evidence_review", rewrite_count=0,
        reason_codes=["MATRIX_SNAPSHOT_UNAVAILABLE"],
    )
    replay = _post_report(store, executor, task.research_task_id, title="Methods", key=key, report_version=1)

    assert first.status_code == replay.status_code == 202
    assert replay.json()["report_id"] == first.json()["report_id"]
    assert replay.json()["report_version"] == first.json()["report_version"]
    assert replay.json()["reason_codes"] == ["MATRIX_SNAPSHOT_UNAVAILABLE"]
    assert len(executor.calls) == 1
    assert len(store.list_research_reports(task.research_task_id, OWNER_ID)) == 1


def test_session_report_post_joins_same_title_when_key_is_omitted(tmp_path, monkeypatch):
    store, task, _session = _seed(tmp_path, monkeypatch)
    executor = _RecordingExecutor()

    first = _post_report(store, executor, task.research_task_id, title="Methods")
    replay = _post_report(store, executor, task.research_task_id, title="Methods")

    assert first.status_code == replay.status_code == 202
    assert replay.json()["report_id"] == first.json()["report_id"]
    assert len(executor.calls) == 1
    assert len(store.list_research_reports(task.research_task_id, OWNER_ID)) == 1


def test_different_key_conflicts_with_active_generation_and_returns_existing_url(tmp_path, monkeypatch):
    store, task, _session = _seed(tmp_path, monkeypatch)
    executor = _RecordingExecutor()

    first = _post_report(store, executor, task.research_task_id, title="Methods", key=str(uuid4()))

    def _unexpected_matrix_read(*_args, **_kwargs):
        raise AssertionError("active request must conflict before matrix preflight")

    monkeypatch.setattr(EvidenceMatrixService, "read_matrix", _unexpected_matrix_read)
    conflict = _post_report(store, executor, task.research_task_id, title="Another title", key=str(uuid4()))

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "REPORT_GENERATION_IN_PROGRESS"
    assert conflict.json()["error"]["report_url"] == first.json()["report_url"]
    assert len(executor.calls) == 1
    assert len(store.list_research_reports(task.research_task_id, OWNER_ID)) == 1


def test_reused_idempotency_key_with_different_payload_is_rejected(tmp_path, monkeypatch):
    store, task, _session = _seed(tmp_path, monkeypatch)
    executor = _RecordingExecutor()
    key = str(uuid4())
    _post_report(store, executor, task.research_task_id, title="Methods", key=key)

    response = _post_report(store, executor, task.research_task_id, title="Different", key=key)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REPORT_IDEMPOTENCY_KEY_REUSED"
    assert len(executor.calls) == 1
    assert len(store.list_research_reports(task.research_task_id, OWNER_ID)) == 1


def test_session_report_rejects_non_uuid_idempotency_key_before_reserving(tmp_path, monkeypatch):
    store, task, _session = _seed(tmp_path, monkeypatch)
    executor = _RecordingExecutor()

    response = _post_report(store, executor, task.research_task_id, key="request-17")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REPORT_SCHEMA_INVALID"
    assert store.list_research_reports(task.research_task_id, OWNER_ID) == []
    assert executor.calls == []


def test_explicit_new_report_version_cannot_bypass_atomic_version_allocation(tmp_path, monkeypatch):
    store, task, _session = _seed(tmp_path, monkeypatch)
    executor = _RecordingExecutor()

    response = _post_report(store, executor, task.research_task_id, key=str(uuid4()), report_version=7)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REPORT_VERSION_CONFLICT"
    assert store.list_research_reports(task.research_task_id, OWNER_ID) == []
    assert executor.calls == []


def test_new_key_after_failed_report_allocates_next_version_without_changing_task(tmp_path, monkeypatch):
    store, task, _session = _seed(tmp_path, monkeypatch)
    executor = _RecordingExecutor()
    first = _post_report(store, executor, task.research_task_id, title="Methods", key=str(uuid4()))
    first_report_id = first.json()["report_id"]
    first_item_id = store.list_work_items(task.research_task_id, plan_version=1)[-1].work_item_id
    with store._connect() as connection:
        connection.execute("UPDATE research_reports SET status='failed' WHERE report_id=?", (first_report_id,))
        connection.execute("UPDATE research_work_items SET status='failed' WHERE work_item_id=?", (first_item_id,))
        connection.commit()

    second = _post_report(store, executor, task.research_task_id, title="Methods retry", key=str(uuid4()))

    assert second.status_code == 202
    assert second.json()["report_version"] == 2
    assert [report.report_version for report in store.list_research_reports(task.research_task_id, OWNER_ID)] == [1, 2]
    assert store.get_task(task.research_task_id, OWNER_ID).status == "completed"
    assert len(executor.calls) == 2


def test_session_report_requires_existing_validated_selection_candidates_before_reserving(tmp_path, monkeypatch):
    store, task, _session = _seed(tmp_path, monkeypatch, candidates=False)
    executor = _RecordingExecutor()

    response = _post_report(store, executor, task.research_task_id, key=str(uuid4()))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REPORT_NOT_READY"
    assert store.list_research_reports(task.research_task_id, OWNER_ID) == []
    assert executor.calls == []


@pytest.mark.parametrize("task_status", ["partial", "completed", "failed", "cancelled", "interrupted"])
@pytest.mark.parametrize("predecessor_status", ["interrupted", "completed"])
def test_startup_recovery_rebinds_pending_report_for_any_terminal_task(
    tmp_path, monkeypatch, task_status, predecessor_status,
):
    store, task, _session = _seed(tmp_path, monkeypatch, task_status=task_status)
    prior_input = store.list_work_items(task.research_task_id, plan_version=1)[0].input_params
    reservation = store.reserve_report_generation(
        task.research_task_id,
        OWNER_ID,
        plan_version=1,
        request_key=str(uuid4()),
        request_payload={"plan_version": 1, "title": "Methods", "schema_version": "report-quality-v1"},
        work_item_input={
            "validated_candidates": prior_input["validated_candidates"],
            "citation_allowlist": prior_input["citation_allowlist"],
            "report_title": "Methods",
        },
    )
    running = store.update_work_item_status(reservation.work_item.work_item_id, "running", attempt=1)
    if predecessor_status == "interrupted":
        old = store.update_work_item_status(running.work_item_id, "interrupted", error_code="STARTUP_AUDIT_INTERRUPTED")
    else:
        old = store.update_work_item_status(
            running.work_item_id, "completed", output_json=json.dumps({"status": "completed"}),
        )
    executor = _RecordingExecutor()
    service = ResearchService(store=store, executor=executor, orchestrator=object())

    service.recover_interrupted()

    rebound = store.get_report_generation_reservation(
        task.research_task_id, OWNER_ID,
        request_key=json.loads(reservation.report.report_json)["generation"]["request_key"],
    )
    assert rebound.report.report_version == 1
    assert rebound.report.status == "generating"
    assert rebound.work_item.work_item_id != old.work_item_id
    assert rebound.work_item.status == "queued"
    assert store.get_work_item(old.work_item_id).status == predecessor_status
    assert store.get_task(task.research_task_id, OWNER_ID).status == task_status
    assert len(executor.calls) == 1


@pytest.mark.parametrize("task_status", ["planning", "running", "waiting_approval", "paused"])
def test_report_only_rejects_nonterminal_task_without_reserving(tmp_path, monkeypatch, task_status):
    store, task, _session = _seed(tmp_path, monkeypatch, task_status=task_status)
    executor = _RecordingExecutor()

    response = _post_report(store, executor, task.research_task_id, key=str(uuid4()))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REPORT_NOT_READY"
    assert store.list_research_reports(task.research_task_id, OWNER_ID) == []
    assert executor.calls == []


def test_sessionless_legacy_matrix_route_returns_unvalidated_unpublished_draft(tmp_path, monkeypatch):
    store, task, _session = _seed(tmp_path, monkeypatch, with_session=False)
    executor = _RecordingExecutor()

    response = _post_report(store, executor, task.research_task_id, title="Legacy matrix")

    assert response.status_code == 202
    assert response.json()["status"] == "draft"
    assert response.json()["quality_status"] == "unvalidated"
    assert response.json()["published"] is False
    assert response.json()["reason_codes"] == []
    assert response.json()["report_url"] == f"/api/research-tasks/{task.research_task_id}/reports/1?format=json"
    stored = store.get_research_report(task.research_task_id, OWNER_ID, report_version=1)
    payload = json.loads(stored.report_json)
    assert stored.status == "draft"
    assert payload["generation"]["path"] == "matrix_api"
    assert payload["generation"]["published"] is False
    assert payload["quality_validation"]["status"] == "unvalidated"
    assert executor.calls == []
