"""spec-045 Task 05 红测：观测采样一致 + flush 出 SSE + 私有 SDK 兼容层降级告警。

三项均为「缺陷修复 / 能力补齐」类，先红后绿。未实现的符号（sdk_compat / enqueue_flush /
采样 ContextVar）用方法内延迟导入，使缺失只让对应用例失败，不破坏整模块收集。

运行：
  .venv/bin/python -m pytest tests/observability/test_task05_decoupling.py -q
"""

import itertools
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from backend.app.platform import config
from backend.app.platform.observability import client as obs_client
from backend.app.platform.observability import config as obs_config
from backend.app.platform.observability.trace import end_trace, start_trace
from backend.app.platform.ollama_direct import OllamaChatResult, OllamaTimings


def _result(**overrides):
    payload = {
        "content": "答案",
        "thinking": "思考",
        "timings": OllamaTimings(
            load_ms=7000.0, prompt_eval_ms=300.0, eval_ms=1100.0,
            total_ms=8400.0, prompt_tokens=15, completion_tokens=27,
        ),
        "timings_available": True,
        "first_token_ms": 7300.0,
        "client_wall_ms": 8500.0,
        "chunk_intervals_ms": (40.0, 41.0),
    }
    payload.update(overrides)
    return OllamaChatResult(**payload)


SAMPLE_PROMPT = [
    {"role": "system", "content": "你是学术研究助手"},
    {"role": "user", "content": "请总结这篇论文的核心贡献与实验设置"},
]


class TraceSamplingConsistencyTests(unittest.TestCase):
    """F11 / spec-045 03：同一 trace/请求内各阶段采样决策必须一致。"""

    def setUp(self):
        obs_client.reset_for_tests()

    def tearDown(self):
        obs_client.reset_for_tests()
        from backend.app.platform.observability.config import reset_sample_decision
        reset_sample_decision()

    def test_same_trace_decisions_consistent_at_low_rate(self):
        from backend.app.platform.observability.config import _sample_decision
        # 当前实现：每次调用独立 random.random() → 同一 trace 内各阶段可能不一致。
        with mock.patch.object(config, "LANGFUSE_ENABLED", True), \
             mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"), \
             mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"), \
             mock.patch.object(config, "LANGFUSE_SAMPLE_RATE_RAW", "0.1"), \
             mock.patch("random.random", side_effect=itertools.cycle([0.9, 0.05])):
            decisions = [obs_config.should_sample() for _ in range(8)]
            self.assertEqual(
                len(set(decisions)), 1,
                f"同一 trace 内采样决策必须一致，实际 {decisions}",
            )
            self.assertIsNotNone(
                _sample_decision.get(), "trace 级决策应被缓存到 ContextVar"
            )

    def test_start_trace_caches_decision_for_whole_trace(self):
        from backend.app.platform.observability.config import _sample_decision

        class _StubClient:
            def create_trace_id(self):
                return "a" * 32

            def start_as_current_observation(self, *, trace_context=None, **kwargs):
                return SimpleNamespace()

        with mock.patch.object(config, "LANGFUSE_ENABLED", True), \
             mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"), \
             mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"), \
             mock.patch.object(config, "LANGFUSE_SAMPLE_RATE_RAW", "0.1"), \
             mock.patch.object(obs_client, "get_client", return_value=_StubClient()), \
             mock.patch("random.random", side_effect=itertools.cycle([0.9, 0.05, 0.9, 0.05])):
            tid = start_trace("kb-ask")
            self.assertTrue(tid)
            # 入口决策（random=0.9→不采样 False）已被缓存，后续判断必须一致为 False
            self.assertFalse(
                obs_config.should_sample(),
                "start_trace 后应缓存同一采样决策，record_* 不得重新随机",
            )
            end_trace()
            self.assertIsNone(
                _sample_decision.get(), "end_trace 应复位采样决策 ContextVar"
            )


