"""Spec032 Task06: canonical source IDs, authority and shared result envelopes."""

from __future__ import annotations

import json
import sqlite3

import pytest

from backend.app.paper_discovery.domain.paper_discovery import SearchJob, SourceFetchUnit
from backend.app.paper_discovery.domain.source_authority import (
    AUTHORITY_AGGREGATE,
    AUTHORITY_OFFICIAL_DOI,
    AUTHORITY_OFFICIAL_VENUE,
    CANONICAL_SOURCE_IDS,
    DEFAULT_SOURCE_AUTHORITY,
    canonical_source_id,
    may_overwrite,
)
from backend.app.paper_discovery.domain.source_contract import (
    ImportResult,
    SourceResult,
)
from backend.app.paper_discovery.infrastructure.aggregate_source_adapters import (
    CrossrefCatalogAdapter,
    OpenAlexCatalogAdapter,
    SourceRecord,
)
from backend.app.paper_discovery.infrastructure.ccs_paper_parser import (
    CCS_SOURCE_ID,
    CCS_SOURCE_KIND,
)
from backend.app.paper_discovery.infrastructure.ccs_publication_source import CcsPublicationSource
from backend.app.paper_discovery.infrastructure.dblp_publication_source import DBLPPublicationSource
from backend.app.paper_discovery.infrastructure.ieee_sp_paper_parser import IEEE_SP_SOURCE_ID
from backend.app.paper_discovery.infrastructure.ieee_sp_publication_source import IeeeSpPublicationSource
from backend.app.paper_discovery.infrastructure.ndss_publication_source import NdssPublicationSource
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.paper_discovery.infrastructure.source_registry import SourceRegistry
from backend.app.paper_discovery.infrastructure.usenix_publication_source import UsenixAcceptedSource


def test_canonical_source_ids_and_actual_field_authority_are_stable():
    assert {
        "usenix", "dblp", "ieee_sp", "ccs", "ndss", "openalex", "crossref",
    } == CANONICAL_SOURCE_IDS
    assert canonical_source_id("ieee-sp") == "ieee_sp"
    assert canonical_source_id("acm-ccs") == "ccs"
    assert canonical_source_id("acm_ccs") == "ccs"
    assert DEFAULT_SOURCE_AUTHORITY == {
        "usenix": AUTHORITY_OFFICIAL_VENUE,
        "dblp": AUTHORITY_OFFICIAL_VENUE,
        "ieee_sp": AUTHORITY_OFFICIAL_DOI,
        "ccs": AUTHORITY_OFFICIAL_DOI,
        "ndss": AUTHORITY_OFFICIAL_DOI,
        "crossref": AUTHORITY_OFFICIAL_DOI,
        "openalex": AUTHORITY_AGGREGATE,
    }
    assert AUTHORITY_OFFICIAL_VENUE < AUTHORITY_OFFICIAL_DOI < AUTHORITY_AGGREGATE
    assert may_overwrite("openalex", "crossref") is True
    assert may_overwrite("crossref", "openalex") is False
    # Current IEEE/CCS/NDSS adapters are DOI-backed, so they may enrich an
    # aggregate record but must not overwrite an official venue record.
    assert may_overwrite("openalex", "ieee_sp") is True
    assert may_overwrite("usenix", "ieee_sp") is False
    # An old stored alias resolves to the same source rank as its canonical ID.
    assert may_overwrite("acm-ccs", "openalex") is False


def test_parser_and_crossref_adapter_use_canonical_contract_ids():
    assert IEEE_SP_SOURCE_ID == "ieee_sp"
    assert CCS_SOURCE_ID == CCS_SOURCE_KIND == "ccs"
    adapter = CrossrefCatalogAdapter()
    assert adapter.source_id == adapter.source_kind == "crossref"
    assert adapter.authority_rank == AUTHORITY_OFFICIAL_DOI
    record = SourceRecord(
        source_id="acm-ccs", source_record_id="r1", authority_rank=AUTHORITY_OFFICIAL_VENUE,
    )
    assert record.source_id == "ccs"

    sources = (
        UsenixAcceptedSource, DBLPPublicationSource, IeeeSpPublicationSource,
        CcsPublicationSource, NdssPublicationSource, OpenAlexCatalogAdapter,
        CrossrefCatalogAdapter,
    )
    assert {source.source_id for source in sources} == CANONICAL_SOURCE_IDS
    assert {source.contract_schema_version for source in sources} == {"source-contract-v1"}
    # The three current conference adapters enumerate Crossref, so their actual
    # field authority remains DOI metadata until Task07 adds official-page paths.
    assert {
        source.authority_rank
        for source in (IeeeSpPublicationSource, CcsPublicationSource, NdssPublicationSource)
    } == {AUTHORITY_OFFICIAL_DOI}
    registry = SourceRegistry()
    assert registry.get("ieee-sp").authority_rank == IeeeSpPublicationSource.authority_rank
    assert registry.get("acm-ccs").authority_rank == CcsPublicationSource.authority_rank
    assert registry.get("ndss").authority_rank == NdssPublicationSource.authority_rank


