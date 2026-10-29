"""Canonical report publication stages over the existing report reservation."""

from __future__ import annotations

import hashlib
import json
import uuid
from copy import copy

import pytest

from backend.app.memory.repository import MemoryRepository
from backend.app.research.application.evidence_matrix import EvidenceMatrixService
from backend.app.research.application.report_generation import render_report_payload
from backend.app.research.application.report_quality import ReportQualityContext
from backend.app.research.application.report_synthesis import ReportDeliveryService, ReportSynthesisError
from backend.app.research.domain.models import (
    AgentRun,
    ResearchArtifact,
    ResearchPaperSelection,
    ResearchPlan,
    ResearchSession,
    ResearchTask,
)
from backend.app.research.infrastructure.research_store import ResearchStore

OWNER_ID = "owner-report-publication"


def _report_content() -> dict:
    paper_ids = [f"paper-{number}" for number in range(1, 6)]
    evidence_ids = [f"evidence-{number}" for number in range(1, 6)]
    return {
        "schema_version": "research-report-content-v1",
        "research_question": {"text": f"Compare the evidence {'研究' * 750}"},
        "evidence_scope": {"text": "The approved evidence scope", "paper_ids": paper_ids},
        "paper_analyses": [
            {
                "paper_id": paper_id,
                "method": {"status": "supported", "text": "Method", "evidence_ids": [evidence_id]},
                "findings": {"status": "not_stated", "text": "", "evidence_ids": []},
                "limitations": {"status": "unavailable", "text": "", "evidence_ids": []},
            }
            for paper_id, evidence_id in zip(paper_ids, evidence_ids, strict=True)
        ],
        "cross_paper_comparisons": [{
            "dimension_id": "dimension-method", "paper_ids": paper_ids[:2],
            "statement": "A bounded comparison", "evidence_ids": evidence_ids[:2],
        }],
        "synthesis_findings": [
            {
                "finding_id": f"finding-{number}", "statement": f"Finding {number}",
                "paper_ids": paper_ids[:2], "evidence_ids": evidence_ids[:2],
            }
            for number in range(1, 4)
        ],
        "research_gaps": [],
    }


def _quality() -> dict:
    return {
        "schema_version": "report-quality-v1", "status": "pass", "cjk_count": 1500,
        "count_method": "report-quality-v1", "paper_count": 5, "comparison_count": 1,
        "supported_finding_count": 3, "invalid_evidence_count": 0,
        "failure_codes": [], "revision_count": 0,
    }


