"""Focused contracts for the internal synthesizer -> evidence matrix bridge."""

from __future__ import annotations

import hashlib
import json
import uuid
from types import SimpleNamespace

import pytest

from backend.app.memory.repository import MemoryRepository
from backend.app.research.application.agent_runtime import AgentRunOutput
from backend.app.research.application.evidence_matrix import EvidenceMatrixService
from backend.app.research.application.orchestrator import Orchestrator, _validate_synthesis_matrix_payload
from backend.app.research.application.report_generation import ReportGenerationService
from backend.app.research.application.report_synthesis import ReportSynthesizer, report_output_hash
from backend.app.research.domain.models import (
    AgentRun,
    ResearchArtifact,
    ResearchPaperSelection,
    ResearchSession,
    ResearchTask,
)
from backend.app.research.infrastructure.research_store import ResearchStore


def _context() -> dict:
    abstract = "A bounded catalog abstract."
    digest = hashlib.sha256(abstract.encode("utf-8")).hexdigest()
    return {
        "schema_version": "evidence-report-v1",
        "plan_version": 1,
        "dimensions": [
            {
                "dimension_id": "facet-1",
                "label": "隐私",
                "definition": "已批准研究范围维度：隐私",
                "display_order": 0,
            }
        ],
        "candidates": [
            {
                "paper_id": "paper-a",
                "catalog_snapshot_id": "search-a",
                "title": "A",
                "abstract": abstract,
                "abstract_digest": digest,
            }
        ],
        "allowed_paper_ids": ["paper-a"],
    }


def _payload() -> dict:
    digest = _context()["candidates"][0]["abstract_digest"]
    return {
        "schema_version": "evidence-report-v1",
        "plan_version": 1,
        "dimensions": [
            {
                "dimension_id": "facet-1",
                "label": "隐私",
                "definition": "已批准研究范围维度：隐私",
                "display_order": 0,
            }
        ],
        "claims": [
            {
                "claim_id": "claim-1",
                "topic": "隐私",
                "statement": "The abstract describes a privacy boundary.",
                "confidence": "medium",
                "status": "supported",
                "evidence_ids": ["evidence-1"],
            }
        ],
        "evidence": [
            {
                "evidence_id": "evidence-1",
                "claim_id": "claim-1",
                "paper_id": "paper-a",
                "evidence_level": "abstract",
                "stance": "supports",
                "status": "available",
                "quote_digest": digest,
                "locator": {
                    "catalog_snapshot_id": "search-a",
                    "abstract_ref": "catalog:paper-a",
                    "abstract_digest": digest,
                },
            }
        ],
        "cells": [
            {
                "claim_id": "claim-1",
                "paper_id": "paper-a",
                "dimension_id": "facet-1",
                "relation": "supports",
                "summary": "The supplied abstract supports the claim.",
                "evidence_ids": ["evidence-1"],
            }
        ],
    }


def test_valid_matrix_payload_is_bound_to_server_context() -> None:
    validated = _validate_synthesis_matrix_payload(_payload(), _context(), plan_version=1)

    assert validated["dimensions"] == _context()["dimensions"]
    assert validated["evidence"][0]["locator"]["catalog_snapshot_id"] == "search-a"


def test_matrix_payload_cannot_escape_candidate_allowlist() -> None:
    payload = _payload()
    payload["evidence"][0]["paper_id"] = "paper-not-allowlisted"

    with pytest.raises(ValueError):
        _validate_synthesis_matrix_payload(payload, _context(), plan_version=1)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dimensions", [{"dimension_id": "facet-9", "label": "模型发明", "definition": "bad", "display_order": 0}]),
        ("evidence_level", "fulltext"),
        ("stance", "supports"),
    ],
)
def test_matrix_bridge_rejects_scope_or_evidence_escalation(field: str, value: object) -> None:
    payload = _payload()
    if field == "dimensions":
        payload[field] = value
    elif field == "evidence_level":
        payload["evidence"][0][field] = value
    else:
        payload["evidence"][0][field] = value
        payload["evidence"][0]["evidence_level"] = "catalog"

    with pytest.raises(ValueError):
        _validate_synthesis_matrix_payload(payload, _context(), plan_version=1)


def test_matrix_bridge_rejects_server_digest_drift() -> None:
    payload = _payload()
    payload["evidence"][0]["locator"]["abstract_digest"] = "0" * 64

    with pytest.raises(ValueError):
        _validate_synthesis_matrix_payload(payload, _context(), plan_version=1)


