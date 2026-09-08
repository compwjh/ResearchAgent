"""spec-011 知识库服务层单元测试（离线可重复：不依赖 Ollama / 真实向量库）。"""

import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx

from backend.app.knowledge_base.infrastructure import embed as embed_module
from backend.app.knowledge_base.infrastructure import index as index_module
from backend.app.knowledge_base.infrastructure import parse as parse_module
from backend.app.knowledge_base.infrastructure import prompts
from backend.app.knowledge_base.infrastructure import retrieve as retrieve_module
from backend.app.knowledge_base.infrastructure import store as store_module
from backend.app.knowledge_base.infrastructure.retrieve import Hit


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

    def test_record_metadata_is_optional_and_serialized(self):
        record = store_module.new_record(
            "readable.pdf",
            title="A Paper",
            authors=["A. Author"],
            year=2025,
            conference_id="ccs",
            conference_name="CCS",
            doi="10.1234/example",
            source_url="https://example.test/paper",
            import_source="paper-discovery",
            stored_name="2025-CCS-A-Paper.pdf",
        )
        payload = record.to_dict()
        self.assertEqual(payload["title"], "A Paper")
        self.assertEqual(payload["authors"], ["A. Author"])
        self.assertEqual(payload["stored_name"], "2025-CCS-A-Paper.pdf")

    def test_resolve_paper_path_supports_new_and_legacy_records(self):
        current = {"paper_id": "new", "stored_name": "2025-CCS-Paper.pdf"}
        legacy = {"paper_id": "old", "file_name": "old.pdf"}
        self.assertEqual(
            store_module.resolve_paper_path(current, self.papers_dir),
            self.papers_dir / "2025-CCS-Paper.pdf",
        )
        self.assertEqual(
            store_module.resolve_paper_path(legacy, self.papers_dir),
            self.papers_dir / "old.pdf",
        )

    def test_load_papers_keeps_legacy_record_without_metadata(self):
        self.meta.write_text(
            '[{"paper_id":"old","file_name":"old.pdf","status":"indexed"}]',
            encoding="utf-8",
        )
        papers = store_module.load_papers(self.meta)
        self.assertEqual(papers[0]["paper_id"], "old")
        self.assertNotIn("stored_name", papers[0])
        self.assertEqual(store_module.resolve_paper_path(papers[0], self.papers_dir), self.papers_dir / "old.pdf")

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

    def test_remove_paper_uses_stored_name(self):
        record = store_module.new_record("display.pdf", stored_name="readable-paper.pdf")
        target = self.papers_dir / record.stored_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"%PDF-1")
        store_module.upsert_paper(record, meta_path=self.meta)
        self.assertTrue(store_module.remove_paper(record.paper_id, self.meta, self.papers_dir))
        self.assertFalse(target.exists())

    def test_load_papers_tolerates_corrupt_file(self):
        self.meta.write_text("{ not json", encoding="utf-8")
        self.assertEqual(store_module.load_papers(self.meta), [])


