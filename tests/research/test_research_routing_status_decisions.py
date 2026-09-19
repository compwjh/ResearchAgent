"""Spec 031 Task07 — GET /status 与 GET /decisions 端点契约测试。

覆盖：
- /status 200：含 active policy / 模型健康 / 资源摘要。
- /status 探针失败 → 503 且响应体含降级状态（degraded + active_policy）。
- /decisions 正常返回 + owner 隔离（别人的决策读不到）。
- /decisions 非法参数（limit/cursor/filter）→ 400 稳定错误码。
- /decisions 脱敏：响应里不含 prompt/response/reasoning/messages 等敏感键名。

独立临时库 + monkeypatch，避免与并行 agent / 在线服务冲突。
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.api import routes_research_routing
from backend.app.main import app
from backend.app.platform.ollama import (
    ResourceProbeUnavailable,
    ResourceSnapshot,
)
from backend.app.research.application.routing_observation import (
    RoutingDecision,
    RoutingObservationService,
)
from backend.app.research.infrastructure.research_store import ResearchStore

SENSITIVE_KEYS = {
    "prompt", "response", "reasoning", "messages", "answer", "completion",
    "thought", "chain", "token", "secret", "credential", "authorization",
    "cookie", "api_key", "access_key", "lease_token",
}


class FakeProbe:
    """可注入的 ResourceProbe 替身：默认健康，可强制探针失败。"""

    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self._snap = ResourceSnapshot(
            available_memory_bytes=16 * 1024**3,
            model_footprint_bytes=2 * 1024**3,
            loaded_model_count=2,
        )

    def snapshot(self) -> ResourceSnapshot:
        if self.fail:
            raise ResourceProbeUnavailable("probe unavailable in test")
        return self._snap

    def max_safe_workers(self):
        if self.fail:
            return 1, "RESOURCE_PROBE_FAILED"
        usable = self._snap.available_memory_bytes * 0.8
        return max(1, int(usable // self._snap.model_footprint_bytes)), None


@pytest.fixture
def store():
    directory = Path(tempfile.mkdtemp(prefix="spec031-routing-"))
    db_path = directory / "research.sqlite3"
    return ResearchStore(database_path=db_path)


@pytest.fixture
def client(store):
    with patch.object(routes_research_routing, "build_research_store", lambda: store), \
         patch.object(routes_research_routing, "ResourceProbe", lambda: FakeProbe()), \
         patch.object(routes_research_routing, "get_available_models", lambda: ["m1", "m2", "m3"]), \
         patch.object(routes_research_routing, "read_loaded_models", lambda: [{"name": "m1"}]):
        yield TestClient(app)


def _seed_active_policy(store: ResearchStore) -> None:
    svc = RoutingObservationService(store)
    svc.register_shadow_policy(
        version="v1",
        profile="balanced",
        rules=[{"task_type": "search", "model": "m1", "reason": "fast path"}],
        thresholds={"min_samples": 1, "min_quality_score": 0.8, "min_schema_valid_rate": 1.0},
        status="shadow",
    )
    store.activate_routing_policy("v1")


def _seed_decisions(store: ResearchStore, owner: str, n: int, base_ts: str) -> None:
    for i in range(n):
        decision = RoutingDecision(
            decision_id=f"{owner}-d{i}",
            owner_id=owner,
            task_type="search" if i % 2 == 0 else "summarize",
            features={"role": "research", "idx": i},
            candidate_models=["m1", "m2"],
            chosen_model="m1",
            reason=f"owner-reason:{owner}",
            policy_version="v1",
            created_at=f"{base_ts[:-1]}{i}Z",
        )
        store.save_routing_decision(decision)


def _walk_keys(obj):
    found = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            found.add(str(k).lower())
            found |= _walk_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            found |= _walk_keys(item)
    return found


@pytest.fixture
def client_failed_probe(store):
    with patch.object(routes_research_routing, "build_research_store", lambda: store), \
         patch.object(routes_research_routing, "ResourceProbe", lambda: FakeProbe(fail=True)), \
         patch.object(routes_research_routing, "get_available_models", lambda: ["m1"]), \
         patch.object(routes_research_routing, "read_loaded_models", lambda: []):
        yield TestClient(app)


def test_status_200_with_active_policy(client, store):
    _seed_active_policy(store)
    resp = client.get("/api/research-routing/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["active_policy"] is not None
    assert body["active_policy"]["version"] == "v1"
    assert body["active_policy"]["status"] == "active"
    assert "rules" in body["active_policy"]
    assert body["active_policy"]["profile"] == "balanced"
    # 严禁输出 host 路径 / token / prompt 等
    assert "lease_token" not in str(body)
    assert body["model_health"]["healthy"] is True
    assert body["model_health"]["available_models"] == 3
    assert body["resource"]["available_memory_bytes"] == 16 * 1024**3
    assert body["resource"]["max_safe_workers"] >= 1


def test_status_probe_failure_returns_503_with_degraded_body(client_failed_probe, store):
    _seed_active_policy(store)
    resp = client_failed_probe.get("/api/research-routing/status")
    assert resp.status_code == 503
    body = resp.json()
    # 503 但仍含降级状态：degraded 标记 + 仍可读取的 active_policy
    assert body.get("degraded") is True
    assert body["error"]["code"] == "RESOURCE_PROBE_FAILED"
    assert body["resource"] is None
    assert body["model_health"] is None
    # 探针坏了，但策略状态照常返回，可区分「探针坏」与「服务坏」
    assert body["active_policy"] is not None
    assert body["active_policy"]["version"] == "v1"


def test_decisions_owner_isolation(client, store):
    _seed_decisions(store, "owner_a", 2, base_ts="2026-09-19T00:00:0")
    _seed_decisions(store, "owner_b", 1, base_ts="2026-09-19T01:00:0")
    # 给 owner_b 一个可区分的 reason
    store.save_routing_decision(RoutingDecision(
        decision_id="owner-b-other", owner_id="owner_b", task_type="summarize",
        features={"x": 1}, candidate_models=["m1"], chosen_model="m1",
        reason="ownerB-confidential", policy_version="v1",
        created_at="2026-09-19T02:00:00Z",
    ))

    resp_a = client.get("/api/research-routing/decisions?owner=owner_a")
    assert resp_a.status_code == 200
    a_body = resp_a.json()
    assert a_body["owner"] == "owner_a"
    assert len(a_body["decisions"]) == 2
    # owner_a 只能看到自己的决策
    assert {d["reason"] for d in a_body["decisions"]} == {"owner-reason:owner_a"}
    assert "ownerB-confidential" not in {d["reason"] for d in a_body["decisions"]}

    resp_b = client.get("/api/research-routing/decisions?owner=owner_b")
    b_body = resp_b.json()
    assert len(b_body["decisions"]) == 2
    assert "ownerB-confidential" in {d["reason"] for d in b_body["decisions"]}
    # owner_a 的决策不能泄漏到 owner_b 的响应里
    assert "owner-reason:owner_a" not in {d["reason"] for d in b_body["decisions"]}


def test_decisions_redacted_no_sensitive_keys(client, store):
    _seed_decisions(store, "owner_a", 1, base_ts="2026-09-19T00:00:0")
    resp = client.get("/api/research-routing/decisions?owner=owner_a")
    assert resp.status_code == 200
    body = resp.json()
    keys = _walk_keys(body)
    leaked = SENSITIVE_KEYS & keys
    assert not leaked, f"响应泄漏敏感键名: {leaked}"
    # 既有契约字段必须存在
    item = body["decisions"][0]
    for field in ("task_type", "features", "candidate_models", "chosen_model", "reason", "policy_version", "created_at"):
        assert field in item


def test_decisions_invalid_limit(client, store):
    _seed_decisions(store, "owner_a", 1, base_ts="2026-09-19T00:00:0")
    for bad in ("0", "200", "abc"):
        resp = client.get(f"/api/research-routing/decisions?owner=owner_a&limit={bad}")
        assert resp.status_code == 400, f"limit={bad} 应 400"
        assert resp.json()["error"]["code"] == "INVALID_LIMIT"


def test_decisions_invalid_cursor(client, store):
    _seed_decisions(store, "owner_a", 1, base_ts="2026-09-19T00:00:0")
    resp = client.get("/api/research-routing/decisions?owner=owner_a&cursor=@@not-a-cursor@@")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_CURSOR"


def test_decisions_invalid_filter(client, store):
    _seed_decisions(store, "owner_a", 1, base_ts="2026-09-19T00:00:0")
    resp = client.get("/api/research-routing/decisions?owner=owner_a&filter=%20%20")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_FILTER"


def test_decisions_cursor_pagination(client, store):
    _seed_decisions(store, "owner_a", 3, base_ts="2026-09-19T00:00:0")
    first = client.get("/api/research-routing/decisions?owner=owner_a&limit=2")
    assert first.status_code == 200
    f = first.json()
    assert len(f["decisions"]) == 2
    assert f["next_cursor"] is not None
    seen_created = {d["created_at"] for d in f["decisions"]}

    second = client.get(f"/api/research-routing/decisions?owner=owner_a&limit=2&cursor={f['next_cursor']}")
    assert second.status_code == 200
    s = second.json()
    assert len(s["decisions"]) == 1
    assert s["next_cursor"] is None
    seen_created |= {d["created_at"] for d in s["decisions"]}
    # 两页累计覆盖 3 条、无重叠（created_at 唯一）
    assert len(seen_created) == 3
