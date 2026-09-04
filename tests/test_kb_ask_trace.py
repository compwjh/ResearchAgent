"""spec-013：/api/kb/ask 链路 trace + 生成埋点接入。

全部外部依赖（Ollama / Qdrant / 观测后端）mock，测试离线秒级完成，
禁止触发真实模型或向量库调用。
"""
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.app.main import app


def _sse_events(text):
    import json
    events = []
    for line in text.split("\n\n"):
        line = line.strip()
        if not line.startswith("data: "):
            continue
        events.append(json.loads(line[6:]))
    return events


def _fake_hit(file_name="paper.pdf", page=3, text="片段内容"):
    hit = MagicMock()
    hit.file_name = file_name
    hit.page = page
    hit.page_end = 0
    hit.chunk_index = 0
    hit.paper_id = "p-1"
    hit.score = 0.8
    hit.text = text
    return hit


class KbAskTraceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    # ---- 正常流程：埋点接入、trace 包裹、report 一次 ----
    @patch("backend.app.api.routes.start_trace")
    @patch("backend.app.api.routes.end_trace")
    @patch("backend.app.api.routes.record_ollama_generation")
    @patch("backend.app.api.routes.hybrid_search")
    @patch("backend.app.api.routes.get_available_models", return_value=["m1"])
    @patch("backend.app.services.ollama.create_chat_model")
    @patch("backend.app.graphs.chat.build_chat_graph")
    def test_normal_flow_reports_generation(
        self, mock_graph, _mock_model, _mock_models, mock_search,
        mock_report, mock_end_trace, mock_start_trace,
    ):
        fake_graph = MagicMock()
        fake_graph.stream.return_value = [
            {"type": "token", "content": "答"},
            {"type": "token", "content": "案"},
        ]
        mock_graph.return_value = fake_graph
        mock_search.return_value = [_fake_hit()]

        response = self.client.post(
            "/api/kb/ask",
            json={"question": "什么是RAG", "model": "m1", "top_k": 3, "chunker": "v1"},
        )
        self.assertEqual(response.status_code, 200)
        events = _sse_events(response.text)

        # SSE 序列与改动前一致：meta -> stage -> citations -> token... -> debug -> done
        self.assertEqual(events[0]["type"], "meta")
        self.assertEqual(events[1]["type"], "stage")
        self.assertEqual(events[2]["type"], "citations")
        tokens = [e for e in events if e["type"] == "token"]
        self.assertEqual([t["content"] for t in tokens], ["答", "案"])
        self.assertEqual(events[-2]["type"], "debug")
        self.assertEqual(events[-1]["type"], "done")

        # trace 包裹
        self.assertEqual(mock_start_trace.call_count, 1)
        self.assertEqual(mock_start_trace.call_args.args[0], "kb-ask")
        mock_start_trace.assert_called_once_with("kb-ask", tags=["kb"])
        self.assertEqual(mock_end_trace.call_count, 1)

        # 生成埋点一次，字段正确
        mock_report.assert_called_once()
        kwargs = mock_report.call_args.kwargs
        self.assertEqual(kwargs["model"], "m1")
        self.assertEqual(kwargs["name"], "kb.generation")
        self.assertEqual(kwargs["tags"], ["kb"])
        # prompt_messages 用的是 build_prompt 结果，而非原始问题
        self.assertEqual(kwargs["prompt_messages"][0]["role"], "user")
        prompt_content = kwargs["prompt_messages"][0]["content"]
        self.assertNotEqual(prompt_content, "什么是RAG")
        self.assertIn("RAG", prompt_content)
        self.assertEqual(kwargs["route"], "langchain")
        extra = kwargs["extra_metadata"]
        self.assertEqual(extra["top_k"], 3)
        self.assertEqual(extra["chunker"], "v1")
        self.assertEqual(extra["hit_count"], 1)
        self.assertEqual(extra["question_chars"], len("什么是RAG"))
        self.assertEqual(extra["prompt_chars"], len(prompt_content))

        # 发给模型的 state 用的是 build_prompt 结果
        streamed_state = fake_graph.stream.call_args.args[0]
        self.assertEqual(streamed_state, {"question": prompt_content})

    # ---- 异常流程：仍输出 error 事件，且 end_trace 仍被调用 ----
    @patch("backend.app.api.routes.start_trace")
    @patch("backend.app.api.routes.end_trace")
    @patch("backend.app.api.routes.record_ollama_generation")
    @patch("backend.app.api.routes.hybrid_search")
    @patch("backend.app.api.routes.get_available_models", return_value=["m1"])
    @patch("backend.app.services.ollama.create_chat_model")
    @patch("backend.app.graphs.chat.build_chat_graph")
    def test_generation_error_still_emits_error_and_ends_trace(
        self, mock_graph, _mock_model, _mock_models, mock_search,
        mock_report, mock_end_trace, mock_start_trace,
    ):
        fake_graph = MagicMock()
        fake_graph.stream.side_effect = RuntimeError("boom")
        mock_graph.return_value = fake_graph
        mock_search.return_value = [_fake_hit()]

        response = self.client.post(
            "/api/kb/ask",
            json={"question": "崩", "model": "m1"},
        )
        self.assertEqual(response.status_code, 200)
        events = _sse_events(response.text)
        errors = [e for e in events if e["type"] == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("生成失败", errors[0]["message"])
        # 生成阶段异常：不产生成功 generation，但必须留下一条失败记录，
        # 否则失败请求既进不了错误率统计，也丢失了诊断信息。
        mock_report.assert_called_once()
        kwargs = mock_report.call_args.kwargs
        self.assertIs(kwargs["success"], False)
        self.assertEqual(kwargs["error_type"], "RuntimeError")
        self.assertEqual(kwargs["name"], "kb.generation")
        # finally 必须复位 trace
        self.assertEqual(mock_end_trace.call_count, 1)
        self.assertEqual(mock_start_trace.call_count, 1)

    # ---- 空 hits 早退：输出提示 + done，不上报，但仍 end_trace ----
    @patch("backend.app.api.routes.start_trace")
    @patch("backend.app.api.routes.end_trace")
    @patch("backend.app.api.routes.record_ollama_generation")
    @patch("backend.app.api.routes.hybrid_search", return_value=[])
    @patch("backend.app.api.routes.get_available_models", return_value=["m1"])
    def test_empty_hits_early_return(
        self, _mock_models, mock_search, mock_report, mock_end_trace, mock_start_trace,
    ):
        response = self.client.post(
            "/api/kb/ask",
            json={"question": "没有命中", "model": "m1", "chunker": "v1"},
        )
        self.assertEqual(response.status_code, 200)
        events = _sse_events(response.text)
        tokens = [e for e in events if e["type"] == "token"]
        self.assertEqual(len(tokens), 1)
        self.assertIn("知识库中没有找到相关内容", tokens[0]["content"])
        self.assertEqual(events[-1]["type"], "done")
        # 没有生成，不上报
        mock_report.assert_not_called()
        # 但仍调用 trace 收尾
        self.assertEqual(mock_end_trace.call_count, 1)
        self.assertEqual(mock_start_trace.call_count, 1)

    @patch("backend.app.api.routes.start_trace", side_effect=RuntimeError("observability init"))
    @patch("backend.app.api.routes.end_trace", side_effect=RuntimeError("observability close"))
    @patch("backend.app.api.routes.hybrid_search", return_value=[])
    @patch("backend.app.api.routes.get_available_models", return_value=["m1"])
    def test_observability_errors_do_not_change_empty_result_sse(
        self, _mock_models, _mock_search, mock_end_trace, mock_start_trace,
    ):
        response = self.client.post("/api/kb/ask", json={"question": "无观测", "model": "m1"})
        self.assertEqual(response.status_code, 200)
        events = _sse_events(response.text)
        self.assertEqual([event["type"] for event in events], ["meta", "stage", "citations", "token", "done"])
        self.assertEqual(mock_start_trace.call_count, 1)
        self.assertEqual(mock_end_trace.call_count, 1)

    @patch("backend.app.observability.config.enabled", return_value=False)
    @patch("backend.app.api.routes.record_ollama_generation")
    @patch("backend.app.api.routes.hybrid_search", return_value=[_fake_hit()])
    @patch("backend.app.api.routes.get_available_models", return_value=["m1"])
    @patch("backend.app.services.ollama.create_chat_model")
    def test_langfuse_disabled_preserves_normal_sse(
        self, mock_model, _mock_models, mock_search, mock_report, mock_enabled,
    ):
        fake_graph = MagicMock()
        fake_graph.stream.return_value = [{"type": "token", "content": "答"}]
        mock_model.return_value = MagicMock()
        with patch("backend.app.graphs.chat.build_chat_graph", return_value=fake_graph):
            response = self.client.post("/api/kb/ask", json={"question": "关闭观测", "model": "m1"})
        self.assertEqual(response.status_code, 200)
        events = _sse_events(response.text)
        self.assertEqual(events[-2]["type"], "debug")
        self.assertEqual(events[-1]["type"], "done")
        self.assertTrue(mock_enabled.called)
        self.assertEqual(mock_search.call_count, 1)
        self.assertEqual(mock_report.call_count, 1)

    @patch("backend.app.api.routes.end_trace")
    @patch("backend.app.api.routes.record_ollama_generation")
    @patch("backend.app.api.routes.hybrid_search", side_effect=RuntimeError("qdrant down"))
    @patch("backend.app.api.routes.get_available_models", return_value=["m1"])
    def test_retrieval_error_still_emits_error_and_ends_trace(
        self, _mock_models, _mock_search, mock_report, mock_end_trace,
    ):
        response = self.client.post("/api/kb/ask", json={"question": "检索失败", "model": "m1"})
        self.assertEqual(response.status_code, 200)
        events = _sse_events(response.text)
        self.assertEqual([event["type"] for event in events], ["meta", "stage", "error"])
        self.assertIn("知识库检索失败", events[-1]["message"])
        mock_report.assert_not_called()
        self.assertEqual(mock_end_trace.call_count, 1)


if __name__ == "__main__":
    unittest.main()