class RetrievalTests(unittest.TestCase):
    def _hybrid_with_hits(self, hits, *, top_k, candidates=20, enabled=True, effect=None):
        client = Mock()
        client.collection_exists.return_value = True
        client.query_points.return_value = SimpleNamespace(points=[])

        def passthrough(_question, selected, **_kwargs):
            return SimpleNamespace(
                hits=list(selected), used=False, degraded=True,
                reason="disabled", scores_by_original_index=None,
            )

        with patch.object(retrieve_module, "embed_texts", return_value=[[0.1]]):
            with patch.object(retrieve_module, "encode_sparse", return_value=Mock()):
                with patch.object(retrieve_module, "rrf_fuse", return_value=hits):
                    with patch.object(retrieve_module, "KB_RERANK_CANDIDATES", candidates):
                        with patch.object(retrieve_module, "RERANKER_ENABLED", enabled):
                            with patch.object(
                                retrieve_module, "rerank_hits",
                                side_effect=effect or passthrough,
                            ) as mock_rerank:
                                result = retrieve_module.hybrid_search(
                                    "问题", top_k=top_k, client=client
                                )
        return result, mock_rerank

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
            with patch.object(retrieve_module, "rerank_hits", side_effect=lambda _, hits, **__: SimpleNamespace(
                hits=list(hits), used=False, scores_by_original_index=None
            )):
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

    def test_rerank_can_promote_rrf_twentieth_hit_and_maps_fields(self):
        hits = [Hit("p1", "a.pdf", 1, i, f"片段{i}", 1.0 - i / 100) for i in range(20)]
        scores = tuple(float(i) for i in range(20))

        def rank_reverse(_question, selected, **_kwargs):
            return SimpleNamespace(
                hits=list(reversed(selected)), used=True, degraded=False,
                reason=None, scores_by_original_index=scores,
            )

        result, mock_rerank = self._hybrid_with_hits(hits, top_k=5, effect=rank_reverse)
        self.assertEqual([hit.chunk_index for hit in result], [19, 18, 17, 16, 15])
        self.assertEqual(len(mock_rerank.call_args.args[1]), 20)
        for index, hit in enumerate(hits):
            self.assertEqual(hit.rerank_score, scores[index])
            self.assertEqual(hit.rerank_rank, 20 - index)

    def test_rerank_degraded_or_disabled_keeps_rrf_top_k(self):
        for enabled, reason in ((True, "timeout"), (False, "disabled")):
            with self.subTest(enabled=enabled):
                hits = [Hit("p1", "a.pdf", 1, i, f"片段{i}", 1.0 - i / 100) for i in range(8)]

                def degrade(_question, selected, **_kwargs):
                    return SimpleNamespace(
                        hits=list(selected), used=False, degraded=True,
                        reason=reason, scores_by_original_index=None,
                    )

                result, mock_rerank = self._hybrid_with_hits(
                    hits, top_k=5, enabled=enabled, effect=degrade
                )
                self.assertEqual(result, hits[:5])
                self.assertEqual(mock_rerank.call_args.kwargs["enabled"], enabled)
                self.assertTrue(all(hit.rerank_score is None for hit in hits))

    def test_rerank_candidate_count_handles_shortage_and_large_top_k(self):
        cases = ((3, 5, 20, 3), (10, 7, 3, 7))
        for hit_count, top_k, candidates, expected in cases:
            with self.subTest(hit_count=hit_count, top_k=top_k, candidates=candidates):
                hits = [Hit("p1", "a.pdf", 1, i, f"片段{i}", 1.0) for i in range(hit_count)]
                result, mock_rerank = self._hybrid_with_hits(
                    hits, top_k=top_k, candidates=candidates
                )
                self.assertEqual(len(mock_rerank.call_args.args[1]), expected)
                self.assertEqual(result, hits[:expected])


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


