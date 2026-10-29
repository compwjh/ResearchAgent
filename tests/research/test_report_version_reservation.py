from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.app.memory.repository import MemoryRepository
from backend.app.research.domain.models import (
    AgentRun,
    ResearchArtifact,
    ResearchPlan,
    ResearchReport,
    ResearchSession,
    ResearchTask,
    ResearchWorkItem,
)
from backend.app.research.infrastructure.research_store import (
    ResearchReportReservationConflict,
    ResearchStore,
    ResearchTaskNotFound,
)

OWNER_ID = "owner-report-reservation"
TASK_ID = "task-report-reservation"
REQUEST_KEY = "4fa3d3a6-7731-47b9-9667-94852b9f9071"
SECOND_KEY = "1728011d-08ec-443e-b793-b0bcf743a6b1"
PAYLOAD = {"plan_version": 1, "title": "Evidence review"}


def _store_with_task(tmp_path, *, task_status: str = "completed", plan_status: str = "completed"):
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = ResearchTask(
        TASK_ID,
        OWNER_ID,
        "conversation-report-reservation",
        "Compare research evidence",
        "en",
        "balanced",
        False,
        5,
        1500,
        task_status,
        1,
        "2026-10-29T00:00:00Z",
        "2026-10-29T00:00:00Z",
    )
    store.create_task(task)
    store.create_plan(
        ResearchPlan(
            TASK_ID,
            1,
            "approved evidence scope",
            '["methods"]',
            plan_status,
            "2026-10-29T00:00:00Z",
            "test-model",
        )
    )
    return store, task


def _reserve(store, *, key: str = REQUEST_KEY, payload: dict | None = None, report_version: int | None = None, work_item_input: dict | None = None):
    return store.reserve_report_generation(
        TASK_ID,
        OWNER_ID,
        plan_version=1,
        request_key=key,
        request_payload=PAYLOAD if payload is None else payload,
        work_item_input=work_item_input,
        report_version=report_version,
    )


def _queued_synthesizer(store: ResearchStore, task_id: str, *, status: str = "queued", input_json: str = '{"goal":"goal"}', work_item_id: str = "task-report-reservation-synth") -> ResearchWorkItem:
    item = ResearchWorkItem(
        work_item_id,
        task_id,
        1,
        "synthesize_preliminary_report",
        "synthesizer",
        "[]",
        input_json,
        status,
        0,
        "2026-10-29T00:00:00Z",
        "2026-10-29T00:00:00Z",
    )
    return store.create_work_items(task_id, [item])[0]


def _seed_artifact_version(store: ResearchStore, tmp_path, version: int) -> None:
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, _activity = memory.create_conversation_messages(
        OWNER_ID, "goal", None, "message", "normal"
    )
    with store._connect() as connection:
        connection.execute(
            "UPDATE research_tasks SET conversation_id=? WHERE research_task_id=?",
            (conversation.conversation_id, TASK_ID),
        )
        connection.commit()
    session = ResearchSession(
        "session-report-reservation",
        OWNER_ID,
        conversation.conversation_id,
        user.message_id,
        "intake-report-reservation",
        "completed",
        research_task_id=TASK_ID,
    )
    store.create_session(session, memory_repository=memory)
    item = _queued_synthesizer(
        store,
        TASK_ID,
        status="completed",
        work_item_id="task-report-reservation-artifact-synth",
    )
    run = store.create_agent_run(
        AgentRun(
            "run-report-reservation-artifact",
            session.research_session_id,
            1,
            "synthesizer",
            "research-report-synthesis",
            "1",
            "test-hash",
            "test-model",
            "off",
            "[]",
            status="completed",
            research_task_id=TASK_ID,
            work_item_id=item.work_item_id,
            owner_id=OWNER_ID,
        ),
        owner_id=OWNER_ID,
    )
    content = "artifact seed"
    store.create_artifact(
        ResearchArtifact(
            f"artifact-report-reservation-{version}",
            TASK_ID,
            version,
            "markdown",
            hashlib.sha256(content.encode("utf-8")).hexdigest(),
            run.agent_run_id,
            content=content,
        ),
        owner_id=OWNER_ID,
    )


