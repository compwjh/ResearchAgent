import unittest
from unittest.mock import patch

from backend.app.domain.article import ArticleCandidate
from backend.app.platform.settings.settings_repository import ArticleSettings
from backend.app.services.article_download import probe_pdf_url


class ArticleHtmlProbeTests(unittest.TestCase):
    def test_article_page_can_reveal_pdf_link(self):
        class HtmlResponse:
            status_code = 200
            headers = {"content-type": "text/html"}
            url = "https://example.com/article"

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def raise_for_status(self):
                return None

            def iter_bytes(self):
                yield b'<a href="/download/paper.pdf">PDF</a>'

        class PdfResponse(HtmlResponse):
            headers = {"content-type": "application/octet-stream"}
            url = "https://example.com/download/paper.pdf"

            def iter_bytes(self):
                yield b"%PDF-1.7"

        candidate = ArticleCandidate("candidate", "Paper", article_url="https://example.com/article")
        with patch("backend.app.services.article_download.httpx.stream", side_effect=[HtmlResponse(), PdfResponse()]):
            self.assertEqual(probe_pdf_url(candidate, ArticleSettings()), ("public_pdf", "https://example.com/download/paper.pdf"))


if __name__ == "__main__":
    unittest.main()
