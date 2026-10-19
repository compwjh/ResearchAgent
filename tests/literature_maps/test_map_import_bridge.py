from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from backend.app.literature_maps.application.import_bridge import LiteratureMapImportBridge
from backend.app.literature_maps.application.paper_import_adapter import PaperImportSourceAdapter
from backend.app.literature_maps.domain.models import MapPaper
from backend.app.paper_discovery.application.paper_import import PaperImportError
from backend.app.paper_discovery.infrastructure.paper_download import PaperDownloadError


@dataclass
class FakeStore:
    calls: list[tuple[str, str, str, dict]] = field(default_factory=list)

    def update_node_import_result(self, map_id: str, node_id: str, owner_id: str, *, import_result: dict):
        self.calls.append((map_id, node_id, owner_id, dict(import_result)))
        return None


def _node(source_url: str = "https://papers.example.test/paper.pdf") -> MapPaper:
    return MapPaper.new(
        "map-1",
        semantic_scholar_id="s2-1",
        title="A paper",
        source_url=source_url,
        provenance={"provider": "semantic_scholar", "operation": "search"},
    )


def test_bridge_calls_existing_importer_and_persists_real_document_handle() -> None:
    received: list[tuple[dict, str]] = []

    def importer(snapshot: dict, source_url: str) -> dict:
        received.append((snapshot, source_url))
        return {"paper_id": "doc-123", "stored_name": "paper.pdf", "status": "indexed"}

    store = FakeStore()
    node = _node()
    result = LiteratureMapImportBridge(importer=importer, store=store, owner_id="owner-1").import_node(
        node, node.source_url or ""
    )

    assert received[0][0]["source_url"] == node.source_url
    assert received[0][1] == node.source_url
    assert result["document_id"] == "doc-123"
    assert result["download_status"] == "indexed"
    assert result.get("catalog_paper_id") is None
    assert store.calls == [("map-1", node.node_id, "owner-1", result)]


def test_bridge_rejects_private_source_without_invoking_importer() -> None:
    called = False

    def importer(snapshot: dict, source_url: str) -> dict:
        nonlocal called
        called = True
        return {"status": "indexed", "paper_id": "doc"}

    with pytest.raises(ValueError, match="IMPORT_URL_UNSAFE"):
        LiteratureMapImportBridge(importer=importer).import_node(_node("http://127.0.0.1/paper.pdf"), "http://127.0.0.1/paper.pdf")
    assert called is False


def test_bridge_rejects_client_source_override_even_when_public() -> None:
    called = False

    def importer(snapshot: dict, source_url: str) -> dict:
        nonlocal called
        called = True
        return {"status": "indexed", "paper_id": "doc"}

    node = _node("https://papers.example.test/paper.pdf")
    with pytest.raises(ValueError, match="IMPORT_URL_UNSAFE"):
        LiteratureMapImportBridge(importer=importer).import_node(
            node,
            "https://attacker.example.test/public.pdf",
        )
    assert called is False