def _finish_report_and_work_item(store: ResearchStore, report_id: str, work_item_id: str) -> None:
    with store._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE research_reports SET status='draft' WHERE report_id=?", (report_id,))
        connection.execute(
            "UPDATE research_work_items SET status='completed', ended_at='2026-10-29T00:01:00Z' WHERE work_item_id=?",
            (work_item_id,),
        )
        connection.commit()


def test_reservation_persists_report_identity_and_reuses_unbound_queued_synthesizer(tmp_path):
    store, task = _store_with_task(tmp_path, task_status="running", plan_status="active")
    existing = _queued_synthesizer(store, task.research_task_id)

    reservation = _reserve(store, work_item_input={"goal": "Compare evidence"})

    assert reservation.report.status == "generating"
    assert reservation.report.report_version == 1
    assert reservation.work_item.work_item_id == existing.work_item_id
    assert reservation.work_item.status == "queued"
    input_json = json.loads(reservation.work_item.input_json)
    assert input_json["report_id"] == reservation.report.report_id
    assert input_json["request_key"] == REQUEST_KEY
    assert input_json["report_version"] == 1
    assert input_json["report_generation"]["request_fingerprint"]
    generation = json.loads(reservation.report.report_json)["generation"]
    assert generation["request_key"] == REQUEST_KEY
    assert generation["work_item_id"] == existing.work_item_id
    assert store.get_task(task.research_task_id, OWNER_ID).status == "running"
    assert len(store.list_research_reports(task.research_task_id, OWNER_ID)) == 1
    assert len(store.list_work_items(task.research_task_id, plan_version=1)) == 1


def test_same_key_same_canonical_payload_returns_same_reservation_after_completion(tmp_path):
    store, _task = _store_with_task(tmp_path)
    first = _reserve(store, payload={"title": "Evidence review", "plan_version": 1})
    _finish_report_and_work_item(store, first.report.report_id, first.work_item.work_item_id)

    retry = _reserve(store, payload={"plan_version": 1, "title": "Evidence review"})

    assert retry.replayed is True
    assert retry.report.report_id == first.report.report_id
    assert retry.report.report_version == first.report.report_version
    assert retry.work_item.work_item_id == first.work_item.work_item_id
    assert retry.work_item.status == "completed"
    assert len(store.list_research_reports(TASK_ID, OWNER_ID)) == 1
    assert len(store.list_work_items(TASK_ID, plan_version=1)) == 1


def test_same_key_with_different_payload_has_typed_conflict_without_writes(tmp_path):
    store, _task = _store_with_task(tmp_path)
    first = _reserve(store)

    with pytest.raises(ResearchReportReservationConflict) as raised:
        _reserve(store, payload={"plan_version": 1, "title": "Different request"})

    assert raised.value.code == "REPORT_IDEMPOTENCY_KEY_REUSED"
    assert len(store.list_research_reports(TASK_ID, OWNER_ID)) == 1
    assert len(store.list_work_items(TASK_ID, plan_version=1)) == 1
    assert first.report.status == "generating"


def test_different_key_during_generation_conflicts_with_existing_report(tmp_path):
    store, _task = _store_with_task(tmp_path)
    first = _reserve(store)

    with pytest.raises(ResearchReportReservationConflict) as raised:
        _reserve(store, key=SECOND_KEY)

    assert raised.value.code == "REPORT_GENERATION_IN_PROGRESS"
    assert raised.value.existing_report.report_id == first.report.report_id
    assert len(store.list_research_reports(TASK_ID, OWNER_ID)) == 1


def test_next_key_after_terminal_report_creates_new_version_without_reopening_task_or_item(tmp_path):
    store, task = _store_with_task(tmp_path)
    first = _reserve(store)
    _finish_report_and_work_item(store, first.report.report_id, first.work_item.work_item_id)

    second = _reserve(store, key=SECOND_KEY)

    assert second.report.report_id != first.report.report_id
    assert second.report.report_version == first.report.report_version + 1
    assert second.work_item.work_item_id != first.work_item.work_item_id
    assert second.work_item.status == "queued"
    assert store.get_task(task.research_task_id, OWNER_ID).status == "completed"
    assert store.get_work_item(first.work_item.work_item_id).status == "completed"


