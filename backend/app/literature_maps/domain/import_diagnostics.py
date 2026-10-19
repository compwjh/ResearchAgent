"""Stable, redacted diagnostics for the map paper-import boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

RESOLVER_DIAGNOSTIC_CODES = frozenset({
    "ARXIV_UNAVAILABLE",
    "ARXIV_RATE_LIMITED",
    "ARXIV_HTTP_ERROR",
    "ARXIV_INVALID_RESPONSE",
    "ARXIV_MATCH_UNCERTAIN",
    "ARXIV_IDENTITY_CONFLICT",
    "SEMANTIC_SCHOLAR_IDENTIFIER_REQUIRED",
    "SEMANTIC_SCHOLAR_UNAVAILABLE",
    "SEMANTIC_SCHOLAR_RATE_LIMITED",
    "SEMANTIC_SCHOLAR_HTTP_ERROR",
    "SEMANTIC_SCHOLAR_INVALID_RESPONSE",
    "SEMANTIC_SCHOLAR_AUTH_FAILED",
    "SEMANTIC_SCHOLAR_NOT_FOUND",
    "SEMANTIC_SCHOLAR_NO_OPEN_PDF",
    "SEMANTIC_SCHOLAR_MATCH_UNCERTAIN",
    "SEMANTIC_SCHOLAR_UNSUPPORTED_PDF_HOST",
    "OA_IDENTITY_CONFLICT",
})

RETRYABLE_RESOLVER_CODES = frozenset({
    "ARXIV_UNAVAILABLE",
    "ARXIV_RATE_LIMITED",
    "SEMANTIC_SCHOLAR_UNAVAILABLE",
    "SEMANTIC_SCHOLAR_RATE_LIMITED",
})

# These outcomes mean that no safe PDF candidate was established.  Provider
# transport/authentication failures remain the primary error so callers can
# distinguish a recoverable resolver outage from a genuine no-OA result.
NO_PDF_CANDIDATE_CODES = frozenset({
    "ARXIV_MATCH_UNCERTAIN",
    "ARXIV_IDENTITY_CONFLICT",
    "SEMANTIC_SCHOLAR_IDENTIFIER_REQUIRED",
    "SEMANTIC_SCHOLAR_NO_OPEN_PDF",
    "SEMANTIC_SCHOLAR_MATCH_UNCERTAIN",
    "SEMANTIC_SCHOLAR_UNSUPPORTED_PDF_HOST",
    "OA_IDENTITY_CONFLICT",
})

SAFE_IMPORT_ERROR_CODES = frozenset({
    "PDF_NOT_FOUND",
    "IMPORT_IDENTITY_CONFLICT",
    "DOWNLOAD_BLOCKED",
    "DOWNLOAD_TIMEOUT",
    "PDF_TOO_LARGE",
    "INVALID_PDF",
    "LOGIN_REQUIRED",
    "BROWSER_SESSION_REQUIRED",
    "BROWSER_SESSION_EXPIRED",
    "KB_IMPORT_FAILED",
    "KB_INDEX_FAILED",
    "KB_STORAGE_LOCKED",
    "DUPLICATE_IMPORT",
    "PAPER_ALREADY_EXISTS",
})


def safe_resolver_codes(source: Mapping[str, Any] | None) -> list[str]:
    """Return only fixed resolver codes, preserving provider order."""
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
        if code in RESOLVER_DIAGNOSTIC_CODES
    ))


def resolver_failure(
    codes: list[str] | tuple[str, ...],
    *,
    retryable: bool = False,
) -> dict[str, Any]:
    """Build a stable resolver failure without exposing provider payloads."""
    safe_codes = [code for code in codes if code in RESOLVER_DIAGNOSTIC_CODES]
    retryable = resolver_retryable(safe_codes, explicit=retryable)
    provider_errors = [code for code in safe_codes if code not in NO_PDF_CANDIDATE_CODES]
    primary = provider_errors[-1] if provider_errors else "PDF_NOT_FOUND"
    return {
        "error_code": primary,
        "resolver_code": safe_codes[-1] if safe_codes else "PDF_NOT_FOUND",
        "resolver_codes": safe_codes,
        "retryable": retryable,
    }


def resolver_retryable(codes: list[str] | tuple[str, ...], *, explicit: bool = False) -> bool:
    """Preserve adapter retryability while recognizing fixed transient codes."""
    return bool(explicit) or any(code in RETRYABLE_RESOLVER_CODES for code in codes)


def normalize_import_diagnostics(import_result: Mapping[str, Any]) -> dict[str, Any] | None:
    """Project an import result into the persisted, redacted diagnostics shape."""
    status = str(import_result.get("download_status") or import_result.get("status") or "").casefold()
    if status in {"indexed", "completed"}:
        return None
    diagnostics: dict[str, Any] = {}
    error_code = import_result.get("error_code")
    if isinstance(error_code, str) and (
        error_code in SAFE_IMPORT_ERROR_CODES or error_code in RESOLVER_DIAGNOSTIC_CODES
    ):
        diagnostics["error_code"] = error_code
    resolver_codes = safe_resolver_codes(import_result)
    if resolver_codes:
        diagnostics["resolver_code"] = resolver_codes[-1]
        diagnostics["resolver_codes"] = resolver_codes
    if resolver_retryable(resolver_codes, explicit=bool(import_result.get("retryable"))):
        diagnostics["retryable"] = True
    return diagnostics or None


__all__ = [
    "NO_PDF_CANDIDATE_CODES",
    "RESOLVER_DIAGNOSTIC_CODES",
    "RETRYABLE_RESOLVER_CODES",
    "normalize_import_diagnostics",
    "resolver_failure",
    "resolver_retryable",
    "safe_resolver_codes",
]