def test_matrix_bridge_hashes_exact_snapshot_abstract_bytes() -> None:
    context = _context()
    raw_abstract = "  A bounded catalog abstract.  "
    context["candidates"][0]["abstract"] = raw_abstract
    context["candidates"][0]["abstract_digest"] = hashlib.sha256(raw_abstract.encode("utf-8")).hexdigest()
    payload = _payload()
    payload["evidence"][0]["quote_digest"] = context["candidates"][0]["abstract_digest"]
    payload["evidence"][0]["locator"]["abstract_digest"] = context["candidates"][0]["abstract_digest"]

    validated = _validate_synthesis_matrix_payload(payload, context, plan_version=1)

    assert validated["evidence"][0]["locator"]["abstract_digest"] == context["candidates"][0]["abstract_digest"]


def test_matrix_bridge_uses_same_bounded_array_limit_as_runtime() -> None:
    payload = _payload()
    payload["claims"] = [dict(payload["claims"][0], claim_id=f"claim-{index}") for index in range(65)]

    with pytest.raises(ValueError):
        _validate_synthesis_matrix_payload(payload, _context(), plan_version=1)


def test_candidate_synthesis_result_keeps_matrix_internal_only() -> None:
    result = ReportSynthesizer().synthesize(
        report_version=1,
        validated_candidates=[
            {"candidate_id": "paper-a", "verified": True, "evidence_refs": ["catalog:paper-a"], "title": "A"}
        ],
        citation_manifest=[{"citation_ref": "catalog:paper-a", "candidate_id": "paper-a"}],
    )

    assert result.evidence_matrix is None
    assert "evidence_matrix" not in result.output.model_dump(mode="json")


def test_validated_matrix_reuses_existing_matrix_service(tmp_path) -> None:
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_task(
        ResearchTask(
            "task-matrix", "owner", "conversation", "goal", "en", "balanced", False,
            1, 60, "running", 1, "", "",
        )
    )
    store.replace_selections(
        "task-matrix",
        [ResearchPaperSelection("task-matrix", "paper-a", 1.0, "[]", "abstract", "")],
    )
    matrix = _validate_synthesis_matrix_payload(_payload(), _context(), plan_version=1)

    projection = EvidenceMatrixService(store).build_matrix(
        "task-matrix",
        "owner",
        plan_version=1,
        dimensions=matrix["dimensions"],
        claims=matrix["claims"],
        evidence=matrix["evidence"],
        cells=matrix["cells"],
    )

    assert projection["schema_version"] == "evidence-report-v1"
    assert projection["claims"][0]["claim_id"] == "claim-1"


