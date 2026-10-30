"""Ability tests for binding model calls to their AgentRun time grant."""

import asyncio
from types import SimpleNamespace

import anyio
import pytest

from backend.app.platform.ollama import create_chat_model
from backend.app.research.application.agent_runtime import (
    AgentRunInput,
    AgentRuntimeError,
    ResearchAgentRunner,
    RoleCapabilityRegistry,
    _ollama_model_factory,
    _OllamaRunnerAdapter,
)
from tests.research.test_agent_runtime_contract import _output, _skill


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class _TimeoutModel:
    def __init__(self, name, clock, *, timeout_after_set=None, output=None):
        self.model_name = name
        self.provider = "ollama" if name.startswith("local:") else "deepseek"
        self.reasoning_effort = "off"
        self.clock = clock
        self.timeout_after_set = timeout_after_set
        self.output = output
        self.request_timeouts = []

    def set_request_timeout(self, seconds):
        self.request_timeouts.append(seconds)

    def invoke(self, _context, _tools=()):
        if self.timeout_after_set:
            self.clock.now += self.request_timeouts[-1]
            raise TimeoutError("provider request timed out")
        self.clock.now += 8
        return {"output_json": self.output}


class _Router:
    def resolve(self, *, role, tier):
        return SimpleNamespace(model="local:qwen", provider="ollama", tier=tier)

    def resolve_online_fallback(self):
        return SimpleNamespace(model="deepseek:flash", provider="deepseek", tier="online")


def _run_input(*, budget):
    skill = _skill("planner")
    return AgentRunInput(
        "run-timeout",
        "session-timeout",
        "planner",
        skill_snapshot=skill,
        budget_snapshot=budget,
        reasoning_effort="off",
    )


def test_provider_timeout_uses_run_grant_and_reserves_existing_fallback_time():
    clock = _Clock()
    models = {}

    def factory(name, _effort):
        model = _TimeoutModel(
            name,
            clock,
            timeout_after_set=name.startswith("local:"),
            output=_output("planner"),
        )
        models[name] = model
        return model

    runner = ResearchAgentRunner(
        model_router=_Router(),
        model_factory=factory,
        online_fallback_factory=factory,
        online_fallback_enabled=True,
        capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]),
        clock=clock,
    )

    result = runner.run(
        _run_input(budget={"max_seconds": 120, "elapsed_seconds": 0})
    )

    assert result.status == "completed"
    assert result.usage["model_loops"] == 2
    assert models["local:qwen"].request_timeouts == [30]
    assert models["deepseek:flash"].request_timeouts == [90]
    assert sum(models["local:qwen"].request_timeouts + models["deepseek:flash"].request_timeouts) == 120
    assert clock.now == 38
    assert result.model_metadata["fallback_attempted"] is True


def test_shorter_remaining_grant_splits_proportionally_without_exceeding_cap():
    clock = _Clock()
    models = {}

    def factory(name, _effort):
        model = _TimeoutModel(
            name,
            clock,
            timeout_after_set=name.startswith("local:"),
            output=_output("planner"),
        )
        models[name] = model
        return model

    runner = ResearchAgentRunner(
        model_router=_Router(),
        model_factory=factory,
        online_fallback_factory=factory,
        online_fallback_enabled=True,
        capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]),
        clock=clock,
    )

    result = runner.run(
        _run_input(budget={"max_seconds": 120, "elapsed_seconds": 40})
    )

    assert result.status == "completed"
    assert models["local:qwen"].request_timeouts == [20]
    assert models["deepseek:flash"].request_timeouts == [60]
    assert sum(models["local:qwen"].request_timeouts + models["deepseek:flash"].request_timeouts) == 80
    assert 40 + clock.now <= 120


def test_long_grant_keeps_primary_timeout_at_thirty_seconds_and_reserves_the_rest_for_fallback():
    clock = _Clock()
    models = {}

    def factory(name, _effort):
        model = _TimeoutModel(
            name,
            clock,
            timeout_after_set=name.startswith("local:"),
            output=_output("planner"),
        )
        models[name] = model
        return model

    runner = ResearchAgentRunner(
        model_router=_Router(),
        model_factory=factory,
        online_fallback_factory=factory,
        online_fallback_enabled=True,
        capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]),
        clock=clock,
    )

    result = runner.run(
        _run_input(budget={"max_seconds": 300, "elapsed_seconds": 0})
    )

    assert result.status == "completed"
    assert models["local:qwen"].request_timeouts == [30]
    assert models["deepseek:flash"].request_timeouts == [270]
    assert sum(models["local:qwen"].request_timeouts + models["deepseek:flash"].request_timeouts) == 300


