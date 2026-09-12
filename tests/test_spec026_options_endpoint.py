"""Spec 026 Task 03 — 能力接口 source/refresh 与发消息路径档位分流（后端契约测试）。

覆盖主会话裁决 A/B 与 spec 026 §端点/接口、边界 B1/B2/B4：

- options 端点：Ollama 不可达 → 200 + ``unknown``（不是 503，也不是 404）；
- options 端点：模型列表可用但模型不在其中 → 404 ``MODEL_NOT_FOUND``（且不触发探测）；
- options 端点：``stale`` 原样透出旧 ``supported_efforts`` 与旧 ``cached_at``；
- options 端点：``refresh=1`` 真正绕过缓存重新探测；
- 发消息路径：能力 ``unknown`` + ``off`` 放行；``unknown`` + 非 ``off`` → 503
  ``MODEL_CAPABILITIES_UNAVAILABLE``（**不是** 409）；
- 发消息路径：``stale`` 按**旧**能力集判定（在集合内放行，不在集合内 409）；
- 发消息路径：能力已知且档位不在 ``supported_efforts`` → 409 ``REASONING_EFFORT_UNSUPPORTED``。
"""

import json
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.api import routes_conversations
from backend.app.main import app
from backend.app.platform import ollama
from backend.app.platform.ollama import ReasoningCapabilities

STALE_CAPS = ReasoningCapabilities(
    "model", ("off", "low"), "low", "ollama_probe", "2026-09-01T00:00:00+00:00", {}
)


@pytest.fixture(autouse=True)
def _isolated_capability_cache():
    ollama.clear_reasoning_capability_cache()
    yield
    ollama.clear_reasoning_capability_cache()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def isolated_db_path():
    """独立 SQLite 路径。

    本仓库沙箱会拒绝 pytest ``tmp_path`` 根目录的 mkdir（表现为 pytest 9 内部
    ``assert not self._finalizers`` 的 setup error），因此这里用 ``tempfile.mkdtemp``
    自建目录并自行清理，与 ``tmp_path`` 语义等价且不依赖沙箱临时目录策略。
    """
    directory = Path(tempfile.mkdtemp(prefix="spec026-task03-"))
    try:
        yield directory / "memory.sqlite3"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _probe_unknown(model):
    return ReasoningCapabilities(str(model), (), None, "unknown", "", {})


def _probe_known(model):
    return ReasoningCapabilities(
        str(model), ("off", "low"), "low", "ollama_probe", "2026-09-12T00:00:00+00:00", {}
    )


def _seed_expired_cache(model: str, caps: ReasoningCapabilities) -> None:
    """写入一条远超 300s TTL 的旧缓存（模拟「探测失败但有旧结果」）。"""
    ollama._capability_cache[model] = (time.monotonic() - 10_000.0, caps)


def _events(text: str):
    return [json.loads(line[6:]) for line in text.split("\n\n") if line.startswith("data: ")]


class FakeRun:
    route = "langchain"
    result = None

    @property
    def events(self):
        yield {"type": "token", "content": "答复"}


class _NoopWorker:
    def enqueue(self, *args, **kwargs):
        return None

    def enqueue_session(self, *args, **kwargs):
        return None


# --- 1) Ollama 不可达：200 + unknown（不判 404、不返回 503） -------------------


def test_options_ollama_unreachable_returns_unknown_200(client, monkeypatch):
    def _down():
        raise httpx.ConnectError("ollama down")

    monkeypatch.setattr(routes_conversations, "get_available_models", _down)
    monkeypatch.setattr(ollama, "probe_reasoning_capabilities", _probe_unknown)

    response = client.get("/api/chat/reasoning-options?model=model")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "unknown"
    assert body["supported_efforts"] == []
    assert body["default_effort"] is None
    assert body["model"] == "model"
    # 能力未知时该字段表示「本次尝试时间」，不得为空，也不得被当成缓存时间。
    assert body["cached_at"]


def test_options_ollama_unreachable_with_expired_cache_returns_stale_200(client, monkeypatch):
    def _down():
        raise httpx.ConnectError("ollama down")

    _seed_expired_cache("model", STALE_CAPS)
    monkeypatch.setattr(routes_conversations, "get_available_models", _down)
    monkeypatch.setattr(ollama, "probe_reasoning_capabilities", _probe_unknown)

    response = client.get("/api/chat/reasoning-options?model=model")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "stale"
    assert body["supported_efforts"] == ["off", "low"]
    assert body["default_effort"] == "low"
    assert body["cached_at"] == "2026-09-01T00:00:00+00:00"


