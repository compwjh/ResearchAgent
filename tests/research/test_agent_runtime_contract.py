"""Task05 Fake Runtime contracts; no Ollama/network dependency."""

import hashlib
import uuid
from threading import Event
from types import SimpleNamespace

import pytest

from backend.app.memory.repository import MemoryRepository
from backend.app.research.application.agent_runtime import (
    AgentRunInput,
    AgentRuntimeError,
    BudgetSnapshot,
    FakeModel,
    FakeTool,
    ResearchAgentRunner,
    RoleCapabilityRegistry,
    _OllamaRunnerAdapter,
)
from backend.app.research.application.approval_service import PlanApprovalService
from backend.app.research.application.orchestrator import Orchestrator
from backend.app.research.application.report_synthesis import report_output_hash
from backend.app.research.domain.models import AgentCheckpoint, ResearchSession, ResearchTask
from backend.app.research.infrastructure.research_store import AgentRunWriteDiscarded, ResearchStore
from backend.app.skills.models import ToolEntry
from backend.app.skills.tool_executor import DispatchResult


def _skill(role: str, tools=()) -> dict:
    names = {
        "planner": "research-plan-authoring",
        "search_worker": "usenix-catalog-orchestration",
        "paper_evaluator": "research-paper-evaluation",
        "research_critic": "research-coverage-review",
        "synthesizer": "research-report-synthesis",
    }
    return {"name": names[role], "schema_version": "1", "content_hash": "skill-hash", "source_ref": f"skill:{names[role]}", "enabled": True, "tools": list(tools)}


def _output(role: str) -> dict:
    base = {"schema_version": "runtime-v1", "safe_summary": {}, "source_refs": []}
    required = {
        "planner": {"plan_version": 1, "objective": "o", "scope": {}, "work_items": [], "capabilities": [], "budget": {}, "report_structure": {}},
        "search_worker": {"work_item_id": "w", "queries": ["q"], "source": "usenix", "candidates": [], "refresh_diagnostics": {}},
        "paper_evaluator": {"candidate_id": "c", "relevance_score": 1, "keep": True, "reason": "r", "evidence_refs": []},
        "research_critic": {"coverage": {}, "gaps": [], "recommendations": [], "bounded_replan": False},
        "synthesizer": {"report_version": 1, "sections": [], "citation_manifest": [], "artifact_ids": []},
    }[role]
    return {**base, **required}


def _runner(role="planner", model=None, tools=()):
    model = model or FakeModel({"output_json": _output(role)})
    registry = RoleCapabilityRegistry(skills=[_skill(role, [getattr(tool, "name", "") for tool in tools])], tools=list(tools))
    return ResearchAgentRunner(model=model, capability_registry=registry)


def _matrix_context() -> dict:
    abstract = "A bounded catalog abstract for a supported comparison claim."
    digest = hashlib.sha256(abstract.encode("utf-8")).hexdigest()
    return {
        "schema_version": "evidence-report-v1",
        "plan_version": 1,
        "dimensions": [{
            "dimension_id": "facet-1",
            "label": "Privacy",
            "definition": "Approved research-scope comparison dimension.",
            "display_order": 0,
        }],
        "candidates": [{
            "paper_id": "paper-a",
            "catalog_snapshot_id": "search-a",
            "title": "Paper A",
            "abstract": abstract,
            "abstract_digest": digest,
        }],
        "allowed_paper_ids": ["paper-a"],
    }


def _synthesizer_output(*, evidence_matrix: dict | None = None) -> dict:
    output = _output("synthesizer")
    output.update({
        "sections": [{
            "heading": "Bounded comparison",
            "candidate_ids": ["paper-a"],
            "summary": "The supplied catalog abstract supports the comparison.",
        }],
        "citation_manifest": [{"citation_ref": "catalog:paper-a", "candidate_id": "paper-a"}],
        "source_refs": ["catalog:paper-a"],
    })
    if evidence_matrix is not None:
        output["evidence_matrix"] = evidence_matrix
    output["output_hash"] = report_output_hash(output)
    return output


