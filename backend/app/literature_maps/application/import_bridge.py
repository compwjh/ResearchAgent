"""Narrow bridge to the existing paper import chain.

The map domain only supplies a node snapshot and a server-side source URL.
This adapter deliberately has no downloader of its own: production wiring
must provide the existing paper-discovery/KB import callable, while tests can
inject a deterministic callable without touching files or external services.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

from backend.app.literature_maps.domain.models import MapPaper
from backend.app.paper_discovery.application.paper_import import (
    KB_IMPORT_FAILED,
    PaperImportError,
    safe_import_error_code,
)
from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi
from backend.app.paper_discovery.infrastructure.paper_download import (
    DOWNLOAD_TIMEOUT,
    LOGIN_REQUIRED,
    PDF_NOT_FOUND,
    PaperDownloadError,
)


class LiteratureMapImportBridge:
    """Adapt one frozen map node to the existing paper-import boundary.

    The bridge receives the source selected by the map service, never a URL
    from the HTTP request.  It does not resolve, download, or index anything
    itself; the injected callable remains the single production import path.
    ``store`` is optional for small unit seams, but the composition root wires
    it so the real document handle is durable on the map node.
    """

    def __init__(
        self,
        importer: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
        *,
        store: Any | None = None,
        owner_id: str | None = None,
        source_resolver: Callable[[MapPaper], Mapping[str, Any] | None] | None = None,
        oa_resolver: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
    ) -> None:
        self.importer = importer
        self.store = store
        self.owner_id = owner_id
        self.source_resolver = source_resolver
        self.oa_resolver = oa_resolver

    def import_node(self, node: MapPaper, source_url: str) -> Mapping[str, Any]:
        if self.importer is None:
            raise RuntimeError("IMPORT_BRIDGE_UNAVAILABLE")
        if not _is_safe_server_source(node, source_url):
            raise ValueError("IMPORT_URL_UNSAFE")
        source = self._resolve_source(node)
        if node.catalog_paper_id and not source.get("catalog_paper_id"):
            source = {**source, "catalog_paper_id": node.catalog_paper_id}
        selected_url = _source_pdf_url(source)
        if not selected_url:
            result = _failure_result(source.get("error_code") or PDF_NOT_FOUND, source)
            return self._persist(node, result)
        if _identity_conflict(node, source):
            result = _failure_result("IMPORT_IDENTITY_CONFLICT", source)
            return self._persist(node, result)
        if _is_semantic_scholar_landing(node, selected_url):
            result = _failure_result(PDF_NOT_FOUND, source)
            return self._persist(node, result)
        if not _is_safe_import_source(selected_url):
            raise ValueError("IMPORT_URL_UNSAFE")
        snapshot = node.to_dict()
        # Keep the frozen node source in the metadata snapshot.  The selected
        # server-side PDF is a separate field and is the only URL sent to the
        # existing downloader/import chain.
        snapshot["source_url"] = node.source_url
        snapshot["pdf_url"] = selected_url
        for key in ("catalog_paper_id", "doi", "arxiv_id", "source_kind"):
            if source.get(key) is not None:
                snapshot[key] = source[key]
        try:
            imported = self.importer(snapshot, selected_url)
        except (PaperDownloadError, PaperImportError) as error:
            result = _failure_result(error.code, source, retryable=_retryable_error(error))
        else:
            result = _normalize_import_result(imported, source)
        return self._persist(node, result)

    def _resolve_source(self, node: MapPaper) -> Mapping[str, Any]:
        if self.source_resolver is None:
            # Unit seams may provide a direct PDF URL.  A map node's S2 page
            # is never accepted as a PDF just because it is https.
            if _looks_like_pdf(node.source_url):
                return {"pdf_url": node.source_url}
            return {"error_code": PDF_NOT_FOUND}
        resolved = self.source_resolver(node)
        source = dict(resolved) if isinstance(resolved, Mapping) else {}
        if _source_pdf_url(source):
            return source
        if self.oa_resolver is not None:
            fallback = self.oa_resolver(node.to_dict())
            if isinstance(fallback, Mapping):
                source.update(dict(fallback))
        source.setdefault("error_code", PDF_NOT_FOUND)
        return source

    def _persist(self, node: MapPaper, result: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.store is not None and self.owner_id is not None:
            try:
                self.store.update_node_import_result(
                    node.map_id,
                    node.node_id,
                    self.owner_id,
                    import_result=result,
                )
            except Exception as error:  # store details never cross the API boundary
                raise RuntimeError("MAP_IMPORT_STATE_UNAVAILABLE") from error
        return result


_ERROR_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_RESOLVER_DIAGNOSTIC_CODES = frozenset({
    "ARXIV_UNAVAILABLE",
    "ARXIV_MATCH_UNCERTAIN",
    "ARXIV_IDENTITY_CONFLICT",
    "SEMANTIC_SCHOLAR_UNAVAILABLE",
    "SEMANTIC_SCHOLAR_NO_OPEN_PDF",
    "SEMANTIC_SCHOLAR_MATCH_UNCERTAIN",
    "SEMANTIC_SCHOLAR_UNSUPPORTED_PDF_HOST",
    "SEMANTIC_SCHOLAR_AUTH_FAILED",
    "SEMANTIC_SCHOLAR_NOT_FOUND",
    "SEMANTIC_SCHOLAR_HTTP_ERROR",
    "SEMANTIC_SCHOLAR_INVALID_RESPONSE",
    "OA_IDENTITY_CONFLICT",
})
_SAFE_STATUS = frozenset({
    "queued", "importing", "downloading", "validating", "indexing",
    "indexed", "completed", "pending", "partial", "waiting_login",
    "loginfailed", "failed",
})

_LOGIN_ERROR_CODES = frozenset({"LOGIN_REQUIRED", "BROWSER_SESSION_REQUIRED", "BROWSER_SESSION_EXPIRED"})


def _is_safe_server_source(node: MapPaper, source_url: str) -> bool:
    """Require the action URL to be the server-frozen node source."""
    if not node.source_url or source_url != node.source_url:
        return False
    return _is_safe_import_source(source_url)


def _is_safe_import_source(source_url: str) -> bool:
    """Perform only non-network preflight; downloader owns DNS/redirect checks."""
    try:
        parsed = urlsplit(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.username or parsed.password or parsed.fragment:
            return False
        hostname = parsed.hostname.casefold().rstrip(".")
        if hostname in {"localhost", "localhost.localdomain"}:
            return False
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address is not None and (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_unspecified
            or address.is_multicast
        ):
            return False
    except ValueError:
        return False
    return True


def _normalize_import_result(result: Any, source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Project existing importer DTOs to the stable map import handle."""
    if hasattr(result, "to_dict"):
        raw = result.to_dict()
    elif isinstance(result, Mapping):
        raw = dict(result)
    else:
        raw = {
            name: getattr(result, name, None)
            for name in ("paper_id", "document_id", "stored_name", "status", "error_code", "existing")
        }
    raw_status = str(raw.get("status") or raw.get("download_status") or "failed").casefold()
    status = raw_status if raw_status in _SAFE_STATUS else "failed"
    document_id = raw.get("document_id") or raw.get("paper_id")
    if document_id is not None:
        document_id = str(document_id)[:200] or None
    error_code = raw.get("error_code")
    if not isinstance(error_code, str) or not _ERROR_CODE_RE.fullmatch(error_code):
        error_code = None if not error_code else "IMPORT_FAILED"
    catalog_paper_id = source.get("catalog_paper_id") if isinstance(source, Mapping) else None
    if catalog_paper_id is not None:
        catalog_paper_id = str(catalog_paper_id)[:200] or None
    normalized = {
        "paper_id": document_id,
        "document_id": document_id,
        "stored_name": str(raw.get("stored_name"))[:255] if raw.get("stored_name") else None,
        "status": status,
        "download_status": status,
        "error_code": error_code,
        "existing": bool(raw.get("existing", False)),
        "retryable": bool(raw.get("retryable", False)),
        "catalog_paper_id": catalog_paper_id,
    }
    resolver_codes = _safe_resolver_codes(source)
    if resolver_codes:
        normalized["resolver_code"] = resolver_codes[-1]
        normalized["resolver_codes"] = resolver_codes
    return normalized


