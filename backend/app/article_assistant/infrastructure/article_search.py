import hashlib
import re
import time
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional

import httpx

from backend.app.article_assistant.domain.article import ArticleCandidate
from backend.app.platform.settings.settings_repository import ArticleSettings


def _title_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _score(query: str, title: str) -> float:
    query_key = _title_key(query)
    title_key = _title_key(title)
    if query_key == title_key:
        return 1.0
    return round(SequenceMatcher(None, query_key, title_key).ratio(), 3)


def _candidate_from_payload(item: Dict[str, Any], index: int, source: str, score: float) -> ArticleCandidate:
    title = str(item.get("title", "")).strip()
    identity = str(item.get("doi") or item.get("article_url") or title or index)
    candidate_id = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
    return ArticleCandidate(
        candidate_id=candidate_id,
        title=title,
        authors=[str(author) for author in item.get("authors", []) if author],
        year=item.get("year"),
        doi=item.get("doi"),
        article_url=item.get("article_url"),
        pdf_url=item.get("pdf_url"),
        source_name=source,
        source_kind="configured",
        confidence=score,
        requires_login=bool(item.get("requires_login", False)),
    )


def _request_json(url: str, settings: ArticleSettings, params: Dict[str, Any]) -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    for attempt in range(settings.article_retry_count + 1):
        try:
            response = httpx.get(url, params=params, timeout=settings.article_request_timeout_seconds, trust_env=False)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            last_error = error
            if attempt < settings.article_retry_count:
                time.sleep(settings.article_retry_backoff_seconds * (2 ** attempt))
    raise last_error or RuntimeError("检索来源请求失败")


def _crossref_candidates(query: str, settings: ArticleSettings) -> Iterable[ArticleCandidate]:
    payload = _request_json(
        "https://api.crossref.org/works",
        settings,
        {"query.bibliographic": query, "rows": settings.article_max_candidates_per_source, "select": "DOI,title,author,published,URL,link"},
    )
    for index, item in enumerate(payload.get("message", {}).get("items", [])):
        title = str((item.get("title") or [""])[0]).strip()
        links = item.get("link") or []
        pdf_url = next((link.get("URL") for link in links if link.get("URL")), None)
        year = (item.get("published", {}).get("date-parts") or [[None]])[0][0]
        yield _candidate_from_payload({
            "title": title,
            "doi": item.get("DOI"),
            "article_url": item.get("URL"),
            "pdf_url": pdf_url,
            "authors": [author.get("family", "") for author in item.get("author", [])],
            "year": year,
        }, index, "Crossref", _score(query, title))


def _openalex_candidates(query: str, settings: ArticleSettings) -> Iterable[ArticleCandidate]:
    payload = _request_json(
        "https://api.openalex.org/works",
        settings,
        {"search": query, "per-page": settings.article_max_candidates_per_source, "select": "id,doi,title,publication_year,authorships,primary_location,open_access"},
    )
    for index, item in enumerate(payload.get("results", [])):
        location = item.get("primary_location") or {}
        best_oa = item.get("open_access") or {}
        pdf_url = location.get("pdf_url") or best_oa.get("oa_url")
        title = str(item.get("title", "")).strip()
        yield _candidate_from_payload({
            "title": title,
            "doi": item.get("doi"),
            "article_url": location.get("landing_page_url") or item.get("id"),
            "pdf_url": pdf_url,
            "authors": [(author.get("author") or {}).get("display_name", "") for author in item.get("authorships", [])],
            "year": item.get("publication_year"),
        }, index, "OpenAlex", _score(query, title))


def search_articles(query: str, settings: ArticleSettings) -> List[ArticleCandidate]:
    candidates: List[ArticleCandidate] = []
    for source in settings.article_metadata_sources:
        try:
            if source.lower() == "crossref":
                candidates.extend(_crossref_candidates(query, settings))
            elif source.lower() == "openalex":
                candidates.extend(_openalex_candidates(query, settings))
        except (httpx.HTTPError, ValueError):
            continue
    for index, source in enumerate(settings.article_search_urls):
        try:
            payload = _request_json(source, settings, {"q": query})
            items = payload.get("results", payload) if isinstance(payload, dict) else payload
            if isinstance(items, list):
                candidates.extend(
                    _candidate_from_payload(item, index, "Configured", _score(query, str(item.get("title", ""))))
                    for item in items if isinstance(item, dict)
                )
        except (httpx.HTTPError, ValueError):
            continue

    unique: Dict[str, ArticleCandidate] = {}
    for candidate in candidates:
        key = candidate.doi.lower() if candidate.doi else _title_key(candidate.title)
        previous = unique.get(key)
        if previous is None or candidate.confidence > previous.confidence or (candidate.pdf_url and not previous.pdf_url):
            unique[key] = candidate
    return sorted(unique.values(), key=lambda item: item.confidence, reverse=True)
