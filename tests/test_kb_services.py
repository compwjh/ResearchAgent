"""spec-011 知识库服务层单元测试（离线可重复：不依赖 Ollama / 真实向量库）。"""

import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx

from backend.app.services.kb import embed as embed_module
from backend.app.services.kb import index as index_module
from backend.app.services.kb import parse as parse_module
from backend.app.services.kb import prompts
from backend.app.services.kb import retrieve as retrieve_module
from backend.app.services.kb import store as store_module
from backend.app.services.kb.retrieve import Hit


def make_point(paper_id, chunk_index, score, text="片段", page=2, file_name="a.pdf"):
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


class SplitTextTests(unittest.TestCase):
    def test_short_text_stays_single_chunk(self):
        self.assertEqual(parse_module.split_text("很短的一句话", 1000, 200), ["很短的一句话"])

    def test_empty_text_returns_nothing(self):
        self.assertEqual(parse_module.split_text("   ", 1000, 200), [])

    def test_long_text_is_split_and_deterministic(self):
        text = "这是用于验证切分能力的长文本。" * 120
        chunks = parse_module.split_text(text, 500, 100)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 500)
        self.assertEqual(chunks, parse_module.split_text(text, 500, 100))

    def test_chunks_keep_page_and_index(self):
        chunks = parse_module.build_chunks([(1, "第一页内容。" * 40), (4, "第四页内容。")], 200, 40)
        self.assertEqual([chunk.page for chunk in chunks][-1], 4)
        self.assertEqual([chunk.chunk_index for chunk in chunks], list(range(len(chunks))))


class ExtractPagesTests(unittest.TestCase):
    def test_reads_text_from_real_pdf(self):
        import pymupdf

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.pdf"
            document = pymupdf.open()
            page = document.new_page()
            page.insert_text((72, 72), "Hybrid retrieval with bge-m3")
            document.save(str(path))
            document.close()
            pages = parse_module.extract_pages(path)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0][0], 1)
        self.assertIn("Hybrid retrieval", pages[0][1])

    def test_missing_file_raises_parse_error(self):
        with self.assertRaises(parse_module.PdfParseError):
            parse_module.extract_pages(Path("/tmp/definitely-missing-paper.pdf"))

    def test_encrypted_pdf_raises_parse_error(self):
        with patch("pymupdf.open") as mock_open:
            document = mock_open.return_value
            document.is_encrypted = True
            document.authenticate.return_value = False
            with self.assertRaises(parse_module.PdfParseError):
                parse_module.extract_pages("x.pdf")
        document.close.assert_called_once()

    def test_empty_document_raises_parse_error(self):
        with patch("pymupdf.open") as mock_open:
            document = mock_open.return_value
            document.is_encrypted = False
            document.page_count = 0
            with self.assertRaises(parse_module.PdfParseError):
                parse_module.extract_pages("x.pdf")


class SparseEncodingTests(unittest.TestCase):
    def test_tokenize_handles_mixed_languages(self):
        tokens = embed_module.tokenize("Hybrid RAG 混合检索 BM25")
        self.assertIn("hybrid", tokens)
        self.assertIn("bm25", tokens)
        self.assertTrue(any(token in ("混合", "检索") for token in tokens))

    def test_sparse_index_is_stable_and_bounded(self):
        first = embed_module.sparse_index("retrieval")
        second = embed_module.sparse_index("retrieval")
        self.assertEqual(first, second)
        self.assertGreaterEqual(first, 0)
        self.assertLess(first, embed_module.SPARSE_DIM)

    def test_sparse_index_does_not_use_python_hash(self):
        token = "rag"
        self.assertNotEqual(embed_module.sparse_index(token), hash(token) % embed_module.SPARSE_DIM)

    def test_term_frequency_uses_sublinear_weight(self):
        vector = embed_module.encode_sparse("检索 检索 向量")
        weights = dict(zip(vector.indices, vector.values))
        self.assertAlmostEqual(max(weights.values()), 1.0 + math.log(2), places=5)
        self.assertEqual(sorted(vector.indices), vector.indices)

    def test_empty_text_returns_empty_vector(self):
        vector = embed_module.encode_sparse("")
        self.assertEqual(vector.indices, [])
        self.assertEqual(vector.values, [])


