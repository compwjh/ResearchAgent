from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.app.memory.repository import MemoryRepository
from backend.app.research.domain.models import (
    AgentRun,
    ResearchPlan,
    ResearchSession,
    ResearchTask,
    ResearchWorkItem,
)
from backend.app.research.infrastructure.research_store import (
    ResearchReportGenerationStateConflict,
    ResearchStore,
)

OWNER_ID = "owner-report-state"
TASK_ID = "task-report-state"
REQUEST_KEY = "e8124dd2-c75c-4e08-9f97-bd753d335a50"


def _setup(tmp_path, *, profile="balanced", soft_budget=None):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, _activity = memory.create_conversation_messages(
        OWNER_ID, "Compare evidence", None, "message", "normal"
    )
    task_budget = soft_budget or {"speed": 600, "balanced": 1500, "quality": 2700}[profile]
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = ResearchTask(
        TASK_ID,
        OWNER_ID,
        conversation.conversation_id,
        "Compare research evidence",
        "en",
        profile,
        False,
        5,
        task_budget,
        "completed",
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
            "completed",
            "2026-10-29T00:00:00Z",
            "test-model",
        )
    )
    store.create_session(
        ResearchSession(
            "session-report-state",
            OWNER_ID,
            conversation.conversation_id,
            user.message_id,
            "intake-report-state",
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
        request_payload={"plan_version": 1, "title": "Evidence report"},
    )
    return store, reservation


def _claim(
    store,
    reservation,
    *,
    claim_id=None,
    run_id=None,
    loops=40,
    calls=160,
    seconds=300,
    **kwargs,
):
    return store.claim_report_generation_budget(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        claim_id=claim_id or str(uuid.uuid4()),
        agent_run_id=run_id or f"run-{uuid.uuid4()}",
        requested_model_loops=loops,
        requested_tool_calls=calls,
        requested_seconds=seconds,
        **kwargs,
    )


def _persist_run(store, reservation, run_id, *, status="completed", loops=0, calls=0, started=None, ended=None):
    return store.create_agent_run(
        AgentRun(
            run_id,
            "session-report-state",
            1,
            "synthesizer",
            "research-report-synthesis",
            "1",
            "test-hash",
            "test-model",
            "off",
            "[]",
            status=status,
            research_task_id=TASK_ID,
            work_item_id=reservation.work_item.work_item_id,
            model_loop_count=loops,
            tool_call_count=calls,
            started_at=started,
            ended_at=ended,
            owner_id=OWNER_ID,
        ),
        owner_id=OWNER_ID,
    )


@pytest.mark.parametrize(
    "profile,expected_seconds",
    [("speed", 600), ("balanced", 1500), ("quality", 2700)],
)
def test_effective_seconds_respect_profile_and_task_soft_budget(tmp_path, profile, expected_seconds):
    store, reservation = _setup(tmp_path, profile=profile)

    budget = store.get_report_generation_budget(TASK_ID, OWNER_ID, reservation.report.report_version)

    assert budget["limits"]["max_seconds"] == expected_seconds
    assert budget["remaining"]["seconds"] == expected_seconds


def test_task_soft_budget_and_approved_plan_can_only_lower_profile_limit(tmp_path):
    store, reservation = _setup(tmp_path, profile="balanced", soft_budget=900)

    budget = store.get_report_generation_budget(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        approved_max_seconds=720,
    )

    assert budget["limits"]["max_seconds"] == 720
    assert budget["remaining"]["seconds"] == 720


def test_approved_lower_budget_is_applied_and_never_raised_by_later_claim(tmp_path):
    store, reservation = _setup(tmp_path, profile="quality")

    first = _claim(store, reservation, claim_id="2f1afaf2-9d72-4b0c-9a72-975d951135ec", seconds=600, approved_max_seconds=600)
    later = _claim(
        store,
        reservation,
        claim_id="8bb853f6-8bfd-47d1-9d37-0e579e8f2430",
        seconds=600,
        approved_max_seconds=2700,
    )

    assert first["allowed"] is True
    assert first["limits"]["max_seconds"] == 600
    assert later["limits"]["max_seconds"] == 600
    assert later["remaining"]["seconds"] == 0
    assert "seconds" in later["exhausted"]


def test_claim_is_idempotent_and_same_key_payload_mismatch_conflicts(tmp_path):
    store, reservation = _setup(tmp_path)
    claim_id = "cf26a3b2-e64d-4edc-a1eb-23a43bf6a44e"

    first = _claim(store, reservation, claim_id=claim_id, run_id="run-idempotent", loops=20, calls=30, seconds=45)
    replay = _claim(store, reservation, claim_id=claim_id, run_id="run-idempotent", loops=20, calls=30, seconds=45)

    assert first["grant"] == replay["grant"]
    assert first["claim_id"] == replay["claim_id"]
    assert replay["replayed"] is True
    assert first["allowed"] is True
    assert first["grant"] == {"model_loops": 20, "tool_calls": 30, "seconds": 45}
    with pytest.raises(ResearchReportGenerationStateConflict) as raised:
        _claim(store, reservation, claim_id=claim_id, run_id="run-idempotent", loops=19, calls=30, seconds=45)
    assert raised.value.code == "REPORT_GENERATION_STATE_CONFLICT"


def test_concurrent_claims_cannot_reserve_more_than_task_caps(tmp_path):
    store, reservation = _setup(tmp_path)
    claim_ids = [str(uuid.uuid4()) for _ in range(5)]

    with ThreadPoolExecutor(max_workers=5) as pool:
        claims = list(
            pool.map(
                lambda claim_id: _claim(
                    store,
                    reservation,
                    claim_id=claim_id,
                    loops=40,
                    calls=160,
                    seconds=100,
                ),
                claim_ids,
            )
        )

    assert sum(item["grant"]["model_loops"] for item in claims) == 160
    assert sum(item["grant"]["tool_calls"] for item in claims) == 640
    assert sum(item["grant"]["seconds"] for item in claims) <= 1500
    assert sum(item["allowed"] for item in claims) == 4
    blocked = next(item for item in claims if not item["allowed"])
    assert "model_loops" in blocked["exhausted"]
    assert "tool_calls" in blocked["exhausted"]


def test_unknown_lost_run_keeps_its_full_persisted_reservation(tmp_path):
    store, reservation = _setup(tmp_path)
    claim = _claim(store, reservation, run_id="run-lost-before-persist", loops=35, calls=100, seconds=321)

    budget = store.get_report_generation_budget(TASK_ID, OWNER_ID, reservation.report.report_version)
    replay = store.settle_report_generation_budget(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        claim_id=claim["claim_id"],
    )

    assert claim["allowed"] is True
    assert budget["reserved"]["seconds"] == 321
    assert budget["remaining"]["seconds"] == 1500 - 321
    assert replay["settled"] is False
    assert replay["reserved"]["seconds"] == 321


@pytest.mark.parametrize(
    "started_at,ended_at,case",
    [
        ("2026-10-29T00:00:00Z", None, "missing end"),
        ("2026-10-29T00:02:00Z", "2026-10-29T00:00:00Z", "reversed clock"),
    ],
)
def test_terminal_claim_with_unknown_timestamps_consumes_full_reserved_seconds(
    tmp_path, started_at, ended_at, case
):
    store, reservation = _setup(tmp_path)
    claim_id = str(uuid.uuid4())
    run_id = f"run-terminal-unknown-{case.replace(' ', '-')}"
    _claim(store, reservation, claim_id=claim_id, run_id=run_id, seconds=300)
    _persist_run(
        store,
        reservation,
        run_id,
        status="completed",
        loops=4,
        calls=9,
        started=started_at,
        ended=ended_at,
    )

    settled = store.settle_report_generation_budget(
        TASK_ID,
        OWNER_ID,
        1,
        claim_id=claim_id,
        now="2026-10-29T00:00:10Z",
    )
    budget = store.get_report_generation_budget(
        TASK_ID, OWNER_ID, 1, now="2026-10-29T00:00:10Z"
    )

    assert settled["settled"] is True
    assert budget["task_totals"]["elapsed_seconds"] == 300.0
    assert budget["report_totals"]["elapsed_seconds"] == 300.0
    assert budget["remaining"]["seconds"] == 1200.0


def test_unclaimed_historical_terminal_run_with_missing_end_consumes_task_cap(tmp_path):
    store, _reservation = _setup(tmp_path)
    item = ResearchWorkItem(
        "work-item-unknown-legacy-time",
        TASK_ID,
        1,
        "search_catalog",
        "search-worker",
        "[]",
        "{}",
        "completed",
        1,
        "2026-10-29T00:00:00Z",
        "2026-10-29T00:00:00Z",
    )
    store.create_work_items(TASK_ID, [item])
    store.create_agent_run(
        AgentRun(
            "run-unknown-legacy-time",
            "session-report-state",
            1,
            "search_worker",
            "paper-catalog-search",
            "1",
            "test-hash",
            "test-model",
            "off",
            "[]",
            status="completed",
            research_task_id=TASK_ID,
            work_item_id=item.work_item_id,
            model_loop_count=2,
            tool_call_count=3,
            started_at="2026-10-29T00:00:00Z",
            ended_at=None,
            owner_id=OWNER_ID,
        ),
        owner_id=OWNER_ID,
    )

    budget = store.get_report_generation_budget(TASK_ID, OWNER_ID, 1, now="2026-10-29T00:00:10Z")

    assert budget["task_totals"]["elapsed_seconds"] == 1500.0
    assert budget["remaining"]["seconds"] == 0.0
    assert "seconds" in budget["exhausted"]


def test_valid_terminal_end_releases_only_unused_run_seconds(tmp_path):
    store, reservation = _setup(tmp_path)
    claim_id = str(uuid.uuid4())
    run_id = "run-terminal-valid-time"
    _claim(store, reservation, claim_id=claim_id, run_id=run_id, seconds=300)
    _persist_run(
        store,
        reservation,
        run_id,
        status="completed",
        loops=4,
        calls=9,
        started="2026-10-29T00:00:00Z",
        ended="2026-10-29T00:01:30Z",
    )

    settled = store.settle_report_generation_budget(
        TASK_ID, OWNER_ID, 1, claim_id=claim_id, now="2026-10-29T00:02:00Z"
    )
    budget = store.get_report_generation_budget(TASK_ID, OWNER_ID, 1, now="2026-10-29T00:02:10Z")

    assert settled["settled"] is True
    assert budget["task_totals"]["elapsed_seconds"] == 90.0
    assert budget["remaining"]["seconds"] == 1410.0


def test_terminal_settlement_and_duplicate_retry_do_not_reduce_persisted_elapsed_total(tmp_path):
    store, reservation = _setup(tmp_path)
    first_claim_id = "3c6fbc3c-c33d-4c24-8f9f-fd86539e26d4"
    first_run_id = "run-monotonic-elapsed"
    _claim(store, reservation, claim_id=first_claim_id, run_id=first_run_id, seconds=300)
    _persist_run(
        store,
        reservation,
        first_run_id,
        status="running",
        loops=3,
        calls=7,
        started="2026-10-29T00:00:00Z",
    )
    _claim(
        store,
        reservation,
        claim_id="cb34d6a2-4498-4e7a-869d-82bb3f03cc09",
        run_id="run-second-claim",
        loops=1,
        calls=1,
        seconds=60,
        now="2026-10-29T00:02:00Z",
    )
    with store._connect() as connection:
        connection.execute(
            "UPDATE research_agent_runs SET status='completed', ended_at=? WHERE agent_run_id=?",
            ("2026-10-29T00:01:30Z", first_run_id),
        )
        connection.commit()

    first_settlement = store.settle_report_generation_budget(
        TASK_ID, OWNER_ID, 1, claim_id=first_claim_id, now="2026-10-29T00:02:10Z"
    )
    duplicate_settlement = store.settle_report_generation_budget(
        TASK_ID, OWNER_ID, 1, claim_id=first_claim_id, now="2026-10-29T00:02:10Z"
    )

    assert first_settlement["task_totals"]["elapsed_seconds"] == 120.0
    assert duplicate_settlement["task_totals"]["elapsed_seconds"] == 120.0
    assert duplicate_settlement["replayed"] is True


def test_settlement_reads_agent_run_counters_and_never_trusts_caller_usage(tmp_path):
    store, reservation = _setup(tmp_path)
    claim_id = "81b82c6f-2147-46c6-82a5-6545e5f3257a"
    run_id = "run-settle-from-store"
    _claim(store, reservation, claim_id=claim_id, run_id=run_id, loops=40, calls=160, seconds=300)
    _persist_run(
        store,
        reservation,
        run_id,
        loops=18,
        calls=45,
        started="2026-10-29T00:00:00Z",
        ended="2026-10-29T00:01:20Z",
    )

    settled = store.settle_report_generation_budget(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        claim_id=claim_id,
    )
    budget = store.get_report_generation_budget(TASK_ID, OWNER_ID, reservation.report.report_version)

    assert settled["settled"] is True
    assert budget["report_totals"] == {"model_loops_used": 18, "tool_calls_used": 45, "elapsed_seconds": 80.0}
    assert budget["task_totals"]["model_loops_used"] == 18
    assert budget["task_totals"]["tool_calls_used"] == 45
    assert budget["task_totals"]["elapsed_seconds"] == 80.0
    assert budget["reserved"] == {"model_loops": 0, "tool_calls": 0, "seconds": 0}
    duplicate = store.settle_report_generation_budget(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        claim_id=claim_id,
    )
    assert duplicate["replayed"] is True


def test_new_report_version_keeps_historical_agent_run_usage(tmp_path):
    store, reservation = _setup(tmp_path)
    claim_id = "14169df4-1f5c-4510-b55a-ecde898a2737"
    run_id = "run-old-version"
    _claim(store, reservation, claim_id=claim_id, run_id=run_id, loops=40, calls=160, seconds=300)
    _persist_run(
        store,
        reservation,
        run_id,
        loops=27,
        calls=88,
        started="2026-10-29T00:00:00Z",
        ended="2026-10-29T00:02:00Z",
    )
    store.settle_report_generation_budget(TASK_ID, OWNER_ID, 1, claim_id=claim_id)
    with store._connect() as connection:
        connection.execute("UPDATE research_reports SET status='draft' WHERE report_id=?", (reservation.report.report_id,))
        connection.commit()

    next_reservation = store.reserve_report_generation(
        TASK_ID,
        OWNER_ID,
        plan_version=1,
        request_key="c124be68-a5b3-4b0e-b066-78e92e6b40ce",
        request_payload={"plan_version": 1, "title": "Retry"},
    )
    budget = store.get_report_generation_budget(TASK_ID, OWNER_ID, next_reservation.report.report_version)
    claim = _claim(store, next_reservation, loops=40, calls=160, seconds=300)

    assert next_reservation.report.report_version == 2
    assert budget["task_totals"]["model_loops_used"] == 27
    assert budget["task_totals"]["tool_calls_used"] == 88
    assert budget["task_totals"]["elapsed_seconds"] == 120.0
    assert claim["remaining"]["model_loops"] == 93
    assert claim["remaining"]["tool_calls"] == 392


def test_report_budget_includes_agent_runs_from_prior_research_stages(tmp_path):
    store, reservation = _setup(tmp_path)
    item = ResearchWorkItem(
        "work-item-prior-search",
        TASK_ID,
        1,
        "search_catalog",
        "search-worker",
        "[]",
        "{}",
        "completed",
        1,
        "2026-10-28T23:58:00Z",
        "2026-10-29T00:00:00Z",
        started_at="2026-10-28T23:58:00Z",
        ended_at="2026-10-29T00:00:00Z",
    )
    store.create_work_items(TASK_ID, [item])
    store.create_agent_run(
        AgentRun(
            "run-prior-search",
            "session-report-state",
            1,
            "search_worker",
            "paper-catalog-search",
            "1",
            "test-hash",
            "test-model",
            "off",
            "[]",
            status="completed",
            research_task_id=TASK_ID,
            work_item_id=item.work_item_id,
            model_loop_count=35,
            tool_call_count=90,
            started_at="2026-10-28T23:58:00Z",
            ended_at="2026-10-29T00:00:00Z",
            owner_id=OWNER_ID,
        ),
        owner_id=OWNER_ID,
    )

    budget = store.get_report_generation_budget(TASK_ID, OWNER_ID, 1)
    claim = _claim(store, reservation, loops=40, calls=160, seconds=300)

    assert budget["task_totals"]["model_loops_used"] == 35
    assert budget["task_totals"]["tool_calls_used"] == 90
    assert budget["task_totals"]["elapsed_seconds"] == 120.0
    assert claim["remaining"]["model_loops"] == 85
    assert claim["remaining"]["tool_calls"] == 390


def test_generation_state_uses_cas_and_rewrite_count_is_monotonic_and_bounded(tmp_path):
    store, reservation = _setup(tmp_path)

    first = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        1,
        expected_revision=0,
        stage="evidence_review",
        rewrite_count=0,
    )
    duplicate = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        1,
        expected_revision=0,
        stage="evidence_review",
        rewrite_count=0,
    )
    assert first["revision"] == duplicate["revision"] == 1
    assert duplicate["replayed"] is True

    with pytest.raises(ResearchReportGenerationStateConflict):
        store.update_report_generation_state(
            TASK_ID,
            OWNER_ID,
            1,
            expected_revision=0,
            stage="comparison",
            rewrite_count=0,
        )
    with pytest.raises(ValueError):
        store.update_report_generation_state(
            TASK_ID,
            OWNER_ID,
            1,
            expected_revision=1,
            stage="evidence_review",
            rewrite_count=3,
        )

    second = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        1,
        expected_revision=1,
        stage="comparison",
        rewrite_count=0,
    )
    quality_check = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        1,
        expected_revision=second["revision"],
        stage="quality_check",
        rewrite_count=0,
    )
    revision = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        1,
        expected_revision=quality_check["revision"],
        stage="targeted_revision",
        rewrite_count=1,
    )
    assert revision["rewrite_count"] == 1
    drafting = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        1,
        expected_revision=revision["revision"],
        stage="drafting",
        rewrite_count=1,
    )
    quality_check_again = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        1,
        expected_revision=drafting["revision"],
        stage="quality_check",
        rewrite_count=1,
    )
    second_revision = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        1,
        expected_revision=quality_check_again["revision"],
        stage="targeted_revision",
        rewrite_count=2,
    )
    assert second_revision["rewrite_count"] == 2
    with pytest.raises(ValueError):
        store.update_report_generation_state(
            TASK_ID,
            OWNER_ID,
            1,
            expected_revision=second_revision["revision"],
            stage="drafting",
            rewrite_count=0,
        )


