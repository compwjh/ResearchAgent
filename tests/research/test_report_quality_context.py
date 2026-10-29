"""Server-owned report-quality runtime context assembly contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest

from backend.app.memory.repository import MemoryRepository
from backend.app.paper_discovery.domain.paper_discovery import CatalogPaper, SearchJob, SearchResult, SearchSession
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.research.application.agent_runtime import (
    AgentRunInput,
    AgentRuntimeError,
    FakeModel,
    ResearchAgentRunner,
    RoleCapabilityRegistry,
)
from backend.app.research.application.evidence_matrix import EvidenceMatrixService
from backend.app.research.application.orchestrator import Orchestrator, ReportQualityContextUnavailable
from backend.app.research.application.report_synthesis import ReportDeliveryService
from backend.app.research.application.research_service import ResearchService
from backend.app.research.domain.models import (
    AgentRun,
    EvidenceUpgrade,
    ResearchPaperSelection,
    ResearchPlan,
    ResearchSession,
    ResearchTask,
    ResearchWorkItem,
)
from backend.app.research.infrastructure.research_store import ResearchStore


def _seed_report_context(
    tmp_path, *, persist_matrix: bool = True, add_fulltext: bool = False,
    fulltext_summary: str | None = None, trusted_paper_count: int = 5,
    approved_facets: list[str] | None = None, research_question: str | None = None,
    abstract_template: str | None = None,
):
    store = ResearchStore(tmp_path / "research.sqlite3")
    catalog_store = PaperDiscoveryStore(database_path=tmp_path / "paper-search.sqlite3")
    task = ResearchTask(
        "task-report-context", "owner", "conversation",
        research_question or "分析五篇论文的方法与局限",
        "zh", "balanced", False, 5, 300, "running", 1, "", "",
    )
    approved_facets = approved_facets or ["研究方法"]
    store.create_task(task)
    store.create_plan(ResearchPlan(
        task.research_task_id, 1, "approved task plan", json.dumps(approved_facets),
        "active", "2026-10-29T00:00:00Z", "test",
    ))
    paper_ids = [f"paper-{index}" for index in range(1, 6)]
    search_id = "search-report-context"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    created_at = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    expires_at = (now + timedelta(days=7)).isoformat(timespec="seconds").replace("+00:00", "Z")
    catalog_store.save_search(SearchSession(search_id, task.goal, expires_at, created_at), [])
    catalog_store.create_search_job(SearchJob(
        search_id=search_id,
        query=task.goal,
        conference_ids=["usenix-security"],
        years=[2024],
        status="completed",
        graph_version="catalog-search-v1",
        total_results=len(paper_ids),
        created_at=created_at,
        completed_at=created_at,
        expires_at=expires_at,
        updated_at=created_at,
    ))
    store.replace_selections(task.research_task_id, [
        ResearchPaperSelection(task.research_task_id, paper_id, 1.0, "[]", "abstract", "", search_id)
        for paper_id in paper_ids
    ])
    candidates = []
    evidence = []
    evidence_ids = []
    for index, paper_id in enumerate(paper_ids, start=1):
        abstract = (
            abstract_template.format(index=index)
            if abstract_template is not None
            else f"Frozen abstract {index}: evidence-bound text."
        )
        digest = hashlib.sha256(abstract.encode("utf-8")).hexdigest()
        candidates.append({
            "paper_id": paper_id,
            "catalog_snapshot_id": search_id,
            "title": f"Paper {index}",
            "abstract": abstract,
            "abstract_digest": digest,
            "abstract_ref": f"catalog:{paper_id}",
        })
        catalog_store.upsert_catalog_paper(CatalogPaper(
            catalog_paper_id=paper_id,
            conference_id="usenix-security",
            year=2024,
            title=f"Paper {index}",
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
            rank=index,
            snapshot={
                "candidate_id": paper_id,
                "catalog_paper_id": paper_id,
                "search_id": search_id,
                "title": f"Paper {index}",
                "abstract": abstract,
            },
            created_at=created_at,
        ))
        if index <= trusted_paper_count:
            evidence_id = f"evidence-{index}"
            evidence_ids.append(evidence_id)
            evidence.append({
                "evidence_id": evidence_id,
                "claim_id": "claim-method",
                "paper_id": paper_id,
                "evidence_level": "abstract",
                "stance": "supports",
                "status": "available",
                "quote_digest": digest,
                "locator": {
                    "catalog_snapshot_id": search_id,
                    "abstract_ref": f"catalog:{paper_id}",
                    "abstract_digest": digest,
                },
            })

    if add_fulltext:
        store.save_evidence_upgrade(EvidenceUpgrade(
            claim_id="claim-method", task_id=task.research_task_id,
            from_level="abstract", to_level="fulltext", chunk_ids=["chunk-1"],
            status="upgraded", document_id="document-1", page=1, page_end=1,
            source_sha256="a" * 64, manifest_generation="generation-1",
            manifest_fingerprint="b" * 64, chunker="v1",
        ))
        evidence.append({
            "evidence_id": "evidence-fulltext",
            "claim_id": "claim-method",
            "paper_id": paper_ids[0],
            "evidence_level": "fulltext",
            "stance": "supports",
            "status": "available",
            "quote_digest": "c" * 64,
            "locator": {
                "document_id": "document-1", "chunk_ids": ["chunk-1"],
                "page": 1, "page_end": 1, "source_sha256": "a" * 64,
                "manifest_generation": "generation-1",
                "manifest_fingerprint": "b" * 64, "chunker": "v1",
                "excerpt": "Authorization: secret=must-not-leak",
            },
        })
        evidence_ids.append("evidence-fulltext")

    if persist_matrix:
        EvidenceMatrixService(store).build_matrix(
            task.research_task_id,
            "owner",
            plan_version=1,
            dimensions=[{
                "dimension_id": f"facet-{index}", "label": facet,
                "definition": f"已批准研究范围维度：{facet}", "display_order": index - 1,
            } for index, facet in enumerate(approved_facets, start=1)],
            claims=[{
                "claim_id": "claim-method", "topic": "研究方法",
                "statement": "当前摘要对研究方法提供了受限描述。",
                "confidence": "medium", "status": "supported",
                "evidence_ids": evidence_ids,
            }],
            evidence=evidence,
            cells=[{
                "claim_id": "claim-method", "paper_id": paper_ids[0],
                "dimension_id": "facet-1", "relation": "supports",
                "summary": fulltext_summary,
                "evidence_ids": ["evidence-fulltext"],
            }] if add_fulltext and fulltext_summary else None,
        )

    work_item = ResearchWorkItem(
        "work-report-context", task.research_task_id, 1,
        "synthesize_preliminary_report", "synthesizer", "[]",
        json.dumps({"report_version": 7}), "running", 1, "", "",
    )
    return store, catalog_store, task, work_item, candidates


def _orchestrator_with_frozen_candidates(store, catalog_store):
    return Orchestrator(
        store=store,
        search_adapter=SimpleNamespace(_store=catalog_store),
        probe=object(),
    )


def test_report_quality_context_uses_persisted_evidence_ids_and_verified_abstracts(tmp_path):
    store, catalog_store, task, work_item, candidates = _seed_report_context(tmp_path)
    orchestrator = _orchestrator_with_frozen_candidates(store, catalog_store)

    context = orchestrator._build_report_quality_context(
        task=task, owner_id="owner", work_item=work_item,
        selected_candidates=[{
            "candidate_id": item["paper_id"],
            "evidence_refs": [f"catalog:{item['paper_id']}"],
            "title": item["title"],
            "abstract": item["abstract"],
            "verified": True,
        } for item in candidates],
        stage="evidence_review", revision_count=0,
    )

    assert context["schema_version"] == "report-quality-v1"
    assert context["stage"] == "evidence_review"
    assert context["revision_count"] == 0
    assert context["plan_version"] == 1
    assert context["report_version"] == 7
    assert context["research_question"] == task.goal
    assert context["selected_paper_ids"] == [item["paper_id"] for item in candidates]
    assert context["dimensions"] == [{
        "dimension_id": "facet-1", "label": "研究方法",
        "definition": "已批准研究范围维度：研究方法",
    }]
    assert [item["evidence_id"] for item in context["evidence"]] == [
        f"evidence-{index}" for index in range(1, 6)
    ]
    assert all(item["evidence_level"] == "abstract" for item in context["evidence"])
    assert context["evidence"][0]["excerpt"] == candidates[0]["abstract"]
    assert all(set(item) == {"evidence_id", "paper_id", "evidence_level", "excerpt"} for item in context["evidence"])
    assert "locator" not in json.dumps(context)


def test_report_quality_context_omits_fulltext_when_only_verified_locator_exists(tmp_path):
    store, catalog_store, task, work_item, candidates = _seed_report_context(tmp_path, add_fulltext=True)
    orchestrator = _orchestrator_with_frozen_candidates(store, catalog_store)

    context = orchestrator._build_report_quality_context(
        task=task, owner_id="owner", work_item=work_item,
        selected_candidates=[{
            "candidate_id": item["paper_id"],
            "evidence_refs": [f"catalog:{item['paper_id']}"],
            "title": item["title"],
            "abstract": item["abstract"],
            "verified": True,
        } for item in candidates],
        stage="drafting", revision_count=0,
    )

    assert all(item["evidence_level"] != "fulltext" for item in context["evidence"])
    assert "must-not-leak" not in json.dumps(context)


def test_report_quality_context_includes_fulltext_only_from_verified_task_bound_cell(tmp_path):
    store, catalog_store, task, work_item, candidates = _seed_report_context(
        tmp_path, add_fulltext=True, fulltext_summary="Verified fulltext matrix summary.",
    )
    orchestrator = _orchestrator_with_frozen_candidates(store, catalog_store)

    context = orchestrator._build_report_quality_context(
        task=task, owner_id="owner", work_item=work_item,
        selected_candidates=[{
            "candidate_id": item["paper_id"],
            "evidence_refs": [f"catalog:{item['paper_id']}"],
            "title": item["title"],
            "abstract": item["abstract"],
            "verified": True,
        } for item in candidates],
        stage="comparison", revision_count=0,
    )

    fulltext = [item for item in context["evidence"] if item["evidence_level"] == "fulltext"]
    assert fulltext == [{
        "evidence_id": "evidence-fulltext", "paper_id": "paper-1",
        "evidence_level": "fulltext", "excerpt": "Verified fulltext matrix summary.",
    }]
    assert "must-not-leak" not in json.dumps(context)


def test_report_quality_context_does_not_upgrade_evidence_without_fulltext_upgrade_level(tmp_path):
    store, catalog_store, task, work_item, candidates = _seed_report_context(
        tmp_path, add_fulltext=True, fulltext_summary="Matrix summary must stay abstract-only.",
    )
    store.save_evidence_upgrade(EvidenceUpgrade(
        claim_id="claim-method", task_id=task.research_task_id,
        from_level="abstract", to_level="abstract", chunk_ids=["chunk-1"],
        status="upgraded", document_id="document-1", page=1, page_end=1,
        source_sha256="a" * 64, manifest_generation="generation-1",
        manifest_fingerprint="b" * 64, chunker="v1",
    ))
    orchestrator = _orchestrator_with_frozen_candidates(store, catalog_store)

    context = orchestrator._build_report_quality_context(
        task=task, owner_id="owner", work_item=work_item,
        selected_candidates=[{
            "candidate_id": item["paper_id"],
            "evidence_refs": [f"catalog:{item['paper_id']}"],
            "title": item["title"],
            "abstract": item["abstract"],
            "verified": True,
        } for item in candidates],
        stage="comparison", revision_count=0,
    )

    assert all(item["evidence_level"] != "fulltext" for item in context["evidence"])
    assert "Matrix summary must stay abstract-only." not in json.dumps(context)


def test_report_quality_context_names_persistent_matrix_dependency_when_absent(tmp_path):
    store, catalog_store, task, work_item, candidates = _seed_report_context(tmp_path, persist_matrix=False)
    orchestrator = _orchestrator_with_frozen_candidates(store, catalog_store)

    with pytest.raises(ReportQualityContextUnavailable) as error:
        orchestrator._build_report_quality_context(
            task=task, owner_id="owner", work_item=work_item,
            selected_candidates=[{
                "candidate_id": item["paper_id"],
                "evidence_refs": [f"catalog:{item['paper_id']}"],
                "title": item["title"],
                "abstract": item["abstract"],
                "verified": True,
            } for item in candidates],
            stage="evidence_review", revision_count=0,
        )

    assert error.value.code == "REPORT_QUALITY_CONTEXT_UNAVAILABLE"
    assert error.value.dependency == "persisted_current_plan_claim_evidence_matrix"


def test_report_quality_context_rejects_candidate_set_outside_durable_selection(tmp_path):
    store, catalog_store, task, work_item, candidates = _seed_report_context(tmp_path)
    orchestrator = _orchestrator_with_frozen_candidates(store, catalog_store)
    selected = [{
        "candidate_id": item["paper_id"],
        "evidence_refs": [f"catalog:{item['paper_id']}"],
        "title": item["title"],
        "abstract": item["abstract"],
        "verified": True,
    } for item in candidates]
    selected[-1]["candidate_id"] = "paper-outside-selection"

    with pytest.raises(ReportQualityContextUnavailable) as error:
        orchestrator._build_report_quality_context(
            task=task, owner_id="owner", work_item=work_item,
            selected_candidates=selected,
            stage="evidence_review", revision_count=0,
        )

    assert error.value.dependency == "frozen_selected_candidate_snapshot"


def _selected_candidates(candidates):
    return [{
        "candidate_id": item["paper_id"],
        "evidence_refs": [f"catalog:{item['paper_id']}"],
        "title": item["title"],
        "abstract": item["abstract"],
        "verified": True,
    } for item in candidates]


def test_report_quality_context_allows_password_and_token_security_topics(tmp_path):
    store, catalog_store, task, work_item, candidates = _seed_report_context(
        tmp_path,
        approved_facets=["password authentication and token-based login"],
        research_question="比较 password authentication 与 token-based login",
        abstract_template=(
            "Frozen abstract {index}: password authentication and token-based login evidence."
        ),
    )
    orchestrator = _orchestrator_with_frozen_candidates(store, catalog_store)

    context = orchestrator._build_report_quality_context(
        task=task,
        owner_id="owner",
        work_item=work_item,
        selected_candidates=_selected_candidates(candidates),
        stage="evidence_review",
        revision_count=0,
    )

    assert context["dimensions"][0]["label"] == "password authentication and token-based login"
    assert context["research_question"] == "比较 password authentication 与 token-based login"
    assert len(context["evidence"]) == 5
    assert all("password authentication" in item["excerpt"] for item in context["evidence"])


@pytest.mark.parametrize(
    "credential_text",
    [
        "password=hunter2",
        '"api_key":"sk-proj-abcdefghijklmnop"',
    ],
)
def test_report_quality_context_rejects_credential_assignments_in_approved_dimensions(
    tmp_path, credential_text,
):
    store, catalog_store, task, work_item, candidates = _seed_report_context(
        tmp_path, approved_facets=[credential_text],
    )
    orchestrator = _orchestrator_with_frozen_candidates(store, catalog_store)

    with pytest.raises(ReportQualityContextUnavailable) as error:
        orchestrator._build_report_quality_context(
            task=task,
            owner_id="owner",
            work_item=work_item,
            selected_candidates=_selected_candidates(candidates),
            stage="evidence_review",
            revision_count=0,
        )

    assert error.value.dependency == "approved_plan_comparison_dimensions"
    assert credential_text not in str(error.value)


@pytest.mark.parametrize(
    "secret_material",
    [
        "password=hunter2",
        "Bearer eyJabcdefghijk.abcdefghijklmnop.abcdefghijk",
        "sk-proj-abcdefghijklmnop",
    ],
)
def test_report_quality_context_excludes_verified_abstracts_with_secret_material(
    tmp_path, secret_material,
):
    store, catalog_store, task, work_item, candidates = _seed_report_context(
        tmp_path,
        abstract_template=f"Frozen abstract {{index}} includes {secret_material}.",
    )
    orchestrator = _orchestrator_with_frozen_candidates(store, catalog_store)

    with pytest.raises(ReportQualityContextUnavailable) as error:
        orchestrator._build_report_quality_context(
            task=task,
            owner_id="owner",
            work_item=work_item,
            selected_candidates=_selected_candidates(candidates),
            stage="evidence_review",
            revision_count=0,
        )

    assert error.value.dependency == "verified_current_plan_evidence_excerpt_projection"
    assert secret_material not in str(error.value)


def _reserve_running_report(store, task, *, request_key, request_payload):
    reservation = store.reserve_report_generation(
        task.research_task_id,
        "owner",
        plan_version=1,
        request_key=request_key,
        request_payload=request_payload,
    )
    running = store.update_work_item_status(
        reservation.work_item.work_item_id, "running", attempt=1,
    )
    return reservation, running


def _quality_report_content(paper_ids, *, cjk_repetitions=320):
    evidence_ids = [f"evidence-{index}" for index in range(1, 6)]
    analyses = []
    for index, paper_id in enumerate(paper_ids):
        evidence_id = evidence_ids[index]
        analyses.append({
            "paper_id": paper_id,
            "method": {
                "status": "supported", "text": "研究" * cjk_repetitions,
                "evidence_ids": [evidence_id],
            },
            "findings": {"status": "unavailable", "text": "", "evidence_ids": []},
            "limitations": {"status": "not_stated", "text": "", "evidence_ids": []},
        })
    shared_refs = [evidence_ids[0], evidence_ids[1]]
    return {
        "schema_version": "research-report-content-v1",
        "research_question": {"text": "分析五篇论文的方法与局限"},
        "evidence_scope": {"text": "仅根据已核验摘要比较", "paper_ids": list(paper_ids)},
        "paper_analyses": analyses,
        "cross_paper_comparisons": [{
            "dimension_id": "facet-1", "paper_ids": list(paper_ids[:2]),
            "statement": "两篇摘要都描述了研究方法。", "evidence_ids": shared_refs,
        }],
        "synthesis_findings": [{
            "finding_id": f"finding-{index}", "statement": f"跨论文发现{index}。",
            "paper_ids": list(paper_ids[:2]), "evidence_ids": shared_refs,
        } for index in range(1, 4)],
        "research_gaps": [],
    }


def _checkpoint_quality_run(
    *, store, catalog_store, task, work_item, session_id, reservation, candidates, model, stage,
    revision_count=0, prior_report_content=None, failure_codes=(), runtime=None,
):
    """Persist a real Runtime output/checkpoint for report restart coverage."""
    orchestrator = _orchestrator_with_frozen_candidates(store, catalog_store)
    marker = orchestrator._build_report_quality_context(
        task=task,
        owner_id="owner",
        work_item=work_item,
        selected_candidates=_selected_candidates(candidates),
        stage=stage,
        revision_count=revision_count,
        prior_report_content=prior_report_content,
        failure_codes=failure_codes,
    )
    stage_name = f"revision-{revision_count}" if stage == "targeted_revision" else stage
    run_id = f"{work_item.work_item_id}:report-{reservation.report.report_version}:{stage_name}-recovery"
    claim_id = str(uuid4())
    claim = store.claim_report_generation_budget(
        task.research_task_id, "owner", reservation.report.report_version,
        claim_id=claim_id, agent_run_id=run_id,
        requested_model_loops=40, requested_tool_calls=160, requested_seconds=120,
    )
    assert claim["allowed"] is True
    skill = {
        "name": "research-report-synthesis", "schema_version": "1",
        "content_hash": "skill-hash", "source_ref": "skill:research-report-synthesis",
        "enabled": True, "tools": [],
    }
    runtime = runtime or ResearchAgentRunner(
        store=store, model=model, capability_registry=RoleCapabilityRegistry(skills=[skill]),
    )
    run_input = AgentRunInput(
        agent_run_id=run_id,
        research_session_id=session_id,
        research_task_id=task.research_task_id,
        work_item_id=work_item.work_item_id,
        owner_id="owner",
        role="synthesizer",
        work_item_input={
            "report_version": reservation.report.report_version,
            "report_quality_context": marker,
        },
        budget_snapshot={
            "model_loops": 0, "tool_calls": 0,
            "task_model_loops": 0, "task_tool_calls": 0,
            "elapsed_seconds": 0,
            "max_model_loops": claim["grant"]["model_loops"],
            "max_tool_calls": claim["grant"]["tool_calls"],
            "task_max_model_loops": 160, "task_max_tool_calls": 640,
            "max_seconds": claim["grant"]["seconds"],
        },
        attempt=1,
    )
    result = runtime.run(run_input)
    assert result.status == "completed", result.error_code
    settled = store.settle_report_generation_budget(
        task.research_task_id, "owner", reservation.report.report_version,
        claim_id=claim_id,
    )
    assert settled["settled"] is True
    return result, run_input, runtime


def _report_runtime_output(report_version, work_item_id, content):
    return {"output_json": {
        "schema_version": "report-synthesis-v1",
        "report_version": report_version,
        "work_item_id": work_item_id,
        "sections": [], "citation_manifest": [], "artifact_ids": [],
        "safe_summary": {}, "source_refs": [], "report_content": content,
    }}


def _create_runtime_session(store, task, session_id):
    class _MemoryReferences:
        @staticmethod
        def get_conversation(_conversation_id, _owner_id):
            return SimpleNamespace(owner_id="owner")

        @staticmethod
        def get_message(_message_id, _owner_id):
            return SimpleNamespace(conversation_id="conversation")

    store.create_session(ResearchSession(
        session_id, "owner", "conversation", "trigger-message",
        f"intake-{session_id}", "running", current_plan_version=1,
        research_task_id=task.research_task_id,
    ), memory_repository=_MemoryReferences())


def test_report_quality_body_fails_when_fewer_than_five_papers_have_trusted_evidence(tmp_path):
    store, catalog_store, task, _work_item, candidates = _seed_report_context(
        tmp_path, trusted_paper_count=4,
    )
    reservation, running = _reserve_running_report(
        store, task, request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6bd77",
        request_payload={"plan_version": 1, "purpose": "trusted-evidence-gate"},
    )
    orchestrator = _orchestrator_with_frozen_candidates(store, catalog_store)

    result = orchestrator._generate_report_quality_body(
        task=task, owner_id="owner", work_item=running,
        selected_candidates=_selected_candidates(candidates),
        reservation=reservation, session_id="unused-with-insufficient-evidence",
    )

    assert result["status"] == "failed"
    assert result["diagnostic"] == {
        "code": "INSUFFICIENT_TRUSTED_EVIDENCE",
        "required_papers": 5,
        "available_papers": 4,
    }
    budget = store.get_report_generation_budget(
        task.research_task_id, "owner", reservation.report.report_version,
    )
    assert budget["report"].status == "failed"
    assert budget["stage"] == "failed"
    persisted = store.get_research_report(
        task.research_task_id, "owner", report_version=reservation.report.report_version,
    )
    assert json.loads(persisted.report_json)["reason_codes"] == ["INSUFFICIENT_TRUSTED_EVIDENCE"]
    assert store.get_work_item(running.work_item_id).status == "running"


def test_report_quality_body_reports_recoverable_state_when_progress_cannot_be_read(tmp_path):
    store, catalog_store, task, _work_item, candidates = _seed_report_context(tmp_path)
    reservation, running = _reserve_running_report(
        store, task, request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6bd7a",
        request_payload={"plan_version": 1, "purpose": "state-read-failure"},
    )
    orchestrator = _orchestrator_with_frozen_candidates(store, catalog_store)

    def fail_read(*_args, **_kwargs):
        raise RuntimeError("temporary report-state read failure")

    store.get_report_generation_budget = fail_read
    result = orchestrator._generate_report_quality_body(
        task=task, owner_id="owner", work_item=running,
        selected_candidates=_selected_candidates(candidates),
        reservation=reservation, session_id="unused-state-read-failure",
    )

    assert result["status"] == "generating"
    assert result["diagnostic"] == {"code": "REPORT_STATE_READ_FAILED", "state": "unknown"}
    report = store.get_research_report(task.research_task_id, "owner", report_version=1)
    assert report.status == "generating"


def test_report_quality_body_does_not_claim_failed_when_failure_state_write_fails(tmp_path):
    store, catalog_store, task, _work_item, candidates = _seed_report_context(
        tmp_path, trusted_paper_count=4,
    )
    reservation, running = _reserve_running_report(
        store, task, request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6bd7b",
        request_payload={"plan_version": 1, "purpose": "state-write-failure"},
    )
    orchestrator = _orchestrator_with_frozen_candidates(store, catalog_store)

    def fail_write(*_args, **_kwargs):
        raise RuntimeError("temporary report-state write failure")

    store.update_report_generation_state = fail_write
    result = orchestrator._generate_report_quality_body(
        task=task, owner_id="owner", work_item=running,
        selected_candidates=_selected_candidates(candidates),
        reservation=reservation, session_id="unused-state-write-failure",
    )

    assert result["status"] == "generating"
    assert result["diagnostic"] == {
        "code": "REPORT_FAILURE_STATE_NOT_PERSISTED",
        "failure_code": "INSUFFICIENT_TRUSTED_EVIDENCE",
        "state": "generating",
    }
    report = store.get_research_report(task.research_task_id, "owner", report_version=1)
    assert report.status == "generating"


def test_runtime_attempt_limit_is_compatible_with_two_report_revisions(tmp_path):
    store, catalog_store, task, _work_item, _candidates = _seed_report_context(tmp_path)
    reservation, running = _reserve_running_report(
        store, task, request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6bd7c",
        request_payload={"plan_version": 1, "purpose": "runtime-attempt-contract"},
    )

    class _MemoryReferences:
        @staticmethod
        def get_conversation(_conversation_id, _owner_id):
            return SimpleNamespace(owner_id="owner")

        @staticmethod
        def get_message(_message_id, _owner_id):
            return SimpleNamespace(conversation_id="conversation")

    store.create_session(ResearchSession(
        "session-report-runtime-attempt", "owner", "conversation", "trigger-message",
        "intake-report-runtime-attempt", "running", current_plan_version=1,
        research_task_id=task.research_task_id,
    ), memory_repository=_MemoryReferences())
    runner = ResearchAgentRunner(store=store)

    with pytest.raises(AgentRuntimeError, match="attempt must be between 1 and 4"):
        runner.run(AgentRunInput(
            agent_run_id="report-runtime-attempt-out-of-range",
            research_session_id="session-report-runtime-attempt",
            research_task_id=task.research_task_id,
            work_item_id=running.work_item_id,
            owner_id="owner",
            role="synthesizer",
            work_item_input={"report_version": reservation.report.report_version},
            attempt=5,
        ))

    assert store.get_agent_run("report-runtime-attempt-out-of-range", "owner") is None


def test_report_quality_body_recovers_quality_check_from_completed_runtime_checkpoint(tmp_path):
    store, catalog_store, task, _work_item, candidates = _seed_report_context(tmp_path)
    reservation, running = _reserve_running_report(
        store, task, request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6bd80",
        request_payload={"plan_version": 1, "purpose": "quality-check-recovery"},
    )
    session_id = "session-report-quality-check-recovery"
    _create_runtime_session(store, task, session_id)
    progress = store.get_report_generation_budget(
        task.research_task_id, "owner", reservation.report.report_version,
    )
    progress = store.update_report_generation_state(
        task.research_task_id, "owner", reservation.report.report_version,
        expected_revision=0, stage="drafting", rewrite_count=0,
    )
    content = _quality_report_content([item["paper_id"] for item in candidates])
    model = FakeModel([_report_runtime_output(reservation.report.report_version, running.work_item_id, content)])
    checkpoint, _run_input, runtime = _checkpoint_quality_run(
        store=store, catalog_store=catalog_store, task=task, work_item=running,
        session_id=session_id, reservation=reservation, candidates=candidates,
        model=model, stage="drafting",
    )
    progress = store.get_report_generation_budget(
        task.research_task_id, "owner", reservation.report.report_version,
    )
    progress = store.update_report_generation_state(
        task.research_task_id, "owner", reservation.report.report_version,
        expected_revision=progress["revision"], stage="quality_check", rewrite_count=0,
    )
    captured = []

    class _RuntimeProbe:
        def run(self, run_input):
            captured.append(run_input)
            return runtime.run(run_input)

    orchestrator = Orchestrator(
        store=store, search_adapter=SimpleNamespace(_store=catalog_store),
        probe=object(), agent_runner=_RuntimeProbe(),
    )
    args = {
        "task": task, "owner_id": "owner", "work_item": running,
        "selected_candidates": _selected_candidates(candidates),
        "reservation": reservation, "session_id": session_id,
    }

    result = orchestrator._generate_report_quality_body(**args)

    assert result["status"] == "generating"
    assert result["diagnostic"]["code"] == "REPORT_DELIVERY_PENDING"
    assert checkpoint.agent_run_id == _run_input.agent_run_id
    assert captured == []
    assert len(model.calls) == 1
    canonical = store.get_research_report(
        task.research_task_id, "owner", report_version=reservation.report.report_version,
    )
    canonical_payload = json.loads(canonical.report_json)
    assert canonical_payload["report_content"] == content
    assert canonical_payload["generation"]["agent_run_ids"] == [_run_input.agent_run_id]

    # A restart after canonical persistence reads and re-renders the saved
    # canonical body; it does not dispatch the completed AgentRun again.
    replay = orchestrator._generate_report_quality_body(**args)
    assert replay["status"] == "generating"
    assert replay["diagnostic"]["code"] == "REPORT_DELIVERY_PENDING"
    assert replay["rendered"] == result["rendered"]
    assert captured == []
    assert len(model.calls) == 1


def test_report_quality_body_recovers_targeted_revision_with_previous_checkpoint_context(tmp_path):
    store, catalog_store, task, _work_item, candidates = _seed_report_context(tmp_path)
    reservation, running = _reserve_running_report(
        store, task, request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6bd81",
        request_payload={"plan_version": 1, "purpose": "targeted-revision-recovery"},
    )
    session_id = "session-report-targeted-revision-recovery"
    _create_runtime_session(store, task, session_id)
    progress = store.get_report_generation_budget(
        task.research_task_id, "owner", reservation.report.report_version,
    )
    progress = store.update_report_generation_state(
        task.research_task_id, "owner", reservation.report.report_version,
        expected_revision=0, stage="drafting", rewrite_count=0,
    )
    paper_ids = [item["paper_id"] for item in candidates]
    failed_content = _quality_report_content(paper_ids, cjk_repetitions=10)
    passing_content = _quality_report_content(paper_ids)
    model = FakeModel([
        _report_runtime_output(reservation.report.report_version, running.work_item_id, failed_content),
        _report_runtime_output(reservation.report.report_version, running.work_item_id, passing_content),
    ])
    first_run, _first_input, runtime = _checkpoint_quality_run(
        store=store, catalog_store=catalog_store, task=task, work_item=running,
        session_id=session_id, reservation=reservation, candidates=candidates,
        model=model, stage="drafting",
    )
    progress = store.get_report_generation_budget(
        task.research_task_id, "owner", reservation.report.report_version,
    )
    progress = store.update_report_generation_state(
        task.research_task_id, "owner", reservation.report.report_version,
        expected_revision=progress["revision"], stage="quality_check", rewrite_count=0,
        reason_codes=["CJK_COUNT_BELOW_MINIMUM"],
    )
    progress = store.get_report_generation_budget(
        task.research_task_id, "owner", reservation.report.report_version,
    )
    progress = store.update_report_generation_state(
        task.research_task_id, "owner", reservation.report.report_version,
        expected_revision=progress["revision"], stage="targeted_revision", rewrite_count=1,
        reason_codes=["CJK_COUNT_BELOW_MINIMUM"],
    )
    captured = []

    class _RuntimeProbe:
        def run(self, run_input):
            captured.append(run_input)
            return runtime.run(run_input)

    orchestrator = Orchestrator(
        store=store, search_adapter=SimpleNamespace(_store=catalog_store),
        probe=object(), agent_runner=_RuntimeProbe(),
    )
    result = orchestrator._generate_report_quality_body(
        task=task, owner_id="owner", work_item=running,
        selected_candidates=_selected_candidates(candidates),
        reservation=reservation, session_id=session_id,
    )

    assert result["status"] == "generating"
    assert result["diagnostic"]["code"] == "REPORT_DELIVERY_PENDING"
    assert len(captured) == 1
    revision_marker = captured[0].work_item_input["report_quality_context"]
    assert revision_marker["stage"] == "targeted_revision"
    assert revision_marker["revision_count"] == 1
    assert revision_marker["prior_report_content"] == failed_content
    assert revision_marker["failure_codes"] == ["CJK_COUNT_BELOW_MINIMUM"]
    assert len(model.calls) == 2
    assert store.get_agent_run(first_run.agent_run_id, "owner").status == "completed"
    assert store.get_report_generation_budget(
        task.research_task_id, "owner", reservation.report.report_version,
    )["rewrite_count"] == 1


def test_report_quality_body_reuses_completed_comparison_checkpoint(tmp_path):
    store, catalog_store, task, _work_item, candidates = _seed_report_context(tmp_path)
    reservation, running = _reserve_running_report(
        store, task, request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6bd82",
        request_payload={"plan_version": 1, "purpose": "comparison-recovery"},
    )
    session_id = "session-report-comparison-recovery"
    _create_runtime_session(store, task, session_id)
    progress = store.update_report_generation_state(
        task.research_task_id, "owner", reservation.report.report_version,
        expected_revision=0, stage="evidence_review", rewrite_count=0,
    )
    progress = store.update_report_generation_state(
        task.research_task_id, "owner", reservation.report.report_version,
        expected_revision=progress["revision"], stage="comparison", rewrite_count=0,
    )
    paper_ids = [item["paper_id"] for item in candidates]
    model = FakeModel([
        _report_runtime_output(
            reservation.report.report_version, running.work_item_id,
            _quality_report_content(paper_ids),
        ),
        _report_runtime_output(
            reservation.report.report_version, running.work_item_id,
            _quality_report_content(paper_ids),
        ),
    ])
    comparison, _comparison_input, runtime = _checkpoint_quality_run(
        store=store, catalog_store=catalog_store, task=task, work_item=running,
        session_id=session_id, reservation=reservation, candidates=candidates,
        model=model, stage="comparison",
    )
    captured = []

    class _RuntimeProbe:
        def run(self, run_input):
            captured.append(run_input)
            return runtime.run(run_input)

    orchestrator = Orchestrator(
        store=store, search_adapter=SimpleNamespace(_store=catalog_store),
        probe=object(), agent_runner=_RuntimeProbe(),
    )
    result = orchestrator._generate_report_quality_body(
        task=task, owner_id="owner", work_item=running,
        selected_candidates=_selected_candidates(candidates),
        reservation=reservation, session_id=session_id,
    )

    assert result["status"] == "generating"
    assert result["diagnostic"]["code"] == "REPORT_DELIVERY_PENDING"
    assert comparison.agent_run_id not in {item.agent_run_id for item in captured}
    assert len(captured) == 1
    assert captured[0].work_item_input["report_quality_context"]["stage"] == "drafting"
    assert len(model.calls) == 2


def test_agent_work_item_resumes_saved_canonical_delivery_without_model_rerun(tmp_path):
    store, catalog_store, task, _unused_item, candidates = _seed_report_context(tmp_path)
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    memory.create_conversation("owner", conversation_id="conversation")
    trigger = memory.create_message("conversation", "owner", "user", task.goal, status="completed")
    activity = memory.create_message(
        "conversation", "owner", "assistant", "research started",
        status="completed", parent_message_id=trigger.message_id,
    )
    session = ResearchSession(
        "session-report-canonical-recovery", "owner", "conversation", trigger.message_id,
        "intake-report-canonical-recovery", "running", current_plan_version=1,
        activity_message_id=activity.message_id, research_task_id=task.research_task_id,
    )
    store.create_session(session, memory_repository=memory)
    reservation = store.reserve_report_generation(
        task.research_task_id, "owner", plan_version=1,
        request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6bd83",
        request_payload={
            "plan_version": 1, "selected_paper_ids": [item["paper_id"] for item in candidates],
            "schema_version": "report-quality-v1",
        },
        work_item_input={"validated_candidates": _selected_candidates(candidates)},
    )
    running = store.update_work_item_status(
        reservation.work_item.work_item_id, "running", attempt=1,
    )
    content = _quality_report_content([item["paper_id"] for item in candidates])
    output = _report_runtime_output(reservation.report.report_version, running.work_item_id, content)
    model = FakeModel([output, output])
    skill = {
        "name": "research-report-synthesis", "schema_version": "1",
        "content_hash": "skill-hash", "source_ref": "skill:research-report-synthesis",
        "enabled": True, "tools": [],
    }
    runtime = ResearchAgentRunner(
        store=store, model=model,
        capability_registry=RoleCapabilityRegistry(skills=[skill]),
    )
    orchestrator = Orchestrator(
        store=store, search_adapter=SimpleNamespace(_store=catalog_store),
        probe=object(), agent_runner=runtime, memory_repository=memory,
    )
    generated = orchestrator._generate_report_quality_body(
        task=task, owner_id="owner", work_item=running,
        selected_candidates=_selected_candidates(candidates),
        reservation=reservation, session_id=session.research_session_id,
    )
    assert generated["status"] == "generating"
    assert generated["diagnostic"]["code"] == "REPORT_DELIVERY_PENDING"
    assert store.get_work_item(running.work_item_id).status == "running"
    assert len(model.calls) == 2

    resumed = orchestrator._run_agent_work_items(task=task, owner_id="owner", plan_version=1)

    assert resumed.status == "completed"
    assert len(model.calls) == 2
    published = store.get_research_report(
        task.research_task_id, "owner", report_version=reservation.report.report_version,
    )
    assert published.status == "completed"
    assert json.loads(published.report_json)["generation"]["published"] is True
    assert store.get_work_item(running.work_item_id).status == "completed"
    assert {item.artifact_type for item in store.list_artifacts_for_task(
        task.research_task_id, "owner", report_version=reservation.report.report_version,
    )} == {"markdown", "html", "citation_manifest"}
    assert len(store.list_notifications("owner")) == 1


@pytest.mark.parametrize(
    ("trusted_paper_count", "expected_report_status", "expected_model_calls", "expected_item_status"),
    [(5, "completed", 2, "completed"), (4, "failed", 0, "failed")],
)
def test_startup_recovery_uses_successor_without_reopening_task(
    tmp_path, trusted_paper_count, expected_report_status, expected_model_calls, expected_item_status,
):
    store, catalog_store, task, _unused_item, candidates = _seed_report_context(
        tmp_path, trusted_paper_count=trusted_paper_count,
    )
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    memory.create_conversation("owner", conversation_id="conversation")
    trigger = memory.create_message("conversation", "owner", "user", task.goal, status="completed")
    activity = memory.create_message(
        "conversation", "owner", "assistant", "research started",
        status="completed", parent_message_id=trigger.message_id,
    )
    session = ResearchSession(
        "session-report-startup-recovery", "owner", "conversation", trigger.message_id,
        "intake-report-startup-recovery", "running", current_plan_version=1,
        activity_message_id=activity.message_id, research_task_id=task.research_task_id,
    )
    store.create_session(session, memory_repository=memory)
    reservation = store.reserve_report_generation(
        task.research_task_id, "owner", plan_version=1,
        request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6d699",
        request_payload={
            "plan_version": 1, "selected_paper_ids": [item["paper_id"] for item in candidates],
            "schema_version": "report-quality-v1",
        },
        work_item_input={"validated_candidates": _selected_candidates(candidates)},
    )
    original = store.update_work_item_status(
        reservation.work_item.work_item_id, "running", attempt=1,
    )
    content = _quality_report_content([item["paper_id"] for item in candidates])

    class _BoundOutputModel:
        def __init__(self):
            self.calls = []

        def invoke(self, context, tools=()):
            self.calls.append((dict(context), tuple(tools)))
            return _report_runtime_output(
                reservation.report.report_version,
                context["server_work_item_id"],
                content,
            )

    class _InlineExecutor:
        def submit(self, function, *args, **kwargs):
            function(*args, **kwargs)

    model = _BoundOutputModel()
    skill = {
        "name": "research-report-synthesis", "schema_version": "1",
        "content_hash": "skill-hash", "source_ref": "skill:research-report-synthesis",
        "enabled": True, "tools": [],
    }
    runtime = ResearchAgentRunner(
        store=store, model=model,
        capability_registry=RoleCapabilityRegistry(skills=[skill]),
    )
    orchestrator = Orchestrator(
        store=store, search_adapter=SimpleNamespace(_store=catalog_store),
        probe=object(), agent_runner=runtime, memory_repository=memory,
    )
    service = ResearchService(store=store, orchestrator=orchestrator, executor=_InlineExecutor())

    assert service.recover_interrupted() == 1

    current_task = store.get_task(task.research_task_id, "owner")
    current_report = store.get_research_report(
        task.research_task_id, "owner", report_version=reservation.report.report_version,
    )
    current_reservation = store.get_report_generation_reservation(
        task.research_task_id, "owner", request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6d699",
    )
    items = store.list_work_items(task.research_task_id, plan_version=1)

    assert current_task.status == "interrupted"
    assert original.status == "running"
    assert store.get_work_item(original.work_item_id).status == "interrupted"
    assert current_reservation.work_item.work_item_id != original.work_item_id
    assert current_reservation.work_item.status == expected_item_status
    assert current_report.status == expected_report_status
    assert len(model.calls) == expected_model_calls
    if expected_report_status == "completed":
        assert json.loads(current_report.report_json)["generation"]["published"] is True
        assert {item.artifact_type for item in store.list_artifacts_for_task(
            task.research_task_id, "owner", report_version=reservation.report.report_version,
        )} == {"markdown", "html", "citation_manifest"}
    else:
        progress = store.get_report_generation_budget(
            task.research_task_id, "owner", reservation.report.report_version,
        )
        assert progress["reason_codes"] == ["INSUFFICIENT_TRUSTED_EVIDENCE"]
        assert "report_content" not in json.loads(current_report.report_json)
        assert store.list_artifacts_for_task(
            task.research_task_id, "owner", report_version=reservation.report.report_version,
        ) == []
    assert len(items) == 2


@pytest.mark.parametrize("completed_before_crash", [False, True])
def test_startup_recovery_reuses_historical_runtime_checkpoint(
    tmp_path, completed_before_crash,
):
    store, catalog_store, task, _unused_item, candidates = _seed_report_context(tmp_path)
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    memory.create_conversation("owner", conversation_id="conversation")
    trigger = memory.create_message("conversation", "owner", "user", task.goal, status="completed")
    activity = memory.create_message(
        "conversation", "owner", "assistant", "research started",
        status="completed", parent_message_id=trigger.message_id,
    )
    session = ResearchSession(
        "session-report-checkpoint-recovery", "owner", "conversation", trigger.message_id,
        "intake-report-checkpoint-recovery", "running", current_plan_version=1,
        activity_message_id=activity.message_id, research_task_id=task.research_task_id,
    )
    store.create_session(session, memory_repository=memory)
    reservation = store.reserve_report_generation(
        task.research_task_id, "owner", plan_version=1,
        request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6d698",
        request_payload={
            "plan_version": 1, "selected_paper_ids": [item["paper_id"] for item in candidates],
            "schema_version": "report-quality-v1",
        },
        work_item_input={"validated_candidates": _selected_candidates(candidates)},
    )
    original = store.update_work_item_status(
        reservation.work_item.work_item_id, "running", attempt=1,
    )
    content = _quality_report_content([item["paper_id"] for item in candidates])
    output = _report_runtime_output(reservation.report.report_version, original.work_item_id, content)
    model = FakeModel([output, output])
    skill = {
        "name": "research-report-synthesis", "schema_version": "1",
        "content_hash": "skill-hash", "source_ref": "skill:research-report-synthesis",
        "enabled": True, "tools": [],
    }
    runtime = ResearchAgentRunner(
        store=store, model=model,
        capability_registry=RoleCapabilityRegistry(skills=[skill]),
    )
    orchestrator = Orchestrator(
        store=store, search_adapter=SimpleNamespace(_store=catalog_store),
        probe=object(), agent_runner=runtime, memory_repository=memory,
    )
    generated = orchestrator._generate_report_quality_body(
        task=task,
        owner_id="owner",
        work_item=original,
        selected_candidates=_selected_candidates(candidates),
        reservation=reservation,
        session_id=session.research_session_id,
    )
    assert generated["status"] == "generating"
    assert len(model.calls) == 2
    if completed_before_crash:
        store.update_work_item_status(
            original.work_item_id,
            "completed",
            output_json=json.dumps({"checkpoint_saved": True}),
        )
    assert store.mark_running_interrupted() == 1

    class _InlineExecutor:
        def submit(self, function, *args, **kwargs):
            function(*args, **kwargs)

    service = ResearchService(store=store, orchestrator=orchestrator, executor=_InlineExecutor())
    assert service.recover_interrupted() == 0

    current_reservation = store.get_report_generation_reservation(
        task.research_task_id, "owner", request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6d698",
    )
    current_report = store.get_research_report(
        task.research_task_id, "owner", report_version=reservation.report.report_version,
    )
    assert store.get_task(task.research_task_id, "owner").status == "interrupted"
    assert current_reservation.work_item.work_item_id != original.work_item_id
    assert current_reservation.work_item.status == "completed"
    assert store.get_work_item(original.work_item_id).status == (
        "completed" if completed_before_crash else "interrupted"
    )
    assert current_report.status == "completed"
    assert json.loads(current_report.report_json)["generation"]["published"] is True
    assert len(model.calls) == 2
    assert {item.artifact_type for item in store.list_artifacts_for_task(
        task.research_task_id, "owner", report_version=reservation.report.report_version,
    )} == {"markdown", "html", "citation_manifest"}


def test_startup_recovery_finalizes_published_canonical_from_terminal_work_item(tmp_path):
    store, catalog_store, task, _unused_item, candidates = _seed_report_context(tmp_path)
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    memory.create_conversation("owner", conversation_id="conversation")
    trigger = memory.create_message("conversation", "owner", "user", task.goal, status="completed")
    activity = memory.create_message(
        "conversation", "owner", "assistant", "research started",
        status="completed", parent_message_id=trigger.message_id,
    )
    session = ResearchSession(
        "session-report-published-recovery", "owner", "conversation", trigger.message_id,
        "intake-report-published-recovery", "running", current_plan_version=1,
        activity_message_id=activity.message_id, research_task_id=task.research_task_id,
    )
    store.create_session(session, memory_repository=memory)
    reservation = store.reserve_report_generation(
        task.research_task_id, "owner", plan_version=1,
        request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6d697",
        request_payload={
            "plan_version": 1, "selected_paper_ids": [item["paper_id"] for item in candidates],
            "schema_version": "report-quality-v1",
        },
        work_item_input={"validated_candidates": _selected_candidates(candidates)},
    )
    original = store.update_work_item_status(
        reservation.work_item.work_item_id, "running", attempt=1,
    )
    content = _quality_report_content([item["paper_id"] for item in candidates])
    output = _report_runtime_output(reservation.report.report_version, original.work_item_id, content)
    model = FakeModel([output, output])
    skill = {
        "name": "research-report-synthesis", "schema_version": "1",
        "content_hash": "skill-hash", "source_ref": "skill:research-report-synthesis",
        "enabled": True, "tools": [],
    }
    runtime = ResearchAgentRunner(
        store=store, model=model,
        capability_registry=RoleCapabilityRegistry(skills=[skill]),
    )
    orchestrator = Orchestrator(
        store=store, search_adapter=SimpleNamespace(_store=catalog_store),
        probe=object(), agent_runner=runtime, memory_repository=memory,
    )
    generated = orchestrator._generate_report_quality_body(
        task=task,
        owner_id="owner",
        work_item=original,
        selected_candidates=_selected_candidates(candidates),
        reservation=reservation,
        session_id=session.research_session_id,
    )
    assert generated["status"] == "generating"
    assert len(model.calls) == 2
    current_report = store.get_research_report(
        task.research_task_id, "owner", report_version=reservation.report.report_version,
    )
    delivery = ReportDeliveryService(store=store, memory_repository=memory)
    delivery.prepare_canonical(
        task=task,
        session=session,
        owner_id="owner",
        reservation=reservation,
        report=current_report,
        report_version=reservation.report.report_version,
        rendered=generated["rendered"],
    )
    progress = store.get_report_generation_budget(
        task.research_task_id, "owner", reservation.report.report_version,
    )
    store.update_report_generation_state(
        task.research_task_id, "owner", reservation.report.report_version,
        expected_revision=progress["revision"], stage="published",
        rewrite_count=progress["rewrite_count"], status="completed", published=True,
        reason_codes=[],
    )
    assert store.update_task_status(
        task.research_task_id, "owner", "interrupted",
    ).status == "interrupted"
    assert store.get_work_item(original.work_item_id).status == "running"

    class _InlineExecutor:
        def submit(self, function, *args, **kwargs):
            function(*args, **kwargs)

    service = ResearchService(store=store, orchestrator=orchestrator, executor=_InlineExecutor())
    assert service.recover_interrupted() == 0

    current_report = store.get_research_report(
        task.research_task_id, "owner", report_version=reservation.report.report_version,
    )
    current_reservation = store.get_report_generation_reservation(
        task.research_task_id, "owner", request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6d697",
    )
    assert store.get_task(task.research_task_id, "owner").status == "interrupted"
    assert current_reservation.work_item.work_item_id == original.work_item_id
    assert current_reservation.work_item.status == "interrupted"
    assert current_report.status == "completed"
    assert json.loads(current_report.report_json)["generation"]["published"] is True
    assert len(model.calls) == 2
    assert {item.artifact_type for item in store.list_artifacts_for_task(
        task.research_task_id, "owner", report_version=reservation.report.report_version,
    )} == {"markdown", "html", "citation_manifest"}
    notifications = store.list_notifications("owner")
    assert sum(item.notification_kind == "completed" for item in notifications) == 1


@pytest.mark.parametrize(
    ("failed_drafts", "keep_failing", "expected_status"),
    [(1, False, "generating"), (2, False, "generating"), (2, True, "draft")],
)
def test_report_quality_body_claims_budget_revises_and_saves_with_reserved_report_version(
    tmp_path, failed_drafts, keep_failing, expected_status,
):
    store, catalog_store, task, _work_item, candidates = _seed_report_context(tmp_path)
    # Advance the report sequence so it cannot be confused with plan_version.
    first = store.reserve_report_generation(
        task.research_task_id, "owner", plan_version=1,
        request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6bd78",
        request_payload={"plan_version": 1, "purpose": "advance-version"},
    )
    store.update_report_generation_state(
        task.research_task_id, "owner", first.report.report_version,
        expected_revision=0, stage="failed", rewrite_count=0, status="failed", published=False,
    )
    reservation, running = _reserve_running_report(
        store, task, request_key="c5b06cd7-7e8e-40ec-88d2-21c066d6bd79",
        request_payload={"plan_version": 1, "purpose": "quality-body"},
    )
    assert reservation.report.report_version == 2

    class _MemoryReferences:
        @staticmethod
        def get_conversation(_conversation_id, _owner_id):
            return SimpleNamespace(owner_id="owner")

        @staticmethod
        def get_message(_message_id, _owner_id):
            return SimpleNamespace(conversation_id="conversation")

    store.create_session(ResearchSession(
        "session-report-quality-body", "owner", "conversation", "trigger-message",
        "intake-report-quality-body", "running", current_plan_version=1,
        research_task_id=task.research_task_id,
    ), memory_repository=_MemoryReferences())
    papers = [item["paper_id"] for item in candidates]
    low_quality = _quality_report_content(papers, cjk_repetitions=10)
    passing = _quality_report_content(papers)
    run_inputs = []

    draft_runs = 0

    def fake_runner(run_input):
        nonlocal draft_runs
        assert 1 <= run_input.attempt <= 4
        run_inputs.append(run_input)
        marker = run_input.work_item_input["report_quality_context"]
        if marker["stage"] == "comparison":
            content = low_quality
        else:
            draft_runs += 1
            content = low_quality if draft_runs <= failed_drafts or keep_failing else passing
        store.create_agent_run(AgentRun(
            run_input.agent_run_id, run_input.research_session_id, run_input.attempt,
            "synthesizer", "research-report-synthesis", "1", "probe-hash", "probe-model",
            "off", "[]", provider="test", status="completed",
            research_task_id=task.research_task_id, work_item_id=running.work_item_id,
            started_at="2026-10-29T00:00:00Z", ended_at="2026-10-29T00:00:01Z",
            owner_id="owner",
        ), owner_id="owner")
        return SimpleNamespace(
            status="completed",
            output_json={
                "schema_version": "runtime-v1", "safe_summary": {}, "source_refs": [],
                "work_item_id": running.work_item_id,
                "report_version": run_input.work_item_input["report_version"],
                "sections": [], "citation_manifest": [], "artifact_ids": [],
                "report_content": content,
            },
            model_metadata={"provider": "test", "model": "probe-model"},
            agent_run_id=run_input.agent_run_id,
        )

    orchestrator = Orchestrator(
        store=store, search_adapter=SimpleNamespace(_store=catalog_store),
        probe=object(), agent_runner=SimpleNamespace(run=fake_runner),
    )
    result = orchestrator._generate_report_quality_body(
        task=task, owner_id="owner", work_item=running,
        selected_candidates=_selected_candidates(candidates),
        reservation=reservation, session_id="session-report-quality-body",
    )

    assert result["status"] == expected_status
    assert result["report_version"] == reservation.report.report_version
    assert result["report_version"] != task.current_plan_version
    assert result["quality_validation"]["status"] == ("fail" if keep_failing else "pass")
    assert result["quality_validation"]["revision_count"] == failed_drafts
    if keep_failing:
        assert result["rendered"] is None
    else:
        assert result["rendered"]["report"]["report_content"] == passing
    assert len(run_inputs) == failed_drafts + 2
    assert [item.attempt for item in run_inputs] == [1] * len(run_inputs)
    assert len({item.agent_run_id for item in run_inputs}) == len(run_inputs)
    comparison_context = run_inputs[0].work_item_input["report_quality_context"]
    assert comparison_context["report_version"] == reservation.report.report_version
    assert comparison_context["stage"] == "comparison"
    first_context = run_inputs[1].work_item_input["report_quality_context"]
    assert first_context["stage"] == "drafting"
    for revision_number, run_input in enumerate(run_inputs[2:], start=1):
        revision_context = run_input.work_item_input["report_quality_context"]
        assert revision_context["stage"] == "targeted_revision"
        assert revision_context["revision_count"] == revision_number
        assert revision_context["failure_codes"] == ["CJK_COUNT_BELOW_MINIMUM"]
        assert revision_context["prior_report_content"] == low_quality
    assert all({item["evidence_level"] for item in context["evidence"]} <= {"abstract", "fulltext"}
               for context in (
                   run_input.work_item_input["report_quality_context"]
                   for run_input in run_inputs
               ))
    progress = store.get_report_generation_budget(
        task.research_task_id, "owner", reservation.report.report_version,
    )
    assert progress["report"].status == expected_status
    assert progress["stage"] == ("draft_saved" if keep_failing else "quality_check")
    assert progress["rewrite_count"] == failed_drafts
    canonical = store.get_research_report(
        task.research_task_id, "owner", report_version=reservation.report.report_version,
    )
    canonical_json = json.loads(canonical.report_json)
    assert canonical_json["report_content"] == (low_quality if keep_failing else passing)
    assert len(canonical_json["generation"]["agent_run_ids"]) == failed_drafts + 2
    claims = canonical_json["generation"]["store_state"]["claims"]
    assert len(claims) == failed_drafts + 2
    assert all(claim["settled"] is True for claim in claims)
    assert all(run_input.budget_snapshot["model_loops"] == 0 for run_input in run_inputs)
    assert all(run_input.budget_snapshot["tool_calls"] == 0 for run_input in run_inputs)
    if keep_failing:
        assert canonical_json["reason_codes"] == ["CJK_COUNT_BELOW_MINIMUM"]


def test_synthesis_dispatch_uses_run_local_budget_after_prior_matrix_run(tmp_path, monkeypatch):
    store, catalog_store, task, _unused_item, candidates = _seed_report_context(tmp_path)
    paper_ids = [item["paper_id"] for item in candidates]
    selected = _selected_candidates(candidates)

    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    memory.create_conversation("owner", conversation_id="conversation")
    trigger_message = memory.create_message(
        "conversation", "owner", "user", task.goal, status="completed",
    )
    activity_message = memory.create_message(
        "conversation", "owner", "assistant", "research started",
        status="completed", parent_message_id=trigger_message.message_id,
    )
    session = ResearchSession(
        "session-report-matrix-budget", "owner", "conversation", trigger_message.message_id,
        "intake-report-matrix-budget", "running", current_plan_version=1,
        activity_message_id=activity_message.message_id,
        research_task_id=task.research_task_id,
    )
    store.create_session(session, memory_repository=memory)
    work_item = ResearchWorkItem(
        "work-report-matrix-budget", task.research_task_id, 1,
        "synthesize_preliminary_report", "synthesizer", "[]", "{}", "queued", 1, "", "",
    )
    store.create_work_items(task.research_task_id, [work_item])
    request_key = str(uuid5(
        NAMESPACE_URL,
        f"spec030-report-quality:{task.research_task_id}:1:{work_item.work_item_id}",
    ))
    request_payload = {
        "plan_version": 1,
        "selected_paper_ids": paper_ids,
        "schema_version": "report-quality-v1",
    }
    reservation = store.reserve_report_generation(
        task.research_task_id, "owner", plan_version=1,
        request_key=request_key, request_payload=request_payload,
        work_item_input={"validated_candidates": selected},
    )
    assert reservation.work_item.work_item_id == work_item.work_item_id

    # Simulate a resumed synthesis WorkItem after its matrix AgentRun consumed
    # the full per-run grant. Its next matrix dispatch must start at zero while
    # preserving cumulative task usage.
    prior_run_id = f"{work_item.work_item_id}:run-1"
    prior_claim_id = str(uuid4())
    prior_claim = store.claim_report_generation_budget(
        task.research_task_id, "owner", reservation.report.report_version,
        claim_id=prior_claim_id, agent_run_id=prior_run_id,
        requested_model_loops=40, requested_tool_calls=160, requested_seconds=120,
    )
    assert prior_claim["allowed"] is True
    store.create_agent_run(AgentRun(
        prior_run_id, session.research_session_id, 1,
        "synthesizer", "research-report-synthesis", "1", "probe-hash", "probe-model",
        "off", "[]", provider="test", status="completed",
        model_loop_count=40, tool_call_count=160,
        research_task_id=task.research_task_id, work_item_id=work_item.work_item_id,
        started_at="2026-10-29T00:00:00Z", ended_at="2026-10-29T00:00:01Z",
        owner_id="owner",
    ), owner_id="owner")
    settled = store.settle_report_generation_budget(
        task.research_task_id, "owner", reservation.report.report_version,
        claim_id=prior_claim_id,
    )
    assert settled["settled"] is True

    import backend.app.research.application.orchestrator as orchestrator_module

    monkeypatch.setattr(
        orchestrator_module, "_recall_allowlist_from_search_outputs",
        lambda _outputs: set(paper_ids),
    )
    monkeypatch.setattr(
        orchestrator_module, "_validated_evaluator_candidates",
        lambda *_args, **_kwargs: [dict(item) for item in selected],
    )
    refs = [f"catalog:{paper_id}" for paper_id in paper_ids]
    synthesis_output = {
        "schema_version": "report-synthesis-v1",
        "report_version": reservation.report.report_version,
        "sections": [{"heading": "候选目录", "candidate_ids": paper_ids}],
        "citation_manifest": [
            {"citation_ref": ref, "candidate_id": paper_id}
            for paper_id, ref in zip(paper_ids, refs, strict=True)
        ],
        "artifact_ids": [],
        "safe_summary": {"candidate_count": len(paper_ids)},
        "source_refs": refs,
    }
    quality_output = {
        "schema_version": "report-synthesis-v1",
        "report_version": reservation.report.report_version,
        "sections": [], "citation_manifest": [], "artifact_ids": [],
        "safe_summary": {}, "source_refs": [],
        "report_content": _quality_report_content(paper_ids),
    }
    model = FakeModel([
        {"output_json": synthesis_output},
        {"output_json": quality_output},
        {"output_json": quality_output},
    ])
    skill = {
        "name": "research-report-synthesis", "schema_version": "1",
        "content_hash": "skill-hash", "source_ref": "skill:research-report-synthesis",
        "enabled": True, "tools": [],
    }
    runtime = ResearchAgentRunner(
        store=store, model=model,
        capability_registry=RoleCapabilityRegistry(skills=[skill]),
    )
    captured = []

    class _RuntimeProbe:
        event_sink = None

        def run(self, run_input):
            captured.append(run_input)
            return runtime.run(run_input)

    orchestrator = Orchestrator(
        store=store, search_adapter=SimpleNamespace(_store=catalog_store),
        probe=object(), agent_runner=_RuntimeProbe(), memory_repository=memory,
    )
    # Preserve the fixture's correctly bound frozen snapshots; the dispatch
    # selection is the same five papers and does not need to rewrite sources.
    orchestrator._persist_agent_selections = lambda *_args, **_kwargs: None
    # The seed already holds a task/plan-bound matrix. This run tests the
    # Runtime preflight for resumed matrix synthesis without making the model
    # generate another matrix payload.
    build_matrix_context = orchestrator._build_synthesis_matrix_context
    matrix_context_calls = 0

    def skip_matrix_prompt_only(**kwargs):
        nonlocal matrix_context_calls
        matrix_context_calls += 1
        if matrix_context_calls == 1:
            return None
        return build_matrix_context(**kwargs)

    orchestrator._build_synthesis_matrix_context = skip_matrix_prompt_only

    result = orchestrator._run_agent_work_items(task=task, owner_id="owner", plan_version=1)

    if result.status != "completed":
        current_report = store.get_research_report(
            task.research_task_id, "owner", report_version=reservation.report.report_version,
        )
        current_payload = json.loads(current_report.report_json) if current_report else {}
        current_generation = current_payload.get("generation", {})
        activity = memory.get_activity_message(
            session.conversation_id, "owner", f"research-report:{task.research_task_id}:1",
        )
        raise AssertionError({
            "error_code": result.error_code,
            "report_status": current_report.status if current_report else None,
            "generation_path": current_generation.get("path"),
            "published": current_generation.get("published"),
            "reason_codes": current_payload.get("reason_codes"),
            "quality_status": current_payload.get("quality_validation", {}).get("status"),
            "artifacts": [item.artifact_type for item in store.list_artifacts_for_task(
                task.research_task_id, "owner", report_version=reservation.report.report_version,
            )],
            "activity_status": activity.status if activity else None,
        })
    assert len(captured) == 3  # matrix synthesis, comparison, and body drafting
    matrix_dispatch = captured[0]
    assert matrix_dispatch.attempt == 2
    assert matrix_dispatch.budget_snapshot["model_loops"] == 0
    assert matrix_dispatch.budget_snapshot["tool_calls"] == 0
    assert matrix_dispatch.budget_snapshot["task_model_loops"] == 40
    assert matrix_dispatch.budget_snapshot["task_tool_calls"] == 160
    assert matrix_dispatch.budget_snapshot["max_model_loops"] == 40
    assert matrix_dispatch.budget_snapshot["max_tool_calls"] == 160
    assert [item.attempt for item in captured[1:]] == [1, 1]
    # The actual ResearchAgentRunner reached the injected model. With the old
    # 40/40 run-local snapshot it returned limit_reached before this call.
    assert len(model.calls) == 3
    assert store.get_agent_run(matrix_dispatch.agent_run_id, "owner").status == "completed"
    published = store.get_research_report(
        task.research_task_id, "owner", report_version=reservation.report.report_version,
    )
    assert published.status == "completed"
    assert json.loads(published.report_json)["generation"]["published"] is True
    artifacts = store.list_artifacts_for_task(
        task.research_task_id, "owner", report_version=reservation.report.report_version,
    )
    assert {item.artifact_type for item in artifacts} == {"markdown", "html", "citation_manifest"}
    final_message = memory.get_activity_message(
        session.conversation_id, "owner", f"research-report:{task.research_task_id}:1",
    )
    assert final_message.status == "completed"
    assert len(store.list_notifications("owner")) == 1

