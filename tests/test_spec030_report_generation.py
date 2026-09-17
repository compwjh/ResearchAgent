import json

import pytest
from fastapi.testclient import TestClient

from backend.app.api import routes_research
from backend.app.main import app
from backend.app.research.application.evidence_matrix import EvidenceMatrixError
from backend.app.research.application.report_generation import (
    EvidenceReportError,
    ReportGenerationService,
    render_evidence_report,
)
from backend.app.research.domain.models import ResearchReport, ResearchTask
from backend.app.research.infrastructure.research_store import ResearchReportConflict, ResearchStore


def _matrix():
    return {
        "schema_version": "evidence-report-v1",
        "task_id": "task-1",
        "plan_version": 1,
        "claims": [
            {"claim_id": "claim-1", "task_id": "task-1", "topic": "方法", "statement": "A supports B", "status": "supported", "evidence_ids": ["e-1"]},
            {"claim_id": "claim-2", "task_id": "task-1", "topic": "缺口", "statement": "No conclusion", "status": "unresolved", "evidence_ids": []},
        ],
        "evidence": [
            {"evidence_id": "e-1", "claim_id": "claim-1", "task_id": "task-1", "paper_id": "paper-a", "evidence_level": "abstract", "stance": "supports", "status": "available"},
            {"evidence_id": "e-2", "claim_id": "claim-2", "task_id": "task-1", "paper_id": "paper-b", "evidence_level": "catalog", "stance": "contextual", "status": "unavailable"},
        ],
        "dimensions": [{"dimension_id": "d-1", "label": "维度", "definition": "定义"}],
        "cells": [
            {"claim_id": "claim-1", "paper_id": "paper-a", "dimension_id": "d-1", "relation": "supports", "summary": "bounded", "evidence_ids": ["e-1"]},
            {"claim_id": "claim-2", "paper_id": "paper-b", "dimension_id": "d-1", "relation": "missing", "summary": "", "evidence_ids": [], "missing_reason": "No locator"},
        ],
        "limitations": ["Coverage is partial."],
    }


def test_report_projection_has_numeric_manifest_and_safe_consistent_views():
    built = render_evidence_report(_matrix(), report_id="r-1", report_version=1, title="<Report>")
    report = built["report"]
    assert report["status"] == "partial"
    assert report["citation_manifest"]["citations"] == [{"citation_no": 1, "paper_id": "paper-a", "evidence_ids": ["e-1"], "claim_ids": ["claim-1"]}]
    assert "[1]" in built["markdown"]
    assert 'data-citation-no="1"' in built["html"]
    assert "&lt;Report&gt;" in built["html"]
    assert "<Report>" not in built["html"]
    assert "No conclusion" in json.dumps(report, ensure_ascii=False)


def test_report_rejects_orphan_and_unavailable_cell_evidence():
    matrix = _matrix()
    matrix["claims"][0]["evidence_ids"] = ["deleted"]
    with pytest.raises(EvidenceReportError):
        render_evidence_report(matrix, report_id="r-1", report_version=1)
    matrix = _matrix()
    matrix["cells"][0]["evidence_ids"] = ["e-2"]
    with pytest.raises(EvidenceReportError):
        render_evidence_report(matrix, report_id="r-1", report_version=1)


class _Store:
    def __init__(self, matrix):
        self.matrix = matrix
        self.saved = []

    def get_task(self, task_id, owner_id):
        return object()

    def next_report_version(self, task_id, owner_id):
        return 2

    def save_research_report(self, report, *, owner_id):
        self.saved.append(report)
        return report

    def get_research_report(self, task_id, owner_id, *, report_version=None):
        return self.saved[-1] if self.saved else None

    def list_claims(self, task_id, *, plan_version=None):
        return []

    def list_claim_evidence(self, task_id, *, plan_version=None):
        return []

    def list_comparison_dimensions(self, task_id, *, plan_version=None):
        return []

    def list_comparison_cells(self, task_id, *, plan_version=None):
        return []