def test_generation_stage_and_revision_survive_store_reopen(tmp_path):
    store, reservation = _setup(tmp_path)
    current = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        1,
        expected_revision=0,
        stage="evidence_review",
        rewrite_count=0,
    )
    reopened = ResearchStore(store.database_path)

    recovered = reopened.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        1,
        expected_revision=current["revision"],
        stage="comparison",
        rewrite_count=0,
    )

    assert recovered["revision"] == 2
    assert recovered["stage"] == "comparison"
    assert reopened.get_report_generation_reservation(TASK_ID, OWNER_ID, request_key=REQUEST_KEY).report.report_id == reservation.report.report_id


def test_completed_status_requires_passing_quality_and_accepted_agent_runner_output(tmp_path):
    store, reservation = _setup(tmp_path)
    with store._connect() as connection:
        report_json = json.loads(reservation.report.report_json)
        report_json["quality_validation"] = {"status": "pass"}
        report_json["generation"].update({"path": "agent_runner", "output_disposition": "accepted"})
        connection.execute(
            "UPDATE research_reports SET report_json=? WHERE report_id=?",
            (json.dumps(report_json), reservation.report.report_id),
        )
        connection.commit()
    stage = store.update_report_generation_state(
        TASK_ID, OWNER_ID, 1, expected_revision=0, stage="evidence_review", rewrite_count=0
    )
    stage = store.update_report_generation_state(
        TASK_ID, OWNER_ID, 1, expected_revision=stage["revision"], stage="comparison", rewrite_count=0
    )
    stage = store.update_report_generation_state(
        TASK_ID, OWNER_ID, 1, expected_revision=stage["revision"], stage="drafting", rewrite_count=0
    )
    stage = store.update_report_generation_state(
        TASK_ID, OWNER_ID, 1, expected_revision=stage["revision"], stage="quality_check", rewrite_count=0
    )

    completed = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        1,
        expected_revision=stage["revision"],
        stage="published",
        rewrite_count=0,
        status="completed",
        published=True,
    )

    assert completed["report"].status == "completed"
    assert json.loads(completed["report"].report_json)["generation"]["published"] is True


