"""Task10 backend contracts for approval runtime, idempotency, and cleanup CLI."""

from __future__ import annotations

import json
import sqlite3
import sys
from types import SimpleNamespace

import pytest
from test_spec034_task04_contract import OWNER, _output, _setup
from test_spec034_task05_contract import _output as _runtime_output
from test_spec034_task05_contract import _skill as _runtime_skill
from test_spec034_task09_backend import _legacy

from backend.app.research.application.agent_runtime import (
    AgentRunInput,
    FakeModel,
    FakeTool,
    ResearchAgentRunner,
    RoleCapabilityRegistry,
    _ollama_model_factory,
    _OllamaRunnerAdapter,
    _safe_catalog_metadata,
)
from backend.app.research.application.orchestrator import _canonicalize_search_worker_binding, _catalog_evidence_view
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


def test_ollama_model_factory_off_skips_capability_probe(monkeypatch):
    created = object()
    calls = []

    def fake_create(model_name, *, reasoning=None):
        calls.append((model_name, reasoning))
        return created

    def unexpected_resolve(*_args, **_kwargs):
        raise AssertionError("off must not resolve or probe reasoning capabilities")

    monkeypatch.setattr("backend.app.platform.ollama.create_chat_model", fake_create)
    monkeypatch.setattr("backend.app.platform.ollama.resolve_reasoning_effort", unexpected_resolve)

    result = _ollama_model_factory("qwen3.8:27b", "off")

    assert isinstance(result, _OllamaRunnerAdapter)
    assert result.model is created
    assert result.model_name == "qwen3.8:27b"
    assert result.reasoning_effort == "off"
    assert calls == [("qwen3.8:27b", False)]


def test_ollama_adapter_sends_role_contract_before_context():
    captured = {}

    class Chat:
        def invoke(self, messages):
            captured["messages"] = messages
            return SimpleNamespace(content='{"schema_version":"runtime-v1"}', tool_calls=[])

    adapter = _OllamaRunnerAdapter(Chat(), model_name="test-model", effort="off")
    response = adapter.invoke(
        {"role": "search_worker", "tool_results": [{"catalog_paper_ids": ["paper-1"]}]},
    )

    messages = captured["messages"]
    assert [message["role"] for message in messages] == ["system", "user"]
    contract = messages[0]["content"]
    assert "exactly one JSON object" in contract
    for field in ("schema_version", "safe_summary", "source_refs", "work_item_id", "queries", "source", "candidates", "refresh_diagnostics"):
        assert field in contract
    assert "Do not call a tool again" in contract
    assert "download or import PDFs" in contract
    assert '"catalog_paper_ids"' in messages[1]["content"]
    assert response["output_json"]["schema_version"] == "runtime-v1"


def test_ollama_adapter_evaluator_allows_title_only_catalog_evidence():
    captured = {}

    class Chat:
        def invoke(self, messages):
            captured["messages"] = messages
            return SimpleNamespace(content='{}', tool_calls=[])

    adapter = _OllamaRunnerAdapter(Chat(), model_name="test-model", effort="off")
    adapter.invoke(
        {
            "role": "paper_evaluator",
            "work_item_input": {
                "catalog_paper_ids": ["paper-1"],
                "catalog_evidence": [{
                    "candidate_ids": ["paper-1"],
                    "evidence_refs": ["catalog:paper-1"],
                    "summary": "1. Exact title match\n   摘要: （缺失）",
                }],
            },
        },
    )

    contract = captured["messages"][0]["content"]
    assert "metadata-only" in contract
    assert "Do not invent abstract/content claims" in contract


def test_ollama_adapter_synthesizer_requires_bounded_delivery_shape():
    captured = {}

    class Chat:
        def invoke(self, messages):
            captured["messages"] = messages
            return SimpleNamespace(content="{}", tool_calls=[])

    adapter = _OllamaRunnerAdapter(Chat(), model_name="test-model", effort="off")
    adapter.invoke(
        {
            "role": "synthesizer",
            "work_item_input": {
                "validated_candidates": [{"candidate_id": "paper-1", "evidence_refs": ["catalog:paper-1"]}],
            },
        },
    )

    contract = captured["messages"][0]["content"]
    assert "sections must be a non-empty array" in contract
    assert "artifact_ids must be an empty array" in contract
    assert "section summary must only compare" in contract


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


