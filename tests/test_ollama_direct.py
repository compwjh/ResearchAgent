"""直连 Ollama 采集器单测（spec-013）。

用假的 httpx 响应驱动，不依赖真实 Ollama 与网络。
重点覆盖：原生 timings 解析、thinking/content 分离、以及"耗时字段缺失"等边界。
"""

import json
import unittest
from unittest import mock

import pytest

from backend.app.services.ollama_direct import (
    OllamaChatResult,
    OllamaTimings,
    chat_direct,
    chat_direct_stream,
)
from backend.app.services.ollama import run_chat


class _FakeResponse:
    """模拟 httpx.stream 的响应对象：支持 with 与 iter_lines。"""

    def __init__(self, events, status_code=200, raise_on_iter=None):
        self.status_code = status_code
        self._events = events
        self._raise_on_iter = raise_on_iter

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_lines(self):
        for event in self._events:
            if self._raise_on_iter is not None and event is self._raise_on_iter:
                raise self._raise_on_iter
            yield json.dumps(event, ensure_ascii=False)


def _stream_patch(response, capture=None):
    """构造 httpx.stream 的替身，可选捕获调用参数。"""

    def _fake_stream(*args, **kwargs):
        if capture is not None:
            capture.update(kwargs)
        return response

    return _fake_stream


def _done_event(**overrides):
    event = {
        "model": "qwen3.8:27b-mlx",
        "done": True,
        "done_reason": "stop",
        "load_duration": 7_476_239_542,
        "prompt_eval_duration": 1_812_638_750,
        "eval_duration": 976_026_625,
        "total_duration": 10_268_029_084,
        "prompt_eval_count": 15,
        "eval_count": 27,
    }
    event.update(overrides)
    return event


class TimingsParsingTests(unittest.TestCase):
    def test_parses_nanosecond_timings_into_milliseconds(self):
        events = [
            {"message": {"role": "assistant", "content": "OK"}, "done": False},
            _done_event(),
        ]
        with mock.patch(
            "backend.app.services.ollama_direct.httpx.stream",
            _stream_patch(_FakeResponse(events)),
        ):
            result = chat_direct([{"role": "user", "content": "hi"}], "qwen3.8:27b-mlx")

        self.assertTrue(result.timings_available)
        self.assertAlmostEqual(result.timings.load_ms, 7476.24, delta=1.0)
        self.assertAlmostEqual(result.timings.prompt_eval_ms, 1812.64, delta=1.0)
        self.assertAlmostEqual(result.timings.eval_ms, 976.03, delta=1.0)
        self.assertAlmostEqual(result.timings.total_ms, 10268.03, delta=1.0)

    def test_parses_token_counts(self):
        with mock.patch(
            "backend.app.services.ollama_direct.httpx.stream",
            _stream_patch(_FakeResponse([_done_event()])),
        ):
            result = chat_direct([{"role": "user", "content": "hi"}], "m")

        self.assertEqual(result.timings.prompt_tokens, 15)
        self.assertEqual(result.timings.completion_tokens, 27)


class LangchainReasoningCompatibilityTests(unittest.TestCase):
    def test_default_langchain_call_keeps_legacy_factory_signature(self):
        graph = mock.Mock()
        graph.stream.return_value = [{"type": "token", "content": "ok"}]
        with mock.patch("backend.app.services.ollama.create_chat_model") as create_model, mock.patch(
            "backend.app.graphs.chat.build_chat_graph", return_value=graph
        ):
            list(run_chat("q", "m", route="langchain").events)

        create_model.assert_called_once_with("m")

    def test_disabled_reasoning_is_explicit_for_langchain_call(self):
        graph = mock.Mock()
        graph.stream.return_value = [{"type": "token", "content": "ok"}]
        with mock.patch("backend.app.services.ollama.create_chat_model") as create_model, mock.patch(
            "backend.app.graphs.chat.build_chat_graph", return_value=graph
        ):
            list(run_chat("q", "m", route="langchain", think=False).events)

        create_model.assert_called_once_with("m", reasoning=False)

    def test_factory_does_not_force_thinking_by_default(self):
        """默认不得下发 reasoning，否则 langchain 会发 think=true。

        ChatOllama 把 reasoning 映射为请求体 think 字段；不支持 thinking 的模型
        （如 deepseek-coder-v2:16b）收到 think=true 会返回 HTTP 400
        `does not support thinking`。改动前默认即为 None（think: null）。
        """
        from backend.app.services.ollama import create_chat_model

        self.assertIsNone(
            create_chat_model("m").reasoning,
            "默认必须保持 reasoning=None，避免对非思考模型强制 think=true",
        )

    def test_factory_forwards_explicit_reasoning(self):
        from backend.app.services.ollama import create_chat_model

        self.assertIs(create_chat_model("m", reasoning=False).reasoning, False)
        self.assertIs(create_chat_model("m", reasoning=True).reasoning, True)