class DualChunkerIndexTests(unittest.TestCase):
    """spec-012：point_id 与 payload 必须带 chunker 维度，否则两版本会互相覆盖。"""

    def test_point_id_includes_chunker(self):
        self.assertNotEqual(
            index_module.point_id("p1", 0, "v1"), index_module.point_id("p1", 0, "v2")
        )

    def test_point_id_defaults_to_v1(self):
        self.assertEqual(index_module.point_id("p1", 0), index_module.point_id("p1", 0, "v1"))

    def test_point_id_is_deterministic_per_version(self):
        self.assertEqual(index_module.point_id("p1", 3, "v2"), index_module.point_id("p1", 3, "v2"))

    def test_upsert_writes_new_payload_fields(self):
        client = Mock()
        client.collection_exists.return_value = True
        chunks = [index_module.Chunk(text="正文", page=1, chunk_index=0, section="1 Intro")]
        with patch.object(index_module, "embed_texts", return_value=[[0.1]]):
            index_module.upsert_chunks("p1", "a.pdf", chunks, "2026-01-01", client=client,
                                       chunker="v2")
        payload = client.upsert.call_args.kwargs["points"][0].payload
        self.assertEqual(payload["chunker"], "v2")
        self.assertEqual(payload["section"], "1 Intro")
        self.assertEqual(payload["page_end"], 1)
        self.assertFalse(payload["is_citation"])

    def test_upsert_marks_citation_when_reference_zone_known(self):
        client = Mock()
        client.collection_exists.return_value = True
        # 两条 `[数字]` 条目即判定为参考文献区
        text = "[1] A. Author, \"T,\" in ICML, 2023.\n[2] B. Author, \"T2,\" in NeurIPS, 2022."
        chunks = [index_module.Chunk(text=text, page=9, chunk_index=0)]
        with patch.object(index_module, "embed_texts", return_value=[[0.1]]):
            index_module.upsert_chunks("p1", "a.pdf", chunks, client=client, chunker="v1",
                                       ref_start_page=8)
        self.assertTrue(client.upsert.call_args.kwargs["points"][0].payload["is_citation"])

    def test_upsert_keeps_citation_false_before_reference_zone(self):
        client = Mock()
        client.collection_exists.return_value = True
        text = "[1] A. Author, 2023.\n[2] B. Author, 2022."
        chunks = [index_module.Chunk(text=text, page=3, chunk_index=0)]
        with patch.object(index_module, "embed_texts", return_value=[[0.1]]):
            index_module.upsert_chunks("p1", "a.pdf", chunks, client=client, chunker="v1",
                                       ref_start_page=8)
        self.assertFalse(client.upsert.call_args.kwargs["points"][0].payload["is_citation"])

    def test_upsert_without_reference_zone_leaves_citation_false(self):
        client = Mock()
        client.collection_exists.return_value = True
        chunks = [index_module.Chunk(text="[1] A. Author, 2023.", page=9, chunk_index=0)]
        with patch.object(index_module, "embed_texts", return_value=[[0.1]]):
            index_module.upsert_chunks("p1", "a.pdf", chunks, client=client, chunker="v1")
        self.assertFalse(client.upsert.call_args.kwargs["points"][0].payload["is_citation"])

    def test_delete_paper_chunker_filters_by_both_keys(self):
        """T3：重建前必须按 paper_id + chunker 删除，否则残留旧点污染检索。"""
        client = Mock()
        client.collection_exists.return_value = True
        index_module.delete_paper_chunker("p1", "v2", client=client)
        conditions = client.delete.call_args.kwargs["points_selector"].filter.must
        self.assertEqual({cond.key for cond in conditions}, {"paper_id", "chunker"})

    def test_delete_paper_chunker_skips_missing_collection(self):
        client = Mock()
        client.collection_exists.return_value = False
        index_module.delete_paper_chunker("p1", "v2", client=client)
        client.delete.assert_not_called()


class RetrieveFilterTests(unittest.TestCase):
    def test_build_filter_by_chunker(self):
        self.assertEqual([c.key for c in retrieve_module.build_filter(chunker="v2").must],
                         ["chunker"])

    def test_build_filter_excludes_citations(self):
        flt = retrieve_module.build_filter(chunker="v1", include_citations=False)
        self.assertEqual([c.key for c in flt.must], ["chunker", "is_citation"])

    def test_build_filter_none_when_empty(self):
        self.assertIsNone(retrieve_module.build_filter())

    def test_citation_intent_positive(self):
        for text in ["这篇论文的参考文献有哪些", "列出参考书目", "list of references",
                     "bibliography", "which papers are cited"]:
            self.assertTrue(retrieve_module.looks_like_citation_query(text), text)

    def test_citation_intent_negative(self):
        for text in ["reference implementation 是什么", "这个方法的复杂度",
                     "实验结果怎么样", ""]:
            self.assertFalse(retrieve_module.looks_like_citation_query(text), text)

    def test_rrf_fuse_keeps_versions_apart(self):
        """T1：归并 key 缺 chunker 会让 v1/v2 静默混召回。"""
        def point(chunker):
            return SimpleNamespace(
                score=1.0,
                payload={"paper_id": "p1", "file_name": "a.pdf", "page": 1,
                         "chunk_index": 0, "text": "t", "chunker": chunker},
            )

        fused = retrieve_module.rrf_fuse([[point("v1"), point("v2")]])
        self.assertEqual(len(fused), 2)

    def test_hybrid_search_filters_both_routes(self):
        """T2：两路都必须带同一个 filter，否则稀疏路会漏掉过滤。"""
        client = Mock()
        client.collection_exists.return_value = True
        client.query_points.return_value = Mock(points=[])
        with patch.object(retrieve_module, "embed_texts", return_value=[[0.1]]):
            with patch.object(retrieve_module, "encode_sparse", return_value=Mock()):
                with patch.object(retrieve_module, "rerank_hits", side_effect=lambda _, hits, **__: SimpleNamespace(
                    hits=list(hits), used=False, scores_by_original_index=None
                )):
                    retrieve_module.hybrid_search("问题", client=client, chunker="v2")
        calls = client.query_points.call_args_list
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertIn("chunker", [c.key for c in call.kwargs["query_filter"].must])

    def test_hit_defaults_page_end_to_page(self):
        hit = Hit("p1", "a.pdf", 3, 0, "t", 1.0)
        self.assertEqual(hit.page_end, 3)

    def test_markdown_payload_keeps_null_page_and_lines(self):
        point = SimpleNamespace(
            score=0.5,
            payload={
                "paper_id": "p1", "file_name": "a.md", "page": None,
                "page_end": None, "start_line": 7, "end_line": 10,
                "chunk_index": 0, "text": "markdown", "chunker": "v1",
            },
        )
        hit = retrieve_module._to_hit(point)
        self.assertIsNone(hit.page)
        self.assertIsNone(hit.page_end)
        self.assertEqual((hit.start_line, hit.end_line), (7, 10))
        payload = prompts.citation_payloads([hit])[0]
        self.assertIsNone(payload["page"])
        self.assertIsNone(payload["page_end"])
        self.assertEqual((payload["start_line"], payload["end_line"]), (7, 10))

    def test_markdown_context_uses_line_range_without_page_zero(self):
        hit = Hit(
            "p1", "a.md", None, 0, "markdown", 0.5,
            start_line=7, end_line=10,
        )
        context = prompts.build_context([hit])
        self.assertIn("行 7–10", context)
        self.assertNotIn("第 0 页", context)