def test_approve_plan_materializes_task_scoped_dependencies_and_replay_is_unique(tmp_path):
    memory, store, session = _setup(tmp_path)
    service = PlanApprovalService(store=store, memory_repository=memory)
    service.author_plan(session.research_session_id, OWNER, _output())

    result = service.command(
        session.research_session_id,
        OWNER,
        command="approve_plan",
        subject_version=1,
        scope_json={},
        idempotency_key="dependency-prefix",
    )
    task_id = result["research_task_id"]
    items = {item.work_item_id: item for item in store.list_work_items(task_id, plan_version=1)}

    assert set(items) == {f"{task_id}:s1", f"{task_id}:s2", f"{task_id}:e1"}
    assert json.loads(items[f"{task_id}:e1"].depends_on_json) == [f"{task_id}:s1", f"{task_id}:s2"]
    assert json.loads(items[f"{task_id}:s1"].depends_on_json) == []

    replay = service.command(
        session.research_session_id,
        OWNER,
        command="approve_plan",
        subject_version=1,
        scope_json={},
        idempotency_key="dependency-prefix",
    )
    assert replay == result
    assert len(store.list_work_items(task_id, plan_version=1)) == 3

    with pytest.raises(ResearchCommandError) as conflict:
        service.command(
            session.research_session_id,
            OWNER,
            command="approve_plan",
            subject_version=1,
            scope_json={},
            idempotency_key="dependency-prefix-second-window",
        )
    assert conflict.value.code == "APPROVAL_CONFLICT"
    assert len(store.list_work_items(task_id, plan_version=1)) == 3


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


def test_search_worker_preserves_catalog_candidates_when_optional_detail_fetch_fails():
    search = FakeTool(
        "search_paper_catalog",
        lambda _args: {"ok": True, "result_id": "search-1", "output": "catalog candidates"},
        parameters={
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["source", "query"],
        },
    )
    detail = FakeTool(
        "fetch_paper_detail",
        lambda _args: {"ok": False, "error_code": "TOOL_EXECUTION_FAILED"},
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    )
    output = _runtime_output("search_worker")
    output["work_item_id"] = "search-1"
    output["candidates"] = ["paper-1"]
    model = FakeModel([
        {"tool_calls": [{"name": "search_paper_catalog", "arguments": {"source": "usenix", "query": "supply chain"}}]},
        {"tool_calls": [{"name": "fetch_paper_detail", "arguments": {"url": "https://www.usenix.org/conference/usenixsecurity24/presentation/paper"}}]},
        {"tool_calls": [{"name": "fetch_paper_detail", "arguments": {"url": "https://www.usenix.org/conference/usenixsecurity24/presentation/paper"}}]},
        {"output_json": output},
    ])
    registry = RoleCapabilityRegistry(
        skills=[_runtime_skill("search_worker", ["search_paper_catalog", "fetch_paper_detail"])],
        tools=[search, detail],
    )

    result = ResearchAgentRunner(model=model, capability_registry=registry).run(
        AgentRunInput(
            "search-run",
            "session-1",
            "search_worker",
            research_task_id="task-1",
            work_item_id="search-1",
            work_item_input={"query": "supply chain"},
            skill_snapshot=_runtime_skill("search_worker", ["search_paper_catalog", "fetch_paper_detail"]),
            tool_snapshot=[search, detail],
        )
    )

    assert result.status == "completed"
    assert result.error_code is None
    assert result.output_json["candidates"] == ["paper-1"]
    diagnostics = result.output_json["refresh_diagnostics"]
    assert diagnostics["degraded"] is True
    assert diagnostics["detail_fetch_failed"] is True
    assert diagnostics["detail_error_codes"] == ["TOOL_EXECUTION_FAILED"]
    assert search.calls and len(detail.calls) == 1


