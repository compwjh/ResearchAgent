"""Spec032 Task09: shared Worker Tool envelope and fail-closed source seam."""

from dataclasses import dataclass

from backend.app.paper_discovery.application.worker_tool import (
    PAPER_DISCOVERY_TOOL_NAME,
    WORKER_TOOL_SCHEMA_VERSION,
    PaperDiscoveryToolFacade,
    validate_worker_tool_result,
)
from backend.app.skills.registry import build_default_tool_registry
from backend.app.skills.tool_dispatch import build_default_dispatch


@dataclass
class _Entry:
    source_id: str
    enabled: bool = True


class _Store:
    def list_conferences(self):
        return [
            type("Conference", (), {"conference_id": "usenix-security", "enabled": True})(),
        ]


class _Usenix:
    def search(self, _conference, _query, _years, limit=20):
        del limit
        return type("Result", (), {
            "records": ({"title": "USENIX paper", "year": 2024, "doi": "10.1/usenix"},),
            "error_code": None,
        })()

    def normalize_identity(self, record):
        return f"doi:{record['doi']}"


class _Ieee:
    def sync_units(self, _scope):
        return type("Result", (), {
            "records": ({
                "title": "IEEE official paper", "year": 2024, "doi": "10.1/ieee",
                "provenance": {"title": "ieee_sp", "year": "ieee_sp"},
            },),
            "failed_years": (), "error_code": None,
        })()

    def normalize_identity(self, record):
        return f"doi:{record['doi']}"


class _Registry:
    def __init__(self):
        self._entries = {"usenix": _Entry("usenix"), "ieee_sp": _Entry("ieee_sp")}
        self._adapters = {"usenix": _Usenix(), "ieee_sp": _Ieee()}

    def get(self, source_id):
        return self._entries.get(source_id)

    def adapter(self, source_id, **_kwargs):
        return self._adapters[source_id]


def test_registry_exposes_one_shared_worker_tool_schema():
    tool = next(item for item in build_default_tool_registry() if item.name == PAPER_DISCOVERY_TOOL_NAME)
    assert tool.parameters["required"] == ["operation", "source_id"]
    assert tool.parameters["properties"]["operation"]["enum"] == ["discover", "import"]
    assert WORKER_TOOL_SCHEMA_VERSION == "worker-tool-v1"


def test_usenix_and_ieee_use_same_result_validator():
    facade = PaperDiscoveryToolFacade(registry=_Registry(), store=_Store())
    usenix = facade.discover("usenix", {"query": "memory", "years": [2024]})
    ieee = facade.discover("ieee_sp", {"years": [2024], "route": "official"})

    for result, source in ((usenix, "usenix"), (ieee, "ieee_sp")):
        checked = validate_worker_tool_result(result.to_dict(), expected_source=source, expected_operation="discover")
        assert checked.schema_version == WORKER_TOOL_SCHEMA_VERSION
        assert checked.source_id == source
        assert checked.provenance
        assert checked.elapsed_ms >= 0
        assert checked.error is None
        assert checked.payload["candidates"][0]["candidate_id"].startswith(f"{source}:")


def test_generic_source_worker_honors_candidate_limit():
    class _ManyIeee(_Ieee):
        def sync_units(self, _scope):
            records = tuple({"title": f"IEEE paper {index}", "year": 2024, "doi": f"10.1/{index}"}
                            for index in range(5))
            return type("Result", (), {"records": records, "failed_years": (), "error_code": None})()

    registry = _Registry()
    registry._adapters["ieee_sp"] = _ManyIeee()
    facade = PaperDiscoveryToolFacade(registry=registry, store=_Store())
    result = facade.discover("ieee_sp", {"years": [2024], "limit": 2})

    assert result.status == "completed"
    assert len(result.payload["candidates"]) == 2


def test_worker_rejects_out_of_range_limit():
    facade = PaperDiscoveryToolFacade(registry=_Registry(), store=_Store())
    result = facade.discover("ieee_sp", {"years": [2024], "limit": 0})

    assert result.status == "failed"
    assert result.error_code == "INVALID_LIMIT"


def test_unknown_source_and_arbitrary_url_fail_closed():
    facade = PaperDiscoveryToolFacade(registry=_Registry(), store=_Store())
    unknown = facade.discover("made-up", {"years": [2024]})
    assert unknown.status == "failed"
    assert unknown.error_code == "SOURCE_NOT_ALLOWED"

    arbitrary = facade.discover("ieee_sp", {"years": [2024], "url": "https://evil.example"})
    assert arbitrary.status == "failed"
    assert arbitrary.error_code == "UNAUTHORIZED_URL"


def test_registered_dispatch_returns_machine_readable_envelope_for_unknown_source():
    result = build_default_dispatch()(PAPER_DISCOVERY_TOOL_NAME, {
        "operation": "discover", "source_id": "unknown",
    })
    assert result.ok is False
    assert '"schema_version": "worker-tool-v1"' in result.output
    assert '"error"' in result.output


def test_worker_preserves_actionable_download_error_and_candidate_id(monkeypatch):
    from backend.app.paper_discovery.application import paper_import
    from backend.app.paper_discovery.infrastructure.paper_download import PaperDownloadError

    def blocked_import(*_args, **_kwargs):
        raise PaperDownloadError("LOGIN_REQUIRED", "login required")

    monkeypatch.setattr(paper_import, "import_candidate", blocked_import)
    monkeypatch.setattr(
        "backend.app.api.common._paper_candidate_hosts",
        lambda _candidate: {"ieeexplore.ieee.org"},
    )
    candidate = {
        "candidate_id": "ieee_sp:doi:10.1109/example",
        "source_id": "ieee_sp",
        "source_kind": "ieee_sp",
        "title": "IEEE paper",
        "pdf_url": "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?arnumber=1",
    }
    facade = PaperDiscoveryToolFacade(registry=_Registry(), store=_Store())
    result = facade.import_candidate("ieee_sp", candidate)

    assert result.status == "failed"
    assert result.candidate_id == candidate["candidate_id"]
    assert result.error_code == "LOGIN_REQUIRED"
    assert result.error.retryable is True