def test_schema_retries_consume_one_run_deadline_instead_of_resetting_it():
    clock = _Clock()

    class InvalidSchemaModel(_TimeoutModel):
        def invoke(self, _context, _tools=()):
            self.clock.now += min(0.4, self.request_timeouts[-1])
            return {"output_json": {}}

    model = InvalidSchemaModel("local:qwen", clock)
    runner = ResearchAgentRunner(
        model=model,
        online_fallback_enabled=False,
        capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]),
        clock=clock,
    )

    result = runner.run(
        _run_input(budget={"max_seconds": 1.0, "elapsed_seconds": 0})
    )

    assert result.status == "limit_reached"
    assert result.error_code == "TASK_TIME_LIMIT_REACHED"
    assert result.usage["model_loops"] == 3
    assert model.request_timeouts == pytest.approx([1.0, 0.6, 0.2])
    assert clock.now == pytest.approx(1.0)


def test_disabled_fallback_gets_all_remaining_run_time():
    clock = _Clock()
    model = _TimeoutModel("local:qwen", clock, timeout_after_set=True, output=_output("planner"))
    runner = ResearchAgentRunner(
        model=model,
        online_fallback_enabled=False,
        capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]),
        clock=clock,
    )

    result = runner.run(
        _run_input(budget={"max_seconds": 120, "elapsed_seconds": 0})
    )

    assert result.status == "limit_reached"
    assert result.error_code == "TASK_TIME_LIMIT_REACHED"
    assert model.request_timeouts == [120]
    assert result.usage["model_loops"] == 1
    assert result.model_metadata.get("fallback_attempted") is None


def test_primary_and_fallback_timeout_stop_at_the_same_run_grant():
    clock = _Clock()
    models = {}

    class AlwaysTimeoutModel(_TimeoutModel):
        def invoke(self, _context, _tools=()):
            self.clock.now += self.request_timeouts[-1]
            raise TimeoutError("provider request timed out")

    def factory(name, _effort):
        model = AlwaysTimeoutModel(name, clock, output=_output("planner"))
        models[name] = model
        return model

    runner = ResearchAgentRunner(
        model_router=_Router(),
        model_factory=factory,
        online_fallback_factory=factory,
        online_fallback_enabled=True,
        capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]),
        clock=clock,
    )

    result = runner.run(
        _run_input(budget={"max_seconds": 120, "elapsed_seconds": 0})
    )

    assert result.status == "limit_reached"
    assert result.error_code == "TASK_TIME_LIMIT_REACHED"
    assert result.usage["model_loops"] == 2
    assert models["local:qwen"].request_timeouts == [30]
    assert models["deepseek:flash"].request_timeouts == [90]
    assert clock.now == 120


def test_continuous_provider_stream_is_cancelled_and_clients_close_once():
    models = {}
    factory_calls = []

    class StreamingClient:
        def __init__(self):
            self.tokens_seen = 0
            self.cancelled = False
            self.closed = False
            self.close_count = 0
            self._async_client = self

        async def ainvoke(self, _messages):
            try:
                while True:
                    await anyio.sleep(0.005)
                    self.tokens_seen += 1
            except BaseException:
                self.cancelled = True
                raise

        async def close(self):
            self.closed = True
            self.close_count += 1

    def factory(name, effort):
        factory_calls.append(name)
        chat = StreamingClient()
        adapter = _OllamaRunnerAdapter(chat, model_name=name, effort=effort)
        if name.startswith("deepseek:"):
            adapter.provider = "deepseek"
        models[name] = chat
        return adapter

    runner = ResearchAgentRunner(
        model_router=_Router(),
        model_factory=factory,
        online_fallback_factory=factory,
        online_fallback_enabled=True,
        capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]),
    )

    result = runner.run(
        _run_input(budget={"max_seconds": 0.25, "elapsed_seconds": 0})
    )

    assert result.status == "limit_reached"
    assert result.error_code == "TASK_TIME_LIMIT_REACHED"
    assert result.usage["model_loops"] == 2
    assert factory_calls == ["local:qwen", "deepseek:flash"]
    assert all(model.tokens_seen > 0 for model in models.values())
    assert all(model.cancelled and model.closed for model in models.values())
    assert all(model.close_count == 1 for model in models.values())


def test_adapter_rejects_nested_sync_call_on_event_loop_thread():
    class AsyncChat:
        called = False

        async def ainvoke(self, _messages):
            self.called = True
            return SimpleNamespace(content="{}", tool_calls=[])

    chat = AsyncChat()
    adapter = _OllamaRunnerAdapter(chat, model_name="local:qwen", effort="off")
    adapter.set_request_timeout(1)

    async def invoke_from_running_loop():
        with pytest.raises(AgentRuntimeError, match="MODEL_EXECUTION_CONTEXT_INVALID"):
            adapter.invoke({"role": "planner"})

    anyio.run(invoke_from_running_loop)

    assert chat.called is False


