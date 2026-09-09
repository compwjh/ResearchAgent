"""spec-011 知识库路由测试（TestClient + mock，离线可重复）。"""
# Legacy test groups intentionally keep nested patch scopes for readability.
# ruff: noqa: SIM117

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient

from backend.app.knowledge_base.application import KnowledgeDocumentMigrationError
from backend.app.knowledge_base.infrastructure.retrieve import Hit
from backend.app.main import app

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
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.json()["error_code"], "UNSUPPORTED_MEDIA_TYPE")

    def test_rejects_pdf_name_without_pdf_content(self):
        response = self.client.post(
            "/api/kb/upload", files={"file": ("fake.pdf", b"not a pdf", "application/pdf")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_code"], "INVALID_PDF")

    def test_rejects_empty_file(self):
        response = self.client.post(
            "/api/kb/upload", files={"file": ("empty.pdf", b"", "application/pdf")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_code"], "INVALID_PDF")

    def test_rejects_oversized_file(self):
        with patch("backend.app.api.routes_kb.KB_MAX_UPLOAD_MB", 0):
            response = self.client.post(
                "/api/kb/upload", files={"file": ("big.pdf", PDF_BYTES, "application/pdf")}
            )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error_code"], "PAYLOAD_TOO_LARGE")

    def test_upload_stores_file_and_indexes(self):
        record = {
            "document_id": "paper-1",
            "media_type": "application/pdf",
            "file_name": "paper.pdf",
            "source_sha256": "a" * 64,
            "status": "pending",
            "chunkers": {"v1": {"status": "pending"}, "v2": {"status": "pending"}},
        }
        with patch("backend.app.api.routes_kb.create_uploaded_document", return_value={"document": record, "task_id": None}) as create:
            response = self.client.post(
                "/api/kb/upload", files={"file": ("paper.pdf", PDF_BYTES, "application/pdf")}
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["document_id"], "paper-1")
        create.assert_called_once()


class PaperListTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_returns_empty_list(self):
        with patch("backend.app.api.routes_kb.load_papers", return_value=[]):
            response = self.client.get("/api/kb/papers")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"papers": []})

    def test_returns_stored_papers(self):
        papers = [{"paper_id": "p1", "file_name": "a.pdf", "status": "indexed"}]
        with patch("backend.app.api.routes_kb.load_papers", return_value=papers):
            response = self.client.get("/api/kb/papers")
        self.assertEqual(response.json()["papers"][0]["file_name"], "a.pdf")


class DeletePaperTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_missing_paper_returns_404(self):
        with patch("backend.app.api.routes_kb.delete_document", return_value=None):
            response = self.client.delete("/api/kb/papers/unknown")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error_code"], "DOCUMENT_NOT_FOUND")

    def test_delete_removes_metadata_and_vectors(self):
        result = {"document_id": "p1", "status": "completed", "deleted": {"source": True, "metadata": True, "manifests": True, "vectors": True}}
        with patch("backend.app.api.routes_kb.delete_document", return_value=result):
            response = self.client.delete("/api/kb/papers/p1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), result)

    def test_vector_failure_is_reported(self):
        result = {"document_id": "p1", "status": "DELETE_PENDING", "error_code": "DELETE_PENDING", "tombstoned": True}
        with patch("backend.app.api.routes_kb.delete_document", return_value=result):
            response = self.client.delete("/api/kb/papers/p1")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error_code"], "DELETE_PENDING")
        self.assertEqual(response.headers["retry-after"], "10")
        self.assertEqual(response.headers["location"], "/api/kb/documents/p1")
        self.assertEqual(response.json()["details"]["retry_after_seconds"], 10)


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
        with patch("backend.app.api.routes_kb.get_available_models", side_effect=httpx.HTTPError("down")):
            response = self.client.post("/api/kb/ask", json={"question": "核心贡献？", "model": "qwen3.5:9b"})
        self.assertEqual(response.status_code, 502)

    def test_rejects_unknown_model(self):
        with patch("backend.app.api.routes_kb.get_available_models", return_value=["qwen3.5:9b"]):
            response = self.client.post("/api/kb/ask", json={"question": "核心贡献？", "model": "ghost"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("不存在", response.json()["detail"])

    def test_streams_tokens_and_citations(self):
        chat = Mock()
        chat.stream.return_value = [Mock(content="混合检索"), Mock(content="效果更好")]
        with patch("backend.app.api.routes_kb.get_available_models", return_value=["qwen3.5:9b"]):
            with patch("backend.app.api.routes_kb.hybrid_search", return_value=self.hits):
                with patch("backend.app.platform.ollama.create_chat_model", return_value=chat) as mock_create:
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
        mock_create.assert_called_once_with("qwen3.5:9b", reasoning=False)

    def test_reports_retrieval_failure(self):
        with patch("backend.app.api.routes_kb.get_available_models", return_value=["qwen3.5:9b"]):
            with patch("backend.app.api.routes_kb.hybrid_search", side_effect=RuntimeError("qdrant down")):
                response = self.client.post(
                    "/api/kb/ask", json={"question": "核心贡献？", "model": "qwen3.5:9b"}
                )
        events = sse_events(response)
        error = next(event for event in events if event["type"] == "error")
        self.assertIn("检索失败", error["message"])

    def test_empty_knowledge_base_is_friendly(self):
        with patch("backend.app.api.routes_kb.get_available_models", return_value=["qwen3.5:9b"]):
            with patch("backend.app.api.routes_kb.hybrid_search", return_value=[]):
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
        client.collection_exists.return_value = True
        generation_store = Mock()
        generation_store.require_generation.return_value = {"alias_target": "papers_rebuild_live"}
        with patch("backend.app.api.routes_kb.get_client", return_value=client):
            with patch("backend.app.api.routes_kb._generation_store", return_value=generation_store):
                with patch("backend.app.api.routes_kb.count_points", return_value=42):
                    with patch("backend.app.api.routes_kb.embed_texts", return_value=[[0.1]]):
                        with patch("backend.app.api.routes_kb.load_papers", return_value=[{"paper_id": "p1"}]):
                            response = self.client.get("/api/kb/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["qdrant"])
        self.assertTrue(body["embedding"])
        self.assertEqual(body["chunks"], 42)
        self.assertEqual(body["papers"], 1)
        self.assertIn("reranker", body)
        client.collection_exists.assert_called_once_with("papers_rebuild_live")

    def test_degrades_when_components_down(self):
        with patch("backend.app.api.routes_kb.get_client", side_effect=RuntimeError("no qdrant")):
            with patch("backend.app.api.routes_kb.embed_texts", side_effect=RuntimeError("no ollama")):
                with patch("backend.app.api.routes_kb.load_papers", return_value=[]):
                    response = self.client.get("/api/kb/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["qdrant"])
        self.assertFalse(body["embedding"])


class AskChunkerTests(unittest.TestCase):
    """spec-012：切分版本每次提问时选择，默认 v1。"""

    def setUp(self):
        self.client = TestClient(app)
        self.hits = [Hit("p1", "paper.pdf", 4, 0, "混合检索提升召回", 0.9)]

    def _ask(self, payload, hits=None, reply="回答内容"):
        chat = Mock()
        token = Mock()
        token.content = reply
        chat.stream.return_value = [token]
        with patch("backend.app.api.routes_kb.get_available_models", return_value=["qwen3.5:9b"]):
            with patch("backend.app.api.routes_kb.hybrid_search",
                       return_value=self.hits if hits is None else hits) as search:
                with patch("backend.app.platform.ollama.create_chat_model", return_value=chat):
                    response = self.client.post("/api/kb/ask", json=payload)
        return response, search

    def test_defaults_to_v1(self):
        response, search = self._ask({"question": "核心贡献？", "model": "qwen3.5:9b"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(search.call_args.kwargs["chunker"], "v1")

    def test_passes_selected_chunker(self):
        response, search = self._ask(
            {"question": "核心贡献？", "model": "qwen3.5:9b", "chunker": "v2"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(search.call_args.kwargs["chunker"], "v2")

    def test_rejects_unknown_chunker(self):
        response = self.client.post(
            "/api/kb/ask", json={"question": "x", "model": "qwen3.5:9b", "chunker": "v3"}
        )
        self.assertEqual(response.status_code, 422)

    def test_meta_event_carries_chunker(self):
        response, _ = self._ask(
            {"question": "核心贡献？", "model": "qwen3.5:9b", "chunker": "v2"}
        )
        meta = [event for event in sse_events(response) if event["type"] == "meta"][0]
        self.assertEqual(meta["chunker"], "v2")

    def test_v2_not_ready_hint_does_not_fall_back_to_v1(self):
        """v2 无命中时给出明确提示，且不回退到 v1（spec-012 边界）。"""
        response, _ = self._ask(
            {"question": "核心贡献？", "model": "qwen3.5:9b", "chunker": "v2"}, hits=[]
        )
        tokens = [e["content"] for e in sse_events(response) if e["type"] == "token"]
        joined = "".join(tokens)
        self.assertIn("尚未就绪", joined)
        self.assertIn("v1", joined)


class ReindexTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "p1.pdf").write_bytes(b"%PDF-1.4 fake")
        self.paper = {
            "paper_id": "p1",
            "file_name": "p1.pdf",
            "status": "indexed",
            "chunkers": {
                "v1": {"status": "indexed", "chunk_count": 3, "progress": 100, "error": None},
                "v2": {"status": "failed", "chunk_count": 0, "progress": 0, "error": "x"},
            },
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_paper_returns_404(self):
        with patch("backend.app.api.routes_kb._require_generation", return_value=None), patch(
            "backend.app.api.routes_kb.submit_document_reindex",
            side_effect=KnowledgeDocumentMigrationError("DOCUMENT_NOT_FOUND"),
        ):
            response = self.client.post("/api/kb/papers/nope/reindex", json={"chunker": "all"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error_code"], "DOCUMENT_NOT_FOUND")

    def test_missing_source_file_returns_404(self):
        record = {"schema_version": "knowledge-document-v1", "document_id": "p1"}
        with patch("backend.app.api.routes_kb.load_papers_strict", return_value=[record]), patch(
            "backend.app.api.routes_kb._require_generation", return_value=None
        ), patch(
            "backend.app.api.routes_kb.submit_document_reindex",
            side_effect=KnowledgeDocumentMigrationError("SOURCE_NOT_FOUND"),
        ):
            response = self.client.post("/api/kb/papers/p1/reindex", json={"chunker": "all"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error_code"], "SOURCE_NOT_FOUND")

    def test_reindex_all_submits_both_versions(self):
        result = {"task_id": "task-1", "document_id": "p1", "chunker": "all", "submitted": {"v1": True, "v2": True}}
        record = {"schema_version": "knowledge-document-v1", "document_id": "p1"}
        with patch("backend.app.api.routes_kb.load_papers_strict", return_value=[record]), patch(
            "backend.app.api.routes_kb._require_generation", return_value=None
        ), patch(
            "backend.app.api.routes_kb.submit_document_reindex", return_value=result
        ) as submit:
            response = self.client.post("/api/kb/papers/p1/reindex", json={"chunker": "all"})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["chunker"], "all")
        self.assertEqual(response.headers["retry-after"], "2")
        submit.assert_called_once_with("p1", "all")

    def test_reindex_single_version(self):
        result = {"task_id": "task-2", "document_id": "p1", "chunker": "v2", "submitted": {"v2": True}}
        record = {"schema_version": "knowledge-document-v1", "document_id": "p1"}
        with patch("backend.app.api.routes_kb.load_papers_strict", return_value=[record]), patch(
            "backend.app.api.routes_kb._require_generation", return_value=None
        ), patch(
            "backend.app.api.routes_kb.submit_document_reindex", return_value=result
        ) as submit:
            response = self.client.post("/api/kb/papers/p1/reindex", json={"chunker": "v2"})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["chunker"], "v2")
        submit.assert_called_once_with("p1", "v2")

    def test_reindex_uses_stored_name_for_new_record(self):
        result = {"task_id": "task-3", "document_id": "p1", "chunker": "v1", "submitted": {"v1": True}}
        record = {"schema_version": "knowledge-document-v1", "document_id": "p1"}
        with patch("backend.app.api.routes_kb.load_papers_strict", return_value=[record]), patch(
            "backend.app.api.routes_kb._require_generation", return_value=None
        ), patch(
            "backend.app.api.routes_kb.submit_document_reindex", return_value=result
        ):
            response = self.client.post("/api/kb/papers/p1/reindex", json={"chunker": "v1"})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["task_id"], "task-3")


class PaperListChunkerTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_returns_per_version_state_and_progress(self):
        papers = [{
            "paper_id": "p1",
            "file_name": "a.pdf",
            "status": "indexed",
            "chunkers": {
                "v1": {"status": "indexed", "chunk_count": 3, "progress": 100, "error": None},
                "v2": {"status": "indexing", "chunk_count": 0, "progress": 45, "error": None},
            },
        }]
        with patch("backend.app.api.routes_kb.load_papers", return_value=papers):
            response = self.client.get("/api/kb/papers")
        chunkers = response.json()["papers"][0]["chunkers"]
        self.assertEqual(chunkers["v2"]["status"], "indexing")
        self.assertEqual(chunkers["v2"]["progress"], 45)


if __name__ == "__main__":
    unittest.main()
