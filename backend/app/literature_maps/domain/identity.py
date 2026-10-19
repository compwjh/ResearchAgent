"""Deterministic external identity rules used by map ingestion."""

from __future__ import annotations

import re
from typing import Any, Mapping

from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi

_ARXIV_PREFIX = re.compile(r"^arxiv:", re.IGNORECASE)


def normalize_external_id(kind: str, value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if kind == "doi":
        return normalize_doi(raw) or None
    if kind == "arxiv":
        raw = _ARXIV_PREFIX.sub("", raw).strip()
        return raw.casefold() or None
    if kind == "semantic_scholar":
        return raw[:200] or None
    return raw[:200] or None


def canonical_external_ids(value: Mapping[str, Any] | Any) -> dict[str, str]:
    """Return only allowlisted provider identities in stable wire-key form."""
    if not isinstance(value, Mapping):
        return {}
    external = value.get("externalIds") if isinstance(value.get("externalIds"), Mapping) else value
    result: dict[str, str] = {}
    candidates = {
        "semantic_scholar": value.get("paperId") if isinstance(value, Mapping) else None,
        "doi": external.get("DOI") if isinstance(external, Mapping) else None,
        "arxiv": external.get("ArXiv") if isinstance(external, Mapping) else None,
    }
    for kind, raw in candidates.items():
        normalized = normalize_external_id(kind, raw)
        if normalized:
            result[kind] = normalized
    # Already-normalized maps are accepted for domain objects and test seams.
    for kind in ("semantic_scholar", "doi", "arxiv"):
        normalized = normalize_external_id(kind, value.get(kind))
        if normalized:
            result[kind] = normalized
    return result


def deterministic_identity_key(external_ids: Mapping[str, Any] | Any) -> str | None:
    ids = canonical_external_ids(external_ids)
    for kind in ("doi", "arxiv", "semantic_scholar"):
        if ids.get(kind):
            return f"{kind}:{ids[kind]}"
    return None
