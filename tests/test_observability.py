"""埋点层单测（spec-013）。

核心验收点：**观测永远不影响业务**——未启用、未配置、SDK 异常时都必须静默跳过。
"""

import unittest
from unittest import mock

from backend.app.platform import config
from backend.app.platform.observability import client as obs_client
from backend.app.platform.observability import config as obs_config
from backend.app.platform.observability.spans import derive_metrics, record_event, record_ollama_generation
from backend.app.platform.observability.trace import end_trace, get_current_trace_id, start_trace
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


class SampleRateTests(unittest.TestCase):
    def setUp(self):
        obs_client.reset_for_tests()

    def tearDown(self):
        obs_client.reset_for_tests()

    def test_disabled_by_default_skips_sampling(self):
        with mock.patch.object(config, "LANGFUSE_ENABLED", False):
            self.assertFalse(obs_config.enabled())
            self.assertFalse(obs_config.should_sample())

    def test_missing_credentials_skips_sampling(self):
        with mock.patch.object(config, "LANGFUSE_ENABLED", True), \
             mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", ""), \
             mock.patch.object(config, "LANGFUSE_SECRET_KEY", ""):
            self.assertFalse(obs_config.should_sample())

    def test_sample_rate_zero_and_one(self):
        with mock.patch.object(config, "LANGFUSE_ENABLED", True), \
             mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"), \
             mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"):
            with mock.patch.object(config, "LANGFUSE_SAMPLE_RATE_RAW", "0"):
                self.assertFalse(obs_config.should_sample())
            with mock.patch.object(config, "LANGFUSE_SAMPLE_RATE_RAW", "1"):
                self.assertTrue(obs_config.should_sample())

    def test_invalid_sample_rate_falls_back_to_full(self):
        """越界或非数值都回退到 1.0：宁可多采，也不要静默丢数据。"""
        for raw in ("abc", "-0.5", "1.5", ""):
            with mock.patch.object(config, "LANGFUSE_SAMPLE_RATE_RAW", raw):
                self.assertEqual(obs_config.sample_rate(), 1.0, f"raw={raw}")


class MetricsTests(unittest.TestCase):
    def test_overhead_is_client_wall_minus_server_total(self):
        metrics = derive_metrics(_result())
        self.assertAlmostEqual(metrics["overhead_ms"], 100.0, delta=0.001)

    def test_overhead_never_negative(self):
        """客户端墙钟小于服务端总耗时（时钟误差）时，开销取 0 而非负数。"""
        metrics = derive_metrics(_result(client_wall_ms=8000.0))
        self.assertEqual(metrics["overhead_ms"], 0.0)

    def test_tokens_per_second_from_eval_duration(self):
        metrics = derive_metrics(_result())
        self.assertAlmostEqual(metrics["tokens_per_sec"], 27 / 1.1, delta=0.01)

    def test_tokens_per_second_zero_when_no_eval(self):
        result = _result(timings=OllamaTimings(total_ms=100.0))
        metrics = derive_metrics(result)
        self.assertEqual(metrics["tokens_per_sec"], 0.0)

    def test_cold_start_flag_follows_threshold(self):
        with mock.patch.object(config, "OBS_COLD_START_THRESHOLD_MS", 200.0):
            self.assertEqual(derive_metrics(_result())["is_cold_start"], 1.0)
            warm = _result(
                timings=OllamaTimings(load_ms=1.0, eval_ms=1100.0, total_ms=1400.0, completion_tokens=27)
            )
            self.assertEqual(derive_metrics(warm)["is_cold_start"], 0.0)


class NoOpSafetyTests(unittest.TestCase):
    def setUp(self):
        obs_client.reset_for_tests()

    def tearDown(self):
        obs_client.reset_for_tests()

    def test_record_is_noop_when_disabled(self):
        """未启用时不得产生任何上报动作（也不得抛异常）。"""
        with mock.patch.object(config, "LANGFUSE_ENABLED", False), mock.patch.object(
            obs_client, "get_client"
        ) as get_client_mock:
            record_ollama_generation(
                model="m",
                prompt_messages=[{"role": "user", "content": "q"}],
                result=_result(),
                route="direct",
            )
            get_client_mock.assert_not_called()

    def test_client_returns_none_without_credentials(self):
        with mock.patch.object(config, "LANGFUSE_ENABLED", True), \
             mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", ""), \
             mock.patch.object(config, "LANGFUSE_SECRET_KEY", ""):
            self.assertIsNone(obs_client.get_client())

    def test_sdk_exception_does_not_propagate(self):
        """SDK 任何异常都不得冒泡到业务。"""

        class _BrokenClient:
            def start_as_current_observation(self, **kwargs):
                raise RuntimeError("SDK 炸了")

        with mock.patch.object(config, "LANGFUSE_ENABLED", True), \
             mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"), \
             mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"), \
             mock.patch.object(obs_client, "get_client", return_value=_BrokenClient()):
            # 不应抛出
            record_ollama_generation(
                model="m",
                prompt_messages=[{"role": "user", "content": "q"}],
                result=_result(),
                route="direct",
            )
            record_event(name="kb-retrieve", duration_ms=12.0)

    def test_flush_failure_is_swallowed(self):
        class _BrokenFlush:
            def flush(self):
                raise RuntimeError("flush 失败")

        with mock.patch.object(obs_client, "get_client", return_value=_BrokenFlush()):
            obs_client.flush()  # 不应抛出


