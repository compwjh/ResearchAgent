"""首屏就绪优化（P0 health 155s + 预热编排 + GET /api/ready）后端测试。

设计原则（fail-open，不依赖 Ollama / Qdrant 真实可达）：
- 预热项全部用 monkeypatch / patch 注入失败或可控行为，绝不打真实网络；
- 任一预热项失败都只标 failed，绝不抛异常、绝不阻塞启动；
- /api/ready 恒 200，即使预热全部失败。
"""

import threading
import time
from unittest.mock import MagicMock

import httpx
from fastapi.testclient import TestClient

from backend.app.api import routes_kb
from backend.app.main import app
from backend.app.platform import warmup
from backend.app.platform.warmup import readiness_snapshot, reset_warmup, start_warmup

WARMUP_KEYS = ["jieba", "ollama_tags", "embedding", "qdrant"]


def _wait_until_terminal(timeout: float = 12.0):
    """轮询直到所有预热项达到终态（ready/failed）或超时。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = readiness_snapshot()
        if snap and all(v["status"] in ("ready", "failed") for v in snap.values()):
            return snap
        time.sleep(0.05)
    return readiness_snapshot()


def _boom(*_a, **_k):
    raise RuntimeError("injected warmup failure")


def test_api_ready_always_200_and_structure():
    """要求 1：/api/ready 恒 200 且结构含各预热项。"""
    reset_warmup()
    client = TestClient(app)  # 不进入 with，避免触发 lifespan 真实预热
    resp = client.get("/api/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body.get("ready"), bool)
    warmup_part = body.get("warmup", {})
    for key in WARMUP_KEYS:
        assert key in warmup_part, f"缺少预热项 {key}"
        item = warmup_part[key]
        assert set(item.keys()) == {"status", "elapsed_ms", "error"}
        assert item["status"] in ("unknown", "loading", "ready", "failed")


def test_warmup_all_fail_does_not_raise_and_service_usable(monkeypatch):
    """要求 2：预热项全部失败时 start_warmup() 不抛异常、服务可用。"""
    reset_warmup()
    for name in ("_warm_jieba", "_warm_ollama_tags", "_warm_embedding", "_warm_qdrant"):
        monkeypatch.setattr(warmup, name, _boom)
    # 不抛异常是关键断言
    start_warmup()
    snap = _wait_until_terminal()
    assert all(v["status"] == "failed" for v in snap.values())
    # 服务可用：/api/ready 仍 200
    client = TestClient(app)
    assert client.get("/api/ready").status_code == 200


def test_warmup_jieba_marks_ready(monkeypatch):
    """要求 3：jieba 预热后 readiness_snapshot() 该项为 ready（且不阻塞）。"""
    reset_warmup()
    # 仅让其它重量/外部项失败，聚焦 jieba
    monkeypatch.setattr(warmup, "_warm_ollama_tags", _boom)
    monkeypatch.setattr(warmup, "_warm_embedding", _boom)
    monkeypatch.setattr(warmup, "_warm_qdrant", _boom)
    start_warmup()
    snap = _wait_until_terminal()
    assert snap["jieba"]["status"] == "ready"
    assert snap["ollama_tags"]["status"] == "failed"
    assert snap["embedding"]["status"] == "failed"
    assert snap["qdrant"]["status"] == "failed"


def test_health_embedding_probe_uses_registry_shortcut(monkeypatch):
    """要求 4（短路）：注册表已登记 ready 时，health 探测直接采用，不再调用 embed_texts。"""
    reset_warmup()
    # 让 health 探测走注册表短路
    monkeypatch.setattr(
        routes_kb,
        "readiness_snapshot",
        lambda: {k: {"status": "ready" if k == "embedding" else "unknown", "elapsed_ms": 1.0, "error": None} for k in WARMUP_KEYS},
    )
    # 真实向量化相关调用全部桩掉，且记录是否被调用
    called = []
    monkeypatch.setattr(routes_kb, "embed_texts", lambda *a, **k: called.append(1))
    monkeypatch.setattr(routes_kb, "get_available_models", lambda: [])
    monkeypatch.setattr(routes_kb, "get_client", lambda *a, **k: MagicMock())
    monkeypatch.setattr(routes_kb, "count_points", lambda *a, **k: 0)

    status = routes_kb.kb_component_status()
    assert status["embedding"] is True
    assert called == [], "注册表已给出结论时不应再调用 embed_texts（避免 155s 真实向量化）"


def test_health_embedding_probe_bounded_under_slow_network(monkeypatch):
    """要求 4（短超时兜底）：注册表无结论且网络极慢时，探测被短超时约束、不会卡上百秒。"""
    reset_warmup()
    # 注册表无结论
    monkeypatch.setattr(
        routes_kb,
        "readiness_snapshot",
        lambda: {k: {"status": "unknown", "elapsed_ms": None, "error": None} for k in WARMUP_KEYS},
    )
    monkeypatch.setattr(routes_kb, "get_available_models", lambda: [])
    monkeypatch.setattr(routes_kb, "get_client", lambda *a, **k: MagicMock())
    monkeypatch.setattr(routes_kb, "count_points", lambda *a, **k: 0)

    # httpx.post 挂起（模拟 Ollama 不可达），用可释放的 Event，避免线程久挂
    release = threading.Event()

    def _hang(*a, **k):
        release.wait(30)

    monkeypatch.setattr(httpx, "post", _hang)
    try:
        started = time.perf_counter()
        status = routes_kb.kb_component_status()
        elapsed = time.perf_counter() - started
    finally:
        release.set()  # 释放挂起的工作线程

    assert status["embedding"] is False
    # 远小于基线 155s：被 KB_HEALTH_PROBE_TIMEOUT_SECONDS（默认 3s）约束
    assert elapsed < 10, f"探测未被短超时约束，耗时 {elapsed:.1f}s"


def test_warmup_calls_refresh_available_models(monkeypatch):
    """要求 5：预热必须调用 refresh_available_models()（强制回源）。"""
    reset_warmup()
    called = {}

    def _tracked(*a, **k):
        called["refresh"] = True
        raise httpx.ConnectError("unreachable (test)")

    monkeypatch.setattr(warmup, "refresh_available_models", _tracked)
    # 其它项快速失败，聚焦 ollama_tags 预热
    monkeypatch.setattr(warmup, "_warm_jieba", _boom)
    monkeypatch.setattr(warmup, "_warm_embedding", _boom)
    monkeypatch.setattr(warmup, "_warm_qdrant", _boom)

    start_warmup()
    _wait_until_terminal()
    assert called.get("refresh") is True, "预热应调用 refresh_available_models() 强制回源"
