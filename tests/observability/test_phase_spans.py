"""spec-041 T-E：record_ollama_generation 反推 4 个阶段子 span（load/prefill/decode/overhead）。

验收点（regression-guard 边界 12：不得恒真、不得「依赖缺失就静默跳过」）：
- 调用后用真实 OTel Tracer（带 InMemorySpanExporter）捕获 SDK 上报，断言生成了
  4 个 child span，name 分别为 phase:load / phase:prefill / phase:decode / phase:overhead；
- 每个 child span 的 start_time / end_time（纳秒）与 started_at + timings 算出的
  绝对时间戳相等（同公式，允许 ±1ns 浮点误差）；
- generation 主体的 completion_start_time == started_at + first_token_ms；
- 任一阶段上报失败（SDK 抛异常）不影响其它阶段与 generation 上报，且不冒泡到业务。

本文件直接 import 被测模块与 dataclass 并真实注入 tracer，若实现被整目录删除，import 即失败。
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from backend.app.platform import config
from backend.app.platform.observability import client as obs_client
from backend.app.platform.observability import spans as spans_module
from backend.app.platform.observability.spans import (
    _to_ns,
    record_ollama_generation,
)
from backend.app.platform.ollama_direct import OllamaChatResult, OllamaTimings


def _result(**overrides) -> OllamaChatResult:
    payload = {
        "content": "答案",
        "thinking": "思考",
        "timings": OllamaTimings(
            load_ms=7000.0,
            prompt_eval_ms=300.0,
            eval_ms=1100.0,
            total_ms=8400.0,
            prompt_tokens=15,
            completion_tokens=27,
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


def _expected_phases(started_at: datetime, result: OllamaChatResult):
    """与 spans._report_phase_spans 同源的绝对起止时刻（started_at + timings）。"""
    t = result.timings
    load_start = started_at
    load_end = started_at + timedelta(milliseconds=t.load_ms)
    prefill_start = load_end
    prefill_end = prefill_start + timedelta(milliseconds=t.prompt_eval_ms)
    decode_start = started_at + timedelta(milliseconds=result.first_token_ms)
    decode_end = decode_start + timedelta(milliseconds=t.eval_ms)
    overhead_start = decode_end
    overhead_end = started_at + timedelta(milliseconds=result.client_wall_ms)
    return {
        "phase:load": (load_start, load_end),
        "phase:prefill": (prefill_start, prefill_end),
        "phase:decode": (decode_start, decode_end),
        "phase:overhead": (overhead_start, overhead_end),
    }


class _FakeGeneration:
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
    """注入真实 OTel tracer（带 InMemorySpanExporter）的假 Langfuse client。

    start_as_current_observation 只返回假 generation（不设置 OTel 当前 span），
    但 _otel_tracer 是真实 tracer，因此 _report_phase_spans 创建的子 span
    会经同一 tracer/provider 落到内存 exporter，便于断言 name 与起止时间。
    """

    def __init__(self, tracer):
        self._otel_tracer = tracer
        self.last_start_kwargs = None

    def start_as_current_observation(self, **kwargs):
        self.last_start_kwargs = kwargs
        return _FakeObservation(_FakeGeneration())


class PhaseSpanCaptureTests(unittest.TestCase):
    def setUp(self):
        obs_client.reset_for_tests()
        self.provider = TracerProvider()
        self.exporter = InMemorySpanExporter()
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.client = _FakeClient(self.provider.get_tracer("langfuse-test"))
        self.started_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def tearDown(self):
        obs_client.reset_for_tests()
        self.exporter.clear()
        self.provider.shutdown()

    def _run(self, result, started_at=None):
        with mock.patch.object(config, "LANGFUSE_ENABLED", True), \
             mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"), \
             mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"), \
             mock.patch.object(config, "LANGFUSE_SAMPLE_RATE_RAW", "1.0"), \
             mock.patch.object(obs_client, "get_client", return_value=self.client):
            record_ollama_generation(
                model="m",
                prompt_messages=SAMPLE_PROMPT,
                result=result,
                route="direct",
                started_at=started_at,
            )

    def test_four_phase_child_spans_created_with_exact_start_end_times(self):
        self._run(_result(), started_at=self.started_at)

        spans = {s.name: s for s in self.exporter.get_finished_spans()}
        self.assertEqual(
            set(spans.keys()),
            {"phase:load", "phase:prefill", "phase:decode", "phase:overhead"},
            f"应有 4 个阶段子 span，实际：{sorted(spans.keys())}",
        )

        expected = _expected_phases(self.started_at, _result())
        for name, span in spans.items():
            start_dt, end_dt = expected[name]
            exp_start = _to_ns(start_dt)
            exp_end = _to_ns(end_dt)
            # 非恒真：逐字比对绝对纳秒时间戳，允许 ±1ns 浮点误差
            self.assertTrue(
                abs(span.start_time - exp_start) <= 1,
                f"{name} start_time 期望 {exp_start}，实际 {span.start_time}",
            )
            self.assertTrue(
                abs(span.end_time - exp_end) <= 1,
                f"{name} end_time 期望 {exp_end}，实际 {span.end_time}",
            )
            # 子 span 必须被打 langfuse.observation.type=span，dual 模式才落 observations
            self.assertEqual(
                span.attributes.get("langfuse.observation.type"), "span",
                f"{name} 缺少 langfuse.observation.type=span",
            )

    def test_generation_completion_start_time_equals_started_at_plus_first_token(self):
        self._run(_result(), started_at=self.started_at)

        self.assertIsNotNone(self.client.last_start_kwargs, "generation 未被上报")
        cst = self.client.last_start_kwargs.get("completion_start_time")
        self.assertEqual(
            cst,
            self.started_at + timedelta(milliseconds=_result().first_token_ms),
            f"completion_start_time 期望 started_at+first_token_ms，实际 {cst}",
        )

    def test_one_phase_failure_does_not_block_others_or_generation(self):
        """让 phase:decode 的上报抛异常，其余 3 个仍应生成，generation 仍应上报。"""
        class _FlakyTracer:
            def __init__(self, real):
                self._real = real

            def start_as_current_span(self, name, **kwargs):
                if name == "phase:decode":
                    raise RuntimeError("injected OTel failure for decode")
                return self._real.start_as_current_span(name, **kwargs)

        self.client._otel_tracer = _FlakyTracer(self.client._otel_tracer)
        # 不应抛到业务层
        self._run(_result(), started_at=self.started_at)

        names = {s.name for s in self.exporter.get_finished_spans()}
        self.assertEqual(
            names, {"phase:load", "phase:prefill", "phase:overhead"},
            f"decode 失败后应仍有 3 个阶段 span，实际：{sorted(names)}",
        )
        self.assertIsNotNone(
            self.client.last_start_kwargs, "generation 在阶段失败时应仍被上报"
        )

    def test_tracer_blows_up_is_fail_open_and_generates_no_child_spans(self):
        """整个 tracer 抛异常：generation 仍上报、无 child span、不冒泡。"""
        boom = mock.MagicMock()
        # 让 start_as_current_span 抛异常（没有任何 span 对象被创建），覆盖「tracer 不可用」路径
        boom.start_as_current_span.side_effect = RuntimeError("tracer down")
        self.client._otel_tracer = boom

        self._run(_result(), started_at=self.started_at)

        # 抛异常路径下不会进入 with 块，exporter 不应收到任何 span（含空壳）
        self.assertEqual(
            len(self.exporter.get_finished_spans()), 0,
            "tracer 故障时不应产生任何 child span",
        )
        self.assertIsNotNone(
            self.client.last_start_kwargs, "tracer 故障时 generation 仍应上报"
        )

    def test_missing_create_span_attributes_helper_still_reports_generation(self):
        """模拟 langfuse 私有符号 `create_span_attributes` 缺失（导入期 ImportError 降级为 None）。

        验收（评审 HIGH 必改项）：模块仍可导入、record_ollama_generation 不抛异常、
        generation 主体仍上报、4 个阶段子 span 仍创建（时间戳为核心）、业务不冒泡。
        不得恒真、不得 skip——直接 monkeypatch 模块级 helper 为 None 后真实调用。
        """
        with mock.patch.object(spans_module, "_create_span_attributes", None):
            # 不应抛到业务层（导入期已容错，运行期 helper 缺失也跳过富化属性）
            self._run(_result(), started_at=self.started_at)

        # generation 主体仍上报
        self.assertIsNotNone(
            self.client.last_start_kwargs,
            "私有符号缺失时 generation 仍应上报",
        )

        # 4 个阶段子 span 仍应创建（时间戳是核心，不依赖私有 helper）
        spans = {s.name: s for s in self.exporter.get_finished_spans()}
        self.assertEqual(
            set(spans.keys()),
            {"phase:load", "phase:prefill", "phase:decode", "phase:overhead"},
            f"私有符号缺失时仍应有 4 个阶段子 span，实际：{sorted(spans.keys())}",
        )
        # 最小属性集：硬编码 langfuse.observation.type=span 仍应被打上
        for name, span in spans.items():
            self.assertEqual(
                span.attributes.get("langfuse.observation.type"), "span",
                f"{name} 缺失 helper 时仍应打最小属性集 observation.type=span",
            )


if __name__ == "__main__":
    unittest.main()
