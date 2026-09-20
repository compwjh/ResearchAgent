"""Spec040 Task04: opt-in online provider fallback at the runtime seam."""

from types import SimpleNamespace

import pytest

from backend.app.platform import config
from backend.app.research.application.agent_runtime import (
    AgentRunInput,
    AgentRuntimeError,
    ResearchAgentRunner,
    RoleCapabilityRegistry,
)


def _skill(role="planner"):
    return {
        "name": "research-plan-authoring",
        "schema_version": "1",
        "content_hash": "skill-hash",
        "source_ref": "skill:research-plan-authoring",
        "enabled": True,
        "tools": [],
    }


def _output():
    return {
        "schema_version": "runtime-v1",
        "safe_summary": {},
        "source_refs": [],
        "plan_version": 1,
        "objective": "o",
        "scope": {},
        "work_items": [],
        "capabilities": [],
        "budget": {},
        "report_structure": {},
    }


class _TimeoutModel:
    provider = "ollama"

    def __init__(self, model_name):
        self.model_name = model_name
        self.reasoning_effort = "off"

    def invoke(self, _context, _tools=()):
        raise AgentRuntimeError("MODEL_TIMEOUT", "provider timed out")


class _GoodModel:
    provider = "deepseek"
    reasoning_effort = "off"

    def __init__(self, model_name):
        self.model_name = model_name

    def invoke(self, _context, _tools=()):
        return {"output_json": _output()}


class _InvalidModel(_TimeoutModel):
    def invoke(self, _context, _tools=()):
        return {"output_json": {}}


def _runner(factory):
    return ResearchAgentRunner(
        model_factory=factory,
        capability_registry=RoleCapabilityRegistry(skills=[_skill()]),
    )


def _input():
    return AgentRunInput(
        "run-online-fallback",
        "session-1",
        "planner",
        skill_snapshot=_skill(),
        resolved_model="local:model",
        reasoning_effort="off",
    )


def test_online_fallback_is_disabled_by_default(monkeypatch):
    monkeypatch.setenv("RESEARCH_ONLINE_FALLBACK_ENABLED", "false")
    monkeypatch.setattr(config, "RESEARCH_ONLINE_FALLBACK_ENABLED", False, raising=False)
    calls = []

    def factory(model_name, _effort):
        calls.append(model_name)
        return _TimeoutModel(model_name)

    result = _runner(factory).run(_input())
    assert result.status == "failed"
    assert result.error_code == "MODEL_TIMEOUT"
    assert calls == ["local:model"]


def test_enabled_fallback_uses_registered_online_alias_after_local_timeout(monkeypatch):
    monkeypatch.setattr(config, "RESEARCH_ONLINE_FALLBACK_ENABLED", True, raising=False)
    monkeypatch.setenv("ONLINE_MODELS", "deepseek:deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-fake-key")
    calls = []

    def factory(model_name, _effort):
        calls.append(model_name)
        return _TimeoutModel(model_name) if model_name == "local:model" else _GoodModel(model_name)

    result = _runner(factory).run(_input())
    assert result.status == "completed"
    assert calls == ["local:model", "deepseek:deepseek-chat"]
    assert result.model_metadata["model"] == "deepseek:deepseek-chat"
    assert result.model_metadata["provider"] == "deepseek"


def test_fallback_event_keeps_only_aliases_and_reason(monkeypatch):
    monkeypatch.setattr(config, "RESEARCH_ONLINE_FALLBACK_ENABLED", True, raising=False)
    captured = []

    class Store:
        def append_event(self, _task_id, _event_type, payload):
            captured.append(payload)

    runner = ResearchAgentRunner(store=Store())
    runner._fallback_event(
        AgentRunInput("run-event", "session-1", "planner", research_task_id="task-1", work_item_id="item-1"),
        choice=SimpleNamespace(model="deepseek:chat", provider="deepseek"),
        reason_code="MODEL_TIMEOUT",
        attempt=2,
        from_model="local:model",
    )
    assert captured[0]["event_type"] == "provider_fallback"
    assert captured[0]["to_model"] == "deepseek:chat"
    assert "api_key" not in captured[0]
    assert "prompt" not in captured[0]


def test_output_retry_exhaustion_can_switch_once(monkeypatch):
    monkeypatch.setattr(config, "RESEARCH_ONLINE_FALLBACK_ENABLED", True, raising=False)
    monkeypatch.setenv("ONLINE_MODELS", "deepseek:deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-fake-key")
    calls = []

    def factory(model_name, _effort):
        calls.append(model_name)
        return _InvalidModel(model_name) if model_name == "local:model" else _GoodModel(model_name)

    result = _runner(factory).run(_input())
    assert result.status == "completed"
    assert calls == ["local:model", "deepseek:deepseek-chat"]
    assert result.model_metadata["original_error_code"] == "AGENT_OUTPUT_INVALID"


def test_online_failure_preserves_local_and_online_error_codes(monkeypatch):
    monkeypatch.setattr(config, "RESEARCH_ONLINE_FALLBACK_ENABLED", True, raising=False)
    monkeypatch.setenv("ONLINE_MODELS", "deepseek:deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-fake-key")

    def factory(model_name, _effort):
        return _TimeoutModel(model_name)

    result = _runner(factory).run(_input())
    assert result.status == "failed"
    assert result.error_code == "MODEL_TIMEOUT"
    assert result.model_metadata["original_error_code"] == "MODEL_TIMEOUT"
    assert result.model_metadata["fallback_error_code"] == "MODEL_TIMEOUT"


@pytest.mark.parametrize("code", ["CAPABILITY_NOT_AUTHORIZED", "CANCELLED", "EVIDENCE_OUT_OF_SCOPE"])
def test_non_transient_errors_do_not_trigger_online_fallback(monkeypatch, code):
    monkeypatch.setattr(config, "RESEARCH_ONLINE_FALLBACK_ENABLED", True, raising=False)
    monkeypatch.setenv("ONLINE_MODELS", "deepseek:deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-fake-key")
    calls = []

    class Model:
        model_name = "local:model"
        provider = "ollama"
        reasoning_effort = "off"

        def invoke(self, _context, _tools=()):
            raise AgentRuntimeError(code)

    def factory(model_name, _effort):
        calls.append(model_name)
        return Model()

    result = _runner(factory).run(_input())
    assert result.status == "failed"
    assert result.error_code == code
    assert calls == ["local:model"]
