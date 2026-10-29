from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.app.memory.repository import MemoryRepository
from backend.app.research.domain.models import (
    AgentRun,
    ResearchPlan,
    ResearchSession,
    ResearchTask,
)
from backend.app.research.infrastructure.research_store import (
    ResearchReportGenerationStateConflict,
    ResearchStore,
)

OWNER_ID = "owner-budget-recovery-probe"
TASK_ID = "task-budget-recovery-probe"
REQUEST_KEY = "7b4aacbe-1df4-4f19-88c2-05f21f262759"


def _fresh_report_store(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, _activity = memory.create_conversation_messages(
        OWNER_ID, "Compare research evidence", None, "message", "normal"
    )
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_task(
        ResearchTask(
            TASK_ID,
            OWNER_ID,
            conversation.conversation_id,
            "Compare research evidence",
            "en",
            "balanced",
            False,
            5,
            1500,
            "completed",
            1,
            "2026-10-29T00:00:00Z",
            "2026-10-29T00:00:00Z",
        )
    )
    store.create_plan(
        ResearchPlan(
            TASK_ID,
            1,
            "approved scope",
            '["methods"]',
            "completed",
            "2026-10-29T00:00:00Z",
            "probe-model",
        )
    )
    store.create_session(
        ResearchSession(
            "session-budget-recovery-probe",
            OWNER_ID,
            conversation.conversation_id,
            user.message_id,
            "intake-budget-recovery-probe",
            "completed",
            research_task_id=TASK_ID,
        ),
        memory_repository=memory,
    )
    reservation = store.reserve_report_generation(
        TASK_ID,
        OWNER_ID,
        plan_version=1,
        request_key=REQUEST_KEY,
        request_payload={"plan_version": 1, "title": "Recovery probe"},
    )
    return store, reservation


def _claim(store, reservation, *, seconds, loops=40, calls=160, claim_id=None, run_id=None):
    return store.claim_report_generation_budget(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        claim_id=claim_id or str(uuid.uuid4()),
        agent_run_id=run_id or f"probe-run-{uuid.uuid4()}",
        requested_model_loops=loops,
        requested_tool_calls=calls,
        requested_seconds=seconds,
    )


def _persist_run(store, reservation, run_id, *, status, started_at, ended_at, loops=0, calls=0):
    store.create_agent_run(
        AgentRun(
            run_id,
            "session-budget-recovery-probe",
            1,
            "synthesizer",
            "research-report-synthesis",
            "1",
            "probe-hash",
            "probe-model",
            "off",
            "[]",
            status=status,
            research_task_id=TASK_ID,
            work_item_id=reservation.work_item.work_item_id,
            model_loop_count=loops,
            tool_call_count=calls,
            started_at=started_at,
            ended_at=ended_at,
            owner_id=OWNER_ID,
        ),
        owner_id=OWNER_ID,
    )


@pytest.mark.parametrize(
    "started_at,ended_at",
    [
        ("2026-10-29T00:00:00Z", None),
        ("2026-10-29T00:02:00Z", "2026-10-29T00:00:00Z"),
    ],
    ids=("missing-terminal-end", "reversed-terminal-time"),
)
def test_restart_keeps_full_claim_for_terminal_run_with_unknown_time(
    tmp_path, started_at, ended_at
):
    store, reservation = _fresh_report_store(tmp_path)
    claim_id = "e68e6313-5015-467e-89b5-ff564fc2a717"
    run_id = "probe-terminal-unknown-time"
    claim = _claim(
        store, reservation, seconds=300, claim_id=claim_id, run_id=run_id
    )
    _persist_run(
        store,
        reservation,
        run_id,
        status="completed",
        started_at=started_at,
        ended_at=ended_at,
        loops=4,
        calls=7,
    )

    restarted = ResearchStore(store.database_path)
    settled = restarted.settle_report_generation_budget(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        claim_id=claim_id,
        now="2026-10-29T00:03:00Z",
    )
    budget = restarted.get_report_generation_budget(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        now="2026-10-29T00:03:10Z",
    )

    assert claim["allowed"] is True
    assert settled["settled"] is True
    assert budget["task_totals"]["elapsed_seconds"] == 300.0
    assert budget["report_totals"]["elapsed_seconds"] == 300.0
    assert budget["reserved"]["seconds"] == 0.0
    assert budget["remaining"]["seconds"] == 1200.0


def test_concurrent_claims_serialize_against_one_task_budget(tmp_path):
    store, reservation = _fresh_report_store(tmp_path)
    identities = [
        (f"b45a6ce5-b4db-4ce4-8f0a-{index:012d}", f"probe-concurrent-{index}")
        for index in range(5)
    ]

    def request(identity):
        claim_id, run_id = identity
        return _claim(
            store,
            reservation,
            seconds=500,
            loops=40,
            calls=160,
            claim_id=claim_id,
            run_id=run_id,
        )

    with ThreadPoolExecutor(max_workers=len(identities)) as executor:
        claims = list(executor.map(request, identities))

    allowed = [claim for claim in claims if claim["allowed"]]
    assert len(allowed) == 3
    assert sum(claim["grant"]["seconds"] for claim in allowed) == 1500
    assert sum(claim["grant"]["model_loops"] for claim in allowed) == 120
    assert sum(claim["grant"]["tool_calls"] for claim in allowed) == 480
    budget = store.get_report_generation_budget(
        TASK_ID, OWNER_ID, reservation.report.report_version
    )
    assert budget["reserved"]["seconds"] == 1500.0
    assert budget["remaining"]["seconds"] == 0.0


def test_restart_and_new_version_preserve_historical_run_totals(tmp_path):
    store, first = _fresh_report_store(tmp_path)
    claim_id = "5c56ab06-5e35-4b54-bfaf-64572baaa1a4"
    run_id = "probe-history-first-version"
    _claim(store, first, seconds=300, claim_id=claim_id, run_id=run_id)
    _persist_run(
        store,
        first,
        run_id,
        status="completed",
        started_at="2026-10-29T00:00:00Z",
        ended_at="2026-10-29T00:02:00Z",
        loops=17,
        calls=29,
    )
    store.settle_report_generation_budget(
        TASK_ID, OWNER_ID, first.report.report_version, claim_id=claim_id
    )
    with store._connect() as connection:
        connection.execute(
            "UPDATE research_reports SET status='draft' WHERE report_id=?",
            (first.report.report_id,),
        )
        connection.commit()

    second = store.reserve_report_generation(
        TASK_ID,
        OWNER_ID,
        plan_version=1,
        request_key="1f488263-8650-4f77-943c-a4a254c6e98e",
        request_payload={"plan_version": 1, "title": "Second version"},
    )
    reopened = ResearchStore(store.database_path)
    historical = reopened.get_report_generation_budget(
        TASK_ID, OWNER_ID, second.report.report_version
    )
    next_claim = _claim(reopened, second, seconds=300)

    assert second.report.report_version == 2
    assert historical["task_totals"] == {
        "model_loops_used": 17,
        "tool_calls_used": 29,
        "elapsed_seconds": 120.0,
    }
    assert next_claim["allowed"] is True
    assert next_claim["remaining"]["model_loops"] == 103
    assert next_claim["remaining"]["tool_calls"] == 451
    assert next_claim["remaining"]["seconds"] == 1080.0


def test_state_cas_rejects_stale_writer_after_store_restart(tmp_path):
    store, reservation = _fresh_report_store(tmp_path)
    first = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        expected_revision=0,
        stage="evidence_review",
        rewrite_count=0,
    )
    restarted = ResearchStore(store.database_path)

    with pytest.raises(ResearchReportGenerationStateConflict):
        restarted.update_report_generation_state(
            TASK_ID,
            OWNER_ID,
            reservation.report.report_version,
            expected_revision=0,
            stage="comparison",
            rewrite_count=0,
        )

    latest = restarted.get_report_generation_budget(
        TASK_ID, OWNER_ID, reservation.report.report_version
    )
    assert first["revision"] == 1
    assert latest["revision"] == 1
    assert latest["stage"] == "evidence_review"
