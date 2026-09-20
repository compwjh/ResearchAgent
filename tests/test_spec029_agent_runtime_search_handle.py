"""Spec029 Task06: AgentRuntime catalog handle handoff contracts."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from backend.app.memory.repository import MemoryRepository
from backend.app.research.application.agent_runtime import (
    AgentRunInput,
    AgentRunOutput,
    FakeModel,
    FakeTool,
    ResearchAgentRunner,
    RoleCapabilityRegistry,
)
from backend.app.research.application.orchestrator import Orchestrator
from backend.app.research.domain.models import ResearchSession, ResearchTask
from backend.app.research.infrastructure.research_store import ResearchStore
from backend.app.skills.tool_executor import DispatchResult


def _skill(tools):
    return {
        "name": "usenix-catalog-orchestration",
        "schema_version": "1",
        "content_hash": "skill-hash",
        "source_ref": "skill:usenix-catalog-orchestration",
        "enabled": True,
        "tools": [tool if isinstance(tool, str) else tool.name for tool in tools],
    }


def _output():
    return {
        "schema_version": "runtime-v1",
        "safe_summary": {},
        "source_refs": [],
        "work_item_id": "search-1",
        "queries": ["supply chain"],
        "source": "usenix",
        "candidates": ["paper-1"],
        "refresh_diagnostics": {},
    }


def _search_tool(value):
    return FakeTool(
        "search_paper_catalog",
        lambda _args: value,
        parameters={
            "type": "object",
            "properties": {"source": {"type": "string"}, "query": {"type": "string"}},
            "required": ["source", "query"],
        },
    )


def test_runtime_preserves_structured_catalog_handle_through_summary_and_output():
    handle = "server-search-029"
    search = _search_tool(DispatchResult(ok=True, name="search_paper_catalog", output="catalog_paper_id: paper-1", search_id=handle))
    output = _output()
    model = FakeModel([
        {"tool_calls": [{"name": "search_paper_catalog", "arguments": {"source": "usenix", "query": "supply chain"}}]},
        {"output_json": output},
    ])
    skill = _skill([search])

    result = ResearchAgentRunner(
        model=model,
        capability_registry=RoleCapabilityRegistry(skills=[skill], tools=[search]),
    ).run(AgentRunInput(
        "search-handle-runtime", "session-1", "search_worker",
        research_task_id="task-1", work_item_id="search-1",
        work_item_input={"query": "supply chain"}, skill_snapshot=skill, tool_snapshot=[search],
    ))

    assert result.status == "completed"
    assert result.tool_results[0]["search_id"] == handle
    assert result.tool_results[0]["source_refs"] == [f"search:{handle}"]
    assert result.output_json["search_id"] == handle
    assert result.output_json["source_refs"] == [f"search:{handle}"]


def test_runtime_recovery_keeps_catalog_handle_and_rejects_url_handle():
    handle = "server-search-029"
    valid = _search_tool({
        "ok": True,
        "output": "检索完成：\n1. Paper\n   catalog_paper_id: paper-1",
        "search_id": handle,
    })
    skill = _skill([valid])
    result = ResearchAgentRunner(
        model=FakeModel([
            {"tool_calls": [{"name": "search_paper_catalog", "arguments": {"source": "usenix", "query": "supply chain"}}]},
            {"output_json": {}},
        ]),
        capability_registry=RoleCapabilityRegistry(skills=[skill], tools=[valid]),
    ).run(AgentRunInput(
        "search-handle-recovery", "session-1", "search_worker",
        research_task_id="task-1", work_item_id="search-1",
        work_item_input={"query": "supply chain"}, skill_snapshot=skill, tool_snapshot=[valid],
    ))
    assert result.status == "completed"
    assert result.output_json["search_id"] == handle
    assert result.output_json["source_refs"] == [f"search:{handle}"]

    invalid = _search_tool({
        "ok": True,
        "output": "catalog_paper_id: paper-1",
        "search_id": "https://attacker.invalid/search",
    })
    invalid_skill = _skill([invalid])
    invalid_result = ResearchAgentRunner(
        model=FakeModel([
            {"tool_calls": [{"name": "search_paper_catalog", "arguments": {"source": "usenix", "query": "supply chain"}}]},
            {"output_json": {}},
        ]),
        capability_registry=RoleCapabilityRegistry(skills=[invalid_skill], tools=[invalid]),
    ).run(AgentRunInput(
        "search-handle-invalid", "session-1", "search_worker",
        research_task_id="task-1", work_item_id="search-1",
        work_item_input={"query": "supply chain"}, skill_snapshot=invalid_skill, tool_snapshot=[invalid],
    ))
    assert invalid_result.status == "completed"
    assert "search_id" not in invalid_result.tool_results[0]
    assert "search_id" not in invalid_result.output_json


def test_orchestrator_persists_runtime_catalog_handle_on_task(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, _assistant = memory.create_conversation_messages(
        "owner", "research goal", None, "model", "normal"
    )
    session = ResearchSession(
        uuid.uuid4().hex, "owner", conversation.conversation_id, user.message_id,
        uuid.uuid4().hex, "intake_pending",
    )
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_session(session, memory_repository=memory)
    task_id = uuid.uuid4().hex
    store.create_task(ResearchTask(
        research_task_id=task_id, owner_id="owner", conversation_id=conversation.conversation_id,
        goal="research goal", language="en", quality_profile="balanced", review_plan_first=False,
        target_paper_count=1, soft_budget_seconds=60, status="draft", current_plan_version=1,
        created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
    ))
    store.update_session_links(session.research_session_id, "owner", research_task_id=task_id)
    handle = "server-search-orchestrator"
    class _Runner:
        event_sink = None

        def run(self, run_input):
            output = _output()
            output.update({
                "work_item_id": run_input.work_item_id,
                "search_id": handle,
                "source_refs": [f"search:{handle}"],
            })
            return AgentRunOutput(
                "completed", output_json=output, output_hash="hash", agent_run_id=run_input.agent_run_id,
            )

    runner = _Runner()
    planner = SimpleNamespace(build_plan=lambda **_: SimpleNamespace(
        facets=("systems",), planner_model="fake", rationale_summary="fake",
        work_items=({
            "id": "s1", "task_type": "search_catalog", "role": "search-worker",
            "depends_on": [], "params": {"query": "research goal"},
        },),
    ))

    Orchestrator(store=store, search_adapter=SimpleNamespace(), planner=planner, agent_runner=runner).run(task_id, "owner")

    assert store.get_task(task_id, "owner").search_id == handle