def _matrix_output() -> dict:
    context = _matrix_context()
    digest = context["candidates"][0]["abstract_digest"]
    return {
        "schema_version": "evidence-report-v1",
        "plan_version": 1,
        "dimensions": context["dimensions"],
        "claims": [{
            "claim_id": "claim-1",
            "topic": "Privacy",
            "statement": "The supplied abstract supports a privacy boundary.",
            "confidence": "medium",
            "status": "supported",
            "evidence_ids": ["evidence-1"],
        }],
        "evidence": [{
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
        }],
        "cells": [{
            "claim_id": "claim-1",
            "paper_id": "paper-a",
            "dimension_id": "facet-1",
            "relation": "supports",
            "summary": "The supplied abstract supports the claim.",
            "evidence_ids": ["evidence-1"],
        }],
    }


def _synthesizer_input(*, matrix_context: dict | None) -> AgentRunInput:
    work_item_input = {"validated_candidates": [{"candidate_id": "paper-a"}]}
    if matrix_context is not None:
        work_item_input["matrix_context"] = matrix_context
    return AgentRunInput(
        "matrix-run",
        "session-1",
        "synthesizer",
        work_item_input=work_item_input,
        skill_snapshot=_skill("synthesizer"),
        research_task_id="task-1",
        work_item_id="work-1",
    )


def test_fake_output_is_structured_and_checkpointed():
    result = _runner().run(AgentRunInput("run-1", "session-1", "planner", skill_snapshot=_skill("planner")))
    assert result.status == "completed"
    assert result.output_json["schema_version"] == "runtime-v1"
    assert len(result.output_hash) == 64
    assert result.checkpoint_ref.startswith("checkpoint:run-1:")
    assert len(result.checkpoint_hash) == 64
    assert result.usage == {"model_loops": 1, "tool_calls": 0}


def test_invalid_output_retries_at_most_four_attempts():
    model = FakeModel([{"output_json": {}}] * 4)
    result = _runner(model=model).run(AgentRunInput("run-2", "session-1", "planner", skill_snapshot=_skill("planner")))
    assert result.status == "failed"
    assert result.error_code == "AGENT_OUTPUT_INVALID"
    assert result.usage["model_loops"] == 4
    assert len(model.calls) == 4


def test_synthesizer_requires_matrix_when_context_is_present_and_retries_with_feedback():
    missing_matrix = {"output_json": _synthesizer_output()}
    legal_matrix = {"output_json": _synthesizer_output(evidence_matrix=_matrix_output())}
    model = FakeModel([missing_matrix, legal_matrix])

    result = _runner(role="synthesizer", model=model).run(
        _synthesizer_input(matrix_context=_matrix_context())
    )

    assert result.status == "completed"
    assert result.output_json is not None
    assert result.output_json["evidence_matrix"]["schema_version"] == "evidence-report-v1"
    assert len(model.calls) == 2
    feedback = model.calls[1][0]["validation_feedback"]
    assert feedback["code"] == "MATRIX_NOT_READY"
    assert "evidence_matrix" in feedback["required_fields"]
    assert "claims" in feedback["shape"]


def test_synthesizer_matrix_requirement_exhausts_as_bounded_failure():
    model = FakeModel([{"output_json": _synthesizer_output()}] * 4)

    result = _runner(role="synthesizer", model=model).run(
        _synthesizer_input(matrix_context=_matrix_context())
    )

    assert result.status == "failed"
    assert result.error_code == "MATRIX_NOT_READY"
    assert result.usage["model_loops"] == 4
    assert len(model.calls) == 4
    assert all(call[0]["validation_feedback"]["code"] == "MATRIX_NOT_READY" for call in model.calls[1:])


def test_synthesizer_without_matrix_context_keeps_optional_extension_compatibility():
    model = FakeModel({"output_json": _synthesizer_output()})

    result = _runner(role="synthesizer", model=model).run(
        _synthesizer_input(matrix_context=None)
    )

    assert result.status == "completed"
    assert len(model.calls) == 1
    assert "validation_feedback" not in model.calls[0][0]


def test_ollama_synthesizer_prompt_exposes_internal_matrix_shape_only_with_context():
    captured = {}

    class Chat:
        def invoke(self, messages):
            captured["messages"] = messages
            return SimpleNamespace(content="{}", tool_calls=[])

    adapter = _OllamaRunnerAdapter(Chat(), model_name="test-model", effort="off")
    adapter.invoke({
        "role": "synthesizer",
        "work_item_input": {"matrix_context": _matrix_context()},
    })

    contract = captured["messages"][0]["content"]
    assert '"evidence_matrix"' in contract
    assert '"schema_version":"evidence-report-v1"' in contract
    assert '"claims"' in contract and '"evidence"' in contract and '"cells"' in contract


