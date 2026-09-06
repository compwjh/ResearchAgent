import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator, Optional, Tuple
from urllib.parse import urljoin

import httpx

from backend.app.platform.settings.settings_repository import ArticleSettings
from backend.app.domain.article import ArticleCandidate


class _PdfLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href", "")
        if href and ("pdf" in href.lower() or "download" in href.lower()):
            self.links.append(href)


def safe_filename(title: str, suffix: str = ".pdf") -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff .-]+", "_", title).strip(" .") or "article"
    return f"{cleaned[:180]}{suffix}"


def probe_pdf_url(candidate: ArticleCandidate, settings: ArticleSettings) -> Tuple[str, str]:
    url = candidate.pdf_url or candidate.article_url or (settings.article_download_urls[0] if settings.article_download_urls else None)
    if not url:
        return "not_found", ""
    try:
        with httpx.stream("GET", url, headers={"Range": "bytes=0-1023"}, timeout=settings.article_pdf_probe_timeout_seconds, follow_redirects=True, trust_env=False) as response:
            if response.status_code in (401, 403):
                return "login_required", url
            if response.status_code == 429:
                return "rate_limited", url
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            chunks = []
            for chunk in response.iter_bytes():
                chunks.append(chunk)
                if sum(len(item) for item in chunks) >= 8192:
                    break
            body = b"".join(chunks)
            prefix = body[:5]
            if prefix == b"%PDF-" or "application/pdf" in content_type:
                return "public_pdf", str(response.url)
            if "text/html" in content_type or body.lstrip().startswith(b"<"):
                parser = _PdfLinkParser()
                parser.feed(body.decode("utf-8", errors="ignore"))
                for link in parser.links:
                    linked_url = urljoin(str(response.url), link)
                    if linked_url == url:
                        continue
                    linked_candidate = ArticleCandidate(candidate.candidate_id, candidate.title, pdf_url=linked_url)
                    status, resolved_url = probe_pdf_url(linked_candidate, settings)
                    if status == "public_pdf":
                        return status, resolved_url
                    if status == "login_required":
                        return status, resolved_url
            return "invalid", str(response.url)
    except httpx.HTTPStatusError as error:
        if error.response.status_code in (401, 403):
            return "login_required", url
        return "not_found", url
    except httpx.HTTPError:
        return "not_found", url


def download_article(candidate: ArticleCandidate, settings: ArticleSettings, extra_headers: Optional[dict] = None) -> Iterator[dict]:
    download_url = candidate.pdf_url or (settings.article_download_urls[0] if settings.article_download_urls else None)
    if not download_url:
        raise ValueError("候选文章没有可下载的 PDF 地址")
    output_dir = Path(settings.article_download_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / safe_filename(candidate.title)
    max_bytes = settings.article_max_file_size_mb * 1024 * 1024
    digest = hashlib.sha256()
    total = 0
    request_headers = dict(extra_headers or {})
    with httpx.stream("GET", download_url, headers=request_headers, timeout=settings.article_request_timeout_seconds, follow_redirects=True, trust_env=False) as response:
        if response.status_code in (401, 403):
            candidate.requires_login = True
            raise PermissionError("下载来源需要登录")
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        content_length = int(response.headers.get("content-length", "0") or 0)
        if content_length > max_bytes:
            raise ValueError("文件超过大小限制")
        with output_path.open("wb") as file:
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    output_path.unlink(missing_ok=True)
                    raise ValueError("文件超过大小限制")
                digest.update(chunk)
                file.write(chunk)
    with output_path.open("rb") as file:
        if file.read(5) != b"%PDF-":
            output_path.unlink(missing_ok=True)
            raise ValueError(f"下载内容不是 PDF（{content_type or '未知类型'}）")
    yield {"type": "result", "file_path": str(output_path), "file_size": total, "checksum": digest.hexdigest()}
