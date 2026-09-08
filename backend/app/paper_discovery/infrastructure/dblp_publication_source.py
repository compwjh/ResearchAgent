"""Narrow DBLP publication-search adapter for configured main conferences."""
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

from backend.app.paper_discovery.domain.paper_discovery import ConferenceSource
from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi, normalize_title

_EXCLUDED = re.compile(r"\b(workshop|poster|doctoral|soups|demo|tutorial|ccsw|spw)\b", re.I)


def _text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def filter_main_conference_records(records: Iterable[Dict[str, Any]], source: ConferenceSource, year: int) -> List[Dict[str, Any]]:
    """Accept only strict main-conference records; unknown type/key never passes."""
    aliases = {_text(alias) for alias in source.venue_aliases if _text(alias)}
    accepted: List[Dict[str, Any]] = []
    for raw in records:
        info = raw.get("info", raw) if isinstance(raw, dict) else {}
        if not isinstance(info, dict) or str(info.get("year", "")) != str(year):
            continue
        key, kind, venue = str(info.get("key", "")), str(info.get("type", "")), _text(info.get("venue"))
        if not key.startswith(f"{source.dblp_stream}/") or "conference" not in kind.casefold() or venue not in aliases:
            continue
        if _EXCLUDED.search(" ".join(str(info.get(field, "")) for field in ("title", "venue", "key", "doi"))):
            continue
        accepted.append(info)
    return accepted


def deduplicate_publications(records: Iterable[Dict[str, Any]], conference_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Keep the first record for DOI, DBLP key, or title/year/conference.

    A DBLP key is normally unique by itself, but the identity contract for
    this adapter is scoped to the returned conference and publication year.
    Including both fields prevents a malformed upstream record from causing
    two otherwise distinct records to disappear during a multi-year search.
    """
    seen, unique = set(), []
    for record in records:
        info = record.get("info", record) if isinstance(record, dict) else {}
        if not isinstance(info, dict):
            continue
        year = str(info.get("year") or "").strip()
        conference = str(conference_id or info.get("conference_id") or _text(info.get("venue"))).strip().casefold()
        keys = set()
        doi = normalize_doi(info.get("doi"))
        key = str(info.get("key", "")).strip().casefold()
        title = normalize_title(info.get("title"))
        if doi:
            keys.add(f"doi:{doi}")
        if key:
            keys.add(f"key:{key}:{year}:{conference}")
        if title:
            keys.add(f"title:{title}:{year}:{conference}")
        if not keys or keys & seen:
            continue
        seen.update(keys)
        unique.append(record)
    return unique


@dataclass(frozen=True)
class DBLPPublicationResult:
    records: Tuple[Dict[str, Any], ...]
    warnings: Tuple[str, ...] = ()
    error_code: Optional[str] = None
    # Keep the per-year failure evidence so callers can preserve successful
    # units while marking only the years degraded by a warning.
    failed_years: Tuple[int, ...] = ()


class DBLPPublicationSource:
    endpoint = "https://dblp.org/search/publ/api"
    user_agent = "ResearchAgent-Spec015/1.0 (+https://localhost)"

    def __init__(self, *, timeout: float = 20, retries: int = 2, backoff: float = .25,
                 client: Optional[httpx.Client] = None, transport: Any = None, sleep=time.sleep):
        self.timeout, self.retries, self.backoff, self.client, self.transport, self.sleep = timeout, retries, backoff, client, transport, sleep

    def search(self, source: ConferenceSource, query: str, years: Iterable[int], limit: int = 100) -> DBLPPublicationResult:
        selected_years, records, warnings, failure_codes, failed_years = tuple(dict.fromkeys(years)), [], [], [], []
        for year in selected_years:
            payload, warning = self._request(source.dblp_stream, query, int(year), limit)
            if warning:
                warnings.append(warning)
                failure_codes.append(warning)
                failed_years.append(int(year))
                continue
            hits, shape_error = self._extract_hits(payload)
            if shape_error:
                warnings.append(shape_error)
                failure_codes.append(shape_error)
                failed_years.append(int(year))
                continue
            records.extend(filter_main_conference_records(hits, source, int(year)))
        if failure_codes and len(failure_codes) == len(selected_years):
            error = "DBLP_INVALID_RESPONSE" if all(code == "DBLP_INVALID_RESPONSE" for code in failure_codes) else "DBLP_UNAVAILABLE"
        else:
            error = None
        return DBLPPublicationResult(
            tuple(deduplicate_publications(records, source.conference_id)),
            tuple(dict.fromkeys(warnings)), error, tuple(failed_years),
        )

    @staticmethod
    def _extract_hits(payload: Any) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Validate the DBLP envelope instead of treating malformed data as no hits."""
        if not isinstance(payload, dict):
            return [], "DBLP_INVALID_RESPONSE"
        result = payload.get("result")
        hits = result.get("hits") if isinstance(result, dict) else None
        hit_rows = hits.get("hit") if isinstance(hits, dict) else None
        if not isinstance(hit_rows, list) or any(not isinstance(row, dict) for row in hit_rows):
            return [], "DBLP_INVALID_RESPONSE"
        return hit_rows, None

    def _request(self, stream: str, query: str, year: int, limit: int) -> Tuple[Dict[str, Any], Optional[str]]:
        for attempt in range(self.retries + 1):
            try:
                # Keep the endpoint and conference/year constraints server-controlled;
                # httpx encodes the validated query as a single query parameter.
                publication_query = f"{query} stream:{stream} year:{year}"
                kwargs = {"headers": {"User-Agent": self.user_agent}, "params": {"q": publication_query, "format": "json", "h": max(1, min(limit, 100)), "f": 0}}
                if self.client:
                    response = self.client.get(self.endpoint, timeout=self.timeout, **kwargs)
                else:
                    with httpx.Client(timeout=self.timeout, trust_env=False, transport=self.transport) as client:
                        response = client.get(self.endpoint, **kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError("retryable", request=response.request, response=response)
                response.raise_for_status()
                try: payload = response.json()
                except ValueError: return {}, "DBLP_INVALID_RESPONSE"
                return (payload, None) if isinstance(payload, dict) else ({}, "DBLP_INVALID_RESPONSE")
            except httpx.TimeoutException: code = "DBLP_TIMEOUT"
            except httpx.HTTPStatusError as error: code = "DBLP_RATE_LIMITED" if error.response.status_code == 429 else "DBLP_HTTP_ERROR"
            except (httpx.HTTPError, ValueError): code = "DBLP_NETWORK_ERROR"
            if attempt < self.retries: self.sleep(self.backoff * (2 ** attempt))
        return {}, code