def test_runtime_composition_root_injects_callable_importer(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.api import common
    from backend.app.literature_maps.application import runtime

    class FakeMapStore:
        pass

    runtime.reset_literature_map_runtime()
    monkeypatch.setattr(runtime, "LiteratureMapStore", lambda: FakeMapStore())
    monkeypatch.setattr(common, "_paper_store", lambda: object())
    try:
        service = runtime.get_literature_map_service()
        bridge = service.import_bridge.__self__
        assert callable(bridge.importer)
        assert callable(bridge.source_resolver)
    finally:
        runtime.reset_literature_map_runtime()


def test_bridge_preserves_login_or_queued_state_and_does_not_invent_catalog_id() -> None:
    store = FakeStore()
    node = _node()
    result = LiteratureMapImportBridge(
        importer=lambda snapshot, source_url: {"status": "waiting_login", "error_code": "LOGIN_REQUIRED"},
        store=store,
        owner_id="owner-1",
    ).import_node(node, node.source_url or "")

    assert result["status"] == "waiting_login"
    assert result["download_status"] == "waiting_login"
    assert result["document_id"] is None
    assert result.get("catalog_paper_id") is None
    assert store.calls[0][3] == result


def test_bridge_never_treats_semantic_scholar_landing_page_as_pdf() -> None:
    store = FakeStore()
    node = _node("https://www.semanticscholar.org/paper/s2-1")
    called = False

    def importer(snapshot: dict, source_url: str) -> dict:
        nonlocal called
        called = True
        return {"paper_id": "doc", "status": "indexed"}

    result = LiteratureMapImportBridge(
        importer=importer,
        source_resolver=lambda _: {"pdf_url": None},
        oa_resolver=lambda _: None,
        store=store,
        owner_id="owner-1",
    ).import_node(node, node.source_url or "")

    assert called is False
    assert result["status"] == "failed"
    assert result["error_code"] == "PDF_NOT_FOUND"
    assert store.calls[0][3] == result


def test_bridge_rejects_resolver_mislabelling_semantic_scholar_landing() -> None:
    called = False
    node = _node("https://www.semanticscholar.org/paper/s2-1")

    def importer(snapshot: dict, source_url: str) -> dict:
        nonlocal called
        called = True
        return {"paper_id": "doc", "status": "indexed"}

    result = LiteratureMapImportBridge(
        importer=importer,
        source_resolver=lambda item: {"pdf_url": item.source_url},
    ).import_node(node, node.source_url or "")

    assert called is False
    assert result["status"] == "failed"
    assert result["error_code"] == "PDF_NOT_FOUND"


def test_bridge_prefers_server_catalog_pdf_and_keeps_catalog_identity_separate() -> None:
    received: list[tuple[dict, str]] = []
    node = MapPaper.new(
        "map-1",
        external_ids={"semantic_scholar": "s2-1", "doi": "10.1000/example"},
        title="A paper",
        source_url="https://www.semanticscholar.org/paper/s2-1",
        provenance={"provider": "semantic_scholar", "source": "usenix", "conference_id": "usenix-security"},
    )

    def importer(snapshot: dict, source_url: str) -> dict:
        received.append((snapshot, source_url))
        return {"paper_id": "doc-123", "status": "indexed"}

    store = FakeStore()
    result = LiteratureMapImportBridge(
        importer=importer,
        source_resolver=lambda _: {
            "catalog_paper_id": "catalog-1",
            "doi": "10.1000/example",
            "official_pdf_url": "https://www.usenix.org/system/files/conference/x.pdf",
        },
        oa_resolver=lambda _: pytest.fail("OA fallback must not replace an official PDF"),
        store=store,
        owner_id="owner-1",
    ).import_node(node, node.source_url or "")

    assert received[0][1].endswith("/x.pdf")
    assert received[0][0]["source_url"] == node.source_url
    assert received[0][0]["pdf_url"].endswith("/x.pdf")
    assert result["catalog_paper_id"] == "catalog-1"
    assert store.calls[0][3] == result


def test_catalog_adapter_uses_frozen_official_snapshot_before_live_oa_lookup() -> None:
    node = MapPaper.new(
        "map-1",
        external_ids={"semantic_scholar": "s2-1", "doi": "10.1000/example"},
        title="A paper",
        source_url="https://www.usenix.org/paper-page",
        catalog_paper_id="catalog-1",
        provenance={
            "source": "usenix",
            "catalog_paper_id": "catalog-1",
            "official_pdf_url": "https://www.usenix.org/system/files/conference/frozen.pdf",
        },
    )
    store = SimpleNamespace(
        get_catalog_paper=lambda _: SimpleNamespace(
            catalog_paper_id="catalog-1",
            official_pdf_url="https://www.usenix.org/system/files/conference/refreshed.pdf",
        )
    )
    adapter = PaperImportSourceAdapter(
        catalog_store=store,
        oa_resolver=lambda _: pytest.fail("frozen official PDF must win"),
    )

    source = adapter.resolve(node)

    assert source["catalog_paper_id"] == "catalog-1"
    assert source["official_pdf_url"].endswith("frozen.pdf")


def test_catalog_adapter_does_not_bind_same_title_without_deterministic_identity() -> None:
    node = MapPaper.new(
        "map-1",
        semantic_scholar_id="s2-1",
        title="Same title",
        source_url="https://www.semanticscholar.org/paper/s2-1",
        provenance={"source": "usenix", "conference_id": "usenix-security"},
    )
    store = SimpleNamespace(
        list_catalog_papers=lambda *_args, **_kwargs: [
            SimpleNamespace(
                catalog_paper_id="catalog-other",
                title="Same title",
                doi="10.9999/other",
                official_pdf_url="https://www.usenix.org/system/files/conference/other.pdf",
            )
        ]
    )

    source = PaperImportSourceAdapter(catalog_store=store).resolve(node)

    assert source["error_code"] == "PDF_NOT_FOUND"
    assert "catalog_paper_id" not in source
    assert "official_pdf_url" not in source


def test_catalog_adapter_rejects_same_title_with_different_doi() -> None:
    node = MapPaper.new(
        "map-1",
        external_ids={"semantic_scholar": "s2-1", "doi": "10.1000/node"},
        title="Same title",
        source_url="https://www.semanticscholar.org/paper/s2-1",
        provenance={"source": "usenix", "conference_id": "usenix-security"},
    )
    store = SimpleNamespace(
        list_catalog_papers=lambda *_args, **_kwargs: [
            SimpleNamespace(
                catalog_paper_id="catalog-other",
                title="Same title",
                doi="10.9999/other",
                official_pdf_url="https://www.usenix.org/system/files/conference/other.pdf",
            )
        ]
    )

    source = PaperImportSourceAdapter(catalog_store=store).resolve(node)

    assert source["error_code"] == "PDF_NOT_FOUND"
    assert "catalog_paper_id" not in source
    assert "official_pdf_url" not in source


def test_catalog_adapter_accepts_server_catalog_id_without_external_id() -> None:
    node = MapPaper.new(
        "map-1",
        semantic_scholar_id="s2-1",
        title="Catalog-only identity",
        source_url="https://www.usenix.org/paper-page",
        catalog_paper_id="catalog-1",
        provenance={
            "source": "usenix",
            "catalog_paper_id": "catalog-1",
            "catalog_snapshot": {
                "catalog_paper_id": "catalog-1",
                "official_pdf_url": "https://www.usenix.org/system/files/conference/frozen.pdf",
            },
        },
    )

    source = PaperImportSourceAdapter().resolve(node)

    assert source["catalog_paper_id"] == "catalog-1"
    assert source["official_pdf_url"].endswith("frozen.pdf")


def test_catalog_adapter_uses_matching_doi_for_catalog_lookup() -> None:
    node = MapPaper.new(
        "map-1",
        external_ids={"semantic_scholar": "s2-1", "doi": "10.1000/node"},
        title="A paper",
        source_url="https://www.semanticscholar.org/paper/s2-1",
        provenance={"source": "usenix", "conference_id": "usenix-security"},
    )
    store = SimpleNamespace(
        list_catalog_papers=lambda *_args, **_kwargs: [
            SimpleNamespace(
                catalog_paper_id="catalog-1",
                title="A paper",
                doi="https://doi.org/10.1000/node",
                official_pdf_url="https://www.usenix.org/system/files/conference/matched.pdf",
            )
        ]
    )

    source = PaperImportSourceAdapter(catalog_store=store).resolve(node)

    assert source["catalog_paper_id"] == "catalog-1"
    assert source["official_pdf_url"].endswith("matched.pdf")


def test_bridge_rejects_catalog_identity_conflict_without_invoking_importer() -> None:
    called = False
    node = MapPaper.new(
        "map-1",
        external_ids={"semantic_scholar": "s2-1", "doi": "10.1000/example"},
        title="A paper",
        source_url="https://www.semanticscholar.org/paper/s2-1",
    )

    def importer(snapshot: dict, source_url: str) -> dict:
        nonlocal called
        called = True
        return {"paper_id": "doc", "status": "indexed"}

    store = FakeStore()
    result = LiteratureMapImportBridge(
        importer=importer,
        source_resolver=lambda _: {
            "catalog_paper_id": "s2-1",
            "doi": "10.1000/example",
            "official_pdf_url": "https://www.usenix.org/system/files/conference/x.pdf",
        },
        store=store,
        owner_id="owner-1",
    ).import_node(node, node.source_url or "")

    assert called is False
    assert result["status"] == "failed"
    assert result["error_code"] == "IMPORT_IDENTITY_CONFLICT"
    assert store.calls[0][3] == result


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (PaperDownloadError("PDF_NOT_FOUND", "internal detail"), "failed"),
        (PaperImportError("LOGIN_REQUIRED", "internal detail", retryable=True), "waiting_login"),
    ],
)
def test_bridge_persists_stable_expected_import_errors(error: Exception, status: str) -> None:
    store = FakeStore()
    node = _node()

    def importer(snapshot: dict, source_url: str) -> dict:
        raise error

    result = LiteratureMapImportBridge(
        importer=importer,
        store=store,
        owner_id="owner-1",
    ).import_node(node, node.source_url or "")

    assert result["status"] == status
    assert result["error_code"] in {"PDF_NOT_FOUND", "LOGIN_REQUIRED"}
    assert result["retryable"] is (status == "waiting_login")
    assert store.calls[0][3] == result