class BackfillTests(unittest.TestCase):
    """旧点缺 chunker 字段会导致按版本过滤后完全检索不到，迁移必须补上。"""

    def test_backfills_missing_chunker_field(self):
        client = Mock()
        client.collection_exists.return_value = True
        stale = SimpleNamespace(id="1", payload={"page": 4})
        client.scroll.return_value = ([stale], None)
        count = index_module.backfill_chunker_defaults(client=client)
        self.assertEqual(count, 1)
        written = [call.kwargs["payload"] for call in client.set_payload.call_args_list]
        self.assertTrue(any("chunker" in payload for payload in written))

    def test_backfill_skips_already_migrated(self):
        client = Mock()
        client.collection_exists.return_value = True
        client.scroll.return_value = ([SimpleNamespace(id="1", payload={"chunker": "v1"})], None)
        self.assertEqual(index_module.backfill_chunker_defaults(client=client), 0)

    def test_backfill_skips_missing_collection(self):
        client = Mock()
        client.collection_exists.return_value = False
        self.assertEqual(index_module.backfill_chunker_defaults(client=client), 0)


class CitationPageRangeTests(unittest.TestCase):
    """spec-012：v2 跨页合并片段的引用显示为 `p.3-4`，单页仍为 `p.3`。"""

    def test_payload_carries_page_end(self):
        hits = [Hit("p1", "a.pdf", 3, 0, "跨页片段", 1.0, page_end=4)]
        payload = prompts.citation_payloads(hits)[0]
        self.assertEqual(payload["page"], 3)
        self.assertEqual(payload["page_end"], 4)

    def test_payload_falls_back_to_page_when_not_cross_page(self):
        hits = [Hit("p1", "a.pdf", 3, 0, "单页片段", 1.0)]
        self.assertEqual(prompts.citation_payloads(hits)[0]["page_end"], 3)

    def test_context_shows_range_for_cross_page_hit(self):
        hits = [Hit("p1", "a.pdf", 3, 0, "跨页片段", 1.0, page_end=4)]
        self.assertIn("第 3-4 页", prompts.build_context(hits))

    def test_context_shows_single_page(self):
        hits = [Hit("p1", "a.pdf", 3, 0, "单页片段", 1.0)]
        context = prompts.build_context(hits)
        self.assertIn("第 3 页", context)
        self.assertNotIn("3-4", context)


if __name__ == "__main__":
    unittest.main()
