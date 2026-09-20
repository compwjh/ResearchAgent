"""来源 ID 归一化与字段权威等级契约。"""

from backend.app.paper_discovery.domain.source_authority import (
    AUTHORITY_AGGREGATE,
    AUTHORITY_OFFICIAL_DOI,
    AUTHORITY_OFFICIAL_VENUE,
    DEFAULT_SOURCE_AUTHORITY,
    canonical_source_id,
    may_overwrite,
)
from backend.app.paper_discovery.infrastructure.source_registry import SourceRegistry


def test_current_source_authority_matches_adapter_backing_sources():
    assert canonical_source_id("ieee-sp") == "ieee_sp"
    assert canonical_source_id("acm-ccs") == "ccs"
    assert DEFAULT_SOURCE_AUTHORITY == {
        "usenix": AUTHORITY_OFFICIAL_VENUE,
        "dblp": AUTHORITY_OFFICIAL_VENUE,
        "ieee_sp": AUTHORITY_OFFICIAL_DOI,
        "ccs": AUTHORITY_OFFICIAL_DOI,
        "ndss": AUTHORITY_OFFICIAL_DOI,
        "crossref": AUTHORITY_OFFICIAL_DOI,
        "openalex": AUTHORITY_AGGREGATE,
    }


def test_doi_backed_sources_enrich_aggregate_but_do_not_replace_official_venue():
    assert may_overwrite("openalex", "ieee_sp") is True
    assert may_overwrite("usenix", "ieee_sp") is False
    assert may_overwrite("acm-ccs", "openalex") is False


def test_registry_exposes_canonical_entries_and_protects_required_sources():
    registry = SourceRegistry()
    assert registry.get("ieee-sp").source_id == "ieee_sp"
    assert registry.get("ieee_sp").authority_rank == AUTHORITY_OFFICIAL_DOI
    assert registry.get("openalex").authority_rank == AUTHORITY_AGGREGATE
    try:
        registry.set_enabled("usenix", False, via_external=True)
    except RuntimeError as exc:
        assert getattr(exc, "code", None) == "SOURCE_TOGGLE_FORBIDDEN"
    else:  # pragma: no cover - makes the protection failure explicit
        raise AssertionError("required source must reject external toggles")
