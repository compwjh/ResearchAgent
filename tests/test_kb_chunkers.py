"""切分器单测（spec-012）。

重点覆盖：v1 行为零变更、v2 硬上限 / 跨章节不合并 / 跨页合并 / 降级，
以及 LLM prompt 编号与解析口径一致（曾因编号错位导致判定失效）。
"""

import unittest
from unittest.mock import patch

from backend.app.knowledge_base.infrastructure import chunkers as chunkers_module
from backend.app.knowledge_base.infrastructure import parse as parse_module
from backend.app.knowledge_base.infrastructure.chunkers import (
    Chunk,
    build_chunks_v1,
    build_chunks_v2,
    split_text,
)

LIMIT = 1200


def make_pages(count: int = 14):
    """构造多页文本：含编号小节、跨页正文、表格、参考文献。

    候选边界数刻意大于批大小（8），用于验证多批次时的编号口径。
    """
    pages = [(1, "Deep Skill Discovery\n\nAgentic systems rely on reusable procedural "
                 "capabilities to execute long-horizon tasks across many domains.")]
    for number in range(2, 11):
        pages.append((number, f"Body paragraph on page {number}. It continues the "
                              f"discussion without any heading so it becomes a candidate."))
    pages.append((11, "TABLE 1\n\nAblation results across three seeds, mean plus minus std."))
    pages.append((12, "3.2 Method\n\nOur method has three stages that run sequentially."))
    pages.append((13, "References\n\n[1] A. Author, \"A paper title,\" in ICML, 2023."))
    pages.append((14, "[2] B. Author, \"Another title,\" in NeurIPS, 2022."))
    return pages


PAGES = make_pages()


class ChunkCompatTests(unittest.TestCase):
    def test_new_fields_have_defaults(self):
        chunk = Chunk(text="x", page=3, chunk_index=0)
        self.assertEqual(chunk.section, "")
        self.assertEqual(chunk.page_end, 3, "page_end 未显式传时应等于 page")

    def test_page_end_keeps_explicit_value(self):
        chunk = Chunk(text="x", page=3, chunk_index=0, page_end=5, section="3.2 Method")
        self.assertEqual(chunk.page_end, 5)
        self.assertEqual(chunk.section, "3.2 Method")


class V1BehaviourTests(unittest.TestCase):
    """v1 从 parse.py 迁来，行为必须与迁移前一致。"""

    def test_split_text_short_input_returns_whole(self):
        self.assertEqual(split_text("短文本", chunk_size=100), ["短文本"])

    def test_split_text_empty_returns_empty(self):
        self.assertEqual(split_text("   "), [])

    def test_split_text_respects_size(self):
        pieces = split_text("正文内容。" * 200, chunk_size=300, overlap=50)
        self.assertTrue(pieces)
        self.assertTrue(all(len(piece) <= 300 for piece in pieces))

    def test_build_chunks_v1_never_crosses_pages(self):
        chunks = build_chunks_v1(PAGES)
        self.assertTrue(chunks)
        self.assertTrue(all(chunk.page_end == chunk.page for chunk in chunks))

    def test_build_chunks_v1_index_is_sequential(self):
        chunks = build_chunks_v1(PAGES)
        self.assertEqual([c.chunk_index for c in chunks], list(range(len(chunks))))

    def test_build_chunks_v1_skips_blank_pages(self):
        chunks = build_chunks_v1([(1, "内容"), (2, ""), (3, "更多内容")])
        self.assertEqual(sorted({c.page for c in chunks}), [1, 3])

    def test_parse_reexports_keep_import_paths(self):
        """既有导入路径不能断：index.py 用 build_chunks，__init__.py 用 split_text。"""
        self.assertIs(parse_module.split_text, chunkers_module.split_text)
        self.assertIs(parse_module.Chunk, chunkers_module.Chunk)
        # build_chunks 是 v1 的委派别名，行为必须与 build_chunks_v1 完全一致
        self.assertEqual(
            [chunk.text for chunk in parse_module.build_chunks(PAGES)],
            [chunk.text for chunk in chunkers_module.build_chunks_v1(PAGES)],
        )


class V2RuleTests(unittest.TestCase):
    def test_degrades_without_llm(self):
        chunks, llm_used = build_chunks_v2(PAGES, max_chars=LIMIT)
        self.assertTrue(chunks)
        self.assertFalse(llm_used)

    def test_hard_limit_is_never_exceeded(self):
        chunks, _ = build_chunks_v2(PAGES, max_chars=LIMIT)
        self.assertTrue(all(len(chunk.text) <= LIMIT for chunk in chunks))

    def test_no_duplicate_chunks(self):
        """曾因分组循环未推进 start 而产出大量重叠重复内容。"""
        chunks, _ = build_chunks_v2(PAGES, max_chars=LIMIT)
        texts = [chunk.text for chunk in chunks]
        self.assertEqual(len(texts), len(set(texts)))

    def test_sections_are_not_merged_across_headings(self):
        chunks, _ = build_chunks_v2(PAGES, max_chars=LIMIT)
        table = [c for c in chunks if "Ablation results" in c.text]
        method = [c for c in chunks if "Our method has three stages" in c.text]
        self.assertTrue(table and method)
        self.assertNotEqual(table[0].chunk_index, method[0].chunk_index)

    def test_reference_entry_becomes_own_chunk(self):
        chunks, _ = build_chunks_v2(PAGES, max_chars=LIMIT)
        refs = [c for c in chunks if c.text.strip().startswith("[1]")]
        self.assertTrue(refs, "参考文献条目应独立成块")

    def test_section_field_is_populated(self):
        chunks, _ = build_chunks_v2(PAGES, max_chars=LIMIT)
        sections = {chunk.section for chunk in chunks if chunk.section}
        self.assertTrue(sections & {"3.2 Method", "TABLE 1"})

    def test_page_end_covers_page_range(self):
        chunks, _ = build_chunks_v2(PAGES, max_chars=LIMIT)
        self.assertTrue(all(chunk.page_end >= chunk.page for chunk in chunks))
        self.assertTrue(all(chunk.page_end <= 14 for chunk in chunks))

    def test_empty_input_returns_empty(self):
        chunks, llm_used = build_chunks_v2([])
        self.assertEqual(chunks, [])
        self.assertFalse(llm_used)

    def test_oversized_block_without_sentence_breaks(self):
        """无句子边界的超长块曾导致无限递归，必须硬切兜底。"""
        chunks, _ = build_chunks_v2([(1, "X" * 5000)], max_chars=LIMIT)
        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk.text) <= LIMIT for chunk in chunks))


