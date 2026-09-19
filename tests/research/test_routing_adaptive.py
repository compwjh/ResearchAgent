"""Task04 contracts: bounded adaptive workers and guarded policy activation."""

from pathlib import Path
import threading

import pytest

from backend.app.platform.ollama import ResourceProbe, ResourceProbeUnavailable, _GlobalWorkerScheduler
from backend.app.research.application.adaptive_routing import (
    AdaptiveRoutingService,
    PolicyActivationError,
    WorkerGrant,
)
from backend.app.research.application.routing_observation import RoutingObservationService
from backend.app.research.application.scheduler import ResearchScheduler
from backend.app.research.infrastructure.research_store import ResearchStore


GB = 1024**3


class FakeProbe:
    def __init__(self, cap=4, code=None):
        self.cap, self.code, self.used = cap, code, 0

    def arbitrate(self, task_id, requested):
        grant = min(int(requested), max(0, self.cap - self.used))
        self.used += grant
        return grant, self.code

    def release(self, task_id, *, count=None):
        self.used = max(0, self.used - (self.used if count is None else int(count)))

    def snapshot(self):
        from backend.app.platform.ollama import ResourceSnapshot
        return ResourceSnapshot(10 * GB, 2 * GB, 1)


def test_global_worker_cap_and_per_task_fairness_for_1_2_4():
    for cap in (1, 2, 4):
        scheduler = _GlobalWorkerScheduler()
        first = scheduler.acquire("task-a", 4, cap)
        second = scheduler.acquire("task-b", 4, cap)
        assert first + second <= cap
        if cap > 1:
            assert first == second == cap // 2
        else:
            assert (first, second) == (1, 0)
        scheduler.release("task-a")
        scheduler.release("task-b")
        assert scheduler.acquire("task-b", 1, cap) == min(1, cap)
        scheduler.release("task-b")
        assert scheduler.in_use() == 0


