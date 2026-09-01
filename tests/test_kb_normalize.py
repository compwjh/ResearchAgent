"""文本清洗与参考文献识别单测（spec-012）。

覆盖 LaTeX 排版噪声的两类根因（行末连字符断词、段落内硬换行），
以及"只对疑似排版产物下手"的边界：真连字符、列表、标题不能被误伤。
"""

import unittest

from backend.app.services.kb.normalize import (
    detect_citation,
    locate_reference_start,
    normalize_text,
)


class HyphenBreakTests(unittest.TestCase):
    def test_joins_hyphenated_word_broken_across_lines(self):
        self.assertEqual(normalize_text("proce-\ndural"), "procedural")

    def test_hyphen_is_removed_when_joining(self):
        """已知局限（012-tech-review T5）：真连字符折行也会被合并掉连字符。

        `long-\nhorizon` → `longhorizon`，无法与断词区分，spec 明确不追求消除，
        此处固化该行为以便将来若要改进时能被测试捕捉。
        """
        self.assertEqual(normalize_text("long-\nhorizon tasks"), "longhorizon tasks")

    def test_keeps_real_hyphen_on_one_line(self):
        """行内真连字符中间没有换行，不能被动到。"""
        self.assertEqual(normalize_text("state-of-the-art e-mail"), "state-of-the-art e-mail")

    def test_multiple_hyphen_breaks(self):
        self.assertEqual(normalize_text("dis-\ncov-\nery"), "discovery")


class SoftLineBreakTests(unittest.TestCase):
    def test_joins_mid_sentence_break_with_space(self):
        self.assertEqual(normalize_text("skills\noperate across tasks"), "skills operate across tasks")

    def test_keeps_break_after_sentence_ending_punctuation(self):
        self.assertEqual(normalize_text("This is one.\nThis is two."), "This is one.\nThis is two.")

    def test_keeps_break_before_list_item(self):
        text = normalize_text("We compare:\n- first item\n- second item")
        self.assertIn("- first item\n- second item", text)

    def test_keeps_break_before_numbered_section(self):
        """`1. Introduction` 这类以「数字. + 空格」开头的行为结构行。

        注意 `3.2 Method` 不在此列（正则要求小数点后紧跟空白），
        它靠"上一行以句末标点结尾"来保留换行。
        """
        text = normalize_text("Body text here\n1. Introduction")
        self.assertIn("\n1. Introduction", text)

    def test_keeps_break_before_subsection_after_sentence(self):
        self.assertEqual(
            normalize_text("Body text here.\n3.2 Method details"),
            "Body text here.\n3.2 Method details",
        )

    def test_keeps_break_before_uppercase_heading(self):
        self.assertEqual(normalize_text("Some body text\nABSTRACT"), "Some body text\nABSTRACT")

    def test_collapses_whitespace_runs(self):
        self.assertEqual(normalize_text("a  \t b"), "a b")

    def test_preserves_paragraph_breaks(self):
        self.assertEqual(normalize_text("Para one.\n\nPara two."), "Para one.\n\nPara two.")

    def test_empty_input(self):
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text(None), "")


class ReferenceZoneTests(unittest.TestCase):
    def test_ref_zone_keeps_only_new_entries(self):
        """参考文献区内只有 `[数字]` 开头才换行，避免条目被行末冒号切成两半。"""
        raw = "[1] A. Author, \"Title,\" in ICML, 2023.\ncontinued text here"
        result = normalize_text(raw, ref_zone=True)
        self.assertEqual(result, "[1] A. Author, \"Title,\" in ICML, 2023. continued text here")

    def test_ref_zone_splits_on_new_entry(self):
        raw = "[1] A. Author, 2023.\n[2] B. Author, 2022."
        result = normalize_text(raw, ref_zone=True)
        self.assertEqual(result.count("\n"), 1)


class LocateReferenceStartTests(unittest.TestCase):
    def test_finds_plain_references_heading(self):
        pages = [(1, "Body"), (5, "References\n\n[1] A. Author")]
        self.assertEqual(locate_reference_start(pages), 5)

    def test_finds_numbered_heading(self):
        pages = [(1, "Body"), (7, "6. References\n\n[1] A.")]
        self.assertEqual(locate_reference_start(pages), 7)

    def test_finds_chinese_heading(self):
        pages = [(3, "参考文献\n\n[1] 作者")]
        self.assertEqual(locate_reference_start(pages), 3)

    def test_returns_none_when_absent(self):
        self.assertIsNone(locate_reference_start([(1, "Abstract"), (2, "Method")]))


class DetectCitationTests(unittest.TestCase):
    def test_returns_false_without_reference_zone(self):
        text = "[1] A. Author, \"T,\" in ICML, 2023.\n[2] B. Author, \"T2,\" in NeurIPS, 2022."
        self.assertFalse(detect_citation(text, page=9, ref_start_page=None))

    def test_returns_false_before_reference_zone(self):
        text = "[1] A. Author, 2023.\n[2] B. Author, 2022."
        self.assertFalse(detect_citation(text, page=3, ref_start_page=8))

    def test_detects_by_entry_count(self):
        text = "[1] A. Author, 2023.\n[2] B. Author, 2022."
        self.assertTrue(detect_citation(text, page=9, ref_start_page=8))

    def test_detects_by_feature_density(self):
        text = ("K. Nottingham, \"A title,\" in ICML, 2023. "
                "arXiv:2301.00001. et al. in Proceedings of.")
        self.assertTrue(detect_citation(text, page=9, ref_start_page=8))

    def test_body_text_is_not_citation(self):
        text = "Our method improves accuracy on three benchmarks in 2024."
        self.assertFalse(detect_citation(text, page=9, ref_start_page=8))


if __name__ == "__main__":
    unittest.main()