# --- 2) 模型列表可用但模型不存在：404 MODEL_NOT_FOUND -------------------------


def test_options_model_not_in_available_list_returns_404(client, monkeypatch):
    monkeypatch.setattr(routes_conversations, "get_available_models", lambda: ["other"])

    def _unexpected(*args, **kwargs):
        raise AssertionError("unknown model must be rejected before probing capabilities")

    monkeypatch.setattr(routes_conversations, "get_reasoning_capabilities", _unexpected)

    response = client.get("/api/chat/reasoning-options?model=missing")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "MODEL_NOT_FOUND"
    assert response.json()["detail"]["retryable"] is False


# --- 3) refresh=1 真正绕过缓存 -----------------------------------------------


def test_options_refresh_query_bypasses_cache(client, monkeypatch):
    probed: list[str] = []

    def _probe(model):
        probed.append(model)
        return _probe_known(model)

    monkeypatch.setattr(ollama, "probe_reasoning_capabilities", _probe)
    monkeypatch.setattr(routes_conversations, "get_available_models", lambda: ["m"])

    first = client.get("/api/chat/reasoning-options?model=m").json()
    cached = client.get("/api/chat/reasoning-options?model=m").json()
    refreshed = client.get("/api/chat/reasoning-options?model=m&refresh=1").json()

    assert first["source"] == "ollama_probe"
    assert cached["source"] == "cache"
    assert refreshed["source"] == "ollama_probe"
    assert refreshed["cached_at"] == "2026-09-12T00:00:00+00:00"
    assert probed == ["m", "m"]  # refresh=1 触发了第二次真实探测


# --- 4) 发消息路径：unknown 能力下的档位分流 ---------------------------------


def test_message_path_unknown_capabilities_allows_off(isolated_db_path, monkeypatch):
    monkeypatch.setattr(routes_conversations, "get_available_models", lambda: ["model"])
    monkeypatch.setattr(ollama, "probe_reasoning_capabilities", _probe_unknown)
    monkeypatch.setattr(routes_conversations, "get_memory_analysis_worker", lambda repo: _NoopWorker())
    monkeypatch.setattr(routes_conversations, "get_memory_evolution_worker", lambda repo: _NoopWorker())

    with patch("backend.app.memory.repository.default_database_path", return_value=isolated_db_path):
        client = TestClient(app)
        with patch("backend.app.api.routes_conversations.run_chat", return_value=FakeRun()):
            response = client.post(
                "/api/conversations/messages",
                json={"content": "hi", "model": "model", "reasoning_effort": "off"},
            )

    assert response.status_code == 200
    meta = _events(response.text)[0]
    assert meta["type"] == "meta"
    assert meta["reasoning_effort"] == "off"
    assert meta["capabilities_source"] == "unknown"


def test_message_path_unknown_capabilities_rejects_non_off_with_503(isolated_db_path, monkeypatch):
    monkeypatch.setattr(routes_conversations, "get_available_models", lambda: ["model"])
    monkeypatch.setattr(ollama, "probe_reasoning_capabilities", _probe_unknown)

    with patch("backend.app.memory.repository.default_database_path", return_value=isolated_db_path):
        client = TestClient(app)
        response = client.post(
            "/api/conversations/messages",
            json={"content": "hi", "model": "model", "reasoning_effort": "xhigh"},
        )

        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "MODEL_CAPABILITIES_UNAVAILABLE"
        assert response.json()["detail"]["retryable"] is True
        # 未建空会话（错误发生在任何写入之前）
        assert client.get("/api/conversations").json()["conversations"] == []


@pytest.mark.parametrize("effort", ["off", "low", "medium", "high", "xhigh"])
def test_resolve_request_effort_unknown_allows_only_off(effort):
    with patch.object(ollama, "probe_reasoning_capabilities", _probe_unknown):
        if effort == "off":
            resolution = routes_conversations._resolve_request_effort("model", effort)
            assert resolution.effort == "off"
            assert resolution.provider_value is False
            assert resolution.capabilities.source == "unknown"
        else:
            with pytest.raises(HTTPException) as error:
                routes_conversations._resolve_request_effort("model", effort)
            assert error.value.status_code == 503
            assert error.value.detail["code"] == "MODEL_CAPABILITIES_UNAVAILABLE"
            assert error.value.detail["retryable"] is True


