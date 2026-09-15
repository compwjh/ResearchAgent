"""spec-032 Task03：OpenAlex / Crossref 聚合来源适配器测试（固定样本，离线）。"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.app.paper_discovery.infrastructure.aggregate_source_adapters import (
    AUTHORITY_OFFICIAL,
    CrossrefCatalogAdapter,
    FetchUnit,
    OpenAlexCatalogAdapter,
    SourceRecord,
    content_fingerprint,
    dedupe_by_identity,
    merge_source_records,
)

OPENALEX_PAYLOAD = {
    "meta": {"count": 2, "next_cursor": "CURSOR2"},
    "results": [
        {
            "id": "https://openalex.org/W1",
            "doi": "https://doi.org/10.1000/sample-one",
            "display_name": "Sample Paper One",
            "publication_year": 2024,
            "authorships": [
                {"author": {"display_name": "Ada Lovelace"}},
                {"author": {"display_name": "Alan Turing"}},
            ],
            "abstract_inverted_index": {"Hello": [0], "World": [1]},
            "primary_location": {
                "landing_page_url": "https://example.org/one",
                "pdf_url": "https://example.org/one.pdf",
            },
            "keywords": [{"display_name": "security"}, {"display_name": "privacy"}],
        },
        {
            "id": "https://openalex.org/W2",
            "doi": "https://doi.org/10.1000/sample-two",
            "display_name": "",  # 无标题 → 丢弃
            "publication_year": 2024,
        },
    ],
}

CROSSREF_PAYLOAD = {
    "message": {
        "next-cursor": "NEXT",
        "items": [
            {
                "DOI": "10.2000/one",
                "title": ["Sample Paper One"],
                "author": [{"given": "Ada", "family": "Lovelace"}],
                "issued": {"date-parts": [[2024, 5, 1]]},
                "URL": "https://doi.org/10.2000/one",
                "abstract": "<jats:p>Abstract text</jats:p>",
                "link": [{"content-type": "application/pdf", "URL": "https://example.org/x.pdf"}],
            },
            {
                "DOI": "10.2000/two",
                "title": ["Paper Without Much Metadata"],
                "issued": {"date-parts": [[2023]]},
            },
        ],
    }
}


def response(payload: dict, *, status: int = 200, headers: dict | None = None, body: bytes | None = None):
    return SimpleNamespace(
        status_code=status,
        headers=headers or {},
        content=body if body is not None else json.dumps(payload).encode("utf-8"),
        json=lambda: payload,
        text=json.dumps(payload),
    )


class OpenAlexAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = OpenAlexCatalogAdapter()

    def test_discover_units_by_year(self):
        units = self.adapter.discover_units({"year": 2024})
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].scope_key, "openalex:2024")
        self.assertEqual(units[0].status, "pending")

    def test_discover_units_year_range(self):
        units = self.adapter.discover_units({"from_year": 2022, "to_year": 2024})
        self.assertEqual([unit.scope_key for unit in units], ["openalex:2022", "openalex:2023", "openalex:2024"])

    def test_parse_catalog_maps_fields_and_skips_untitled(self):
        records = self.adapter.parse_catalog(OPENALEX_PAYLOAD)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.title, "Sample Paper One")
        self.assertEqual(record.abstract, "Hello World")
        self.assertEqual(record.authors, ("Ada Lovelace", "Alan Turing"))
        self.assertEqual(record.year, 2024)
        self.assertEqual(record.doi, "10.1000/sample-one")
        self.assertEqual(record.keywords, ("security", "privacy"))
        self.assertEqual(record.pdf_url, "https://example.org/one.pdf")
        self.assertEqual(record.provenance_for("abstract"), "openalex")

    def test_parse_catalog_handles_missing_fields(self):
        payload = {"meta": {}, "results": [{"id": "W9", "display_name": "Only Title"}]}
        records = self.adapter.parse_catalog(payload)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.abstract, "")
        self.assertEqual(record.authors, ())
        self.assertIsNone(record.year)
        self.assertEqual(record.provenance_for("abstract"), "openalex")  # 未填字段回退到来源 id

    def test_fetch_unit_records_etag_hash_and_cursor(self):
        unit = FetchUnit(source_id="openalex", scope_key="openalex:2024", params={"filter": "x"})
        fake = response(OPENALEX_PAYLOAD, headers={"ETag": '"abc"', "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT"})
        with patch.object(self.adapter, "_get", return_value=fake):
            updated, payload = self.adapter.fetch_unit(unit)
        self.assertEqual(updated.status, "fetched")
        self.assertEqual(updated.etag, '"abc"')
        self.assertEqual(updated.cursor, "CURSOR2")
        self.assertEqual(updated.content_hash, content_fingerprint(fake.content))
        self.assertIs(payload, OPENALEX_PAYLOAD)

    def test_fetch_unit_304_is_unchanged(self):
        unit = FetchUnit(source_id="openalex", scope_key="openalex:2024", etag='"abc"')
        with patch.object(self.adapter, "_get", return_value=response({}, status=304)):
            updated, payload = self.adapter.fetch_unit(unit)
        self.assertEqual(updated.status, "unchanged")
        self.assertIsNone(payload)

    def test_fetch_unit_same_content_hash_is_unchanged(self):
        body = json.dumps(OPENALEX_PAYLOAD).encode("utf-8")
        unit = FetchUnit(source_id="openalex", scope_key="openalex:2024", content_hash=content_fingerprint(body))
        with patch.object(self.adapter, "_get", return_value=response(OPENALEX_PAYLOAD, body=body)):
            updated, payload = self.adapter.fetch_unit(unit)
        self.assertEqual(updated.status, "unchanged")
        self.assertIsNone(payload)  # 内容未变化 → 不重复解析/向量化

    def test_fetch_unit_network_failure_keeps_old_cache(self):
        unit = FetchUnit(source_id="openalex", scope_key="openalex:2024", content_hash="old", etag='"keep"')
        with patch.object(self.adapter, "_get", return_value=None):
            updated, payload = self.adapter.fetch_unit(unit)
        self.assertEqual(updated.status, "failed")
        self.assertIsNone(payload)
        self.assertEqual(updated.content_hash, "old")  # 失败不清空旧缓存
        self.assertEqual(updated.etag, '"keep"')

    def test_conditional_headers_include_etag(self):
        unit = FetchUnit(source_id="openalex", scope_key="k", etag='"e"', last_modified="LM")
        self.assertEqual(unit.conditional_headers(), {"If-None-Match": '"e"', "If-Modified-Since": "LM"})

    def test_health_ok_and_failure(self):
        with patch.object(self.adapter, "_get", return_value=response({}, status=200)):
            self.assertEqual(self.adapter.health(), {"source_id": "openalex", "ok": True, "kind": "aggregate"})
        with patch.object(self.adapter, "_get", return_value=None):
            self.assertEqual(self.adapter.health()["ok"], False)


class CrossrefAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = CrossrefCatalogAdapter()

    def test_parse_catalog_maps_fields_and_strips_jats(self):
        records = self.adapter.parse_catalog(CROSSREF_PAYLOAD)
        self.assertEqual(len(records), 2)
        first = records[0]
        self.assertEqual(first.title, "Sample Paper One")
        self.assertEqual(first.doi, "10.2000/one")
        self.assertEqual(first.year, 2024)
        self.assertEqual(first.authors, ("Ada Lovelace",))
        self.assertEqual(first.pdf_url, "https://example.org/x.pdf")

    def test_parse_catalog_missing_fields_are_empty(self):
        records = self.adapter.parse_catalog(CROSSREF_PAYLOAD)
        second = records[1]
        self.assertEqual(second.authors, ())
        self.assertEqual(second.year, 2023)
        self.assertEqual(second.page_url, "")

    def test_fetch_unit_captures_cursor(self):
        unit = FetchUnit(source_id="crossref", scope_key="crossref:2024", params={"filter": "f"})
        with patch.object(self.adapter, "_get", return_value=response(CROSSREF_PAYLOAD)):
            updated, payload = self.adapter.fetch_unit(unit)
        self.assertEqual(updated.status, "fetched")
        self.assertEqual(updated.cursor, "NEXT")
        self.assertIs(payload, CROSSREF_PAYLOAD)

    def test_parse_from_raw_bytes(self):
        raw = json.dumps(CROSSREF_PAYLOAD).encode("utf-8")
        self.assertEqual(len(self.adapter.parse_catalog(raw)), 2)


class MergeAndIdentityTests(unittest.TestCase):
    def _official(self, **overrides):
        base = {
            "source_id": "usenix",
            "source_record_id": "u1",
            "authority_rank": AUTHORITY_OFFICIAL,
            "title": "Official Title",
            "abstract": "Official abstract",
            "year": 2024,
            "doi": "10.1000/sample-one",
        }
        base.update(overrides)
        return SourceRecord(**base)

    def _aggregate(self, **overrides):
        base = {
            "source_id": "openalex",
            "source_record_id": "W1",
            "authority_rank": 30,
            "title": "Aggregate Title",
            "abstract": "Aggregate abstract",
            "keywords": ("k1",),
            "authors": ("Someone",),
            "year": 2024,
            "doi": "10.1000/sample-one",
        }
        base.update(overrides)
        return SourceRecord(**base)

    def test_aggregate_only_fills_missing_fields(self):
        official = self._official(abstract="")
        merged, filled = merge_source_records(official, self._aggregate())
        self.assertEqual(merged.title, "Official Title")  # 官方标题不被降级
        self.assertEqual(merged.abstract, "Aggregate abstract")  # 缺失被填补
        self.assertEqual(merged.provenance_for("abstract"), "openalex")
        self.assertEqual(filled, ["abstract", "keywords", "authors"])

    def test_aggregate_never_overwrites_official_field(self):
        official = self._official()
        merged, filled = merge_source_records(official, self._aggregate())
        self.assertEqual(merged.title, "Official Title")
        self.assertEqual(merged.abstract, "Official abstract")
        # 官方已有字段不变；官方为空的 keywords/authors 由聚合来源补缺。
        self.assertEqual(filled, ["keywords", "authors"])

    def test_identity_mismatch_returns_base(self):
        official = self._official(doi="10.9999/other")
        merged, filled = merge_source_records(official, self._aggregate())
        self.assertEqual(merged.doi, "10.9999/other")
        self.assertEqual(filled, [])

    def test_identity_key_prefers_doi_then_title_year(self):
        self.assertEqual(self._official().identity_key(), "doi:10.1000/sample-one")
        no_doi = self._official(doi="")
        self.assertEqual(no_doi.identity_key(), "title:officialtitle:2024")

    def test_dedupe_by_identity_keeps_first(self):
        records = [self._official(), self._aggregate()]
        self.assertEqual(len(dedupe_by_identity(records)), 1)  # 同 DOI 去重


if __name__ == "__main__":
    unittest.main()