def test_search_worker_deduplicates_repeated_readonly_tool_calls_before_output():
    search = FakeTool(
        "search_paper_catalog",
        lambda _args: {
            "ok": True,
            "result_id": "search-1",
            "output": "检索完成：来源=USENIX Security，命中 1 篇候选论文。\n"
            "1. Paper\n   catalog_paper_id: paper-1\n"
            "   详情页: https://www.usenix.org/conference/usenixsecurity24/presentation/paper",
        },
        parameters={
            "type": "object",
            "properties": {"source": {"type": "string"}, "query": {"type": "string"}},
            "required": ["source", "query"],
        },
    )
    output = _runtime_output("search_worker")
    output.update({"work_item_id": "search-1", "candidates": ["paper-1"]})
    model = FakeModel([
        {"tool_calls": [{"name": "search_paper_catalog", "arguments": {"source": "usenix", "query": "supply chain"}}]},
        {"tool_calls": [{"name": "search_paper_catalog", "arguments": {"source": "usenix", "query": "supply chain"}}]},
        {"output_json": output},
    ])
    registry = RoleCapabilityRegistry(
        skills=[_runtime_skill("search_worker", ["search_paper_catalog"])],
        tools=[search],
    )

    result = ResearchAgentRunner(model=model, capability_registry=registry).run(
        AgentRunInput(
            "search-dedup",
            "session-1",
            "search_worker",
            research_task_id="task-1",
            work_item_id="search-1",
            work_item_input={"query": "supply chain"},
            skill_snapshot=_runtime_skill("search_worker", ["search_paper_catalog"]),
            tool_snapshot=[search],
        )
    )

    assert result.status == "completed"
    assert result.output_json["candidates"] == ["paper-1"]
    assert len(search.calls) == 1
    assert any(item.get("result_id") == "TOOL_ALREADY_EXECUTED" for item in result.tool_results)


def test_search_worker_recovers_catalog_ids_when_model_never_emits_final_json():
    search = FakeTool(
        "search_paper_catalog",
        lambda _args: {
            "ok": True,
            "result_id": "search-1",
            "output": "检索完成：来源=USENIX Security，命中 1 篇候选论文。\n"
            "1. Paper\n   catalog_paper_id: paper-1",
        },
        parameters={
            "type": "object",
            "properties": {"source": {"type": "string"}, "query": {"type": "string"}},
            "required": ["source", "query"],
        },
    )
    model = FakeModel([
        {"tool_calls": [{"name": "search_paper_catalog", "arguments": {"source": "usenix", "query": "supply chain"}}]},
        {"output_json": {}},
    ])
    registry = RoleCapabilityRegistry(
        skills=[_runtime_skill("search_worker", ["search_paper_catalog"])],
        tools=[search],
    )

    result = ResearchAgentRunner(model=model, capability_registry=registry).run(
        AgentRunInput(
            "search-recover",
            "session-1",
            "search_worker",
            research_task_id="task-1",
            work_item_id="search-1",
            work_item_input={"query": "supply chain", "sources": ["usenix"]},
            skill_snapshot=_runtime_skill("search_worker", ["search_paper_catalog"]),
            tool_snapshot=[search],
        )
    )

    assert result.status == "completed", f"{result.error_code}: {result.to_dict()}"
    assert result.output_json["candidates"] == ["paper-1"]
    assert result.output_json["refresh_diagnostics"]["recovered_from_catalog_tool"] is True
    assert result.output_json["refresh_diagnostics"]["metadata_only"] is True