def test_shared_result_envelopes_round_trip_and_fail_closed_unknown_source():
    source = SourceResult(
        source_id="ieee-sp", operation="parse_catalog", status="partial",
        coverage={"requested": 2, "completed": 1},
        papers=({"stable_id": "p1"},), error={"code": "RATE_LIMITED", "retryable": True},
        elapsed_ms=12,
    )
    assert SourceResult.from_dict(source.to_dict()) == source
    assert source.to_dict()["source_id"] == "ieee_sp"
    assert source.error_code == "RATE_LIMITED"

    imported = ImportResult(
        candidate_id="p1", status="waiting", identity_verdict="uncertain",
        attempts=2, error="LOGIN_REQUIRED",
    )
    assert ImportResult.from_dict(imported.to_dict()) == imported
    assert imported.to_dict()["schema_version"] == source.to_dict()["schema_version"]

    with pytest.raises(ValueError):
        canonical_source_id("https://evil.example", strict=True)
    with pytest.raises(ValueError):
        SourceResult("https://evil.example", "discover", "completed")
    with pytest.raises(ValueError, match="document_id"):
        ImportResult(candidate_id="p1", status="completed")
    assert json.loads(json.dumps(SourceResult(
        source_id="ccs", operation="parse_catalog", status="completed",
        papers=(SourceRecord("ccs", "r1", AUTHORITY_OFFICIAL_VENUE, title="Paper"),),
    ).to_dict()))["papers"][0]["title"] == "Paper"


def test_publication_sources_expose_the_shared_result_wrapper():
    sources = (
        UsenixAcceptedSource(), DBLPPublicationSource(), IeeeSpPublicationSource(),
        CcsPublicationSource(), NdssPublicationSource(),
    )
    for source in sources:
        result = source.result("discover_units", status="completed")
        assert result.source_id == source.source_id
        assert result.schema_version == "source-contract-v1"
    failed = CcsPublicationSource().parse_catalog_result(None, scope={"year": 2024})
    assert failed.status == "failed"
    assert failed.error_code == "CCS_INVALID_RESPONSE"
    assert failed.scope == {"year": 2024}


def test_store_migrates_legacy_progress_aliases_without_dropping_rows(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    store = PaperDiscoveryStore(path)
    store.create_search_job(SearchJob(
        "s-legacy", "security", expires_at="2099-01-01T00:00:00Z",
        created_at="2098-01-01T00:00:00Z",
    ))
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE search_source_progress RENAME TO search_source_progress_legacy")
        connection.execute("""CREATE TABLE search_source_progress(
            search_id TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            status TEXT NOT NULL,
            cached_units_json TEXT NOT NULL DEFAULT '[]',
            fetching_units_json TEXT NOT NULL DEFAULT '[]',
            completed_units_json TEXT NOT NULL DEFAULT '[]',
            paper_count INTEGER NOT NULL DEFAULT 0,
            error_code TEXT,
            message_code TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(search_id, source_kind))""")
        connection.execute(
            "INSERT INTO search_source_progress VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("s-legacy", "ieee-sp", "completed", "[]", "[]", "[]", 1, None, None, "2098-01-01T00:00:00Z"),
        )
        connection.execute("DROP TABLE search_source_progress_legacy")
        connection.execute("UPDATE schema_meta SET version=2")
    reopened = PaperDiscoveryStore(path)
    progress = reopened.get_source_progress("s-legacy")
    assert len(progress) == 1
    assert progress[0].source_kind == "ieee_sp"


def test_store_normalizes_old_aliases_on_write_and_read(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    unit = SourceFetchUnit(
        fetch_unit_id="ieee-sp|sp|2024", source_kind="ieee-sp", conference_id="ieee-sp",
        year=2024, unit_key="sp:2024", created_at="2099-01-01T00:00:00Z",
        updated_at="2099-01-01T00:00:00Z",
    )
    store.save_fetch_unit(unit)
    loaded = store.get_fetch_unit(unit.fetch_unit_id)
    assert loaded is not None
    assert loaded.source_kind == "ieee_sp"
    with store._connect() as connection:
        raw = connection.execute(
            "SELECT source_kind FROM source_fetch_units WHERE fetch_unit_id=?",
            (unit.fetch_unit_id,),
        ).fetchone()
    assert raw[0] == "ieee_sp"
