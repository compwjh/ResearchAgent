"""Task03 contract tests: redacted routing persistence and shadow replay."""

from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from backend.app.platform.ollama import ResourceSnapshot
from backend.app.research.application.model_router import ModelRouter
from backend.app.research.application.routing_observation import RoutingObservationService
from backend.app.research.infrastructure.research_store import ResearchStore


def _service(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    return store, RoutingObservationService(store)


def test_decision_is_redacted_bounded_and_idempotent(tmp_path):
    store, service = _service(tmp_path)
    first = service.record_decision(
        owner_id="owner-a", task_type="search_catalog", features={"tier": "fast"},
        candidate_models=["qwen3.5:9b"], chosen_model="qwen3.5:9b",
        reason="static rule", policy_version="p1", idempotency_key="event-1",
    )
    second = service.record_decision(
        owner_id="owner-a", task_type="search_catalog", features={"tier": "fast"},
        candidate_models=["qwen3.5:9b"], chosen_model="qwen3.5:9b",
        reason="static rule", policy_version="p1", idempotency_key="event-1",
    )
    assert first and second and first.decision_id == second.decision_id
    assert set(first.public()) == {"task_type", "features", "candidate_models", "chosen_model", "reason", "policy_version"}
    assert "prompt" not in first.public()
    assert store.get_routing_decision(first.decision_id, owner_id="owner-b") is None


def test_outcome_allowlist_and_probe_failure_are_persisted(tmp_path):
    store, service = _service(tmp_path)
    decision = service.record_decision(
        owner_id="owner-a", task_type="evaluate_papers", features={}, candidate_models=["m"],
        chosen_model="m", reason="rule", policy_version="p1",
    )
    outcome = service.record_outcome(owner_id="owner-a", decision_id=decision.decision_id, schema_valid=True, quality_score=.8, ttft=1.0, duration=2.0, tokens=3, error_code=None)
    assert outcome and set(outcome.public()) == {"schema_valid", "quality_score", "ttft", "duration", "tokens", "error_code"}

    class BrokenProbe:
        def snapshot(self):
            raise RuntimeError("private details must not be persisted")

    snapshot = service.capture_resource_snapshot(owner_id="owner-a", probe=BrokenProbe())
    assert snapshot and snapshot.probe_error == "RESOURCE_PROBE_FAILED"
    assert snapshot.available_memory is None
    assert "private details" not in repr(snapshot)


def test_shadow_replay_does_not_change_production_choice(tmp_path):
    store, service = _service(tmp_path)
    decision = service.record_decision(
        owner_id="owner-a", task_type="search_catalog", features={"tier": "fast"},
        candidate_models=["fast", "strong"], chosen_model="fast", reason="static", policy_version="p1",
    )
    service.register_shadow_policy(version="p2", profile="balanced", rules=[{"task_type": "search_catalog", "model": "strong"}])
    replay = service.replay_shadow(owner_id="owner-a", policy_version="p2")
    assert replay[0]["chosen_model"] == "fast"
    assert replay[0]["shadow_model"] == "strong"
    assert store.get_routing_decision(decision.decision_id, owner_id="owner-a").chosen_model == "fast"


def test_model_router_observation_is_write_only():
    seen = []

    class Sink:
        def record_decision(self, **kwargs):
            seen.append(kwargs)

    router = ModelRouter(available_models_provider=lambda: ["fast-9b", "strong-27b"], observation_service=Sink())
    choice = router.resolve(role="search-worker", tier="fast", owner_id="owner-a", features={"x": 1})
    assert choice.model == "fast-9b"
    assert seen[0]["chosen_model"] == "fast-9b"
    assert seen[0]["owner_id"] == "owner-a"


def test_observation_rejects_prompt_shaped_feature():
    with pytest.raises(ValueError):
        from backend.app.research.application.routing_observation import _safe_features
        _safe_features({"prompt": "do not store"})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task_type", "answer=PRIVATE_RESPONSE"),
        ("reason", "prompt=PRIVATE_ANSWER"),
        ("policy_version", "https://private.example/token"),
        ("idempotency_key", "credential=PRIVATE_TOKEN"),
    ],
)
def test_sensitive_values_are_rejected_before_sqlite(tmp_path, field, value):
    store, service = _service(tmp_path)
    kwargs = {
        "owner_id": "owner-a", "task_type": "search_catalog", "features": {},
        "candidate_models": ["qwen3.5:9b"], "chosen_model": "qwen3.5:9b",
        "reason": "static rule", "policy_version": "p1",
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        service.record_decision(**kwargs)
    with sqlite3.connect(tmp_path / "research.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM research_routing_decisions").fetchone()[0] == 0


@pytest.mark.parametrize("value", ["PRIVATE_RESPONSE", "PRIVATE_TOKEN", "chain_of_thought", "private-response"])
def test_joined_sensitive_values_are_rejected(tmp_path, value):
    _store, service = _service(tmp_path)
    with pytest.raises(ValueError):
        service.record_decision(
            owner_id="owner-a", task_type="search_catalog", features={"tier": "fast"},
            candidate_models=["m"], chosen_model="m", reason=value, policy_version="p1",
        )


def test_store_boundary_rejects_hand_built_sensitive_decision(tmp_path):
    from backend.app.research.application.routing_observation import RoutingDecision

    store = ResearchStore(tmp_path / "research.sqlite3")
    decision = RoutingDecision(
        decision_id="routing-decision:unsafe", owner_id="owner-a", task_type="search_catalog",
        features={}, candidate_models=["m"], chosen_model="m",
        reason="answer=PRIVATE", policy_version="p1",
    )
    with pytest.raises(ValueError):
        store.save_routing_decision(decision)


def test_policy_text_and_langfuse_metadata_are_value_sanitized(monkeypatch, tmp_path):
    store, service = _service(tmp_path)
    with pytest.raises(ValueError):
        service.register_shadow_policy(
            version="p2", profile="balanced", rules=[{"reason": "chain of thought: PRIVATE"}]
        )

    from backend.app.platform.observability import spans

    events = []
    monkeypatch.setattr(spans, "record_event", lambda **kwargs: events.append(kwargs))
    spans.record_routing_observation(
        task_type="search_catalog", features={"tier": "fast"}, candidate_models=["m"],
        chosen_model="m", reason="static rule", policy_version="p1",
    )
    assert events and events[-1]["metadata"]["reason"] == "static rule"
    for unsafe_reason in ("PRIVATE_RESPONSE", "PRIVATE_TOKEN", "chain_of_thought"):
        spans.record_routing_observation(
            task_type="search_catalog", features={"tier": "fast"}, candidate_models=["m"],
            chosen_model="m", reason=unsafe_reason, policy_version="p1",
        )
    assert len(events) == 1


def test_production_entry_installs_opt_in_observation(monkeypatch, tmp_path):
    from backend.app.research.application import entry

    store = ResearchStore(tmp_path / "research.sqlite3")
    monkeypatch.setattr(entry, "build_research_store", lambda: store)
    entry.build_research_service.cache_clear()
    service = entry.build_research_service()
    assert service._model_router._observation is not None
    assert service._model_router._observation.store is store
    assert callable(service._model_router._observation._observability)
    entry.build_research_service.cache_clear()
