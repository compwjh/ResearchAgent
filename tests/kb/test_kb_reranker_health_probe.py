"""KB health probe / 检索熔断回归测试（任务 U：修复 20261110 评审 BLOCK）。

全部用进程内 httpx.BaseTransport fake，不依赖真实 llama-server，不连真实端口。

契约依据（spec-014，未修订）
----------------------------
- :72  ``available`` = 「HTTP 与排序质量探针是否通过」；
- :102 质量探针至少 3 条相关度明显不同的文档，最相关文档必须排第一；
- :131 不可达或**质量探针失败**后至少缓存负状态 30 秒；连接/读取超时上限 2s/60s；
- :134 30 秒内并发请求只触发一次探针；
- :149 A7 health 能区分禁用、不可达、质量探针失败和可用。

RED → GREEN 记录（2026-11-10，任务 N 的 liveness-only 实现下先跑出红灯）
-----------------------------------------------------------------------
旧实现：``_health_probe()`` 只发 ``GET /health``（不再跑 ``/v1/rerank`` 质量推理）、
``rerank_hits`` 只把 ``>=500`` / ``ConnectError`` 判为可缓存、health 的 ``timeout``
完全不写负缓存。下列断言在旧实现下失败（真实 RED，非放宽断言）：
- 「心跳必须真的执行质量探针」/「两档 read cap」→ 旧实现无 POST、KeyError；
- 「timeout 写 3–5s 短缓存」→ 旧实现零缓存；
- 「质量探针失败 / 4xx / invalid_* / unexpected / ConnectTimeout 进 30s 负缓存」→
  旧实现立即重试（``cacheable=False``）；
- 「模型质量损坏时 health 不得报 available=true」→ 旧实现 liveness=true 即放行。
修复后这些断言全部转绿，且每一条都比旧门禁**更严格**（新增质量语义与缓存边界，
不删弱任何既有断言）。
"""

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient

from backend.app.api import routes_kb
from backend.app.knowledge_base.infrastructure import reranker, retrieve
from backend.app.main import app

# 本机实测：单请求 /v1/rerank 约 1.5–2.3s；5 并发时最长 18.3s。
SLOW_INFERENCE_SECONDS = 2.2
CONCURRENT_INFERENCE_SECONDS = 18.3
# liveness 的 read cap 为 6.0s；质量推理的 read cap 为 30.0s（覆盖 18.3s，仍有硬上限）。
SLOW_HEALTH_SECONDS = 7.0
QUALITY_TIMEOUT_SECONDS = 31.0
# spec-014:131 负状态缓存下限。
NEGATIVE_TTL_SECONDS = 30.0

_VALID_RESULTS = [
    {"index": 0, "relevance_score": 0.1},
    {"index": 1, "relevance_score": 0.9},
    {"index": 2, "relevance_score": 0.2},
]
_TIED_RESULTS = [
    {"index": 0, "relevance_score": 0.5},
    {"index": 1, "relevance_score": 0.5},
    {"index": 2, "relevance_score": 0.5},
]
_WRONG_ORDER_RESULTS = [
    {"index": 0, "relevance_score": 0.9},
    {"index": 1, "relevance_score": 0.1},
    {"index": 2, "relevance_score": 0.2},
]
# 单块合法质量响应：用于验证正常的 1.5–2.3s 推理不会被总时限误杀。
_VALID_RERANK_BODY = (
    b'{"results":[{"index":0,"relevance_score":0.1},'
    b'{"index":1,"relevance_score":0.9},{"index":2,"relevance_score":0.2}]}'
)


@dataclass(frozen=True)
class Hit:
    text: str


