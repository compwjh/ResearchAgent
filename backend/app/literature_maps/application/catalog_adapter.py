"""Narrow bridge to the existing paper-catalog search boundary.

The map application does not own a second crawler or source registry.  This
adapter only turns the existing ``CatalogSearchAdapter``/``CatalogSearchGraph``
composition seam into the small metadata contract the map service needs.  A
runtime may inject a resolver-backed callable; without one, an official scope
is reported as unavailable instead of treating a Semantic Scholar venue label
as proof of conference membership.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from backend.app.paper_discovery.domain.source_authority import (
    CANONICAL_SOURCE_IDS,
    SOURCE_ID_ALIASES,
)

SUPPORTED_SOURCE_IDS = frozenset(CANONICAL_SOURCE_IDS)
SUPPORTED_CONFERENCE_IDS = frozenset({
    "usenix-security", "ieee-sp", "ccs", "ndss",
})
# These are the catalog routes that can attest a conference membership.  The
# aggregate sources remain valid standalone source selectors, but they are not
# silently treated as official conference membership evidence.
SOURCE_CONFERENCE_COMPATIBILITY = {
    "usenix": frozenset({"usenix-security"}),
    "dblp": frozenset({"usenix-security"}),
    "ieee_sp": frozenset({"ieee-sp"}),
    "ccs": frozenset({"ccs"}),
    "ndss": frozenset({"ndss"}),
}
CONFERENCE_SOURCE_IDS = {
    conference: tuple(source for source, conferences in SOURCE_CONFERENCE_COMPATIBILITY.items() if conference in conferences)
    for conference in SUPPORTED_CONFERENCE_IDS
}
CONFERENCE_ALIASES = {
    "usenix": "usenix-security",
    "sp": "ieee-sp",
    "ieee_s&p": "ieee-sp",
    "acm-ccs": "ccs",
    "acm_ccs": "ccs",
}


def canonical_source(value: object) -> str:
    raw = str(value or "").strip().casefold()
    return SOURCE_ID_ALIASES.get(raw, raw)


def canonical_conference(value: object) -> str:
    raw = str(value or "").strip().casefold()
    return CONFERENCE_ALIASES.get(raw, raw)


def compatible_scope_pairs(source_ids: Iterable[str], conference_ids: Iterable[str]) -> tuple[tuple[str, str | None], ...]:
    """Return deterministic source/conference query pairs after scope validation."""
    sources = tuple(dict.fromkeys(canonical_source(item) for item in source_ids if str(item).strip()))
    conferences = tuple(dict.fromkeys(canonical_conference(item) for item in conference_ids if str(item).strip()))
    if sources and conferences:
        return tuple(
            (source, conference)
            for source in sources
            for conference in conferences
            if conference in SOURCE_CONFERENCE_COMPATIBILITY.get(source, ())
        )
    if sources:
        return tuple((source, None) for source in sources)
    if conferences:
        return tuple((source, conference) for conference in conferences for source in CONFERENCE_SOURCE_IDS.get(conference, ()))
    return (("usenix", None),)


@dataclass(frozen=True)
class CatalogRow:
    """One catalog-attested metadata row.

    ``metadata`` remains the existing Semantic Scholar DTO; the scope fields
    are attestations from the catalog adapter, never inferred from ``venue``.
    """

    metadata: Any
    source_id: str | None = None
    conference_id: str | None = None
    catalog_paper_id: str | None = None
    official_page_url: str | None = None
    official_pdf_url: str | None = None
    prepublication_pdf_url: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    # The catalog search boundary owns this snapshot.  The map service only
    # exposes its allow-listed provenance fields to downstream importers.
    snapshot: Mapping[str, Any] | None = None
    source_kind: str | None = None


class CatalogSourceAdapter:
    """Call the existing catalog search seam through an injectable resolver."""

    def __init__(self, searcher: Callable[..., Any] | None = None, *, semantic_client: Any | None = None, catalog_store: Any | None = None) -> None:
        self.searcher = searcher
        self.semantic_client = semantic_client
        self.catalog_store = catalog_store
        self.last_error: str | None = None

    def search(
        self,
        *,
        query: str,
        source_ids: Iterable[str],
        conference_ids: Iterable[str],
        year_start: int | None = None,
        year_end: int | None = None,
        limit: int = 30,
    ) -> list[CatalogRow]:
        sources = tuple(canonical_source(item) for item in source_ids)
        conferences = tuple(canonical_conference(item) for item in conference_ids)
        if self.searcher is None:
            pairs = compatible_scope_pairs(sources, conferences)
            if (sources and conferences and not pairs) or not pairs:
                self.last_error = "INVALID_MAP_SCOPE"
                return []
            result = []
            errors: list[str] = []
            per_pair_limit = max(1, int(limit))
            for source_id, conference_id in pairs:
                rows = self._existing_catalog_search(
                    query=query,
                    source_ids=(source_id,),
                    conference_ids=(conference_id,) if conference_id else (),
                    year_start=year_start,
                    year_end=year_end,
                    limit=per_pair_limit,
                )
                result.extend(rows)
                if not rows and self.last_error:
                    errors.append(self.last_error)
            if not result and errors:
                self.last_error = errors[0]
            elif result:
                self.last_error = None
        else:
            result = self.searcher(
                query=query,
                source_ids=sources,
                conference_ids=conferences,
                year_start=year_start,
                year_end=year_end,
                limit=limit,
            )
        if self.searcher is not None:
            self.last_error = None
        if isinstance(result, Mapping):
            result = result.get("rows", result.get("metadata", ()))
        if result is None:
            return []
        rows: list[CatalogRow] = []
        for item in result:
            if isinstance(item, CatalogRow):
                rows.append(item)
                continue
            if isinstance(item, Mapping) and "metadata" in item:
                metadata = item.get("metadata")
                snapshot = item.get("snapshot", item.get("catalog_snapshot"))
                source_id = item.get("source_id", snapshot.get("source_id") if isinstance(snapshot, Mapping) else None)
                conference_id = item.get("conference_id", snapshot.get("conference_id") if isinstance(snapshot, Mapping) else None)
                source_kind = item.get("source_kind", snapshot.get("source_kind") if isinstance(snapshot, Mapping) else None)
                catalog_paper_id = item.get("catalog_paper_id", item.get("candidate_id", snapshot.get("catalog_paper_id") if isinstance(snapshot, Mapping) else None))
                official_page_url = item.get("official_page_url", item.get("article_url", snapshot.get("official_page_url", snapshot.get("article_url")) if isinstance(snapshot, Mapping) else None))
                official_pdf_url = item.get("official_pdf_url", item.get("pdf_url", snapshot.get("official_pdf_url", snapshot.get("pdf_url")) if isinstance(snapshot, Mapping) else None))
                prepublication_pdf_url = item.get("prepublication_pdf_url", snapshot.get("prepublication_pdf_url") if isinstance(snapshot, Mapping) else None)
                doi = item.get("doi", snapshot.get("doi") if isinstance(snapshot, Mapping) else None)
                arxiv_id = item.get("arxiv_id", snapshot.get("arxiv_id") if isinstance(snapshot, Mapping) else None)
            else:
                metadata = item
                source_id = None
                conference_id = None
                source_kind = None
                snapshot = None
                catalog_paper_id = None
                official_page_url = None
                official_pdf_url = None
                prepublication_pdf_url = None
                doi = None
                arxiv_id = None
            if metadata is not None:
                rows.append(CatalogRow(
                    metadata=metadata,
                    source_id=canonical_source(source_id) if source_id else None,
                    conference_id=canonical_conference(conference_id) if conference_id else None,
                    source_kind=str(source_kind).strip() if source_kind else None,
                    catalog_paper_id=str(catalog_paper_id).strip() if catalog_paper_id else None,
                    official_page_url=str(official_page_url).strip() if official_page_url else None,
                    official_pdf_url=str(official_pdf_url).strip() if official_pdf_url else None,
                    prepublication_pdf_url=str(prepublication_pdf_url).strip() if prepublication_pdf_url else None,
                    doi=str(doi).strip() if doi else None,
                    arxiv_id=str(arxiv_id).strip() if arxiv_id else None,
                    snapshot=dict(snapshot) if isinstance(snapshot, Mapping) else None,
                ))
        return rows[: max(0, int(limit))]

    def _existing_catalog_search(self, *, query: str, source_ids: tuple[str, ...], conference_ids: tuple[str, ...], year_start: int | None, year_end: int | None, limit: int) -> list[CatalogRow]:
        """Use the existing catalog graph/cache and enrich only real IDs.

        Catalog IDs are never copied into the map's Semantic Scholar identity.
        The existing S2 batch/enrichment contract resolves DOI/arXiv-backed
        catalog records to a real S2 metadata object before a row is admitted.
        """
        try:
            from backend.app.research.application.search_catalog_adapter import CatalogSearchAdapter

            source_scope = source_ids[0] if source_ids else {
                "ieee-sp": "ieee_sp", "ccs": "ccs", "ndss": "ndss",
            }.get(conference_ids[0] if conference_ids else "", "usenix")
            years = tuple(range(int(year_start), int(year_end) + 1)) if year_start is not None and year_end is not None else ()
            search = CatalogSearchAdapter(store=self.catalog_store)
            outcome = search.search(query=query, sources=(source_scope,), max_results=limit, years=years)
            if getattr(outcome, "error_code", None):
                self.last_error = "CATALOG_SOURCE_UNAVAILABLE"
                return []
            store = self.catalog_store or getattr(search, "_store", None)
            lookup = getattr(store, "get_catalog_paper", None)
            enrich = getattr(self.semantic_client, "enrich", None)
            if not callable(lookup) or not callable(enrich):
                self.last_error = "CATALOG_SOURCE_UNAVAILABLE"
                return []
            papers = [lookup(str(identifier)) for identifier in getattr(outcome, "catalog_paper_ids", ())]
            papers = [paper for paper in papers if paper is not None]
            source_kinds = getattr(store, "get_catalog_source_kinds", None)
            scoped_papers = []
            for paper in papers:
                actual_conference = canonical_conference(getattr(paper, "conference_id", None))
                actual_sources = {
                    canonical_source(item)
                    for item in (source_kinds(str(getattr(paper, "catalog_paper_id", ""))) if callable(source_kinds) else ())
                }
                if conference_ids and actual_conference not in conference_ids:
                    continue
                if source_ids and not actual_sources.intersection(source_ids):
                    continue
                scoped_papers.append(paper)
            papers = scoped_papers
            if not papers:
                self.last_error = "CATALOG_SCOPE_UNVERIFIED"
                return []
            rows: list[CatalogRow] = []
            source_id = source_ids[0] if source_ids else source_scope
            conference_id = conferences[0] if (conferences := conference_ids) else None
            matches = enrich(papers)
            matches_by_id = {str(getattr(match, "catalog_paper_id", "")): match for match in matches}
            for paper in papers:
                match = matches_by_id.get(str(getattr(paper, "catalog_paper_id", "")))
                if match is None:
                    continue
                metadata = getattr(match, "metadata", None)
                if metadata is not None:
                    catalog_paper_id = str(getattr(paper, "catalog_paper_id", "") or "") or None
                    actual_sources = tuple(sorted({
                        canonical_source(item)
                        for item in (source_kinds(catalog_paper_id) if callable(source_kinds) else (source_id,))
                    }))
                    actual_source = next((item for item in actual_sources if not source_ids or item in source_ids), source_id)
                    actual_conference = canonical_conference(getattr(paper, "conference_id", None)) or conference_id
                    snapshot = {
                        "catalog_paper_id": catalog_paper_id,
                        "source_id": actual_source,
                        "source_kind": actual_source,
                        "conference_id": actual_conference,
                        "title": getattr(paper, "title", None),
                        "authors": list(getattr(paper, "authors", ()) or ()),
                        "year": getattr(paper, "year", None),
                        "doi": getattr(paper, "doi", None),
                        "arxiv_id": getattr(paper, "arxiv_id", None),
                        "official_page_url": getattr(paper, "official_page_url", None),
                        "official_pdf_url": getattr(paper, "official_pdf_url", None),
                        "prepublication_pdf_url": getattr(paper, "prepublication_pdf_url", None),
                    }
                    rows.append(CatalogRow(
                        metadata,
                        source_id=actual_source,
                        conference_id=actual_conference,
                        source_kind=actual_source,
                        catalog_paper_id=catalog_paper_id,
                        official_page_url=getattr(paper, "official_page_url", None),
                        official_pdf_url=getattr(paper, "official_pdf_url", None),
                        prepublication_pdf_url=getattr(paper, "prepublication_pdf_url", None),
                        doi=getattr(paper, "doi", None),
                        arxiv_id=getattr(paper, "arxiv_id", None),
                        snapshot=snapshot,
                    ))
            if not rows:
                self.last_error = "CATALOG_SOURCE_UNAVAILABLE"
            return rows
        except Exception:  # catalog runtime converts provider/store failures to a stable boundary
            self.last_error = "CATALOG_SOURCE_UNAVAILABLE"
            return []


__all__ = [
    "CONFERENCE_SOURCE_IDS",
    "CONFERENCE_ALIASES",
    "CatalogRow",
    "CatalogSourceAdapter",
    "SOURCE_CONFERENCE_COMPATIBILITY",
    "SUPPORTED_CONFERENCE_IDS",
    "SUPPORTED_SOURCE_IDS",
    "canonical_conference",
    "canonical_source",
    "compatible_scope_pairs",
]
