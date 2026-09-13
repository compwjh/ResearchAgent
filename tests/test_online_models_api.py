"""GET /api/models 端点契约测试（spec-035 Task04）。

覆盖：返回结构（current/groups/local/online 字段与层级）、分组正确、
Ollama 不可达降级为 200 + 空 local 组、无线上配置 online 为空、当前模型回退、
当前为线上模型。全部用 monkeypatch 注入 routes_models 命名空间函数与 config.MODEL_NAME，
绝不发真实网络请求；并断言响应体不含任何 api_key 片段。
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.platform import config
from backend.app.platform.model_catalog import OnlineModelEntry

# 测试用假 Key（绝不可能是真实凭据）
FAKE_KEY = "sk-test-fake-key-not-real"


def _online_entry():
    return OnlineModelEntry(
        id="deepseek:deepseek-chat",
        provider="deepseek",
        model="deepseek-chat",
        display_name="deepseek:deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key=FAKE_KEY,
        source="online",
    )


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    # 默认：本地两个模型，线上一个已配置模型，默认当前为本地首个
    monkeypatch.setattr(
        "backend.app.api.routes_models.get_available_models",
        lambda: ["qwen3.8:27b-mlx", "qwen3.5:9b"],
    )
    monkeypatch.setattr(
        "backend.app.api.routes_models.get_online_models",
        lambda: [_online_entry()],
    )
    monkeypatch.setattr(config, "MODEL_NAME", "qwen3.8:27b-mlx")
    # 默认不探测；探测被 mock 为 ready（用于验证 probe=1 触发逻辑）
    monkeypatch.setattr(
        "backend.app.api.routes_models.probe_online_model",
        lambda entry, *, timeout=8.0: "ready",
    )
    yield


def test_structure_and_groups(client):
    r = client.get("/api/models")
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"current", "groups"}
    assert data["current"] == "qwen3.8:27b-mlx"
    assert [g["source"] for g in data["groups"]] == ["local", "online"]
    local = next(g for g in data["groups"] if g["source"] == "local")
    online = next(g for g in data["groups"] if g["source"] == "online")
    assert local["label"] == "端侧模型"
    assert online["label"] == "线上模型"
    assert len(local["models"]) == 2
    assert len(online["models"]) == 1


def test_local_model_fields(client):
    data = client.get("/api/models").json()
    m = data["groups"][0]["models"][0]
    assert m == {
        "id": "qwen3.8:27b-mlx",
        "name": "qwen3.8:27b-mlx",
        "source": "local",
        "provider": None,
        "display_name": "qwen3.8:27b-mlx",
        "current": True,
        "status": "ready",
        "capabilities": {"reasoning_efforts": ["off", "low", "medium", "high", "xhigh"]},
    }


def test_online_model_fields_no_probe(client):
    data = client.get("/api/models").json()
    m = data["groups"][1]["models"][0]
    assert m["id"] == "deepseek:deepseek-chat"
    assert m["name"] == "deepseek-chat"
    assert m["source"] == "online"
    assert m["provider"] == "deepseek"
    assert m["display_name"] == "deepseek:deepseek-chat"
    assert m["current"] is False
    # 不带 probe：线上 status 为 unknown
    assert m["status"] == "unknown"
    assert m["capabilities"] == {"reasoning_efforts": None}


def test_probe_sets_status_and_invokes(client, monkeypatch):
    calls = []
    def fake_probe(entry, *, timeout=8.0):
        calls.append(entry.id)
        return "ready"
    monkeypatch.setattr("backend.app.api.routes_models.probe_online_model", fake_probe)
    data = client.get("/api/models?probe=1").json()
    m = data["groups"][1]["models"][0]
    assert m["status"] == "ready"
    assert calls == ["deepseek:deepseek-chat"]


def test_ollama_unreachable_downgrades_to_200_empty_local(client, monkeypatch):
    def _raise(*_a, **_k):
        raise RuntimeError("ollama down")
    monkeypatch.setattr("backend.app.api.routes_models.get_available_models", _raise)
    r = client.get("/api/models")
    assert r.status_code == 200
    data = r.json()
    local = next(g for g in data["groups"] if g["source"] == "local")
    assert local["models"] == []
    online = next(g for g in data["groups"] if g["source"] == "online")
    assert online["models"]  # 线上仍正常


def test_no_online_config_empty_online_group(client, monkeypatch):
    monkeypatch.setattr("backend.app.api.routes_models.get_online_models", lambda: [])
    data = client.get("/api/models").json()
    online = next(g for g in data["groups"] if g["source"] == "online")
    assert online["models"] == []
    local = next(g for g in data["groups"] if g["source"] == "local")
    assert local["models"]  # 端侧仍正常


def test_current_fallback_when_default_missing(client, monkeypatch):
    monkeypatch.setattr(config, "MODEL_NAME", "does-not-exist:xyz")
    data = client.get("/api/models").json()
    # 不在可用列表内 → 回退第一个可用（local 第一个）
    assert data["current"] == "qwen3.8:27b-mlx"
    assert data["groups"][0]["models"][0]["current"] is True


def test_current_none_when_no_models(client, monkeypatch):
    monkeypatch.setattr("backend.app.api.routes_models.get_available_models", lambda: [])
    monkeypatch.setattr("backend.app.api.routes_models.get_online_models", lambda: [])
    monkeypatch.setattr(config, "MODEL_NAME", "x")
    data = client.get("/api/models").json()
    assert data["current"] is None
    assert all(g["models"] == [] for g in data["groups"])


def test_current_is_online_model(client, monkeypatch):
    monkeypatch.setattr(config, "MODEL_NAME", "deepseek:deepseek-chat")
    data = client.get("/api/models").json()
    assert data["current"] == "deepseek:deepseek-chat"
    online = next(g for g in data["groups"] if g["source"] == "online")
    assert online["models"][0]["current"] is True


def test_response_body_contains_no_api_key(client):
    body = client.get("/api/models").text
    assert FAKE_KEY not in body