def test_probe_failure_grants_exactly_one_worker(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    scheduler = ResearchScheduler(store, probe=FakeProbe(cap=1, code="RESOURCE_PROBE_FAILED"))
    grant = scheduler.grant_workers("task-a", requested=4, model_tier="fast")
    assert isinstance(grant, WorkerGrant)
    assert grant.granted == 1
    assert grant.reason == "RESOURCE_PROBE_FAILED"
    scheduler.release_grant(grant)


def test_strong_tier_is_single_concurrency_and_expiry_recovers(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    scheduler = ResearchScheduler(store, probe=FakeProbe(cap=4))
    first = scheduler.grant_workers("task-a", requested=4, model_tier="strong", lease_seconds=1, now="2026-09-17T00:00:00Z")
    second = scheduler.grant_workers("task-b", requested=4, model_tier="strong", lease_seconds=1, now="2026-09-17T00:00:00Z")
    assert first.granted == 1
    assert second.granted == 0
    assert scheduler.recover(now="2026-09-17T00:00:02Z")["reservations"] == 1
    recovered = scheduler.grant_workers("task-b", requested=4, model_tier="strong", now="2026-09-17T00:00:02Z")
    assert recovered.granted == 1
    scheduler.release_grant(recovered)


def test_strong_tier_is_atomic_across_scheduler_instances(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    first_scheduler = ResearchScheduler(store, probe=FakeProbe(cap=1), recover_on_start=False)
    second_scheduler = ResearchScheduler(store, probe=FakeProbe(cap=1), recover_on_start=False)
    barrier = threading.Barrier(2)
    results = []

    def claim(scheduler, task_id):
        barrier.wait()
        results.append(scheduler.grant_workers(task_id, 1, model_tier="strong"))

    threads = [
        threading.Thread(target=claim, args=(first_scheduler, "task-a")),
        threading.Thread(target=claim, args=(second_scheduler, "task-b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(result.granted for result in results) == 1
    assert len(store.list_resource_reservations()) == 1
    assert {result.reason for result in results} == {None, "STRONG_WORKER_BUSY"}


def test_recover_releases_durable_expired_quota_for_new_task(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    probe = FakeProbe(cap=1)
    scheduler = ResearchScheduler(store, probe=probe, recover_on_start=False)
    first = scheduler.grant_workers("task-a", 1, lease_seconds=1, now="2026-09-17T00:00:00Z")
    assert first.granted == 1
    assert scheduler.grant_workers("task-b", 1, now="2026-09-17T00:00:00Z").granted == 0
    assert scheduler.recover(now="2026-09-17T00:00:02Z")["reservations"] == 1
    assert scheduler.grant_workers("task-b", 1, now="2026-09-17T00:00:02Z").granted == 1


def test_reservation_failure_rolls_back_probe_and_store(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    probe = FakeProbe(cap=4)
    scheduler = ResearchScheduler(store, probe=probe)
    original = store.reserve_resources
    calls = {"n": 0}

    def fail_second(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("reservation failure")
        return original(*args, **kwargs)

    store.reserve_resources = fail_second
    with pytest.raises(RuntimeError):
        scheduler.grant_workers("task-a", requested=2, estimated_bytes=10)
    assert probe.used == 0
    assert store.list_resource_reservations() == []


def test_release_grant_isolated_for_same_task_and_idempotent(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    scheduler = ResearchScheduler(store, probe=FakeProbe(cap=4), recover_on_start=False)
    first = scheduler.grant_workers("task-a", 1, worker_prefix="first")
    second = scheduler.grant_workers("task-a", 1, worker_prefix="second")
    assert first.granted == second.granted == 1
    scheduler.release_grant(first)
    assert second.reservation_ids[0] in {item.reservation_id for item in store.list_resource_reservations()}
    scheduler.release_grant(first)
    assert second.reservation_ids[0] in {item.reservation_id for item in store.list_resource_reservations()}
    scheduler.release_grant(second)
    assert store.list_resource_reservations() == []


def test_adaptive_router_records_grant_without_changing_model_choice(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    observation = RoutingObservationService(store)
    scheduler = ResearchScheduler(store, probe=FakeProbe(cap=2))

    class Router:
        def resolve(self, **kwargs):
            from backend.app.research.application.model_router import ModelChoice
            return ModelChoice("fast", "qwen:9b", "static choice")

    adaptive = AdaptiveRoutingService(Router(), scheduler, observation=observation)
    choice, grant = adaptive.resolve(owner_id="owner-a", task_id="task-a", role="search-worker", requested_workers=2)
    assert choice.model == "qwen:9b"
    assert grant.granted == 2
    decision = store.list_routing_decisions(owner_id="owner-a")[0]
    assert decision.chosen_model == "qwen:9b"
    assert decision.features["worker_grant"] == 2
    adaptive.release(grant)


def test_policy_activation_requires_all_gates_and_is_atomic(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    observation = RoutingObservationService(store)
    assert observation.register_shadow_policy(version="p2", profile="balanced", rules=[])
    with pytest.raises(PolicyActivationError):
        observation.activate_policy(version="p2", manual_confirmation=False, evidence_id="fake")
    with pytest.raises(PolicyActivationError):
        observation.activate_policy(version="p2", manual_confirmation=True, quality_gate=True, resource_gate=True)
    with pytest.raises(PolicyActivationError):
        observation.activate_policy(version="p2", manual_confirmation=True, evidence_id="fake")
    with pytest.raises(PolicyActivationError):
        observation.activate_policy(version="p2", manual_confirmation=True, gate_evidence={"passed": True})
    decision = observation.record_decision(
        owner_id="owner-a", task_type="search_catalog", features={}, candidate_models=["m"],
        chosen_model="m", reason="rule", policy_version="p2",
    )
    observation.record_outcome(owner_id="owner-a", decision_id=decision.decision_id, schema_valid=True, quality_score=0.9)
    evidence = observation.issue_activation_evidence(version="p2", probe=FakeProbe(cap=1))
    active = observation.activate_policy(version="p2", manual_confirmation=True, evidence_id=evidence["evidence_id"])
    assert active["status"] == "active"
    assert store.get_routing_policy("p2")["status"] == "active"


def test_policy_activation_retires_previous_active_in_one_transition(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    observation = RoutingObservationService(store)
    assert observation.register_shadow_policy(version="p1", profile="balanced", rules=[])
    decision = observation.record_decision(owner_id="owner-a", task_type="search_catalog", features={}, candidate_models=["m"], chosen_model="m", reason="rule", policy_version="p1")
    observation.record_outcome(owner_id="owner-a", decision_id=decision.decision_id, schema_valid=True, quality_score=0.9)
    evidence = observation.issue_activation_evidence(version="p1", probe=FakeProbe(cap=1))
    assert observation.activate_policy(version="p1", manual_confirmation=True, evidence_id=evidence["evidence_id"])["status"] == "active"
    assert observation.register_shadow_policy(version="p2", profile="balanced", rules=[])
    decision = observation.record_decision(owner_id="owner-a", task_type="search_catalog", features={}, candidate_models=["m"], chosen_model="m", reason="rule", policy_version="p2")
    observation.record_outcome(owner_id="owner-a", decision_id=decision.decision_id, schema_valid=True, quality_score=0.9)
    evidence = observation.issue_activation_evidence(version="p2", probe=FakeProbe(cap=1))
    assert observation.activate_policy(version="p2", manual_confirmation=True, evidence_id=evidence["evidence_id"])["status"] == "active"
    assert store.get_routing_policy("p1")["status"] == "retired"


def test_policy_threshold_cannot_be_lowered_by_evidence_request(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    observation = RoutingObservationService(store)
    assert observation.register_shadow_policy(
        version="thresholded", profile="balanced", rules=[],
        thresholds={"min_samples": 1, "min_quality_score": 0.9, "min_schema_valid_rate": 1.0},
    )
    decision = observation.record_decision(
        owner_id="owner-a", task_type="search_catalog", features={}, candidate_models=["m"],
        chosen_model="m", reason="rule", policy_version="thresholded",
    )
    observation.record_outcome(owner_id="owner-a", decision_id=decision.decision_id, schema_valid=True, quality_score=0.0)
    with pytest.raises(PolicyActivationError) as exc_info:
        observation.issue_activation_evidence(
            version="thresholded", probe=FakeProbe(cap=1), min_quality_score=0.0,
        )
    assert exc_info.value.code == "QUALITY_GATE_FAILED"


def test_model_router_legacy_signature_remains_compatible():
    from backend.app.research.application.model_router import ModelRouter
    router = ModelRouter(available_models_provider=lambda: ["qwen:9b"])
    assert router.resolve(role="search-worker").model == "qwen:9b"


def test_activation_api_keeps_shadow_policy_behind_explicit_gates(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from backend.app.api.routes_research_routing import router
    from fastapi import FastAPI

    store = ResearchStore(tmp_path / "research.sqlite3")
    observation = RoutingObservationService(store)
    observation.register_shadow_policy(version="p2", profile="balanced", rules=[])
    monkeypatch.setattr("backend.app.api.routes_research_routing.build_research_store", lambda: store)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.post("/research-routing/policies/p2/activate", json={"manual_confirmation": False})
    assert response.status_code == 409
    response = client.post("/research-routing/policies/p2/activate", json={"manual_confirmation": True, "quality_gate": True, "resource_gate": True})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GATE_EVIDENCE_REQUIRED"