def test_invalid_tool_batch_executes_nothing():
    first = FakeTool("read_a")
    second = FakeTool("read_b")
    model = FakeModel({"tool_calls": [{"name": "read_a", "arguments": {}}, {"name": "unknown", "arguments": {}}]})
    runner = _runner(model=model, tools=[first, second])
    result = runner.run(AgentRunInput("run-3", "session-1", "planner", skill_snapshot=_skill("planner", ["read_a", "read_b"]), tool_snapshot=[first, second]))
    assert result.status == "failed"
    assert result.error_code == "CAPABILITY_NOT_AUTHORIZED"
    assert first.calls == [] and second.calls == []


def test_tool_results_are_safe_and_counted():
    tool = FakeTool("read_a", lambda _args: {"result_id": "r1", "content": "https://secret.invalid Authorization: token"})
    model = FakeModel([{"tool_calls": [{"name": "read_a", "arguments": {}}]}, {"output_json": _output("planner")}])
    result = _runner(model=model, tools=[tool]).run(AgentRunInput("run-4", "session-1", "planner", skill_snapshot=_skill("planner", ["read_a"]), tool_snapshot=[tool]))
    assert result.status == "completed"
    assert result.usage["tool_calls"] == 1
    assert "https://" not in str(result.tool_results)
    assert result.tool_results[0]["result_id"] == "r1"


def test_cancel_barrier_rejects_late_model_result():
    token = Event()
    model = FakeModel({"output_json": _output("planner")})
    token.set()
    result = _runner(model=model).run(AgentRunInput("run-5", "session-1", "planner", skill_snapshot=_skill("planner"), cancellation_token=token))
    assert result.status == "cancelled"
    assert result.error_code == "CANCELLED"
    assert model.calls == []


def test_budget_limit_is_stable_and_has_followup_signal():
    result = _runner().run(AgentRunInput("run-6", "session-1", "planner", skill_snapshot=_skill("planner"), budget_snapshot=BudgetSnapshot(max_model_loops=0)))
    assert result.status == "limit_reached"
    assert result.error_code == "MODEL_LOOP_LIMIT_REACHED"
    assert result.approval_signal["kind"] == "resource_extension"


def test_store_binding_and_counter_checkpoint_contract(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, _ = memory.create_conversation_messages("owner-a", "q", None, "m", "normal")
    session = ResearchSession(uuid.uuid4().hex, "owner-a", conversation.conversation_id, user.message_id, uuid.uuid4().hex, "intake_pending")
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_session(session, memory_repository=memory)
    runner = ResearchAgentRunner(store=store, model=FakeModel({"output_json": _output("planner")}), capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]))
    result = runner.run(AgentRunInput(uuid.uuid4().hex, session.research_session_id, "planner", skill_snapshot=_skill("planner"), owner_id="owner-a"))
    assert result.status == "completed"
    # Provider metadata intentionally contains no internal prompt or identity.
    assert result.checkpoint_hash


def test_nested_unsafe_output_is_rejected_before_checkpoint():
    bad = _output("planner")
    bad["safe_summary"] = {"nested": {"prompt": "secret"}}
    result = _runner(model=FakeModel({"output_json": bad})).run(AgentRunInput("run-7", "session-1", "planner", skill_snapshot=_skill("planner")))
    assert result.status == "failed" and result.error_code == "AGENT_OUTPUT_INVALID"
    assert result.checkpoint_ref is None


def test_tool_exception_is_stable_failure():
    tool = FakeTool("read_a", lambda _args: (_ for _ in ()).throw(RuntimeError("boom")))
    model = FakeModel({"tool_calls": [{"name": "read_a", "arguments": {}}]})
    result = _runner(model=model, tools=[tool]).run(AgentRunInput("run-8", "session-1", "planner", skill_snapshot=_skill("planner", ["read_a"]), tool_snapshot=[tool]))
    assert result.status == "failed" and result.error_code == "TOOL_EXECUTION_FAILED"
    assert result.tool_results[0]["error_code"] == "TOOL_EXECUTION_FAILED"


def test_budget_caps_are_not_caller_raiseable():
    result = _runner().run(AgentRunInput("run-9", "session-1", "planner", skill_snapshot=_skill("planner"), budget_snapshot={"max_model_loops": 500, "max_tool_calls": 500, "task_max_model_loops": 500, "task_max_tool_calls": 500, "max_seconds": 999999, "extensions": 3}))
    assert result.status == "completed"
    assert result.usage["model_loops"] == 1