class _FakeClock:
    """单调时钟替身，便于断言正/负缓存的命中与过期。"""

    def __init__(self, value=100.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class _FakeRerankerServer(httpx.BaseTransport):
    """llama-server 的进程内 fake：/health 轻量、/v1/rerank 是一次慢推理。

    用 ``request.extensions["timeout"]["read"]`` 判断「响应耗时是否超过客户端
    read timeout」，超过则抛 httpx.ReadTimeout（与真实 socket 读超时语义一致）。
    这样 liveness 6s 档与质量 30s 档会在同一 fake 上产生真实不同的结果。
    """

    def __init__(
        self,
        *,
        connect_error=False,
        connect_timeout=False,
        read_error=False,
        health_status=200,
        health_seconds=0.0,
        health_payload=None,
        health_body=None,
        transient_health_timeouts=0,
        transient_inference_timeouts=0,
        inference_seconds=SLOW_INFERENCE_SECONDS,
        rerank_status=200,
        rerank_results=None,
        rerank_body=None,
        really_sleep=False,
        unexpected_error=False,
    ):
        self.calls = []
        self.unexpected_error = unexpected_error
        self.read_timeouts = []
        self.connect_error = connect_error
        self.connect_timeout = connect_timeout
        self.read_error = read_error
        self.health_status = health_status
        self.health_seconds = health_seconds
        self.health_payload = health_payload
        self.health_body = health_body
        self.transient_health_timeouts = transient_health_timeouts
        self.transient_inference_timeouts = transient_inference_timeouts
        self.inference_seconds = inference_seconds
        self.rerank_status = rerank_status
        self.rerank_results = rerank_results
        self.rerank_body = rerank_body
        self.really_sleep = really_sleep

    def handle_request(self, request):
        self.calls.append((request.method, request.url.path))
        read_timeout = float(request.extensions.get("timeout", {}).get("read") or 0.0)
        self.read_timeouts.append((request.url.path, read_timeout))
        if self.unexpected_error:
            raise RuntimeError("unexpected code-level failure")
        if self.connect_timeout:
            raise httpx.ConnectTimeout("connect timed out", request=request)
        if self.connect_error:
            raise httpx.ConnectError("connection refused", request=request)
        if self.read_error:
            raise httpx.ReadError("peer reset", request=request)
        if request.url.path == "/health":
            if self.transient_health_timeouts > 0:
                self.transient_health_timeouts -= 1
                raise httpx.ReadTimeout("health did not answer", request=request)
            if self.really_sleep and self.health_seconds:
                time.sleep(self.health_seconds)
            if self.health_seconds > read_timeout:
                raise httpx.ReadTimeout("slow health", request=request)
            if self.health_body is not None:
                return httpx.Response(self.health_status, content=self.health_body)
            payload = {"status": "ok"} if self.health_payload is None else self.health_payload
            return httpx.Response(self.health_status, json=payload)
        if request.url.path == "/v1/rerank":
            if self.transient_inference_timeouts > 0:
                self.transient_inference_timeouts -= 1
                raise httpx.ReadTimeout("inference did not answer", request=request)
            if self.really_sleep and self.inference_seconds:
                time.sleep(self.inference_seconds)
            if self.inference_seconds > read_timeout:
                raise httpx.ReadTimeout("slow inference", request=request)
            if self.rerank_body is not None:
                return httpx.Response(self.rerank_status, content=self.rerank_body)
            results = _VALID_RESULTS if self.rerank_results is None else self.rerank_results
            return httpx.Response(self.rerank_status, json={"results": results})
        return httpx.Response(404, json={"error": "not found"})


class _ClockDrivenStream(httpx.SyncByteStream):
    """按注入时钟逐块吐字节：每块之间间隔 ``step`` 秒（小于 read cap，httpx 不会超时）。

    用假时钟推进模拟时间，使「异常后端每隔数秒吐 1 字节」的场景可在毫秒级复现，
    无需真的 sleep 数十秒。``body`` 为单块合法 JSON 时用于验证正常推理不被总时限误杀。
    """

    def __init__(self, clock, *, step, count=1, body=None, advance_before=True):
        self.clock = clock
        self.step = step
        self.count = count
        self.body = body
        self.advance_before = advance_before

    def __iter__(self):
        for _ in range(self.count):
            if self.advance_before:
                self.clock.advance(self.step)
            yield b"x" if self.body is None else self.body


class _SlowDripRerankerServer(httpx.BaseTransport):
    """liveness 正常；质量 POST 无限慢速吐单字节，模拟 read timeout 永不触发的后端。"""

    def __init__(self, clock, *, step=3.0, count=100, body=None):
        self.clock = clock
        self.step = step
        self.count = count
        self.body = body
        self.calls = []
        self.read_timeouts = []

    def handle_request(self, request):
        self.calls.append((request.method, request.url.path))
        read_timeout = float(request.extensions.get("timeout", {}).get("read") or 0.0)
        self.read_timeouts.append((request.url.path, read_timeout))
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, stream=_ClockDrivenStream(
            self.clock, step=self.step, count=self.count, body=self.body,
        ))


class _BlockingHealthServer(httpx.BaseTransport):
    """leader 进到 /health 后阻塞，直到 release；用于验证 single-flight 等待有界。"""

    def __init__(self, entered, release):
        self.entered = entered
        self.release = release
        self.calls = []

    def handle_request(self, request):
        self.calls.append((request.method, request.url.path))
        self.entered.set()
        self.release.wait(timeout=5.0)
        raise httpx.ReadTimeout("slow health", request=request)


def _cached_entries(transport):
    """取出该 fake transport 对应的健康缓存条目 (detail, expire_at)。"""
    token = id(transport)
    with retrieve._health_condition:
        return [
            entry
            for (_endpoint, _model, tid), entry in retrieve._health_cache.items()
            if tid == token
        ]