class EmbedTextsTests(unittest.TestCase):
    def _response(self, count, status_code=200):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = {"embeddings": [[0.1, 0.2]] * count}
        return response

    def test_always_sends_explicit_num_batch(self):
        with patch.object(embed_module.httpx, "post", return_value=self._response(1)) as mock_post:
            vectors = embed_module.embed_texts(["一句话"])
        self.assertEqual(vectors, [[0.1, 0.2]])
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["options"]["num_batch"], embed_module.KB_EMBED_NUM_BATCH)

    def test_batches_requests(self):
        def fake_post(url, json=None, **kwargs):
            return self._response(len(json["input"]))

        with patch.object(embed_module, "KB_EMBED_BATCH_SIZE", 2):
            with patch.object(embed_module.httpx, "post", side_effect=fake_post) as mock_post:
                vectors = embed_module.embed_texts(["一", "二", "三", "四", "五"])
        self.assertEqual(len(vectors), 5)
        self.assertEqual(mock_post.call_count, 3)

    def test_num_batch_must_cover_longest_input(self):
        """num_batch 需 ≥ 单条输入 token 数，否则 Ollama 会静默截断（011-tech-review R1）。"""
        self.assertGreaterEqual(embed_module.KB_EMBED_NUM_BATCH, 1024)

    def test_retries_once_on_transport_error(self):
        failure = httpx.HTTPError("connection reset")
        with patch.object(embed_module.httpx, "post", side_effect=[failure, self._response(1)]) as mock_post:
            vectors = embed_module.embed_texts(["一句话"])
        self.assertEqual(vectors, [[0.1, 0.2]])
        self.assertEqual(mock_post.call_count, 2)

    def test_raises_after_repeated_transport_error(self):
        failure = httpx.HTTPError("connection reset")
        with patch.object(embed_module.httpx, "post", side_effect=failure):
            with self.assertRaises(embed_module.EmbeddingError):
                embed_module.embed_texts(["一句话"])

    def test_raises_on_http_error(self):
        response = Mock(status_code=500)
        response.json.return_value = {"error": "Compute error."}
        with patch.object(embed_module.httpx, "post", return_value=response):
            with self.assertRaises(embed_module.EmbeddingError) as context:
                embed_module.embed_texts(["一句话"])
        self.assertIn("Compute error.", str(context.exception))

    def test_raises_on_count_mismatch(self):
        with patch.object(embed_module.httpx, "post", return_value=self._response(1)):
            with self.assertRaises(embed_module.EmbeddingError):
                embed_module.embed_texts(["一", "二"])

    def test_raises_on_null_vector(self):
        response = Mock(status_code=200)
        response.json.return_value = {"embeddings": [None]}
        with patch.object(embed_module.httpx, "post", return_value=response):
            with self.assertRaises(embed_module.EmbeddingError):
                embed_module.embed_texts(["一句话"])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.meta = self.root / "papers.json"
        self.papers_dir = self.root / "papers"
        self.addCleanup(self.tmp.cleanup)

    def test_save_upload_uses_isolated_ids_for_same_name(self):
        first_id, first_path = store_module.save_upload("same.pdf", b"%PDF-1", papers_dir=self.papers_dir)
        second_id, second_path = store_module.save_upload("same.pdf", b"%PDF-1", papers_dir=self.papers_dir)
        self.assertNotEqual(first_id, second_id)
        self.assertTrue(first_path.exists())
        self.assertTrue(second_path.exists())

    def test_upsert_updates_existing_record(self):
        record = store_module.new_record("a.pdf")
        store_module.upsert_paper(record, meta_path=self.meta)
        record.status = store_module.STATUS_INDEXED
        record.chunk_count = 7
        store_module.upsert_paper(record, meta_path=self.meta)
        papers = store_module.load_papers(self.meta)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["status"], store_module.STATUS_INDEXED)
        self.assertEqual(papers[0]["chunk_count"], 7)

    def test_remove_paper_deletes_file_and_metadata(self):
        record = store_module.new_record("b.pdf")
        _, path = store_module.save_upload(
            "b.pdf", b"%PDF-1", papers_dir=self.papers_dir, paper_id=record.paper_id
        )
        store_module.upsert_paper(record, meta_path=self.meta)
        self.assertTrue(store_module.remove_paper(record.paper_id, self.meta, self.papers_dir))
        self.assertFalse(path.exists())
        self.assertEqual(store_module.load_papers(self.meta), [])
        self.assertFalse(store_module.remove_paper(record.paper_id, self.meta, self.papers_dir))

    def test_load_papers_tolerates_corrupt_file(self):
        self.meta.write_text("{ not json", encoding="utf-8")
        self.assertEqual(store_module.load_papers(self.meta), [])


