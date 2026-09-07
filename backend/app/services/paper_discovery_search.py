"""Service-layer orchestration for DBLP recall and optional OpenAlex enrichment."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Mapping, Optional
from uuid import uuid4

from backend.app.domain.paper_discovery import ConferenceSource, PaperCandidate, SearchSession
from backend.app.platform.settings.settings_repository import (
    ArticleSettings,
    load_article_settings,
)
from backend.app.services.dblp_publication_source import DBLPPublicationSource
from backend.app.services.paper_discovery_normalization import normalize_doi, normalize_title
from backend.app.services.paper_discovery_store import PaperDiscoveryStore
from backend.app.services.usenix_publication_source import UsenixAcceptedSource


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normal_title(value: Any) -> str:
    return normalize_title(value)


def _normal_doi(value: Any) -> str:
    return normalize_doi(value)


def _normal_author_set(authors: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({key for value in authors if (key := _normal_title(value))}))


_STAGE_PRIORITY = {"prepublication": 0, "accepted": 1, "published": 2}
_SOURCE_PRIORITY = {"arxiv": 0, "usenix_accepted": 1, "dblp": 2}


def _warning(code: str, source: str, message: str) -> Dict[str, str]:
    return {"code": code, "source": source, "message": message}


class PaperDiscoverySearchError(ValueError):
    """A client-correctable search input error with a stable error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.error_code = code


@dataclass
class SearchResult:
    session: SearchSession
    candidates: List[PaperCandidate] = field(default_factory=list)
    warnings: List[Dict[str, str]] = field(default_factory=list)
    error_code: Optional[str] = None


