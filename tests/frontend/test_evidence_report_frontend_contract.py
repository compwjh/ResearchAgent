"""Spec030 Task05: report workspace static contracts."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
RESEARCH = (ROOT / "frontend/research-tasks.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_report_workspace_exposes_matrix_versions_formats_and_locator_controls():
    for marker in (
        'id="research-matrix-section"',
        'id="research-evidence-matrix"',
        'id="research-matrix-gap-list"',
        'id="research-report-version-select"',
        'data-report-format="markdown"',
        'data-report-format="html"',
        'data-report-format="json"',
        'id="research-report-citation-detail"',
    ):
        assert marker in INDEX
    for marker in (
        "/evidence-matrix",
        "/reports/${version}?format=json",
        "requestText",
        "openEvidenceLocator",
        "createCitationButton",
        "locator.chunk_ids",
    ):
        assert marker in RESEARCH


def test_report_workspace_uses_text_dom_boundaries_and_responsive_styles():
    assert "innerHTML" not in RESEARCH
    assert "textContent" in RESEARCH
    for marker in ("research-matrix-table", "research-citation-button", "research-report-format-tab", "max-width: 760px"):
        assert marker in STYLES


def test_report_quality_feedback_exposes_publication_metrics_progress_and_retry():
    for marker in (
        'id="research-report-feedback"',
        'id="research-report-publication"',
        'id="research-report-progress"',
        'id="research-report-quality-metrics"',
        'id="research-report-reasons"',
        'id="research-report-retry"',
    ):
        assert marker in INDEX
    for marker in (
        "report-quality-v1",
        "Idempotency-Key",
        "report_url",
        "quality_validation",
        "elapsed_seconds",
        "renderReportFeedback",
        "scheduleReportPoll",
        "reportDownloadAllowed",
        "isQualityValidated",
    ):
        assert marker in RESEARCH
    for marker in ("research-report-feedback", "research-report-quality-metric", "research-report-retry"):
        assert marker in STYLES
    assert "innerHTML" not in RESEARCH