def test_search_worker_replaces_schema_valid_empty_candidates_with_catalog_facts():
    search = FakeTool(
        "search_paper_catalog",
        lambda _args: {"ok": True, "result_id": "search-2", "output": "catalog_paper_id: paper-2"},
        parameters={"type": "object", "properties": {"source": {"type": "string"}, "query": {"type": "string"}}, "required": ["source", "query"]},
    )
    valid_empty = _runtime_output("search_worker")
    valid_empty.update({"candidates": [], "work_item_id": "usenix-catalog-orchestration"})
    model = FakeModel([
        {"tool_calls": [{"name": "search_paper_catalog", "arguments": {"source": "usenix", "query": "supply chain"}}]},
        {"output_json": valid_empty},
    ])
    skill = _runtime_skill("search_worker", ["search_paper_catalog"])
    result = ResearchAgentRunner(
        model=model,
        capability_registry=RoleCapabilityRegistry(skills=[skill], tools=[search]),
    ).run(AgentRunInput(
        "search-recover-valid-empty", "session-1", "search_worker", research_task_id="task-1", work_item_id="task:s1",
        work_item_input={"query": "supply chain", "sources": ["usenix"]}, skill_snapshot=skill, tool_snapshot=[search],
    ))
    assert result.status == "completed"
    assert result.output_json["candidates"] == ["paper-2"]


def test_search_worker_binding_is_owned_by_runtime_not_model_output():
    normalized = _canonicalize_search_worker_binding(
        {"work_item_id": "usenix-catalog-orchestration", "candidates": ["paper-1"]},
        work_item_id="task:s1",
    )
    assert normalized["work_item_id"] == "task:s1"
    assert _canonicalize_search_worker_binding(
        {"work_item_id": "other-task:s1"},
        work_item_id="task:s1",
    )["work_item_id"] == "task:s1"


def test_search_worker_normalizes_rich_candidates_to_catalog_ids():
    output = _runtime_output("search_worker")
    output.update({
        "work_item_id": "search-objects",
        "candidates": [
            {"catalog_paper_id": "paper-1", "title": "Paper 1"},
            {"catalog_paper_id": "paper-1", "title": "duplicate"},
            {"title": "missing id"},
        ],
    })
    result = ResearchAgentRunner(
        model=FakeModel({"output_json": output}),
        capability_registry=RoleCapabilityRegistry(skills=[_runtime_skill("search_worker")]),
    ).run(
        AgentRunInput(
            "search-normalize",
            "session-1",
            "search_worker",
            research_task_id="task-1",
            work_item_id="search-objects",
            work_item_input={"query": "supply chain"},
            skill_snapshot=_runtime_skill("search_worker"),
        )
    )
    assert result.status == "completed"
    assert result.output_json["candidates"] == ["paper-1"]


def test_search_worker_catalog_result_is_reinjected_without_redacting_candidate_ids():
    """A catalog URL must not erase the facts needed for Search Worker JSON."""
    search = FakeTool(
        "search_paper_catalog",
        lambda _args: {
            "ok": True,
            "result_id": "search-1",
            "output": (
                "检索完成：命中 1 篇候选论文。\n"
                "1. Supply-chain paper\n"
                "   catalog_paper_id: paper-1\n"
                "   详情页: https://www.usenix.org/conference/usenixsecurity24/presentation/paper"
            ),
        },
        parameters={
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["source", "query"],
        },
    )
    output = _runtime_output("search_worker")
    output.update({"work_item_id": "search-1", "candidates": ["paper-1"]})
    model = FakeModel([
        {"tool_calls": [{"name": "search_paper_catalog", "arguments": {"source": "usenix", "query": "supply chain"}}]},
        {"content": "```json\n" + json.dumps(output, ensure_ascii=False) + "\n```"},
    ])
    registry = RoleCapabilityRegistry(
        skills=[_runtime_skill("search_worker", ["search_paper_catalog"])],
        tools=[search],
    )

    result = ResearchAgentRunner(model=model, capability_registry=registry).run(
        AgentRunInput(
            "search-run-catalog-reinjection",
            "session-1",
            "search_worker",
            research_task_id="task-1",
            work_item_id="search-1",
            work_item_input={"query": "supply chain"},
            skill_snapshot=_runtime_skill("search_worker", ["search_paper_catalog"]),
            tool_snapshot=[search],
        )
    )

    assert result.status == "completed"
    assert result.output_json["candidates"] == ["paper-1"]
    assert search.calls == [{"source": "usenix", "query": "supply chain"}]
    tool_result = result.tool_results[0]
    assert "https://" not in str(tool_result)
    assert tool_result["catalog_paper_ids"] == ["paper-1"]
    assert "paper-1" in tool_result["summary"]
    assert model.calls[1][0]["tool_results"][0]["catalog_paper_ids"] == ["paper-1"]


