"""spec-035 Task05 — 各模块无缝适配：线上模型并集校验 + reasoning 降级 + direct 路由回退。

覆盖（按任务书边界）：
- is_model_available 并集语义：线上 id / 本地名 / 不存在名 / 注册表清空 /
  Ollama 不可达但线上可用 / 线上可用但 Ollama 不可达；
- 对话 _validate_model 对线上模型放行，且 503/404 文案逐字不变；
- reasoning-options 对线上模型返回 200 + {supported:false, efforts:[]}（不 404 / 不 MODEL_NOT_FOUND）；
- chat_runner 在 route=direct 且模型为线上时强制回退 langchain 路由；
- GET /api/models 当前模型为线上模型；
- POST /api/chat 传入线上 id（含 Ollama 不可达场景）不再被 400 拒绝。

全部用 monkeypatch 注入 env / 路由命名空间函数，不依赖真实网络与真实 Key。
"""

from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.api import routes_chat, routes_conversations
from backend.app.api.routes_conversations import _validate_model
from backend.app.chat.application.chat_runner import run_chat
from backend.app.main import app
from backend.app.platform import config
from backend.app.platform.model_catalog import OnlineModelEntry, is_model_available

FAKE_KEY = "sk-test-fake-key-not-real"
ONLINE_ID = "deepseek:deepseek-chat"
LOCAL_NAME = "qwen3.5:9b"


