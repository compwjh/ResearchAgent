"""Offline integration coverage for evaluated candidates and approved imports."""

from __future__ import annotations

import json
import time

from backend.app.memory.repository import MemoryRepository
from backend.app.paper_discovery.application.paper_import import (
    LOGIN_REQUIRED,
    PaperImportError,
    PaperImportResult,
)
from backend.app.paper_discovery.application.paper_import_batch_service import (
    PaperImportBatchService,
)
from backend.app.paper_discovery.domain.paper_discovery import PaperCandidate, SearchSession
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.paper_discovery.infrastructure.paper_import_batch_store import PaperImportBatchStore
from backend.app.research.application.acquisition import (
    ApprovedPlanAutoImporter,
    ResearchAcquisitionService,
)
from backend.app.research.application.approval_service import PlanApprovalService
from backend.app.research.application.orchestrator import Orchestrator
from backend.app.research.application.plan_authoring import plan_output_hash
from backend.app.research.domain.models import IntakeField, ResearchSession
from backend.app.research.infrastructure.research_store import ResearchStore

OWNER = "owner-integration"


def _plan_output() -> dict:
    output = {
        "schema_version": "1",
        "plan_version": 1,
        "objective": "evaluate catalog candidates",
        "scope": {"facets": ["security"]},
        "work_items": [
            {
                "id": "s1",
                "task_type": "search_catalog",
                "role": "search-worker",
                "depends_on": [],
                "params": {"query": "security"},
            },
            {
                "id": "e1",
                "task_type": "evaluate_papers",
                "role": "paper-evaluator",
                "depends_on": ["s1"],
                "params": {"catalog_paper_ids": []},
            },
        ],
        "capabilities": [],
        "budget": {
            "quality_profile": "balanced",
            "target_paper_count": 2,
            "soft_budget_seconds": 60,
            "language": "en",
        },
        "report_structure": {"sections": ["summary"]},
        "safe_summary": {"decision": "bounded"},
        "source_refs": ["intake:1"],
    }
    output["output_hash"] = plan_output_hash(output)
    return output


def _research_session(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, _assistant = memory.create_conversation_messages(
        OWNER, "evaluate catalog candidates", None, "model", "normal"
    )
    store = ResearchStore(tmp_path / "research.sqlite3")
    session = ResearchSession(
        research_session_id="session-integration",
        owner_id=OWNER,
        conversation_id=conversation.conversation_id,
        trigger_message_id=user.message_id,
        intake_draft_id="draft-integration",
        status="intake_pending",
    )
    store.create_session(session, memory_repository=memory)
    for field_name in ("topic", "objective", "time_range"):
        store.upsert_intake_field(
            IntakeField(
                "draft-integration",
                field_name,
                json.dumps("security"),
                "user_explicit",
                1.0,
                "confirmed",
                "2026-01-01T00:00:00Z",
                user.message_id,
            ),
            OWNER,
        )
    store.update_intake_status("draft-integration", OWNER, "complete")
    return memory, store, session


def test_evaluated_candidates_flow_through_approved_auto_import_to_task_issue(tmp_path):
    memory, research_store, session = _research_session(tmp_path)
    approval_service = PlanApprovalService(store=research_store, memory_repository=memory)
    approval_service.author_plan(session.research_session_id, OWNER, _plan_output())
    approved = approval_service.command(
        session.research_session_id,
        OWNER,
        command="approve_plan",
        subject_version=1,
        scope_json={"plan_version": 1},
        idempotency_key="approve-integration",
    )
    task_id = approved["task"]["research_task_id"]

    catalog_store = PaperDiscoveryStore(tmp_path / "catalog.sqlite3")
    candidates = [
        PaperCandidate(
            "paper-ok",
            "search-integration",
            "Successful paper",
            "ndss",
            "NDSS",
            year=2024,
            doi="10.1000/ok",
            article_url="https://example.test/ok",
            pdf_url="https://example.test/ok.pdf",
        ),
        PaperCandidate(
            "paper-login",
            "search-integration",
            "Login paper",
            "ndss",
            "NDSS",
            year=2024,
            doi="10.1000/login",
            article_url="https://example.test/login",
            pdf_url="https://example.test/login.pdf",
        ),
    ]
    catalog_store.save_search(
        SearchSession("search-integration", "security", "2099-01-01T00:00:00Z"),
        candidates,
    )
    research_store.set_task_search_id(task_id, "search-integration")

    # This is the same durable projection used after a paper-evaluator result;
    # the whitelist prevents evaluator output from inventing candidate IDs.
    orchestrator = Orchestrator(store=research_store, planner=None, probe=object())
    orchestrator._persist_agent_selections(
        task_id,
        {
            "kept": [
                {
                    "candidate_id": "paper-ok",
                    "keep": True,
                    "relevance_score": 0.9,
                    "evidence_refs": ["catalog:paper-ok"],
                },
                {
                    "candidate_id": "paper-login",
                    "keep": True,
                    "relevance_score": 0.8,
                    "evidence_refs": ["catalog:paper-login"],
                },
            ]
        },
        {"paper-ok", "paper-login"},
        {"paper-ok": "search-integration", "paper-login": "search-integration"},
    )
    assert [item.catalog_paper_id for item in research_store.list_selections(task_id)] == [
        "paper-ok",
        "paper-login",
    ]

    def importer(candidate, *_args):
        if candidate.candidate_id == "paper-login":
            raise PaperImportError(LOGIN_REQUIRED, "login required")
        return PaperImportResult("document-ok", "successful-paper.pdf", "indexed")

    batch_service = PaperImportBatchService(
        PaperImportBatchStore(tmp_path / "imports.sqlite3"),
        discovery_store=catalog_store,
        importer=importer,
        max_workers=1,
    )
    acquisition = ResearchAcquisitionService(research_store, batch_service)
    auto_importer = ApprovedPlanAutoImporter(research_store, acquisition)
    orchestrator = Orchestrator(
        store=research_store,
        planner=None,
        probe=object(),
        auto_importer=auto_importer,
    )
    task = research_store.get_task(task_id, OWNER)
    result = orchestrator._auto_import_approved_selection(
        task=task, owner_id=OWNER, plan_version=1
    )

    assert result["batch_id"]
    batch_id = result["batch_id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        items = batch_service.store.get_items(batch_id)
        if items and all(item.status in {"completed", "waiting_login", "failed"} for item in items):
            break
        time.sleep(0.01)
    status = acquisition.status(task_id)
    assert {item["status"] for item in status["items"]} == {"completed", "waiting_login"}
    issues = research_store.list_acquisition_issues(task_id=task_id, status="open")
    assert len(issues) == 1
    assert issues[0].candidate_id == "paper-login"
    assert issues[0].task_ids == [task_id]
    assert issues[0].reason_code == LOGIN_REQUIRED
    assert issues[0].batch_id == batch_id
