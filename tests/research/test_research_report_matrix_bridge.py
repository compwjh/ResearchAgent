"""Focused contracts for the internal synthesizer -> evidence matrix bridge."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.app.memory.repository import MemoryRepository
from backend.app.paper_discovery.domain.paper_discovery import CatalogPaper, SearchJob, SearchResult, SearchSession
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.research.application.agent_runtime import AgentRunOutput
from backend.app.research.application.evidence_matrix import EvidenceMatrixService
from backend.app.research.application.orchestrator import (
    Orchestrator,
    _separate_synthesis_matrix,
    _validate_synthesis_matrix_payload,
)
from backend.app.research.application.report_generation import ReportGenerationService
from backend.app.research.application.report_synthesis import ReportSynthesizer, report_output_hash
from backend.app.research.application.search_catalog_adapter import CatalogSearchAdapter
from backend.app.research.domain.models import (
    AgentRun,
    ResearchArtifact,
    ResearchPaperSelection,
    ResearchPlan,
    ResearchSession,
    ResearchTask,
)
from backend.app.research.infrastructure.research_store import ResearchStore


def _context(paper_ids: list[str] | None = None) -> dict:
    paper_ids = paper_ids or ["paper-a"]
    candidates = []
    for paper_id in paper_ids:
        abstract = "A bounded catalog abstract." if paper_id == "paper-a" else f"A bounded catalog abstract for {paper_id}."
        candidates.append({
            "paper_id": paper_id,
            "catalog_snapshot_id": "search-a" if paper_id == "paper-a" else f"search-{paper_id}",
            "title": "A" if paper_id == "paper-a" else paper_id,
            "abstract": abstract,
            "abstract_digest": hashlib.sha256(abstract.encode("utf-8")).hexdigest(),
        })
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
        "candidates": candidates,
        "allowed_paper_ids": paper_ids,
    }


def _payload(paper_ids: list[str] | None = None) -> dict:
    context = _context(paper_ids)
    paper_ids = paper_ids or ["paper-a"]
    evidence_ids = [f"evidence-{index}" for index in range(1, len(paper_ids) + 1)]
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
                "evidence_ids": evidence_ids,
            }
        ],
        "evidence": [
            {
                "evidence_id": evidence_id,
                "claim_id": "claim-1",
                "paper_id": paper_id,
                "evidence_level": "abstract",
                "stance": "supports",
                "status": "available",
                "quote_digest": context["candidates"][index - 1]["abstract_digest"],
                "locator": {
                    "catalog_snapshot_id": context["candidates"][index - 1]["catalog_snapshot_id"],
                    "abstract_ref": f"catalog:{paper_id}",
                    "abstract_digest": context["candidates"][index - 1]["abstract_digest"],
                },
            }
            for index, (paper_id, evidence_id) in enumerate(zip(paper_ids, evidence_ids, strict=True), start=1)
        ],
        "cells": [
            {
                "claim_id": "claim-1",
                "paper_id": paper_id,
                "dimension_id": "facet-1",
                "relation": "supports",
                "summary": "The supplied abstract supports the claim.",
                "evidence_ids": [evidence_id],
            }
            for paper_id, evidence_id in zip(paper_ids, evidence_ids, strict=True)
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


def test_separate_synthesis_matrix_strips_runtime_work_item_binding() -> None:
    """Runtime identity must not enter the public report envelope."""
    result = ReportSynthesizer().synthesize(
        report_version=1,
        validated_candidates=[
            {"candidate_id": "paper-a", "verified": True, "evidence_refs": ["catalog:paper-a"], "title": "A"}
        ],
        citation_manifest=[{"citation_ref": "catalog:paper-a", "candidate_id": "paper-a"}],
    )
    payload = result.output.model_dump(mode="json")
    payload["work_item_id"] = "task:syn"
    payload["evidence_matrix"] = _payload()
    payload["output_hash"] = report_output_hash(payload)

    artifact, matrix, error = _separate_synthesis_matrix(payload, _context(), plan_version=1)

    assert error is None
    assert matrix is not None
    assert artifact.get("work_item_id") is None
    assert artifact["output_hash"] == report_output_hash(artifact)


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


def test_live_snapshot_context_resolves_shared_store_when_adapter_is_unbound(tmp_path, monkeypatch) -> None:
    """The live adapter starts unbound even after the shared search DB has snapshots."""
    research_store = ResearchStore(tmp_path / "research.sqlite3")
    catalog_store = PaperDiscoveryStore(database_path=tmp_path / "paper-search.sqlite3")
    task = ResearchTask(
        "task-live-matrix-context", "owner", "conversation", "比较至少 5 篇方法与局限", "zh",
        "balanced", False, 5, 60, "running", 1, "", "search-a",
    )
    research_store.create_task(task)
    research_store.create_plan(
        ResearchPlan(
            task.research_task_id,
            1,
            "bounded live shape",
            json.dumps(["比较至少 5 篇方法与局限", "研究方法"], ensure_ascii=False),
            "active",
            "2026-01-01T00:00:00Z",
            "test",
        )
    )

    now = datetime.now(timezone.utc).replace(microsecond=0)
    created_at = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    expires_at = (now + timedelta(days=7)).isoformat(timespec="seconds").replace("+00:00", "Z")
    snapshots = {
        "paper-a": ("search-a", "Stop, Don't Click Here Anymore", "A snapshot abstract for paper A."),
        "paper-b": ("search-a", "Cascade", "A snapshot abstract for paper B."),
        "paper-c": ("search-a", "GhostRace", "A snapshot abstract for paper C."),
        "paper-d": ("search-b", "DNN-GP", "A snapshot abstract for paper D."),
    }
    for search_id in ("search-a", "search-b"):
        catalog_store.save_search(SearchSession(search_id, "比较至少 5 篇方法与局限", expires_at, created_at), [])
        catalog_store.create_search_job(SearchJob(
            search_id=search_id,
            query="比较至少 5 篇方法与局限",
            conference_ids=["usenix-security"],
            years=[2024],
            status="completed",
            graph_version="catalog-search-v1",
            total_results=sum(1 for source_id, *_ in snapshots.values() if source_id == search_id),
            created_at=created_at,
            completed_at=created_at,
            expires_at=expires_at,
            updated_at=created_at,
        ))
    for rank, (paper_id, (search_id, title, abstract)) in enumerate(snapshots.items(), start=1):
        catalog_store.upsert_catalog_paper(CatalogPaper(
            catalog_paper_id=paper_id,
            conference_id="usenix-security",
            year=2024,
            title=title,
            normalized_title=paper_id,
            authors=[paper_id],
            abstract=abstract,
            metadata_hash=hashlib.sha256(f"{paper_id}:{abstract}".encode("utf-8")).hexdigest(),
            index_status="indexed",
            index_version=1,
            created_at=created_at,
            updated_at=created_at,
        ))
        catalog_store.save_search_result(SearchResult(
            search_id=search_id,
            catalog_paper_id=paper_id,
            rank=rank,
            snapshot={
                "candidate_id": paper_id,
                "catalog_paper_id": paper_id,
                "search_id": search_id,
                "title": title,
                "abstract": abstract,
            },
            created_at=created_at,
        ))
    research_store.replace_selections(
        task.research_task_id,
        [ResearchPaperSelection(
            task.research_task_id,
            paper_id,
            1.0,
            "[]",
            "catalog",
            created_at,
            search_id,
        ) for paper_id, (search_id, _title, _abstract) in snapshots.items()],
    )

    validated_candidates = [
        {
            "candidate_id": paper_id,
            "evidence_refs": [f"catalog:{paper_id}"],
            "title": title,
            "abstract": abstract,
            "verified": True,
        }
        for paper_id, (_search_id, title, abstract) in snapshots.items()
    ]
    adapter = CatalogSearchAdapter()
    monkeypatch.setattr("backend.app.api.common._paper_store", lambda: catalog_store)
    orchestrator = Orchestrator(
        store=research_store,
        search_adapter=adapter,
        probe=object(),
    )

    context = orchestrator._build_synthesis_matrix_context(
        task=research_store.get_task(task.research_task_id, "owner"),
        plan_version=1,
        validated_candidates=validated_candidates,
    )

    assert context is not None
    assert context["allowed_paper_ids"] == list(snapshots)
    assert [item["catalog_snapshot_id"] for item in context["candidates"]] == [
        "search-a", "search-a", "search-a", "search-b",
    ]
    assert all(item["abstract_digest"] == hashlib.sha256(
        snapshots[item["paper_id"]][2].encode("utf-8")
    ).hexdigest() for item in context["candidates"])


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
    target_paper_count: int = 1,
    minimum_paper_count: int | None = None,
    candidate_count: int = 1,
    validated_sequences: list[list[dict]] | None = None,
    synthesis_has_matrix: bool = True,
):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, activity = memory.create_conversation_messages(
        "owner", "bounded research", None, "model", "normal"
    )
    store = ResearchStore(tmp_path / "research.sqlite3")
    paper_ids = [f"paper-{chr(ord('a') + index)}" for index in range(candidate_count)]
    candidates = [
        {
            "candidate_id": paper_id,
            "verified": True,
            "evidence_refs": [f"catalog:{paper_id}"],
            "title": "A" if paper_id == "paper-a" else paper_id,
            "abstract": _context(paper_ids)["candidates"][index]["abstract"],
        }
        for index, paper_id in enumerate(paper_ids)
    ]
    task = ResearchTask(
        "task-matrix-terminal", "owner", conversation.conversation_id, "bounded research", "en",
        "balanced", False, target_paper_count, 60, "draft", 1, "", "",
    )
    store.create_task(task)
    session = ResearchSession(
        "session-matrix-terminal", "owner", conversation.conversation_id, user.message_id,
        "draft", "running", research_task_id=task.research_task_id,
        activity_message_id=activity.message_id,
    )
    store.create_session(session, memory_repository=memory)

    synthesis = ReportSynthesizer().synthesize(
        report_version=1,
        validated_candidates=candidates,
        citation_manifest=[
            {"citation_ref": f"catalog:{paper_id}", "candidate_id": paper_id}
            for paper_id in paper_ids
        ],
    ).output.model_dump(mode="json")
    if synthesis_has_matrix:
        synthesis["evidence_matrix"] = _payload(paper_ids)
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
            validated_candidates=candidates,
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
                    "candidates": paper_ids,
                    "evidence_refs": [f"catalog:{paper_id}" for paper_id in paper_ids],
                    "source_refs": ["usenix_security"],
                }
            elif run_input.role == "paper_evaluator":
                output = {
                    "schema_version": "paper-evaluation-v1", "work_item_id": run_input.work_item_id,
                    "kept": [
                        {
                            "candidate_id": paper_id, "relevance_score": 1.0, "keep": True,
                            "reason": "bounded", "evidence_refs": [f"catalog:{paper_id}"],
                        }
                        for paper_id in paper_ids
                    ],
                    "evidence_refs": [f"catalog:{paper_id}" for paper_id in paper_ids],
                    "source_refs": ["usenix_security"],
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
    validated_calls = {"count": 0}

    def validated_candidates(*_args, **_kwargs):
        if validated_sequences:
            index = min(validated_calls["count"], len(validated_sequences) - 1)
            validated_calls["count"] += 1
            return [dict(item) for item in validated_sequences[index]]
        return list(candidates)

    monkeypatch.setattr(
        "backend.app.research.application.orchestrator._validated_evaluator_candidates",
        validated_candidates,
    )
    monkeypatch.setattr(
        "backend.app.research.application.orchestrator._promote_catalog_floor",
        lambda validated, *_args, **_kwargs: validated,
    )
    monkeypatch.setattr(
        Orchestrator,
        "_build_synthesis_matrix_context",
        lambda *_args, **_kwargs: _context(paper_ids),
    )
    if minimum_paper_count is not None:
        monkeypatch.setattr(
            store,
            "get_session_plan",
            lambda *_args, **_kwargs: SimpleNamespace(
                capabilities_json="[]",
                budget_json=json.dumps({"target_paper_count": target_paper_count}),
                scope_json=json.dumps([f"min_paper_count:{minimum_paper_count}"]),
            ),
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


def test_synthesis_keeps_the_same_candidate_allowlist_after_final_projection_changes(
    tmp_path, monkeypatch
) -> None:
    """A valid model citation must not be invalidated by a second floor pass."""
    candidates = [
        {
            "candidate_id": f"paper-{chr(ord('a') + index)}",
            "verified": True,
            "evidence_refs": [f"catalog:paper-{chr(ord('a') + index)}"],
        }
        for index in range(5)
    ]
    result, store, task, _memory = _run_matrix_agent_scenario(
        tmp_path,
        monkeypatch,
        candidate_count=5,
        validated_sequences=[
            candidates,
            [*candidates[:4], {
                "candidate_id": "paper-x",
                "verified": True,
                "evidence_refs": ["catalog:paper-x"],
            }],
        ],
    )

    assert result.status == "completed"
    assert result.error_code is None
    assert result.selected_count == 5
    assert {item.catalog_paper_id for item in store.list_selections(task.research_task_id)} == {
        item["candidate_id"] for item in candidates
    }
    assert store.list_research_reports(task.research_task_id, "owner")


def test_matrix_build_failure_cannot_close_agent_task_as_completed(tmp_path, monkeypatch) -> None:
    """A candidate artifact fallback is still a degraded, non-canonical result."""
    result, store, task, _memory = _run_matrix_agent_scenario(tmp_path, monkeypatch, fail_matrix=True)

    assert result.status == "partial"
    assert result.error_code == "MATRIX_NOT_READY"
    assert store.list_research_reports(task.research_task_id, "owner") == []


def test_missing_matrix_output_stays_partial_without_canonical_report(tmp_path, monkeypatch) -> None:
    result, store, task, _memory = _run_matrix_agent_scenario(
        tmp_path,
        monkeypatch,
        synthesis_has_matrix=False,
    )

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


@pytest.mark.parametrize(
    ("minimum_paper_count", "candidate_count", "expected_status", "expected_error"),
    [
        (5, 1, "partial", "EVIDENCE_INSUFFICIENT"),
        (5, 4, "partial", "EVIDENCE_INSUFFICIENT"),
        (1, 4, "completed", None),
        (5, 5, "completed", None),
    ],
)
def test_approved_minimum_controls_agent_completion_and_surface_reason(
    tmp_path,
    monkeypatch,
    minimum_paper_count: int,
    candidate_count: int,
    expected_status: str,
    expected_error: str | None,
) -> None:
    result, store, task, memory = _run_matrix_agent_scenario(
        tmp_path,
        monkeypatch,
        target_paper_count=5,
        minimum_paper_count=minimum_paper_count,
        candidate_count=candidate_count,
    )

    selected_count = candidate_count
    shortfall_reason = (
        f"approved minimum paper count not met: selected {selected_count} of {minimum_paper_count}"
        if selected_count < minimum_paper_count else None
    )
    assert result.status == expected_status
    assert result.error_code == expected_error
    assert result.selected_count == selected_count
    assert store.get_task(task.research_task_id, "owner").status == expected_status

    terminal = [
        event for event in store.list_events(task.research_task_id)
        if event.event_type == "terminal"
    ]
    assert terminal
    terminal_payload = json.loads(terminal[-1].safe_payload_json)
    assert terminal_payload["status"] == expected_status
    assert terminal_payload["selected_count"] == selected_count
    assert terminal_payload.get("error_code") == expected_error
    assert terminal_payload.get("reason") == shortfall_reason

    activity = memory.get_activity_message(
        task.conversation_id, "owner", f"research-report:{task.research_task_id}:1"
    )
    assert activity is not None
    assert activity.status == expected_status
    if shortfall_reason:
        assert shortfall_reason in activity.content

    markdown = next(
        item.content
        for item in store.list_artifacts_for_task(task.research_task_id, "owner")
        if item.artifact_type == "markdown"
    )
    if shortfall_reason:
        assert shortfall_reason in markdown

    reports = store.list_research_reports(task.research_task_id, "owner")
    assert reports
    report_limitations = json.loads(reports[-1].limitations_json)
    if shortfall_reason:
        assert shortfall_reason in report_limitations
    else:
        assert shortfall_reason not in report_limitations

    notifications = store.list_notifications("owner")
    assert notifications
    if expected_status == "partial":
        assert all(item.notification_kind != "completed" for item in notifications)
        assert all(
            json.loads(item.payload_json).get("reason") == shortfall_reason
            for item in notifications
        )
    else:
        assert any(item.notification_kind == "completed" for item in notifications)
        assert all(json.loads(item.payload_json).get("reason") is None for item in notifications)


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