class RouteConfigTests(unittest.TestCase):
    def test_unknown_route_falls_back_to_langchain(self):
        """保持既有行为：未知取值一律走 langchain。"""
        with mock.patch.object(config, "OLLAMA_ROUTE", "weird"):
            self.assertEqual(obs_config.route(), "langchain")

    def test_valid_routes_are_accepted(self):
        for value in ("langchain", "direct"):
            with mock.patch.object(config, "OLLAMA_ROUTE", value):
                self.assertEqual(obs_config.route(), value)


class ReportingContentTests(unittest.TestCase):
    def setUp(self):
        obs_client.reset_for_tests()

    def tearDown(self):
        obs_client.reset_for_tests()

    def test_reports_generation_with_scores_and_metadata(self):
        """验证上报内容包含 prompt 组成、思考过程、耗时分解与 numeric score。"""
        captured = {}

        class _FakeObservation:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def update(self, **kwargs):
                captured.setdefault("update", []).append(kwargs)

            def score(self, **kwargs):
                captured.setdefault("scores", []).append(kwargs)

        class _FakeClient:
            def start_as_current_observation(self, **kwargs):
                captured["start"] = kwargs
                return _FakeObservation()

        with mock.patch.object(config, "LANGFUSE_ENABLED", True), \
             mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"), \
             mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"), \
             mock.patch.object(obs_client, "get_client", return_value=_FakeClient()):
            record_ollama_generation(
                model="qwen3.8:27b-mlx",
                prompt_messages=[{"role": "user", "content": "问题"}],
                result=_result(),
                route="direct",
                session_id="s-1",
                tags=["chat"],
                extra_metadata={"reasoning_duration_ms": 12.5, "answer_duration_ms": 34.0},
            )

        start = captured.get("start", {})
        self.assertEqual(start.get("as_type"), "generation")
        self.assertEqual(start.get("model"), "qwen3.8:27b-mlx")
        self.assertIn("user", start.get("input", ""))
        self.assertIsNotNone(start.get("completion_start_time"), "应传入首 token 时刻")

        metadata = start.get("metadata", {})
        # Spec024 allowlist: raw reasoning is never persisted in metadata;
        # only its presence and filtered character count are observable.
        self.assertTrue(metadata.get("reasoning_present"))
        self.assertEqual(metadata.get("reasoning_chars"), len("思考"))
        self.assertNotIn("thinking", metadata)
        self.assertNotIn("思考", repr(metadata))
        self.assertEqual(metadata.get("route"), "direct")
        self.assertNotIn("session_id", metadata)
        self.assertNotIn("timings_available", metadata)
        self.assertNotIn("load_ms", metadata)
        self.assertEqual(metadata.get("reasoning_duration_ms"), 12.5)
        self.assertEqual(metadata.get("answer_duration_ms"), 34.0)

        score_names = {item["name"] for item in captured.get("scores", [])}
        for expected in ("ttft_ms", "load_ms", "eval_ms", "tokens_per_sec", "is_cold_start"):
            self.assertIn(expected, score_names)

        outputs = captured.get("update", [])
        self.assertTrue(any("答案" in str(item.get("output", "")) for item in outputs))

    def test_long_output_is_truncated(self):
        captured = {}

        class _FakeObservation:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def update(self, **kwargs):
                captured["output"] = kwargs.get("output", "")

            def score(self, **kwargs):
                pass

        class _FakeClient:
            def start_as_current_observation(self, **kwargs):
                return _FakeObservation()

        with mock.patch.object(config, "LANGFUSE_ENABLED", True), \
             mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"), \
             mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"), \
             mock.patch.object(config, "OBS_MAX_OUTPUT_CHARS", 10), \
             mock.patch.object(obs_client, "get_client", return_value=_FakeClient()):
            record_ollama_generation(
                model="m",
                prompt_messages=[{"role": "user", "content": "q"}],
                result=_result(content="x" * 100),
                route="direct",
            )

        self.assertIn("已截断", captured.get("output", ""))