def _cached_details(transport):
    return [detail for detail, _expire in _cached_entries(transport)]


def _offline_kb_health_patches():
    """让 /api/kb/health 的 Qdrant/embedding/模型枚举分支完全离线。"""
    stack = ExitStack()
    client = Mock()
    client.collection_exists.return_value = True
    generation_store = Mock()
    generation_store.require_generation.return_value = {"alias_target": "papers_rebuild_live"}
    stack.enter_context(patch.object(routes_kb, "get_client", return_value=client))
    stack.enter_context(patch.object(routes_kb, "_generation_store", return_value=generation_store))
    stack.enter_context(patch.object(routes_kb, "count_points", return_value=42))
    stack.enter_context(patch.object(routes_kb, "load_papers", return_value=[{"paper_id": "p1"}]))
    stack.enter_context(patch.object(routes_kb, "get_available_models", return_value=[]))
    stack.enter_context(patch.object(
        routes_kb, "readiness_snapshot", return_value={"embedding": {"status": "ready"}},
    ))
    return stack


class HealthProbeTests(unittest.TestCase):
    """retrieve.reranker_health() / GET /api/kb/health 的质量语义与缓存门禁。"""

    def setUp(self):
        with retrieve._health_condition:
            retrieve._health_cache.clear()
            retrieve._health_inflight.clear()
        reranker.clear_negative_cache()

    def tearDown(self):
        with retrieve._health_condition:
            retrieve._health_cache.clear()
            retrieve._health_inflight.clear()
        reranker.clear_negative_cache()

    def test_slow_but_successful_quality_probe_is_available(self):
        """① 2.2s 慢推理成功 → available=true；心跳必须真的跑三文档质量探针。"""
        fake = _FakeRerankerServer(really_sleep=True)
        detail = retrieve.reranker_health(enabled=True, transport=fake)
        self.assertTrue(detail["available"], detail)
        self.assertIsNone(detail["reason"], detail)
        self.assertEqual(
            fake.calls, [("GET", "/health"), ("POST", "/v1/rerank")],
            "available 必须代表质量已验证，不能只判 liveness",
        )
        cached = _cached_details(fake)
        self.assertEqual(len(cached), 1)
        self.assertTrue(cached[0]["available"], "不得写入 available=False 的负缓存")
        self.assertIsNone(cached[0]["reason"])

    def test_concurrent_slow_inference_within_quality_cap_is_available(self):
        """实测 5 并发最长 18.3s，仍在质量 read cap 内 → 慢但成功不得假降级。"""
        fake = _FakeRerankerServer(inference_seconds=CONCURRENT_INFERENCE_SECONDS)
        detail = retrieve.reranker_health(enabled=True, transport=fake)
        self.assertTrue(detail["available"], detail)
        self.assertIsNone(detail["reason"], detail)
        self.assertEqual(fake.calls, [("GET", "/health"), ("POST", "/v1/rerank")])

    def test_quality_probe_uses_wider_read_cap_than_liveness(self):
        """两档超时：质量 POST 的 read cap 必须 >18.3s 且 ≤30s；liveness GET 保持 6s 上限。"""
        fake = _FakeRerankerServer()
        retrieve.reranker_health(enabled=True, transport=fake)
        timeouts = dict(fake.read_timeouts)
        self.assertIn("/v1/rerank", timeouts, "心跳必须执行质量探针")
        self.assertAlmostEqual(timeouts["/health"], 6.0)
        self.assertGreater(timeouts["/v1/rerank"], CONCURRENT_INFERENCE_SECONDS)
        self.assertLessEqual(timeouts["/v1/rerank"], 30.0, "质量探针也必须有上限")

    def test_slow_health_response_within_liveness_cap_is_available(self):
        """慢 /health 响应（2.2s）在 6s 上限内成功，质量探针随后也通过。"""
        fake = _FakeRerankerServer(health_seconds=2.2)
        detail = retrieve.reranker_health(enabled=True, transport=fake)
        self.assertTrue(detail["available"], detail)
        self.assertIsNone(detail["reason"], detail)
        self.assertEqual(fake.calls, [("GET", "/health"), ("POST", "/v1/rerank")])

    def test_liveness_beyond_cap_is_still_timeout(self):
        """超时有上限：超过 6s 的 /health 仍判 timeout，绝不改成无限等待。"""
        fake = _FakeRerankerServer(health_seconds=SLOW_HEALTH_SECONDS)
        detail = retrieve.reranker_health(enabled=True, transport=fake)
        self.assertFalse(detail["available"], detail)
        self.assertEqual(detail["reason"], "timeout")
        self.assertEqual(fake.calls, [("GET", "/health")], "liveness 失败后不得再发质量推理")

    def test_quality_inference_beyond_cap_is_still_timeout(self):
        """质量推理 31s 超过 30s 硬上限仍判 timeout（有上限，不是无限等待）。"""
        fake = _FakeRerankerServer(inference_seconds=QUALITY_TIMEOUT_SECONDS)
        detail = retrieve.reranker_health(enabled=True, transport=fake)
        self.assertFalse(detail["available"], detail)
        self.assertEqual(detail["reason"], "timeout")

    def test_timeout_writes_short_cache_not_zero_or_thirty_seconds(self):
        """timeout 写 3–5s 短缓存：零缓存会打满后端，30s 是旧假降级根因。"""
        fake = _FakeRerankerServer(transient_inference_timeouts=1)
        clock = _FakeClock(100.0)
        first = retrieve.reranker_health(enabled=True, transport=fake, clock=clock)
        self.assertFalse(first["available"], first)
        self.assertEqual(first["reason"], "timeout")
        entries = _cached_entries(fake)
        self.assertEqual(len(entries), 1, "timeout 不得零缓存（持续故障会打满后端）")
        ttl = entries[0][1] - clock()
        self.assertGreater(ttl, 0.0)
        self.assertGreaterEqual(ttl, 3.0, "短缓存应落在任务建议的 3–5s")
        self.assertLessEqual(ttl, 5.0, "timeout 不得写 30s 负缓存（旧假降级根因）")
        clock.advance(2.0)
        second = retrieve.reranker_health(enabled=True, transport=fake, clock=clock)
        self.assertFalse(second["available"], second)
        self.assertEqual(len(fake.calls), 2, "短缓存期内不得重跑推理")
        clock.advance(3.0)
        third = retrieve.reranker_health(enabled=True, transport=fake, clock=clock)
        self.assertTrue(third["available"], third)
        self.assertEqual(len(fake.calls), 4, "短缓存过期后应重新探测并恢复")

    def test_real_connection_failure_still_writes_30s_negative_cache(self):
        """② 真实连接失败 → 30s 负缓存且 reason=connection（spec-014:131）。"""
        fake = _FakeRerankerServer(connect_error=True)
        clock = _FakeClock(100.0)
        first = retrieve.reranker_health(enabled=True, transport=fake, clock=clock)
        self.assertFalse(first["available"], first)
        self.assertEqual(first["reason"], "connection")
        self.assertEqual(len(fake.calls), 1)
        entries = _cached_entries(fake)
        self.assertEqual(len(entries), 1)
        self.assertAlmostEqual(entries[0][1] - clock(), NEGATIVE_TTL_SECONDS)
        self.assertFalse(entries[0][0]["available"])
        second = retrieve.reranker_health(enabled=True, transport=fake, clock=clock)
        self.assertEqual(second["reason"], "connection")
        self.assertEqual(len(fake.calls), 1, "真实连接失败应命中负缓存，不重复探测")
        clock.advance(31)
        retrieve.reranker_health(enabled=True, transport=fake, clock=clock)
        self.assertEqual(len(fake.calls), 2, "TTL 过期后应重新探测")

    def test_quality_probe_failure_writes_30s_negative_cache(self):
        """质量探针失败（三文档同分）→ available=false + 30s 负缓存（spec-014:131/:149）。"""
        fake = _FakeRerankerServer(rerank_results=_TIED_RESULTS)
        clock = _FakeClock(100.0)
        first = retrieve.reranker_health(enabled=True, transport=fake, clock=clock)
        self.assertFalse(first["available"], first)
        self.assertEqual(first["reason"], "quality_probe_failed")
        self.assertEqual(fake.calls, [("GET", "/health"), ("POST", "/v1/rerank")])
        entries = _cached_entries(fake)
        self.assertEqual(len(entries), 1)
        self.assertAlmostEqual(entries[0][1] - clock(), NEGATIVE_TTL_SECONDS)
        second = retrieve.reranker_health(enabled=True, transport=fake, clock=clock)
        self.assertEqual(second["reason"], "quality_probe_failed")
        self.assertEqual(len(fake.calls), 2, "质量失败应命中 30s 负缓存，不重复跑推理")

    def test_wrong_ranking_order_is_not_available(self):
        """最相关文档未排第一 → 判不可用（spec-014:102）。"""
        fake = _FakeRerankerServer(rerank_results=_WRONG_ORDER_RESULTS)
        detail = retrieve.reranker_health(enabled=True, transport=fake)
        self.assertFalse(detail["available"], detail)
        self.assertEqual(detail["reason"], "quality_probe_failed")

    def test_connect_timeout_is_classified_as_connection_and_cached(self):
        """HIGH-1：ConnectTimeout 归 connection 并 30s 熔断，不能归 timeout（短缓存）。"""
        fake = _FakeRerankerServer(connect_timeout=True)
        clock = _FakeClock(100.0)
        first = retrieve.reranker_health(enabled=True, transport=fake, clock=clock)
        self.assertFalse(first["available"], first)
        self.assertEqual(first["reason"], "connection")
        self.assertEqual(len(fake.calls), 1)
        entries = _cached_entries(fake)
        self.assertEqual(len(entries), 1)
        self.assertAlmostEqual(entries[0][1] - clock(), NEGATIVE_TTL_SECONDS)

    def test_read_error_is_classified_as_connection_consistently(self):
        """ReadError/RemoteProtocolError 在 health 侧归 connection（与检索侧一致）。"""
        fake = _FakeRerankerServer(read_error=True)
        detail = retrieve.reranker_health(enabled=True, transport=fake)
        self.assertFalse(detail["available"], detail)
        self.assertEqual(detail["reason"], "connection")

    def test_health_503_is_model_not_prepared_and_cached(self):
        """心跳 503 → model_not_prepared 且 30s 负缓存。"""
        fake = _FakeRerankerServer(health_status=503)
        clock = _FakeClock(100.0)
        first = retrieve.reranker_health(enabled=True, transport=fake, clock=clock)
        self.assertFalse(first["available"], first)
        self.assertEqual(first["reason"], "model_not_prepared")
        self.assertEqual(fake.calls, [("GET", "/health")])
        entries = _cached_entries(fake)
        self.assertEqual(len(entries), 1)
        self.assertAlmostEqual(entries[0][1] - clock(), NEGATIVE_TTL_SECONDS)

    def test_explicitly_disabled_returns_disabled_without_probe(self):
        """③ 显式 RERANKER_ENABLED=false → reason=disabled，零探测。"""
        fake = _FakeRerankerServer()
        detail = retrieve.reranker_health(enabled=False, transport=fake)
        self.assertFalse(detail["enabled"], detail)
        self.assertFalse(detail["available"], detail)
        self.assertEqual(detail["reason"], "disabled")
        self.assertEqual(fake.calls, [])
        self.assertEqual(_cached_entries(fake), [])

    def test_api_kb_health_disabled_reason_and_no_probe(self):
        """③ 端点级：配置禁用时 /api/kb/health 不发起任何探测。"""
        fake = _FakeRerankerServer()
        with patch.object(retrieve, "RERANKER_ENABLED", False), patch.object(
            routes_kb, "reranker_health", lambda: retrieve.reranker_health(transport=fake)
        ), _offline_kb_health_patches():
            response = TestClient(app).get("/api/kb/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["reranker_detail"]["reason"], "disabled")
        self.assertFalse(body["reranker"])
        self.assertEqual(fake.calls, [], "显式禁用时不应发起任何探测")

    def test_api_kb_health_structure_is_unchanged(self):
        """④ /api/kb/health 响应结构与 reranker_detail 字段名、语义不变。"""
        fake = _FakeRerankerServer()
        with patch.object(
            routes_kb, "reranker_health",
            lambda: retrieve.reranker_health(enabled=True, transport=fake),
        ), _offline_kb_health_patches():
            response = TestClient(app).get("/api/kb/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {
            "qdrant", "embedding", "reranker", "reranker_detail",
            "papers", "chunks", "v2_llm", "generation",
        })
        detail = body["reranker_detail"]
        self.assertEqual(set(detail), {"enabled", "available", "backend", "model", "reason"})
        self.assertIsInstance(detail["enabled"], bool)
        self.assertIsInstance(detail["available"], bool)
        self.assertIsInstance(detail["model"], str)
        self.assertEqual(detail["backend"], "llama.cpp")
        self.assertEqual(body["reranker"], bool(detail["enabled"] and detail["available"]))
        self.assertTrue(detail["available"], "慢但成功的推理不得让 health 假降级")
        self.assertIsNone(detail["reason"])
        self.assertIn(("POST", "/v1/rerank"), fake.calls)

    def test_api_kb_health_quality_failure_is_not_reported_available(self):
        """CRITICAL：模型质量损坏时 health 不得报 available=true（消除 health/事件矛盾）。"""
        fake = _FakeRerankerServer(rerank_results=_TIED_RESULTS)
        with patch.object(
            routes_kb, "reranker_health",
            lambda: retrieve.reranker_health(enabled=True, transport=fake),
        ), _offline_kb_health_patches():
            response = TestClient(app).get("/api/kb/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["reranker_detail"]["available"])
        self.assertEqual(body["reranker_detail"]["reason"], "quality_probe_failed")
        self.assertFalse(body["reranker"])
        self.assertIn(("POST", "/v1/rerank"), fake.calls)

    def test_unexpected_failure_reason_is_diagnosable_and_logged(self):
        """L-1：代码级意外异常不得伪装成质量失败，且必须留服务端日志（原始异常不进响应）。"""
        fake = _FakeRerankerServer(unexpected_error=True)
        clock = _FakeClock(100.0)
        with self.assertLogs(retrieve.__name__, level="ERROR") as logs:
            detail = retrieve.reranker_health(enabled=True, transport=fake, clock=clock)
        self.assertFalse(detail["available"], detail)
        self.assertEqual(detail["reason"], "unexpected")
        self.assertEqual(len(fake.calls), 1)
        self.assertTrue(any("reason=unexpected" in line for line in logs.output))
        self.assertNotIn("What is the capital of France", "\n".join(logs.output))
        entries = _cached_entries(fake)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][0]["reason"], "unexpected")
        self.assertAlmostEqual(entries[0][1] - clock(), NEGATIVE_TTL_SECONDS)
        with retrieve._health_condition:
            self.assertFalse(retrieve._health_inflight)

    def test_api_kb_health_unexpected_reason_is_diagnosable(self):
        """L-1：endpoint 级响应结构不变，reason 明确为 unexpected。"""
        fake = _FakeRerankerServer(unexpected_error=True)
        with self.assertLogs(retrieve.__name__, level="ERROR"), patch.object(
            routes_kb, "reranker_health",
            lambda: retrieve.reranker_health(enabled=True, transport=fake),
        ), _offline_kb_health_patches():
            response = TestClient(app).get("/api/kb/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {
            "qdrant", "embedding", "reranker", "reranker_detail",
            "papers", "chunks", "v2_llm", "generation",
        })
        detail = body["reranker_detail"]
        self.assertEqual(set(detail), {"enabled", "available", "backend", "model", "reason"})
        self.assertFalse(detail["available"])
        self.assertEqual(detail["reason"], "unexpected")
        self.assertFalse(body["reranker"])

    def test_slow_dribble_response_exits_at_total_deadline(self):
        """M-2：每 3s 吐 1 字节（远小于 30s read cap）也必须在总时限内判 timeout。"""
        total_cap = getattr(retrieve, "_RERANKER_HEALTH_TOTAL_TIMEOUT_SECONDS", None)
        self.assertIsNotNone(total_cap, "health 探针必须有总时限常量")
        self.assertGreater(total_cap, retrieve._RERANKER_HEALTH_QUALITY_READ_TIMEOUT_CAP)
        self.assertLessEqual(total_cap, 60.0, "总时限必须有上限，不得无限等待")
        step = 3.0
        self.assertLess(step, retrieve._RERANKER_HEALTH_QUALITY_READ_TIMEOUT_CAP,
                        "单字节间隔必须小于 read cap，否则测不到 read timeout 非总时限的缺口")
        clock = _FakeClock(100.0)
        fake = _SlowDripRerankerServer(clock, step=step, count=100)
        start = clock()
        detail = retrieve.reranker_health(enabled=True, transport=fake, clock=clock)
        self.assertFalse(detail["available"], detail)
        self.assertEqual(detail["reason"], "timeout")
        self.assertEqual(fake.calls, [("GET", "/health"), ("POST", "/v1/rerank")])
        self.assertEqual(dict(fake.read_timeouts)["/v1/rerank"], 30.0, "两档 read cap 不变")
        self.assertLessEqual(clock() - start, total_cap + step)
        entries = _cached_entries(fake)
        self.assertEqual(len(entries), 1)
        self.assertAlmostEqual(entries[0][1] - clock(), 4.0, places=3,
                               msg="总时限超时仍按 timeout 走 4s 短缓存")
        with retrieve._health_condition:
            self.assertFalse(retrieve._health_inflight, "探针必须收敛，inflight 不得残留")

    def test_normal_slow_inference_survives_total_deadline(self):
        """M-2：正常 2.3s 推理不得被总时限误杀（1.5–2.3s 是本机实测区间上界）。"""
        clock = _FakeClock(100.0)
        fake = _SlowDripRerankerServer(clock, step=2.3, count=1, body=_VALID_RERANK_BODY)
        detail = retrieve.reranker_health(enabled=True, transport=fake, clock=clock)
        self.assertTrue(detail["available"], detail)
        self.assertIsNone(detail["reason"])
        self.assertEqual(clock(), 102.3)

    def test_single_flight_wait_is_bounded(self):
        """M-2：leader 挂起时 waiter 不得无限等待，须在有界 deadline 内快速失败。"""
        entered, release = threading.Event(), threading.Event()
        fake = _BlockingHealthServer(entered, release)
        clock = _FakeClock(100.0)
        wait_cap = 0.3
        with patch.object(retrieve, "_RERANKER_HEALTH_WAIT_CAP", wait_cap, create=True), \
                ThreadPoolExecutor(max_workers=2) as pool:
            leader = pool.submit(
                retrieve.reranker_health, enabled=True, transport=fake, clock=clock,
            )
            self.assertTrue(entered.wait(2.0), "leader 必须进入探针")
            waiter = pool.submit(
                retrieve.reranker_health, enabled=True, transport=fake, clock=clock,
            )
            try:
                time.sleep(wait_cap + 0.3)
                self.assertTrue(waiter.done(), "leader 仍挂起时 waiter 必须已按有界 deadline 返回")
            finally:
                release.set()
            detail = waiter.result(timeout=3.0)
            self.assertFalse(detail["available"], detail)
            self.assertEqual(detail["reason"], "timeout")
            self.assertEqual(fake.calls, [("GET", "/health")], "等待者不得重复发起探针")
            leader.result(timeout=3.0)
        with retrieve._health_condition:
            self.assertFalse(retrieve._health_inflight)


