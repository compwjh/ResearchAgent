"""Shared canonicalization rules for paper identity and comparison."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_doi(value: Any) -> str:
    """Return a DOI without URL/prefix decoration or citation punctuation."""
    doi = str(value or "").strip().casefold()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:\s*", "", doi)
    return doi.strip().rstrip(".").strip()


def normalize_title(value: Any) -> str:
    """Normalize case, accents and punctuation for identity/comparison."""
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^\w]+", "", text, flags=re.UNICODE)
