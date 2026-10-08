"""WorkItem terminal completion happens only after durable output write-back."""

from __future__ import annotations

import json
import re
import uuid
from types import SimpleNamespace

import pytest

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
from backend.app.research.domain.models import ResearchSession, ResearchTask, ResearchWorkItem
from backend.app.research.infrastructure.research_store import ResearchStore
from backend.app.skills.tool_executor import DispatchResult


def _id() -> str:
    return uuid.uuid4().hex


def _skill(role: str) -> dict:
    names = {
        "search_worker": "usenix-catalog-orchestration",
        "paper_evaluator": "research-paper-evaluation",
    }
    name = names[role]
    return {
        "name": name,
        "schema_version": "1",
        "content_hash": "skill-hash",
        "source_ref": f"skill:{name}",
        "enabled": True,
        "tools": [],
    }


def _store_with_item(tmp_path, *, role: str, input_json: str = "{}", create_item: bool = True):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, assistant = memory.create_conversation_messages(
        "owner", "goal", None, "model", "normal"
    )
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = ResearchTask(
        _id(), "owner", conversation.conversation_id, "goal", "en",
        "balanced", False, 1, 60, "draft", 1,
        "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z",
    )
    store.create_task(task)
    session = ResearchSession(
        _id(), "owner", conversation.conversation_id, user.message_id,
        _id(), "running", research_task_id=task.research_task_id,
        activity_message_id=assistant.message_id,
    )
    store.create_session(session, memory_repository=memory)
    store.update_session_links(session.research_session_id, "owner", research_task_id=task.research_task_id)
    work_item_id = f"{task.research_task_id}:e1"
    now = "2026-01-01T00:00:00Z"
    if create_item:
        store.create_work_items(task.research_task_id, [ResearchWorkItem(
            work_item_id, task.research_task_id, 1, "evaluate_papers", "paper-evaluator", "[]",
            input_json, "queued", 0, now, now,
        )])
    return memory, store, task, session, work_item_id


def _evaluator_output(work_item_id: str, *, candidate_id: str = "paper-1") -> dict:
    return {
        "schema_version": "paper-evaluation-v1",
        "safe_summary": {},
        "source_refs": [],
        "work_item_id": work_item_id,
        "candidate_id": candidate_id,
        "relevance_score": 0.9,
        "keep": True,
        "reason": "bounded catalog evidence",
        "evidence_refs": [f"catalog:{candidate_id}"],
    }


def test_agent_runner_leaves_work_item_open_until_orchestrator_writeback(tmp_path):
    _memory, store, task, session, work_item_id = _store_with_item(tmp_path, role="paper_evaluator")
    skill = _skill("paper_evaluator")
    runner = ResearchAgentRunner(
        store=store,
        model=FakeModel({"output_json": _evaluator_output(work_item_id)}),
        capability_registry=RoleCapabilityRegistry(skills=[skill]),
    )

    result = runner.run(AgentRunInput(
        f"{work_item_id}:run-1", session.research_session_id, "paper_evaluator",
        research_task_id=task.research_task_id, work_item_id=work_item_id,
        owner_id="owner", work_item_input={}, skill_snapshot=skill,
    ))

    assert result.status == "completed"
    item = store.get_work_item(work_item_id)
    assert item is not None
    assert item.status == "running"
    assert item.output_json is None


class _Probe:
    def arbitrate(self, _task_id, requested):
        return max(1, requested), None

    def release(self, _task_id):
        return None


class _MultiRoleModel:
    def invoke(self, context, _tools=()):
        role = context["role"]
        if role == "search_worker":
            return {"output_json": {
                "schema_version": "runtime-v1",
                "safe_summary": {},
                "source_refs": [],
                "work_item_id": "model-owned",
                "queries": ["goal"],
                "source": "usenix",
                "candidates": ["paper-1"],
                "refresh_diagnostics": {},
            }}
        return {"output_json": _evaluator_output("model-owned", candidate_id="paper-not-recalled")}


def _planner():
    return SimpleNamespace(build_plan=lambda **_: SimpleNamespace(
        facets=("systems",), planner_model="fake", rationale_summary="fake",
        work_items=(
            {"id": "s1", "task_type": "search_catalog", "role": "search-worker", "depends_on": [],
             "params": {"query": "goal", "source_ids": ["usenix"], "sources": ["usenix"]}},
            {"id": "e1", "task_type": "evaluate_papers", "role": "paper-evaluator", "depends_on": ["s1"],
             "params": {}},
        ),
    ))


def _find(items, suffix):
    for item in items:
        if re.split(r"[:-]", item.work_item_id)[-1] == suffix:
            return item
    raise AssertionError(f"work item {suffix} not found")