class RerankNegativeCacheTests(unittest.TestCase):
    """reranker.py 检索链路熔断：所有持续性失败都必须 ≥30s 负缓存（spec-014:131）。

    任务 N 的 ``cacheable`` 排除逻辑把 timeout / invalid_* / unexpected / 4xx
    判为「立即重试」，叠加 60s read timeout 无熔断，会打满 FastAPI 线程池；
    本组用例恢复基线的「所有失败无条件 _remember」并统一异常归类。
    """

    def setUp(self):
        reranker.clear_negative_cache()
        self.hits = [Hit("a"), Hit("b"), Hit("c")]

    def tearDown(self):
        reranker.clear_negative_cache()

    def _two_calls(self, handler):
        calls = []

        def wrapped(request):
            calls.append(request)
            return handler(request)

        transport = httpx.MockTransport(wrapped)
        clock = _FakeClock(100.0)
        first = reranker.rerank_hits(
            "q", self.hits, transport=transport, clock=clock, negative_ttl=1,
        )
        second = reranker.rerank_hits(
            "q", self.hits, transport=transport, clock=clock, negative_ttl=1,
        )
        return first, second, calls

    def _assert_cached(self, first, second, calls, reason):
        self.assertEqual(first.reason, reason)
        self.assertEqual(second.reason, reason)
        self.assertFalse(first.used)
        self.assertEqual(len(calls), 1, f"{reason} 必须命中 30s 负缓存，只发一次请求")

    def test_timeout_enters_30s_negative_cache(self):
        """timeout（持续 hang）必须熔断：旧实现的「立即重试」会每次阻塞 60s。"""
        def handler(request):
            raise httpx.ReadTimeout("slow inference", request=request)

        first, second, calls = self._two_calls(handler)
        self._assert_cached(first, second, calls, "timeout")

    def test_connection_failure_still_enters_negative_cache(self):
        """ConnectError 仍进负缓存，避免每次检索都重试不可达端口。"""
        def handler(request):
            raise httpx.ConnectError("refused", request=request)

        first, second, calls = self._two_calls(handler)
        self._assert_cached(first, second, calls, "connection")

    def test_5xx_still_enters_negative_cache(self):
        """5xx 是真实服务端失败，仍进负缓存。"""
        def handler(request):
            return httpx.Response(503, json={"error": "unavailable"})

        first, second, calls = self._two_calls(handler)
        self._assert_cached(first, second, calls, "http_status")

    def test_4xx_enters_negative_cache(self):
        """4xx 是持续性故障（非瞬态），必须熔断（旧实现误判立即重试）。"""
        def handler(request):
            return httpx.Response(404, json={"error": "not found"})

        first, second, calls = self._two_calls(handler)
        self._assert_cached(first, second, calls, "http_status")

    def test_invalid_json_enters_negative_cache(self):
        """invalid_json（模型输出持续损坏）仍进 30s 负缓存。"""
        def handler(request):
            return httpx.Response(200, content=b"{")

        first, second, calls = self._two_calls(handler)
        self._assert_cached(first, second, calls, "invalid_json")

    def test_invalid_score_enters_negative_cache(self):
        """invalid_score（NaN 分数）仍进 30s 负缓存。"""
        def handler(request):
            return httpx.Response(200, content=(
                b'{"results":[{"index":0,"relevance_score":NaN},'
                b'{"index":1,"relevance_score":2},{"index":2,"relevance_score":3}]}'
            ))

        first, second, calls = self._two_calls(handler)
        self._assert_cached(first, second, calls, "invalid_score")

    def test_unexpected_enters_negative_cache(self):
        """unexpected 兜底（真实意外故障）仍进 30s 负缓存。"""
        def handler(request):
            raise RuntimeError("boom")

        first, second, calls = self._two_calls(handler)
        self._assert_cached(first, second, calls, "unexpected")

    def test_connect_timeout_is_connection_and_cached(self):
        """HIGH-1：ConnectTimeout 单独归 connection（可缓存），不归 timeout。"""
        def handler(request):
            raise httpx.ConnectTimeout("connect timed out", request=request)

        first, second, calls = self._two_calls(handler)
        self._assert_cached(first, second, calls, "connection")

    def test_read_error_is_connection_and_cached(self):
        """ReadError/RemoteProtocolError 在检索侧也归 connection（两模块一致）。"""
        def handler(request):
            raise httpx.ReadError("peer reset", request=request)

        first, second, calls = self._two_calls(handler)
        self._assert_cached(first, second, calls, "connection")

    def test_read_timeout_cap_does_not_exceed_spec_limit(self):
        """检索路径 read timeout 有 spec-014:131 的 60s 硬上限，配置越界也不无限等待。"""
        seen = []

        def handler(request):
            seen.append(request.extensions["timeout"]["read"])
            return httpx.Response(200, json={"results": [
                {"index": i, "relevance_score": i} for i in range(3)]})

        result = reranker.rerank_hits(
            "q", self.hits, read_timeout=600.0, transport=httpx.MockTransport(handler),
        )
        self.assertTrue(result.used)
        self.assertEqual(seen, [60.0], "配置 600s 也必须钳到 spec-014:131 的 60s 上限")

    def test_negative_cache_ttl_floor_is_at_least_30_seconds(self):
        """L-2：负缓存下限 ≥30s 必须有门禁（29s 仍命中、31s 后重新发请求）。"""
        clock = _FakeClock(100.0)
        calls = []

        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("slow inference", request=request)

        transport = httpx.MockTransport(handler)
        first = reranker.rerank_hits(
            "q", self.hits, transport=transport, clock=clock, negative_ttl=1,
        )
        self.assertEqual(first.reason, "timeout")
        with reranker._lock:
            expiry = reranker._cache[(reranker.DEFAULT_BASE_URL, "")][1]
        self.assertGreaterEqual(expiry - clock(), NEGATIVE_TTL_SECONDS,
                                "_remember 必须用 max(MIN_NEGATIVE_TTL, ttl)")
        clock.advance(29)
        second = reranker.rerank_hits(
            "q", self.hits, transport=transport, clock=clock, negative_ttl=1,
        )
        self.assertEqual(second.reason, "timeout")
        self.assertEqual(len(calls), 1, "29s 仍必须命中 ≥30s 负缓存")
        clock.advance(31)
        third = reranker.rerank_hits(
            "q", self.hits, transport=transport, clock=clock, negative_ttl=1,
        )
        self.assertEqual(third.reason, "timeout")
        self.assertEqual(len(calls), 2, "31s 后必须重新发起请求")

    def test_concurrent_first_hang_makes_only_one_network_call(self):
        """M-1：5 个并发首次请求同时 hang，只有 1 次真实重排调用，其余快速失败。"""
        wait_cap = getattr(reranker, "_RERANK_INFLIGHT_WAIT_CAP", 0.5)
        self.assertLess(wait_cap, reranker.MAX_READ_TIMEOUT,
                        "在飞等待上限必须显著小于 60s read 上限，不得各自阻塞满 60s")
        entered, release = threading.Event(), threading.Event()
        calls = []

        def handler(request):
            calls.append(request)
            entered.set()
            release.wait(timeout=8.0)
            raise httpx.ReadTimeout("slow inference", request=request)

        transport = httpx.MockTransport(handler)

        def call():
            started_at = time.monotonic()
            result = reranker.rerank_hits("q", self.hits, transport=transport)
            return result, time.monotonic() - started_at

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(call) for _ in range(5)]
            self.assertTrue(entered.wait(2.0), "必须真的发起一次重排请求")
            try:
                time.sleep(wait_cap + 0.2)
                self.assertEqual(len(calls), 1, "并发首次 hang 期间不得出现第二次真实重排调用")
            finally:
                release.set()
            outcomes = [future.result(timeout=10.0) for future in futures]
        self.assertEqual(len(calls), 1, "5 个并发首次请求只能有 1 次真实重排调用")
        for result, _elapsed in outcomes:
            self.assertFalse(result.used)
            self.assertEqual(result.reason, "timeout")
        fast = [elapsed for _result, elapsed in outcomes if elapsed < wait_cap + 1.0]
        self.assertGreaterEqual(len(fast), 4, "至少 4 个等待者应在有界等待内快速失败")
        self.assertEqual(
            reranker._cached((reranker.DEFAULT_BASE_URL, ""), time.monotonic()),
            "timeout", "leader 失败后仍须写 ≥30s 负缓存（spec-014:131）",
        )


if __name__ == "__main__":
    unittest.main()