class ThinkingSeparationTests(unittest.TestCase):
    def test_thinking_and_content_are_accumulated_separately(self):
        events = [
            {"message": {"role": "assistant", "thinking": "先想想", "content": ""}, "done": False},
            {"message": {"role": "assistant", "thinking": "再想想", "content": ""}, "done": False},
            {"message": {"role": "assistant", "content": "答案"}, "done": False},
            _done_event(),
        ]
        with mock.patch(
            "backend.app.services.ollama_direct.httpx.stream",
            _stream_patch(_FakeResponse(events)),
        ):
            result = chat_direct([{"role": "user", "content": "q"}], "m")

        self.assertEqual(result.thinking, "先想想再想想")
        self.assertEqual(result.content, "答案")

    def test_thinking_is_empty_string_when_absent(self):
        with mock.patch(
            "backend.app.services.ollama_direct.httpx.stream",
            _stream_patch(_FakeResponse([{"message": {"content": "x"}, "done": False}, _done_event()])),
        ):
            result = chat_direct([{"role": "user", "content": "q"}], "m")

        self.assertEqual(result.thinking, "")


class MissingTimingsTests(unittest.TestCase):
    def test_marks_unavailable_and_zeros_fields_without_raising(self):
        """某些模型/版本不返回耗时字段：必须置 0 并标记，且不得抛异常。"""
        events = [
            {"message": {"role": "assistant", "content": "hi"}, "done": False},
            {"done": True, "done_reason": "stop"},
        ]
        with mock.patch(
            "backend.app.services.ollama_direct.httpx.stream",
            _stream_patch(_FakeResponse(events)),
        ):
            result = chat_direct([{"role": "user", "content": "q"}], "m")

        self.assertFalse(result.timings_available)
        self.assertEqual(result.timings.load_ms, 0.0)
        self.assertEqual(result.timings.prompt_eval_ms, 0.0)
        self.assertEqual(result.timings.eval_ms, 0.0)
        self.assertEqual(result.timings.total_ms, 0.0)
        self.assertEqual(result.timings.prompt_tokens, 0)
        self.assertEqual(result.timings.completion_tokens, 0)
        self.assertEqual(result.content, "hi")


class LatencyRecordingTests(unittest.TestCase):
    def test_first_token_ms_is_recorded(self):
        events = [
            {"message": {"role": "assistant", "content": "a"}, "done": False},
            {"message": {"role": "assistant", "content": "b"}, "done": False},
            _done_event(),
        ]
        with mock.patch(
            "backend.app.services.ollama_direct.httpx.stream",
            _stream_patch(_FakeResponse(events)),
        ):
            result = chat_direct([{"role": "user", "content": "q"}], "m")

        self.assertGreater(result.first_token_ms, 0.0)
        self.assertGreaterEqual(result.client_wall_ms, result.first_token_ms)
        # 两个内容片段之间应有 1 个间隔
        self.assertEqual(len(result.chunk_intervals_ms), 1)

    def test_uses_trust_env_false(self):
        """macOS 系统代理会把 localhost 请求截走返回 503，必须禁用环境代理。"""
        capture = {}
        with mock.patch(
            "backend.app.services.ollama_direct.httpx.stream",
            _stream_patch(_FakeResponse([_done_event()]), capture=capture),
        ):
            chat_direct([{"role": "user", "content": "q"}], "m")

        self.assertFalse(capture.get("trust_env", True), "httpx 调用必须传 trust_env=False")

    def test_think_flag_is_sent_to_ollama(self):
        capture = {}
        with mock.patch(
            "backend.app.services.ollama_direct.httpx.stream",
            _stream_patch(_FakeResponse([_done_event()]), capture=capture),
        ):
            chat_direct([{"role": "user", "content": "q"}], "m", think=False)

        self.assertIs(capture["json"]["think"], False)


class ErrorHandlingTests(unittest.TestCase):
    def test_http_error_status_raises(self):
        with mock.patch(
            "backend.app.services.ollama_direct.httpx.stream",
            _stream_patch(_FakeResponse([], status_code=503)),
        ):
            with self.assertRaises(RuntimeError):
                chat_direct([{"role": "user", "content": "q"}], "m")

    def test_connection_error_before_any_content_raises(self):
        import httpx

        def _raise(*args, **kwargs):
            raise httpx.ConnectError("refused")

        with mock.patch("backend.app.services.ollama_direct.httpx.stream", _raise):
            with self.assertRaises(RuntimeError):
                chat_direct([{"role": "user", "content": "q"}], "m")

    def test_broken_stream_keeps_partial_content(self):
        """流中途断开：已收到的内容仍应返回，不能被吞掉。"""
        import httpx

        events = [
            {"message": {"role": "assistant", "content": "前半段"}, "done": False},
            _done_event(),
        ]
        response = _FakeResponse(events, raise_on_iter=httpx.RemoteProtocolError("closed"))

        with mock.patch(
            "backend.app.services.ollama_direct.httpx.stream",
            _stream_patch(response),
        ):
            result = chat_direct([{"role": "user", "content": "q"}], "m")

        self.assertEqual(result.content, "前半段")


