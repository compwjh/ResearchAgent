"""Task07 CCS coverage gate: official coverage stays blocked until evidence is complete.

This is intentionally a local contract test.  It does not call the external CCS site,
download a PDF, or turn an official URL into a parser fixture.  The audit artifact is
the handoff that must be revised together with any future official-source implementation.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from backend.app.paper_discovery.infrastructure.ccs_publication_source import CcsPublicationSource

ROOT = Path(__file__).parents[2]
AUDIT = ROOT / "artifacts" / "task-07" / "ccs-coverage.md"


def _source() -> CcsPublicationSource:
    return CcsPublicationSource(
        client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})), trust_env=False),
        dns_resolver=lambda _host: ["93.184.216.34"],
        rate_limit_seconds=0.0,
        sleep=lambda _seconds: None,
    )


def test_ccs_audit_records_bounded_no_go_for_every_requested_year():
    audit = AUDIT.read_text(encoding="utf-8")

    assert "NO-GO / 未验证（全年度覆盖）" in audit
    assert "blocked_js_or_data" in audit
    assert "blocked_identity" in audit
    for year in range(2021, 2026):
        assert f"| {year} |" in audit


def test_ccs_runtime_is_still_crossref_openalex_fallback_only():
    source = _source()

    assert source.allowed_hosts == frozenset({"api.crossref.org", "api.openalex.org"})
    units = source.discover_units({"years": [2021, 2025]})
    assert [unit.source_url.split("/", 3)[2] for unit in units] == [
        "api.crossref.org",
        "api.crossref.org",
    ]
