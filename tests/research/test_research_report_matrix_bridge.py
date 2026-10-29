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
    _matrix_persistence_diagnostic,
    _separate_synthesis_matrix,
    _validate_synthesis_matrix_payload,
)
from backend.app.research.application.report_generation import ReportGenerationService
from backend.app.research.application.report_synthesis import ReportSynthesizer, report_output_hash
from backend.app.research.application.search_catalog_adapter import CatalogSearchAdapter
from backend.app.research.domain.models import (
    AgentCheckpoint,
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


def _quality_report_content(paper_ids: list[str], *, evidence_ids: list[str] | None = None) -> dict:
    evidence_ids = evidence_ids or [f"evidence-{index}" for index in range(1, 6)]
    paper_analyses = []
    for index, paper_id in enumerate(paper_ids):
        paper_analyses.append({
            "paper_id": paper_id,
            "method": {
                "status": "supported", "text": "研究" * 320,
                "evidence_ids": [evidence_ids[index]],
            },
            "findings": {"status": "unavailable", "text": "", "evidence_ids": []},
            "limitations": {"status": "not_stated", "text": "", "evidence_ids": []},
        })
    shared_evidence = evidence_ids[:2]
    return {
        "schema_version": "research-report-content-v1",
        "research_question": {"text": "比较五篇论文中的隐私方法"},
        "evidence_scope": {"text": "根据已核验摘要进行比较", "paper_ids": list(paper_ids)},
        "paper_analyses": paper_analyses,
        "cross_paper_comparisons": [{
            "dimension_id": "facet-1", "paper_ids": list(paper_ids[:2]),
            "statement": "两篇论文都描述了隐私边界。", "evidence_ids": shared_evidence,
        }],
        "synthesis_findings": [{
            "finding_id": f"finding-{index}", "statement": f"跨论文发现{index}。",
            "paper_ids": list(paper_ids[:2]), "evidence_ids": shared_evidence,
        } for index in range(1, 4)],
        "research_gaps": [],
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

    artifact, matrix, error, diagnostic = _separate_synthesis_matrix(
        payload, _context(), research_task_id="task-syn", plan_version=1,
    )

    assert error is None
    assert diagnostic is None
    assert matrix is not None
    assert matrix["claims"][0]["claim_id"] != "claim-1"
    assert matrix["evidence"][0]["evidence_id"] != "evidence-1"
    assert artifact.get("work_item_id") is None
    assert artifact["output_hash"] == report_output_hash(artifact)


def _synthesis_envelope_with_matrix(matrix: dict) -> dict:
    result = ReportSynthesizer().synthesize(
        report_version=1,
        validated_candidates=[{
            "candidate_id": "paper-a", "verified": True,
            "evidence_refs": ["catalog:paper-a"], "title": "A",
        }],
        citation_manifest=[{"citation_ref": "catalog:paper-a", "candidate_id": "paper-a"}],
    )
    payload = result.output.model_dump(mode="json")
    payload["evidence_matrix"] = matrix
    payload["work_item_id"] = "task:syn"
    payload["output_hash"] = report_output_hash(payload)
    return payload


def test_matrix_ids_are_task_plan_scoped_and_replay_idempotently(tmp_path) -> None:
    store = ResearchStore(tmp_path / "research.sqlite3")
    task_ids = ["task-matrix-alpha", "task-matrix-beta"]
    for task_id in task_ids:
        store.create_task(ResearchTask(
            task_id, "owner", "conversation", "goal", "en", "balanced", False,
            1, 60, "running", 1, "", "",
        ))
        store.replace_selections(
            task_id,
            [ResearchPaperSelection(task_id, "paper-a", 1.0, "[]", "abstract", "")],
        )

    bound_matrices = {}
    for task_id in task_ids:
        _, matrix, error, diagnostic = _separate_synthesis_matrix(
            _synthesis_envelope_with_matrix(_payload()),
            _context(),
            research_task_id=task_id,
            plan_version=1,
        )
        assert error is None
        assert diagnostic is None
        assert matrix is not None
        bound_matrices[task_id] = matrix
        EvidenceMatrixService(store).build_matrix(
            task_id,
            "owner",
            plan_version=1,
            dimensions=matrix["dimensions"],
            claims=matrix["claims"],
            evidence=matrix["evidence"],
            cells=matrix["cells"],
        )

    alpha_claim_id = bound_matrices[task_ids[0]]["claims"][0]["claim_id"]
    beta_claim_id = bound_matrices[task_ids[1]]["claims"][0]["claim_id"]
    alpha_evidence_id = bound_matrices[task_ids[0]]["evidence"][0]["evidence_id"]
    beta_evidence_id = bound_matrices[task_ids[1]]["evidence"][0]["evidence_id"]
    assert alpha_claim_id != beta_claim_id
    assert alpha_evidence_id != beta_evidence_id
    assert bound_matrices[task_ids[0]]["claims"][0]["statement"] == _payload()["claims"][0]["statement"]
    assert bound_matrices[task_ids[0]]["claims"][0]["evidence_ids"] == [alpha_evidence_id]
    assert bound_matrices[task_ids[0]]["evidence"][0]["claim_id"] == alpha_claim_id
    assert bound_matrices[task_ids[0]]["cells"][0]["evidence_ids"] == [alpha_evidence_id]

    replayed_output, replayed, error, diagnostic = _separate_synthesis_matrix(
        _synthesis_envelope_with_matrix(_payload()),
        _context(),
        research_task_id=task_ids[0],
        plan_version=1,
    )
    assert error is None
    assert diagnostic is None
    assert replayed == bound_matrices[task_ids[0]]
    EvidenceMatrixService(store).build_matrix(
        task_ids[0], "owner", plan_version=1,
        dimensions=replayed["dimensions"], claims=replayed["claims"],
        evidence=replayed["evidence"], cells=replayed["cells"],
    )
    assert EvidenceMatrixService(store).read_matrix(task_ids[0], "owner", plan_version=1)["claims"][0]["claim_id"] == alpha_claim_id
    assert EvidenceMatrixService(store).read_matrix(task_ids[1], "owner", plan_version=1)["claims"][0]["claim_id"] == beta_claim_id


def test_unknown_model_evidence_reference_is_rejected_before_namespacing() -> None:
    payload = _payload()
    payload["claims"][0]["evidence_ids"] = ["evidence-does-not-exist"]
    envelope = _synthesis_envelope_with_matrix(payload)

    artifact, matrix, error, diagnostic = _separate_synthesis_matrix(
        envelope,
        _context(),
        research_task_id="task-unknown-reference",
        plan_version=1,
    )

    assert error == "REPORT_SCHEMA_INVALID"
    assert matrix is None
    assert diagnostic == {
        "matrix_error_code": "REPORT_SCHEMA_INVALID",
        "rule_id": "matrix.claim.evidence_ownership",
        "field_paths": ["evidence_matrix.claims[].evidence_ids"],
    }
    assert artifact["output_hash"] == report_output_hash(artifact)


def test_matrix_persistence_conflict_has_bounded_claim_id_diagnostic() -> None:
    diagnostic = _matrix_persistence_diagnostic(
        ValueError("claim_id already exists with different content"),
    )

    assert diagnostic == {
        "matrix_error_code": "MATRIX_ID_CONFLICT",
        "rule_id": "matrix.persistence.claim_id_conflict",
        "field_paths": ["claims[].claim_id"],
    }
    assert "already exists" not in json.dumps(diagnostic)


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
    run_trace: list | None = None,
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
        current_plan_version=1,
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
            if run_trace is not None:
                run_trace.append(run_input)
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
            elif run_input.role == "synthesizer" and isinstance(
                run_input.work_item_input.get("report_quality_context"), dict
            ):
                marker = run_input.work_item_input["report_quality_context"]
                evidence_id_by_paper = {
                    item["paper_id"]: item["evidence_id"]
                    for item in marker["evidence"]
                }
                output = {
                    "schema_version": "runtime-v1", "safe_summary": {}, "source_refs": [],
                    "work_item_id": run_input.work_item_id,
                    "report_version": marker["report_version"],
                    "sections": [], "citation_manifest": [], "artifact_ids": [],
                    "report_content": _quality_report_content(
                        paper_ids,
                        evidence_ids=[evidence_id_by_paper[paper_id] for paper_id in paper_ids],
                    ),
                }
            else:
                output = synthesis
            checkpoint_ref = None
            checkpoint_hash = None
            checkpoint_content = None
            run_started_at = (
                datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
                if run_input.role == "synthesizer" else "2026-10-29T00:00:00Z"
            )
            if run_input.role == "synthesizer":
                checkpoint_content = json.dumps(
                    {"schema_version": output.get("schema_version", "runtime-v1"),
                     "output": output, "tool_results": []},
                    ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                )
                checkpoint_hash = hashlib.sha256(checkpoint_content.encode("utf-8")).hexdigest()
                checkpoint_ref = f"checkpoint:{run_input.agent_run_id}:{checkpoint_hash[:16]}"
            store.create_agent_run(AgentRun(
                agent_run_id=run_input.agent_run_id,
                research_session_id=session.research_session_id,
                attempt=run_input.attempt,
                role=run_input.role,
                skill_name="test",
                skill_schema_version="1",
                skill_content_hash="test",
                resolved_model="test",
                reasoning_effort="off",
                allowed_tools_json="[]",
                provider="test",
                status="running" if run_input.role == "synthesizer" else "completed",
                output_hash=hashlib.sha256(
                    json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
                ).hexdigest(),
                checkpoint_ref=checkpoint_ref,
                checkpoint_hash=checkpoint_hash,
                model_loop_count=(
                    40 if run_input.role == "synthesizer" and
                    "report_quality_context" not in run_input.work_item_input else 0
                ),
                tool_call_count=(
                    160 if run_input.role == "synthesizer" and
                    "report_quality_context" not in run_input.work_item_input else 0
                ),
                research_task_id=task.research_task_id,
                work_item_id=run_input.work_item_id,
                started_at=run_started_at,
                ended_at=None if run_input.role == "synthesizer" else "2026-10-29T00:00:01Z",
                owner_id="owner",
            ), owner_id="owner")
            if run_input.role == "synthesizer":
                store.create_agent_checkpoint(AgentCheckpoint(
                    checkpoint_ref=checkpoint_ref,
                    owner_id="owner",
                    research_session_id=session.research_session_id,
                    research_task_id=task.research_task_id,
                    work_item_id=run_input.work_item_id,
                    agent_run_id=run_input.agent_run_id,
                    schema_version=output.get("schema_version", "runtime-v1"),
                    content=checkpoint_content,
                    content_hash=checkpoint_hash,
                ), expected_generation=0)
                store.update_agent_run_status(
                    run_input.agent_run_id, "owner", "completed",
                )
            return AgentRunOutput(
                "completed", output_json=output, output_hash="hash", agent_run_id=run_input.agent_run_id,
            )

    planner = SimpleNamespace(build_plan=lambda **_: SimpleNamespace(
        facets=("隐私",), planner_model="test", rationale_summary="test",
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


def test_natural_language_synthesis_runs_quality_body_before_single_work_item_terminal(
    tmp_path, monkeypatch,
) -> None:
    run_trace = []
    result, store, task, _memory = _run_matrix_agent_scenario(
        tmp_path,
        monkeypatch,
        target_paper_count=5,
        candidate_count=5,
        run_trace=run_trace,
    )

    synthesizer_runs = [item for item in run_trace if item.role == "synthesizer"]
    assert len(synthesizer_runs) == 3
    assert "report_quality_context" not in synthesizer_runs[0].work_item_input
    comparison_marker = synthesizer_runs[1].work_item_input["report_quality_context"]
    marker = synthesizer_runs[2].work_item_input["report_quality_context"]
    assert comparison_marker["schema_version"] == "report-quality-v1"
    assert comparison_marker["stage"] == "comparison"
    assert comparison_marker["report_version"] == synthesizer_runs[1].work_item_input["report_version"]
    assert marker["stage"] == "drafting"
    assert marker["report_version"] == synthesizer_runs[2].work_item_input["report_version"]
    assert {item["evidence_level"] for item in marker["evidence"]} == {"abstract"}
    assert len({item["paper_id"] for item in marker["evidence"]}) == 5

    synthesis_item = next(
        item for item in store.list_work_items(task.research_task_id, plan_version=1)
        if item.role == "synthesizer"
    )
    assert synthesis_item.status == "completed"
    assert synthesis_item.attempt == 1
    report = store.get_research_report(task.research_task_id, "owner", report_version=1)
    assert report is not None
    assert report.status == "completed"
    canonical = json.loads(report.report_json)
    assert canonical["generation"]["published"] is True
    persisted_agent_run_ids = canonical["generation"]["agent_run_ids"]
    assert {item.agent_run_id for item in synthesizer_runs[1:]} <= set(persisted_agent_run_ids)
    assert all(
        store.get_agent_run(item.agent_run_id, "owner").status == "completed"
        for item in synthesizer_runs
    )
    for item in synthesizer_runs[1:]:
        persisted_run = store.get_agent_run(item.agent_run_id, "owner")
        checkpoint = store.get_agent_checkpoint(persisted_run.checkpoint_ref, "owner")
        assert checkpoint is not None
        checkpoint_payload = json.loads(checkpoint.content)
        paper_order = sorted({entry["paper_id"] for entry in marker["evidence"]})
        evidence_id_by_paper = {
            entry["paper_id"]: entry["evidence_id"] for entry in marker["evidence"]
        }
        assert checkpoint_payload["output"]["report_content"] == _quality_report_content(
            paper_order[:5],
            evidence_ids=[evidence_id_by_paper[paper_id] for paper_id in paper_order[:5]],
        )
    assert canonical["quality_validation"]["status"] == "pass"
    assert canonical["report_content"]["schema_version"] == "research-report-content-v1"
    assert all(claim["settled"] for claim in canonical["generation"]["store_state"]["claims"])
    assert len(canonical["generation"]["store_state"]["claims"]) == 3
    assert synthesizer_runs[1].budget_snapshot["model_loops"] == 0
    assert synthesizer_runs[1].budget_snapshot["tool_calls"] == 0
    assert synthesizer_runs[1].budget_snapshot["task_model_loops"] == 40
    assert synthesizer_runs[1].budget_snapshot["task_tool_calls"] == 160
    assert synthesizer_runs[2].budget_snapshot["model_loops"] == 0
    assert synthesizer_runs[2].budget_snapshot["tool_calls"] == 0
    assert synthesizer_runs[2].budget_snapshot["task_model_loops"] == 40
    assert synthesizer_runs[2].budget_snapshot["task_tool_calls"] == 160
    artifacts = store.list_artifacts_for_task(task.research_task_id, "owner", report_version=1)
    assert {item.artifact_type for item in artifacts} == {
        "markdown", "html", "citation_manifest",
    }
    session = store.get_session("session-matrix-terminal", "owner")
    final_message = _memory.get_activity_message(
        session.conversation_id, "owner", "research-report:task-matrix-terminal:1",
    )
    assert final_message is not None
    assert final_message.status == "completed"
    assert session.final_message_id == final_message.message_id
    notifications = store.list_notifications("owner")
    assert len(notifications) == 1
    assert notifications[0].research_task_id == task.research_task_id
    assert notifications[0].subject_version == 1
    assert result.status == "completed"
    assert result.error_code is None


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

    if expected_status == "running":
        report = store.get_research_report(task.research_task_id, "owner", report_version=1)
        assert report is not None and report.status == "generating"
        assert store.list_artifacts_for_task(task.research_task_id, "owner") == []
        assert not [event for event in store.list_events(task.research_task_id)
                    if event.event_type == "terminal"]
        return

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
