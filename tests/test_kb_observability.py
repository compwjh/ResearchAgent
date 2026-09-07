"""spec-013 知识库 embedding / retrieval 阶段埋点单元测试。

全部离线：mock 掉 Ollama / Qdrant 真实后端，并对 record_event 做断言。
绝不触发任何真实网络或模型调用。
"""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx

from backend.app.knowledge_base.infrastructure import embed as embed_module
from backend.app.knowledge_base.infrastructure import retrieve as retrieve_module


def make_point(paper_id, chunk_index, score, text="片段", page=1, file_name="a.pdf"):
    return SimpleNamespace(
        id=f"{paper_id}-{chunk_index}",
        score=score,
        payload={
            "paper_id": paper_id,
            "file_name": file_name,
            "page": page,
            "chunk_index": chunk_index,
            "text": text,
        },
    )


class EmbedEventTests(unittest.TestCase):
    def _response(self, count, status_code=200):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = {"embeddings": [[0.1, 0.2]] * count}
        return response

    def test_records_success_event(self):
        def fake_post(url, json=None, **kwargs):
            return self._response(len(json["input"]))

        with patch.object(embed_module.httpx, "post", side_effect=fake_post):
            with patch.object(embed_module, "record_event") as record:
                vectors = embed_module.embed_texts(["一句话", "第二句"])
        self.assertEqual(vectors, [[0.1, 0.2], [0.1, 0.2]])
        record.assert_called_once()
        kwargs = record.call_args.kwargs
        self.assertEqual(kwargs["name"], "kb.embedding")
        self.assertIsInstance(kwargs["duration_ms"], float)
        self.assertGreaterEqual(kwargs["duration_ms"], 0)
        metadata = kwargs["metadata"]
        self.assertEqual(metadata["model"], embed_module.EMBED_MODEL)
        self.assertEqual(metadata["text_count"], 2)
        self.assertEqual(metadata["status"], "ok")

    def test_records_error_event_and_reraises(self):
        failure = httpx.HTTPError("connection reset")
        with patch.object(embed_module.httpx, "post", side_effect=failure):
            with patch.object(embed_module, "record_event") as record:
                with self.assertRaises(embed_module.EmbeddingError):
                    embed_module.embed_texts(["一句话"])
        record.assert_called_once()
        kwargs = record.call_args.kwargs
        self.assertEqual(kwargs["name"], "kb.embedding")
        self.assertIsInstance(kwargs["duration_ms"], float)
        self.assertGreaterEqual(kwargs["duration_ms"], 0)
        self.assertEqual(kwargs["metadata"]["status"], "error")
        self.assertEqual(kwargs["metadata"]["error_type"], "EmbeddingError")
        self.assertEqual(kwargs["metadata"]["text_count"], 1)


class RetrievalEventTests(unittest.TestCase):
    def _events(self, record, name):
        return [call.kwargs for call in record.call_args_list if call.kwargs["name"] == name]

    def test_records_success_event(self):
        client = Mock()
        client.collection_exists.return_value = True
        client.query_points.side_effect = [
            SimpleNamespace(points=[make_point("p1", 1, 0.8)]),
            SimpleNamespace(points=[make_point("p1", 2, 0.7)]),
        ]
        with patch.object(retrieve_module, "embed_texts", return_value=[[0.1] * 4]):
            with patch.object(retrieve_module, "record_event") as record:
                hits = retrieve_module.hybrid_search("问题", top_k=5, chunker="v1", client=client)
        self.assertEqual(len(hits), 2)
        kwargs = self._events(record, "kb.retrieval")[0]
        self.assertEqual(kwargs["name"], "kb.retrieval")
        self.assertIsInstance(kwargs["duration_ms"], float)
        self.assertGreaterEqual(kwargs["duration_ms"], 0)
        metadata = kwargs["metadata"]
        self.assertEqual(metadata["top_k"], 5)
        self.assertGreaterEqual(metadata["candidate_pool"], 1)
        self.assertEqual(metadata["chunker"], "v1")
        self.assertIn("reranker_enabled", metadata)
        self.assertIsInstance(metadata["reranker_enabled"], bool)
        self.assertEqual(metadata["hit_count"], 2)
        self.assertEqual(metadata["status"], "ok")

    def test_records_event_on_empty_collection(self):
        client = Mock()
        client.collection_exists.return_value = False
        with patch.object(retrieve_module, "embed_texts", return_value=[[0.1] * 4]):
            with patch.object(retrieve_module, "record_event") as record:
                result = retrieve_module.hybrid_search("问题", client=client)
        self.assertEqual(result, [])
        kwargs = self._events(record, "kb.retrieval")[0]
        self.assertEqual(kwargs["name"], "kb.retrieval")
        self.assertEqual(kwargs["metadata"]["status"], "ok")
        self.assertEqual(kwargs["metadata"]["hit_count"], 0)

    def test_records_error_event_and_reraises(self):
        client = Mock()
        client.collection_exists.return_value = True
        client.query_points.side_effect = RuntimeError("qdrant down")
        with patch.object(retrieve_module, "embed_texts", return_value=[[0.1] * 4]):
            with patch.object(retrieve_module, "record_event") as record:
                with self.assertRaises(RuntimeError):
                    retrieve_module.hybrid_search("问题", client=client)
        kwargs = self._events(record, "kb.retrieval")[0]
        self.assertEqual(kwargs["name"], "kb.retrieval")
        self.assertIsInstance(kwargs["duration_ms"], float)
        self.assertGreaterEqual(kwargs["duration_ms"], 0)
        self.assertEqual(kwargs["metadata"]["status"], "error")
        self.assertEqual(kwargs["metadata"]["error_type"], "RuntimeError")

    def test_rerank_records_success(self):
        hits = [make_point("p1", 1, 0.8), make_point("p1", 2, 0.7)]
        converted = [retrieve_module._to_hit(point) for point in hits]
        chat = Mock()
        chat.invoke.side_effect = [SimpleNamespace(content="9"), SimpleNamespace(content="2")]
        with patch("backend.app.services.ollama.create_chat_model", return_value=chat):
            with patch.object(retrieve_module, "record_event") as record:
                result = retrieve_module.rerank("问题", converted, model="reranker")
        self.assertEqual([hit.chunk_index for hit in result], [1, 2])
        event = self._events(record, "kb.rerank")[0]
        self.assertEqual(event["metadata"], {
            "status": "ok", "input_count": 2, "output_count": 2, "enabled": True
        })

    def test_rerank_records_disabled(self):
        hit = retrieve_module._to_hit(make_point("p1", 1, 0.8))
        with patch.object(retrieve_module, "record_event") as record:
            result = retrieve_module.rerank("问题", [hit], model="")
        self.assertEqual(result, [hit])
        event = self._events(record, "kb.rerank")[0]
        self.assertEqual(event["metadata"]["status"], "disabled")
        self.assertFalse(event["metadata"]["enabled"])

    def test_rerank_records_degraded_and_observation_failure_is_ignored(self):
        hits = [retrieve_module._to_hit(make_point("p1", 1, 0.8)), retrieve_module._to_hit(make_point("p1", 2, 0.7))]
        with patch("backend.app.services.ollama.create_chat_model", side_effect=RuntimeError("offline")):
            with patch.object(retrieve_module, "record_event", side_effect=RuntimeError("telemetry")):
                result = retrieve_module.rerank("问题", hits, model="reranker")
        self.assertEqual(result, hits)


if __name__ == "__main__":
    unittest.main()
