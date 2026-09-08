"""补齐 backend API 路由与端点的测试覆盖（spec-010）。

目标：把 `backend` 覆盖率从 69% 提升到 ≥80%。
原则（评审约束）：
- 每个用例都有真实断言，禁止"调用即结束"。
- 外部依赖（Ollama、网络、子进程）全部 mock，测试离线可重复运行。
- 不修改任何业务代码。
"""
import unittest
from unittest.mock import MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from backend.app.api import common
from backend.app.article_assistant.domain.article import ArticleCandidate
from backend.app.main import app


def _candidate(candidate_id="c-1", **kwargs):
    defaults = dict(
        candidate_id=candidate_id,
        title="A Paper",
        article_url="https://example.com/paper",
        pdf_url="https://example.com/paper.pdf",
        source_name="Example",
        confidence=0.9,
    )
    defaults.update(kwargs)
    return ArticleCandidate(**defaults)


def _sse_events(text):
    """解析 SSE 文本，返回事件 dict 列表。"""
    import json

    events = []
    for line in text.split("\n\n"):
        line = line.strip()
        if not line.startswith("data: "):
            continue
        events.append(json.loads(line[6:]))
    return events


class HealthAndSettingsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self._orig_settings = common.article_settings

    def tearDown(self):
        common.article_settings = self._orig_settings

    @patch("backend.app.api.routes_system.get_available_models", return_value=["m1", "m2"])
    def test_health_returns_model_list(self, _mock_models):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["models"], ["m1", "m2"])
        self.assertIn("model", body)

    @patch("backend.app.api.routes_system.get_available_models", side_effect=httpx.HTTPError("ollama down"))
    def test_health_degrades_to_empty_models_on_ollama_error(self, _mock_models):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["models"], [])

    def test_get_settings_exposes_source_counts(self):
        response = self.client.get("/api/agent/settings")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("article_metadata_sources", body)
        self.assertEqual(body["search_sources"], len(self._orig_settings.article_search_urls))
        self.assertEqual(body["download_sources"], len(self._orig_settings.article_download_urls))

    @patch("backend.app.api.routes_article.save_article_settings")
    def test_put_settings_updates_in_memory_and_persists(self, mock_save):
        payload = self._orig_settings.model_dump()
        payload["article_max_candidates_per_source"] = 7
        response = self.client.put("/api/agent/settings", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["article_max_candidates_per_source"], 7)
        self.assertEqual(common.article_settings.article_max_candidates_per_source, 7)
        mock_save.assert_called_once()


class TaskLookupTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_get_task_returns_404_when_missing(self):
        response = self.client.get("/api/agent/tasks/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "任务不存在")

    def test_get_task_returns_task_with_candidates(self):
        candidate = _candidate(confidence=0.95)
        with patch("backend.app.api.routes_article.search_articles", return_value=[candidate]):
            search = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Paper"})
        task_id = search.json()["task_id"]
        response = self.client.get(f"/api/agent/tasks/{task_id}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["task_id"], task_id)
        self.assertEqual(len(body["candidates"]), 1)
        self.assertEqual(body["candidates"][0]["candidate_id"], "c-1")


class ProbeEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_probe_returns_404_when_task_or_candidate_missing(self):
        response = self.client.post("/api/agent/articles/probe", json={"task_id": "x", "candidate_id": "y"})
        self.assertEqual(response.status_code, 404)

    def test_probe_marks_public_pdf(self):
        candidate = _candidate(pdf_url=None)
        with patch("backend.app.api.routes_article.search_articles", return_value=[candidate]):
            search = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Paper"})
        task_id = search.json()["task_id"]
        with patch("backend.app.api.routes_article.probe_pdf_url", return_value=("public_pdf", "https://example.com/found.pdf")):
            response = self.client.post("/api/agent/articles/probe", json={"task_id": task_id, "candidate_id": "c-1"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["pdf_url_status"], "public_pdf")
        self.assertEqual(body["pdf_url"], "https://example.com/found.pdf")
        self.assertEqual(body["download_outcome"], "downloaded")

    def test_probe_marks_login_required(self):
        candidate = _candidate(pdf_url=None, requires_login=False)
        with patch("backend.app.api.routes_article.search_articles", return_value=[candidate]):
            search = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Paper"})
        task_id = search.json()["task_id"]
        with patch("backend.app.api.routes_article.probe_pdf_url", return_value=("login_required", None)):
            response = self.client.post("/api/agent/articles/probe", json={"task_id": task_id, "candidate_id": "c-1"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["pdf_url_status"], "login_required")
        self.assertTrue(body["requires_login"])
        self.assertEqual(body["download_outcome"], "login_required")


class ChatEndpointTests(unittest.TestCase):
    """覆盖 /api/chat 端点（此前完全未覆盖）。"""

    def setUp(self):
        self.client = TestClient(app)

    def test_chat_rejects_empty_question(self):
        response = self.client.post("/api/chat", json={"question": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "问题不能为空")

    def test_chat_rejects_too_long_question(self):
        response = self.client.post("/api/chat", json={"question": "x" * 2001, "mode": "normal"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("最多支持", response.json()["detail"])

    def test_chat_allows_longer_question_in_developer_mode(self):
        """developer 模式阈值 20000，2500 字应通过长度校验。"""
        with patch("backend.app.api.routes_chat.get_available_models", return_value=["m1"]):
            response = self.client.post(
                "/api/chat", json={"question": "x" * 2500, "mode": "developer", "model": "m1"}
            )
        self.assertNotEqual(response.status_code, 400)

    @patch("backend.app.api.routes_chat.get_available_models", side_effect=httpx.HTTPError("down"))
    def test_chat_returns_502_when_ollama_unreachable(self, _mock_models):
        response = self.client.post("/api/chat", json={"question": "你好"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "无法连接 Ollama 服务")

    @patch("backend.app.api.routes_chat.get_available_models", return_value=["installed-model"])
    def test_chat_rejects_unknown_model(self, _mock_models):
        response = self.client.post("/api/chat", json={"question": "你好", "model": "ghost-model"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("不存在", response.json()["detail"])

    @patch("backend.app.api.routes_chat.get_available_models", return_value=["m1"])
    @patch("backend.app.platform.ollama.create_chat_model")
    @patch("backend.app.chat.application.chat_graph.build_chat_graph")
    def test_chat_streams_tokens_and_done(self, mock_graph, mock_model, _mock_models):
        fake_graph = MagicMock()
        fake_graph.stream.return_value = [
            {"type": "token", "content": "你"},
            {"type": "token", "content": "好"},
        ]
        mock_graph.return_value = fake_graph
        response = self.client.post("/api/chat", json={"question": "你好", "model": "m1"})
        self.assertEqual(response.status_code, 200)
        events = _sse_events(response.text)
        self.assertEqual(events[0]["type"], "meta")
        self.assertEqual(events[0]["model"], "m1")
        tokens = [e for e in events if e["type"] == "token"]
        self.assertEqual([t["content"] for t in tokens], ["你", "好"])
        self.assertEqual(events[-1]["type"], "done")
        mock_model.assert_called_once_with("m1")

    @patch("backend.app.api.routes_chat.get_available_models", return_value=["m1"])
    @patch("backend.app.platform.ollama.create_chat_model")
    @patch("backend.app.chat.application.chat_graph.build_chat_graph")
    def test_chat_emits_debug_event_in_developer_mode(self, mock_graph, _mock_model, _mock_models):
        fake_graph = MagicMock()
        fake_graph.stream.return_value = [{"type": "token", "content": "ok"}]
        mock_graph.return_value = fake_graph
        response = self.client.post("/api/chat", json={"question": "你好", "model": "m1", "mode": "developer"})
        events = _sse_events(response.text)
        debug = [e for e in events if e["type"] == "debug"]
        self.assertEqual(len(debug), 1)
        self.assertEqual(debug[0]["debug"]["graph_node"], "ask_model")
        self.assertEqual(debug[0]["debug"]["input_length"], 2)

    @patch("backend.app.api.routes_chat.get_available_models", return_value=["m1"])
    @patch("backend.app.platform.ollama.create_chat_model")
    @patch("backend.app.chat.application.chat_graph.build_chat_graph")
    def test_chat_stream_error_is_reported(self, mock_graph, _mock_model, _mock_models):
        fake_graph = MagicMock()
        fake_graph.stream.side_effect = RuntimeError("boom")
        mock_graph.return_value = fake_graph
        response = self.client.post("/api/chat", json={"question": "你好", "model": "m1", "mode": "developer"})
        events = _sse_events(response.text)
        error = [e for e in events if e["type"] == "error"]
        self.assertEqual(len(error), 1)
        self.assertEqual(error[0]["detail"], "boom")


class SearchEndpointBranchTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_search_rejects_empty_query(self):
        response = self.client.post("/api/agent/articles/search", json={"query": ""})
        self.assertEqual(response.status_code, 400)
        self.assertIn("搜索关键词", response.json()["detail"])

    def test_search_rejects_non_download_intent(self):
        response = self.client.post("/api/agent/articles/search", json={"query": "帮我写个故事"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("不是论文下载意图", response.json()["detail"])

    @patch("backend.app.api.routes_article.search_articles", side_effect=httpx.HTTPError("upstream down"))
    def test_search_returns_502_on_upstream_error(self, _mock_search):
        response = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Paper"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "文章检索来源不可用")

    @patch("backend.app.api.routes_article.search_articles", return_value=[_candidate(confidence=0.3)])
    def test_search_fails_when_all_candidates_below_threshold(self, _mock_search):
        response = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Paper"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "failed")
        self.assertEqual(body["candidates"], [])
        self.assertIn("50%", body["error"])


class DownloadEndpointBranchTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_download_returns_404_when_task_missing(self):
        response = self.client.post("/api/agent/articles/download", json={"task_id": "x", "candidate_id": "y"})
        self.assertEqual(response.status_code, 404)

    def test_download_probes_pdf_and_reports_login_required(self):
        candidate = _candidate(pdf_url=None)
        with patch("backend.app.api.routes_article.search_articles", return_value=[candidate]):
            search = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Paper"})
        task_id = search.json()["task_id"]
        with patch("backend.app.api.routes_article.probe_pdf_url", return_value=("login_required", None)):
            response = self.client.post("/api/agent/articles/download", json={"task_id": task_id, "candidate_id": "c-1"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "waiting_login")
        self.assertEqual(body["download_outcome"], "login_required")

    def test_download_reports_404_for_non_public_pdf(self):
        candidate = _candidate(pdf_url=None)
        with patch("backend.app.api.routes_article.search_articles", return_value=[candidate]):
            search = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Paper"})
        task_id = search.json()["task_id"]
        with patch("backend.app.api.routes_article.probe_pdf_url", return_value=("not_found", None)):
            response = self.client.post("/api/agent/articles/download", json={"task_id": task_id, "candidate_id": "c-1"})
        self.assertEqual(response.status_code, 404)
        detail = response.json()["detail"]
        self.assertEqual(detail["download_outcome"], "not_found")
        self.assertIn("没有找到可公开访问的 PDF", detail["user_message"])

    @patch("backend.app.api.routes_article.download_article", side_effect=PermissionError("need login"))
    def test_download_permission_error_becomes_waiting_login(self, _mock_download):
        candidate = _candidate()
        with patch("backend.app.api.routes_article.search_articles", return_value=[candidate]):
            search = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Paper"})
        task_id = search.json()["task_id"]
        response = self.client.post(
            "/api/agent/articles/download",
            json={"task_id": task_id, "candidate_id": "c-1", "use_skill": False},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "waiting_login")
        self.assertEqual(body["download_outcome"], "login_required")
        self.assertEqual(body["message"], "need login")

    @patch("backend.app.api.routes_article.download_article", side_effect=httpx.HTTPError("network down"))
    def test_download_returns_502_on_network_error(self, _mock_download):
        candidate = _candidate()
        with patch("backend.app.api.routes_article.search_articles", return_value=[candidate]):
            search = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Paper"})
        task_id = search.json()["task_id"]
        response = self.client.post(
            "/api/agent/articles/download",
            json={"task_id": task_id, "candidate_id": "c-1", "use_skill": False},
        )
        self.assertEqual(response.status_code, 502)

    @patch("backend.app.api.routes_article.download_article")
    def test_download_reports_error_result_as_502(self, mock_download):
        mock_download.return_value = iter(
            [{"type": "error", "download_outcome": "rate_limited", "user_message": "文章来源当前限流，请稍后重试。"}]
        )
        candidate = _candidate()
        with patch("backend.app.api.routes_article.search_articles", return_value=[candidate]):
            search = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Paper"})
        task_id = search.json()["task_id"]
        response = self.client.post(
            "/api/agent/articles/download",
            json={"task_id": task_id, "candidate_id": "c-1", "use_skill": False},
        )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["download_outcome"], "rate_limited")


class LoginCompletedTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_login_completed_rejects_task_not_waiting_login(self):
        candidate = _candidate()
        with patch("backend.app.api.routes_article.search_articles", return_value=[candidate]):
            search = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Paper"})
        task_id = search.json()["task_id"]
        response = self.client.post(
            f"/api/agent/tasks/{task_id}/human-actions/login-completed",
            json={"candidate_id": "c-1"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "任务当前不在等待登录状态")

    def test_login_completed_rejects_unknown_candidate(self):
        candidate = _candidate(pdf_url=None, requires_login=True)
        with patch("backend.app.api.routes_article.search_articles", return_value=[candidate]):
            search = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Paper"})
        task_id = search.json()["task_id"]
        with patch("backend.app.api.routes_article.probe_pdf_url", return_value=("login_required", None)):
            self.client.post("/api/agent/articles/download", json={"task_id": task_id, "candidate_id": "c-1"})
        response = self.client.post(
            f"/api/agent/tasks/{task_id}/human-actions/login-completed",
            json={"candidate_id": "ghost"},
        )
        self.assertEqual(response.status_code, 404)

    @patch("backend.app.api.routes_article.skill_status")
    @patch("backend.app.api.routes_article.get_available_models", return_value=[])
    @patch("backend.app.api.routes_article.download_article")
    def test_login_completed_resumes_download(self, mock_download, _mock_models, mock_status):
        # login_completed 内部会再调 download_article_endpoint（不带 use_skill），
        # 因此必须 mock skill_status / get_available_models，避免真实 Ollama 调用。
        mock_status.return_value = {"available": False}
        mock_download.return_value = iter(
            [{"type": "result", "file_path": "/tmp/x.pdf", "file_size": 1, "checksum": "abc"}]
        )
        candidate = _candidate(pdf_url="https://example.com/paper.pdf", requires_login=True)
        with patch("backend.app.api.routes_article.search_articles", return_value=[candidate]):
            search = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Paper"})
        task_id = search.json()["task_id"]
        paused = self.client.post(
            "/api/agent/articles/download",
            json={"task_id": task_id, "candidate_id": "c-1", "use_skill": False},
        )
        self.assertEqual(paused.json()["status"], "waiting_login")
        response = self.client.post(
            f"/api/agent/tasks/{task_id}/human-actions/login-completed",
            json={"candidate_id": "c-1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")
        mock_download.assert_called_once()


class RunAgentBranchTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_run_rejects_empty_question(self):
        response = self.client.post("/api/agent/run", json={"question": "  "})
        self.assertEqual(response.status_code, 400)
        self.assertIn("500 个字符", response.json()["detail"])

    def test_run_rejects_too_long_question(self):
        response = self.client.post("/api/agent/run", json={"question": "x" * 501})
        self.assertEqual(response.status_code, 400)

    @patch("backend.app.api.routes_article.search_articles", side_effect=httpx.HTTPError("upstream down"))
    def test_run_reports_search_failure(self, _mock_search):
        response = self.client.post("/api/agent/run", json={"question": "下载论文 A Paper"})
        self.assertEqual(response.status_code, 200)
        events = _sse_events(response.text)
        error = [e for e in events if e["type"] == "error"]
        self.assertEqual(error[0]["message"], "文章检索来源不可用")

    @patch("backend.app.api.routes_article.search_articles", return_value=[])
    def test_run_reports_no_candidates(self, _mock_search):
        response = self.client.post("/api/agent/run", json={"question": "下载论文 A Paper"})
        events = _sse_events(response.text)
        error = [e for e in events if e["type"] == "error"]
        self.assertIn("没有找到候选文章", error[0]["message"])

    @patch("backend.app.api.routes_article.search_articles", return_value=[_candidate(confidence=0.2)])
    def test_run_reports_all_candidates_below_threshold(self, _mock_search):
        response = self.client.post("/api/agent/run", json={"question": "下载论文 A Paper"})
        events = _sse_events(response.text)
        error = [e for e in events if e["type"] == "error"]
        self.assertIn("50%", error[0]["message"])
        self.assertIn("done", [e["type"] for e in events])

    @patch("backend.app.api.routes_article.get_available_models", return_value=["m1"])
    @patch("backend.app.platform.ollama.create_chat_model")
    @patch("backend.app.chat.application.chat_graph.build_chat_graph")
    def test_run_chat_branch_streams_answer(self, mock_graph, _mock_model, _mock_models):
        fake_graph = MagicMock()
        fake_graph.stream.return_value = [{"type": "token", "content": "hi"}]
        mock_graph.return_value = fake_graph
        response = self.client.post("/api/agent/run", json={"question": "帮我处理数据", "model": "m1"})
        events = _sse_events(response.text)
        self.assertIn("token", [e["type"] for e in events])
        self.assertIn("done", [e["type"] for e in events])

    @patch("backend.app.api.routes_article.get_available_models", return_value=[])
    def test_run_chat_branch_reports_missing_model(self, _mock_models):
        response = self.client.post("/api/agent/run", json={"question": "帮我处理数据", "model": "m1"})
        events = _sse_events(response.text)
        error = [e for e in events if e["type"] == "error"]
        self.assertIn("不存在", error[0]["message"])

    @patch("backend.app.api.routes_article.get_available_models", return_value=["m1"])
    @patch("backend.app.platform.ollama.create_chat_model")
    @patch("backend.app.chat.application.chat_graph.build_chat_graph")
    def test_run_chat_branch_reports_exception(self, mock_graph, _mock_model, _mock_models):
        fake_graph = MagicMock()
        fake_graph.stream.side_effect = RuntimeError("boom")
        mock_graph.return_value = fake_graph
        response = self.client.post(
            "/api/agent/run", json={"question": "帮我处理数据", "model": "m1", "mode": "developer"}
        )
        events = _sse_events(response.text)
        error = [e for e in events if e["type"] == "error"]
        self.assertEqual(error[0]["message"], "boom")


class ChatGraphTests(unittest.TestCase):
    """覆盖 graphs/chat.py 的 ask_model 分支。"""

    def test_build_chat_graph_streams_content_chunks(self):
        from backend.app.chat.application.chat_graph import build_chat_graph

        class _Chunk:
            def __init__(self, content):
                self.content = content

        fake_model = MagicMock()
        fake_model.stream.return_value = [_Chunk("你"), _Chunk(""), _Chunk("好")]
        graph = build_chat_graph(fake_model)
        result = graph.invoke({"question": "你好"})
        self.assertEqual(result["answer"], "你好")

    def test_build_chat_graph_handles_non_string_content(self):
        from backend.app.chat.application.chat_graph import build_chat_graph

        class _Chunk:
            def __init__(self, content):
                self.content = content

        fake_model = MagicMock()
        fake_model.stream.return_value = [_Chunk(["list", "content"])]
        graph = build_chat_graph(fake_model)
        result = graph.invoke({"question": "你好"})
        self.assertEqual(result["answer"], "['list', 'content']")


class EntryPointTests(unittest.TestCase):
    def test_backend_main_entry_module_is_importable(self):
        import backend.main as entry

        self.assertTrue(hasattr(entry, "app") or hasattr(entry, "main"))


if __name__ == "__main__":
    unittest.main()