class TraceContextTests(unittest.TestCase):
    """调用级 trace 上下文：把 RAG 多阶段 observation 归到同一 trace。"""

    def setUp(self):
        obs_client.reset_for_tests()

    def tearDown(self):
        obs_client.reset_for_tests()

    def test_start_trace_sets_context_and_records_event_in_same_trace(self):
        """start_trace 之后，record_event 的 observation 归入同一 trace。"""

        class _FakeObservation:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def update(self, **kwargs):
                pass

        class _StubClient:
            def __init__(self):
                self.last_trace_context = "UNSET"

            def create_trace_id(self):
                return "a" * 32

            def start_as_current_observation(self, *, trace_context=None, **kwargs):
                self.last_trace_context = trace_context
                return _FakeObservation()

        stub = _StubClient()
        with mock.patch.object(obs_config, "enabled", return_value=True), \
             mock.patch.object(obs_config, "credentials_ready", return_value=True), \
             mock.patch.object(obs_client, "get_client", return_value=stub):
            tid = start_trace("kb-ask")
            self.assertTrue(tid, "start_trace 应返回非空 trace id")
            self.assertEqual(get_current_trace_id(), tid, "ContextVar 应指向该 trace")

            record_event(name="kb.embedding")
            recorded = stub.last_trace_context
            self.assertIsNotNone(recorded, "有活动 trace 时应传入 trace_context")
            self.assertEqual(recorded.get("trace_id"), get_current_trace_id(),
                             "record_event 应挂到当前 trace 上")

            end_trace()
            self.assertIsNone(get_current_trace_id(), "end_trace 后 ContextVar 应复位为 None")

    def test_start_trace_noop_when_disabled(self):
        """观测未启用时 start_trace 是 no-op：返回空串且不写 ContextVar。"""
        with mock.patch.object(obs_config, "enabled", return_value=False), \
             mock.patch.object(obs_config, "credentials_ready", return_value=True), \
             mock.patch.object(obs_client, "get_client") as get_client_mock:
            self.assertEqual(start_trace("x"), "")
            self.assertIsNone(get_current_trace_id())
            get_client_mock.assert_not_called()


class MetadataCharCountTests(unittest.TestCase):
    """Spec024 allowlist metadata remains bounded and reasoning-safe."""

    def setUp(self):
        obs_client.reset_for_tests()

    def tearDown(self):
        obs_client.reset_for_tests()

    def _capture(self):
        captured = {}

        class _FakeObservation:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def update(self, **kwargs):
                captured.setdefault("update", []).append(kwargs)

            def score(self, **kwargs):
                captured.setdefault("scores", []).append(kwargs)

        class _FakeClient:
            def start_as_current_observation(self, **kwargs):
                captured["start"] = kwargs
                return _FakeObservation()

        return captured

    def _enabled(self):
        return (
            mock.patch.object(config, "LANGFUSE_ENABLED", True),
            mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"),
            mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"),
        )

    def test_char_counts_are_pre_truncation(self):
        """字符数必须是截断前的原始长度，与实际截断后的上报内容解耦。"""
        captured = self._capture()
        long_content = "x" * 100
        long_thinking = "y" * 50
        prompt = "z" * 80

        patches = self._enabled()
        patches += (
            mock.patch.object(config, "OBS_MAX_OUTPUT_CHARS", 10),
            mock.patch.object(config, "OBS_MAX_INPUT_CHARS", 10),
            mock.patch.object(obs_client, "get_client", return_value=self._make_client(captured)),
        )
        import contextlib
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            record_ollama_generation(
                model="m",
                prompt_messages=[{"role": "user", "content": prompt}],
                result=_result(content=long_content, thinking=long_thinking),
                route="direct",
            )

        metadata = captured.get("start", {}).get("metadata", {})
        self.assertTrue(metadata.get("reasoning_present"))
        self.assertEqual(metadata.get("reasoning_chars"), len(long_thinking))
        self.assertNotIn("output_chars", metadata)
        self.assertNotIn("thinking_chars", metadata)
        self.assertNotIn("input_chars", metadata)
        self.assertNotIn("y" * 10, repr(metadata))

        # 实际上报的 output 确实被截断，与字符数字段解耦。
        outputs = captured.get("update", [])
        self.assertTrue(any("已截断" in str(item.get("output", "")) for item in outputs))
        # 而 input 也截断了。
        self.assertIn("已截断", captured.get("start", {}).get("input", ""))

    def _make_client(self, captured):
        class _FakeObservation:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def update(self, **kwargs):
                captured.setdefault("update", []).append(kwargs)

            def score(self, **kwargs):
                captured.setdefault("scores", []).append(kwargs)

        class _FakeClient:
            def start_as_current_observation(self, **kwargs):
                captured["start"] = kwargs
                return _FakeObservation()

        return _FakeClient()

    def test_thinking_chars_zero_when_absent(self):
        """无思考过程时 thinking_chars 为 0。"""
        captured = self._capture()
        patches = self._enabled() + (
            mock.patch.object(obs_client, "get_client", return_value=self._make_client(captured)),
        )
        import contextlib
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            record_ollama_generation(
                model="m",
                prompt_messages=[{"role": "user", "content": "q"}],
                result=_result(content="答案", thinking=""),
                route="direct",
            )

        metadata = captured.get("start", {}).get("metadata", {})
        self.assertFalse(metadata.get("reasoning_present"))
        self.assertEqual(metadata.get("reasoning_chars"), 0)
        self.assertNotIn("thinking_chars", metadata)
        self.assertNotIn("output_chars", metadata)

    def test_failure_records_success_flag_and_error_type(self):
        """失败时只保留稳定错误码，不暴露旧 success/error-type 字段。"""
        captured = self._capture()
        patches = self._enabled() + (
            mock.patch.object(obs_client, "get_client", return_value=self._make_client(captured)),
        )
        import contextlib
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            record_ollama_generation(
                model="m",
                prompt_messages=[{"role": "user", "content": "q"}],
                result=_result(),
                route="direct",
                success=False,
                error_type="ValueError",
                extra_metadata={"stable_error_code": "CHAT_FAILED"},
            )

        metadata = captured.get("start", {}).get("metadata", {})
        self.assertEqual(metadata.get("stable_error_code"), "CHAT_FAILED")
        self.assertNotIn("success", metadata)
        self.assertNotIn("success_flag", metadata)
        self.assertNotIn("error_type", metadata)

    def test_success_default_has_no_error_type(self):
        """默认成功观测不再写入旧 success/error-type 字段。"""
        captured = self._capture()
        patches = self._enabled() + (
            mock.patch.object(obs_client, "get_client", return_value=self._make_client(captured)),
        )
        import contextlib
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            record_ollama_generation(
                model="m",
                prompt_messages=[{"role": "user", "content": "q"}],
                result=_result(),
                route="direct",
            )

        metadata = captured.get("start", {}).get("metadata", {})
        self.assertTrue(metadata.get("reasoning_present"))
        self.assertEqual(metadata.get("reasoning_chars"), len("思考"))
        self.assertNotIn("success", metadata)
        self.assertNotIn("success_flag", metadata)
        self.assertNotIn("error_type", metadata)