def test_checkpoint_survives_runner_instance_restart(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, _ = memory.create_conversation_messages("owner-a", "q", None, "m", "normal")
    session = ResearchSession(uuid.uuid4().hex, "owner-a", conversation.conversation_id, user.message_id, uuid.uuid4().hex, "intake_pending")
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_session(session, memory_repository=memory)
    first = ResearchAgentRunner(store=store, model=FakeModel({"output_json": _output("planner")}), capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]))
    original_id = uuid.uuid4().hex
    saved = first.run(AgentRunInput(original_id, session.research_session_id, "planner", skill_snapshot=_skill("planner"), owner_id="owner-a"))
    assert store.get_agent_checkpoint(saved.checkpoint_ref, "owner-a").content_hash == saved.checkpoint_hash


def test_resource_lease_spans_model_and_tool_lifecycle():
    class Probe:
        def __init__(self):
            self.active = 0
            self.max_active = 0
        def arbitrate(self, _task, _requested):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            return 1, None
        def release(self, _task):
            self.active -= 1
    probe = Probe()
    tool = FakeTool("read_a")
    result = ResearchAgentRunner(model=FakeModel([{"tool_calls": [{"name": "read_a", "arguments": {}}]}, {"output_json": _output("planner")}]), capability_registry=RoleCapabilityRegistry(skills=[_skill("planner", ["read_a"])], tools=[tool]), resource_probe=probe).run(AgentRunInput("run-10", "session-1", "planner", skill_snapshot=_skill("planner", ["read_a"]), tool_snapshot=[tool], research_task_id="task-1", work_item_id="work-1"))
    assert result.status == "completed" and probe.active == 0 and probe.max_active == 1


