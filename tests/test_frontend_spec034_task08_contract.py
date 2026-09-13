"""Static contracts for Spec034 Task08 report and notification UI."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
RESEARCH = (ROOT / "frontend/research-tasks.js").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_report_projection_has_allowlisted_artifacts_and_safe_dom_boundary() -> None:
    for marker in ("renderConversationReport", "citation_manifest", "download", "noopener noreferrer", "reportStatusLabel", "mode=inline", "artifactActionUrl"):
        assert marker in APP
    assert "textContent" in APP
    assert "innerHTML" not in APP[APP.index("function renderConversationReport"):APP.index("function renderConversationMessage")]
    assert "safeArtifactUrl" in RESEARCH and "ARTIFACT_ROUTE" in RESEARCH
    assert "artifactActionUrl" in RESEARCH and "mode=inline" in RESEARCH


def test_research_tab_fetches_session_artifacts_and_has_empty_error_states() -> None:
    assert "/api/research-sessions/${encodeURIComponent(sessionId)}/artifacts" in RESEARCH
    for marker in ("renderReportArtifacts", "renderReportCitations", "任务完成后显示报告", "报告尚未生成"):
        assert marker in RESEARCH or marker in INDEX
    for marker in ('id="research-report-artifacts"', 'id="research-report-citations"', 'id="research-report-citation-list"'):
        assert marker in INDEX


def test_notification_cursor_sse_read_and_six_state_contract() -> None:
    for marker in ("research-notifications", "after_seq", "Last", "notificationLastSeq", "markNotificationRead", "NOTIFICATION_EVENT_TYPES"):
        assert marker in RESEARCH or marker in INDEX
    for kind in ("completed", "partial", "failed", "waiting_approval", "interrupted"):
        assert kind in RESEARCH
    assert "retry'" not in RESEARCH.split("const NOTIFICATION_EVENT_TYPES", 1)[1].split("const ARTIFACT_TYPES", 1)[0]
    assert "retryable" in RESEARCH and "retry_attempt" in RESEARCH and "研究失败，可重试" in RESEARCH
    assert "heartbeat" in RESEARCH
    assert "/api/research-notifications/${encodeURIComponent(notification.notification_id)}/read" in RESEARCH


def test_notification_and_report_css_is_scoped_and_motion_safe() -> None:
    for marker in ("research-notification-item", "conversation-report", "research-report-artifact", "research-report-citations"):
        assert marker in STYLES
    assert "@media (prefers-reduced-motion: reduce)" in STYLES
    assert "#research-view .research-report-artifact" in STYLES


def test_task08_assets_are_versioned() -> None:
    assert "/assets/app.js?v=47" in INDEX
    assert "/assets/styles.css?v=47" in INDEX
