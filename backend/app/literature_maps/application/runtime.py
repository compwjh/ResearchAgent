"""Composition root for the literature-map service."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from backend.app.literature_maps.application.import_bridge import LiteratureMapImportBridge
from backend.app.literature_maps.application.analysis import MapAnalysisService
from backend.app.literature_maps.application.paper_import_adapter import PaperImportSourceAdapter
from backend.app.literature_maps.application.service import LiteratureMapService
from backend.app.literature_maps.domain.import_diagnostics import resolver_failure
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.memory.repository import OWNER_ID, MemoryRepository
from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_doi
from backend.app.paper_discovery.infrastructure.arxiv_adapter import (
    arxiv_identity_matches,
    normalize_arxiv_id,
)

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
    """Use the existing arXiv/S2 OA metadata adapters without downloading."""
    from backend.app.api import common
    from backend.app.paper_discovery.infrastructure.arxiv_adapter import ArxivFallbackAdapter
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
    # never derive trust from an OA URL returned by either metadata provider.
    allowed_hosts.update(builtin_allowed_hosts("arxiv"))

    resolver_codes: list[str] = []
    resolver_retryable = False
    arxiv_identity_conflict = False
    raw_arxiv_id = candidate.get("arxiv_id")
    arxiv_id = normalize_arxiv_id(raw_arxiv_id)
    invalid_arxiv_id = bool(str(raw_arxiv_id or "").strip()) and arxiv_id is None
    if invalid_arxiv_id:
        resolver_codes.append("ARXIV_IDENTITY_CONFLICT")
        arxiv_identity_conflict = True
    arxiv_result = None
    if not invalid_arxiv_id:
        try:
            if arxiv_id:
                arxiv_result = ArxivFallbackAdapter().lookup_by_id(
                    arxiv_id,
                    str(candidate.get("title") or ""),
                    candidate.get("authors") or (),
                    candidate.get("year"),
                )
            else:
                arxiv_result = ArxivFallbackAdapter().lookup(
                    str(candidate.get("title") or ""),
                    candidate.get("authors") or (),
                    candidate.get("year"),
                )
        except Exception:
            resolver_codes.append("ARXIV_UNAVAILABLE")
            resolver_retryable = True
    if not invalid_arxiv_id:
        resolver_retryable = resolver_retryable or bool(getattr(arxiv_result, "retryable", False))
        arxiv_match = getattr(arxiv_result, "match", None)
        arxiv_pdf_url = getattr(arxiv_match, "pdf_url", None)
        if arxiv_match is not None:
            match_arxiv_id = normalize_arxiv_id(getattr(arxiv_match, "arxiv_id", None))
            if arxiv_id and not arxiv_identity_matches(arxiv_id, match_arxiv_id):
                resolver_codes.append("ARXIV_IDENTITY_CONFLICT")
                arxiv_identity_conflict = True
            elif isinstance(arxiv_pdf_url, str) and arxiv_pdf_url.strip():
                return {
                    "pdf_url": arxiv_pdf_url.strip(),
                    "arxiv_id": getattr(arxiv_match, "arxiv_id", None),
                    "source_kind": "arxiv",
                    "resolver": "arxiv",
                }
        arxiv_code = getattr(arxiv_result, "code", None)
        if arxiv_code:
            resolver_codes.append(str(arxiv_code))
            arxiv_identity_conflict = arxiv_identity_conflict or arxiv_code == "ARXIV_IDENTITY_CONFLICT"
        elif arxiv_match is None and arxiv_result is not None:
            resolver_codes.append("ARXIV_MATCH_UNCERTAIN")

    result = SemanticScholarFallbackAdapter().lookup(candidate, allowed_hosts=allowed_hosts)
    match = getattr(result, "match", None)
    pdf_url = getattr(match, "pdf_url", None)
    result_code = getattr(result, "code", None)
    if result_code:
        resolver_codes.append(str(result_code))
    if not match or not pdf_url:
        return _resolver_failure(
            resolver_codes,
            retryable=resolver_retryable or bool(getattr(result, "retryable", False)),
        )
    if not _candidate_identity_matches(candidate, match):
        resolver_codes.append("OA_IDENTITY_CONFLICT")
        return _resolver_failure(
            resolver_codes,
            retryable=resolver_retryable or bool(getattr(result, "retryable", False)),
        )
    if arxiv_identity_conflict:
        return _resolver_failure(
            resolver_codes,
            retryable=resolver_retryable or bool(getattr(result, "retryable", False)),
        )
    return {
        "pdf_url": str(pdf_url).strip(),
        "doi": getattr(match, "doi", None),
        "arxiv_id": getattr(match, "arxiv_id", None),
        "semantic_scholar_id": getattr(match, "paper_id", None),
        "source_kind": "arxiv" if getattr(match, "arxiv_id", None) else candidate.get("source_kind"),
        "resolver": "semantic_scholar",
    }


def _resolver_failure(codes: list[str], *, retryable: bool = False) -> dict[str, object]:
    return resolver_failure([str(code) for code in codes if str(code).strip()], retryable=retryable)


def _candidate_identity_matches(candidate: dict, match: object) -> bool:
    raw_arxiv = candidate.get("arxiv_id")
    candidate_arxiv = normalize_arxiv_id(raw_arxiv)
    if raw_arxiv and candidate_arxiv is None:
        return False
    if candidate_arxiv:
        return arxiv_identity_matches(candidate_arxiv, getattr(match, "arxiv_id", None))
    candidate_doi = normalize_doi(candidate.get("doi"))
    match_doi = normalize_doi(getattr(match, "doi", None))
    return not candidate_doi or candidate_doi == match_doi


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
        _service.analysis_service = MapAnalysisService(
            store=store,
            executor=_executor,
            memory_repository=MemoryRepository(),
        )
    return _service


def recover_literature_map_jobs() -> int:
    service = get_literature_map_service()
    recovered = service.recover()
    analysis = getattr(service, "analysis_service", None)
    if analysis is not None:
        recovered += analysis.recover()
    return recovered


def reset_literature_map_runtime() -> None:
    global _service, _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
    _service = None
    _executor = None


__all__ = ["get_literature_map_service", "recover_literature_map_jobs", "reset_literature_map_runtime"]