def test_router_selected_model_is_the_model_factory_input():
    class Router:
        def __init__(self): self.tiers = []
        def resolve(self, *, role, tier):
            self.tiers.append((role, tier))
            return type("Choice", (), {"model": f"{tier}-model"})()
    router = Router()
    used = []
    def factory(model, effort):
        used.append((model, effort))
        return FakeModel({"output_json": _output("planner")})
    result = ResearchAgentRunner(model_factory=factory, model_router=router, capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")])).run(AgentRunInput("run-11", "session-1", "planner", skill_snapshot=_skill("planner"), reasoning_effort="high"))
    assert result.status == "completed" and used == [("fast-model", "high")]
    assert result.model_metadata["model"] == "fast-model"


def test_caller_cannot_forge_registered_tool_schema_or_skill_snapshot():
    tool = FakeTool("read_a", parameters={"type": "object", "properties": {"q": {"type": "string"}}})
    registry = RoleCapabilityRegistry(skills=[_skill("planner", ["read_a"])], tools=[tool])
    forged = {"name": "read_a", "parameters": {"type": "object", "properties": {}}, "parameters_hash": "x", "enabled": True}
    runner = ResearchAgentRunner(model=FakeModel({"output_json": _output("planner")}), capability_registry=registry)
    with pytest.raises(Exception, match="caller schema"):
        runner.run(AgentRunInput("run-12", "session-1", "planner", skill_snapshot=_skill("planner", ["read_a"]), tool_snapshot=[forged]))


def test_explicit_skill_snapshot_without_approved_registry_fails_closed():
    runner = ResearchAgentRunner(model=FakeModel({"output_json": _output("planner")}), capability_registry=RoleCapabilityRegistry())
    with pytest.raises(AgentRuntimeError, match="approved skill snapshot"):
        runner.run(AgentRunInput("run-13", "session-1", "planner", skill_snapshot=_skill("planner")))


def test_plan_approval_snapshot_envelope_adapts_existing_registries():
    tool = FakeTool("read_a")
    tool.enabled = True
    tool.entry = "test.registry.read_a"
    detail = SimpleNamespace(
        name="research-plan-authoring", description="planner", tools=["read_a"],
        body="approved skill body", enabled=True,
    )
    skill_registry = SimpleNamespace(list_skills=lambda: [detail], get_skill=lambda _name: detail)
    tool_registry = SimpleNamespace(list_tools=lambda: [tool], get_tool=lambda _name: tool)
    approved = PlanApprovalService(
        store=None, skill_registry=skill_registry, tool_registry=tool_registry
    )._normalize_capabilities([{"skill": detail.name, "tools": [tool.name]}])[0]
    registry = RoleCapabilityRegistry(skill_registry=skill_registry, tool_registry=tool_registry)
    result = ResearchAgentRunner(
        model=FakeModel({"output_json": _output("planner")}), capability_registry=registry
    ).run(AgentRunInput("run-13b", "session-1", "planner", skill_snapshot=approved))
    assert result.status == "completed"
    assert result.model_metadata["provider"] == "injected"


def test_production_runner_uses_existing_default_dispatch(monkeypatch):
    tool = ToolEntry("read_a", "read", enabled=True, entry="test.registry.read_a", parameters={"type": "object", "properties": {}})
    calls = []
    def dispatch(name, args):
        calls.append((name, args))
        return DispatchResult(ok=True, name=name, output="safe")
    monkeypatch.setattr("backend.app.skills.tool_dispatch.build_default_dispatch", lambda: dispatch)
    registry = RoleCapabilityRegistry(skills=[_skill("planner", ["read_a"])], tools=[tool])
    result = ResearchAgentRunner(
        model=FakeModel([{"tool_calls": [{"name": "read_a", "arguments": {}}]}, {"output_json": _output("planner")}]),
        capability_registry=registry,
    ).run(AgentRunInput("run-dispatch", "session-1", "planner", skill_snapshot=_skill("planner", ["read_a"]), tool_snapshot=[tool]))
    assert result.status == "completed" and calls == [("read_a", {})]


def test_lease_is_released_when_checkpoint_store_fails():
    class Probe:
        def __init__(self):
            self.active = 0
        def arbitrate(self, _task, _requested):
            self.active += 1
            return 1, None
        def release(self, _task):
            self.active -= 1
    class BrokenStore:
        def get_agent_checkpoint(self, _ref, _owner):
            raise OSError("store offline")
    probe = Probe()
    runner = ResearchAgentRunner(
        store=BrokenStore(), model=FakeModel({"output_json": _output("planner")} ),
        capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]), resource_probe=probe,
    )
    with pytest.raises(AgentRuntimeError, match="checkpoint lookup failed"):
        runner.run(AgentRunInput("run-lease-error", "session-1", "planner", skill_snapshot=_skill("planner"), owner_id="owner-a", research_task_id="task-1", work_item_id="work-1", checkpoint_ref="checkpoint:x", checkpoint_hash="0" * 64))
    assert probe.active == 0


def test_ollama_adapter_and_unique_orchestrator_runner_seam(monkeypatch):
    import backend.app.platform.ollama as ollama
    captured = {}
    class Chat:
        def bind_tools(self, schemas):
            captured["schemas"] = schemas
            return self
        def invoke(self, _messages):
            return SimpleNamespace(content='{"schema_version":"runtime-v1"}', tool_calls=[])
    monkeypatch.setattr(ollama, "resolve_reasoning_effort", lambda model, effort: SimpleNamespace(provider_value=False))
    monkeypatch.setattr(ollama, "create_chat_model", lambda model, reasoning: captured.update(model=model, reasoning=reasoning) or Chat())
    from backend.app.research.application.agent_runtime import _ollama_model_factory
    adapter = _ollama_model_factory("selected-model", "off")
    assert adapter.model_name == "selected-model" and adapter.reasoning_effort == "off"
    assert captured["model"] == "selected-model" and captured["reasoning"] is False
    response = adapter.invoke({"role": "planner"}, [{"name": "read_a", "description": "read", "parameters": {"type": "object"}}])
    assert response["output_json"]["schema_version"] == "runtime-v1" and captured["schemas"][0]["function"]["name"] == "read_a"
    runner = type("Runner", (), {"run": lambda self, value: ("one-runner", value)})()
    orchestrator = Orchestrator(store=SimpleNamespace(), agent_runner=runner)
    assert orchestrator.run_agent("work-item-input") == ("one-runner", "work-item-input")


def test_fourth_extension_is_stable_limit_result():
    result = _runner().run(AgentRunInput("run-14", "session-1", "planner", skill_snapshot=_skill("planner"), budget_snapshot={"extensions": 4}))
    assert result.status == "limit_reached" and result.error_code == "TASK_MODEL_LIMIT_REACHED"


