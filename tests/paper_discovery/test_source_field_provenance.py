"""Spec032：字段级 provenance（`field_provenance` 表）回归测试。

锁定 Spec032 的硬约束：
- 字段无归属来源时可写；已有归属时只有**更高权威**（数值更小）才能覆盖。
- 低权威来源**只补缺失**，绝不覆盖高权威已写入的字段。
- `observed_at` 必须落盘，可按论文回查每个字段来自哪个源。
- v4 迁移幂等，且不丢既有数据。
"""
from __future__ import annotations

import sqlite3

from backend.app.paper_discovery.domain.source_authority import may_overwrite
from backend.app.paper_discovery.infrastructure.paper_discovery_store import (
    SCHEMA_VERSION,
    PaperDiscoveryStore,
)


def _store(tmp_path):
    return PaperDiscoveryStore(tmp_path / "state.sqlite3")


def test_schema_is_at_least_v4_with_field_provenance_table(tmp_path):
    """v4：`field_provenance` 表与索引必须存在。"""
    store = _store(tmp_path)
    assert SCHEMA_VERSION >= 4
    with sqlite3.connect(store.database_path) as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "field_provenance" in tables


def test_first_write_is_allowed_and_readable(tmp_path):
    """字段首次落盘：可写，且能按论文回查来源与 observed_at。"""
    store = _store(tmp_path)
    assert store.save_field_provenance(
        "paper-1", "title", "usenix", source_record_id="rec-1", now="2026-09-19T00:00:00Z"
    ) is True
    provenance = store.get_field_provenance("paper-1")
    assert provenance["title"]["source_id"] == "usenix"
    assert provenance["title"]["source_record_id"] == "rec-1"
    assert provenance["title"]["observed_at"] == "2026-09-19T00:00:00Z"


def test_lower_authority_cannot_overwrite_higher(tmp_path):
    """低权威（聚合源）不能覆盖已由官方源写入的字段。"""
    store = _store(tmp_path)
    assert store.save_field_provenance("paper-2", "abstract", "usenix") is True
    # openalex 是聚合源（30），权威低于官方会场（10）→ 拒绝覆盖。
    assert store.save_field_provenance("paper-2", "abstract", "openalex") is False
    assert store.get_field_provenance("paper-2")["abstract"]["source_id"] == "usenix"


def test_higher_authority_can_overwrite_lower(tmp_path):
    """高权威（官方会场）可以覆盖低权威（聚合源）已写入的字段。"""
    store = _store(tmp_path)
    assert store.save_field_provenance("paper-3", "doi", "openalex") is True
    assert store.save_field_provenance("paper-3", "doi", "usenix") is True
    assert store.get_field_provenance("paper-3")["doi"]["source_id"] == "usenix"


def test_lower_authority_fills_only_missing_fields(tmp_path):
    """低权威只补缺失字段：已有字段不动，缺失字段照写。"""
    store = _store(tmp_path)
    store.save_field_provenance("paper-4", "title", "usenix")
    # abstract 尚无归属 → 聚合源可补
    assert store.save_field_provenance("paper-4", "abstract", "openalex") is True
    # title 已属官方 → 聚合源不可写
    assert store.save_field_provenance("paper-4", "title", "openalex") is False
    provenance = store.get_field_provenance("paper-4")
    assert provenance["title"]["source_id"] == "usenix"
    assert provenance["abstract"]["source_id"] == "openalex"


def test_provenance_is_scoped_per_paper(tmp_path):
    """provenance 按论文隔离，不会串到别的论文。"""
    store = _store(tmp_path)
    store.save_field_provenance("paper-5", "title", "usenix")
    assert store.get_field_provenance("paper-6") == {}


def test_migration_is_idempotent_and_keeps_rows(tmp_path):
    """重开库（再跑一次迁移）不丢数据、不报错。"""
    db_path = tmp_path / "state.sqlite3"
    store = PaperDiscoveryStore(db_path)
    store.save_field_provenance("paper-7", "title", "ccs", now="2026-09-19T00:00:00Z")
    reopened = PaperDiscoveryStore(db_path)
    assert reopened.get_field_provenance("paper-7")["title"]["source_id"] == "ccs"


def test_may_overwrite_direction_is_smaller_is_more_authoritative():
    """方向守卫：数值越小越权威（防止再出现反向判定）。"""
    # 官方会场(10) 可以覆盖 聚合(30)
    assert may_overwrite("openalex", "usenix") is True
    # 聚合(30) 不能覆盖 官方会场(10)
    assert may_overwrite("usenix", "openalex") is False
    # 无归属 → 始终可写
    assert may_overwrite(None, "openalex") is True
