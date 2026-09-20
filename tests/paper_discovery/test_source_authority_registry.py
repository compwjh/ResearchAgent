"""Spec032 Task05：权威统一 / 来源注册表 / source_kind CHECK 迁移 的回归测试。

锁定：
- 权威方向唯一：数值越小越权威（OFFICIAL_VENUE=10 < OFFICIAL_DOI=20 < AGGREGATE=30）。
- 三会议 parser 与聚合 adapter 引用同一套共享常量（domain/source_authority）。
- 官方字段不被低权威来源覆盖；低权威只补缺失字段；聚合源权威低于官方源。
- SourceRegistry：枚举 / 按 kind 过滤 / 服务端配置关闭 / 外部输入关闭必需源返回 409。
- search_source_progress 的 source_kind CHECK 已扩展到新来源，且迁移不丢数据。
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.app.paper_discovery.domain.source_authority import (
    AUTHORITY_AGGREGATE,
    AUTHORITY_OFFICIAL_DOI,
    AUTHORITY_OFFICIAL_VENUE,
    SOURCE_KINDS,
    may_overwrite,
)
from backend.app.paper_discovery.infrastructure.aggregate_source_adapters import (
    AUTHORITY_AGGREGATE as AGG_AUTHORITY,
)
from backend.app.paper_discovery.infrastructure.aggregate_source_adapters import (
    AUTHORITY_OFFICIAL,
    SourceRecord,
    merge_source_records,
)
from backend.app.paper_discovery.infrastructure.ccs_paper_parser import (
    AUTHORITY_AGGREGATOR as CCS_AGG,
)
from backend.app.paper_discovery.infrastructure.ccs_paper_parser import (
    AUTHORITY_OFFICIAL_DOI as CCS_DOI,
)
from backend.app.paper_discovery.infrastructure.ccs_paper_parser import (
    AUTHORITY_OFFICIAL_VENUE as CCS_VENUE,
)
from backend.app.paper_discovery.infrastructure.ccs_paper_parser import (
    CCS_AGGREGATOR_AUTHORITY,
    CCS_OFFICIAL_DOI_AUTHORITY,
    CcsCatalogRecord,
    CcsEnrichment,
    merge_enrichment,
)
from backend.app.paper_discovery.infrastructure.source_registry import (
    SourceRegistry,
    SourceToggleForbiddenError,
)

# --------------------------------------------------------------------------
# 任务 1：权威方向统一
# --------------------------------------------------------------------------

def test_authority_direction_is_smaller_is_higher():
    assert AUTHORITY_OFFICIAL_VENUE < AUTHORITY_OFFICIAL_DOI < AUTHORITY_AGGREGATE
    assert AUTHORITY_AGGREGATE > AUTHORITY_OFFICIAL_DOI > AUTHORITY_OFFICIAL_VENUE


def test_parsers_and_aggregate_share_same_constants():
    assert CCS_OFFICIAL_DOI_AUTHORITY == AUTHORITY_OFFICIAL_DOI
    assert CCS_AGGREGATOR_AUTHORITY == AUTHORITY_AGGREGATE
    assert CCS_VENUE == AUTHORITY_OFFICIAL_VENUE
    assert CCS_DOI == AUTHORITY_OFFICIAL_DOI
    assert CCS_AGG == AUTHORITY_AGGREGATE
    assert AUTHORITY_OFFICIAL == AUTHORITY_OFFICIAL_VENUE
    assert AGG_AUTHORITY == AUTHORITY_AGGREGATE


def test_may_overwrite_respects_direction():
    assert may_overwrite(None, "openalex") is True
    assert may_overwrite("crossref", "openalex") is False
    assert may_overwrite("crossref", "usenix") is True
    assert may_overwrite("unknown_source", "openalex") is False
    assert may_overwrite("unknown_source", "usenix") is False


def test_merge_source_records_official_not_overwritten_by_aggregate():
    official = SourceRecord(
        source_id="usenix", source_record_id="u1", authority_rank=AUTHORITY_OFFICIAL_VENUE,
        title="Official Title", abstract="Official abstract", keywords=("k",), authors=("a",),
        year=2024, doi="10.1000/x",
    )
    agg = SourceRecord(
        source_id="openalex", source_record_id="W1", authority_rank=AGG_AUTHORITY,
        title="Agg Title", abstract="Agg abstract", keywords=("ak",), authors=("aa",),
        year=2024, doi="10.1000/x",
    )
    merged, filled = merge_source_records(official, agg)
    assert merged.title == "Official Title"
    assert merged.abstract == "Official abstract"
    assert filled == []


def test_merge_source_records_low_authority_only_fills_missing():
    official = SourceRecord(
        source_id="usenix", source_record_id="u1", authority_rank=AUTHORITY_OFFICIAL_VENUE,
        title="Official Title", abstract="", year=2024, doi="10.1000/x",
    )
    agg = SourceRecord(
        source_id="openalex", source_record_id="W1", authority_rank=AGG_AUTHORITY,
        title="Agg Title", abstract="Agg abstract", keywords=("ak",), authors=("aa",),
        year=2024, doi="10.1000/x",
    )
    merged, filled = merge_source_records(official, agg)
    assert merged.title == "Official Title"
    assert merged.abstract == "Agg abstract"
    assert set(filled) == {"abstract", "keywords", "authors"}


def test_ccs_merge_enrichment_low_authority_never_overwrites():
    # 用真实 parser 的记录类型：OpenAlex 是聚合来源（权威最低），不得覆盖官方 DOI 源字段。
    authoritative = CcsCatalogRecord(
        doi="10.1145/1", title="T", authors=("A B",), year=2024,
        container_title="CCS", article_url="https://dl.acm.org/doi/10.1145/1",
        abstract="官方摘要", keywords=("官方关键词",), pdf_url="https://dl.acm.org/x",
        provenance={"abstract": "acm_ccs_page", "keywords": "acm_ccs_page"},
    )
    enrichment = CcsEnrichment(
        doi="10.1145/1", abstract="OpenAlex 摘要", keywords=("security",),
        pdf_url="https://dl.acm.org/x.pdf",
    )
    merged = merge_enrichment(authoritative, enrichment)
    assert merged.abstract == "官方摘要"
    assert merged.keywords == ("官方关键词",)
    assert merged.pdf_url == "https://dl.acm.org/x"


# --------------------------------------------------------------------------
# 任务 2：SourceRegistry
# --------------------------------------------------------------------------

def test_registry_enumerates_all_builtin_sources():
    registry = SourceRegistry()
    assert len(registry.list_all()) == 7
    ids = {e.source_id for e in registry.list_all()}
    assert ids == {"usenix", "dblp", "ieee_sp", "ccs", "ndss", "openalex", "crossref"}


def test_registry_get_and_filter_by_kind():
    registry = SourceRegistry()
    usenix = registry.get("usenix")
    assert usenix is not None
    assert usenix.source_kind == "usenix"
    assert usenix.authority_rank == AUTHORITY_OFFICIAL_VENUE
    assert usenix.enabled is True
    assert usenix.required is True
    ieee = registry.list_by_kind("ieee_sp")
    assert [e.source_id for e in ieee] == ["ieee_sp"]
    assert registry.get("openalex").required is False
    assert registry.get("crossref").authority_rank == AUTHORITY_OFFICIAL_DOI


def test_registry_external_toggle_of_required_source_is_forbidden():
    registry = SourceRegistry()
    with pytest.raises(SourceToggleForbiddenError):
        registry.set_enabled("usenix", False, via_external=True)
    with pytest.raises(SourceToggleForbiddenError):
        registry.set_enabled("ccs", True, via_external=True)
    updated = registry.set_enabled("openalex", False, via_external=True)
    assert updated.enabled is False
    assert registry.get("openalex").enabled is False


def test_registry_server_config_can_disable_sources():
    registry = SourceRegistry(disabled_by_config=["openalex", "crossref"])
    assert registry.get("openalex").enabled is False
    assert registry.get("crossref").enabled is False
    assert registry.get("usenix").enabled is True
    assert registry.get("nonexistent") is None


# --------------------------------------------------------------------------
# 任务 3：source_kind CHECK 扩展 + 迁移
# --------------------------------------------------------------------------

def test_migrate_to_v3_expands_check_and_preserves_data():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE schema_meta(version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_meta(version) VALUES(2)")
    conn.execute("CREATE TABLE search_jobs(search_id TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO search_jobs(search_id) VALUES('s1')")
    conn.execute(
        """CREATE TABLE search_source_progress(
            search_id TEXT NOT NULL REFERENCES search_jobs(search_id) ON DELETE RESTRICT,
            source_kind TEXT NOT NULL CHECK(source_kind IN ('usenix','dblp')),
            status TEXT NOT NULL DEFAULT 'queued',
            cached_units_json TEXT NOT NULL DEFAULT '[]',
            fetching_units_json TEXT NOT NULL DEFAULT '[]',
            completed_units_json TEXT NOT NULL DEFAULT '[]',
            paper_count INTEGER NOT NULL DEFAULT 0,
            error_code TEXT, message_code TEXT, updated_at TEXT NOT NULL,
            PRIMARY KEY(search_id, source_kind))"""
    )
    conn.execute(
        "INSERT INTO search_source_progress(search_id, source_kind, status, updated_at) "
        "VALUES('s1','usenix','completed','2026-01-01')"
    )
    conn.commit()

    from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
    PaperDiscoveryStore._migrate_to_v3(conn)

    rows = conn.execute(
        "SELECT search_id, source_kind, status FROM search_source_progress"
    ).fetchall()
    assert rows == [("s1", "usenix", "completed")]
    conn.execute(
        "INSERT INTO search_source_progress(search_id, source_kind, status, updated_at) "
        "VALUES('s1','ccs','queued','2026-01-01')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO search_source_progress(search_id, source_kind, status, updated_at) "
            "VALUES('s1','bogus','queued','2026-01-01')"
        )
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='search_source_progress'"
    ).fetchone()[0]
    for kind in ("ieee_sp", "ccs", "ndss", "openalex", "crossref"):
        assert kind in sql


def test_fresh_store_accepts_all_source_kinds(tmp_path):
    from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore

    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    with store._connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO search_jobs(search_id, query, created_at, expires_at, updated_at) "
            "VALUES('s1','q','2026-01-01','2026-12-31','2026-01-01')"
        )
        for kind in sorted(SOURCE_KINDS):
            conn.execute(
                "INSERT INTO search_source_progress(search_id, source_kind, status, updated_at) "
                "VALUES('s1',?, 'queued','2026-01-01')", (kind,)
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO search_source_progress(search_id, source_kind, status, updated_at) "
                "VALUES('s1','bogus','queued','2026-01-01')"
            )