def _raise_connect(*_a, **_k):
    raise httpx.ConnectError("ollama down")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    # 隔离真实 .env；默认：清空线上注册表，本地仅 LOCAL_NAME 可用。
    monkeypatch.delenv("ONLINE_MODELS", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.setattr(
        "backend.app.platform.ollama.get_available_models", lambda: [LOCAL_NAME]
    )
    # routes_* 通过 `from ... import get_available_models` 绑定独立名字，需分别 patch。
    monkeypatch.setattr(routes_conversations, "get_available_models", lambda: [LOCAL_NAME])
    monkeypatch.setattr(routes_chat, "get_available_models", lambda: [LOCAL_NAME])
    yield


def _enable_online(monkeypatch, online_id=ONLINE_ID):
    provider, _m = online_id.split(":", 1)
    monkeypatch.setenv("ONLINE_MODELS", online_id)
    monkeypatch.setenv(f"{provider.upper()}_API_KEY", FAKE_KEY)


@pytest.fixture
def client():
    return TestClient(app)


# ---------- 1) is_model_available：本地 ∪ 线上 并集 ----------


def test_is_available_online_hit(monkeypatch):
    _enable_online(monkeypatch)
    assert is_model_available(ONLINE_ID) is True


def test_is_available_local_hit():
    assert is_model_available(LOCAL_NAME) is True


def test_is_available_nonexistent_is_false():
    assert is_model_available("nope:model") is False


def test_is_available_registry_cleared_online_false():
    # fixture 已清空 ONLINE_MODELS：未注册的线上 id 不可用
    assert is_model_available(ONLINE_ID) is False


def test_is_available_registry_cleared_local_still_true():
    assert is_model_available(LOCAL_NAME) is True


def test_is_available_ollama_unreachable_but_online_available(monkeypatch):
    # Ollama 不可达（本地枚举抛异常），但线上注册表命中 → True
    monkeypatch.setattr(
        "backend.app.platform.ollama.get_available_models", _raise_connect
    )
    _enable_online(monkeypatch)
    assert is_model_available(ONLINE_ID) is True


def test_is_available_online_available_but_ollama_unreachable(monkeypatch):
    # 与上一例同义：线上可用 + 本地不可达 → True
    monkeypatch.setattr(
        "backend.app.platform.ollama.get_available_models", _raise_connect
    )
    _enable_online(monkeypatch)
    assert is_model_available(ONLINE_ID) is True


def test_is_available_ollama_unreachable_no_online_false(monkeypatch):
    # Ollama 不可达且无线上模型 → False
    monkeypatch.setattr(
        "backend.app.platform.ollama.get_available_models", _raise_connect
    )
    assert is_model_available(LOCAL_NAME) is False


# ---------- 2) 对话 _validate_model：线上模型放行，错误码文案不变 ----------


def test_validate_model_accepts_online_model(monkeypatch):
    _enable_online(monkeypatch)
    # 本地列表不含线上模型；靠 is_model_available 并集放行，不应抛异常
    monkeypatch.setattr(routes_conversations, "get_available_models", lambda: ["local-model"])
    _validate_model(ONLINE_ID)


def test_validate_model_accepts_local_model():
    _validate_model(LOCAL_NAME)  # 本地列表包含，直接放行


def test_validate_model_rejects_missing_local_with_404():
    with pytest.raises(HTTPException) as exc:
        _validate_model("does-not-exist:xyz")
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "MODEL_NOT_FOUND"
    assert exc.value.detail["retryable"] is False


def test_validate_model_ollama_down_but_online_available(monkeypatch):
    _enable_online(monkeypatch)
    monkeypatch.setattr(routes_conversations, "get_available_models", _raise_connect)
    # Ollama 不可达但线上模型可用：不应抛 503
    _validate_model(ONLINE_ID)


def test_validate_model_ollama_down_missing_is_503(monkeypatch):
    monkeypatch.setattr(routes_conversations, "get_available_models", _raise_connect)
    with pytest.raises(HTTPException) as exc:
        _validate_model("does-not-exist:xyz")
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "MODEL_UNAVAILABLE"
    assert exc.value.detail["retryable"] is True


# ---------- 3) reasoning-options：线上模型返回 200 + 不支持（不 404） ----------


def test_reasoning_options_online_returns_200_unsupported(client, monkeypatch):
    _enable_online(monkeypatch)
    resp = client.get(f"/api/chat/reasoning-options?model={ONLINE_ID}")
    assert resp.status_code == 200
    assert resp.json() == {"supported": False, "efforts": []}


def test_reasoning_options_local_still_404_when_missing(client):
    # 本地模型且不在可用列表：保持 404（不受线上逻辑影响）
    resp = client.get("/api/chat/reasoning-options?model=does-not-exist:xyz")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "MODEL_NOT_FOUND"


# ---------- 4) chat_runner：direct 路由遇线上模型强制回退 langchain ----------


def test_run_chat_direct_falls_back_for_online_model(monkeypatch):
    _enable_online(monkeypatch)
    # 生成器未迭代则不调用 create_chat_model；路由应已回退为 langchain。
    with patch("backend.app.platform.ollama.create_chat_model") as mock_create:
        run = run_chat("hi", ONLINE_ID, route="direct")
    assert run.route == "langchain"
    mock_create.assert_not_called()


def test_run_chat_direct_kept_for_local_model(monkeypatch):
    monkeypatch.setattr(
        "backend.app.platform.ollama.get_available_models", lambda: [LOCAL_NAME]
    )

    class _DummyStream:
        result = None

        def __iter__(self):
            return iter([])

    monkeypatch.setattr(
        "backend.app.chat.application.chat_runner.chat_direct_stream",
        lambda *a, **k: _DummyStream(),
    )
    run = run_chat("hi", LOCAL_NAME, route="direct")
    assert run.route == "direct"


# ---------- 5) GET /api/models：当前模型为线上模型 ----------


def test_models_current_is_online_model(client, monkeypatch):
    _enable_online(monkeypatch)
    monkeypatch.setattr(
        "backend.app.api.routes_models.get_online_models",
        lambda: [
            OnlineModelEntry(
                id=ONLINE_ID,
                provider="deepseek",
                model="deepseek-chat",
                display_name=ONLINE_ID,
                base_url="https://api.deepseek.com",
                api_key=FAKE_KEY,
                source="online",
            )
        ],
    )
    monkeypatch.setattr("backend.app.api.routes_models.get_available_models", lambda: [])
    monkeypatch.setattr(config, "MODEL_NAME", ONLINE_ID)
    data = client.get("/api/models").json()
    assert data["current"] == ONLINE_ID


# ---------- 6) POST /api/chat：线上 id 不再被 400 拒绝 ----------


class _FakeRule:
    enabled = False
    content = ""


class _FakeMemoryRepo:
    def get_system_rule(self, owner_id):
        return _FakeRule()


class FakeRun:
    route = "langchain"
    result = None

    @property
    def events(self):
        yield {"type": "token", "content": "答复"}


def test_api_chat_accepts_online_model(client, monkeypatch):
    _enable_online(monkeypatch)
    # 本地列表不含线上模型：若无并集校验会判 400。靠 is_model_available 放行。
    monkeypatch.setattr(routes_chat, "get_available_models", lambda: ["local-model"])
    monkeypatch.setattr(
        "backend.app.api.routes_chat.get_provider",
        lambda name: _FakeMemoryRepo() if name == "memory_repository" else None,
    )
    with patch("backend.app.api.routes_chat.run_chat", return_value=FakeRun()):
        resp = client.post("/api/chat", json={"question": "hi", "model": ONLINE_ID})
    assert resp.status_code == 200


def test_api_chat_online_model_when_ollama_unreachable(client, monkeypatch):
    _enable_online(monkeypatch)
    # Ollama 不可达（直接调用抛 ConnectError），但线上模型仍应放行（不 502 / 不 400）。
    monkeypatch.setattr(routes_chat, "get_available_models", _raise_connect)
    monkeypatch.setattr(
        "backend.app.api.routes_chat.get_provider",
        lambda name: _FakeMemoryRepo() if name == "memory_repository" else None,
    )
    with patch("backend.app.api.routes_chat.run_chat", return_value=FakeRun()):
        resp = client.post("/api/chat", json={"question": "hi", "model": ONLINE_ID})
    assert resp.status_code == 200
