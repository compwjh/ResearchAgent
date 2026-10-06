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
    """与 spans._report_phase_spans 同源的绝对起止时刻（started_at + 服务端时间轴）。

    spec-041 T-H 修正：decode 不再从 first_token_ms 起算（eval_ms 含思考 token 的
    生成，从 prefill 结束就开始算），四段改为首尾相接铺满 [base, base + 墙钟]。
    """
    t = result.timings
    server_total_ms = t.load_ms + t.prompt_eval_ms + t.eval_ms
    end_ms = max(result.client_wall_ms, server_total_ms)
    load_start = started_at
    load_end = started_at + timedelta(milliseconds=t.load_ms)
    prefill_start = load_end
    prefill_end = prefill_start + timedelta(milliseconds=t.prompt_eval_ms)
    decode_start = prefill_end
    decode_end = started_at + timedelta(milliseconds=server_total_ms)
    overhead_start = decode_end
    overhead_end = started_at + timedelta(milliseconds=end_ms)
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

    def test_phases_are_contiguous_and_never_exceed_client_wall(self):
        """四段须首尾相接，且任何一段都不得超出真实结束时刻（client_wall_ms）。"""
        self._run(_result(), started_at=self.started_at)

        spans = {s.name: s for s in self.exporter.get_finished_spans()}
        wall_end = _to_ns(self.started_at + timedelta(milliseconds=_result().client_wall_ms))
        for name, span in spans.items():
            self.assertGreaterEqual(
                span.end_time, span.start_time, f"{name} 出现了负时长",
            )
            self.assertLessEqual(
                span.end_time, wall_end + 1,
                f"{name} 结束于 {span.end_time}，超出真实墙钟结束时刻 {wall_end}",
            )
        order = ["phase:load", "phase:prefill", "phase:decode", "phase:overhead"]
        for prev, nxt in zip(order, order[1:], strict=False):
            self.assertTrue(
                abs(spans[prev].end_time - spans[nxt].start_time) <= 1,
                f"{prev} 终点 {spans[prev].end_time} 与 {nxt} 起点 {spans[nxt].start_time} 不相接",
            )

    def test_decode_uses_server_timeline_not_first_token_plus_eval(self):
        """spec-041 T-H 回归锁定：用一次真实调用（预热后）的实测数字。

        旧口径 decode=[first_token_ms, first_token_ms+eval_ms] 会算出 2449.6+3450=
        5899.6ms，比真实墙钟 3915.9ms 多出近 2s：decode 条会伸出父 generation 之外，
        且 overhead 因起点晚于终点而被压成 0。新口径按服务端时间轴 (load+prefill+eval)
        截断，四段铺满 [0, 墙钟]。
        """
        real = _result(
            timings=OllamaTimings(
                load_ms=26.8, prompt_eval_ms=352.5, eval_ms=3450.0,
                total_ms=3845.6, prompt_tokens=103, completion_tokens=18,
            ),
            first_token_ms=2449.6,
            client_wall_ms=3915.9,
        )
        self._run(real, started_at=self.started_at)

        spans = {s.name: s for s in self.exporter.get_finished_spans()}
        # 正向：decode 终点必须是服务端三阶段之和
        expected_decode_end = _to_ns(
            self.started_at + timedelta(milliseconds=26.8 + 352.5 + 3450.0)
        )
        self.assertTrue(
            abs(spans["phase:decode"].end_time - expected_decode_end) <= 1,
            f"decode 终点期望 {expected_decode_end}（服务端 total），实际 {spans['phase:decode'].end_time}",
        )
        # 反向（防恒真）：绝不能落回旧口径的 first_token_ms + eval_ms
        old_decode_end = _to_ns(self.started_at + timedelta(milliseconds=2449.6 + 3450.0))
        self.assertNotEqual(
            spans["phase:decode"].end_time, old_decode_end,
            "decode 退回了旧口径 first_token_ms + eval_ms（会超出真实墙钟）",
        )
        # overhead 必须仍是有效时长（旧口径下会被压成 0）
        overhead = spans["phase:overhead"]
        self.assertGreater(
            overhead.end_time - overhead.start_time, 0,
            "overhead 不应为 0：客户端开销 = 墙钟 - 服务端 total",
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


class _BackdatingClient(_FakeClient):
    """让 generation 持有**真实** OTel span，便于断言起点回填结果。

    复用真实 tracer 的 `start_span`（非 current），使 `_backdate_generation_start`
    改写的是真实 `Span._start_time`，从而能被逐字断言。
    """

    def __init__(self, tracer):
        super().__init__(tracer)
        self.generation = None
        self.generation_span = None

    def start_as_current_observation(self, **kwargs):
        self.last_start_kwargs = kwargs
        span = self._otel_tracer.start_span("ollama-chat")
        self.generation_span = span
        generation = _FakeGeneration()
        generation._otel_span = span
        self.generation = generation
        return _FakeObservation(generation)


class GenerationStartBackdateTests(unittest.TestCase):
    """spec-041 T-G：generation 主体起点必须回填到真实请求起点。

    不回填时 startTime≈endTime（SDK 不支持 start_time）：实测一次 21.8s 的调用
    generation 落在末尾且 dur 只有 11ms，瀑布图父子颠倒、延迟分位统计全是错的。
    """

    def setUp(self):
        obs_client.reset_for_tests()
        self.provider = TracerProvider()
        self.exporter = InMemorySpanExporter()
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.client = _BackdatingClient(self.provider.get_tracer("langfuse-test"))

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

    def test_generation_start_equals_started_at_exactly(self):
        result = _result()  # client_wall_ms=8500
        started_at = datetime.now(timezone.utc) - timedelta(milliseconds=result.client_wall_ms)

        self._run(result, started_at=started_at)

        span = self.client.generation_span
        self.assertIsNotNone(span, "generation 未被上报")
        # 非恒真：逐字比对绝对纳秒时间戳，允许 ±1ns
        self.assertTrue(
            abs(span.start_time - _to_ns(started_at)) <= 1,
            f"generation 起点期望 {_to_ns(started_at)}（started_at），实际 {span.start_time}",
        )

    def test_phase_spans_never_start_before_generation(self):
        """父 generation 起点回填后，4 个子 span 都不得早于它（父子关系不得颠倒）。"""
        result = _result()
        started_at = datetime.now(timezone.utc) - timedelta(milliseconds=result.client_wall_ms)

        self._run(result, started_at=started_at)

        gen_start = self.client.generation_span.start_time
        phase_spans = [s for s in self.exporter.get_finished_spans() if s.name.startswith("phase:")]
        self.assertEqual(len(phase_spans), 4, f"应有 4 个阶段 span，实际 {len(phase_spans)}")
        for span in phase_spans:
            self.assertGreaterEqual(
                span.start_time, gen_start,
                f"{span.name} 起点 {span.start_time} 早于 generation 起点 {gen_start}",
            )

    def test_without_started_at_backdates_by_client_wall_ms(self):
        result = _result()  # client_wall_ms=8500
        before = datetime.now(timezone.utc)

        self._run(result, started_at=None)

        span = self.client.generation_span
        expected = _to_ns(before - timedelta(milliseconds=result.client_wall_ms))
        # 容差 500ms：只验算「确实是往过去回填了约一个墙钟」，不做逐字比对
        self.assertTrue(
            abs(span.start_time - expected) <= 500 * 1_000_000,
            f"未传 started_at 时期望约 {expected}，实际 {span.start_time}",
        )
        # 反向断言（防恒真）：必须明显早于「现在」，即确实被回填过
        self.assertLess(
            span.start_time, _to_ns(before) - 5000 * 1_000_000,
            f"generation 起点 {span.start_time} 未被回填，仍约等于上报时刻",
        )

    def test_future_started_at_is_not_backdated(self):
        """起点落在未来时不得回填，绝不产生未来时间戳或负时长。"""
        result = _result()
        started_at = datetime.now(timezone.utc) + timedelta(seconds=60)
        before = datetime.now(timezone.utc)

        self._run(result, started_at=started_at)

        span = self.client.generation_span
        now_ns = _to_ns(datetime.now(timezone.utc))
        self.assertLessEqual(span.start_time, now_ns, "回填产生了未来时间戳")
        self.assertGreater(
            span.start_time, _to_ns(before) - 1_000_000_000,
            f"未回填时起点应保持在调用时刻附近，实际 {span.start_time}",
        )

    def test_missing_otel_span_is_fail_open(self):
        """`_otel_span` 缺失 / 不可回填时静默降级：不抛异常，generation 仍上报。"""
        class _NoSpanGeneration(_FakeGeneration):
            @property
            def _otel_span(self):
                return None

        class _NoSpanClient(_FakeClient):
            def start_as_current_observation(self, **kwargs):
                self.last_start_kwargs = kwargs
                return _FakeObservation(_NoSpanGeneration())

        self.client = _NoSpanClient(self.provider.get_tracer("langfuse-test"))
        started_at = datetime.now(timezone.utc) - timedelta(milliseconds=8500)

        # 不抛到业务层（fail-open）
        self._run(_result(), started_at=started_at)

        self.assertIsNotNone(
            self.client.last_start_kwargs, "otel span 缺失时 generation 仍应上报"
        )
        # 阶段子 span 也不受影响
        self.assertEqual(
            len(self.exporter.get_finished_spans()), 4,
            "otel span 缺失时 4 个阶段子 span 仍应创建",
        )

    def test_backdate_failure_is_fail_open(self):
        """写入 `_start_time` 抛异常时不得冒泡，generation 仍上报。"""
        class _FrozenStartSpan:
            """_start_time 只读（property 无 setter）→ 赋值抛 AttributeError。"""
            def __init__(self):
                self._value = _to_ns(datetime.now(timezone.utc))

            @property
            def _start_time(self):
                return self._value

        class _FrozenClient(_FakeClient):
            def start_as_current_observation(self, **kwargs):
                self.last_start_kwargs = kwargs
                generation = _FakeGeneration()
                generation._otel_span = _FrozenStartSpan()
                return _FakeObservation(generation)

        self.client = _FrozenClient(self.provider.get_tracer("langfuse-test"))
        started_at = datetime.now(timezone.utc) - timedelta(milliseconds=8500)

        self._run(_result(), started_at=started_at)

        self.assertIsNotNone(
            self.client.last_start_kwargs, "回填抛异常时 generation 仍应上报（fail-open）"
        )


if __name__ == "__main__":
    unittest.main()
