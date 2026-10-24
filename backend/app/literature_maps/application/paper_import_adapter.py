"""Server-side source selection for literature-map imports.

This module is a metadata adapter only.  It reads the existing catalog
snapshot and, when needed, asks the injected OA metadata resolver for an
address.  The production runtime composes the existing arXiv fallback first
and Semantic Scholar OA second.  The returned address is always handed to ``import_candidate``;
this module never downloads, follows redirects, or expands a host allowlist.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from backend.app.literature_maps.domain.models import MapPaper
from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi
from backend.app.paper_discovery.infrastructure.arxiv_adapter import (
    arxiv_identity_matches,
    normalize_arxiv_id,
)


class PaperImportSourceAdapter:
    """Resolve one map node against the persisted catalog/OA metadata chain."""

    def __init__(
        self,
        *,
        catalog_store: Any | None = None,
        oa_resolver: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
    ) -> None:
        self.catalog_store = catalog_store
        self.oa_resolver = oa_resolver

    def resolve(self, node: MapPaper) -> Mapping[str, Any]:
        source = self._catalog_source(node)
        catalog_identity_proven = _catalog_identity_proven(node, source)
        if _has_pdf(source) and catalog_identity_proven:
            return source
        if _has_pdf(source):
            # A catalog URL without a server-owned catalog ID or a matching
            # DOI/arXiv identity must not bind this node to another paper.
            source = _without_pdf(source)
        if not catalog_identity_proven:
            source.pop("catalog_paper_id", None)
        if self.oa_resolver is not None:
            oa = self.oa_resolver(node.to_dict())
            if isinstance(oa, Mapping):
                merged = dict(source)
                merged.update(dict(oa))
                if not catalog_identity_proven:
                    merged.pop("catalog_paper_id", None)
                return merged
        source.setdefault("error_code", "PDF_NOT_FOUND")
        return source

    def _catalog_source(self, node: MapPaper) -> dict[str, Any]:
        provenance = node.provenance if isinstance(node.provenance, Mapping) else {}
        snapshot = provenance.get("catalog_snapshot")
        frozen: dict[str, Any] = {}
        if isinstance(snapshot, Mapping):
            frozen.update(dict(snapshot))
        frozen.update({
            "catalog_paper_id": node.catalog_paper_id or provenance.get("catalog_paper_id"),
            "doi": provenance.get("doi") or node.external_ids.get("doi"),
            "arxiv_id": provenance.get("arxiv_id") or node.external_ids.get("arxiv"),
            "official_pdf_url": provenance.get("official_pdf_url") or frozen.get("official_pdf_url"),
            "prepublication_pdf_url": provenance.get("prepublication_pdf_url") or frozen.get("prepublication_pdf_url"),
            "source_kind": provenance.get("source") or provenance.get("source_kind"),
        })
        frozen = {key: value for key, value in frozen.items() if value is not None}
        # The map node is a server-frozen catalog snapshot.  Prefer its
        # official/prepublication addresses so a later catalog refresh cannot
        # silently change what a user's click imports.
        if frozen.get("official_pdf_url") or frozen.get("prepublication_pdf_url"):
            return frozen
        store = self.catalog_store
        if store is None:
            return frozen
        get_paper = getattr(store, "get_catalog_paper", None)
        list_papers = getattr(store, "list_catalog_papers", None)
        paper = None
        explicit_id = node.catalog_paper_id or provenance.get("catalog_paper_id")
        if explicit_id and callable(get_paper):
            paper = get_paper(str(explicit_id))
            if paper is None:
                return {"error_code": "IMPORT_IDENTITY_CONFLICT"}
        if paper is None and callable(list_papers):
            conference_id = node.provenance.get("conference_id")
            years = [node.year] if node.year is not None else None
            kwargs = {"index_status": None}
            try:
                papers = list(list_papers([conference_id] if conference_id else None, years, **kwargs))
            except TypeError:
                papers = list(list_papers([conference_id] if conference_id else None, years))
            paper = self._match(node, papers)
        if paper is None:
            return {}
        source = {
            "catalog_paper_id": _value(paper, "catalog_paper_id"),
            "doi": _value(paper, "doi"),
            "arxiv_id": _value(paper, "arxiv_id"),
            "official_pdf_url": _value(paper, "official_pdf_url"),
            "prepublication_pdf_url": _value(paper, "prepublication_pdf_url"),
            "source_kind": provenance.get("source"),
        }
        merged = dict(frozen)
        merged.update({key: value for key, value in source.items() if value is not None})
        return merged

    @staticmethod
    def _match(node: MapPaper, papers: list[Any]) -> Any | None:
        ids = node.external_ids
        expected_doi = normalize_doi(ids.get("doi"))
        expected_arxiv = normalize_arxiv_id(ids.get("arxiv"))
        matches: list[Any] = []
        for paper in papers:
            doi = normalize_doi(_value(paper, "doi"))
            arxiv = normalize_arxiv_id(_value(paper, "arxiv_id"))
            if (
                (expected_doi and doi and expected_doi == doi)
                or (expected_arxiv and arxiv and arxiv_identity_matches(expected_arxiv, arxiv))
            ):
                matches.append(paper)
        if len(matches) == 1:
            return matches[0]
        return None


def _value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _has_pdf(source: Mapping[str, Any]) -> bool:
    return any(source.get(key) for key in ("pdf_url", "official_pdf_url", "prepublication_pdf_url"))


def _without_pdf(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in source.items()
        if key not in {"pdf_url", "official_pdf_url", "prepublication_pdf_url"}
    }


def _catalog_identity_proven(node: MapPaper, source: Mapping[str, Any]) -> bool:
    catalog_id = str(source.get("catalog_paper_id") or "").strip()
    if not catalog_id:
        return _matching_external_id(node, source)
    if catalog_id == str(node.external_ids.get("semantic_scholar") or "").strip():
        return False
    server_catalog_id = str(node.catalog_paper_id or node.provenance.get("catalog_paper_id") or "").strip()
    if server_catalog_id:
        return catalog_id == server_catalog_id
    return _matching_external_id(node, source)


def _matching_external_id(node: MapPaper, source: Mapping[str, Any]) -> bool:
    node_doi = normalize_doi(node.external_ids.get("doi"))
    source_doi = normalize_doi(source.get("doi"))
    if node_doi and source_doi and node_doi == source_doi:
        return True
    node_arxiv = normalize_arxiv_id(node.external_ids.get("arxiv")) or ""
    source_arxiv = normalize_arxiv_id(source.get("arxiv_id") or source.get("arxiv")) or ""
    return bool(node_arxiv and source_arxiv and arxiv_identity_matches(node_arxiv, source_arxiv))


__all__ = ["PaperImportSourceAdapter"]