def test_generation_persists_one_immutable_projection(monkeypatch):
    store = _Store(_matrix())
    monkeypatch.setattr(
        "backend.app.research.application.report_generation.EvidenceMatrixService.read_matrix",
        lambda self, *args, **kwargs: store.matrix,
    )
    result = ReportGenerationService(store).generate("task-1", "owner-1")
    assert result["report"]["report_version"] == 2
    assert len(store.saved) == 1
    assert json.loads(store.saved[0].report_json)["report_id"] == result["report"]["report_id"]


def test_store_rejects_overwriting_a_report_version(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite3")
    task = ResearchTask("task-1", "owner-1", "conversation-1", "goal", "zh", "speed", False, 1, 60, "draft", 1, "now", "now")
    store.create_task(task)
    report = ResearchReport("report-1", "task-1", 1, 1, "partial", "# one", "<p>one</p>", '{"report_id":"report-1"}', "[]", "now")
    store.save_research_report(report, owner_id="owner-1")
    replacement = ResearchReport("report-2", "task-1", 1, 1, "completed", "# two", "<p>two</p>", '{"report_id":"report-2"}', "[]", "now")
    with pytest.raises(ResearchReportConflict):
        store.save_research_report(replacement, owner_id="owner-1")


class _MissingReportService:
    def read(self, task_id, owner_id, *, report_version=None, format="json"):
        raise EvidenceReportError("report is not ready", code="REPORT_NOT_READY")


def _json_response(response):
    if hasattr(response, "json"):
        return response.json()
    return json.loads(response.body)


@pytest.mark.parametrize(
    ("task_id", "report_version"),
    [("unknown-task", 1), ("task-1", 999)],
)
def test_versioned_report_unknown_task_or_version_returns_safe_404(monkeypatch, task_id, report_version):
    monkeypatch.setattr(routes_research, "_report_generation_service", lambda: _MissingReportService())

    response = routes_research.get_versioned_research_report(task_id, report_version, format="json")

    assert response.status_code == 404
    assert _json_response(response) == {
        "error": {"code": "REPORT_NOT_READY", "message": "report is not ready"}
    }
    assert "AttributeError" not in response.body.decode()


def test_versioned_report_rejects_unsupported_format_with_406(monkeypatch):
    class _UnexpectedService:
        def read(self, *_args, **_kwargs):
            raise AssertionError("unsupported format must be rejected at the API boundary")

    monkeypatch.setattr(routes_research, "_report_generation_service", lambda: _UnexpectedService())

    response = routes_research.get_versioned_research_report("task-1", 1, format="xml")

    assert response.status_code == 406
    assert _json_response(response) == {
        "error": {"code": "FORMAT_SEMANTIC_MISMATCH", "message": "不支持的报告格式"}
    }


def test_report_generation_error_response_uses_exception_text(monkeypatch):
    class _FailingService:
        def generate(self, *_args, **_kwargs):
            raise EvidenceReportError("matrix is not ready", code="REPORT_NOT_READY")

    monkeypatch.setattr(routes_research, "_report_generation_service", lambda: _FailingService())

    response = TestClient(app).post("/api/research-tasks/task-1/reports", json={})

    assert response.status_code == 409
    assert _json_response(response) == {
        "error": {"code": "REPORT_NOT_READY", "message": "matrix is not ready"}
    }


def test_report_generation_maps_matrix_not_ready_to_report_not_ready_409(monkeypatch):
    class _MatrixNotReadyService:
        def generate(self, *_args, **_kwargs):
            raise EvidenceMatrixError("MATRIX_NOT_READY", "证据矩阵尚未准备完成")

    monkeypatch.setattr(routes_research, "_report_generation_service", lambda: _MatrixNotReadyService())

    response = TestClient(app).post("/api/research-tasks/task-1/reports", json={})

    assert response.status_code == 409
    assert _json_response(response) == {
        "error": {"code": "REPORT_NOT_READY", "message": "report is not ready"}
    }
