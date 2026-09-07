import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.domain.article import ArticleCandidate
from backend.app.main import app
from backend.app.services.download_paper_skill import SKILL_NAME


class AgentApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_run_emits_intent_events(self):
        from backend.app.domain.article import ArticleTask

        task = ArticleTask(
            task_id="task-chat",
            query="帮我处理实验数据",
            normalized_query="帮我处理实验数据",
            intent="chat",
            intent_confidence=0.9,
        )
        with patch("backend.app.api.routes_article.build_task", return_value=task):
            with patch("backend.app.api.routes_article.get_available_models", return_value=[]):
                response = self.client.post("/api/agent/run", json={"question": "帮我处理实验数据"})
        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "normalized"', response.text)
        self.assertIn('"intent": "chat"', response.text)

    def test_login_required_candidate_pauses_download(self):
        candidate = ArticleCandidate(
            candidate_id="candidate-1",
            title="A Paper",
            article_url="https://example.com/login",
            pdf_url="https://example.com/paper.pdf",
            source_name="Example",
            confidence=0.9,
            requires_login=True,
        )
        with patch("backend.app.api.routes_article.search_articles", return_value=[candidate]):
            search = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Paper"})
        self.assertEqual(search.status_code, 200)
        data = search.json()
        download = self.client.post("/api/agent/articles/download", json={"task_id": data["task_id"], "candidate_id": "candidate-1"})
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.json()["status"], "waiting_login")

    @patch("backend.app.api.routes_article.get_available_models", return_value=["deepseek-coder:33b"])
    @patch("backend.app.api.routes_article.skill_status")
    def test_download_paper_skill_status(self, mock_status, _mock_models):
        mock_status.return_value = {
            "skill_name": "download-paper",
            "available": True,
            "worker_model": "deepseek-coder:33b",
            "worker_model_available": True,
            "missing_files": [],
        }
        response = self.client.get("/api/agent/skills/download-paper")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["skill_name"], "download-paper")

    @patch("backend.app.api.routes_article.get_available_models", return_value=["deepseek-coder:33b"])
    @patch("backend.app.api.routes_article.skill_status")
    @patch("backend.app.api.routes_article.build_skill_plan")
    def test_plan_download_is_skill_led(self, mock_plan, mock_status, _mock_models):
        candidate = ArticleCandidate(
            candidate_id="candidate-public",
            title="A Public Paper",
            pdf_url="https://example.com/public.pdf",
            pdf_url_status="public_pdf",
            confidence=0.9,
        )
        mock_status.return_value = {"available": True, "worker_model": "deepseek-coder:33b"}
        mock_plan.return_value = {
            "skill_name": "download-paper",
            "orchestration": "skill_led",
            "download_method": "public_https",
            "requires_credentials": False,
        }
        with patch("backend.app.api.routes_article.search_articles", return_value=[candidate]):
            search = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Public Paper"})
        response = self.client.post(
            "/api/agent/articles/plan-download",
            json={"task_id": search.json()["task_id"], "candidate_id": "candidate-public"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["orchestration"], "skill_led")
        self.assertEqual(body["download_method"], "public_https")
        mock_plan.assert_called_once_with(candidate, "deepseek-coder:33b")

    @patch("backend.app.api.routes_article.get_available_models", return_value=["deepseek-coder:33b"])
    @patch("backend.app.api.routes_article.skill_status")
    @patch("backend.app.api.routes_article.download_under_skill")
    def test_download_with_use_skill_records_skill_name(self, mock_skill_exec, mock_status, _mock_models):
        mock_status.return_value = {"available": True, "worker_model": "deepseek-coder:33b"}
        mock_skill_exec.return_value = iter(
            [{"type": "result", "file_path": "/tmp/x.pdf", "file_size": 10, "checksum": "abc", "skill_name": SKILL_NAME}]
        )
        candidate = ArticleCandidate(
            candidate_id="candidate-public",
            title="A Public Paper",
            pdf_url="https://example.com/public.pdf",
            pdf_url_status="public_pdf",
            confidence=0.9,
        )
        with patch("backend.app.api.routes_article.search_articles", return_value=[candidate]):
            search = self.client.post("/api/agent/articles/search", json={"query": "下载论文 A Public Paper"})
        task_id = search.json()["task_id"]
        response = self.client.post(
            "/api/agent/articles/download",
            json={"task_id": task_id, "candidate_id": "candidate-public", "use_skill": True},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["skill_name"], SKILL_NAME)
        mock_skill_exec.assert_called_once()

    def test_search_filters_low_confidence_and_caps_at_three(self):
        from backend.app.domain.article import ArticleTask

        high = [
            ArticleCandidate(candidate_id=f"hi-{i}", title=f"Hi {i}", confidence=0.9 - i * 0.05)
            for i in range(3)
        ]
        low = [
            ArticleCandidate(candidate_id=f"lo-{i}", title=f"Lo {i}", confidence=0.4)
            for i in range(3)
        ]
        mixed = high + low + [ArticleCandidate(candidate_id="mid", title="Mid", confidence=0.6)]
        with patch("backend.app.api.routes_article.build_task") as mock_build:
            mock_build.return_value = ArticleTask(
                task_id="task-mixed",
                query="下载论文 Mixed",
                normalized_query="下载论文 Mixed",
                intent="download_paper",
                intent_confidence=0.9,
            )
            with patch("backend.app.api.routes_article.search_articles", return_value=mixed):
                response = self.client.post("/api/agent/articles/search", json={"query": "下载论文 Mixed"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        confidences = [item["confidence"] for item in data["candidates"]]
        self.assertLessEqual(len(confidences), 3)
        for confidence in confidences:
            self.assertGreater(confidence, 0.5)
        self.assertEqual(confidences, sorted(confidences, reverse=True))

    def test_run_intent_event_carries_skill_for_download_paper(self):
        from backend.app.domain.article import ArticleTask

        task = ArticleTask(
            task_id="task-x",
            query="下载论文 X",
            normalized_query="下载论文 X",
            intent="download_paper",
            intent_confidence=0.92,
        )
        candidate = ArticleCandidate(
            candidate_id="candidate-x",
            title="X Paper",
            pdf_url="https://example.com/x.pdf",
            pdf_url_status="public_pdf",
            confidence=0.92,
        )
        with patch("backend.app.api.routes_article.build_task", return_value=task):
            with patch("backend.app.api.routes_article.search_articles", return_value=[candidate]):
                response = self.client.post("/api/agent/run", json={"question": "下载论文 X"})
        self.assertEqual(response.status_code, 200)
        intent_event = None
        for line in response.text.split("\n\n"):
            line = line.strip()
            if not line.startswith("data: "):
                continue
            event = __import__("json").loads(line[6:])
            if event.get("type") == "intent":
                intent_event = event
                break
        self.assertIsNotNone(intent_event)
        self.assertEqual(intent_event["intent"], "download_paper")
        self.assertEqual(intent_event["skill"], SKILL_NAME)


if __name__ == "__main__":
    unittest.main()