def test_matrix_rows_roll_back_as_one_unit_when_store_write_fails(tmp_path, monkeypatch) -> None:
    """A failure after the first matrix table write leaves no durable rows."""
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_task(
        ResearchTask(
            "task-matrix-rollback", "owner", "conversation", "goal", "en", "balanced", False,
            1, 60, "running", 1, "", "",
        )
    )
    store.replace_selections(
        "task-matrix-rollback",
        [ResearchPaperSelection("task-matrix-rollback", "paper-a", 1.0, "[]", "abstract", "")],
    )
    matrix = _validate_synthesis_matrix_payload(_payload(), _context(), plan_version=1)
    original = store._persist_evidence_matrix_rows

    def fail_after_writes(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected matrix write failure")

    monkeypatch.setattr(store, "_persist_evidence_matrix_rows", fail_after_writes)
    with pytest.raises(RuntimeError, match="injected matrix write failure"):
        EvidenceMatrixService(store).build_matrix(
            "task-matrix-rollback",
            "owner",
            plan_version=1,
            dimensions=matrix["dimensions"],
            claims=matrix["claims"],
            evidence=matrix["evidence"],
            cells=matrix["cells"],
        )

    assert store.list_claims("task-matrix-rollback", plan_version=1) == []
    assert store.list_claim_evidence("task-matrix-rollback", plan_version=1) == []
    assert store.list_comparison_dimensions("task-matrix-rollback", plan_version=1) == []
    assert store.list_comparison_cells("task-matrix-rollback", plan_version=1) == []


def _run_matrix_agent_scenario(
    tmp_path,
    monkeypatch,
    *,
    fail_matrix: bool = False,
    fail_report: bool = False,
    existing_artifact: bool = False,
):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, activity = memory.create_conversation_messages(
        "owner", "bounded research", None, "model", "normal"
    )
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = ResearchTask(
        "task-matrix-terminal", "owner", conversation.conversation_id, "bounded research", "en",
        "balanced", False, 1, 60, "draft", 1, "", "",
    )
    store.create_task(task)
    session = ResearchSession(
        "session-matrix-terminal", "owner", conversation.conversation_id, user.message_id,
        "draft", "running", research_task_id=task.research_task_id,
        activity_message_id=activity.message_id,
    )
    store.create_session(session, memory_repository=memory)

    candidate = {
        "candidate_id": "paper-a",
        "verified": True,
        "evidence_refs": ["catalog:paper-a"],
        "title": "A",
        "abstract": "A bounded catalog abstract.",
    }
    synthesis = ReportSynthesizer().synthesize(
        report_version=1,
        validated_candidates=[candidate],
        citation_manifest=[{"citation_ref": "catalog:paper-a", "candidate_id": "paper-a"}],
    ).output.model_dump(mode="json")
    synthesis["evidence_matrix"] = _payload()
    synthesis["output_hash"] = report_output_hash(synthesis)
    seeded_artifact = {"done": False}

    def seed_existing_artifact() -> None:
        if not existing_artifact or seeded_artifact["done"]:
            return
        seeded_artifact["done"] = True
        previous_run_id = "preexisting-synthesizer-run"
        synthesizer_item = next(
            item for item in store.list_work_items(task.research_task_id, plan_version=1)
            if item.role == "synthesizer"
        )
        store.create_agent_run(AgentRun(
            agent_run_id=previous_run_id,
            research_session_id=session.research_session_id,
            attempt=1,
            role="synthesizer",
            skill_name="test",
            skill_schema_version="1",
            skill_content_hash="test",
            resolved_model="test",
            reasoning_effort="off",
            allowed_tools_json="[]",
            provider="test",
            status="completed",
            research_task_id=task.research_task_id,
            work_item_id=synthesizer_item.work_item_id,
            owner_id="owner",
        ), owner_id="owner")
        previous_output = dict(synthesis)
        previous_output.pop("evidence_matrix", None)
        previous_output["output_hash"] = report_output_hash(previous_output)
        previous_result = ReportSynthesizer().consume_validated_output(
            output=previous_output,
            validated_candidates=[candidate],
            title="深度研究报告",
        )
        manifest = json.dumps(
            list(previous_result.citation_manifest), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        for artifact_type, content in {
            "markdown": previous_result.markdown,
            "html": previous_result.html,
            "citation_manifest": manifest,
        }.items():
            store.create_artifact(ResearchArtifact(
                artifact_id=f"preexisting-{uuid.uuid4().hex}",
                research_task_id=task.research_task_id,
                report_version=1,
                artifact_type=artifact_type,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                generated_by_agent_run_id=previous_run_id,
                content=content,
            ), owner_id="owner")

    class Probe:
        def arbitrate(self, _task_id, requested):
            return max(1, requested), None

        def release(self, _task_id):
            return None

    class Runner:
        event_sink = None

        def run(self, run_input):
            seed_existing_artifact()
            if run_input.role == "search_worker":
                output = {
                    "schema_version": "runtime-v1", "work_item_id": run_input.work_item_id,
                    "source": "usenix", "queries": ["bounded research"],
                    "candidates": ["paper-a"], "evidence_refs": ["catalog:paper-a"],
                    "source_refs": ["usenix_security"],
                }
            elif run_input.role == "paper_evaluator":
                output = {
                    "schema_version": "paper-evaluation-v1", "work_item_id": run_input.work_item_id,
                    "kept": [{
                        "candidate_id": "paper-a", "relevance_score": 1.0, "keep": True,
                        "reason": "bounded", "evidence_refs": ["catalog:paper-a"],
                    }],
                    "evidence_refs": ["catalog:paper-a"], "source_refs": ["usenix_security"],
                }
            else:
                output = synthesis
            store.create_agent_run(AgentRun(
                agent_run_id=run_input.agent_run_id,
                research_session_id=session.research_session_id,
                attempt=1,
                role=run_input.role,
                skill_name="test",
                skill_schema_version="1",
                skill_content_hash="test",
                resolved_model="test",
                reasoning_effort="off",
                allowed_tools_json="[]",
                provider="test",
                status="completed",
                research_task_id=task.research_task_id,
                work_item_id=run_input.work_item_id,
                owner_id="owner",
            ), owner_id="owner")
            return AgentRunOutput(
                "completed", output_json=output, output_hash="hash", agent_run_id=run_input.agent_run_id,
            )

    planner = SimpleNamespace(build_plan=lambda **_: SimpleNamespace(
        facets=("systems",), planner_model="test", rationale_summary="test",
        work_items=(
            {"id": "s1", "task_type": "search_catalog", "role": "search-worker", "depends_on": [], "params": {}},
            {"id": "e1", "task_type": "evaluate_papers", "role": "paper-evaluator", "depends_on": ["s1"], "params": {}},
            {"id": "syn", "task_type": "synthesize_preliminary_report", "role": "synthesizer", "depends_on": ["e1"], "params": {}},
        ),
    ))
    monkeypatch.setattr(
        "backend.app.research.application.orchestrator._validated_evaluator_candidates",
        lambda *_args, **_kwargs: [candidate],
    )
    monkeypatch.setattr(
        "backend.app.research.application.orchestrator._promote_catalog_floor",
        lambda validated, *_args, **_kwargs: validated,
    )
    monkeypatch.setattr(
        Orchestrator,
        "_build_synthesis_matrix_context",
        lambda *_args, **_kwargs: _context(),
    )
    if fail_matrix:
        monkeypatch.setattr(
            EvidenceMatrixService,
            "build_matrix",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("injected matrix failure")),
        )
    if fail_report:
        monkeypatch.setattr(
            ReportGenerationService,
            "generate",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("injected report generation failure")),
        )

    result = Orchestrator(
        store=store, planner=planner, agent_runner=Runner(), probe=Probe(), memory_repository=memory,
    ).run(task.research_task_id, "owner")
    return result, store, task, memory


