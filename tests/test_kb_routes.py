"""spec-011 知识库路由测试（TestClient + mock，离线可重复）。"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.kb.retrieve import Hit

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF"


def sse_events(response):
    events = []
    for block in response.text.split("\n\n"):
        block = block.strip()
        if not block.startswith("data: "):
            continue
        events.append(json.loads(block[6:]))
    return events


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_rejects_non_pdf_extension(self):
        response = self.client.post(
            "/api/kb/upload", files={"file": ("note.txt", b"hello", "text/plain")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("只支持上传 PDF", response.json()["detail"])

    def test_rejects_pdf_name_without_pdf_content(self):
        response = self.client.post(
            "/api/kb/upload", files={"file": ("fake.pdf", b"not a pdf", "application/pdf")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("不是合法的 PDF", response.json()["detail"])

    def test_rejects_empty_file(self):
        response = self.client.post(
            "/api/kb/upload", files={"file": ("empty.pdf", b"", "application/pdf")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("为空", response.json()["detail"])

    def test_rejects_oversized_file(self):
        with patch("backend.app.api.routes.KB_MAX_UPLOAD_MB", 0):
            response = self.client.post(
                "/api/kb/upload", files={"file": ("big.pdf", PDF_BYTES, "application/pdf")}
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("上限", response.json()["detail"])

    def test_upload_stores_file_and_indexes(self):
        with TemporaryDirectory() as tmp:
            record_payload = {
                "paper_id": "paper-1",
                "file_name": "paper.pdf",
                "status": "indexed",
                "page_count": 3,
                "chunk_count": 12,
                "uploaded_at": "2026-08-30T10:00:00",
                "error": None,
            }
            with patch("backend.app.api.routes.new_record") as mock_new:
                mock_new.return_value = Mock(paper_id="paper-1", file_name="paper.pdf")
                with patch("backend.app.api.routes.save_upload", return_value=("paper-1", Path(tmp) / "paper-1.pdf")) as mock_save:
                    with patch("backend.app.api.routes.upsert_paper") as mock_upsert:
                        with patch("backend.app.api.routes.index_paper", return_value=record_payload) as mock_index:
                            response = self.client.post(
                                "/api/kb/upload", files={"file": ("paper.pdf", PDF_BYTES, "application/pdf")}
                            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "indexed")
        self.assertEqual(body["chunk_count"], 12)
        mock_upsert.assert_called_once()
        self.assertEqual(mock_save.call_args.kwargs["paper_id"], "paper-1")
        mock_index.assert_called_once()


class PaperListTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_returns_empty_list(self):
        with patch("backend.app.api.routes.load_papers", return_value=[]):
            response = self.client.get("/api/kb/papers")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"papers": []})

    def test_returns_stored_papers(self):
        papers = [{"paper_id": "p1", "file_name": "a.pdf", "status": "indexed"}]
        with patch("backend.app.api.routes.load_papers", return_value=papers):
            response = self.client.get("/api/kb/papers")
        self.assertEqual(response.json()["papers"][0]["file_name"], "a.pdf")


class DeletePaperTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_missing_paper_returns_404(self):
        with patch("backend.app.api.routes.remove_paper", return_value=False):
            response = self.client.delete("/api/kb/papers/unknown")
        self.assertEqual(response.status_code, 404)
        self.assertIn("论文不存在", response.json()["detail"])

    def test_delete_removes_metadata_and_vectors(self):
        with patch("backend.app.api.routes.remove_paper", return_value=True):
            with patch("backend.app.api.routes.delete_paper") as mock_delete:
                response = self.client.delete("/api/kb/papers/p1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": True, "vectors_removed": True})
        mock_delete.assert_called_once_with("p1")

    def test_vector_failure_is_reported(self):
        with patch("backend.app.api.routes.remove_paper", return_value=True):
            with patch("backend.app.api.routes.delete_paper", side_effect=RuntimeError("qdrant down")):
                response = self.client.delete("/api/kb/papers/p1")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["vectors_removed"])


class AskTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.hits = [Hit("p1", "paper.pdf", 4, 0, "混合检索提升召回", 0.9)]

    def test_rejects_empty_question(self):
        response = self.client.post("/api/kb/ask", json={"question": "   ", "model": "qwen3.5:9b"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("问题不能为空", response.json()["detail"])

    def test_rejects_overlong_question(self):
        response = self.client.post("/api/kb/ask", json={"question": "问" * 2001, "model": "qwen3.5:9b"})
        self.assertEqual(response.status_code, 400)

    def test_requires_ollama(self):
        with patch("backend.app.api.routes.get_available_models", side_effect=httpx.HTTPError("down")):
            response = self.client.post("/api/kb/ask", json={"question": "核心贡献？", "model": "qwen3.5:9b"})
        self.assertEqual(response.status_code, 502)

    def test_rejects_unknown_model(self):
        with patch("backend.app.api.routes.get_available_models", return_value=["qwen3.5:9b"]):
            response = self.client.post("/api/kb/ask", json={"question": "核心贡献？", "model": "ghost"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("不存在", response.json()["detail"])

    def test_streams_tokens_and_citations(self):
        chat = Mock()
        chat.stream.return_value = [Mock(content="混合检索"), Mock(content="效果更好")]
        with patch("backend.app.api.routes.get_available_models", return_value=["qwen3.5:9b"]):
            with patch("backend.app.api.routes.hybrid_search", return_value=self.hits):
                with patch("backend.app.api.routes.create_chat_model", return_value=chat):
                    response = self.client.post(
                        "/api/kb/ask", json={"question": "核心贡献？", "model": "qwen3.5:9b"}
                    )
        self.assertEqual(response.status_code, 200)
        events = sse_events(response)
        tokens = [event["content"] for event in events if event["type"] == "token"]
        self.assertEqual("".join(tokens), "混合检索效果更好")
        citations = [event["citations"] for event in events if event["type"] == "citations"]
        self.assertEqual(citations[0][0]["file_name"], "paper.pdf")
        self.assertEqual(citations[0][0]["page"], 4)
        self.assertIn("done", [event["type"] for event in events])

    def test_reports_retrieval_failure(self):
        with patch("backend.app.api.routes.get_available_models", return_value=["qwen3.5:9b"]):
            with patch("backend.app.api.routes.hybrid_search", side_effect=RuntimeError("qdrant down")):
                response = self.client.post(
                    "/api/kb/ask", json={"question": "核心贡献？", "model": "qwen3.5:9b"}
                )
        events = sse_events(response)
        error = next(event for event in events if event["type"] == "error")
        self.assertIn("检索失败", error["message"])

    def test_empty_knowledge_base_is_friendly(self):
        with patch("backend.app.api.routes.get_available_models", return_value=["qwen3.5:9b"]):
            with patch("backend.app.api.routes.hybrid_search", return_value=[]):
                response = self.client.post(
                    "/api/kb/ask", json={"question": "核心贡献？", "model": "qwen3.5:9b"}
                )
        events = sse_events(response)
        tokens = [event["content"] for event in events if event["type"] == "token"]
        self.assertIn("没有找到相关内容", "".join(tokens))


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_reports_component_status(self):
        client = Mock()
        with patch("backend.app.api.routes.get_client", return_value=client):
            with patch("backend.app.api.routes.ensure_collection") as mock_collection:
                with patch("backend.app.api.routes.count_points", return_value=42):
                    with patch("backend.app.api.routes.embed_texts", return_value=[[0.1]]):
                        with patch("backend.app.api.routes.load_papers", return_value=[{"paper_id": "p1"}]):
                            response = self.client.get("/api/kb/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["qdrant"])
        self.assertTrue(body["embedding"])
        self.assertEqual(body["chunks"], 42)
        self.assertEqual(body["papers"], 1)
        self.assertIn("reranker", body)
        mock_collection.assert_called_once_with(client)

    def test_degrades_when_components_down(self):
        with patch("backend.app.api.routes.get_client", side_effect=RuntimeError("no qdrant")):
            with patch("backend.app.api.routes.embed_texts", side_effect=RuntimeError("no ollama")):
                with patch("backend.app.api.routes.load_papers", return_value=[]):
                    response = self.client.get("/api/kb/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["qdrant"])
        self.assertFalse(body["embedding"])


if __name__ == "__main__":
    unittest.main()
