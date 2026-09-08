"""Injected, allowlisted USENIX accepted-paper source."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional
from urllib.parse import urlsplit

import httpx

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
from backend.app.paper_discovery.domain.paper_download_security import URLSecurityError, validate_url
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
)


class _SyncResult:
    """Outcome of a single ``sync_usenix_units`` run over discovered pages."""
    __slots__ = ("status", "error_code", "cached", "completed", "failed", "waiting", "paper_count")

    def __init__(self) -> None:
        self.status = "completed"
        self.error_code: Optional[str] = None
        self.cached: list[str] = []
        self.completed: list[str] = []
        self.failed: list[str] = []
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
        if selected_years and not listings:
            error = "USENIX_UNAVAILABLE"
        elif listing_years and failed_years == len(listing_years):
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
        template = str(route["listing_url_template"])
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
                       result: "_SyncResult", route: Any) -> None:
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
        metadata = {
            "title": title,
            "authors": list(paper.authors),
            "year": paper.year,
            "abstract": paper.abstract,
            "article_url": paper.article_url,
            "page_unit_id": unit_id,
        }
        metadata_hash = hashlib.sha256(
            json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        catalog = CatalogPaper(
            catalog_paper_id=catalog_paper_id, conference_id=conference_id, year=paper.year,
            title=title, normalized_title=key, authors=list(paper.authors),
            abstract=paper.abstract or None, publication_stage="accepted",
            official_page_url=paper.article_url,
            official_pdf_url=paper.official_pdf_url,
            prepublication_pdf_url=paper.prepublication_pdf_url,
            metadata_hash=metadata_hash, index_status="pending",
            created_at=now, updated_at=now,
        )
        self.store.upsert_catalog_paper(catalog, now)
        source_record = CatalogSourceRecord(
            source_record_id=f"{unit_id}|{catalog_paper_id}".replace("/", "-"),
            catalog_paper_id=catalog_paper_id, fetch_unit_id=unit_id,
            source_kind="usenix", source_key=catalog_paper_id,
            raw_metadata=metadata, observed_at=now,
        )
        self.store.save_source_record(source_record, now)

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
        for page in pages:
            try:
                self._sync_one_page(search_id, conference_id, page, owner,
                                    lease_seconds, now, result, route)
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