class RetrievalTests(unittest.TestCase):
    def test_rrf_fuse_prefers_items_ranked_high_in_both_lists(self):
        shared = make_point("p1", 0, 0.9, text="共享片段")
        only_dense = make_point("p1", 1, 0.8)
        only_sparse = make_point("p1", 2, 0.7)
        fused = retrieve_module.rrf_fuse([[shared, only_dense], [shared, only_sparse]])
        self.assertEqual([hit.chunk_index for hit in fused], [0, 1, 2])
        self.assertAlmostEqual(fused[0].score, 2 / (retrieve_module.RRF_K + 1), places=9)

    def test_hybrid_search_fuses_two_routes(self):
        client = Mock()
        client.collection_exists.return_value = True
        client.query_points.side_effect = [
            SimpleNamespace(points=[make_point("p1", 1, 0.8)]),
            SimpleNamespace(points=[make_point("p1", 2, 0.7)]),
        ]
        with patch.object(retrieve_module, "embed_texts", return_value=[[0.1] * 4]):
            hits = retrieve_module.hybrid_search("问题", top_k=2, client=client)
        self.assertEqual(len(hits), 2)
        self.assertEqual(client.query_points.call_count, 2)
        usings = [call.kwargs["using"] for call in client.query_points.call_args_list]
        self.assertEqual(usings, [index_module.DENSE_VECTOR, index_module.SPARSE_VECTOR])

    def test_hybrid_search_returns_empty_without_collection(self):
        client = Mock()
        client.collection_exists.return_value = False
        with patch.object(retrieve_module, "embed_texts", return_value=[[0.1] * 4]):
            self.assertEqual(retrieve_module.hybrid_search("问题", client=client), [])

    def test_rerank_degrades_to_original_order_on_failure(self):
        hits = [Hit("p1", "a.pdf", 1, 0, "第一", 0.5), Hit("p1", "a.pdf", 2, 1, "第二", 0.4)]
        with patch.object(retrieve_module, "RERANKER_MODEL", "missing-reranker"):
            with patch("backend.app.services.ollama.create_chat_model", side_effect=RuntimeError("模型不可用")):
                self.assertEqual(retrieve_module.rerank("问题", hits), hits)

    def test_rerank_skipped_when_model_not_configured(self):
        hits = [Hit("p1", "a.pdf", 1, 0, "第一", 0.5)]
        with patch.object(retrieve_module, "RERANKER_MODEL", ""):
            self.assertEqual(retrieve_module.rerank("问题", hits), hits)


