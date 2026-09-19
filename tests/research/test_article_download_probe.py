import unittest
from unittest.mock import patch

from backend.app.article_assistant.domain.article import ArticleCandidate
from backend.app.article_assistant.infrastructure.article_download import probe_pdf_url
from backend.app.platform.settings.settings_repository import ArticleSettings


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
        settings = ArticleSettings(article_download_urls=["https://example.com/fallback.pdf"])
        with patch("backend.app.core.url_security.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]), patch(
            "backend.app.article_assistant.infrastructure.article_download.httpx.stream", return_value=FakeResponse()
        ):
            self.assertEqual(probe_pdf_url(candidate, settings), ("public_pdf", "https://example.com/paper.pdf"))

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
        settings = ArticleSettings(article_download_urls=["https://example.com/fallback.pdf"])
        with patch("backend.app.core.url_security.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]), patch(
            "backend.app.article_assistant.infrastructure.article_download.httpx.stream", return_value=FakeResponse()
        ):
            self.assertEqual(probe_pdf_url(candidate, settings), ("login_required", "https://example.com/login"))

    def test_private_ip_is_rejected_before_http_request(self):
        candidate = ArticleCandidate("candidate", "Private", pdf_url="http://127.0.0.1/private.pdf")
        with patch("backend.app.article_assistant.infrastructure.article_download.httpx.stream") as stream:
            self.assertEqual(probe_pdf_url(candidate, ArticleSettings()), ("not_found", "http://127.0.0.1/private.pdf"))
        stream.assert_not_called()

    def test_redirect_to_private_ip_is_rejected_and_not_followed(self):
        class RedirectResponse:
            status_code = 302
            headers = {"location": "http://127.0.0.1/private.pdf"}
            url = "https://example.com/article"

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        candidate = ArticleCandidate("candidate", "Redirect", article_url="https://example.com/article")
        settings = ArticleSettings(article_download_urls=["https://example.com/fallback.pdf"])
        with patch("backend.app.core.url_security.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]), patch(
            "backend.app.article_assistant.infrastructure.article_download.httpx.stream",
            return_value=RedirectResponse(),
        ) as stream:
            self.assertEqual(probe_pdf_url(candidate, settings), ("not_found", "https://example.com/article"))
        self.assertEqual(stream.call_count, 1)

    def test_unconfigured_public_candidate_host_is_not_allowed(self):
        candidate = ArticleCandidate("candidate", "Unconfigured", pdf_url="https://example.com/paper.pdf")
        with patch("backend.app.article_assistant.infrastructure.article_download.httpx.stream") as stream:
            self.assertEqual(probe_pdf_url(candidate, ArticleSettings()), ("not_found", "https://example.com/paper.pdf"))
        stream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
