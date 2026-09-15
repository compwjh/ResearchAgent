"""Injected, allowlisted USENIX accepted-paper source."""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
import tempfile
import threading
import time
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Mapping, Optional
from urllib.parse import urlsplit

import httpx

from backend.app.core.url_security import URLSecurityError, validate_url
from backend.app.paper_discovery.domain.paper_discovery import (
    CatalogPaper,
    CatalogSourceRecord,
    ConferenceSource,
    SearchEvent,
    SearchJob,
    SearchSourceProgress,
    SourceFetchUnit,
)
from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_title
from backend.app.paper_discovery.infrastructure.arxiv_adapter import ArxivFallbackAdapter
from backend.app.paper_discovery.infrastructure.paper_download import (
    INVALID_PDF,
    PDF_TOO_LARGE,
    PaperDownloadError,
    download_candidate,
)
from backend.app.paper_discovery.infrastructure.usenix_paper_parser import (
    UsenixAcceptedParser,
    parse_accepted_papers,
    parse_usenix_detail,
)


class _SyncResult:
    """Outcome of a single ``sync_usenix_units`` run over discovered pages."""
    __slots__ = ("status", "error_code", "cached", "completed", "failed", "detail_failed",
                 "waiting", "paper_count")

    def __init__(self) -> None:
        self.status = "completed"
        self.error_code: Optional[str] = None
        self.cached: list[str] = []
        self.completed: list[str] = []
        # ``failed`` is the listing-page (recall path) failure bucket: it is what
        # drives ``partial``/``degraded`` for the source and the whole search job.
        self.failed: list[str] = []
        # ``detail_failed`` tracks presentation-page (abstract backfill) failures.
        # An abstract is an enhancement, not the recall path, so these units stay
        # ``failed``/retryable and emit their own event, but they never degrade
        # the source status or the job.
        self.detail_failed: list[str] = []
        self.waiting: list[str] = []
        self.paper_count = 0


def _default_utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _lease_expires_at(now: str, lease_seconds: int) -> str:
    """Return a recoverable lease deadline for stores without release support."""
    from datetime import datetime, timedelta

    parsed = datetime.fromisoformat(now.replace("Z", "+00:00"))
    return (parsed + timedelta(seconds=max(0, int(lease_seconds)))).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def _paper_metadata(*, title: str, authors: Iterable[str], year: Any, abstract: Optional[str],
                    article_url: Optional[str], page_unit_id: Optional[str]) -> dict[str, Any]:
    """Build the exact metadata dict every catalog hash is computed over.

    ``_persist_paper`` (listing sync) and ``_catalog_metadata_hash`` (detail
    backfill) MUST hash the same field set, otherwise re-persisting an unchanged
    row produces a different hash, ``upsert_catalog_paper`` treats it as new
    metadata and resets ``index_status`` to ``pending`` - re-embedding an
    abstract that was already indexed.  Sharing this builder makes that parity
    structural instead of a convention two call sites have to remember.
    """
    return {
        "title": title,
        "authors": list(authors),
        "year": year,
        "abstract": abstract or "",
        "article_url": article_url,
        "page_unit_id": page_unit_id,
    }


