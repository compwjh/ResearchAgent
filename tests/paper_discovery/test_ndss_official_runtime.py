"""Runtime routing for the bounded NDSS official catalogue years."""

from pathlib import Path
from unittest.mock import patch

import httpx

from backend.app.paper_discovery.application.catalog_runtime import CatalogSourceRuntime
from backend.app.paper_discovery.domain.paper_discovery import SearchJob
from backend.app.paper_discovery.infrastructure.ndss_paper_parser import NDSS_OFFICIAL_ACCEPTED_PAPERS_URLS
from backend.app.paper_discovery.infrastructure.ndss_publication_source import NdssPublicationSource
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.paper_discovery.infrastructure.source_registry import SourceRegistry

FIXTURE_2025 = Path(__file__).parents[1] / "fixtures" / "ndss" / "official-accepted-papers-2025.html"
NDSS_2025_OFFICIAL_URL = NDSS_OFFICIAL_ACCEPTED_PAPERS_URLS[2025]


def test_catalog_runtime_routes_ndss_2025_to_controlled_official_listing(tmp_path):
    store = PaperDiscoveryStore(tmp_path / "ndss-runtime.sqlite3")
    store.create_search_job(SearchJob(
        "ndss-2025-runtime", "ndss official", ["ndss"], [2025],
        expires_at="2099-01-01T00:00:00Z", created_at="2026-10-08T00:00:00Z",
    ))
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert str(request.url) == NDSS_2025_OFFICIAL_URL
        assert request.url.host == "www.ndss-symposium.org"
        assert not request.url.path.endswith(".pdf")
        return httpx.Response(200, content=FIXTURE_2025.read_bytes(), headers={"ETag": '"official-2025-v1"'})

    source = NdssPublicationSource(
        client=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        dns_resolver=lambda host: ["93.184.216.34"],
        rate_limit_seconds=0.0,
        sleep=lambda _seconds: None,
    )
    registry = SourceRegistry(store=store)
    with patch.object(registry, "adapter", return_value=source):
        result = CatalogSourceRuntime(store=store, registry=registry).run(
            "ndss-2025-runtime", "ndss", [2025]
        )

    assert result.status == "completed"
    assert calls == [NDSS_2025_OFFICIAL_URL]
    unit = store.get_fetch_unit("ndss|ndss|2025|official")
    assert unit is not None
    assert unit.unit_key == "ndss:2025:official"
    assert unit.source_url == NDSS_2025_OFFICIAL_URL
    assert unit.paper_count == 3
