from __future__ import annotations

import json
import uuid

import pytest

from backend.app.research.domain.models import ResearchPlan, ResearchTask
from backend.app.research.infrastructure.research_store import (
    ResearchReportConflict,
    ResearchReportGenerationStateConflict,
    ResearchStore,
    ResearchTaskNotFound,
)

OWNER_ID = "owner-canonical-report"
TASK_ID = "task-canonical-report"
REQUEST_KEY = "f75c96c7-05bc-4ef0-a85e-b16d1766dd99"


def _setup(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_task(
        ResearchTask(
            TASK_ID,
            OWNER_ID,
            "conversation-canonical-report",
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
            "approved evidence scope",
            '["methods"]',
            "completed",
            "2026-10-29T00:00:00Z",
            "test-model",
        )
    )
    reservation = store.reserve_report_generation(
        TASK_ID,
        OWNER_ID,
        plan_version=1,
        request_key=REQUEST_KEY,
        request_payload={"plan_version": 1, "title": "Evidence report"},
    )
    return store, reservation


def _report_content(question="Compare findings"):
    paper_ids = [f"paper-{number}" for number in range(1, 6)]
    evidence_ids = [f"evidence-{number}" for number in range(1, 6)]
    return {
        "schema_version": "research-report-content-v1",
        "research_question": {"text": question},
        "evidence_scope": {"text": "Approved scope", "paper_ids": paper_ids},
        "paper_analyses": [
            {
                "paper_id": paper_id,
                "method": {"status": "supported", "text": "Method", "evidence_ids": [evidence_id]},
                "findings": {"status": "not_stated", "text": "", "evidence_ids": []},
                "limitations": {"status": "unavailable", "text": "", "evidence_ids": []},
            }
            for paper_id, evidence_id in zip(paper_ids, evidence_ids, strict=True)
        ],
        "cross_paper_comparisons": [
            {
                "dimension_id": "dimension-method",
                "paper_ids": paper_ids[:2],
                "statement": "A bounded comparison",
                "evidence_ids": evidence_ids[:2],
            }
        ],
        "synthesis_findings": [
            {
                "finding_id": f"finding-{number}",
                "statement": f"Finding {number}",
                "paper_ids": paper_ids[:2],
                "evidence_ids": evidence_ids[:2],
            }
            for number in range(1, 4)
        ],
        "research_gaps": [],
    }


def _quality_validation(status="pass"):
    return {
        "schema_version": "report-quality-v1",
        "status": status,
        "cjk_count": 1500 if status == "pass" else 0,
        "count_method": "report-quality-v1",
        "paper_count": 5,
        "comparison_count": 1,
        "supported_finding_count": 3,
        "invalid_evidence_count": 0,
        "failure_codes": [] if status == "pass" else ["CJK_COUNT_BELOW_MINIMUM"],
        "revision_count": 0,
    }


def _generation_output():
    return {
        "path": "agent_runner",
        "output_disposition": "accepted",
        "agent_run_ids": ["run-canonical-1"],
        "provider": "test-provider",
        "model": "test-model",
        "fallback_reason_code": None,
    }


def _write(store, reservation, *, expected_revision=0, question="Compare findings", plan_version=1):
    return store.save_report_generation_output(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        plan_version=plan_version,
        expected_revision=expected_revision,
        report_content=_report_content(question),
        quality_validation=_quality_validation(),
        generation_output=_generation_output(),
    )


def test_canonical_output_updates_reserved_row_and_preserves_budget_ledger(tmp_path):
    store, reservation = _setup(tmp_path)
    claim = store.claim_report_generation_budget(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        claim_id=str(uuid.uuid4()),
        agent_run_id="run-canonical-1",
        requested_model_loops=20,
        requested_tool_calls=40,
        requested_seconds=120,
    )
    before = json.loads(claim["report"].report_json)

    result = _write(store, reservation, expected_revision=claim["revision"])

    saved = json.loads(result["report"].report_json)
    assert result["report"].report_id == reservation.report.report_id
    assert result["report"].status == "generating"
    assert saved["report_content"] == _report_content()
    assert saved["quality_validation"] == _quality_validation()
    assert saved["generation"]["path"] == "agent_runner"
    assert saved["generation"]["output_disposition"] == "accepted"
    assert saved["generation"]["budget"] == before["generation"]["budget"]
    assert saved["generation"]["store_state"] == {
        **before["generation"]["store_state"],
        "revision": claim["revision"] + 1,
    }
    with store._connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_reports WHERE research_task_id=?", (TASK_ID,)
        ).fetchone()[0] == 1


def test_canonical_output_replay_is_idempotent_but_divergent_stale_write_conflicts(tmp_path):
    store, reservation = _setup(tmp_path)
    first = _write(store, reservation)

    replay = _write(store, reservation, expected_revision=0)

    assert replay["replayed"] is True
    assert replay["revision"] == first["revision"] == 1
    with pytest.raises(ResearchReportGenerationStateConflict):
        _write(store, reservation, expected_revision=0, question="Different content")