def _safe_resolver_codes(source: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(source, Mapping):
        return []
    values: list[Any] = []
    raw_codes = source.get("resolver_codes")
    if isinstance(raw_codes, (list, tuple)):
        values.extend(raw_codes)
    raw_code = source.get("resolver_code")
    if raw_code is not None:
        values.append(raw_code)
    return list(dict.fromkeys(
        code for code in (str(value).strip() for value in values)
        if code in _RESOLVER_DIAGNOSTIC_CODES
    ))


def _source_pdf_url(source: Mapping[str, Any]) -> str | None:
    for key in ("pdf_url", "official_pdf_url", "prepublication_pdf_url"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _looks_like_pdf(source_url: str | None) -> bool:
    if not isinstance(source_url, str) or not source_url.strip():
        return False
    try:
        parsed = urlsplit(source_url)
    except ValueError:
        return False
    return parsed.path.casefold().endswith(".pdf")


def _identity_conflict(node: MapPaper, source: Mapping[str, Any]) -> bool:
    external = {str(key).casefold(): str(value).strip() for key, value in node.external_ids.items() if value}
    catalog_id = str(source.get("catalog_paper_id") or "").strip()
    if catalog_id and catalog_id == external.get("semantic_scholar", ""):
        # A Semantic Scholar provider id is not a catalog_paper_id.
        return True
    if node.catalog_paper_id and catalog_id and node.catalog_paper_id != catalog_id:
        return True
    doi = normalize_doi(source.get("doi")) or ""
    external_doi = normalize_doi(external.get("doi")) or ""
    if doi and external_doi and doi != external_doi:
        return True
    arxiv = _normalize_arxiv(source.get("arxiv_id"))
    external_arxiv = _normalize_arxiv(external.get("arxiv"))
    if arxiv and external_arxiv and arxiv != external_arxiv:
        return True
    semantic_id = str(source.get("semantic_scholar_id") or "").strip()
    return bool(semantic_id and external.get("semantic_scholar") and semantic_id != external["semantic_scholar"])


def _is_semantic_scholar_landing(node: MapPaper, selected_url: str) -> bool:
    if selected_url == node.source_url:
        return not _looks_like_pdf(selected_url)
    try:
        hostname = (urlsplit(selected_url).hostname or "").casefold().rstrip(".")
    except ValueError:
        return True
    return hostname in {"semanticscholar.org", "www.semanticscholar.org"}


def _normalize_arxiv(value: object) -> str:
    raw = str(value or "").strip().casefold()
    if raw.startswith("http://") or raw.startswith("https://"):
        raw = raw.rstrip("/").rsplit("/", 1)[-1]
    return raw.removeprefix("arxiv:")


def _retryable_error(error: PaperDownloadError | PaperImportError) -> bool:
    return bool(getattr(error, "retryable", False)) or error.code in {
        LOGIN_REQUIRED,
        "BROWSER_SESSION_REQUIRED",
        "BROWSER_SESSION_EXPIRED",
        DOWNLOAD_TIMEOUT,
    }


def _failure_result(
    error_code: object,
    source: Mapping[str, Any] | None = None,
    *,
    retryable: bool = False,
) -> dict[str, Any]:
    code = str(error_code or PDF_NOT_FOUND)
    if code not in {"IMPORT_IDENTITY_CONFLICT", PDF_NOT_FOUND}:
        code = safe_import_error_code(code, KB_IMPORT_FAILED)
    status = "waiting_login" if code in _LOGIN_ERROR_CODES else "failed"
    result = _normalize_import_result(
        {"status": status, "error_code": code, "retryable": retryable},
        source,
    )
    result["retryable"] = retryable or status == "waiting_login"
    return result


__all__ = ["LiteratureMapImportBridge"]
