"""Spec032：`/api/papers/sources*` 三个端点的回归测试。

锁定 Spec032 的边界：
- 来源集合由服务端受控，调用方不能新增来源。
- `health` 为配置级、脱敏、无下载副作用（不允许出现主机路径 / 密钥 / Prompt）。
- 内置必需源不允许通过外部输入启停 → 409；未知来源 → 404。
- `sync` 只接受受控年度单元，不接受任意 URL / host（SSRF）。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.api import routes_paper
from backend.app.api.routes_paper import _validate_sync_years
from backend.app.main import app
from backend.app.paper_discovery.infrastructure.source_registry import (
    REQUIRED_SOURCE_IDS,
    SourceRegistry,
)


@pytest.fixture()
def client(monkeypatch):
    """启用 paper discovery 后的测试客户端（每个用例重置注册表单例）。"""
    monkeypatch.setattr(routes_paper, "_paper_discovery_enabled", lambda: True)
    monkeypatch.setattr(routes_paper, "_SOURCE_REGISTRY_SINGLETON", None)
    return TestClient(app)


def test_patch_toggle_is_visible_to_later_requests(client):
    """启停必须对后续请求可见（注册表按进程共享，不是每请求新建）。"""
    assert client.patch("/api/papers/sources/openalex", json={"enabled": False}).status_code == 200
    sources = client.get("/api/papers/sources").json()["sources"]
    state = {item["source_id"]: item["enabled"] for item in sources}
    assert state["openalex"] is False
    assert state["usenix"] is True


def test_get_sources_returns_registered_sources(client):
    response = client.get("/api/papers/sources")
    assert response.status_code == 200
    payload = response.json()
    ids = {item["source_id"] for item in payload["sources"]}
    assert {"usenix", "dblp", "ieee_sp", "ccs", "ndss", "openalex", "crossref"} <= ids
    assert payload["count"] == len(payload["sources"])
    verified_years = {item["source_id"]: item["verified_years"] for item in payload["sources"]}
    assert verified_years["usenix"] == [2024]
    assert verified_years["ieee_sp"] == []
    assert verified_years["ccs"] == []
    assert verified_years["ndss"] == []


def test_get_sources_health_is_configuration_level_and_sanitized(client):
    """health 不得含主机路径、密钥、Prompt，且明确未发起网络探测。"""
    response = client.get("/api/papers/sources")
    assert response.status_code == 200
    body = response.text.lower()
    for forbidden in ("secret", "token", "prompt", "password", "/users/", "/home/"):
        assert forbidden not in body
    for source in response.json()["sources"]:
        assert source["health"]["network_probe"] == "not_performed"


def test_get_sources_filter_matches_id_or_kind(client):
    response = client.get("/api/papers/sources", params={"filter": "NDSS"})
    assert response.status_code == 200
    ids = [item["source_id"] for item in response.json()["sources"]]
    assert ids == ["ndss"]


def test_get_sources_rejects_overlong_filter(client):
    assert client.get("/api/papers/sources", params={"filter": "x" * 65}).status_code == 400


def test_get_sources_returns_503_when_discovery_disabled(monkeypatch):
    monkeypatch.setattr(routes_paper, "_paper_discovery_enabled", lambda: False)
    assert TestClient(app).get("/api/papers/sources").status_code == 503


def test_patch_unknown_source_is_404(client):
    assert client.patch("/api/papers/sources/nope", json={"enabled": False}).status_code == 404


def test_patch_can_toggle_non_required_source(client):
    response = client.patch("/api/papers/sources/openalex", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["source"]["enabled"] is False


@pytest.mark.parametrize("source_id", sorted(REQUIRED_SOURCE_IDS))
def test_patch_required_source_is_forbidden(client, source_id):
    """内置必需源不允许通过外部输入启停 → 409。"""
    response = client.patch(f"/api/papers/sources/{source_id}", json={"enabled": False})
    assert response.status_code == 409
    # routes_paper 的错误体是扁平结构（与该文件其它端点一致）。
    assert response.json()["code"] == "SOURCE_TOGGLE_FORBIDDEN"


def test_patch_rejects_unknown_body_fields(client):
    """extra=forbid：不接受模型外的字段。"""
    response = client.patch("/api/papers/sources/openalex", json={"enabled": True, "authority_rank": 1})
    assert response.status_code == 422


def test_sync_accepts_controlled_year_scope(client):
    source_id = "usenix"
    response = client.post(
        f"/api/papers/sources/{source_id}/sync", json={"scope": {"years": [2024, 2025]}}
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["entrypoint"] == "source_registry.adapter"
    assert payload["scope"]["years"] == [2024, 2025]


def test_sync_rejects_arbitrary_host_or_url_in_scope(client):
    """SSRF：scope 只接受年度单元，任意 host / URL 一律拒收。"""
    source_id = "usenix"
    response = client.post(
        f"/api/papers/sources/{source_id}/sync",
        json={"scope": {"years": [2024], "url": "http://evil.example.com"}},
    )
    assert response.status_code == 422


def test_sync_rejects_out_of_range_years(client):
    source_id = "usenix"
    response = client.post(
        f"/api/papers/sources/{source_id}/sync", json={"scope": {"years": [1]}}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_SCOPE"


def test_sync_rejects_oversized_scope(client):
    source_id = "usenix"
    response = client.post(
        f"/api/papers/sources/{source_id}/sync", json={"scope": {"years": list(range(1900, 1960))}}
    )
    assert response.status_code == 400


def test_sync_unknown_source_is_404(client):
    assert client.post("/api/papers/sources/nope/sync", json={}).status_code == 404


def test_sync_without_registry_adapter_is_409(client, monkeypatch):
    """registry adapter 不可用时不得伪造 queued，也不得启动调度。"""
    def unavailable_adapter(self, source_id, **kwargs):
        raise LookupError(f"no controlled adapter for {source_id}")

    monkeypatch.setattr(SourceRegistry, "adapter", unavailable_adapter)
    monkeypatch.setattr(
        routes_paper,
        "submit_catalog_source_sync",
        lambda *_args, **_kwargs: pytest.fail("unavailable adapter must not be scheduled"),
    )
    response = client.post("/api/papers/sources/usenix/sync", json={"scope": {"years": [2024]}})
    assert response.status_code == 409
    assert response.json()["code"] == "SYNC_ENTRYPOINT_UNAVAILABLE"


def test_sync_disabled_source_is_409(client):
    registry = SourceRegistry(disabled_by_config=("ccs",))
    assert registry.get("ccs").enabled is False


def test_validate_sync_years_accepts_empty_scope():
    assert _validate_sync_years([]) is None