def test_approved_resource_snapshot_adds_positive_bound_increment():
    snapshot = {
        "max_model_loops": 999,
        "resource_snapshot": {
            "approved": True,
            "owner_id": "owner-a",
            "research_session_id": "session-1",
            "research_task_id": "task-1",
            "base_limits": {"max_model_loops": 120, "max_tool_calls": 480, "task_max_model_loops": 600, "task_max_tool_calls": 2400, "max_seconds": 1800},
            "increments": {"model_loops": 40, "tool_calls": 160, "task_model_loops": 40, "task_tool_calls": 160, "seconds": 1800},
            "extensions": 1,
        },
    }
    budget = BudgetSnapshot.from_value(snapshot, owner_id="owner-a", research_session_id="session-1", research_task_id="task-1")
    assert (budget.max_model_loops, budget.max_tool_calls) == (160, 640)
    assert (budget.task_max_model_loops, budget.task_max_tool_calls, budget.max_seconds) == (640, 2560, 3600)


def test_only_approved_extensions_raise_initial_budget_until_hard_caps():
    expected = {
        0: (40, 160, 160, 640, 5400),
        1: (80, 320, 320, 1280, 10800),
        2: (120, 480, 480, 1920, 16200),
        3: (160, 640, 640, 2560, 21600),
    }
    for extensions, limits in expected.items():
        budget = BudgetSnapshot.from_value({
            "max_model_loops": 9999,
            "resource_snapshot": {
                "approved": True, "owner_id": "owner-a", "research_session_id": "session-1", "research_task_id": "task-1",
                "base_limits": {"max_model_loops": 40 + extensions * 40, "max_tool_calls": 160 + extensions * 160, "task_max_model_loops": 160 + extensions * 160, "task_max_tool_calls": 640 + extensions * 640, "max_seconds": 5400 + extensions * 5400},
                "increments": {"model_loops": 0, "tool_calls": 0, "task_model_loops": 0, "task_tool_calls": 0, "seconds": 0},
                "extensions": extensions,
            },
        }, owner_id="owner-a", research_session_id="session-1", research_task_id="task-1")
        assert (budget.max_model_loops, budget.max_tool_calls, budget.task_max_model_loops, budget.task_max_tool_calls, budget.max_seconds) == limits
    with pytest.raises(AgentRuntimeError, match="extension limit"):
        BudgetSnapshot.from_value({"resource_snapshot": {"approved": True, "owner_id": "owner-a", "research_session_id": "session-1", "research_task_id": "task-1", "extensions": 4}}, owner_id="owner-a", research_session_id="session-1", research_task_id="task-1")
    caller_only = BudgetSnapshot.from_value({"max_model_loops": 999, "max_tool_calls": 999, "task_max_model_loops": 999, "task_max_tool_calls": 999, "max_seconds": 999999})
    assert (caller_only.max_model_loops, caller_only.max_tool_calls, caller_only.task_max_model_loops, caller_only.task_max_tool_calls, caller_only.max_seconds) == (40, 160, 160, 640, 5400)


def test_resource_probe_failure_records_single_worker_fallback():
    class Probe:
        def __init__(self):
            self.released = 0
        def arbitrate(self, _task, _requested):
            return 1, "RESOURCE_PROBE_FAILED"
        def release(self, _task):
            self.released += 1
    probe = Probe()
    result = ResearchAgentRunner(model=FakeModel({"output_json": _output("planner")}), capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]), resource_probe=probe).run(AgentRunInput("run-15", "session-1", "planner", skill_snapshot=_skill("planner"), research_task_id="task-1", work_item_id="work-1"))
    assert result.status == "completed"
    assert result.model_metadata["worker_grant"] == 1
    assert result.model_metadata["resource_probe_code"] == "RESOURCE_PROBE_FAILED"
    assert probe.released == 1


def test_model_factory_failure_releases_admission_lease():
    class Probe:
        def __init__(self):
            self.active = 0
        def arbitrate(self, _task, _requested):
            self.active += 1
            return 1, None
        def release(self, _task):
            self.active -= 1
    probe = Probe()
    def factory(_model, _effort):
        raise RuntimeError("provider unavailable")
    result = ResearchAgentRunner(model_factory=factory, capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]), resource_probe=probe).run(AgentRunInput("run-16", "session-1", "planner", skill_snapshot=_skill("planner"), research_task_id="task-1", work_item_id="work-1"))
    assert result.status == "failed" and result.error_code == "MODEL_UNAVAILABLE" and probe.active == 0


