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


def _oa_candidate() -> dict:
    return {
        "title": "A paper",
        "authors": ["Ada Lovelace"],
        "year": 2024,
        "external_ids": {"arxiv": "1809.07041"},
    }


def test_runtime_oa_resolver_prefers_matching_existing_arxiv_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.literature_maps.application import runtime
    from backend.app.paper_discovery.infrastructure import arxiv_adapter, semantic_scholar_adapter

    class FakeArxiv:
        def lookup(self, title, authors, year):
            assert (title, tuple(authors), year) == ("A paper", ("Ada Lovelace",), 2024)
            return SimpleNamespace(
                match=SimpleNamespace(arxiv_id="1809.07041", pdf_url="https://arxiv.org/pdf/1809.07041"),
                code=None,
            )

    class UnexpectedS2:
        def __init__(self):
            raise AssertionError("S2 must not replace a matching arXiv fallback")

    monkeypatch.setattr(arxiv_adapter, "ArxivFallbackAdapter", FakeArxiv)
    monkeypatch.setattr(semantic_scholar_adapter, "SemanticScholarFallbackAdapter", UnexpectedS2)

    result = runtime._existing_oa_resolver(_oa_candidate())

    assert result == {
        "pdf_url": "https://arxiv.org/pdf/1809.07041",
        "arxiv_id": "1809.07041",
        "source_kind": "arxiv",
        "resolver": "arxiv",
    }


def test_runtime_oa_resolver_rejects_arxiv_identity_conflict_before_s2_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.literature_maps.application import runtime
    from backend.app.paper_discovery.infrastructure import arxiv_adapter, semantic_scholar_adapter

    class ConflictingArxiv:
        def lookup(self, *_args, **_kwargs):
            return SimpleNamespace(
                match=SimpleNamespace(arxiv_id="9999.00001", pdf_url="https://arxiv.org/pdf/9999.00001"),
                code=None,
            )

    class NoPdfS2:
        def lookup(self, candidate, *, allowed_hosts):
            assert candidate["arxiv_id"] == "1809.07041"
            assert "arxiv.org" in allowed_hosts
            return SimpleNamespace(match=None, code="SEMANTIC_SCHOLAR_NO_OPEN_PDF")

    monkeypatch.setattr(arxiv_adapter, "ArxivFallbackAdapter", ConflictingArxiv)
    monkeypatch.setattr(semantic_scholar_adapter, "SemanticScholarFallbackAdapter", NoPdfS2)

    result = runtime._existing_oa_resolver(_oa_candidate())

    assert "pdf_url" not in result
    assert result["error_code"] == "PDF_NOT_FOUND"
    assert result["resolver_codes"] == ["ARXIV_IDENTITY_CONFLICT", "SEMANTIC_SCHOLAR_NO_OPEN_PDF"]


def test_runtime_oa_resolver_uses_s2_after_arxiv_fallback_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.literature_maps.application import runtime
    from backend.app.paper_discovery.infrastructure import arxiv_adapter, semantic_scholar_adapter

    class MissedArxiv:
        def lookup(self, *_args, **_kwargs):
            return SimpleNamespace(match=None, code="ARXIV_MATCH_UNCERTAIN")

    class MatchingS2:
        def lookup(self, candidate, *, allowed_hosts):
            assert candidate["arxiv_id"] == "1809.07041"
            assert "arxiv.org" in allowed_hosts
            return SimpleNamespace(
                match=SimpleNamespace(
                    paper_id="s2-1",
                    arxiv_id="1809.07041",
                    doi=None,
                    pdf_url="https://arxiv.org/pdf/1809.07041",
                ),
                code=None,
            )

    monkeypatch.setattr(arxiv_adapter, "ArxivFallbackAdapter", MissedArxiv)
    monkeypatch.setattr(semantic_scholar_adapter, "SemanticScholarFallbackAdapter", MatchingS2)

    result = runtime._existing_oa_resolver(_oa_candidate())

    assert result["pdf_url"].endswith("/1809.07041")
    assert result["resolver"] == "semantic_scholar"
    assert result["semantic_scholar_id"] == "s2-1"