def test_canonical_output_checks_owner_plan_and_report_version(tmp_path):
    store, reservation = _setup(tmp_path)

    with pytest.raises(ResearchTaskNotFound):
        store.save_report_generation_output(
            TASK_ID,
            "another-owner",
            reservation.report.report_version,
            plan_version=1,
            expected_revision=0,
            report_content=_report_content(),
            quality_validation=_quality_validation(),
            generation_output=_generation_output(),
        )
    with pytest.raises(ResearchTaskNotFound):
        store.save_report_generation_output(
            "another-task",
            OWNER_ID,
            reservation.report.report_version,
            plan_version=1,
            expected_revision=0,
            report_content=_report_content(),
            quality_validation=_quality_validation(),
            generation_output=_generation_output(),
        )
    with pytest.raises(ResearchReportGenerationStateConflict):
        _write(store, reservation, plan_version=2)
    with pytest.raises(ResearchReportConflict):
        store.save_report_generation_output(
            TASK_ID,
            OWNER_ID,
            reservation.report.report_version + 1,
            plan_version=1,
            expected_revision=0,
            report_content=_report_content(),
            quality_validation=_quality_validation(),
            generation_output=_generation_output(),
        )


@pytest.mark.parametrize(
    ("scope", "field"),
    [
        ("top", "report_id"),
        ("top", "report_version"),
        ("top", "plan_version"),
        ("top", "request_key"),
        ("top", "request_fingerprint"),
        ("nested", "report_id"),
        ("nested", "report_version"),
        ("nested", "plan_version"),
        ("nested", "request_key"),
        ("nested", "request_fingerprint"),
    ],
)
def test_reservation_read_and_canonical_write_reject_mismatched_work_item_identity(
    tmp_path, scope, field
):
    store, reservation = _setup(tmp_path)
    with store._connect() as connection:
        row = connection.execute(
            "SELECT input_json FROM research_work_items WHERE work_item_id=?",
            (reservation.work_item.work_item_id,),
        ).fetchone()
        item_input = json.loads(row["input_json"])
        target = item_input if scope == "top" else item_input["report_generation"]
        if field in {"report_version", "plan_version"}:
            target[field] = 99
        elif field == "request_key":
            target[field] = "11111111-1111-4111-8111-111111111111"
        elif field == "request_fingerprint":
            target[field] = "0" * 64
        else:
            target[field] = "report-from-another-reservation"
        connection.execute(
            "UPDATE research_work_items SET input_json=? WHERE work_item_id=?",
            (json.dumps(item_input), reservation.work_item.work_item_id),
        )
        connection.commit()

    with pytest.raises(RuntimeError):
        store.get_report_generation_reservation(TASK_ID, OWNER_ID, request_key=REQUEST_KEY)
    with pytest.raises(RuntimeError):
        _write(store, reservation)


def test_canonical_output_cannot_replace_terminal_report(tmp_path):
    store, reservation = _setup(tmp_path)
    first = _write(store, reservation)
    stage = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        expected_revision=first["revision"],
        stage="evidence_review",
        rewrite_count=0,
    )
    stage = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        expected_revision=stage["revision"],
        stage="comparison",
        rewrite_count=0,
    )
    stage = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        expected_revision=stage["revision"],
        stage="drafting",
        rewrite_count=0,
    )
    stage = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        expected_revision=stage["revision"],
        stage="quality_check",
        rewrite_count=0,
    )
    terminal = store.update_report_generation_state(
        TASK_ID,
        OWNER_ID,
        reservation.report.report_version,
        expected_revision=stage["revision"],
        stage="draft_saved",
        rewrite_count=0,
        status="draft",
        published=False,
    )
    before = terminal["report"].report_json

    with pytest.raises(ResearchReportGenerationStateConflict):
        _write(store, reservation, expected_revision=terminal["revision"], question="Overwrite")

    assert store.get_research_report(TASK_ID, OWNER_ID, report_version=1).report_json == before


def test_canonical_output_enforces_bounded_validated_envelope(tmp_path):
    store, reservation = _setup(tmp_path)
    content = _report_content()
    content["unexpected"] = "not allowed"
    with pytest.raises(ValueError):
        store.save_report_generation_output(
            TASK_ID,
            OWNER_ID,
            reservation.report.report_version,
            plan_version=1,
            expected_revision=0,
            report_content=content,
            quality_validation=_quality_validation(),
            generation_output=_generation_output(),
        )
    generation_output = _generation_output()
    generation_output["untrusted_raw_output"] = "not part of the generation envelope"
    with pytest.raises(ValueError):
        store.save_report_generation_output(
            TASK_ID,
            OWNER_ID,
            reservation.report.report_version,
            plan_version=1,
            expected_revision=0,
            report_content=_report_content(),
            quality_validation=_quality_validation(),
            generation_output=generation_output,
        )

    with pytest.raises(ValueError):
        store.save_report_generation_output(
            TASK_ID,
            OWNER_ID,
            reservation.report.report_version,
            plan_version=1,
            expected_revision=0,
            report_content=_report_content(question="x" * (512 * 1024)),
            quality_validation=_quality_validation(),
            generation_output=_generation_output(),
        )