def test_resolve_request_effort_unknown_implicit_request_falls_back_to_off():
    # 请求未携带档位时，后端默认取的 xhigh 是**替用户造的默认值**；能力未知时不能因为
    # 自己造的默认值就把请求拒掉（会复现「模型能力暂时不可用」）。改为回落 off 放行。
    with patch.object(ollama, "probe_reasoning_capabilities", _probe_unknown):
        resolution = routes_conversations._resolve_request_effort("model", None)
    assert resolution.effort == "off"
    assert resolution.capabilities.source == "unknown"


def test_resolve_request_effort_unknown_explicit_non_off_is_503():
    # 用户**显式**选择非 off 档位、且能力未知时，无法确认是否支持，仍返回 503。
    with patch.object(ollama, "probe_reasoning_capabilities", _probe_unknown):
        with pytest.raises(HTTPException) as error:
            routes_conversations._resolve_request_effort("model", "xhigh")
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "MODEL_CAPABILITIES_UNAVAILABLE"


def test_resolve_request_effort_unknown_invalid_effort_is_400():
    with patch.object(ollama, "probe_reasoning_capabilities", _probe_unknown):
        with pytest.raises(HTTPException) as error:
            routes_conversations._resolve_request_effort("model", "bogus")
    assert error.value.status_code == 400
    assert error.value.detail["code"] == "INVALID_REASONING_EFFORT"


# --- 5) 发消息路径：stale 按旧能力集判定 -------------------------------------


def test_resolve_request_effort_stale_uses_old_supported_set():
    _seed_expired_cache("model", STALE_CAPS)
    with patch.object(ollama, "probe_reasoning_capabilities", _probe_unknown):
        allowed = routes_conversations._resolve_request_effort("model", "low")
        assert allowed.effort == "low"
        assert allowed.capabilities.source == "stale"

        with pytest.raises(HTTPException) as error:
            routes_conversations._resolve_request_effort("model", "xhigh")
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "REASONING_EFFORT_UNSUPPORTED"
    assert error.value.detail["retryable"] is False


# --- 6) 发消息路径：能力已知且不支持 → 409 -----------------------------------


def test_resolve_request_effort_known_unsupported_effort_is_409():
    with patch.object(ollama, "probe_reasoning_capabilities", _probe_known):
        allowed = routes_conversations._resolve_request_effort("model", "low")
        assert allowed.effort == "low"
        assert allowed.capabilities.source == "ollama_probe"

        with pytest.raises(HTTPException) as error:
            routes_conversations._resolve_request_effort("model", "xhigh")
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "REASONING_EFFORT_UNSUPPORTED"


# --- 7) P2-1：失败路径只探测一轮（禁止二次探测） -----------------------------


def test_resolve_request_effort_unknown_failure_probes_once():
    """spec-026 P2-1 验收：``unknown`` + 非 ``off`` 失败路径只探测一轮。

    修复前 ``resolve_reasoning_effort`` 内部已探测一次，``_resolve_request_effort``
    的 UNSUPPORTED 分支又调一次 ``get_reasoning_capabilities``，最坏再跑 25s 串行
    探测。修复后整个请求只探测一轮（异常携带 ``capabilities``，复用而不重探）。
    """
    probe_calls = {"n": 0}

    def _counted_probe(model):
        probe_calls["n"] += 1
        return _probe_unknown(model)

    with patch.object(ollama, "probe_reasoning_capabilities", _counted_probe):
        with pytest.raises(HTTPException) as error:
            routes_conversations._resolve_request_effort("model", "xhigh")
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "MODEL_CAPABILITIES_UNAVAILABLE"
    assert error.value.detail["retryable"] is True
    assert probe_calls["n"] == 1


def test_resolve_request_effort_stale_failure_probes_once():
    """spec-026 P2-1 验收：``stale`` + 不支持档位同样只探测一轮。"""
    probe_calls = {"n": 0}

    def _counted_probe(model):
        probe_calls["n"] += 1
        return _probe_unknown(model)

    _seed_expired_cache("model", STALE_CAPS)
    with patch.object(ollama, "probe_reasoning_capabilities", _counted_probe):
        with pytest.raises(HTTPException) as error:
            routes_conversations._resolve_request_effort("model", "xhigh")
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "REASONING_EFFORT_UNSUPPORTED"
    assert error.value.detail["retryable"] is False
    assert probe_calls["n"] == 1