def test_semantic_invalid_output_is_failed_with_durable_envelope(tmp_path):
    _memory, store, task, _session, _work_item_id = _store_with_item(
        tmp_path, role="paper_evaluator", create_item=False,
    )
    registry = RoleCapabilityRegistry(skills=[_skill("search_worker"), _skill("paper_evaluator")])
    runner = ResearchAgentRunner(store=store, model=_MultiRoleModel(), capability_registry=registry)
    result = Orchestrator(
        store=store, planner=_planner(), agent_runner=runner, probe=_Probe(), memory_repository=None,
    ).run(task.research_task_id, "owner")

    evaluator = _find(store.list_work_items(task.research_task_id), "e1")
    assert result.status == "partial"
    assert evaluator.status == "failed"
    assert evaluator.error_code == "EVALUATOR_EVIDENCE_OUT_OF_SCOPE"
    assert evaluator.output_json is not None
    assert json.loads(evaluator.output_json)["status"] == "completed"


class _TerminalWriteFailureStore(ResearchStore):
    def __init__(self, path):
        super().__init__(path)
        self.fail_terminal_write = False

    def update_work_item_status(self, work_item_id, next_status, **kwargs):
        if self.fail_terminal_write and kwargs.get("output_json") is not None:
            raise RuntimeError("terminal output write failed")
        return super().update_work_item_status(work_item_id, next_status, **kwargs)


class _CompletedSearchRunner:
    event_sink = None

    def run(self, run_input):
        return AgentRunOutput(
            "completed",
            output_json={
                "schema_version": "runtime-v1",
                "safe_summary": {},
                "source_refs": [],
                "work_item_id": run_input.work_item_id,
                "queries": ["goal"],
                "source": "usenix",
                "candidates": ["paper-1"],
                "refresh_diagnostics": {},
            },
            output_hash="hash",
            agent_run_id=run_input.agent_run_id,
        )


class _NullCompletedSearchRunner:
    event_sink = None

    def run(self, run_input):
        return AgentRunOutput(
            "completed",
            output_json=None,
            output_hash="",
            agent_run_id=run_input.agent_run_id,
        )


def _single_search_task(tmp_path, store_cls=ResearchStore):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, assistant = memory.create_conversation_messages(
        "owner", "goal", None, "model", "normal"
    )
    store = store_cls(tmp_path / "research.sqlite3")
    task = ResearchTask(
        _id(), "owner", conversation.conversation_id, "goal", "en",
        "balanced", False, 1, 60, "draft", 1,
        "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z",
    )
    store.create_task(task)
    session = ResearchSession(
        _id(), "owner", conversation.conversation_id, user.message_id,
        _id(), "running", research_task_id=task.research_task_id,
        activity_message_id=assistant.message_id,
    )
    store.create_session(session, memory_repository=memory)
    store.update_session_links(session.research_session_id, "owner", research_task_id=task.research_task_id)
    return memory, store, task


def _search_planner():
    return SimpleNamespace(build_plan=lambda **_: SimpleNamespace(
        facets=("systems",), planner_model="fake", rationale_summary="fake",
        work_items=({"id": "s1", "task_type": "search_catalog", "role": "search-worker",
                     "depends_on": [], "params": {"sources": ["usenix"]}},),
    ))


def _controlled_search_recovery(_work_item_input, work_item_id):
    return {
        "schema_version": "runtime-v1",
        "safe_summary": {},
        "source_refs": ["search:trusted-search"],
        "work_item_id": work_item_id,
        "queries": ["goal"],
        "source": "usenix",
        "search_id": "trusted-search",
        "candidates": ["paper-1"],
        "refresh_diagnostics": {},
    }


def test_null_completed_agent_result_cannot_be_promoted_by_search_recovery(tmp_path, monkeypatch):
    _memory, store, task = _single_search_task(tmp_path)
    orchestrator = Orchestrator(
        store=store,
        planner=_search_planner(),
        agent_runner=_NullCompletedSearchRunner(),
        probe=_Probe(),
        memory_repository=None,
    )
    monkeypatch.setattr(orchestrator, "_recover_search_worker_output", _controlled_search_recovery)

    result = orchestrator.run(task.research_task_id, "owner")

    item = store.list_work_items(task.research_task_id)[0]
    assert result.status == "partial"
    assert result.error_code == "AGENT_OUTPUT_INVALID"
    assert item.status == "failed"
    assert item.output_json is not None
    envelope = json.loads(item.output_json)
    assert envelope["status"] == "completed"
    assert envelope["output_json"] is None