def test_running_unreserved_synthesizer_is_not_rewritten_or_reused(tmp_path):
    store, _task = _store_with_task(tmp_path, task_status="running", plan_status="active")
    running = _queued_synthesizer(
        store,
        TASK_ID,
        status="running",
        input_json='{"goal":"already dispatched","report_version":1}',
    )

    reservation = _reserve(store, work_item_input={"goal": "new request"})

    assert reservation.work_item.work_item_id != running.work_item_id
    assert store.get_work_item(running.work_item_id).input_json == running.input_json
    assert store.get_work_item(running.work_item_id).status == "running"


def test_work_item_bound_to_another_reservation_is_not_reused(tmp_path):
    store, _task = _store_with_task(tmp_path, task_status="running", plan_status="active")
    reserved_input = json.dumps(
        {"report_generation": {"request_key": SECOND_KEY, "report_version": 3, "report_id": "other-report"}},
        sort_keys=True,
        separators=(",", ":"),
    )
    existing = _queued_synthesizer(store, TASK_ID, input_json=reserved_input)

    reservation = _reserve(store)

    assert reservation.work_item.work_item_id != existing.work_item_id
    assert store.get_work_item(existing.work_item_id).input_json == reserved_input


def test_requested_version_must_match_existing_reservation(tmp_path):
    store, _task = _store_with_task(tmp_path)
    first = _reserve(store)

    with pytest.raises(ResearchReportReservationConflict) as raised:
        _reserve(store, key=REQUEST_KEY, report_version=2)

    assert raised.value.code == "REPORT_VERSION_CONFLICT"
    assert store.get_research_report(TASK_ID, OWNER_ID, report_version=first.report.report_version).report_id == first.report.report_id


def test_new_request_cannot_claim_a_caller_selected_report_version(tmp_path):
    store, _task = _store_with_task(tmp_path)

    with pytest.raises(ResearchReportReservationConflict) as raised:
        _reserve(store, report_version=9)

    assert raised.value.code == "REPORT_VERSION_CONFLICT"
    assert store.list_research_reports(TASK_ID, OWNER_ID) == []
    assert store.list_work_items(TASK_ID, plan_version=1) == []


def test_version_uses_maximum_of_existing_reports_and_artifacts(tmp_path):
    store, _task = _store_with_task(tmp_path)
    report = ResearchReport(
        "report-existing-v3",
        TASK_ID,
        1,
        3,
        "draft",
        "",
        "",
        '{"generation":{}}',
        "[]",
        "2026-10-29T00:00:00Z",
    )
    store.save_research_report(report, owner_id=OWNER_ID)
    _seed_artifact_version(store, tmp_path, 7)

    reservation = _reserve(store)

    assert reservation.report.report_version == 8


def test_concurrent_same_key_returns_one_persisted_reservation(tmp_path):
    store, _task = _store_with_task(tmp_path)

    def reserve():
        return _reserve(store)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(lambda _index: reserve(), range(2)))

    assert first.report.report_id == second.report.report_id
    assert first.report.report_version == second.report.report_version == 1
    assert first.work_item.work_item_id == second.work_item.work_item_id
    assert len(store.list_research_reports(TASK_ID, OWNER_ID)) == 1
    assert len(store.list_work_items(TASK_ID, plan_version=1)) == 1


def test_concurrent_different_keys_only_reserve_one_version(tmp_path):
    store, _task = _store_with_task(tmp_path)

    def reserve(key):
        try:
            return _reserve(store, key=key)
        except ResearchReportReservationConflict as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(reserve, (REQUEST_KEY, SECOND_KEY)))

    results = [first, second]
    winners = [result for result in results if not isinstance(result, ResearchReportReservationConflict)]
    conflicts = [result for result in results if isinstance(result, ResearchReportReservationConflict)]
    assert len(winners) == 1
    assert len(conflicts) == 1
    assert conflicts[0].code == "REPORT_GENERATION_IN_PROGRESS"
    assert len(store.list_research_reports(TASK_ID, OWNER_ID)) == 1
    assert len(store.list_work_items(TASK_ID, plan_version=1)) == 1