class FlushQueueDecouplingTests(unittest.TestCase):
    """F9 / spec-045 04：flush 移出 SSE 关键路径，enqueue_flush 必须非阻塞。"""

    def setUp(self):
        obs_client.reset_for_tests()

    def tearDown(self):
        obs_client.reset_for_tests()

    def test_enqueue_flush_is_nonblocking_when_client_hangs(self):
        from backend.app.platform.observability.client import enqueue_flush

        class _SlowFlushClient:
            def __init__(self):
                self._gate = threading.Event()

            def flush(self):
                # 模拟 Langfuse 挂起（client.py 的 timeout=5 仍会阻塞到这里）
                self._gate.wait(timeout=10)

        client = _SlowFlushClient()
        with mock.patch.object(obs_client, "get_client", return_value=client):
            start = time.perf_counter()
            enqueue_flush()
            elapsed = time.perf_counter() - start
            self.assertLess(
                elapsed, 0.1,
                f"enqueue_flush 必须非阻塞，不应被 5s flush 拖慢（耗时 {elapsed:.3f}s）",
            )
            client._gate.set()


class SdkCompatDegradationTests(unittest.TestCase):
    """F16 / Q7：私有 SDK 符号缺失时显式降级 + 告警，主链路仍正常。"""

    def setUp(self):
        obs_client.reset_for_tests()

    def tearDown(self):
        obs_client.reset_for_tests()

    def test_missing_create_span_attributes_warns_and_returns_empty(self):
        from backend.app.platform.observability import sdk_compat
        with mock.patch.object(sdk_compat, "_create_span_attributes", None):
            with self.assertLogs(logger=sdk_compat.logger, level="WARNING") as cm:
                attrs = sdk_compat.create_span_attributes(
                    observation_type="span", metadata={"phase": "x"}
                )
            self.assertEqual(attrs, {})
            self.assertTrue(
                any("create_span_attributes" in m for m in cm.output), cm.output
            )

    def test_missing_otel_tracer_warns_and_returns_none(self):
        from backend.app.platform.observability import sdk_compat

        class _NoTracer:
            pass

        with self.assertLogs(logger=sdk_compat.logger, level="WARNING") as cm:
            tracer = sdk_compat.get_otel_tracer(_NoTracer())
        self.assertIsNone(tracer)
        self.assertTrue(any("_otel_tracer" in m for m in cm.output), cm.output)

    def test_missing_otel_span_warns_but_main_path_ok(self):
        from backend.app.platform.observability import sdk_compat
        from backend.app.platform.observability.spans import record_ollama_generation
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        provider = TracerProvider()
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        class _NoSpanGeneration:
            def __init__(self):
                self.updates = []
                self.scores = []

            def update(self, **kwargs):
                self.updates.append(kwargs)

            def score(self, **kwargs):
                self.scores.append(kwargs)

        class _FakeObservation:
            def __init__(self, generation):
                self._generation = generation

            def __enter__(self):
                return self._generation

            def __exit__(self, *args):
                return False

        class _FakeClient:
            def __init__(self, tracer):
                self._otel_tracer = tracer
                self.last_start_kwargs = None

            def start_as_current_observation(self, **kwargs):
                self.last_start_kwargs = kwargs
                # 故意不设 _otel_span：模拟私有符号缺失
                return _FakeObservation(_NoSpanGeneration())

        client = _FakeClient(provider.get_tracer("langfuse-test"))
        with mock.patch.object(config, "LANGFUSE_ENABLED", True), \
             mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"), \
             mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"), \
             mock.patch.object(config, "LANGFUSE_SAMPLE_RATE_RAW", "1.0"), \
             mock.patch.object(obs_client, "get_client", return_value=client):
            with self.assertLogs(logger=sdk_compat.logger, level="WARNING") as cm:
                record_ollama_generation(
                    model="m",
                    prompt_messages=SAMPLE_PROMPT,
                    result=_result(),
                    route="direct",
                )
        self.assertTrue(
            any("otel_span" in m or "_otel_span" in m for m in cm.output),
            cm.output,
        )
        # 主链路正常：generation 仍上报、4 个阶段子 span 仍创建（时间戳为核心）
        self.assertIsNotNone(client.last_start_kwargs)
        self.assertEqual(len(exporter.get_finished_spans()), 4)
        provider.shutdown()


if __name__ == "__main__":
    unittest.main()