def test_adapter_rejects_asyncio_loop_callback_before_creating_coroutine(recwarn):
    class AsyncChat:
        calls = 0

        async def ainvoke(self, _messages):
            self.calls += 1
            return SimpleNamespace(content="{}", tool_calls=[])

    chat = AsyncChat()
    adapter = _OllamaRunnerAdapter(chat, model_name="local:qwen", effort="off")
    adapter.set_request_timeout(1)

    async def invoke_from_callback():
        loop = asyncio.get_running_loop()
        result = loop.create_future()

        def callback():
            try:
                adapter.invoke({"role": "planner"})
            except AgentRuntimeError as exc:
                result.set_result(exc.code)
            except Exception as exc:
                result.set_result(type(exc).__name__)

        loop.call_soon(callback)
        return await result

    assert asyncio.run(invoke_from_callback()) == "MODEL_EXECUTION_CONTEXT_INVALID"
    assert chat.calls == 0
    assert not any("never awaited" in str(warning.message) for warning in recwarn)


def test_provider_return_after_full_grant_does_not_construct_fallback():
    clock = _Clock()
    primary_models = []
    fallback_factory_calls = []

    class LateProviderModel(_TimeoutModel):
        def invoke(self, _context, _tools=()):
            self.clock.now = 120
            return {"output_json": self.output}

    def primary_factory(name, _effort):
        model = LateProviderModel(name, clock, output=_output("planner"))
        primary_models.append(model)
        return model

    def fallback_factory(name, _effort):
        fallback_factory_calls.append(name)
        return _TimeoutModel(name, clock, output=_output("planner"))

    runner = ResearchAgentRunner(
        model_router=_Router(),
        model_factory=primary_factory,
        online_fallback_factory=fallback_factory,
        online_fallback_enabled=True,
        capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]),
        clock=clock,
    )

    result = runner.run(
        _run_input(budget={"max_seconds": 120, "elapsed_seconds": 0})
    )

    assert result.status == "limit_reached"
    assert result.error_code == "TASK_TIME_LIMIT_REACHED"
    assert fallback_factory_calls == []
    assert result.model_metadata["provider"] == "ollama"
    assert result.model_metadata["model"] == "local:qwen"
    assert result.model_metadata.get("fallback_attempted") is None
    assert primary_models[0].request_timeouts == [30]


def test_exhausted_run_budget_skips_provider_and_preserves_model_projection():
    clock = _Clock()
    model = _TimeoutModel("local:qwen", clock, output=_output("planner"))
    runner = ResearchAgentRunner(
        model=model,
        capability_registry=RoleCapabilityRegistry(skills=[_skill("planner")]),
        clock=clock,
    )

    result = runner.run(
        _run_input(budget={"max_seconds": 10, "elapsed_seconds": 10})
    )

    assert result.status == "limit_reached"
    assert result.error_code == "TASK_TIME_LIMIT_REACHED"
    assert model.request_timeouts == []
    assert result.model_metadata["model"] == "local:qwen"
    assert result.model_metadata["provider"] == "ollama"


def test_ollama_factory_rebuilds_provider_client_with_per_call_timeout(monkeypatch):
    captured = []

    def fake_create(model_name, *, reasoning=None, timeout_seconds=None):
        captured.append((model_name, reasoning, timeout_seconds))
        return object()

    monkeypatch.setattr("backend.app.platform.ollama.create_chat_model", fake_create)
    adapter = _ollama_model_factory("local:qwen", "off")

    adapter.set_request_timeout(17.5)

    assert captured == [
        ("local:qwen", False, None),
        ("local:qwen", False, 17.5),
    ]


def test_platform_clients_receive_deadline_and_disable_internal_retries(monkeypatch):
    monkeypatch.delenv("ONLINE_MODELS", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    local = create_chat_model("local:qwen", reasoning=False, timeout_seconds=12.5)

    assert local.sync_client_kwargs["timeout"] == 12.5
    assert local.async_client_kwargs["timeout"] == 12.5
    assert local.client_kwargs["trust_env"] is False

    monkeypatch.setenv("ONLINE_MODELS", "deepseek:deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-not-a-real-key")
    online = create_chat_model(
        "deepseek:deepseek-chat", timeout_seconds=7.25
    )

    assert online.request_timeout == 7.25
    assert online.max_retries == 0