def test_runtime_oa_resolver_preserves_provider_failure_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.literature_maps.application import runtime
    from backend.app.paper_discovery.infrastructure import arxiv_adapter, semantic_scholar_adapter

    class FailedArxiv:
        def lookup(self, *_args, **_kwargs):
            return SimpleNamespace(match=None, code="ARXIV_UNAVAILABLE")

    class FailedS2:
        def lookup(self, *_args, **_kwargs):
            return SimpleNamespace(match=None, code="SEMANTIC_SCHOLAR_UNAVAILABLE")

    monkeypatch.setattr(arxiv_adapter, "ArxivFallbackAdapter", FailedArxiv)
    monkeypatch.setattr(semantic_scholar_adapter, "SemanticScholarFallbackAdapter", FailedS2)

    result = runtime._existing_oa_resolver(_oa_candidate())

    assert result["error_code"] == "SEMANTIC_SCHOLAR_UNAVAILABLE"
    assert result["resolver_codes"] == ["ARXIV_UNAVAILABLE", "SEMANTIC_SCHOLAR_UNAVAILABLE"]
    assert result["resolver_code"] == "SEMANTIC_SCHOLAR_UNAVAILABLE"
    assert result["retryable"] is True


@pytest.mark.parametrize(
    ("arxiv_code", "retryable"),
    [
        ("ARXIV_RATE_LIMITED", True),
        ("ARXIV_HTTP_ERROR", False),
        ("ARXIV_INVALID_RESPONSE", False),
        ("ARXIV_UNAVAILABLE", True),
    ],
)
def test_runtime_oa_resolver_keeps_arxiv_provider_failure_as_primary(
    monkeypatch: pytest.MonkeyPatch,
    arxiv_code: str,
    retryable: bool,
) -> None:
    from backend.app.literature_maps.application import runtime
    from backend.app.paper_discovery.infrastructure import arxiv_adapter, semantic_scholar_adapter

    class FailedArxiv:
        def lookup(self, *_args, **_kwargs):
            return SimpleNamespace(match=None, code=arxiv_code)

    class NoPdfS2:
        def lookup(self, *_args, **_kwargs):
            return SimpleNamespace(match=None, code="SEMANTIC_SCHOLAR_NO_OPEN_PDF")

    monkeypatch.setattr(arxiv_adapter, "ArxivFallbackAdapter", FailedArxiv)
    monkeypatch.setattr(semantic_scholar_adapter, "SemanticScholarFallbackAdapter", NoPdfS2)

    result = runtime._existing_oa_resolver(_oa_candidate())

    assert result["error_code"] == arxiv_code
    assert result["resolver_codes"] == [arxiv_code, "SEMANTIC_SCHOLAR_NO_OPEN_PDF"]
    assert result["retryable"] is retryable


def test_runtime_oa_resolver_keeps_semantic_scholar_rate_limit_as_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.literature_maps.application import runtime
    from backend.app.paper_discovery.infrastructure import arxiv_adapter, semantic_scholar_adapter

    class UncertainArxiv:
        def lookup(self, *_args, **_kwargs):
            return SimpleNamespace(match=None, code="ARXIV_MATCH_UNCERTAIN")

    class RateLimitedS2:
        def lookup(self, *_args, **_kwargs):
            return SimpleNamespace(match=None, code="SEMANTIC_SCHOLAR_RATE_LIMITED", retryable=True)

    monkeypatch.setattr(arxiv_adapter, "ArxivFallbackAdapter", UncertainArxiv)
    monkeypatch.setattr(semantic_scholar_adapter, "SemanticScholarFallbackAdapter", RateLimitedS2)

    result = runtime._existing_oa_resolver(_oa_candidate())

    assert result["error_code"] == "SEMANTIC_SCHOLAR_RATE_LIMITED"
    assert result["resolver_codes"] == ["ARXIV_MATCH_UNCERTAIN", "SEMANTIC_SCHOLAR_RATE_LIMITED"]
    assert result["retryable"] is True