def test_search_worker_catalog_evidence_view_is_bounded_to_real_tool_facts():
    output = {"candidates": ["paper-1", "paper-2"]}
    view = _catalog_evidence_view(
        output,
        [
            {
                "name": "search_paper_catalog",
                "status": "ok",
                "catalog_paper_ids": ["paper-1", "paper-3"],
                "summary": "1. Supply-chain paper\n   catalog_paper_id: paper-1\n   详情页: [redacted-url]",
            },
            {
                "name": "fetch_paper_detail",
                "status": "ok",
                "summary": "must not cross the Search→Evaluator boundary",
            },
        ],
    )
    assert view == [
        {
            "candidate_ids": ["paper-1"],
            "evidence_refs": ["catalog:paper-1"],
            "summary": "1. Supply-chain paper\n   catalog_paper_id: paper-1\n   详情页: [redacted-url]",
        }
    ]
    assert "paper-3" not in json.dumps(view, ensure_ascii=False)
    assert "https://" not in json.dumps(view, ensure_ascii=False)


def test_catalog_metadata_is_carried_only_from_sanitized_search_facts():
    summary = (
        "检索完成：命中 1 篇候选论文。\n"
        "1. Supply-chain defenses\n"
        "   catalog_paper_id: paper-1\n"
        "   摘要: A bounded defense abstract.\n"
        "   关键词: supply chain, defense\n"
        "   详情页: https://www.usenix.org/private/detail"
    )
    metadata = _safe_catalog_metadata(summary)
    assert metadata == [{
        "title": "Supply-chain defenses",
        "candidate_id": "paper-1",
        "abstract": "A bounded defense abstract.",
        "keywords": ["supply chain", "defense"],
    }]
    view = _catalog_evidence_view(
        {"candidates": ["paper-1"]},
        [{
            "name": "search_paper_catalog", "status": "ok",
            "catalog_paper_ids": ["paper-1"], "summary": summary,
            "catalog_metadata": metadata,
        }],
    )
    assert view[0]["catalog_metadata"][0]["title"] == "Supply-chain defenses"
    assert "https://" not in json.dumps(view, ensure_ascii=False)


def test_search_worker_work_item_allowlist_can_only_narrow_approved_tools():
    search = FakeTool(
        "search_paper_catalog",
        parameters={"type": "object", "properties": {"source": {"type": "string"}}},
    )
    detail = FakeTool(
        "fetch_paper_detail",
        parameters={"type": "object", "properties": {"url": {"type": "string"}}},
    )
    model = FakeModel({
        "tool_calls": [{"name": "fetch_paper_detail", "arguments": {"url": "https://www.usenix.org/conference/usenixsecurity24/presentation/paper"}}]
    })
    registry = RoleCapabilityRegistry(
        skills=[_runtime_skill("search_worker", ["search_paper_catalog", "fetch_paper_detail"])],
        tools=[search, detail],
    )

    result = ResearchAgentRunner(model=model, capability_registry=registry).run(
        AgentRunInput(
            "search-run-narrowed",
            "session-1",
            "search_worker",
            research_task_id="task-1",
            work_item_id="search-1",
            work_item_input={"allowed_tools": ["search_paper_catalog"]},
            skill_snapshot=_runtime_skill("search_worker", ["search_paper_catalog", "fetch_paper_detail"]),
            tool_snapshot=[search, detail],
        )
    )

    assert result.status == "failed"
    assert result.error_code == "CAPABILITY_NOT_AUTHORIZED"
    assert detail.calls == []
