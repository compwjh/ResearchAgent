from fastapi.testclient import TestClient

from backend.app.api import routes_paper
from backend.app.main import app
from backend.app.paper_discovery.domain.paper_discovery import CatalogPaper
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore


def _paper(paper_id: str = "paper-1") -> CatalogPaper:
    return CatalogPaper(
        catalog_paper_id=paper_id,
        conference_id="usenix-security",
        year=2024,
        title="A Paper",
        normalized_title="a paper",
        authors=["Ada"],
        abstract="Abstract",
        metadata_hash="hash-1",
    )


def test_provenance_endpoint_returns_paper_and_field_provenance(tmp_path, monkeypatch):
    store = PaperDiscoveryStore(tmp_path / "state.sqlite3")
    paper = _paper()
    store.upsert_catalog_paper(paper, now="2024-01-01T00:00:00Z")
    store.save_field_provenance(
        paper.catalog_paper_id,
        "title",
        "usenix",
        source_record_id="record-1",
        now="2024-01-01T00:00:00Z",
    )
    monkeypatch.setattr(routes_paper, "_paper_store", lambda: store)
    monkeypatch.setattr(routes_paper, "_paper_discovery_enabled", lambda: True)

    response = TestClient(app).get(f"/api/papers/{paper.catalog_paper_id}/provenance")

    assert response.status_code == 200
    payload = response.json()
    assert payload["paper_id"] == paper.catalog_paper_id
    assert payload["paper"]["title"] == paper.title
    assert payload["paper"]["authors"] == paper.authors
    assert payload["provenance"]["title"] == {
        "source_id": "usenix",
        "source_record_id": "record-1",
        "observed_at": "2024-01-01T00:00:00Z",
    }


def test_provenance_endpoint_returns_404_without_reading_provenance(monkeypatch):
    class Store:
        def get_catalog_paper(self, _paper_id):
            return None

        def get_field_provenance(self, _paper_id):
            raise AssertionError("provenance must not be read for an unknown paper")

    monkeypatch.setattr(routes_paper, "_paper_store", Store)
    monkeypatch.setattr(routes_paper, "_paper_discovery_enabled", lambda: True)

    response = TestClient(app).get("/api/papers/missing/provenance")

    assert response.status_code == 404
    assert response.json()["code"] == "PAPER_NOT_FOUND"


def test_provenance_endpoint_maps_store_failure_to_503(monkeypatch):
    class Store:
        def get_catalog_paper(self, _paper_id):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(routes_paper, "_paper_store", Store)
    monkeypatch.setattr(routes_paper, "_paper_discovery_enabled", lambda: True)

    response = TestClient(app).get("/api/papers/paper-1/provenance")

    assert response.status_code == 503
    assert response.json()["code"] == "PAPER_DISCOVERY_STORE_UNAVAILABLE"
    assert response.json()["retryable"] is True