def test_store_binding_failure_releases_admission_lease():
    class Probe:
        def __init__(self):
            self.active = 0
        def arbitrate(self, _task, _requested):
            self.active += 1
            return 1, None
        def release(self, _task):
            self.active -= 1
    class BrokenStore:
        def get_agent_run(self, _run_id, _owner):
            raise OSError("store offline")
    probe = Probe()
    runner = ResearchAgentRunner(
        store=BrokenStore(), model=FakeModel({"output_json": _output("planner")}),
        capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]), resource_probe=probe,
    )
    with pytest.raises(AgentRuntimeError, match="run binding rejected"):
        runner.run(AgentRunInput("run-store-error", "session-1", "planner", skill_snapshot=_skill("planner"), research_task_id="task-1", work_item_id="work-1"))
    assert probe.active == 0


def test_checkpoint_write_barrier_rejects_terminal_generation(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, _ = memory.create_conversation_messages("owner-a", "q", None, "m", "normal")
    session = ResearchSession(uuid.uuid4().hex, "owner-a", conversation.conversation_id, user.message_id, uuid.uuid4().hex, "intake_pending")
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_session(session, memory_repository=memory)
    run_id = uuid.uuid4().hex
    result = ResearchAgentRunner(store=store, model=FakeModel({"output_json": _output("planner")}), capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")])).run(AgentRunInput(run_id, session.research_session_id, "planner", skill_snapshot=_skill("planner"), owner_id="owner-a"))
    run = store.get_agent_run(run_id, "owner-a")
    assert result.status == "completed" and run is not None
    content = "{}"
    checkpoint = AgentCheckpoint("checkpoint:late", "owner-a", session.research_session_id, None, None, run_id, "runtime-v1", content, hashlib.sha256(content.encode()).hexdigest())
    with pytest.raises(AgentRunWriteDiscarded):
        store.create_agent_checkpoint(checkpoint, expected_generation=run.generation)


def test_resume_requires_previous_limit_run_and_uses_persisted_handoff(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, _ = memory.create_conversation_messages("owner-a", "q", None, "m", "normal")
    session = ResearchSession(uuid.uuid4().hex, "owner-a", conversation.conversation_id, user.message_id, uuid.uuid4().hex, "intake_pending")
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_session(session, memory_repository=memory)
    tool = FakeTool("read_a")
    registry = RoleCapabilityRegistry(skills=[_skill("planner", ["read_a"])], tools=[tool])
    first_id = uuid.uuid4().hex
    first = ResearchAgentRunner(
        store=store,
        model=FakeModel({"tool_calls": [{"name": "read_a", "arguments": {}}]}),
        capability_registry=registry,
    ).run(AgentRunInput(first_id, session.research_session_id, "planner", skill_snapshot=_skill("planner", ["read_a"]), tool_snapshot=[tool], owner_id="owner-a", budget_snapshot={"max_model_loops": 1}))
    assert first.status == "limit_reached" and first.checkpoint_ref and first.checkpoint_hash
    second_id = uuid.uuid4().hex
    second = ResearchAgentRunner(
        store=store,
        model=FakeModel({"output_json": _output("planner")}),
        capability_registry=registry,
    ).run(AgentRunInput(second_id, session.research_session_id, "planner", skill_snapshot=_skill("planner", ["read_a"]), tool_snapshot=[tool], owner_id="owner-a", continued_from_agent_run_id=first_id, checkpoint_ref=first.checkpoint_ref, checkpoint_hash=first.checkpoint_hash))
    assert second.status == "completed"


def test_four_attempts_are_independent_persisted_runs(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, _ = memory.create_conversation_messages("owner-a", "q", None, "m", "normal")
    session = ResearchSession(uuid.uuid4().hex, "owner-a", conversation.conversation_id, user.message_id, uuid.uuid4().hex, "intake_pending")
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_session(session, memory_repository=memory)
    root_id = uuid.uuid4().hex
    result = ResearchAgentRunner(
        store=store,
        model=FakeModel([{"output_json": {}}] * 4),
        capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]),
    ).run(AgentRunInput(root_id, session.research_session_id, "planner", skill_snapshot=_skill("planner"), owner_id="owner-a"))
    assert result.status == "failed" and result.error_code == "AGENT_OUTPUT_INVALID"
    runs = [store.get_agent_run(f"{root_id}:attempt-{index}", "owner-a") for index in range(2, 5)]
    assert all(run is not None for run in runs)
    assert [run.attempt for run in runs if run is not None] == [2, 3, 4]
    assert [run.status for run in runs if run is not None] == ["limit_reached", "limit_reached", "failed"]


def test_four_attempts_persist_router_metadata_with_generation_cas(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, _ = memory.create_conversation_messages("owner-a", "q", None, "m", "normal")
    session = ResearchSession(uuid.uuid4().hex, "owner-a", conversation.conversation_id, user.message_id, uuid.uuid4().hex, "intake_pending")
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_session(session, memory_repository=memory)
    class Router:
        def resolve(self, *, role, tier):
            return SimpleNamespace(model=f"{tier}-selected")
    def factory(model, effort):
        adapter = FakeModel({"output_json": {}})
        adapter.model_name, adapter.reasoning_effort, adapter.provider = model, effort, "fake-provider"
        return adapter
    root_id = uuid.uuid4().hex
    result = ResearchAgentRunner(
        store=store, model_router=Router(), model_factory=factory,
        capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]),
        # Keep this historical four-attempt contract deterministic even when
        # the developer's .env opts into the real online fallback provider.
        online_fallback_enabled=False,
    ).run(AgentRunInput(root_id, session.research_session_id, "planner", skill_snapshot=_skill("planner"), owner_id="owner-a", reasoning_effort="high"))
    assert result.status == "failed"
    runs = [store.get_agent_run(root_id if index == 1 else f"{root_id}:attempt-{index}", "owner-a") for index in range(1, 5)]
    assert [(run.resolved_model, run.reasoning_effort, run.provider) for run in runs if run is not None] == [
        ("fast-selected", "high", "fake-provider"),
        ("fast-selected", "high", "fake-provider"),
        ("fast-selected", "high", "fake-provider"),
        ("strong-selected", "high", "fake-provider"),
    ]


def test_orchestrator_agent_pipeline_creates_bound_run_per_work_item(tmp_path):
    memory = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation, user, _ = memory.create_conversation_messages("owner-a", "research goal", None, "m", "normal")
    session_id = uuid.uuid4().hex
    session = ResearchSession(session_id, "owner-a", conversation.conversation_id, user.message_id, uuid.uuid4().hex, "intake_pending")
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_session(session, memory_repository=memory)
    task_id = uuid.uuid4().hex
    store.create_task(ResearchTask(
        research_task_id=task_id, owner_id="owner-a", conversation_id=conversation.conversation_id,
        goal="research goal", language="zh", quality_profile="balanced", review_plan_first=False,
        target_paper_count=2, soft_budget_seconds=90 * 60, status="draft", current_plan_version=1,
        created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
    ))
    store.update_session_links(session_id, "owner-a", research_task_id=task_id)
    class MultiRoleModel:
        def invoke(self, context, _tools=()):
            return {"output_json": _output(context["role"])}
    capabilities = RoleCapabilityRegistry(skills=[_skill(role) for role in ("planner", "search_worker", "paper_evaluator", "research_critic", "synthesizer")])
    runner = ResearchAgentRunner(store=store, model=MultiRoleModel(), capability_registry=capabilities)
    planner = SimpleNamespace(build_plan=lambda **_: SimpleNamespace(
        facets=("systems",), planner_model="fake", rationale_summary="fake",
        work_items=({"id": "s1", "task_type": "search_catalog", "role": "search-worker", "depends_on": [], "params": {"query": "systems"}},),
    ))
    result = Orchestrator(store=store, search_adapter=SimpleNamespace(), planner=planner, agent_runner=runner).run(task_id, "owner-a")
    items = store.list_work_items(task_id, plan_version=1)
    assert result.status == "completed" and items[0].status == "completed"
    # AgentRunner may finalize the WorkItem before the orchestrator writes the
    # serialized AgentRunOutput; terminal write-back must preserve that payload.
    assert items[0].output_json and '"schema_version": "runtime-v1"' in items[0].output_json
    run = store.get_agent_run(f"{items[0].work_item_id}:run-1", "owner-a")
    assert run is not None and run.research_session_id == session_id and run.research_task_id == task_id and run.work_item_id == items[0].work_item_id