def test_terminal_report_cannot_be_overwritten_and_completed_requires_quality_pass(tmp_path):
    store, reservation = _setup(tmp_path)
    with store._connect() as connection:
        report_json = json.loads(reservation.report.report_json)
        report_json["quality_validation"] = {"status": "fail"}
        connection.execute(
            "UPDATE research_reports SET report_json=? WHERE report_id=?",
            (json.dumps(report_json), reservation.report.report_id),
        )
        connection.commit()

    with pytest.raises(ValueError):
        store.update_report_generation_state(
            TASK_ID,
            OWNER_ID,
            1,
            expected_revision=0,
            stage="published",
            rewrite_count=0,
            status="completed",
            published=True,
        )
    with store._connect() as connection:
        connection.execute("UPDATE research_reports SET status='completed' WHERE report_id=?", (reservation.report.report_id,))
        connection.commit()
    current = store.get_research_report(TASK_ID, OWNER_ID, report_version=1)

    with pytest.raises(ResearchReportGenerationStateConflict):
        store.update_report_generation_state(
            TASK_ID,
            OWNER_ID,
            1,
            expected_revision=0,
            stage="draft_saved",
            rewrite_count=0,
            status="draft",
            published=False,
        )
    assert store.get_research_report(TASK_ID, OWNER_ID, report_version=1) == current


def test_budget_claim_rolls_back_with_report_json_update_failure(tmp_path):
    store, reservation = _setup(tmp_path)
    with store._connect() as connection:
        connection.execute(
            "CREATE TRIGGER fail_report_state_update BEFORE UPDATE ON research_reports "
            "BEGIN SELECT RAISE(ABORT, 'forced update failure'); END"
        )
        connection.commit()

    with pytest.raises(Exception, match="forced update failure"):
        _claim(store, reservation, claim_id="c8700dd1-52fd-4a4b-aab1-2b0f644b8534")

    report = store.get_research_report(TASK_ID, OWNER_ID, report_version=1)
    generation = json.loads(report.report_json)["generation"]
    assert generation.get("store_state") is None


def test_read_budget_does_not_reopen_or_mutate_terminal_report(tmp_path):
    store, reservation = _setup(tmp_path)
    with store._connect() as connection:
        connection.execute("UPDATE research_reports SET status='failed' WHERE report_id=?", (reservation.report.report_id,))
        connection.commit()

    budget = store.get_report_generation_budget(TASK_ID, OWNER_ID, 1)
    report = store.get_research_report(TASK_ID, OWNER_ID, report_version=1)

    assert budget["limits"]["model_loops"] == 160
    assert report.status == "failed"