class PaperDiscoverySearchService:
    """Run all external calls first, then persist one complete search snapshot."""

    def __init__(
        self,
        *,
        dblp_source: Optional[DBLPPublicationSource] = None,
        accepted_source: Optional[UsenixAcceptedSource] = None,
        openalex_enricher: Any = None,
        store: Optional[PaperDiscoveryStore] = None,
        settings: Optional[ArticleSettings] = None,
        max_limit: Optional[int] = None,
        max_years: int = 10,
        default_years: Optional[int] = None,
        search_ttl_seconds: Optional[int] = None,
    ):
        self.dblp_source = dblp_source or DBLPPublicationSource()
        self.accepted_source = accepted_source or UsenixAcceptedSource()
        self.openalex_enricher = openalex_enricher
        self.store = store or PaperDiscoveryStore()
        self.settings = settings or load_article_settings()
        self.default_limit = getattr(self.settings, "paper_discovery_search_limit", 20)
        configured_max_limit = getattr(self.settings, "paper_discovery_max_search_limit", 100)
        self.max_limit = max_limit if max_limit is not None else configured_max_limit
        self.max_years = max_years
        self.default_years = default_years if default_years is not None else getattr(self.settings, "paper_discovery_default_years", 5)
        configured_ttl = getattr(self.settings, "paper_discovery_search_ttl_seconds", 86400)
        self.search_ttl_seconds = search_ttl_seconds if search_ttl_seconds is not None else configured_ttl
        self.candidate_pool = getattr(self.settings, "paper_discovery_candidate_pool", 200)

    def search(
        self,
        source: ConferenceSource,
        query: str,
        years: Optional[Iterable[int]],
        limit: Optional[int] = None,
        publication_scope: str = "published",
    ) -> SearchResult:
        if publication_scope not in {"published", "accepted", "all"}:
            raise PaperDiscoverySearchError("INVALID_PUBLICATION_SCOPE", "publication_scope must be published, accepted, or all")
        source, query, selected_years, limit = self._validate(
            source, query, years, limit, allow_current_year=publication_scope in {"accepted", "all"}
        )
        now = _utcnow()
        session = SearchSession(
            search_id=uuid4().hex,
            query=query,
            expires_at=(now + timedelta(seconds=self.search_ttl_seconds)).isoformat(timespec="seconds").replace("+00:00", "Z"),
            created_at=now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        )
        warnings: List[Dict[str, str]] = []
        error_code: Optional[str] = None

        records: list[Mapping[str, Any]] = []
        if publication_scope in {"published", "all"}:
            try:
                recalled = self.dblp_source.search(source, query, selected_years, limit=limit)
                records.extend(list(getattr(recalled, "records", ()) or ()))
                for code in getattr(recalled, "warnings", ()) or ():
                    warnings.append(_warning(str(code), "dblp", "DBLP publication search degraded for one or more years"))
                error_code = getattr(recalled, "error_code", None)
            except Exception:
                error_code = "DBLP_UNAVAILABLE"
                warnings.append(_warning(error_code, "dblp", "DBLP publication search failed; saved an empty session"))
        if publication_scope in {"accepted", "all"}:
            try:
                recalled = self.accepted_source.search(source, query, selected_years, limit=limit)
                records.extend(list(getattr(recalled, "records", ()) or ()))
                for code in getattr(recalled, "warnings", ()) or ():
                    warnings.append(_warning(str(code), "usenix", "USENIX accepted search degraded; retained other results"))
                if publication_scope == "accepted" and not records:
                    error_code = getattr(recalled, "error_code", None)
            except Exception:
                if publication_scope == "accepted":
                    error_code = "USENIX_UNAVAILABLE"
                warnings.append(_warning("USENIX_UNAVAILABLE", "usenix", "USENIX accepted search failed; retained other results"))

        # DBLP appends results in request order. Establish a source-stable
        # order after merge input is collected so years=[2023, 2024] and
        # years=[2024, 2023] produce identical initial ranks.
        records.sort(key=self._record_sort_key)
        candidates: List[PaperCandidate] = []
        for initial_rank, record in enumerate(records):
            candidate = self._candidate_from_record(record, source, session.search_id, query)
            if candidate is None:
                continue
            candidate.initial_rank = initial_rank
            candidate.normalized_title = _normal_title(candidate.title)
            candidate = self._enrich(candidate, warnings)
            candidates = self._merge_candidate(candidates, candidate)

        for candidate in candidates:
            # The same canonical title is used by identity, sorting and SQLite.
            candidate.normalized_title = _normal_title(candidate.title)
        candidates.sort(key=self._sort_key)
        candidates = candidates[: min(limit, self.candidate_pool)]
        for rank, candidate in enumerate(candidates, 1):
            candidate.rank = rank
        # Deliberately after every DBLP/OpenAlex call: the store transaction never holds a network call.
        self.store.save_search(session, candidates)
        return SearchResult(session, candidates, warnings, error_code)

    def _validate(self, source: ConferenceSource, query: str, years: Optional[Iterable[int]], limit: int,
                  *, allow_current_year: bool = False):
        if not isinstance(source, ConferenceSource) or not source.enabled:
            raise PaperDiscoverySearchError("CONFERENCE_DISABLED", "conference must be an enabled configured source")
        configured = {item.conference_id: item for item in self.store.list_conferences()}
        stored = configured.get(source.conference_id)
        if stored is None:
            raise PaperDiscoverySearchError("CONFERENCE_NOT_CONFIGURED", "conference must be configured by the server")
        if not stored.enabled:
            raise PaperDiscoverySearchError("CONFERENCE_DISABLED", "conference must be an enabled configured source")
        if (
            not source.conference_id or not source.name or not source.short_name or not source.dblp_stream
            or not isinstance(source.venue_aliases, list) or not source.venue_aliases
            or any(not isinstance(alias, str) or not alias.strip() for alias in source.venue_aliases)
        ):
            raise PaperDiscoverySearchError("CONFERENCE_INVALID", "conference source is incomplete")
        # API callers do not supply persistence timestamps, so compare every
        # configuration-bearing field while intentionally ignoring those two
        # store-managed fields. A matching stream alone is insufficient:
        # forged names, aliases, or built_in state must not reach DBLP.
        source_config = (
            source.conference_id, source.name, source.short_name, source.dblp_stream,
            tuple(source.venue_aliases), source.built_in, source.enabled,
        )
        stored_config = (
            stored.conference_id, stored.name, stored.short_name, stored.dblp_stream,
            tuple(stored.venue_aliases), stored.built_in, stored.enabled,
        )
        if source_config != stored_config:
            raise PaperDiscoverySearchError("CONFERENCE_INVALID", "conference source does not match server configuration")
        if not isinstance(query, str) or not query.strip() or len(query.strip()) > 500:
            raise PaperDiscoverySearchError("INVALID_QUERY", "query must contain 1-500 non-whitespace characters")
        if limit is None:
            limit = self.default_limit
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.max_limit:
            raise PaperDiscoverySearchError("INVALID_LIMIT", f"limit must be between 1 and {self.max_limit}")
        if years is None:
            current_year = _utcnow().year
            values = list(range(current_year - self.default_years, current_year))
        elif isinstance(years, int) and not isinstance(years, bool):
            values = [years]
        else:
            try:
                values = list(years)
            except TypeError as error:
                raise PaperDiscoverySearchError("INVALID_YEARS", "years must be an iterable of integers") from error
        if not values or len(values) > self.max_years or any(isinstance(year, bool) or not isinstance(year, int) for year in values):
            raise PaperDiscoverySearchError("INVALID_YEARS", "years must contain a bounded non-empty list of integers")
        max_year = _utcnow().year if allow_current_year else _utcnow().year - 1
        if any(year < 1900 or year > max_year for year in values):
            raise PaperDiscoverySearchError("INVALID_YEARS", f"years must be between 1900 and {max_year}")
        return stored, query.strip(), tuple(dict.fromkeys(values)), limit

    @staticmethod
    def _sort_key(item: PaperCandidate):
        return (-item.final_score, item.initial_rank, item.year is None, -(item.year or 0),
                item.normalized_title or _normal_title(item.title), item.candidate_id)

    @staticmethod
    def _record_sort_key(record: Mapping[str, Any]):
        info = record.get("info", record) if isinstance(record, Mapping) else {}
        if not isinstance(info, Mapping):
            info = {}
        try:
            year = int(info.get("year"))
        except (TypeError, ValueError):
            year = 0
        # Prefer upstream identity fields, then canonical title. Every part
        # is text-normalized and therefore independent of response ordering.
        stable_key = (
            str(info.get("key", "")).strip().casefold(),
            _normal_doi(info.get("doi")),
            _normal_title(info.get("title")),
            str(info.get("url", info.get("ee", ""))).strip(),
        )
        return (-year, stable_key)

    @staticmethod
    def _candidate_from_record(record: Mapping[str, Any], source: ConferenceSource, search_id: str, query: str):
        info = record.get("info", record) if isinstance(record, Mapping) else {}
        if not isinstance(info, Mapping):
            return None
        title = str(info.get("title", "")).strip()
        if not title:
            return None
        year = info.get("year")
        try:
            year = int(year) if year is not None and str(year).strip() else None
        except (TypeError, ValueError):
            year = None
        doi = _normal_doi(info.get("doi")) or None
        key = str(info.get("key", "")).strip().casefold() or None
        authors = info.get("authors", info.get("author", []))
        if isinstance(authors, Mapping):
            authors = authors.get("author", [])
        if not isinstance(authors, (list, tuple)):
            authors = [authors]
        names = [str(item.get("text", item.get("name", "")) if isinstance(item, Mapping) else item).strip() for item in authors]
        names = [name for name in names if name]
        year_key = "" if year is None else str(year)
        conference_key = source.conference_id.strip().casefold()
        author_key = ",".join(_normal_author_set(names))
        identity = (
            f"doi:{doi}" if doi else
            f"key:{key}:{year_key}:{conference_key}" if key else
            f"title:{_normal_title(title)}:{author_key}:{year_key}:{conference_key}"
        )
        candidate_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        score = PaperDiscoverySearchService._score(query, title)
        candidate = PaperCandidate(candidate_id, search_id, title, source.conference_id, source.name, year, names, key, doi,
                              None, info.get("url") or info.get("ee"), None, "unknown", score, None, score, 0, None,
                              0, _normal_title(title))
        # Optional Task11 metadata remains backward-compatible with older
        # domain/store snapshots; newer PaperCandidate versions expose fields.
        setattr(candidate, "publication_stage", str(info.get("publication_stage") or "published"))
        setattr(candidate, "source_kind", str(info.get("source_kind") or "dblp"))
        setattr(candidate, "source_page_url", info.get("source_page_url") or info.get("url"))
        setattr(candidate, "arxiv_id", info.get("arxiv_id"))
        links = info.get("source_links") or [
            {"kind": "dblp_page", "url": info.get("url")},
            {"kind": "pdf", "url": info.get("ee")},
        ]
        candidate.source_links = [
            item if isinstance(item, Mapping) else {"kind": "source", "url": item}
            for item in links if (item.get("url") if isinstance(item, Mapping) else item)
        ]
        if info.get("pdf_url"):
            candidate.pdf_url = info["pdf_url"]
            candidate.pdf_access = "public"
        return candidate

    @staticmethod
    def _score(query: str, title: str) -> float:
        query_key, title_key = _normal_title(query), _normal_title(title)
        if not query_key or not title_key:
            return 0.0
        if query_key == title_key:
            return 1.0
        return round(max(SequenceMatcher(None, query_key, title_key).ratio(), 0.75 if query_key in title_key else 0.0), 6)

    def _enrich(self, candidate: PaperCandidate, warnings: List[Dict[str, str]]) -> PaperCandidate:
        enricher = self.openalex_enricher
        if enricher is None:
            return candidate
        try:
            if candidate.doi and callable(getattr(enricher, "enrich_by_doi", None)):
                try:
                    payload = enricher.enrich_by_doi(candidate.doi, title=candidate.title, year=candidate.year)
                except TypeError:
                    # Keep compatibility with small test/dedicated adapters
                    # that expose the original one-argument helper.
                    payload = enricher.enrich_by_doi(candidate.doi)
            elif not candidate.doi and callable(getattr(enricher, "enrich_by_title", None)):
                payload = enricher.enrich_by_title(candidate.title, candidate.year)
            else:
                method = getattr(enricher, "enrich", enricher)
                try:
                    payload = method({"doi": candidate.doi, "title": candidate.title, "year": candidate.year})
                except TypeError:
                    payload = method(doi=candidate.doi, title=candidate.title, year=candidate.year)
        except Exception:
            warnings.append(_warning("OPENALEX_UNAVAILABLE", "openalex", "OpenAlex enrichment failed; retained DBLP metadata"))
            return candidate
        issues = getattr(payload, "warnings", ()) or ()
        for issue in issues:
            warnings.append(_warning(str(getattr(issue, "code", issue)), "openalex", "OpenAlex enrichment warning"))
        issue_error = getattr(payload, "error_code", None)
        if issue_error and not any(item["code"] == issue_error for item in warnings):
            warnings.append(_warning(str(issue_error), "openalex", "OpenAlex enrichment unavailable; retained DBLP metadata"))
        if not payload:
            if not issues and not issue_error:
                warnings.append(_warning("OPENALEX_NO_MATCH", "openalex", "OpenAlex returned no enrichment for this candidate"))
            return candidate
        if hasattr(payload, "candidates"):
            matches = list(getattr(payload, "candidates", ()) or ())
            values = self._metadata_from_candidate(matches[0]) if matches else {}
        else:
            values = dict(payload) if isinstance(payload, Mapping) else vars(payload)
        for field_name in ("abstract", "article_url", "pdf_url", "pdf_access"):
            value = values.get(field_name)
            if value not in (None, ""):
                setattr(candidate, field_name, value)
        if not candidate.doi:
            doi = _normal_doi(values.get("doi"))
            if doi:
                candidate.doi = doi
        if isinstance(values.get("open_access"), Mapping):
            oa = values["open_access"]
            if values.get("pdf_access") in (None, ""):
                candidate.pdf_access = "public" if oa.get("is_oa") else candidate.pdf_access
            if not candidate.pdf_url:
                candidate.pdf_url = oa.get("oa_url")
        if candidate.pdf_access not in {"unknown", "public", "login_required", "unavailable"}:
            candidate.pdf_access = "unknown"
        return candidate

    @staticmethod
    def _metadata_from_candidate(candidate: PaperCandidate) -> Dict[str, Any]:
        return {name: getattr(candidate, name) for name in ("doi", "abstract", "article_url", "pdf_url", "pdf_access")}

    @staticmethod
    def _merge_candidate(candidates: List[PaperCandidate], incoming: PaperCandidate) -> List[PaperCandidate]:
        incoming_keys = PaperDiscoverySearchService._identity_keys(incoming)
        for index, previous in enumerate(candidates):
            previous_keys = PaperDiscoverySearchService._identity_keys(previous)
            if incoming_keys & previous_keys and not PaperDiscoverySearchService._strong_identity_conflict(previous, incoming):
                links = list(getattr(previous, "source_links", []) or [])
                for link in getattr(incoming, "source_links", []) or []:
                    if link not in links:
                        links.append(link)
                previous.source_links = incoming.source_links = links
                previous_priority = PaperDiscoverySearchService._candidate_priority(previous)
                incoming_priority = PaperDiscoverySearchService._candidate_priority(incoming)
                previous_richness = PaperDiscoverySearchService._metadata_richness(previous)
                incoming_richness = PaperDiscoverySearchService._metadata_richness(incoming)
                winner = incoming if (incoming_priority, incoming_richness) > (previous_priority, previous_richness) else previous
                loser = previous if winner is incoming else incoming
                # A stronger source wins, but may only fill missing metadata.
                for field_name in ("abstract", "article_url", "pdf_url", "doi"):
                    if getattr(winner, field_name) in (None, "", "unknown"):
                        value = getattr(loser, field_name)
                        if value not in (None, "", "unknown"):
                            setattr(winner, field_name, value)
                winner.candidate_id = previous.candidate_id
                winner.initial_rank = previous.initial_rank
                winner.normalized_title = previous.normalized_title
                winner.rank = previous.rank
                candidates[index] = winner
                return candidates
        candidates.append(incoming)
        return candidates

    @staticmethod
    def _candidate_priority(candidate: PaperCandidate) -> tuple[int, int]:
        stage = str(getattr(candidate, "publication_stage", "published")).casefold()
        source = str(getattr(candidate, "source_kind", "dblp")).casefold()
        return _STAGE_PRIORITY.get(stage, -1), _SOURCE_PRIORITY.get(source, -1)

    @staticmethod
    def _strong_identity_conflict(left: PaperCandidate, right: PaperCandidate) -> bool:
        left_doi, right_doi = _normal_doi(left.doi), _normal_doi(right.doi)
        if left_doi or right_doi:
            return bool(left_doi and right_doi and left_doi != right_doi)
        left_key = str(left.dblp_key or "").strip().casefold()
        right_key = str(right.dblp_key or "").strip().casefold()
        return bool(left_key and right_key and left_key != right_key)

    @staticmethod
    def _metadata_richness(candidate: PaperCandidate) -> int:
        return sum(value not in (None, "", [], "unknown") for value in
                   (candidate.abstract, candidate.pdf_url, candidate.doi))

    @staticmethod
    def _identity_keys(candidate: PaperCandidate) -> set[str]:
        """Return canonical identity keys scoped to the candidate's year/conference."""
        year = "" if candidate.year is None else str(candidate.year)
        conference = str(candidate.conference_id or "").strip().casefold()
        keys = set()
        doi = _normal_doi(candidate.doi)
        dblp_key = str(candidate.dblp_key or "").strip().casefold()
        title = _normal_title(candidate.title)
        author_key = ",".join(_normal_author_set(candidate.authors))
        if doi:
            keys.add(f"doi:{doi}")
        if dblp_key:
            keys.add(f"key:{dblp_key}:{year}:{conference}")
        if title:
            keys.add(f"title:{title}:{author_key}:{year}:{conference}")
        return keys
