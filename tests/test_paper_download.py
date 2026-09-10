import io
import stat
from pathlib import Path

import httpx
import pytest

from backend.app.paper_discovery.infrastructure.paper_download import (
    DOWNLOAD_BLOCKED,
    DOWNLOAD_TIMEOUT,
    INVALID_PDF,
    LOGIN_REQUIRED,
    PDF_NOT_FOUND,
    PDF_TOO_LARGE,
    PaperDownloadError,
    download_candidate,
)
from backend.app.platform.settings.settings_repository import ArticleSettings

PUBLIC = "93.184.216.34"
PDF = b"%PDF-1.7\nminimal test body"


class BrokenPdfStream(httpx.SyncByteStream):
    def __iter__(self):
        yield b"%PDF-1.7\npartial"
        raise httpx.ReadError("connection dropped")

    def close(self):
        return None


def encrypted_pdf() -> bytes:
    import fitz

    document = fitz.open()
    document.new_page()
    output = io.BytesIO()
    document.save(output, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="password", owner_pw="owner")
    document.close()
    return output.getvalue()


def settings(tmp_path: Path) -> ArticleSettings:
    return ArticleSettings(article_download_dir=str(tmp_path))


def run_download(tmp_path, handler, candidate=None, **kwargs):
    transport = httpx.MockTransport(handler)
    validate_pages = kwargs.pop("validate_pdf_pages", False)
    return download_candidate(
        candidate or {"pdf_url": "https://papers.example/paper.pdf"},
        settings(tmp_path),
        {"papers.example"},
        transport=transport,
        dns_resolver=lambda _host: [PUBLIC],
        peer_ip_resolver=lambda *_args: PUBLIC,
        validate_pdf_pages=validate_pages,
        **kwargs,
    )


def test_downloads_pdf_with_manual_redirect_and_private_random_file(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/paper.pdf":
            return httpx.Response(302, headers={"Location": "/final.pdf"})
        return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=PDF)

    result = run_download(tmp_path, handler)
    output = Path(result.file_path)
    assert calls == ["/paper.pdf", "/final.pdf"]
    assert output.read_bytes() == PDF
    assert output.suffix == ".pdf"
    assert stat.S_IMODE(output.parent.stat().st_mode) == 0o700
    assert result.file_size == len(PDF)


def test_only_candidate_pdf_url_is_used(tmp_path):
    def handler(request):
        return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=PDF)

    with pytest.raises(PaperDownloadError) as error:
        download_candidate(
            {"article_url": "https://papers.example/paper.pdf"},
            ArticleSettings(article_download_urls=["https://papers.example/fallback.pdf"], article_download_dir=str(tmp_path)),
            {"papers.example"},
        )
    assert error.value.code == PDF_NOT_FOUND


def test_redirect_target_is_revalidated_and_blocked(tmp_path):
    def handler(request):
        return httpx.Response(302, headers={"Location": "https://private.example/x.pdf"})

    with pytest.raises(PaperDownloadError) as error:
        run_download(tmp_path, handler, max_redirects=5)
    assert error.value.code == DOWNLOAD_BLOCKED
    assert not list(tmp_path.rglob("*"))


def test_two_hop_redirect_loop_hits_bound_and_cleans_private_files(tmp_path):
    def handler(request):
        next_path = "/a" if request.url.path in ("/paper.pdf", "/b") else "/b"
        return httpx.Response(302, headers={"Location": next_path})

    with pytest.raises(PaperDownloadError) as error:
        run_download(tmp_path, handler, max_redirects=2)
    assert error.value.code == DOWNLOAD_BLOCKED
    assert not list(tmp_path.rglob("*"))


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(401), LOGIN_REQUIRED),
        (httpx.Response(404), PDF_NOT_FOUND),
        (httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"%PDF-not-real"), INVALID_PDF),
        (httpx.Response(200, headers={"Content-Type": "application/json"}, content=PDF), INVALID_PDF),
    ],
)
def test_stable_http_and_pdf_errors_are_reported_and_cleaned(tmp_path, response, code):
    with pytest.raises(PaperDownloadError) as error:
        run_download(tmp_path, lambda _request, response=response: response)
    assert error.value.code == code
    assert not list(tmp_path.rglob("*"))


def test_declared_and_streamed_size_limits_clean_up(tmp_path):
    with pytest.raises(PaperDownloadError) as error:
        run_download(tmp_path, lambda _request: httpx.Response(200, headers={"Content-Length": "11"}, content=PDF), max_bytes=10)
    assert error.value.code == PDF_TOO_LARGE
    assert not list(tmp_path.rglob("*"))


def test_oversized_headers_are_blocked_without_echoing_sensitive_headers(tmp_path):
    response = httpx.Response(
        200,
        headers={"Content-Type": "application/pdf", "X-Large": "x" * 64, "Cookie": "session=COOKIESECRET", "Authorization": "Bearer AUTHSECRET"},
        content=PDF,
    )
    with pytest.raises(PaperDownloadError) as error:
        run_download(tmp_path, lambda _request: response, max_header_bytes=32)
    assert error.value.code == DOWNLOAD_BLOCKED
    assert "COOKIESECRET" not in str(error.value)
    assert "AUTHSECRET" not in str(error.value)
    assert not list(tmp_path.rglob("*"))


def test_stream_interruption_maps_to_stable_error_and_cleans_partial(tmp_path):
    response = httpx.Response(200, headers={"Content-Type": "application/pdf"}, stream=BrokenPdfStream())
    with pytest.raises(PaperDownloadError) as error:
        run_download(tmp_path, lambda _request: response)
    assert error.value.code == PDF_NOT_FOUND
    assert "connection dropped" not in str(error.value)
    assert not list(tmp_path.rglob("*"))


@pytest.mark.parametrize("content", [b"%PDF-1.7\ntruncated body", b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\nstartxref\n0\n%%EOF"])
def test_truncated_or_corrupt_pdf_is_invalid_and_cleaned(tmp_path, content):
    with pytest.raises(PaperDownloadError) as error:
        run_download(tmp_path, lambda _request, content=content: httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=content), validate_pdf_pages=True)
    assert error.value.code == INVALID_PDF
    assert not list(tmp_path.rglob("*"))


def test_encrypted_pdf_is_rejected_without_exposing_password(tmp_path):
    with pytest.raises(PaperDownloadError) as error:
        run_download(tmp_path, lambda _request: httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=encrypted_pdf()), validate_pdf_pages=True)
    assert error.value.code == INVALID_PDF
    assert "password" not in str(error.value).lower()
    assert "owner" not in str(error.value).lower()
    assert not list(tmp_path.rglob("*"))

def test_timeout_maps_to_stable_error(tmp_path):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(PaperDownloadError) as error:
        run_download(tmp_path, handler)
    assert error.value.code == DOWNLOAD_TIMEOUT
    assert not list(tmp_path.rglob("*"))


def test_page_validator_failure_removes_renamed_file(tmp_path):
    with pytest.raises(PaperDownloadError) as error:
        run_download(tmp_path, lambda _request: httpx.Response(200, content=PDF), pdf_page_validator=lambda _path: 0)
    assert error.value.code == INVALID_PDF
    assert not list(tmp_path.rglob("*"))
