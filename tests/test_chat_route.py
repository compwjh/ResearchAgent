"""聊天链路 route 切换 + 埋点接入测试（spec-013）。

不依赖真实 Ollama：mock create_chat_model 提供假 stream，
并通过 TestClient 验证 /api/chat 默认链路 SSE 仍含 meta/token/done。
"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.chat.application.chat_runner import run_chat
from backend.app.main import app
from backend.app.platform.ollama_direct import OllamaChatResult, OllamaTimings


class _FakeModel:
    """模拟 ChatOllama：.stream(messages) 产出带 .content 的片段。"""

    def __init__(self, chunks):
        self._chunks = chunks

    def stream(self, question):
        for text in self._chunks:
            yield SimpleNamespace(content=text)


class _FakeModelError:
    """模拟 .stream 在产出部分片段后抛异常。"""

    def __init__(self, chunks, error):
        self._chunks = chunks
        self._error = error

    def stream(self, question):
        for text in self._chunks:
            yield SimpleNamespace(content=text)
        raise self._error


class SimpleNamespace:
    def __init__(self, content):
        self.content = content


def _mock_model(chunks):
    return lambda _name: _FakeModel(chunks)


class _CapturingModel:
    def __init__(self, chunks):
        self._chunks = chunks
        self.payloads = []

    def stream(self, payload):
        self.payloads.append(payload)
        for text in self._chunks:
            yield SimpleNamespace(content=text)


class RunChatTests(unittest.TestCase):
    def test_langchain_normalizes_prompt_and_question_to_messages(self):
        model = _CapturingModel(["ok"])
        with patch("backend.app.platform.ollama.create_chat_model", return_value=model):
            prompt_run = run_chat("原始问题", "m", route="langchain", prompt="分类 Prompt")
            list(prompt_run)
            question_run = run_chat("旧 question 路径", "m", route="langchain")
            list(question_run)

        self.assertEqual(prompt_run.result.content, "ok")
        self.assertEqual(question_run.result.content, "ok")
        self.assertEqual(model.payloads[0], [{"role": "user", "content": "分类 Prompt"}])
        self.assertEqual(model.payloads[1], [{"role": "user", "content": "旧 question 路径"}])

    def test_langchain_merges_multiple_system_messages_before_history(self):
        model = _CapturingModel(["ok"])
        messages = [
            {"role": "system", "content": "平台约束"},
            {"role": "system", "content": "项目规则"},
            {"role": "user", "content": "上一问"},
            {"role": "assistant", "content": "上一答"},
            {"role": "tool", "content": "工具结果"},
            {"role": "user", "content": "当前问题"},
        ]
        with patch("backend.app.platform.ollama.create_chat_model", return_value=model):
            list(run_chat("当前问题", "m", route="langchain", messages=messages))

        self.assertEqual(
            model.payloads[0],
            [
                {"role": "system", "content": "平台约束\n\n项目规则"},
                {"role": "user", "content": "上一问"},
                {"role": "assistant", "content": "上一答"},
                {"role": "tool", "content": "工具结果"},
                {"role": "user", "content": "当前问题"},
            ],
        )

    def test_langchain_keeps_single_system_message_unchanged(self):
        model = _CapturingModel(["ok"])
        messages = [
            {"role": "system", "content": "唯一系统规则"},
            {"role": "user", "content": "当前问题"},
        ]
        with patch("backend.app.platform.ollama.create_chat_model", return_value=model):
            list(run_chat("当前问题", "m", route="langchain", messages=messages))

        self.assertEqual(model.payloads[0], messages)

    def test_direct_keeps_multiple_system_messages_unchanged(self):
        class _FakeStream:
            result = OllamaChatResult("ok", "", OllamaTimings(), False, 0, 0)

            def __iter__(self):
                yield {"type": "token", "content": "ok"}

        messages = [
            {"role": "system", "content": "平台约束"},
            {"role": "system", "content": "项目规则"},
            {"role": "user", "content": "当前问题"},
        ]
        with patch("backend.app.chat.application.chat_runner.chat_direct_stream", return_value=_FakeStream()) as direct:
            list(run_chat("当前问题", "m", route="direct", messages=messages))

        self.assertEqual(direct.call_args.args[0], messages)

    def test_langchain_route_yields_tokens_and_synthesizes_result(self):
        with patch("backend.app.platform.ollama.create_chat_model", side_effect=_mock_model(["Hel", "lo", "!"])):
            run = run_chat("你好", "qwen3.5:9b", route="langchain")
            self.assertEqual(run.route, "langchain")
            collected = list(run)

        types = [event["type"] for event in collected]
        self.assertTrue(all(t == "token" for t in types))
        self.assertEqual(len(collected), 3)
        self.assertEqual(run.result.content, "Hello!")
        self.assertIs(run.result.timings_available, False)
        self.assertEqual(run.result.thinking, "")

    def test_unknown_route_falls_back_to_langchain(self):
        with patch("backend.app.platform.ollama.create_chat_model", side_effect=_mock_model(["x"])):
            run = run_chat("q", "m", route="weird")
            self.assertEqual(run.route, "langchain")
            events = list(run)
            self.assertEqual(events[0]["type"], "token")
            self.assertEqual(run.result.content, "x")

    def test_default_route_is_langchain(self):
        with patch("backend.app.platform.ollama.create_chat_model", side_effect=_mock_model(["a"])):
            run = run_chat("q", "m")
            self.assertEqual(run.route, "langchain")
            list(run)
            self.assertEqual(run.result.content, "a")

    def test_direct_route_uses_chat_direct_stream(self):
        class _FakeStream:
            def __init__(self):
                self.result = OllamaChatResult(
                    content="direct-out",
                    thinking="",
                    timings=OllamaTimings(),
                    timings_available=True,
                    first_token_ms=0.0,
                    client_wall_ms=0.0,
                 )

            def __iter__(self):
                for c in ["a", "b"]:
                    yield {"type": "token", "content": c}

        with patch("backend.app.chat.application.chat_runner.chat_direct_stream") as mock_stream:
            fake = _FakeStream()
            mock_stream.return_value = fake
            run = run_chat("q", "m", route="direct")
            events = list(run)

        self.assertEqual(run.route, "direct")
        self.assertEqual([e["content"] for e in events], ["a", "b"])
        self.assertEqual(run.result.content, "direct-out")
        mock_stream.assert_called_once()

    def test_exception_path_still_reports_partial_result(self):
        model = _FakeModelError(["par", "tial"], RuntimeError("boom"))
        with patch("backend.app.platform.ollama.create_chat_model", return_value=model):
            run = run_chat("q", "m", route="langchain")
            with self.assertRaises(RuntimeError):
                list(run)
        # 异常发生在驱动器内，result 仍因 finally 被合成
        self.assertIsNotNone(run.result)
        self.assertEqual(run.result.content, "partial")


class ChatApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _post_chat(self):
        with patch("backend.app.api.routes_chat.get_available_models", return_value=["qwen3.5:9b"]), patch(
            "backend.app.platform.ollama.create_chat_model", side_effect=_mock_model(["Hi", " there"])
        ):
            response = self.client.post("/api/chat", json={"question": "hello", "model": "qwen3.5:9b"})
        return response

    def test_default_route_sse_has_meta_token_done(self):
        response = self._post_chat()
        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "meta"', response.text)
        self.assertIn('"type": "token"', response.text)
        self.assertIn('"type": "done"', response.text)

    def test_record_generation_called_once_with_route(self):
        with patch("backend.app.api.routes_chat.get_available_models", return_value=["qwen3.5:9b"]), patch(
            "backend.app.platform.ollama.create_chat_model", side_effect=_mock_model(["ok"])
        ), patch("backend.app.api.routes_chat.record_ollama_generation") as mock_record:
            response = self.client.post("/api/chat", json={"question": "hi", "model": "qwen3.5:9b"})
        self.assertEqual(response.status_code, 200)
        mock_record.assert_called_once()
        kwargs = mock_record.call_args.kwargs
        self.assertEqual(kwargs["model"], "qwen3.5:9b")
        self.assertEqual(kwargs["route"], "langchain")
        self.assertEqual([message["role"] for message in kwargs["prompt_messages"]], ["system", "user"])
        self.assertTrue(all(message["content"] == "" for message in kwargs["prompt_messages"]))
        self.assertEqual(kwargs["extra_metadata"]["role_count"], 2)
        self.assertEqual(kwargs["extra_metadata"]["role_names"], ["system", "user"])
        self.assertEqual(kwargs["extra_metadata"]["char_counts"][-1], len("hi"))
        self.assertEqual(kwargs["tags"], ["chat"])
        self.assertIsNotNone(kwargs["result"])

    def test_prompt_never_contains_secrets(self):
        # 即便问题里含敏感样内容，观测只保留 role 与脱敏后的空 content。
        with patch("backend.app.api.routes_chat.get_available_models", return_value=["qwen3.5:9b"]), patch(
            "backend.app.platform.ollama.create_chat_model", side_effect=_mock_model(["ok"])
        ), patch("backend.app.api.routes_chat.record_ollama_generation") as mock_record:
            self.client.post("/api/chat", json={"question": "secret-token", "model": "qwen3.5:9b"})
        kwargs = mock_record.call_args.kwargs
        self.assertEqual([message["role"] for message in kwargs["prompt_messages"]], ["system", "user"])
        self.assertTrue(all(message["content"] == "" for message in kwargs["prompt_messages"]))
        self.assertNotIn("secret-token", repr(kwargs["prompt_messages"]))
        self.assertEqual(kwargs["extra_metadata"]["role_names"], ["system", "user"])
        self.assertEqual(kwargs["extra_metadata"]["char_counts"][-1], len("secret-token"))

    def test_error_path_still_streams_error_and_does_not_crash(self):
        model = _FakeModelError(["par"], RuntimeError("boom"))
        with patch("backend.app.api.routes_chat.get_available_models", return_value=["qwen3.5:9b"]), patch(
            "backend.app.platform.ollama.create_chat_model", return_value=model
        ), patch("backend.app.api.routes_chat.record_ollama_generation") as mock_record:
            response = self.client.post(
                "/api/chat",
                json={"question": "hi", "model": "qwen3.5:9b", "mode": "developer"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "error"', response.text)
        # 异常路径下，已收集的 result 仍被上报一次
        mock_record.assert_called_once()
        self.assertEqual(mock_record.call_args.kwargs["tags"], ["chat"])


if __name__ == "__main__":
    unittest.main()