def test_reservation_insert_failure_rolls_back_report_and_work_item(tmp_path):
    store, _task = _store_with_task(tmp_path)
    with store._connect() as connection:
        connection.execute(
            """CREATE TRIGGER reject_report_synthesizer_insert
               BEFORE INSERT ON research_work_items
               WHEN NEW.task_type='synthesize_preliminary_report'
               BEGIN SELECT RAISE(ABORT, 'reserved test failure'); END"""
        )
        connection.commit()

    with pytest.raises(sqlite3.IntegrityError, match="reserved test failure"):
        _reserve(store)

    assert store.list_research_reports(TASK_ID, OWNER_ID) == []
    assert store.list_work_items(TASK_ID, plan_version=1) == []


def test_reservation_checks_task_owner_and_current_plan_before_writing(tmp_path):
    store, _task = _store_with_task(tmp_path, task_status="running", plan_status="active")

    with pytest.raises(ResearchTaskNotFound):
        store.reserve_report_generation(
            TASK_ID,
            "different-owner",
            plan_version=1,
            request_key=REQUEST_KEY,
            request_payload=PAYLOAD,
        )
    with pytest.raises(ResearchReportReservationConflict) as raised:
        store.reserve_report_generation(
            TASK_ID,
            OWNER_ID,
            plan_version=2,
            request_key=SECOND_KEY,
            request_payload={"plan_version": 2, "title": "Stale plan"},
        )

    assert raised.value.code == "REPORT_VERSION_CONFLICT"
    assert store.list_research_reports(TASK_ID, OWNER_ID) == []
    assert store.list_work_items(TASK_ID, plan_version=1) == []


def test_reservation_rejects_a_plan_that_is_not_active_or_completed(tmp_path):
    store, _task = _store_with_task(tmp_path, task_status="running", plan_status="proposed")

    with pytest.raises(ResearchReportReservationConflict) as raised:
        _reserve(store)

    assert raised.value.code == "REPORT_VERSION_CONFLICT"
    assert store.list_research_reports(TASK_ID, OWNER_ID) == []
    assert store.list_work_items(TASK_ID, plan_version=1) == []


def test_get_reservation_by_key_is_owner_scoped_and_includes_terminal_rows(tmp_path):
    store, _task = _store_with_task(tmp_path)
    first = _reserve(store)
    _finish_report_and_work_item(store, first.report.report_id, first.work_item.work_item_id)

    found = store.get_report_generation_reservation(TASK_ID, OWNER_ID, request_key=REQUEST_KEY)

    assert found.report.report_id == first.report.report_id
    assert found.work_item.work_item_id == first.work_item.work_item_id
    assert found.work_item.status == "completed"
    assert store.get_report_generation_reservation(TASK_ID, "different-owner", request_key=REQUEST_KEY) is None
    assert store.get_report_generation_reservation(TASK_ID, OWNER_ID, request_key=SECOND_KEY) is None


def test_report_insert_failure_rolls_back_reused_queued_item_binding(tmp_path):
    store, _task = _store_with_task(tmp_path, task_status="running", plan_status="active")
    existing = _queued_synthesizer(store, TASK_ID)
    with store._connect() as connection:
        connection.execute(
            """CREATE TRIGGER reject_report_row_insert
               BEFORE INSERT ON research_reports
               BEGIN SELECT RAISE(ABORT, 'reserved report insert failure'); END"""
        )
        connection.commit()

    with pytest.raises(sqlite3.IntegrityError, match="reserved report insert failure"):
        _reserve(store)

    saved_item = store.get_work_item(existing.work_item_id)
    assert saved_item.input_json == existing.input_json
    assert saved_item.status == "queued"
    assert store.list_research_reports(TASK_ID, OWNER_ID) == []
