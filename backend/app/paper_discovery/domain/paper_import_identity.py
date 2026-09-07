"""Pure identity and file-name helpers for security-paper imports.

This module deliberately has no filesystem, network, database, or framework
dependencies.  Callers must pass the server-side candidate snapshot and the
server-side conference short name; client supplied URLs and display metadata
are never consulted here.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi, normalize_title

DEFAULT_FILENAME_MAX_LENGTH = 180
DEFAULT_SUFFIX = ".pdf"
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_DBLP_URL = re.compile(r"^[a-z][a-z0-9+.-]*://|^//", re.IGNORECASE)


def _text(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def canonical_doi(value: Any) -> str:
    """Return one DOI representation, accepting common DOI URL prefixes.

    Non-DOI URLs are discarded.  This is important because an article or PDF
    URL is an untrusted locator, not a paper identity.
    """
    value = _text(value).strip("<>\u200b\ufeff")
    value = _DOI_PREFIX.sub("", value).strip()
    # Existing normalization supplies case-folding and citation punctuation
    # handling used by the discovery store.
    doi = normalize_doi(value).strip("<>\u200b\ufeff \t\r\n.,;:)]}")
    if not doi.casefold().startswith("10.") or "/" not in doi:
        return ""
    if any(char.isspace() for char in doi) or "://" in doi:
        return ""
    return doi.casefold()


def canonical_dblp_key(value: Any) -> str:
    """Normalize a DBLP key without treating arbitrary URLs as keys."""
    key = _text(value).strip("<>\u200b\ufeff \t\r\n.,;:)]}")
    if not key or _DBLP_URL.search(key) or "\\" in key or any(char.isspace() for char in key):
        return ""
    return key.casefold()


def _canonical_year(value: Any) -> str:
    if isinstance(value, bool):
        return ""
    year = _text(value)
    if not re.fullmatch(r"\d{4}", year):
        return ""
    return year


def _canonical_conference_id(value: Any) -> str:
    conference = _text(value)
    if not conference or _DBLP_URL.search(conference) or "\\" in conference:
        return ""
    return normalize_title(conference)


@dataclass(frozen=True)
class PaperImportIdentity:
    """Canonical identity fields and all keys usable for duplicate checks."""

    doi: str = ""
    dblp_key: str = ""
    normalized_title: str = ""
    year: str = ""
    conference_id: str = ""

    @property
    def keys(self) -> tuple[str, ...]:
        keys: list[str] = []
        if self.doi:
            keys.append(f"doi:{self.doi}")
        if self.dblp_key and self.year and self.conference_id:
            keys.append(f"key:{self.dblp_key}:{self.year}:{self.conference_id}")
        if self.normalized_title and self.year and self.conference_id:
            keys.append(f"title:{self.normalized_title}:{self.year}:{self.conference_id}")
        return tuple(keys)

    @property
    def primary_key(self) -> str:
        """Return the strongest available key for stable disambiguation."""
        return self.keys[0] if self.keys else ""


def build_paper_identity(
    *,
    doi: Any = None,
    dblp_key: Any = None,
    title: Any = None,
    year: Any = None,
    conference_id: Any = None,
    # Deliberately accepted only for API compatibility; never used.  A
    # display name is client-controlled and is not a stable identity field.
    conference_name: Any = None,
) -> PaperImportIdentity:
    del conference_name
    return PaperImportIdentity(
        doi=canonical_doi(doi),
        dblp_key=canonical_dblp_key(dblp_key),
        normalized_title=normalize_title(_text(title)),
        year=_canonical_year(year),
        conference_id=_canonical_conference_id(conference_id),
    )


def paper_identity_keys(
    *,
    doi: Any = None,
    dblp_key: Any = None,
    title: Any = None,
    year: Any = None,
    conference: Any = None,
    conference_id: Any = None,
    conference_name: Any = None,
) -> set[str]:
    """Return DOI, DBLP-scoped, and title/year/conference duplicate keys.

    ``conference`` is an alias for the server-side conference ID.  The
    ``conference_name`` parameter is intentionally ignored.
    """
    del conference_name
    identity = build_paper_identity(
        doi=doi,
        dblp_key=dblp_key,
        title=title,
        year=year,
        conference_id=conference_id if conference_id is not None else conference,
    )
    return set(identity.keys)


def identity_keys_for_candidate(candidate: Any) -> set[str]:
    """Extract identity fields from a server-side candidate snapshot only."""
    if isinstance(candidate, Mapping):
        get = candidate.get
    else:
        get = lambda name, default=None: getattr(candidate, name, default)
    return paper_identity_keys(
        doi=get("doi"),
        dblp_key=get("dblp_key") or get("dblp"),
        title=get("title"),
        year=get("year"),
        conference_id=get("conference_id") or get("conference"),
    )


def _candidate_identity(candidate: Any) -> PaperImportIdentity:
    if isinstance(candidate, Mapping):
        get = candidate.get
    else:
        get = lambda name, default=None: getattr(candidate, name, default)
    return build_paper_identity(
        doi=get("doi"),
        dblp_key=get("dblp_key") or get("dblp"),
        title=get("title"),
        year=get("year"),
        conference_id=get("conference_id") or get("conference"),
    )


def _identities_match(left: PaperImportIdentity, right: PaperImportIdentity) -> bool:
    """Match strong identifiers before using the title fallback.

    A display title is not sufficient to collapse two records that carry
    different DOI or DBLP identities.  It is only a fallback when at least
    one side lacks a stronger identity, or when both strong identities agree.
    """
    # DOI is the strongest identity.  When only one side has a DOI, do not
    # fall back to title/year/conference: a sparse snapshot must not consume
    # a distinct paper whose DOI is merely missing on that side.  DBLP can
    # still establish identity when both sides carry the same scoped key.
    if left.doi or right.doi:
        if left.doi and right.doi:
            return left.doi == right.doi
        return (
            left.dblp_key and right.dblp_key
            and left.dblp_key == right.dblp_key
            and left.year == right.year
            and left.conference_id == right.conference_id
        )
    if left.dblp_key and right.dblp_key:
        return (
            left.dblp_key == right.dblp_key
            and left.year == right.year
            and left.conference_id == right.conference_id
        )
    title_overlap = bool(
        left.normalized_title
        and left.normalized_title == right.normalized_title
        and left.year
        and left.year == right.year
        and left.conference_id
        and left.conference_id == right.conference_id
    )
    # Title fallback is reserved for records with no stronger identity on
    # either side.
    return title_overlap


def deduplicate_candidates(candidates: Iterable[Any]) -> list[Any]:
    """Keep the first candidate for any shared canonical identity key."""
    identities: list[PaperImportIdentity] = []
    unique: list[Any] = []
    for candidate in candidates:
        identity = _candidate_identity(candidate)
        if identity.keys and any(_identities_match(identity, previous) for previous in identities):
            continue
        if identity.keys:
            identities.append(identity)
        unique.append(candidate)
    return unique


def _safe_component(value: Any, fallback: str) -> str:
    text = unicodedata.normalize("NFKC", _text(value))
    # Remove controls and convert all path/filename separators and punctuation
    # runs to one ASCII separator.  Unicode letters/numbers remain readable.
    chars: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("C"):
            chars.append("-")
        elif char.isalnum():
            chars.append(char)
        else:
            chars.append("-")
    cleaned = re.sub(r"-+", "-", "".join(chars)).strip("- .")
    if not cleaned:
        cleaned = fallback
    if cleaned.casefold() in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned


def _year_component(year: Any) -> str:
    return _canonical_year(year) or "UnknownYear"


def build_paper_filename(
    year: Any,
    conference_short_name: Any,
    title: Any,
    *,
    max_length: int = DEFAULT_FILENAME_MAX_LENGTH,
    suffix: str = DEFAULT_SUFFIX,
) -> str:
    """Build ``year-conference-title.pdf`` using trusted conference input.

    Only the title is truncated for ordinary overlong names.  A malformed
    tiny limit that cannot hold the fixed year/conference prefix is rejected
    instead of silently changing server-controlled identity fields.
    """
    if isinstance(max_length, bool) or not isinstance(max_length, int) or max_length < 1:
        raise ValueError("max_length must be a positive integer")
    suffix = _text(suffix) or DEFAULT_SUFFIX
    if not suffix.startswith(".") or "/" in suffix or "\\" in suffix:
        raise ValueError("suffix must be a simple extension")
    year_part = _year_component(year)
    conference_part = _safe_component(conference_short_name, "Conference")
    title_part = _safe_component(title, "Untitled")
    prefix = f"{year_part}-{conference_part}-"
    available_title = max_length - len(prefix) - len(suffix)
    if available_title < 1:
        raise ValueError("max_length is too small for year and conference")
    title_part = title_part[:available_title].rstrip("- .") or "Untitled"
    # A title made entirely of separators may need the fallback after slicing.
    result = f"{prefix}{title_part}{suffix}"
    if len(result) > max_length:
        result = f"{prefix}{title_part[: max(1, available_title - (len(result) - max_length))].rstrip('- .') or 'Untitled'}{suffix}"
    return result


def unique_paper_filename(
    year: Any,
    conference_short_name: Any,
    title: Any,
    *,
    identity: PaperImportIdentity | Iterable[str] | str | None = None,
    existing_names: Iterable[str] = (),
    max_length: int = DEFAULT_FILENAME_MAX_LENGTH,
) -> str:
    """Return a readable name and add a stable identity suffix on collision."""
    base = build_paper_filename(year, conference_short_name, title, max_length=max_length)
    existing = {str(name).casefold() for name in existing_names}
    if base.casefold() not in existing:
        return base
    if isinstance(identity, PaperImportIdentity):
        identity_text = "|".join(identity.keys)
    elif isinstance(identity, str):
        identity_text = identity
    else:
        identity_text = "|".join(str(item) for item in (identity or ()))
    if not identity_text:
        identity_text = f"{_year_component(year)}|{_text(conference_short_name)}|{_text(title)}"
    token = hashlib.sha256(identity_text.encode("utf-8")).hexdigest()[:10]
    suffix = f"-{token}.pdf"
    stem = base[:-4]
    available_stem = max_length - len(suffix)
    if available_stem < 1:
        raise ValueError("max_length is too small for disambiguated filename")
    candidate = f"{stem[:available_stem].rstrip('- .')}{suffix}"
    if candidate.casefold() not in existing:
        return candidate
    # Same identity and same readable name is the same physical target; when
    # a caller has a different collision policy, retain deterministic suffixes.
    for counter in range(2, 1000):
        counter_suffix = f"-{token}-{counter}.pdf"
        candidate = f"{stem[: max_length - len(counter_suffix)].rstrip('- .')}{counter_suffix}"
        if candidate.casefold() not in existing:
            return candidate
    raise ValueError("unable to allocate a unique filename")


def filename_for_candidate(
    candidate: Any,
    conference_short_name: Any,
    *,
    existing_names: Iterable[str] = (),
    max_length: int = DEFAULT_FILENAME_MAX_LENGTH,
) -> str:
    """Name a server-side candidate using an explicit server conference name."""
    identity = _candidate_identity(candidate)
    if isinstance(candidate, Mapping):
        get = candidate.get
    else:
        get = lambda name, default=None: getattr(candidate, name, default)
    return unique_paper_filename(
        get("year"),
        conference_short_name,
        get("title"),
        identity=identity,
        existing_names=existing_names,
        max_length=max_length,
    )


# Small aliases make the service easy to adopt from import orchestration code.
canonical_filename = build_paper_filename
normalize_filename_component = _safe_component
make_paper_filename = build_paper_filename
paper_filename_for_candidate = filename_for_candidate
deduplicate_paper_candidates = deduplicate_candidates