def _setup(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, activity = memory.create_conversation_messages(
        OWNER_ID, "Compare research evidence", None, "test-model", "normal",
    )
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = ResearchTask(
        uuid.uuid4().hex, OWNER_ID, conversation.conversation_id, "Compare research evidence",
        "en", "balanced", False, 5, 1500, "running", 1, "now", "now",
    )
    store.create_task(task)
    store.create_plan(ResearchPlan(
        task.research_task_id, 1, "approved scope", '["methods"]', "active", "now", "test-model",
    ))
    paper_ids = [f"paper-{number}" for number in range(1, 6)]
    evidence_ids = [f"evidence-{number}" for number in range(1, 6)]
    store.replace_selections(task.research_task_id, [
        ResearchPaperSelection(task.research_task_id, paper_id, 1.0, "[]", "abstract", "", None)
        for paper_id in paper_ids
    ])
    EvidenceMatrixService(store).build_matrix(
        task.research_task_id,
        OWNER_ID,
        plan_version=1,
        dimensions=[{
            "dimension_id": "dimension-method", "label": "Methods",
            "definition": "Approved methods dimension", "display_order": 0,
        }],
        claims=[{
            "claim_id": "claim-method", "topic": "Methods",
            "statement": "Bounded methods evidence", "confidence": "medium",
            "status": "supported", "evidence_ids": evidence_ids,
        }],
        evidence=[
            {
                "evidence_id": evidence_id, "claim_id": "claim-method", "paper_id": paper_id,
                "evidence_level": "abstract", "stance": "supports", "status": "available",
                "quote_digest": hashlib.sha256(f"quote-{number}".encode()).hexdigest(),
                "locator": {
                    "abstract_ref": f"catalog:{paper_id}",
                    "abstract_digest": hashlib.sha256(f"quote-{number}".encode()).hexdigest(),
                },
            }
            for number, (paper_id, evidence_id) in enumerate(zip(paper_ids, evidence_ids, strict=True), start=1)
        ],
    )
    session = ResearchSession(
        uuid.uuid4().hex, OWNER_ID, conversation.conversation_id, user.message_id,
        uuid.uuid4().hex, "running", current_plan_version=1,
        activity_message_id=activity.message_id, research_task_id=task.research_task_id,
    )
    store.create_session(session, memory_repository=memory)
    reservation = store.reserve_report_generation(
        task.research_task_id, OWNER_ID, plan_version=1,
        request_key=str(uuid.uuid4()),
        request_payload={"plan_version": 1, "schema_version": "report-quality-v1"},
        work_item_input={
            "validated_candidates": [{"candidate_id": paper_id} for paper_id in paper_ids],
        },
    )
    run = AgentRun(
        "run-draft-final", session.research_session_id, 1, "synthesizer",
        "research-report-synthesis", "1", "test-skill-hash", "test-model", "off", "[]",
        research_task_id=task.research_task_id,
        work_item_id=reservation.work_item.work_item_id,
        owner_id=OWNER_ID,
    )
    store.create_agent_run(run, owner_id=OWNER_ID)
    progress = store.update_report_generation_state(
        task.research_task_id, OWNER_ID, reservation.report.report_version,
        expected_revision=0, stage="drafting", rewrite_count=0,
    )
    progress = store.update_report_generation_state(
        task.research_task_id, OWNER_ID, reservation.report.report_version,
        expected_revision=progress["revision"], stage="quality_check", rewrite_count=0,
    )
    saved = store.save_report_generation_output(
        task.research_task_id, OWNER_ID, reservation.report.report_version,
        plan_version=1, expected_revision=progress["revision"],
        report_content=_report_content(), quality_validation=_quality(),
        generation_output={
            "path": "agent_runner", "output_disposition": "accepted",
            "agent_run_ids": ["run-comparison", "run-draft-final"],
        },
    )
    report = saved["report"]
    matrix = EvidenceMatrixService(store).read_matrix(
        task.research_task_id, OWNER_ID, plan_version=1,
    )
    quality_context = ReportQualityContext(
        task_id=task.research_task_id,
        plan_version=1,
        selected_paper_ids=paper_ids,
        evidence_matrix=matrix,
        evidence_upgrades=store.list_evidence_upgrades(task.research_task_id),
    )
    rendered = render_report_payload(
        {"report_content": _report_content()},
        report_id=report.report_id,
        report_version=report.report_version,
        context=quality_context,
    )
    delivery = ReportDeliveryService(store=store, memory_repository=memory)
    return store, memory, task, session, reservation, report, rendered, delivery


def _prepare(delivery, task, session, reservation, report, rendered, *, owner_id=OWNER_ID, version=None):
    return delivery.prepare_canonical(
        task=task, session=session, owner_id=owner_id, reservation=reservation,
        report=report,
        report_version=reservation.report.report_version if version is None else version,
        rendered=rendered,
    )


def test_prepare_canonical_writes_three_same_version_artifacts_and_pending_message(tmp_path):
    store, memory, task, session, reservation, report, rendered, delivery = _setup(tmp_path)

    prepared = _prepare(delivery, task, session, reservation, report, rendered)

    expected_manifest = json.dumps(
        rendered["report"]["citation_manifest"], ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    )
    artifacts = store.list_artifacts_for_task(
        task.research_task_id, OWNER_ID, report_version=report.report_version,
    )
    assert {item.artifact_type: item.content for item in artifacts} == {
        "markdown": rendered["markdown"], "html": rendered["html"],
        "citation_manifest": expected_manifest,
    }
    assert all(
        item.content_hash == hashlib.sha256(item.content.encode("utf-8")).hexdigest()
        for item in artifacts
    )
    assert all(item.generated_by_agent_run_id == "run-draft-final" for item in artifacts)
    assert prepared["report_version"] == report.report_version
    assert prepared["message_status"] == "pending"
    assert prepared["notification_id"] is None
    message = memory.get_activity_message(
        session.conversation_id, OWNER_ID,
        f"research-report:{task.research_task_id}:{report.report_version}",
    )
    assert message.status == "pending" and message.content == rendered["markdown"]
    assert store.get_session(session.research_session_id, OWNER_ID).final_message_id == message.message_id
    assert store.list_notifications(OWNER_ID) == []
    assert store.get_research_report(
        task.research_task_id, OWNER_ID, report_version=report.report_version,
    ).status == "generating"


def test_prepare_canonical_replays_artifacts_message_and_hash_conflicts(tmp_path):
    store, memory, task, session, reservation, report, rendered, delivery = _setup(tmp_path)

    first = _prepare(delivery, task, session, reservation, report, rendered)
    replay = _prepare(delivery, task, session, reservation, report, rendered)

    assert replay["artifact_ids"] == first["artifact_ids"]
    assert replay["message_id"] == first["message_id"]
    assert len(store.list_artifacts_for_task(task.research_task_id, OWNER_ID)) == 3
    assert len(memory.list_messages(session.conversation_id, OWNER_ID)[0]) == 3

    changed = {**rendered, "markdown": "# Mutated report\n"}
    with pytest.raises(ReportSynthesisError) as error:
        _prepare(delivery, task, session, reservation, report, changed)
    assert error.value.code == "REPORT_RENDER_INVALID"


@pytest.mark.parametrize("artifact_type", ["markdown", "html", "citation_manifest"])
def test_prepare_canonical_rejects_artifact_content_not_reproduced_by_renderer(tmp_path, artifact_type):
    store, memory, task, session, reservation, report, rendered, delivery = _setup(tmp_path)
    if artifact_type == "markdown":
        forged = {**rendered, "markdown": "# Forged report unrelated to the canonical content\n"}
    elif artifact_type == "html":
        forged = {**rendered, "html": "<h1>Forged report</h1>"}
    else:
        forged = {
            **rendered,
            "report": {
                **rendered["report"],
                "citation_manifest": {
                    **rendered["report"]["citation_manifest"], "citations": [],
                },
            },
        }

    with pytest.raises(ReportSynthesisError) as error:
        _prepare(delivery, task, session, reservation, report, forged)

    assert error.value.code == "REPORT_RENDER_INVALID"
    assert store.list_artifacts_for_task(task.research_task_id, OWNER_ID) == []
    assert memory.get_activity_message(
        session.conversation_id, OWNER_ID,
        f"research-report:{task.research_task_id}:{report.report_version}",
    ) is None


@pytest.mark.parametrize(
    "binding",
    ["task", "task_plan", "owner", "session", "session_plan", "report_plan", "version", "rendered_version"],
)
def test_prepare_canonical_rejects_mismatched_identity_before_writes(tmp_path, binding):
    store, memory, task, session, reservation, report, rendered, delivery = _setup(tmp_path)
    supplied_task, supplied_session, supplied_report = task, session, report
    owner_id = OWNER_ID
    version = report.report_version
    supplied_rendered = rendered
    if binding == "task":
        supplied_task = copy(task)
        supplied_task.research_task_id = "another-task"
    elif binding == "task_plan":
        supplied_task = copy(task)
        supplied_task.current_plan_version = 2
    elif binding == "owner":
        owner_id = "another-owner"
    elif binding == "session":
        supplied_session = copy(session)
        supplied_session.research_task_id = "another-task"
    elif binding == "session_plan":
        supplied_session = copy(session)
        supplied_session.current_plan_version = 2
    elif binding == "report_plan":
        supplied_report = copy(report)
        supplied_report.plan_version = 2
    elif binding == "version":
        version += 1
    else:
        supplied_rendered = {**rendered, "report": {**rendered["report"], "report_version": version + 1}}

    with pytest.raises(ReportSynthesisError) as error:
        _prepare(
            delivery, supplied_task, supplied_session, reservation, supplied_report,
            supplied_rendered, owner_id=owner_id, version=version,
        )

    assert error.value.code == (
        "REPORT_RENDER_INVALID" if binding == "rendered_version"
        else "REPORT_RESERVATION_BINDING_INVALID"
    )
    assert store.list_artifacts_for_task(task.research_task_id, OWNER_ID) == []
    assert memory.get_activity_message(
        session.conversation_id, OWNER_ID,
        f"research-report:{task.research_task_id}:{report.report_version}",
    ) is None


def test_prepare_rejects_nonpass_or_non_agent_runner_canonical_output(tmp_path):
    for field, value in (("quality_validation", {**_quality(), "status": "fail"}),
                         ("generation", {"path": "deterministic_fallback", "output_disposition": "accepted"})):
        store, memory, task, session, reservation, report, rendered, delivery = _setup(tmp_path / field)
        # Rewrite only the test's canonical row through the existing writer so the
        # non-publishable state is durable and bound to the same reservation.
        progress = store.get_report_generation_budget(task.research_task_id, OWNER_ID, report.report_version)
        output = {
            "path": "agent_runner", "output_disposition": "accepted",
            "agent_run_ids": ["run-comparison", "run-draft-final"],
        }
        quality = _quality()
        if field == "quality_validation":
            quality = value
        else:
            output.update(value)
        store.save_report_generation_output(
            task.research_task_id, OWNER_ID, report.report_version,
            plan_version=1, expected_revision=progress["revision"],
            report_content=_report_content(), quality_validation=quality,
            generation_output=output,
        )

        with pytest.raises(ReportSynthesisError) as error:
            _prepare(delivery, task, session, reservation, report, rendered)

        assert error.value.code == "REPORT_NOT_PUBLISHABLE"
        assert store.list_artifacts_for_task(task.research_task_id, OWNER_ID) == []
        assert memory.get_activity_message(
            session.conversation_id, OWNER_ID,
            f"research-report:{task.research_task_id}:{report.report_version}",
        ) is None


def test_prepare_rejects_a_completed_message_before_report_publish(tmp_path):
    store, memory, task, session, reservation, report, rendered, delivery = _setup(tmp_path)
    activity_key = f"research-report:{task.research_task_id}:{report.report_version}"
    memory.create_activity_message(
        session.conversation_id, OWNER_ID, rendered["markdown"],
        activity_idempotency_key=activity_key, status="completed",
        parent_message_id=session.activity_message_id,
    )

    with pytest.raises(ReportSynthesisError) as error:
        _prepare(delivery, task, session, reservation, report, rendered)

    assert error.value.code == "ARTIFACT_IMMUTABLE_CONFLICT"
    assert store.get_research_report(
        task.research_task_id, OWNER_ID, report_version=report.report_version,
    ).status == "generating"
    assert store.list_notifications(OWNER_ID) == []


def test_finalize_requires_publish_cas_then_completes_message_and_notification_once(tmp_path):
    store, memory, task, session, reservation, report, rendered, delivery = _setup(tmp_path)
    prepared = _prepare(delivery, task, session, reservation, report, rendered)

    with pytest.raises(ReportSynthesisError) as error:
        delivery.finalize_canonical(
            task=task, session=session, owner_id=OWNER_ID, reservation=reservation,
            report=report, report_version=report.report_version,
            rendered=rendered, prepared=prepared,
        )
    assert error.value.code == "REPORT_NOT_PUBLISHED"
    message = memory.get_message(prepared["message_id"], OWNER_ID)
    assert message.status == "pending"

    progress = store.get_report_generation_budget(task.research_task_id, OWNER_ID, report.report_version)
    published = store.update_report_generation_state(
        task.research_task_id, OWNER_ID, report.report_version,
        expected_revision=progress["revision"], stage="published", rewrite_count=0,
        status="completed", published=True,
    )
    result = delivery.finalize_canonical(
        task=task, session=session, owner_id=OWNER_ID, reservation=reservation,
        report=published["report"], report_version=report.report_version,
        rendered=rendered, prepared=prepared,
    )
    replay = delivery.finalize_canonical(
        task=task, session=session, owner_id=OWNER_ID, reservation=reservation,
        report=published["report"], report_version=report.report_version,
        rendered=rendered, prepared=prepared,
    )

    completed_message = memory.get_message(prepared["message_id"], OWNER_ID)
    assert completed_message.status == "completed"
    assert result["message_id"] == replay["message_id"] == prepared["message_id"]
    assert result["notification_id"] == replay["notification_id"]
    assert len(store.list_notifications(OWNER_ID)) == 1
    assert store.list_notifications(OWNER_ID)[0].notification_kind == "completed"
    prepared_replay = _prepare(
        delivery, task, session, reservation, published["report"], rendered,
    )
    assert prepared_replay["message_id"] == prepared["message_id"]
    assert prepared_replay["message_status"] == "completed"


def test_prepare_retries_after_artifacts_were_written_but_message_creation_failed(tmp_path, monkeypatch):
    store, memory, task, session, reservation, report, rendered, delivery = _setup(tmp_path)
    original = memory.create_activity_message
    calls = {"count": 0}

    def fail_once(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("simulated memory write failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(memory, "create_activity_message", fail_once)
    with pytest.raises(RuntimeError, match="simulated memory write failure"):
        _prepare(delivery, task, session, reservation, report, rendered)
    assert len(store.list_artifacts_for_task(task.research_task_id, OWNER_ID)) == 3

    prepared = _prepare(delivery, task, session, reservation, report, rendered)

    assert len(store.list_artifacts_for_task(task.research_task_id, OWNER_ID)) == 3
    assert memory.get_message(prepared["message_id"], OWNER_ID).status == "pending"


def test_finalize_recovers_notification_failure_after_message_completion(tmp_path, monkeypatch):
    store, memory, task, session, reservation, report, rendered, delivery = _setup(tmp_path)
    prepared = _prepare(delivery, task, session, reservation, report, rendered)
    progress = store.get_report_generation_budget(task.research_task_id, OWNER_ID, report.report_version)
    published = store.update_report_generation_state(
        task.research_task_id, OWNER_ID, report.report_version,
        expected_revision=progress["revision"], stage="published", rewrite_count=0,
        status="completed", published=True,
    )
    create_notification = store.create_notification
    calls = {"count": 0}

    def fail_once(notification):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("simulated notification failure")
        return create_notification(notification)

    monkeypatch.setattr(store, "create_notification", fail_once)
    with pytest.raises(RuntimeError, match="simulated notification failure"):
        delivery.finalize_canonical(
            task=task, session=session, owner_id=OWNER_ID, reservation=reservation,
            report=published["report"], report_version=report.report_version,
            rendered=rendered, prepared=prepared,
        )
    assert memory.get_message(prepared["message_id"], OWNER_ID).status == "completed"

    replay = delivery.finalize_canonical(
        task=task, session=session, owner_id=OWNER_ID, reservation=reservation,
        report=published["report"], report_version=report.report_version,
        rendered=rendered, prepared=prepared,
    )

    assert replay["notification_id"]
    assert len(store.list_notifications(OWNER_ID)) == 1


def test_replaying_older_published_report_does_not_replace_newer_session_message(tmp_path):
    store, memory, task, session, reservation, report, rendered, delivery = _setup(tmp_path)
    prepared = _prepare(delivery, task, session, reservation, report, rendered)
    progress = store.get_report_generation_budget(task.research_task_id, OWNER_ID, report.report_version)
    published = store.update_report_generation_state(
        task.research_task_id, OWNER_ID, report.report_version,
        expected_revision=progress["revision"], stage="published", rewrite_count=0,
        status="completed", published=True,
    )
    delivery.finalize_canonical(
        task=task, session=session, owner_id=OWNER_ID, reservation=reservation,
        report=published["report"], report_version=report.report_version,
        rendered=rendered, prepared=prepared,
    )

    newer_reservation = store.reserve_report_generation(
        task.research_task_id, OWNER_ID, plan_version=1,
        request_key=str(uuid.uuid4()), request_payload={"plan_version": 1, "title": "Next version"},
    )
    newer_key = f"research-report:{task.research_task_id}:{newer_reservation.report.report_version}"
    newer_markdown = "# Next report\n"
    store.create_artifact(
        ResearchArtifact(
            uuid.uuid4().hex, task.research_task_id, newer_reservation.report.report_version,
            "markdown", hashlib.sha256(newer_markdown.encode()).hexdigest(),
            "run-draft-final", content=newer_markdown,
        ),
        owner_id=OWNER_ID,
    )
    newer_message = memory.create_activity_message(
        session.conversation_id, OWNER_ID, newer_markdown,
        activity_idempotency_key=newer_key, status="pending",
        parent_message_id=session.activity_message_id,
    )
    store.update_session_links(
        session.research_session_id, OWNER_ID, final_message_id=newer_message.message_id,
    )

    replay = _prepare(
        delivery, task, session, reservation, published["report"], rendered,
    )

    assert replay["message_id"] == prepared["message_id"]
    assert store.get_session(session.research_session_id, OWNER_ID).final_message_id == newer_message.message_id


def test_replaying_older_published_report_preserves_newer_legacy_message_without_report_row(tmp_path):
    store, memory, task, session, reservation, report, rendered, delivery = _setup(tmp_path)
    prepared = _prepare(delivery, task, session, reservation, report, rendered)
    progress = store.get_report_generation_budget(task.research_task_id, OWNER_ID, report.report_version)
    published = store.update_report_generation_state(
        task.research_task_id, OWNER_ID, report.report_version,
        expected_revision=progress["revision"], stage="published", rewrite_count=0,
        status="completed", published=True,
    )
    delivery.finalize_canonical(
        task=task, session=session, owner_id=OWNER_ID, reservation=reservation,
        report=published["report"], report_version=report.report_version,
        rendered=rendered, prepared=prepared,
    )

    newer_version = report.report_version + 1
    newer_markdown = "# Newer legacy report\n"
    store.create_artifact(
        ResearchArtifact(
            uuid.uuid4().hex, task.research_task_id, newer_version, "markdown",
            hashlib.sha256(newer_markdown.encode()).hexdigest(), "run-draft-final",
            content=newer_markdown,
        ),
        owner_id=OWNER_ID,
    )
    newer_message = memory.create_activity_message(
        session.conversation_id, OWNER_ID, newer_markdown,
        activity_idempotency_key=f"research-report:{task.research_task_id}:{newer_version}",
        status="completed", parent_message_id=session.activity_message_id,
    )
    store.update_session_links(
        session.research_session_id, OWNER_ID, final_message_id=newer_message.message_id,
    )
    assert store.get_research_report(
        task.research_task_id, OWNER_ID, report_version=newer_version,
    ) is None

    replay = _prepare(delivery, task, session, reservation, published["report"], rendered)

    assert replay["message_id"] == prepared["message_id"]
    assert replay["final_message_id"] == newer_message.message_id
    assert store.get_session(session.research_session_id, OWNER_ID).final_message_id == newer_message.message_id