def test_valid_completed_search_result_keeps_agent_output_and_terminal_write_atomic(tmp_path, monkeypatch):
    _memory, store, task = _single_search_task(tmp_path)
    orchestrator = Orchestrator(
        store=store,
        planner=_search_planner(),
        agent_runner=_CompletedSearchRunner(),
        probe=_Probe(),
        memory_repository=None,
    )
    monkeypatch.setattr(
        orchestrator,
        "_recover_search_worker_output",
        lambda *_: (_ for _ in ()).throw(AssertionError("valid AgentRun must not use recovery")),
    )

    result = orchestrator.run(task.research_task_id, "owner")

    item = store.list_work_items(task.research_task_id)[0]
    assert result.status == "completed"
    assert item.status == "completed"
    envelope = json.loads(item.output_json)
    assert envelope["status"] == "completed"
    assert envelope["output_json"]["work_item_id"] == item.work_item_id


def test_runtime_identity_binding_survives_fresh_terminal_write_and_restart_hydration(tmp_path):
    _memory, store, task = _single_search_task(tmp_path)
    session = store.get_session_by_task(task.research_task_id, "owner")
    assert session is not None
    work_item_id = f"{task.research_task_id}:s1"
    store.create_work_items(task.research_task_id, [ResearchWorkItem(
        work_item_id, task.research_task_id, 1, "search_catalog", "search-worker", "[]",
        json.dumps({"query": "goal", "sources": ["usenix"]}), "queued", 0,
        "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z",
    )])
    search_tool = FakeTool(
        "search_paper_catalog",
        lambda _args: DispatchResult(
            ok=True, name="search_paper_catalog", output="catalog_paper_id: paper-1", search_id="trusted-search",
        ),
        parameters={
            "type": "object",
            "properties": {"source": {"type": "string"}, "query": {"type": "string"}},
            "required": ["source", "query"],
        },
    )
    skill = _skill("search_worker")
    skill["tools"] = [search_tool.name]
    runner = ResearchAgentRunner(
        store=store,
        model=FakeModel([
            {"tool_calls": [{"name": "search_paper_catalog", "arguments": {"source": "usenix", "query": "goal"}}]},
            {"output_json": {
                "schema_version": "runtime-v1", "safe_summary": {}, "source_refs": [],
                "work_item_id": "modelowned", "queries": ["goal"], "source": "usenix",
                "candidates": ["paper-1"], "refresh_diagnostics": {},
            }},
        ]),
        capability_registry=RoleCapabilityRegistry(skills=[skill], tools=[search_tool]),
    )

    result = runner.run(AgentRunInput(
        f"{work_item_id}:run-1", session.research_session_id, "search_worker",
        research_task_id=task.research_task_id, work_item_id=work_item_id,
        owner_id="owner", work_item_input={"query": "goal", "sources": ["usenix"]},
        skill_snapshot=skill, tool_snapshot=[search_tool],
    ))

    assert result.status == "completed", result.to_dict()
    assert result.output_json["work_item_id"] == work_item_id
    assert result.output_json["output_hash"] == result.output_hash
    persisted_run = store.get_agent_run(f"{work_item_id}:run-1", "owner")
    assert persisted_run is not None
    assert persisted_run.status == "completed"
    assert persisted_run.work_item_id == work_item_id
    assert persisted_run.output_hash == result.output_hash
    assert store.get_work_item(work_item_id).status == "running"
    store.update_work_item_status(
        work_item_id, "completed", output_json=json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True),
    )

    class _RestartRunner:
        event_sink = None

        def __init__(self):
            self.calls = []

        def run(self, run_input):
            self.calls.append(run_input)
            raise AssertionError("a valid persisted runtime output must hydrate without rerun")

    restarted_runner = _RestartRunner()
    restart_result = Orchestrator(
        store=store,
        planner=_search_planner(),
        agent_runner=restarted_runner,
        probe=_Probe(),
        memory_repository=None,
    )._run_agent_work_items(task=task, owner_id="owner", plan_version=1)

    assert restarted_runner.calls == []
    assert restart_result.status == "completed"
    assert store.get_work_item(work_item_id).status == "completed"


def test_terminal_output_write_failure_is_not_suppressed(tmp_path):
    _memory, store, task = _single_search_task(tmp_path, _TerminalWriteFailureStore)
    store.fail_terminal_write = True

    with pytest.raises(RuntimeError, match="terminal output write failed"):
        Orchestrator(
            store=store, planner=_search_planner(), agent_runner=_CompletedSearchRunner(),
            probe=_Probe(), memory_repository=None,
        ).run(task.research_task_id, "owner")

    item = store.list_work_items(task.research_task_id)[0]
    assert item.status == "running"
    assert item.output_json is None