def test_runtime_oa_resolver_reports_no_pdf_after_both_existing_adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.literature_maps.application import runtime
    from backend.app.paper_discovery.infrastructure import arxiv_adapter, semantic_scholar_adapter

    class UncertainArxiv:
        def lookup(self, *_args, **_kwargs):
            return SimpleNamespace(match=None, code="ARXIV_MATCH_UNCERTAIN")

    class NoPdfS2:
        def lookup(self, *_args, **_kwargs):
            return SimpleNamespace(
                match=SimpleNamespace(arxiv_id="1809.07041", pdf_url=None),
                code="SEMANTIC_SCHOLAR_NO_OPEN_PDF",
            )

    monkeypatch.setattr(arxiv_adapter, "ArxivFallbackAdapter", UncertainArxiv)
    monkeypatch.setattr(semantic_scholar_adapter, "SemanticScholarFallbackAdapter", NoPdfS2)

    result = runtime._existing_oa_resolver(_oa_candidate())

    assert result["error_code"] == "PDF_NOT_FOUND"
    assert result["resolver_code"] == "SEMANTIC_SCHOLAR_NO_OPEN_PDF"
    assert result["resolver_codes"] == ["ARXIV_MATCH_UNCERTAIN", "SEMANTIC_SCHOLAR_NO_OPEN_PDF"]


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


def test_bridge_persists_allowlisted_resolver_diagnostics_without_raw_details() -> None:
    store = FakeStore()
    node = _node("https://www.semanticscholar.org/paper/s2-1")
    result = LiteratureMapImportBridge(
        importer=lambda snapshot, source_url: pytest.fail("missing PDF must not invoke importer"),
        source_resolver=lambda _: {
            "error_code": "PDF_NOT_FOUND",
            "resolver_code": "SEMANTIC_SCHOLAR_NO_OPEN_PDF",
            "resolver_codes": [
                "ARXIV_UNAVAILABLE",
                "SEMANTIC_SCHOLAR_NO_OPEN_PDF",
                "provider body: https://secret.example/key=abc",
            ],
            "raw_url": "https://secret.example/private.pdf",
        },
        store=store,
        owner_id="owner-1",
    ).import_node(node, node.source_url or "")

    assert result["error_code"] == "PDF_NOT_FOUND"
    assert result["resolver_code"] == "SEMANTIC_SCHOLAR_NO_OPEN_PDF"
    assert result["resolver_codes"] == ["ARXIV_UNAVAILABLE", "SEMANTIC_SCHOLAR_NO_OPEN_PDF"]
    assert "secret.example" not in repr(result)
    assert store.calls[0][3] == result


@pytest.mark.parametrize(
    ("error_code", "retryable"),
    [
        ("ARXIV_RATE_LIMITED", True),
        ("ARXIV_HTTP_ERROR", False),
        ("ARXIV_INVALID_RESPONSE", False),
        ("ARXIV_UNAVAILABLE", True),
        ("SEMANTIC_SCHOLAR_RATE_LIMITED", True),
    ],
)
def test_bridge_preserves_provider_failure_and_retryability(
    error_code: str,
    retryable: bool,
) -> None:
    store = FakeStore()
    node = _node("https://www.semanticscholar.org/paper/s2-1")
    result = LiteratureMapImportBridge(
        importer=lambda *_args: pytest.fail("provider failure must not invoke importer"),
        source_resolver=lambda _: {
            "error_code": error_code,
            "resolver_code": error_code,
            "resolver_codes": [error_code],
            "retryable": retryable,
            "provider_exception": "https://secret.example/key=bad",
        },
        store=store,
        owner_id="owner-1",
    ).import_node(node, node.source_url or "")

    assert result["error_code"] == error_code
    assert result["resolver_code"] == error_code
    assert result["resolver_codes"] == [error_code]
    assert result["retryable"] is retryable
    assert "secret.example" not in repr(result)
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