class IndexTests(unittest.TestCase):
    def tearDown(self):
        index_module.reset_client()

    def test_get_client_is_singleton_and_creates_directory(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "qdrant"
            first = index_module.get_client(str(target))
            second = index_module.get_client(str(target))
            index_module.ensure_collection(first)
            self.assertTrue(first.collection_exists(index_module.KB_COLLECTION))
            self.assertIs(first, second)
            self.assertTrue(target.exists())

    def test_ensure_collection_configures_sparse_idf(self):
        client = Mock()
        client.collection_exists.return_value = False
        index_module.ensure_collection(client, dim=1024)
        kwargs = client.create_collection.call_args.kwargs
        self.assertEqual(kwargs["sparse_vectors_config"][index_module.SPARSE_VECTOR].modifier.value, "idf")
        self.assertEqual(kwargs["vectors_config"][index_module.DENSE_VECTOR].size, 1024)

    def test_ensure_collection_is_idempotent(self):
        client = Mock()
        client.collection_exists.return_value = True
        index_module.ensure_collection(client)
        client.create_collection.assert_not_called()

    def test_count_points_without_collection(self):
        client = Mock()
        client.collection_exists.return_value = False
        self.assertEqual(index_module.count_points(client=client), 0)

    def test_upsert_chunks_skips_empty_input(self):
        client = Mock()
        self.assertEqual(index_module.upsert_chunks("p1", "a.pdf", [], client=client), 0)
        client.upsert.assert_not_called()

    def test_point_id_is_deterministic(self):
        self.assertEqual(index_module.point_id("p1", 3), index_module.point_id("p1", 3))
        self.assertNotEqual(index_module.point_id("p1", 3), index_module.point_id("p1", 4))

    def test_upsert_chunks_writes_dense_and_sparse(self):
        client = Mock()
        client.collection_exists.return_value = True
        chunks = [
            parse_module.Chunk(text="第一段", page=1, chunk_index=0),
            parse_module.Chunk(text="第二段", page=2, chunk_index=1),
        ]
        with patch.object(index_module, "embed_texts", return_value=[[0.1] * 4, [0.2] * 4]):
            count = index_module.upsert_chunks("p1", "a.pdf", chunks, "2026-01-01", client=client)
        self.assertEqual(count, 2)
        payload = client.upsert.call_args.kwargs
        self.assertEqual(len(payload["points"]), 2)
        self.assertIn(index_module.DENSE_VECTOR, payload["points"][0].vector)
        self.assertIn(index_module.SPARSE_VECTOR, payload["points"][0].vector)
        self.assertEqual(payload["points"][0].payload["page"], 1)

    def test_delete_paper_filters_by_paper_id(self):
        client = Mock()
        client.collection_exists.return_value = True
        index_module.delete_paper("p1", client=client)
        selector = client.delete.call_args.kwargs["points_selector"]
        self.assertEqual(selector.filter.must[0].match.value, "p1")

    def test_index_paper_marks_low_text_as_partial(self):
        record = store_module.new_record("scan.pdf")
        with patch.object(index_module, "extract_pages", return_value=[(1, " " * 5)]):
            with patch.object(index_module, "upsert_paper", side_effect=lambda item: item):
                result = index_module.index_paper(record, "scan.pdf")
        self.assertEqual(result["status"], store_module.STATUS_PARTIAL)
        self.assertEqual(result["chunk_count"], 0)

    def test_index_paper_marks_unreadable_pdf_as_failed(self):
        record = store_module.new_record("broken.pdf")
        with patch.object(index_module, "extract_pages", side_effect=parse_module.PdfParseError("PDF 已加密")):
            with patch.object(index_module, "upsert_paper", side_effect=lambda item: item):
                result = index_module.index_paper(record, "broken.pdf")
        self.assertEqual(result["status"], store_module.STATUS_FAILED)
        self.assertIn("加密", result["error"])

    def test_index_paper_records_chunk_count(self):
        record = store_module.new_record("ok.pdf")
        with patch.object(index_module, "extract_pages", return_value=[(1, "正文内容。" * 80)]):
            with patch.object(index_module, "upsert_chunks", return_value=4):
                with patch.object(index_module, "upsert_paper", side_effect=lambda item: item):
                    result = index_module.index_paper(record, "ok.pdf")
        self.assertEqual(result["status"], store_module.STATUS_INDEXED)
        self.assertEqual(result["chunk_count"], 4)
        self.assertEqual(result["page_count"], 1)

    def test_index_paper_captures_embedding_failure(self):
        record = store_module.new_record("ok.pdf")
        with patch.object(index_module, "extract_pages", return_value=[(1, "正文内容。" * 80)]):
            with patch.object(index_module, "upsert_chunks", side_effect=embed_module.EmbeddingError("OOM")):
                with patch.object(index_module, "upsert_paper", side_effect=lambda item: item):
                    result = index_module.index_paper(record, "ok.pdf")
        self.assertEqual(result["status"], store_module.STATUS_FAILED)
        self.assertIn("OOM", result["error"])


class PromptTests(unittest.TestCase):
    def test_prompt_contains_numbered_sources(self):
        hits = [Hit("p1", "paper.pdf", 3, 0, "混合检索效果更好", 0.9)]
        prompt = prompts.build_prompt("哪种检索更好？", hits)
        self.assertIn("[1]", prompt)
        self.assertIn("paper.pdf", prompt)
        self.assertIn("第 3 页", prompt)
        self.assertIn("哪种检索更好？", prompt)

    def test_citations_carry_page_and_file(self):
        hits = [Hit("p1", "paper.pdf", 7, 2, "内容", 0.123456)]
        citations = prompts.citation_payloads(hits)
        self.assertEqual(citations[0]["page"], 7)
        self.assertEqual(citations[0]["chunk_index"], 2)
        self.assertEqual(citations[0]["file_name"], "paper.pdf")
        self.assertEqual(citations[0]["score"], 0.123456)

    def test_citations_carry_source_text_for_expand(self):
        """引用需携带原文，供前端点击展开（011 产品验收 P21）。"""
        hits = [Hit("p1", "paper.pdf", 3, 0, "这是召回到的原文片段", 0.5)]
        self.assertEqual(prompts.citation_payloads(hits)[0]["text"], "这是召回到的原文片段")

    def test_citations_text_survives_html_characters(self):
        """原文含 HTML 时按原样下发，由前端 textContent 渲染（不在此处转义，避免双重转义）。"""
        hits = [Hit("p1", "paper.pdf", 1, 0, "<b>加粗</b> & <script>", 0.5)]
        self.assertEqual(prompts.citation_payloads(hits)[0]["text"], "<b>加粗</b> & <script>")


if __name__ == "__main__":
    unittest.main()