class ChainTypeMetadataTests(unittest.TestCase):
    """旧 chain_type 字段已移除；保留 Spec024 观测 allowlist 断言。"""

    def setUp(self):
        obs_client.reset_for_tests()

    def tearDown(self):
        obs_client.reset_for_tests()

    def _capture(self):
        captured = {}

        class _FakeObservation:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def update(self, **kwargs):
                pass

            def score(self, **kwargs):
                pass

        class _FakeClient:
            def start_as_current_observation(self, **kwargs):
                captured["start"] = kwargs
                return _FakeObservation()

        return captured, _FakeClient()

    def _record(self, *, name="ollama-chat", extra_metadata=None, success=True):
        captured, client = self._capture()
        with mock.patch.object(config, "LANGFUSE_ENABLED", True), \
             mock.patch.object(config, "LANGFUSE_PUBLIC_KEY", "pk"), \
             mock.patch.object(config, "LANGFUSE_SECRET_KEY", "sk"), \
             mock.patch.object(obs_client, "get_client", return_value=client):
            record_ollama_generation(
                model="m",
                prompt_messages=[{"role": "user", "content": "q"}],
                result=_result(),
                name=name,
                extra_metadata=extra_metadata,
                success=success,
                error_type="RuntimeError" if not success else None,
            )
        return captured["start"]["metadata"]

    def test_default_name_gets_chat_chain_type(self):
        metadata = self._record()
        self.assertTrue(metadata["reasoning_present"])
        self.assertEqual(metadata["reasoning_chars"], len("思考"))
        self.assertNotIn("chain_type", metadata)

    def test_kb_generation_name_gets_kb_chain_type(self):
        metadata = self._record(name="kb.generation")
        self.assertTrue(metadata["reasoning_present"])
        self.assertNotIn("chain_type", metadata)

    def test_non_empty_extra_metadata_chain_type_wins(self):
        metadata = self._record(
            name="kb.generation",
            extra_metadata={"chain_type": "custom", "stable_error_code": "KB_FAILED"},
        )
        self.assertEqual(metadata["stable_error_code"], "KB_FAILED")
        self.assertNotIn("chain_type", metadata)

    def test_failure_path_also_gets_default_chain_type(self):
        metadata = self._record(name="kb.generation", success=False)
        self.assertTrue(metadata["reasoning_present"])
        self.assertNotIn("chain_type", metadata)
        self.assertNotIn("success_flag", metadata)


if __name__ == "__main__":
    unittest.main()
