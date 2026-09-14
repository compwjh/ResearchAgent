"""Task10 backend contracts for approval runtime, idempotency, and cleanup CLI."""

from __future__ import annotations

import json
import sqlite3
import sys

import pytest
from test_spec034_task04_contract import OWNER, _output, _setup
from test_spec034_task09_backend import _legacy

from backend.app.research.application.approval_service import PlanApprovalService, ResearchCommandError
from backend.app.research.application.cleanup_snapshot import build_cross_store_snapshot_provider
from backend.app.research.infrastructure.research_store import ResearchStore


class _FakeResearchService:
    def __init__(self, store):
        self.store = store
        self.started: list[tuple[str, str]] = []

    def start(self, task_id: str, owner_id: str) -> bool:
        self.started.append((task_id, owner_id))
        self.store.append_event(task_id, "task", {"status": "planning", "reason": "approved"})
        return True


def test_approve_plan_dispatches_materialized_task_to_existing_research_service(tmp_path):
    memory, store, session = _setup(tmp_path)
    runtime = _FakeResearchService(store)
    service = PlanApprovalService(store=store, memory_repository=memory, research_service=runtime)
    service.author_plan(session.research_session_id, OWNER, _output())

    result = service.command(
        session.research_session_id,
        OWNER,
        command="approve_plan",
        subject_version=1,
        scope_json={},
        idempotency_key="runtime-start",
    )

    task_id = result["task"]["research_task_id"]
    assert runtime.started == [(task_id, OWNER)]
    assert store.get_task(task_id, OWNER).status == "planning"
    assert any(event.event_type == "task" and event.safe_payload_json and "approved" in event.safe_payload_json for event in store.list_events(task_id))


def test_old_command_key_replays_durable_response_before_plan_version_stale(tmp_path):
    memory, store, session = _setup(tmp_path)
    service = PlanApprovalService(store=store, memory_repository=memory)
    service.author_plan(session.research_session_id, OWNER, _output())

    first = service.command(
        session.research_session_id,
        OWNER,
        command="revise_plan",
        subject_version=1,
        scope_json={"objective": "修订后的研究目标"},
        idempotency_key="revise-v1",
    )
    assert store.get_session(session.research_session_id, OWNER).current_plan_version == 2

    replay = service.command(
        session.research_session_id,
        OWNER,
        command="revise_plan",
        subject_version=1,
        scope_json={"objective": "修订后的研究目标"},
        idempotency_key="revise-v1",
    )
    assert replay == first

    with pytest.raises(ResearchCommandError) as stale:
        service.command(
            session.research_session_id,
            OWNER,
            command="revise_plan",
            subject_version=1,
            scope_json={"objective": "另一份新修订"},
            idempotency_key="revise-v1-new-key",
        )
    assert stale.value.code == "PLAN_VERSION_STALE"


def test_cleanup_snapshot_provider_supports_verified_dry_run_and_execute(tmp_path, monkeypatch):
    memory_path = tmp_path / "memory.sqlite3"
    catalog_path = tmp_path / "catalog.sqlite3"
    kb_path = tmp_path / "papers.json"
    research_path = tmp_path / "research.sqlite3"

    # The provider reads pre-existing stores read-only and must never create
    # them as a side effect.
    sqlite3.connect(memory_path).executescript(
        "CREATE TABLE conversations(conversation_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL);"
        "INSERT INTO conversations VALUES('conversation-1','owner-a');"
    )
    sqlite3.connect(catalog_path).executescript(
        "CREATE TABLE catalog_papers(catalog_paper_id TEXT PRIMARY KEY);"
        "INSERT INTO catalog_papers VALUES('paper-1');"
    )
    kb_path.write_text(json.dumps([{"document_id": "doc-1"}]), encoding="utf-8")
    provider = build_cross_store_snapshot_provider(
        owner_id="owner-a",
        memory_database_path=memory_path,
        catalog_database_path=catalog_path,
        kb_metadata_path=kb_path,
    )
    assert provider() == {"sessions": 1, "catalog": 1, "kb": 1, "status": "measured"}

    store = ResearchStore(research_path)
    _legacy(store, "legacy-1", OWNER)
    dry = store.dry_run_legacy_cleanup(OWNER, external_snapshot=provider)
    assert dry["cross_store"]["before"]["status"] == "measured"
    report = store.execute_legacy_cleanup(
        OWNER, confirm=True, dry_run_id=dry["cleanup_id"], external_snapshot=provider
    )
    assert report["status"] == "completed"
    assert report["cross_store"]["unchanged"] is True


def test_cleanup_snapshot_provider_is_unverified_when_external_store_is_unavailable(tmp_path):
    provider = build_cross_store_snapshot_provider(
        owner_id="owner-a",
        memory_database_path=tmp_path / "missing-memory.sqlite3",
        catalog_database_path=tmp_path / "missing-catalog.sqlite3",
        kb_metadata_path=tmp_path / "missing-papers.json",
    )
    value = provider()
    assert value["status"] == "unverified"
    assert value["sessions"] is None
    assert value["catalog"] is None
    assert value["kb"] is None


def test_cleanup_cli_wires_provider_for_real_dry_run_then_execute(tmp_path, monkeypatch, capsys):
    from backend.app.memory.repository import MemoryRepository
    from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
    from backend.scripts import cleanup_legacy_research_tasks as cleanup_cli

    memory_path = tmp_path / "memory.sqlite3"
    catalog_path = tmp_path / "catalog.sqlite3"
    kb_path = tmp_path / "papers.json"
    research_path = tmp_path / "research.sqlite3"
    MemoryRepository(memory_path)
    PaperDiscoveryStore(catalog_path)
    kb_path.write_text(json.dumps([]), encoding="utf-8")
    research = ResearchStore(research_path)
    _legacy(research, "legacy-cli", OWNER)

    monkeypatch.setenv("RESEARCH_DB_PATH", str(research_path))
    monkeypatch.setenv("MEMORY_DB_PATH", str(memory_path))
    monkeypatch.setenv("PAPER_DISCOVERY_DB_PATH", str(catalog_path))
    monkeypatch.setenv("KB_META_PATH", str(kb_path))
    monkeypatch.setattr(sys, "argv", ["cleanup_legacy_research_tasks", "--owner-id", OWNER])
    assert cleanup_cli.main() == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["cross_store"]["before"]["status"] == "measured"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanup_legacy_research_tasks",
            "--owner-id",
            OWNER,
            "--execute",
            "--confirm",
            "--dry-run-id",
            dry["cleanup_id"],
        ],
    )
    assert cleanup_cli.main() == 0
    executed = json.loads(capsys.readouterr().out)
    assert executed["status"] == "completed"
    assert executed["cross_store"]["unchanged"] is True