class DataclassTests(unittest.TestCase):
    def test_timings_defaults_to_zero(self):
        timings = OllamaTimings()
        self.assertEqual(timings.load_ms, 0.0)
        self.assertEqual(timings.prompt_tokens, 0)


class StreamContractTests(unittest.TestCase):
    """用假响应验证 chat_direct_stream 的逐块产出与 .result 契约。"""

    def test_yields_token_events_then_exposes_result(self):
        events = [
            {"message": {"role": "assistant", "content": "你好"}, "done": False},
            {"message": {"role": "assistant", "content": "世界"}, "done": False},
            _done_event(),
        ]
        with mock.patch(
            "backend.app.services.ollama_direct.httpx.stream",
            _stream_patch(_FakeResponse(events)),
        ):
            stream = chat_direct_stream([{"role": "user", "content": "hi"}], "m")
            yielded = [event for event in stream]

        self.assertIsInstance(stream.result, OllamaChatResult)
        token_events = [e for e in yielded if e.get("type") == "token"]
        self.assertGreaterEqual(len(token_events), 1)
        self.assertTrue(all("content" in e for e in token_events))
        self.assertEqual(stream.result.content, "你好世界")

    def test_thinking_and_token_events_are_separated(self):
        events = [
            {"message": {"role": "assistant", "thinking": "先想想", "content": ""}, "done": False},
            {"message": {"role": "assistant", "content": "答案"}, "done": False},
            _done_event(),
        ]
        with mock.patch(
            "backend.app.services.ollama_direct.httpx.stream",
            _stream_patch(_FakeResponse(events)),
        ):
            stream = chat_direct_stream([{"role": "user", "content": "q"}], "m")
            yielded = [event for event in stream]

        thinking_events = [e for e in yielded if e.get("type") == "thinking"]
        token_events = [e for e in yielded if e.get("type") == "token"]
        self.assertEqual("".join(e["content"] for e in thinking_events), "先想想")
        self.assertEqual("".join(e["content"] for e in token_events), "答案")
        self.assertEqual(stream.result.thinking, "先想想")
        self.assertEqual(stream.result.content, "答案")

    def test_result_matches_chat_direct(self):
        events = [
            {"message": {"role": "assistant", "content": "x"}, "done": False},
            {"message": {"role": "assistant", "content": "y"}, "done": False},
            _done_event(),
        ]
        with mock.patch(
            "backend.app.services.ollama_direct.httpx.stream",
            _stream_patch(_FakeResponse(events)),
        ):
            via_stream = chat_direct_stream([{"role": "user", "content": "q"}], "m")
            for _ in via_stream:
                pass
        with mock.patch(
            "backend.app.services.ollama_direct.httpx.stream",
            _stream_patch(_FakeResponse(events)),
        ):
            via_direct = chat_direct([{"role": "user", "content": "q"}], "m")

        self.assertEqual(via_stream.result.content, via_direct.content)
        self.assertEqual(via_stream.result.thinking, via_direct.thinking)
        self.assertIs(via_stream.result.timings_available, via_direct.timings_available)
        self.assertEqual(via_stream.result.timings, via_direct.timings)
        # 计时类间隔两次独立调用必然不同，只比结构（长度）而非数值。
        self.assertEqual(len(via_stream.result.chunk_intervals_ms), len(via_direct.chunk_intervals_ms))

    def test_connection_error_before_any_content_still_raises(self):
        import httpx

        def _raise(*args, **kwargs):
            raise httpx.ConnectError("refused")

        with mock.patch("backend.app.services.ollama_direct.httpx.stream", _raise):
            stream = chat_direct_stream([{"role": "user", "content": "q"}], "m")
            with self.assertRaises(RuntimeError):
                list(stream)

        self.assertIsNone(stream.result)


class RealStreamCallTests(unittest.TestCase):
    """真实调用：用任意可用小模型跑 chat_direct_stream；Ollama 不可达则跳过。"""

    def _pick_model(self):
        try:
            from backend.app.services.ollama import get_available_models

            models = get_available_models()
        except Exception:
            pytest.skip("Ollama 不可达或无可用模型，跳过真实调用")
        if not models:
            pytest.skip("无可用模型")
        return "qwen3.5:9b" if "qwen3.5:9b" in models else models[0]

    def test_real_stream_yields_tokens_and_returns_result(self):
        model = self._pick_model()
        messages = [{"role": "user", "content": "用一句话说明水的沸点。"}]

        stream = chat_direct_stream(messages, model)
        token_events = []
        for event in stream:
            if event.get("type") == "token":
                token_events.append(event)

        self.assertGreaterEqual(len(token_events), 1, "应至少产出一个 token 事件")
        self.assertIsInstance(stream.result, OllamaChatResult)
        self.assertTrue(stream.result.content, "结果 content 应非空")

        via_direct = chat_direct(messages, model)
        self.assertTrue(via_direct.content, "chat_direct content 应非空")
        self.assertTrue(stream.result.content, "chat_direct_stream content 应非空")


if __name__ == "__main__":
    unittest.main()
