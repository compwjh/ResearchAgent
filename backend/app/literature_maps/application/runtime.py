"""Composition root for the literature-map service."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from backend.app.literature_maps.application.import_bridge import LiteratureMapImportBridge
from backend.app.literature_maps.application.paper_import_adapter import PaperImportSourceAdapter
from backend.app.literature_maps.application.service import LiteratureMapService
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.memory.repository import OWNER_ID, MemoryRepository

_service: LiteratureMapService | None = None
_executor: ThreadPoolExecutor | None = None


def _existing_paper_import(snapshot: dict, source_url: str):
    """Call the one existing secure paper/KB import boundary.

    Map nodes are metadata snapshots.  OA resolution is deliberately deferred
    to this user-triggered path; no map read invokes this callable.
    """
    from backend.app.api import common
    from backend.app.paper_discovery.application.paper_import import import_candidate

    candidate = dict(snapshot)
    # ``source_url`` is selected by the server-side source adapter.  Never
    # replace the frozen S2/catalog source page with it; the existing import
    # chain consumes this explicit PDF candidate and owns all DNS/redirect/
    # PDF validation.
    selected_pdf_url = candidate.get("pdf_url")
    if not isinstance(selected_pdf_url, str) or not selected_pdf_url.strip():
        # The bridge must resolve an official/OA PDF before this callable is
        # entered; a missing field is never filled from a landing page.
        raise RuntimeError("IMPORT_SOURCE_UNRESOLVED")
    candidate["pdf_url"] = selected_pdf_url.strip()
    external_ids = candidate.get("external_ids")
    if isinstance(external_ids, dict):
        candidate.setdefault("doi", external_ids.get("doi"))
        candidate.setdefault("arxiv_id", external_ids.get("arxiv"))
    provenance = candidate.get("provenance")
    if isinstance(provenance, dict):
        candidate.setdefault("conference_id", provenance.get("conference_id"))
        candidate.setdefault("source_kind", provenance.get("source"))
    return import_candidate(
        candidate,
        common.article_settings,
        common._paper_candidate_hosts(candidate),
    )


def _existing_oa_resolver(snapshot: dict) -> dict | None:
    """Use the existing OA metadata adapter without creating a download path."""
    from backend.app.api import common
    from backend.app.paper_discovery.infrastructure.semantic_scholar_adapter import (
        SemanticScholarFallbackAdapter,
    )
    from backend.app.paper_discovery.infrastructure.source_registry import builtin_allowed_hosts

    candidate = dict(snapshot)
    external_ids = candidate.get("external_ids")
    if isinstance(external_ids, dict):
        candidate.setdefault("doi", external_ids.get("doi"))
        candidate.setdefault("arxiv_id", external_ids.get("arxiv"))
    provenance = candidate.get("provenance")
    if isinstance(provenance, dict):
        candidate.setdefault("source_kind", provenance.get("source") or provenance.get("source_kind"))
        candidate.setdefault("conference_id", provenance.get("conference_id"))
    allowed_hosts = common._paper_candidate_hosts(candidate)
    # Match the existing import fallback's fixed arXiv source registration;
    # never derive trust from the OA URL returned by Semantic Scholar.
    allowed_hosts.update(builtin_allowed_hosts("arxiv"))
    result = SemanticScholarFallbackAdapter().lookup(candidate, allowed_hosts=allowed_hosts)
    match = getattr(result, "match", None)
    pdf_url = getattr(match, "pdf_url", None)
    if getattr(result, "code", None) or not match or not pdf_url:
        return None
    return {
        "pdf_url": pdf_url,
        "doi": getattr(match, "doi", None),
        "arxiv_id": getattr(match, "arxiv_id", None),
        "semantic_scholar_id": getattr(match, "paper_id", None),
        "source_kind": "arxiv" if getattr(match, "arxiv_id", None) else candidate.get("source_kind"),
    }


def get_literature_map_service() -> LiteratureMapService:
    global _service, _executor
    if _service is None:
        _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="literature-map")
        store = LiteratureMapStore()
        from backend.app.api import common

        source_adapter = PaperImportSourceAdapter(
            catalog_store=common._paper_store(),
            oa_resolver=_existing_oa_resolver,
        )
        bridge = LiteratureMapImportBridge(
            importer=_existing_paper_import,
            store=store,
            owner_id=OWNER_ID,
            source_resolver=source_adapter.resolve,
        )
        _service = LiteratureMapService(
            store=store,
            executor=_executor,
            project_lookup=lambda project_id, owner_id: MemoryRepository().get_project(project_id, owner_id),
            import_bridge=bridge.import_node,
        )
    return _service


def recover_literature_map_jobs() -> int:
    return get_literature_map_service().recover()


def reset_literature_map_runtime() -> None:
    global _service, _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
    _service = None
    _executor = None


__all__ = ["get_literature_map_service", "recover_literature_map_jobs", "reset_literature_map_runtime"]