class V2LlmTests(unittest.TestCase):
    def test_prompt_numbering_restarts_each_batch(self):
        """编号必须每批从 1 开始，否则第 2 批起解析全部错位。"""
        prompts = []

        def fake_llm(prompt):
            prompts.append(prompt)
            return "[1]"

        build_chunks_v2(PAGES, max_chars=LIMIT, llm=fake_llm)
        self.assertGreater(len(prompts), 1, "候选数应多于一个批次")

        def first_number(prompt):
            for line in prompt.splitlines():
                if line.startswith("["):
                    return line.split("]")[0][1:]
            return None

        self.assertEqual(first_number(prompts[0]), "1")
        self.assertEqual(first_number(prompts[1]), "1")

    def test_llm_hits_are_applied(self):
        chunks, llm_used = build_chunks_v2(PAGES, max_chars=LIMIT, llm=lambda p: "[1, 3]")
        self.assertTrue(chunks)
        self.assertTrue(llm_used)

    def test_empty_reply_degrades_gracefully(self):
        chunks, llm_used = build_chunks_v2(PAGES, max_chars=LIMIT, llm=lambda p: "[]")
        self.assertTrue(chunks)
        self.assertTrue(llm_used, "合法 [] 也是成功解析的 LLM 决策")

    def test_unparsable_reply_degrades_gracefully(self):
        chunks, _ = build_chunks_v2(PAGES, max_chars=LIMIT, llm=lambda p: "我不知道")
        self.assertTrue(chunks)

    def test_out_of_range_numbers_are_dropped(self):
        chunks, _ = build_chunks_v2(PAGES, max_chars=LIMIT, llm=lambda p: "[99, 0]")
        self.assertTrue(chunks)

    def test_llm_exception_degrades_without_raising(self):
        def boom(_prompt):
            raise RuntimeError("ollama down")

        chunks, llm_used = build_chunks_v2(PAGES, max_chars=LIMIT, llm=boom)
        self.assertTrue(chunks, "LLM 失败必须降级出结果，不得阻塞上传")
        self.assertFalse(llm_used)
        self.assertTrue(all(len(chunk.text) <= LIMIT for chunk in chunks))

    def test_partial_llm_failure_commits_no_partial_boundaries(self):
        calls = 0

        def flaky(_prompt):
            nonlocal calls
            calls += 1
            if calls == 1:
                return "[]"
            raise RuntimeError("timeout")

        expected, _ = build_chunks_v2(PAGES, max_chars=LIMIT)
        actual, llm_used = build_chunks_v2(PAGES, max_chars=LIMIT, llm=flaky)
        self.assertFalse(llm_used)
        self.assertEqual([item.text for item in actual], [item.text for item in expected])

    def test_progress_is_monotonic_and_ends_at_100(self):
        seen = []
        build_chunks_v2(PAGES, max_chars=LIMIT, llm=lambda p: "[1]", progress=seen.append)
        self.assertTrue(seen)
        self.assertEqual(seen[-1], 100)
        self.assertTrue(all(b >= a for a, b in zip(seen, seen[1:])))
        self.assertTrue(all(0 <= value <= 100 for value in seen))

    def test_progress_callback_errors_do_not_break_chunking(self):
        def bad_progress(_value):
            raise RuntimeError("ui gone")

        chunks, _ = build_chunks_v2(PAGES, max_chars=LIMIT, progress=bad_progress)
        self.assertTrue(chunks)


class OllamaJudgeTests(unittest.TestCase):
    def test_raises_on_http_error(self):
        import httpx

        with patch.object(chunkers_module.httpx, "post", side_effect=httpx.HTTPError("down")):
            with self.assertRaises(chunkers_module.BoundaryLLMError):
                chunkers_module.ollama_boundary_judge("prompt")

    def test_raises_on_empty_content(self):
        response = __import__("unittest.mock", fromlist=["Mock"]).Mock()
        response.status_code = 200
        response.json.return_value = {"message": {"content": ""}}
        with patch.object(chunkers_module.httpx, "post", return_value=response):
            with self.assertRaises(chunkers_module.BoundaryLLMError):
                chunkers_module.ollama_boundary_judge("prompt")

    def test_returns_content_when_valid(self):
        from unittest.mock import Mock

        response = Mock()
        response.status_code = 200
        response.json.return_value = {"message": {"content": "[1, 2]"}}
        with patch.object(chunkers_module.httpx, "post", return_value=response) as post:
            self.assertEqual(chunkers_module.ollama_boundary_judge("prompt"), "[1, 2]")
        payload = post.call_args.kwargs["json"]
        self.assertFalse(payload["think"], "thinking 模型必须关思考，否则输出为空")


if __name__ == "__main__":
    unittest.main()