def _catalog_metadata_hash(paper: Any, abstract: Optional[str]) -> str:
    """Recompute a catalog row's ``metadata_hash`` for a new abstract.

    ``upsert_catalog_paper`` short-circuits when the hash is unchanged, so a
    detail-page backfill MUST change it or the write is silently dropped.  The
    field set is the shared one ``_persist_paper`` hashes, and the
    ``page_unit_id`` is the deterministic per-paper key (``_page_unit_key``)
    rather than the listing unit, so re-persisting the same row from either path
    keeps yielding the same hash.
    """
    metadata = _paper_metadata(
        title=paper.title, authors=paper.authors, year=paper.year, abstract=abstract,
        article_url=paper.official_page_url,
        page_unit_id=_page_unit_key(paper.official_page_url),
    )
    return hashlib.sha256(
        json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _page_unit_key(article_url: Optional[str]) -> Optional[str]:
    """Deterministic per-paper key used for BOTH catalog metadata hashes.

    The listing unit id is not available on the detail (backfill) path, so the
    two paths share this URL-derived key instead.  Any stable value works as
    long as both sides agree; the article URL is the one field they both hold.
    """
    return article_url or None


@dataclass(frozen=True)
class UsenixAcceptedResult:
    records: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    error_code: Optional[str] = None


class UsenixAcceptedSource:
    """Recall USENIX accepted papers with official media priority.

    The client is injected so callers can use a fixture transport.  No network
    operation is performed while the search store is being written.
    """

    origin = "https://www.usenix.org"

    def __init__(self, *, client: Optional[httpx.Client] = None,
                 parser: Optional[UsenixAcceptedParser] = None,
                 arxiv_adapter: Optional[ArxivFallbackAdapter] = None,
                 timeout: float = 20.0,
                 dns_resolver: Optional[Callable[[str], Iterable[object]]] = None,
                 peer_ip_resolver: Optional[Callable[..., str | None]] = None,
                 cache_ttl_seconds: float = 86400.0,
                 now: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 pdf_page_validator: Optional[Callable[[Any], int]] = None,
                 store: Any = None,
                 utcnow: Callable[[], str] = _default_utcnow) -> None:
        self.client = client
        self.parser = parser or UsenixAcceptedParser()
        self.arxiv_adapter = arxiv_adapter or ArxivFallbackAdapter()
        self.store = store
        self._utcnow = utcnow
        self._discovery_routes: list[Any] = []
        self.timeout = timeout
        self.dns_resolver, self.peer_ip_resolver = dns_resolver, peer_ip_resolver
        self.cache_ttl_seconds, self._now, self._sleep = max(0.0, cache_ttl_seconds), now, sleep
        self.pdf_page_validator = pdf_page_validator
        self._cache: dict[tuple[str, object], tuple[float, object]] = {}
        self._search_cache: dict[tuple[object, ...], tuple[float, UsenixAcceptedResult]] = {}
        self._next_request_at = 0.0
        self._lock = threading.Lock()
        self._probe_state = threading.local()

    def search(self, source: ConferenceSource, query: str, years: Iterable[int],
               limit: int = 20, *, cycle: str = "1") -> UsenixAcceptedResult:
        if source.conference_id != "usenix-security":
            return UsenixAcceptedResult(error_code="ACCEPTED_ROUTE_UNAVAILABLE")
        selected_years = tuple(dict.fromkeys(years))
        cycle = str(cycle).removeprefix("cycle") or "1"
        route = self._route(source)
        if route is None:
            return UsenixAcceptedResult(error_code="ACCEPTED_ROUTE_UNAVAILABLE")
        cache_key = (source.conference_id, normalize_title(query), selected_years, cycle, limit)
        cached = self._cached(self._search_cache, cache_key)
        if cached is not None:
            return cached
        interval = self._rate_limit(route)
        self._probe_state.retryable = False
        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        failed_listings: dict[int, int] = {}
        listings_per_year: dict[int, int] = {}
        listings: list[tuple[int, str]] = []
        # An explicit non-default cycle keeps the legacy single-listing behavior;
        # otherwise every cycle slug USENIX serves for that year is requested and
        # aggregated, so summer/fall (2022-2024) and cycle1 (2025+) both resolve.
        explicit_cycle = str(cycle).removeprefix("cycle")
        explicit_cycle = explicit_cycle if explicit_cycle and explicit_cycle not in ("", "1") else None
        for year in selected_years:
            cycles = (explicit_cycle,) if explicit_cycle else self._cycles_for_year(int(year))
            for slug in cycles:
                listings_per_year[year] = listings_per_year.get(year, 0) + 1
                listings.append((int(year), self._listing_url(route, int(year), slug)))
        for year, listing in listings:
            try:
                markup = self._get_text(listing, interval)
                details = self.parser.parse_listing(markup, page_url=listing)
            except Exception:
                failed_listings[year] = failed_listings.get(year, 0) + 1
                continue
            for detail_url in details:
                if len(records) >= limit:
                    break
                try:
                    paper = self.parser.parse_detail(self._get_text(detail_url, interval), page_url=detail_url)
                except Exception:
                    warnings.append("USENIX_PARSE_FAILED")
                    continue
                pdf_url, stage = self._preferred_pdf(paper, interval)
                if not pdf_url:
                    try:
                        fallback = self.arxiv_adapter.lookup(paper.title, paper.authors, paper.year)
                    except Exception:
                        fallback = None
                        warnings.append("ARXIV_UNAVAILABLE")
                    if fallback is None:
                        source_kind, arxiv_id = "usenix_accepted", None
                    elif fallback.match:
                        pdf_url, stage = fallback.match.pdf_url, fallback.match.publication_stage
                        source_kind, arxiv_id = "arxiv", fallback.match.arxiv_id
                    else:
                        source_kind, arxiv_id = "usenix_accepted", None
                        if fallback.code:
                            warnings.append(str(fallback.code))
                else:
                    source_kind, arxiv_id = "usenix_accepted", None
                links = [{"kind": "usenix_page", "url": paper.article_url}]
                for kind, value in (("usenix_pdf", paper.official_pdf_url), ("usenix_prepublication_pdf", paper.prepublication_pdf_url)):
                    if value:
                        links.append({"kind": kind, "url": value})
                if arxiv_id:
                    links.extend(({"kind": "arxiv_page", "url": fallback.match.source_page_url},
                                  {"kind": "arxiv_pdf", "url": pdf_url}))
                records.append({"info": {
                    "title": paper.title, "authors": list(paper.authors), "year": paper.year,
                    "url": paper.article_url, "ee": pdf_url, "source_page_url": paper.article_url,
                    "pdf_url": pdf_url, "publication_stage": stage, "source_kind": source_kind,
                    "arxiv_id": arxiv_id, "source_links": links,
                }})
        # Only years that actually have a listing can fail; years outside the
        # controlled range (no cycles) contribute no listing and are ignored here,
        # so an out-of-range year no longer forces the whole result unavailable.
        listing_years = [year for year in selected_years if year in listings_per_year]
        failed_years = sum(
            1 for year in listing_years
            if failed_listings.get(year, 0) >= listings_per_year[year]
        )
        # A non-empty selection that resolves to zero listings means every year is
        # out of range: surface it instead of silently returning an empty 200.
        if selected_years and not listings or listing_years and failed_years == len(listing_years):
            error = "USENIX_UNAVAILABLE"
        else:
            error = None
        # Any failed listing year (partial or full) still warns; out-of-range years
        # that contributed no listing do not.
        if failed_years or error == "USENIX_UNAVAILABLE":
            warnings.append("USENIX_UNAVAILABLE")
        result = UsenixAcceptedResult(tuple(records), tuple(dict.fromkeys(warnings)), error)
        if not result.error_code and not result.warnings and not getattr(self._probe_state, "retryable", False):
            with self._lock:
                self._search_cache[cache_key] = (self._now(), result)
        return result

    def _get_text(self, url: str, interval: float = 1.0) -> str:
        cached = self._cached(self._cache, ("text", url))
        if cached is not None:
            return str(cached)
        validate_url(url, allowed_hosts={"www.usenix.org"}, dns_resolver=self.dns_resolver)
        self._before_request(interval)
        response = self._client().get(url, timeout=self.timeout, follow_redirects=False)
        response.raise_for_status()
        with self._lock:
            self._cache[("text", url)] = (self._now(), response.text)
        return response.text

    def _get_pdf(self, url: str, interval: float = 1.0) -> bool:
        cached = self._cached(self._cache, ("pdf", url))
        if cached is not None:
            return bool(cached)
        try:
            validate_url(url, allowed_hosts={"www.usenix.org"}, dns_resolver=self.dns_resolver)
            with tempfile.TemporaryDirectory(prefix="usenix-probe-") as temp_dir:
                download_candidate(
                    {"pdf_url": url},
                    self._probe_settings(),
                    {"www.usenix.org"},
                    client=_ProbeClient(self, self._client(), interval),
                    dns_resolver=self.dns_resolver,
                    peer_ip_resolver=self.peer_ip_resolver,
                    temp_dir=temp_dir,
                    pdf_page_validator=self.pdf_page_validator,
                    validate_pdf_pages=True,
                )
            valid = True
        except PaperDownloadError as error:
            valid = False
            # Invalid/oversized bodies are stable probe results; transient or
            # policy errors remain retryable and are deliberately not cached.
            if error.code not in {INVALID_PDF, PDF_TOO_LARGE}:
                self._probe_state.retryable = True
                return False
        except (URLSecurityError, httpx.HTTPError, OSError):
            self._probe_state.retryable = True
            return False
        with self._lock:
            self._cache[("pdf", url)] = (self._now(), valid)
        return valid

    def _client(self) -> httpx.Client:
        if self.client is None:
            self.client = httpx.Client(timeout=self.timeout, trust_env=False)
        return self.client

    def _preferred_pdf(self, paper: Any, interval: float = 1.0) -> tuple[Optional[str], str]:
        if paper.official_pdf_url and self._get_pdf(paper.official_pdf_url, interval):
            return paper.official_pdf_url, "accepted"
        if paper.prepublication_pdf_url and self._get_pdf(paper.prepublication_pdf_url, interval):
            return paper.prepublication_pdf_url, "prepublication"
        return None, "accepted"

    def _route(self, source: ConferenceSource) -> Mapping[str, Any] | None:
        routes = getattr(source, "discovery_routes", None) or []
        if not routes:
            return {"enabled": True, "rate_limit_seconds": 1.0}
        for route in routes:
            if isinstance(route, Mapping) and route.get("route_type") == "usenix_accepted":
                return route if route.get("enabled", True) else None
        return None

    @staticmethod
    def _rate_limit(route: Mapping[str, Any]) -> float:
        try:
            value = float(route.get("rate_limit_seconds", 1.0))
        except (TypeError, ValueError):
            value = 1.0
        return max(0.0, value)

    # USENIX Security publishes accepted papers under different URL slugs
    # depending on the year: 2025+ serves ``cycle{N}``, while 2022-2024 only
    # publish ``summer`` and ``fall`` listings.  Requesting a slug the site
    # does not serve returns 404, so slugs must be resolved per year.
    CYCLE_URL_FROM_YEAR = 2025
    # USENIX Security only publishes ``summer``/``fall`` accepted-paper listings
    # from 2022; earlier years are out of the controlled range and serve none.
    USENIX_MIN_YEAR = 2022
    LEGACY_CYCLES: tuple[str, ...] = ("summer", "fall")

    @classmethod
    def _cycles_for_year(cls, year: int) -> tuple[str, ...]:
        """Return the accepted-paper listing slugs USENIX serves for ``year``."""
        year = int(year)
        if year < cls.USENIX_MIN_YEAR:
            return ()
        if year >= cls.CYCLE_URL_FROM_YEAR:
            return ("cycle1",)
        return cls.LEGACY_CYCLES

    def _listing_url(self, route: Mapping[str, Any], year: int, cycle: str) -> str:
        template = str(route.get("listing_url_template") or
                       f"{self.origin}/conference/usenixsecurity{{yy}}/{{cycle}}-accepted-papers")
        cycle = str(cycle)
        # Historical templates bake a literal ``cycle`` prefix into the
        # placeholder (``cycle{cycle}-accepted-papers``).  Callers pass slugs in
        # two shapes -- bare ("1") or full ("cycle1", "summer", "fall") -- so
        # normalise both: a bare number becomes a cycle slug, and the literal
        # prefix is always dropped.  Otherwise the template renders nonsense
        # such as ``cyclecycle1`` or ``cyclesummer``.
        if not cycle.startswith("cycle") and cycle.isdigit():
            cycle = f"cycle{cycle}"
        template = template.replace("cycle{cycle}", "{cycle}")
        return template.replace("{yy}", f"{year % 100:02d}").replace("{year}", str(year)).replace("{cycle}", cycle)

    def _before_request(self, interval: float) -> None:
        with self._lock:
            now = self._now()
            wait = max(0.0, self._next_request_at - now)
            self._next_request_at = max(now, self._next_request_at) + interval
        if wait:
            self._sleep(wait)

    def _cached(self, cache: dict, key: object) -> object | None:
        with self._lock:
            entry = cache.get(key)
            if entry and self._now() - entry[0] <= self.cache_ttl_seconds:
                return entry[1]
            if entry:
                cache.pop(key, None)
        return None

    def _probe_settings(self) -> Any:
        from backend.app.platform.settings.settings_repository import ArticleSettings
        return ArticleSettings(article_download_dir=tempfile.gettempdir())

    # --- Catalog synchronization (Spec015 Task14) --------------------------
    #
    # Cache authority lives in SQLite via fetch units, so a brand new process
    # re-hitting a completed unit skips the listing fetch entirely.  Discovery
    # is *controlled*: only same-conference, no query/fragment/userinfo
    # accepted-paper pages under a known usenixsecurity cycle are admitted.

    @staticmethod
    def _norm_path(url: str) -> Optional[str]:
        """Return the canonical path of a same-origin USENIX page, else None."""
        parts = urlsplit(url)
        if not parts.scheme or not parts.netloc or parts.query or parts.fragment:
            return None
        if not parts.netloc.casefold().endswith("usenix.org") or parts.username:
            return None
        path = parts.path
        return path if path.endswith("/") else f"{path}/"

    @staticmethod
    def _accepted_path_ok(path: str) -> bool:
        norm = path.rstrip("/")
        return bool(
            re.fullmatch(
                r"/conference/usenixsecurity\d+/"
                r"(cycle\d+|summer|fall|accepted)-accepted-papers",
                norm,
            )
        )

    def _discovered_pages(self, conference_id: str, years: Iterable[int]) -> tuple[str, ...]:
        """Deterministic, same-conference seed + same-year supplementary pages."""
        if conference_id != "usenix-security":
            return ()
        pages: list[str] = []
        seen: set[str] = set()
        for year in dict.fromkeys(int(y) for y in years):
            for cycle in self._cycles_for_year(year):
                url = f"{self.origin}/conference/usenixsecurity{year % 100:02d}/{cycle}-accepted-papers"
                if url not in seen:
                    seen.add(url)
                    pages.append(url)
        return tuple(pages)

    def _listing_for(self, page: str, route: Any) -> str:
        """Canonicalise a discovered page to its listing template form."""
        if route is None or not route.get("listing_url_template"):
            return page
        norm = self._norm_path(page) or "/"
        # Match the slug itself rather than "everything after the year", so the
        # canonical form keeps ``summer``/``fall``/``cycleN`` intact instead of
        # nesting the whole ``<slug>-accepted-papers`` tail into ``{cycle}``.
        match = re.match(r"/conference/usenixsecurity(\d{2})/(cycle\d+|summer|fall)-accepted-papers", norm)
        if not match:
            return page
        yy, cycle = match.group(1), match.group(2)
        return self._listing_url(route, int("20" + yy), cycle)

    def _content_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()

    def _fetch_listing(self, page: str) -> tuple[Optional[str], Optional[str]]:
        """Fetch a listing page text via allowlist + rate limit; (text, error)."""
        try:
            validate_url(page, allowed_hosts={"www.usenix.org"}, dns_resolver=self.dns_resolver)
        except URLSecurityError as error:
            return None, f"URL_SECURITY:{error}"
        try:
            self._before_request(1.0)
            response = self._client().get(page, timeout=self.timeout, follow_redirects=False)
        except (httpx.HTTPError, OSError):
            return None, "USENIX_UNAVAILABLE"
        if response.status_code >= 400:
            return None, f"USENIX_HTTP_{response.status_code}"
        return response.text, None

    def _release_owned_fetch_unit(self, unit_id: str, owner: str, *, status: str,
                                  now: str, lease_seconds: int,
                                  fallback: Optional[SourceFetchUnit] = None) -> None:
        """Release only our lease, retaining a deadline for narrow legacy stores.

        The production store performs an owner-conditional SQL update.  Some
        tests/integrations expose only the older save/get surface, so their
        failed unit receives an explicit expiry instead of becoming immortal.
        If ownership changed before cleanup, the fallback update is skipped.
        """
        release = getattr(self.store, "release_lease", None)
        if callable(release):
            try:
                if release(unit_id, owner, status=status, now=now):
                    return
            except Exception:
                # Best-effort fallback below; never overwrite a new owner's lease.
                pass
        # Re-read after a failed release attempt so a lease that changed hands
        # cannot be overwritten by a stale fallback object.
        try:
            current = self.store.get_fetch_unit(unit_id)
        except Exception:
            current = fallback
        if current is None:
            current = fallback
        if current is None or current.lease_owner != owner:
            return
        current.status = status
        current.lease_owner = owner
        current.lease_expires_at = _lease_expires_at(now, lease_seconds)
        current.updated_at = now
        try:
            self.store.save_fetch_unit(current, now)
        except Exception:
            # The original fetch error must remain the observable failure.
            return

    def _sync_one_page(self, search_id: str, conference_id: str, page: str,
                       owner: str, lease_seconds: int, now: str,
                       result: "_SyncResult", route: Any,
                       attempted: Optional[set[str]] = None,
                       years: Optional[Iterable[int]] = None) -> None:
        """Fetch, dedup and persist one accepted-paper listing page."""
        path = self._norm_path(page)
        if path is None or not self._accepted_path_ok(path.rstrip("/")):
            result.failed.append(page)
            self._append_event(search_id, conference_id, "USENIX_DISCOVERY_REJECTED", "rejected",
                               {"page": page}, now)
            return
        unit_id = f"usenix|{conference_id}|{path}"
        listing = self._listing_for(page, route)

        existing = self.store.get_fetch_unit(unit_id)
        if existing is not None and existing.status == "completed" and existing.content_hash:
            with self._lock:
                result.cached.append(unit_id)
            # The listing is cached, but its detail pages may still be missing
            # (a previous run failed, timed out or was interrupted).  Resume the
            # detail stage from the catalog so a later search keeps filling the
            # gaps; no listing request is repeated.
            self._resume_detail_units(search_id, conference_id, owner, lease_seconds,
                                      now, result, attempted, years)
            return

        pending_unit = SourceFetchUnit(
            fetch_unit_id=unit_id, source_kind="usenix", conference_id=conference_id,
            unit_key=listing, status="pending",
            created_at=existing.created_at if existing is not None and existing.created_at else now,
            updated_at=now,
        )
        ensure = getattr(self.store, "ensure_fetch_unit", None)
        if callable(ensure):
            ensure(pending_unit, now)
        elif existing is None:
            # Compatibility for narrow stores; production uses the atomic
            # INSERT .. DO NOTHING primitive before attempting the lease.
            self.store.save_fetch_unit(pending_unit, now)

        acquired = self.store.acquire_fetch_unit(unit_id, owner, lease_seconds, now)
        if not acquired:
            # Another owner holds a valid lease; keep this run retryable rather
            # than reporting a cache hit that could freeze an empty result.
            with self._lock:
                result.waiting.append(unit_id)
            return

        try:
            text, fetch_error = self._fetch_listing(listing)
            if text is None:
                failed_unit = SourceFetchUnit(
                    fetch_unit_id=unit_id, source_kind="usenix", conference_id=conference_id,
                    status="failed", error_code=fetch_error, lease_owner=owner,
                    lease_expires_at=_lease_expires_at(now, lease_seconds),
                    last_attempt_at=now, created_at=now, updated_at=now,
                )
                self.store.save_fetch_unit(failed_unit, now)
                self._release_owned_fetch_unit(
                    unit_id, owner, status="failed", now=now,
                    lease_seconds=lease_seconds, fallback=failed_unit,
                )
                with self._lock:
                    result.failed.append(page)
                self._append_event(search_id, conference_id, "USENIX_FETCH_FAILED", "failed",
                                   {"unit_id": unit_id, "error_code": fetch_error}, now)
                return

            unit_hash = self._content_hash(text)
            papers = tuple(parse_accepted_papers(text, page_url=listing))
            paper_count = 0
            for paper in papers:
                self._persist_paper(search_id, unit_id, conference_id, paper, now, result)
                paper_count += 1
            # The listing carries no abstract, so every paper whose catalog row
            # still has one missing gets a second, independently lease-guarded
            # detail unit.  Failures there degrade the unit, never the job.
            self._sync_detail_units(search_id, conference_id, papers, owner,
                                    lease_seconds, now, result,
                                    attempted if attempted is not None else set())

            completed_unit = SourceFetchUnit(
                fetch_unit_id=unit_id, source_kind="usenix", conference_id=conference_id,
                status="completed", content_hash=unit_hash, paper_count=paper_count,
                lease_owner=owner, last_attempt_at=now, last_success_at=now,
                created_at=existing.created_at if existing is not None and existing.created_at else now,
                updated_at=now,
            )
            self.store.save_fetch_unit(completed_unit, now)
            self._release_owned_fetch_unit(
                unit_id, owner, status="completed", now=now,
                lease_seconds=lease_seconds, fallback=completed_unit,
            )
            with self._lock:
                result.completed.append(unit_id)
                result.paper_count += paper_count
        except Exception:
            self._release_owned_fetch_unit(
                unit_id, owner, status="failed", now=now,
                lease_seconds=lease_seconds,
            )
            raise

    def _persist_paper(self, search_id: str, unit_id: str, conference_id: str,
                       paper: Any, now: str, result: "_SyncResult") -> None:
        """Upsert a catalog paper and its source record for one accepted paper."""
        title = paper.title
        key = normalize_title(title)
        catalog_paper_id = hashlib.sha256(f"{conference_id}|{key}".encode("utf-8")).hexdigest()[:32]
        # The detail (backfill) path cannot see the listing unit, so both paths
        # hash the SAME shared field set, keyed by the article URL.  Otherwise
        # re-persisting an unchanged row looks like new metadata and resets
        # ``index_status`` to ``pending``, re-embedding an indexed abstract.
        metadata = _paper_metadata(
            title=title, authors=paper.authors, year=paper.year, abstract=paper.abstract,
            article_url=paper.article_url, page_unit_id=_page_unit_key(paper.article_url),
        )
        metadata_hash = hashlib.sha256(
            json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        existing = self._existing_catalog_paper(catalog_paper_id)
        if existing is not None:
            # A second listing may publish the same paper (summer + fall, or a
            # re-run of the same cycle).  Abstracts already backfilled from the
            # detail stage must survive, so metadata and the hash are computed
            # from the stored abstract rather than the listing's empty one.
            metadata["abstract"] = existing.abstract or paper.abstract
            metadata_hash = hashlib.sha256(
                json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
        catalog = CatalogPaper(
            catalog_paper_id=catalog_paper_id, conference_id=conference_id, year=paper.year,
            title=title, normalized_title=key, authors=list(paper.authors),
            abstract=(existing.abstract if existing is not None else None) or paper.abstract or None,
            publication_stage=existing.publication_stage if existing is not None else "accepted",
            official_page_url=paper.article_url,
            official_pdf_url=paper.official_pdf_url,
            prepublication_pdf_url=paper.prepublication_pdf_url,
            metadata_hash=metadata_hash, index_status="pending",
            created_at=now, updated_at=now,
        )
        self.store.upsert_catalog_paper(catalog, now)
        source_record = CatalogSourceRecord(
            # ``catalog_source_records`` is unique on (source_kind, source_key),
            # so the key must identify this paper.  Keying it by the listing unit
            # made every paper of one page collide, and the survivors kept the
            # last paper's id — which then made this source look like it did not
            # own the other rows.  The catalog id is the stable per-paper key.
            source_record_id=f"{unit_id}|{catalog_paper_id}".replace("/", "-"),
            catalog_paper_id=catalog_paper_id, fetch_unit_id=unit_id,
            source_kind="usenix", source_key=catalog_paper_id,
            raw_metadata=metadata, observed_at=now,
        )
        self.store.save_source_record(source_record, now)

    # --- Detail fetch units (Spec032.1 Task03) ------------------------------
    #
    # Accepted-paper listings carry no abstract, so a second unit per
    # presentation page backfills it.  The stage reuses the existing lease,
    # rate-limit, content-hash, event and parser machinery; the only new
    # behaviour is the fill-if-missing write and the per-unit isolation.

    @staticmethod
    def _catalog_paper_id(conference_id: str, title: str) -> str:
        """Derive the catalog key exactly as ``_persist_paper`` does."""
        return hashlib.sha256(f"{conference_id}|{normalize_title(title)}".encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _detail_url_ok(url: Any) -> Optional[str]:
        """Allowlist a presentation page and return its canonical path prefix.

        ``parse_usenix_detail`` only accepts pages the parser itself would
        accept, so a caller can never smuggle an arbitrary URL into the detail
        stage: scheme/host are fixed to https + www.usenix.org and the path must
        be ``/conference/<slug>/presentation/<slug>``.
        """
        if not isinstance(url, str) or not url:
            return None
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            return None
        if (parts.scheme, parts.hostname, port) != ("https", "www.usenix.org", None):
            return None
        if parts.username or parts.password or parts.query or parts.fragment or "\\" in parts.path:
            return None
        match = re.fullmatch(r"/conference/[^/]+/presentation/[^/]+/?", parts.path)
        return match.group(0).rstrip("/") if match else None

    def _detail_unit_id(self, conference_id: str, url: str) -> Optional[str]:
        """Return the deterministic detail unit id, or None for an unsafe URL."""
        path = self._detail_url_ok(url)
        return f"usenix|{conference_id}|{path}|detail" if path else None

    def _page_paper_ids(self, conference_id: str) -> set[str]:
        """Catalog ids persisted by this source, read defensively.

        Freshly synced rows are ``pending`` (they are only marked ``indexed``
        once embedded), so the read must not keep the default
        ``index_status="indexed"`` filter.  Narrow stores (and tests) may not
        expose a catalog reader; without one the stage cannot prove an abstract
        is missing, so it does nothing rather than risk overwriting one.
        """
        reader = getattr(self.store, "list_catalog_papers", None)
        if not callable(reader):
            return set()
        try:
            papers = reader([conference_id], None, index_status=None)
        except TypeError:
            # A narrow store may not implement the index_status argument.
            try:
                papers = reader([conference_id])
            except Exception:  # noqa: BLE001
                return set()
        except Exception:  # noqa: BLE001 - a store read must never abort the sync
            return set()
        return {paper.catalog_paper_id for paper in papers}

    def _existing_catalog_paper(self, catalog_paper_id: str) -> Any:
        """Read a catalog row defensively; narrow stores may not expose a reader."""
        get = getattr(self.store, "get_catalog_paper", None)
        if not callable(get):
            return None
        try:
            return get(catalog_paper_id)
        except Exception:  # noqa: BLE001 - a store read must never abort the sync
            return None

    def _catalog_record(self, catalog_paper_id: str) -> tuple[Optional[str], bool]:
        """Return (abstract, record_is_ours) for fill-if-missing."""
        paper = self._existing_catalog_paper(catalog_paper_id)
        if paper is None:
            return None, False
        kinds = getattr(self.store, "get_catalog_source_kinds", None)
        ours = not callable(kinds)
        if callable(kinds):
            try:
                ours = "usenix" in (kinds(catalog_paper_id) or [])
            except Exception:  # noqa: BLE001
                ours = False
        return paper.abstract or None, ours

    def _sync_detail_units(self, search_id: str, conference_id: str, papers: Iterable[Any],
                           owner: str, lease_seconds: int, now: str,
                           result: "_SyncResult", attempted: set[str]) -> None:
        """Backfill missing abstracts from each paper's presentation page.

        The listing is authoritative: papers it already annotated are skipped
        entirely (fill-if-missing), so a second search only fetches the pages
        that are still missing an abstract.  ``attempted`` is owned by the
        caller because USENIX serves the same papers from both 2024 slugs, and
        one run must not fetch the same presentation page twice.
        """
        persist_ids = self._page_paper_ids(conference_id)
        for paper in papers:
            if (getattr(paper, "abstract", "") or "").strip():
                continue
            url = paper.article_url
            unit_id = self._detail_unit_id(conference_id, url)
            if unit_id is None or unit_id in attempted:
                continue
            catalog_paper_id = self._catalog_paper_id(conference_id, paper.title)
            if not self._abstract_missing(catalog_paper_id, persist_ids):
                continue
            attempted.add(unit_id)
            self._sync_detail_unit(search_id, conference_id, url,
                                   owner, lease_seconds, now, result,
                                   catalog_paper_id=catalog_paper_id)

    def _abstract_missing(self, catalog_paper_id: str, persist_ids: set[str]) -> bool:
        """True only when we can prove this paper's abstract is still empty."""
        abstract, ours = self._catalog_record(catalog_paper_id)
        if not ours and catalog_paper_id in persist_ids:
            ours = True
        return ours and not abstract

    def _resume_detail_units(self, search_id: str, conference_id: str, owner: str,
                             lease_seconds: int, now: str, result: "_SyncResult",
                             attempted: Optional[set[str]],
                             years: Optional[Iterable[int]] = None) -> None:
        """Retry detail pages whose catalog row still has no abstract.

        A cached listing unit must not end the run: incomplete detail units stay
        ``pending``/``failed`` so the next search keeps backfilling.  Only the
        presentation URL is taken from the catalog row, and it is re-validated
        by ``_sync_detail_unit`` before any request.

        The read is narrowed to the years THIS request asked for.  Without that
        filter a search limited to 2024 would resume the 2025 rows a previous
        search left pending and fetch their presentation pages, which both
        violates the per-year contract and multiplies the load on usenix.org.
        """
        reader = getattr(self.store, "list_catalog_papers", None)
        if not callable(reader):
            return
        selected_years = list(dict.fromkeys(int(year) for year in years)) if years else None
        try:
            papers = reader([conference_id], selected_years, index_status=None)
        except TypeError:
            # A narrow store may not implement the year/index_status arguments.
            try:
                papers = reader([conference_id])
            except Exception:  # noqa: BLE001
                return
        except Exception:  # noqa: BLE001
            return
        resumed = attempted if attempted is not None else set()
        for paper in papers:
            if (paper.abstract or "").strip():
                continue
            url = paper.official_page_url
            unit_id = self._detail_unit_id(conference_id, url)
            if unit_id is None or unit_id in resumed:
                continue
            resumed.add(unit_id)
            self._sync_detail_unit(search_id, conference_id, url, owner,
                                   lease_seconds, now, result,
                                   catalog_paper_id=paper.catalog_paper_id)

    def _sync_detail_unit(self, search_id: str, conference_id: str, url: Any,
                          owner: str, lease_seconds: int, now: str,
                          result: "_SyncResult", *, catalog_paper_id: str) -> None:
        """Fetch, parse and fill one presentation page's abstract."""
        unit_id = self._detail_unit_id(conference_id, url)
        if unit_id is None:
            # An unsafe URL is rejected outright and never reaches the network.
            self._append_event(search_id, conference_id, "USENIX_DETAIL_REJECTED",
                               "rejected", {"error_code": "USENIX_PARSE_FAILED"}, now)
            return

        existing = self.store.get_fetch_unit(unit_id)
        if existing is not None and existing.status == "completed" and existing.content_hash:
            with self._lock:
                result.cached.append(unit_id)
            return

        pending_unit = SourceFetchUnit(
            fetch_unit_id=unit_id, source_kind="usenix", conference_id=conference_id,
            unit_key=url, status="pending",
            created_at=existing.created_at if existing is not None and existing.created_at else now,
            updated_at=now,
        )
        ensure = getattr(self.store, "ensure_fetch_unit", None)
        if callable(ensure):
            ensure(pending_unit, now)
        elif existing is None:
            self.store.save_fetch_unit(pending_unit, now)

        acquired = self.store.acquire_fetch_unit(unit_id, owner, lease_seconds, now)
        if not acquired:
            # Another owner holds a valid lease; stay retryable and never
            # report this unit as a cache hit.
            with self._lock:
                result.waiting.append(unit_id)
            return

        try:
            text, error_code = self._fetch_detail(url)
            if text is None:
                self._fail_detail_unit(search_id, conference_id, unit_id, url, owner,
                                       lease_seconds, now, result, error_code, existing)
                return
            detail = parse_usenix_detail(text, page_url=url)
            self._fill_abstract(conference_id, catalog_paper_id, detail, now)
            detail_hash = self._content_hash(text)
            completed_unit = SourceFetchUnit(
                fetch_unit_id=unit_id, source_kind="usenix", conference_id=conference_id,
                unit_key=url, status="completed", content_hash=detail_hash, paper_count=1,
                lease_owner=owner, last_attempt_at=now, last_success_at=now,
                created_at=existing.created_at if existing is not None and existing.created_at else now,
                updated_at=now,
            )
            self.store.save_fetch_unit(completed_unit, now)
            self._release_owned_fetch_unit(unit_id, owner, status="completed", now=now,
                                           lease_seconds=lease_seconds, fallback=completed_unit)
            with self._lock:
                result.completed.append(unit_id)
        except Exception:  # noqa: BLE001 - one detail page must never abort the page
            self._fail_detail_unit(search_id, conference_id, unit_id, url, owner,
                                   lease_seconds, now, result, "USENIX_PARSE_FAILED", existing)

    def _fetch_detail(self, url: str) -> tuple[Optional[str], Optional[str]]:
        """Fetch one allowlisted presentation page; returns (text, error_code).

        The body reuses the source's existing response cache (the same
        ``("text", url)`` entry ``_get_text`` maintains), so a repeated request
        for one presentation page is served locally instead of hitting
        usenix.org again.  The cache only lives as long as the instance, which is
        why the Tool adapter now shares one instance process-wide.
        """
        cached = self._cached(self._cache, ("text", url))
        if cached is not None:
            return str(cached), None
        try:
            validate_url(url, allowed_hosts={"www.usenix.org"}, dns_resolver=self.dns_resolver)
        except URLSecurityError as error:
            return None, f"URL_SECURITY:{error}"
        try:
            self._before_request(self._detail_interval())
            response = self._client().get(url, timeout=self.timeout, follow_redirects=False)
        except (httpx.HTTPError, OSError):
            return None, "USENIX_UNAVAILABLE"
        if response.status_code >= 400:
            return None, f"USENIX_HTTP_{response.status_code}"
        with self._lock:
            self._cache[("text", url)] = (self._now(), response.text)
        return response.text, None

    def _detail_interval(self) -> float:
        """Reuse the configured accepted-paper route's rate limit."""
        route = self._discovery_route("usenix-security")
        return self._rate_limit(route) if route else 1.0

    def _fail_detail_unit(self, search_id: str, conference_id: str, unit_id: str, url: str,
                          owner: str, lease_seconds: int, now: str, result: "_SyncResult",
                          error_code: Optional[str], existing: Optional[SourceFetchUnit]) -> None:
        """Mark a detail unit failed and always hand its lease back."""
        failed_unit = SourceFetchUnit(
            fetch_unit_id=unit_id, source_kind="usenix", conference_id=conference_id,
            unit_key=url, status="failed", error_code=error_code, lease_owner=owner,
            lease_expires_at=_lease_expires_at(now, lease_seconds), last_attempt_at=now,
            created_at=existing.created_at if existing is not None and existing.created_at else now,
            updated_at=now,
        )
        with contextlib.suppress(Exception):
            # Bookkeeping a failed unit must not abort the batch.
            self.store.save_fetch_unit(failed_unit, now)
        self._release_owned_fetch_unit(unit_id, owner, status="failed", now=now,
                                       lease_seconds=lease_seconds, fallback=failed_unit)
        with self._lock:
            # Recorded in the detail bucket, NOT ``failed``: a missing abstract
            # must stay observable and retryable without flipping the source to
            # ``partial`` (which would degrade the whole search job).
            result.detail_failed.append(unit_id)
        self._append_event(search_id, conference_id, "USENIX_DETAIL_FAILED", "failed",
                           {"unit_id": unit_id, "error_code": error_code or "USENIX_PARSE_FAILED"}, now)

    def _fill_abstract(self, conference_id: str, catalog_paper_id: str, detail: Any, now: str) -> None:
        """Write the parsed abstract only when the catalog row still lacks one.

        fill-if-missing is a hard rule: the detail page may only ever fill an
        empty abstract, never replace an existing one (a listing-supplied or
        another source's abstract keeps winning).
        """
        abstract = (getattr(detail, "abstract", "") or "").strip()
        if not abstract:
            return
        paper = self._existing_catalog_paper(catalog_paper_id)
        if paper is None or (paper.abstract or "").strip():
            return
        # ``upsert_catalog_paper`` treats an unchanged ``metadata_hash`` as a
        # no-op, so the hash must be recomputed for the new abstract or the
        # write would be skipped entirely.  The store resets ``index_status`` to
        # ``pending`` so the new abstract gets re-embedded.
        updated = replace(
            paper, abstract=abstract, updated_at=now,
            metadata_hash=_catalog_metadata_hash(paper, abstract),
        )
        try:
            self.store.upsert_catalog_paper(updated, now)
        except Exception:  # noqa: BLE001 - a failed write must not abort the batch
            return

    def backfill_abstracts(self, conference_id: str = "usenix-security", *,
                           years: Optional[Iterable[int]] = None,
                           limit: int = 50, interval: float = 1.0) -> dict[str, Any]:
        """回填缺失摘要：只抓官方 presentation 详情页，严格 fill-if-missing。

        列表页本身不带摘要（894/894 目录行皆空），摘要只能来自详情页。本方法
        把这项能力暴露为可重复调用的入口：每次调用只处理仍然缺摘要的行，
        已填过的会被跳过；``limit`` 限制单次抓取页数，便于分批跑，避免长任务。

        返回 ``{filled, attempted, skipped, failed, failures}``；单页失败只记入
        ``failed``，不影响其它论文。
        """
        store = self.store
        if store is None:
            return {"ok": False, "error_code": "USENIX_STORE_UNAVAILABLE",
                    "filled": 0, "attempted": 0, "skipped": 0, "failed": 0, "failures": []}
        now = _default_utcnow()
        wanted_years = {int(year) for year in (years or ())}
        filled = attempted = skipped = failed = 0
        failures: list[dict[str, str]] = []
        processed = 0
        for paper in store.list_catalog_papers([conference_id]):
            if processed >= max(1, int(limit)):
                break
            processed += 1
            if wanted_years and int(getattr(paper, "year", 0) or 0) not in wanted_years:
                continue
            if (getattr(paper, "abstract", "") or "").strip():
                skipped += 1
                continue
            url = getattr(paper, "official_page_url", "") or ""
            if self._detail_url_ok(url) is None:
                skipped += 1
                continue
            attempted += 1
            try:
                detail = self.fetch_paper_detail(url)
            except Exception as error:  # noqa: BLE001 - 单页失败不中断回填
                failed += 1
                failures.append({"catalog_paper_id": paper.catalog_paper_id, "error": str(error)[:120]})
                continue
            if not detail.get("ok"):
                failed += 1
                failures.append({"catalog_paper_id": paper.catalog_paper_id,
                                 "error": str(detail.get("error_code"))})
                continue
            abstract = (detail.get("abstract") or "").strip()
            if not abstract:
                skipped += 1
                continue
            before = (getattr(paper, "abstract", "") or "").strip()
            self._fill_abstract(conference_id, paper.catalog_paper_id,
                                SimpleNamespace(abstract=abstract), now)
            refreshed = self._existing_catalog_paper(paper.catalog_paper_id)
            if (getattr(refreshed, "abstract", "") or "").strip() and not before:
                filled += 1
            else:
                skipped += 1
            if interval:
                self._sleep(interval)
        return {"ok": True, "error_code": None, "filled": filled, "attempted": attempted,
                "skipped": skipped, "failed": failed, "failures": failures[:20]}

    def backfill_authors(self, conference_id: str = "usenix-security", *,
                          years: Optional[Iterable[int]] = None,
                          interval: float = 1.0) -> dict[str, Any]:
        """回填缺失作者：直接解析官方 accepted-paper 列表页，按 catalog_paper_id 批量写入 authors_json。

        与摘要不同，作者已包含在列表页（每个 ``<article>`` 块的 people 字段），
        因此无需逐篇抓详情页——只抓 8 个列表页即可覆盖全部年份。列表页解析出的
        标题与目录行同源，``catalog_paper_id``（由 conference_id + 归一化标题派生）
        完全一致，据此精准匹配。

        严格 fill-if-missing：仅当当前 ``authors_json`` 为空时才写入，已有作者的
        行绝不覆盖；``metadata_hash`` 因作者变化而改变，store 会把 ``index_status``
        重置为 ``pending``，使新作者随下次嵌入生效。

        返回 ``{filled, attempted, skipped, failed, failures}``；单页/单行失败只记入
        ``failed``，不影响其它论文。
        """
        store = self.store
        if store is None:
            return {"ok": False, "error_code": "USENIX_STORE_UNAVAILABLE",
                    "filled": 0, "attempted": 0, "skipped": 0, "failed": 0, "failures": []}
        now = _default_utcnow()
        wanted_years = {int(year) for year in (years or ())}
        route = self._discovery_route(conference_id) or {"rate_limit_seconds": interval}
        filled = attempted = skipped = failed = 0
        failures: list[dict[str, str]] = []
        # 1) 抓取并解析每个列表页，得到 catalog_paper_id -> authors。
        cid_to_authors: dict[str, list[str]] = {}
        for year in dict.fromkeys(int(y) for y in (years or (2022, 2023, 2024, 2025))):
            for cycle in self._cycles_for_year(year):
                listing = self._listing_url(route, year, cycle)
                try:
                    text = self._get_text(listing, interval)
                    papers = parse_accepted_papers(text, page_url=listing)
                except Exception as error:  # noqa: BLE001 - 单页失败不中断回填
                    failed += 1
                    failures.append({"listing": listing, "error": str(error)[:120]})
                    continue
                for paper in papers:
                    cid = self._catalog_paper_id(conference_id, paper.title)
                    if paper.authors:
                        cid_to_authors[cid] = list(paper.authors)
        # 2) 逐行匹配并 fill-if-missing 写入 authors_json。
        #    ``index_status=None`` 取全部行：摘要回填后这些行被重置为 ``pending``，
        #    默认 ``indexed`` 过滤会把它们漏掉，导致匹配不到。
        for paper in store.list_catalog_papers([conference_id], index_status=None):
            if wanted_years and int(getattr(paper, "year", 0) or 0) not in wanted_years:
                continue
            authors = cid_to_authors.get(paper.catalog_paper_id)
            if not authors or getattr(paper, "authors", None):
                skipped += 1
                continue
            attempted += 1
            new_paper = replace(paper, authors=list(authors))
            updated = replace(
                new_paper,
                metadata_hash=_catalog_metadata_hash(new_paper, paper.abstract),
                updated_at=now,
            )
            try:
                self.store.upsert_catalog_paper(updated, now)
            except Exception as error:  # noqa: BLE001 - 单行失败不中断回填
                failed += 1
                failures.append({"catalog_paper_id": paper.catalog_paper_id, "error": str(error)[:120]})
                continue
            refreshed = self._existing_catalog_paper(paper.catalog_paper_id)
            if refreshed is not None and getattr(refreshed, "authors", None):
                filled += 1
            else:
                skipped += 1
        return {"ok": True, "error_code": None, "filled": filled, "attempted": attempted,
                "skipped": skipped, "failed": failed, "failures": failures[:20]}

    # --- Public detail entry point (Spec032.1 Task04) ------------------------
    #
    # ``fetch_paper_detail`` is the stable, Tool-callable face of the detail
    # stage.  It adds no new fetch/parse behaviour: the allowlist check, the
    # rate-limited request seam and the parser are the SAME ones the sync path
    # uses (``_detail_url_ok`` / ``_fetch_detail`` / ``parse_usenix_detail``),
    # so there is exactly one implementation of each.  Only the abstract page
    # is read -- no PDF is ever downloaded here.

    USENIX_DETAIL_URL_REJECTED = "USENIX_DETAIL_URL_REJECTED"

    def fetch_paper_detail(self, url: Any) -> dict[str, Any]:
        """Fetch one allowlisted USENIX presentation page and parse it.

        ``url`` MUST be an official presentation page
        (``https://www.usenix.org/conference/<slug>/presentation/<slug>``);
        an arbitrary URL is never accepted.  A rejected URL returns a readable
        error and performs **no** network request at all.

        Returns a flat dict with ``ok`` / ``error_code`` / ``error`` plus the
        parsed ``title`` / ``authors`` / ``abstract`` / ``keywords`` /
        ``official_pdf_url`` / ``prepublication_pdf_url`` / ``article_url`` /
        ``year`` / ``publication_stage`` / ``source_kind`` fields.
        """
        safe_url = url if isinstance(url, str) else ""
        if self._detail_url_ok(safe_url) is None:
            return {
                "ok": False,
                "url": safe_url,
                "error_code": self.USENIX_DETAIL_URL_REJECTED,
                "error": (
                    "只接受 USENIX 官方 presentation 详情页（"
                    "https://www.usenix.org/conference/<conference>/presentation/<paper>，"
                    "不得带 query 或 fragment）；不接受任意 URL。"
                ),
            }
        text, error_code = self._fetch_detail(safe_url)
        if text is None:
            return {
                "ok": False,
                "url": safe_url,
                "error_code": error_code or "USENIX_PARSE_FAILED",
                "error": f"详情页抓取失败：{error_code or 'USENIX_PARSE_FAILED'}",
            }
        try:
            # ``parse_usenix_detail`` re-validates the URL, so a page whose
            # markup cannot be parsed raises rather than yielding junk.
            paper = parse_usenix_detail(text, page_url=safe_url)
        except Exception as error:  # noqa: BLE001 - unparsable page is a readable error
            return {
                "ok": False,
                "url": safe_url,
                "error_code": "USENIX_PARSE_FAILED",
                "error": f"详情页解析失败：{type(error).__name__}",
            }
        return {
            "ok": True,
            "url": safe_url,
            "error_code": None,
            "error": None,
            "title": paper.title,
            "authors": list(paper.authors),
            "year": paper.year,
            "abstract": paper.abstract,
            "keywords": list(paper.keywords),
            "article_url": paper.article_url,
            "official_pdf_url": paper.official_pdf_url,
            "prepublication_pdf_url": paper.prepublication_pdf_url,
            "absolute_pdf_url": paper.pdf_url,
            "publication_stage": paper.publication_stage,
            "source_kind": paper.source_kind,
        }

    def _append_event(self, search_id: str, conference_id: str, event_type: str,
                      status: str, payload: Mapping[str, Any], now: str) -> None:
        event = SearchEvent(
            event_id=0, search_id=search_id, node_name="usenix_sync",
            source_kind="usenix", event_type=event_type, status=status,
            safe_payload=dict(payload), created_at=now,
        )
        self.store.append_search_event(event, now)

    def sync_usenix_units(
        self,
        search_id: str,
        conference_id: str,
        years: Iterable[int],
        *,
        owner: str,
        lease_seconds: int = 300,
        now: Optional[str] = None,
    ) -> _SyncResult:
        """Controlled discover + lease + persist USENIX accepted-paper pages."""
        if self.store is None:
            raise ValueError("sync_usenix_units requires a store")
        now = now or self._utcnow()
        route = self._discovery_route(conference_id)
        result = _SyncResult()
        pages = self._discovered_pages(conference_id, years)
        selected_years = list(dict.fromkeys(int(year) for year in years))
        # Detail pages are deduped across every listing slug of this run, because
        # USENIX serves the same papers from both 2024 slugs.
        attempted: set[str] = set()
        for page in pages:
            try:
                self._sync_one_page(search_id, conference_id, page, owner,
                                    lease_seconds, now, result, route, attempted,
                                    selected_years)
            except Exception as error:  # noqa: BLE001 - one page must not abort the batch
                with self._lock:
                    result.failed.append(page)
                self._append_event(search_id, conference_id, "USENIX_SYNC_FAILED", "failed",
                                   {"page": page, "error_code": type(error).__name__}, now)

        if not pages:
            result.status, result.error_code = "failed", "NO_PAGES"
        elif result.waiting:
            # A second worker must remain retryable even if another page in
            # this batch failed; never turn an in-flight observation into a
            # terminal failed/completed job that freezes an empty snapshot.
            result.status = "waiting"
        elif result.failed and not result.completed and not result.cached:
            result.status, result.error_code = "failed", "USENIX_UNAVAILABLE"
        elif result.failed:
            result.status = "partial"

        self._record_progress(search_id, conference_id, result, now)
        self._record_job(search_id, conference_id, years, result, now)
        with self._lock:
            for page in result.failed:
                self._append_event(search_id, conference_id, "USENIX_UNIT_FAILED", "failed",
                                   {"page": page}, now)
        return result

    def _discovery_route(self, conference_id: str) -> Any:
        routes = getattr(self, "_discovery_routes", None) or []
        for route in routes:
            if isinstance(route, Mapping) and route.get("route_type") == "usenix_accepted":
                return route if route.get("enabled", True) else None
        return None

    def _record_progress(self, search_id: str, conference_id: str,
                         result: "_SyncResult", now: str) -> None:
        progress = SearchSourceProgress(
            search_id=search_id, source_kind="usenix", status=result.status,
            cached_units=[{"unit_id": u} for u in result.cached],
            fetching_units=[{"unit_id": u} for u in result.waiting],
            completed_units=[{"unit_id": u} for u in result.completed],
            paper_count=result.paper_count, error_code=result.error_code,
            message_code={"waiting": "FETCHING_SOURCE", "partial": "MERGING_METADATA"}.get(result.status, result.status),
            updated_at=now,
        )
        progress.status = {"waiting": "fetching", "partial": "merging"}.get(result.status, result.status)
        self.store.save_source_progress(progress, now)

    def _record_job(self, search_id: str, conference_id: str,
                    years: Iterable[int], result: "_SyncResult", now: str) -> None:
        job = SearchJob(
            search_id=search_id, query="", conference_ids=[conference_id],
            years=list(dict.fromkeys(int(y) for y in years)),
            status="queued" if result.status == "waiting" else result.status,
            degraded=bool(result.failed),
            error_code=result.error_code, total_results=result.paper_count,
            created_at=now,
            started_at=None if result.status == "waiting" else now,
            completed_at=None if result.status == "waiting" else now,
            updated_at=now,
        )
        self.store.create_search_job(job, now)


class _ProbeClient:
    """Force the shared downloader's request seam to remain no-redirect."""

    def __init__(self, owner: UsenixAcceptedSource, client: httpx.Client, interval: float) -> None:
        self.owner, self.client, self.interval = owner, client, interval

    def stream(self, method: str, url: str, **kwargs: Any):
        self.owner._before_request(self.interval)
        kwargs["follow_redirects"] = False
        return self.client.stream(method, url, **kwargs)


USENIXAcceptedSource = UsenixAcceptedSource

__all__ = ["UsenixAcceptedResult", "UsenixAcceptedSource", "USENIXAcceptedSource"]
