"""线上模型轻量探测测试（spec-035 Task04）。

全部 mock 外发请求，绝不发真实网络请求。覆盖：成功→ready、非 2xx→unreachable、
超时→unreachable、异常→unreachable、60s 缓存命中（不发第二次请求）、
以及日志**不**包含 api_key 与响应体。
"""
import logging
from unittest.mock import MagicMock

import httpx
import pytest

from backend.app.platform import model_catalog
from backend.app.platform.model_catalog import OnlineModelEntry, probe_online_model

# 测试用假 Key（绝不可能是真实凭据）
FAKE_KEY = "sk-test-fake-key-not-real"


@pytest.fixture(autouse=True)
def _clear_probe_cache():
    # 隔离模块级缓存，避免跨测试命中造成误判
    model_catalog._PROBE_CACHE.clear()
    yield
    model_catalog._PROBE_CACHE.clear()


def _make_entry(model_id="deepseek:deepseek-chat", provider="deepseek", model="deepseek-chat"):
    return OnlineModelEntry(
        id=model_id,
        provider=provider,
        model=model,
        display_name=model_id,
        base_url="https://api.deepseek.com",
        api_key=FAKE_KEY,
        source="online",
    )


def _ok_response(status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    return resp


def _fake_client(post_result, *, side_effect=None):
    client = MagicMock()
    if side_effect is not None:
        client.post.side_effect = side_effect
    else:
        client.post.return_value = post_result
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    return client


def test_success_returns_ready(monkeypatch):
    client = _fake_client(_ok_response(200))
    monkeypatch.setattr(model_catalog.httpx, "Client", lambda *a, **k: client)
    assert probe_online_model(_make_entry()) == "ready"


def test_non_2xx_returns_unreachable(monkeypatch):
    client = _fake_client(_ok_response(500))
    monkeypatch.setattr(model_catalog.httpx, "Client", lambda *a, **k: client)
    assert probe_online_model(_make_entry()) == "unreachable"


def test_timeout_returns_unreachable(monkeypatch):
    client = _fake_client(None, side_effect=httpx.TimeoutException("timeout"))
    monkeypatch.setattr(model_catalog.httpx, "Client", lambda *a, **k: client)
    assert probe_online_model(_make_entry()) == "unreachable"


def test_exception_returns_unreachable(monkeypatch):
    client = _fake_client(None, side_effect=httpx.ConnectError("boom"))
    monkeypatch.setattr(model_catalog.httpx, "Client", lambda *a, **k: client)
    assert probe_online_model(_make_entry()) == "unreachable"


def test_cache_hit_avoids_second_request(monkeypatch):
    client = _fake_client(_ok_response(200))
    monkeypatch.setattr(model_catalog.httpx, "Client", lambda *a, **k: client)
    entry = _make_entry()
    assert probe_online_model(entry) == "ready"
    assert probe_online_model(entry) == "ready"
    # 第二次应命中缓存，不再发请求
    assert client.post.call_count == 1


def test_logs_no_key_or_body(monkeypatch, caplog):
    client = _fake_client(_ok_response(200))
    monkeypatch.setattr(model_catalog.httpx, "Client", lambda *a, **k: client)
    with caplog.at_level(logging.INFO):
        probe_online_model(_make_entry())
    for record in caplog.records:
        msg = record.getMessage()
        assert FAKE_KEY not in msg
        assert "ping" not in msg