def test_matrix_build_failure_cannot_close_agent_task_as_completed(tmp_path, monkeypatch) -> None:
    """A candidate artifact fallback is still a degraded, non-canonical result."""
    result, store, task, _memory = _run_matrix_agent_scenario(tmp_path, monkeypatch, fail_matrix=True)

    assert result.status == "partial"
    assert result.error_code == "MATRIX_NOT_READY"
    assert store.list_research_reports(task.research_task_id, "owner") == []


def test_canonical_report_generation_failure_cannot_close_agent_task_as_completed(tmp_path, monkeypatch) -> None:
    result, store, task, memory = _run_matrix_agent_scenario(tmp_path, monkeypatch, fail_report=True)

    assert result.status == "partial"
    assert result.error_code == "REPORT_NOT_READY"
    assert store.list_research_reports(task.research_task_id, "owner") == []
    assert store.get_task(task.research_task_id, "owner").status == "partial"
    notifications = store.list_notifications("owner")
    assert notifications
    assert all(item.notification_kind != "completed" for item in notifications)
    activity = memory.get_activity_message(
        task.conversation_id, "owner", f"research-report:{task.research_task_id}:1"
    )
    assert activity is not None
    assert activity.status == "partial"
    terminal = [
        event for event in store.list_events(task.research_task_id)
        if event.event_type == "terminal"
    ]
    assert terminal
    terminal_payload = json.loads(terminal[-1].safe_payload_json)
    assert terminal_payload["status"] == "partial"
    assert terminal_payload["error_code"] == "REPORT_NOT_READY"


def test_canonical_generation_uses_first_available_version_without_artifact(tmp_path, monkeypatch) -> None:
    result, store, task, _memory = _run_matrix_agent_scenario(tmp_path, monkeypatch)

    assert result.status == "completed"
    assert [item.report_version for item in store.list_research_reports(task.research_task_id, "owner")] == [1]
    assert {item.report_version for item in store.list_artifacts_for_task(task.research_task_id, "owner")} == {1}


def test_canonical_generation_uses_next_available_version_after_existing_artifact(tmp_path, monkeypatch) -> None:
    result, store, task, _memory = _run_matrix_agent_scenario(
        tmp_path, monkeypatch, existing_artifact=True,
    )

    assert result.status == "completed"
    assert [item.report_version for item in store.list_research_reports(task.research_task_id, "owner")] == [2]
    assert {item.report_version for item in store.list_artifacts_for_task(task.research_task_id, "owner")} == {1}
