import unittest
from unittest.mock import patch

from backend.app.core.article_settings import ArticleSettings
from backend.app.domain.article import ArticleCandidate
from backend.app.services.article_download import probe_pdf_url


class ArticleDownloadProbeTests(unittest.TestCase):
    def test_unspecified_content_type_with_pdf_header_is_public_pdf(self):
        class FakeResponse:
            status_code = 200
            headers = {"content-type": "application/octet-stream"}
            url = "https://example.com/paper.pdf"

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def raise_for_status(self):
                return None

            def iter_bytes(self):
                yield b"%PDF-1.7"

        candidate = ArticleCandidate("candidate", "Paper", pdf_url="https://example.com/paper.pdf")
        with patch("backend.app.services.article_download.httpx.stream", return_value=FakeResponse()):
            self.assertEqual(probe_pdf_url(candidate, ArticleSettings()), ("public_pdf", "https://example.com/paper.pdf"))

    def test_auth_response_requires_login(self):
        class FakeResponse:
            status_code = 403
            headers = {}
            url = "https://example.com/login"

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        candidate = ArticleCandidate("candidate", "Paper", article_url="https://example.com/login")
        with patch("backend.app.services.article_download.httpx.stream", return_value=FakeResponse()):
            self.assertEqual(probe_pdf_url(candidate, ArticleSettings()), ("login_required", "https://example.com/login"))


if __name__ == "__main__":
    unittest.main()
