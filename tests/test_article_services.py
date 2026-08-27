import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from backend.app.core.article_settings import ArticleSettings
from backend.app.domain.article import ArticleCandidate
from backend.app.services.article_download import download_article, safe_filename
from backend.app.services.article_search import search_articles
from backend.app.services.download_paper_skill import skill_status


class ArticleServiceTests(unittest.TestCase):
    def test_safe_filename_removes_path_separators(self):
        filename = safe_filename("../results/important paper")
        self.assertNotIn("/", filename)
        self.assertNotIn("..", filename)
        self.assertTrue(filename.endswith(".pdf"))

    @patch("backend.app.services.article_search.httpx.get")
    def test_crossref_response_becomes_candidate(self, mock_get):
        mock_get.return_value = httpx.Response(
            200,
            json={"message": {"items": [{"DOI": "10.1234/test", "title": ["A Research Paper"], "URL": "https://doi.org/10.1234/test"}]}},
            request=httpx.Request("GET", "https://api.crossref.org/works"),
        )
        candidates = search_articles("A Research Paper", ArticleSettings())
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].doi, "10.1234/test")

    def test_non_pdf_download_is_rejected(self):
        class FakeResponse:
            status_code = 200
            headers = {"content-type": "text/html", "content-length": "4"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def raise_for_status(self):
                return None

            def iter_bytes(self):
                yield b"nope"

        candidate = ArticleCandidate("candidate", "Paper", pdf_url="https://example.com/paper.pdf")
        with tempfile.TemporaryDirectory() as directory:
            settings = ArticleSettings(article_download_dir=directory)
            with patch("backend.app.services.article_download.httpx.stream", return_value=FakeResponse()):
                with self.assertRaises(ValueError):
                    next(download_article(candidate, settings))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_download_paper_skill_reports_missing_worker_model(self):
        status = skill_status([])
        self.assertFalse(status["available"])
        self.assertFalse(status["worker_model_available"])
        self.assertEqual(status["worker_model"], "deepseek-coder:33b")


if __name__ == "__main__":
    unittest.main()
