"""Static frontend contracts for Spec034 Task04 plan and approval cards."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
RESEARCH = (ROOT / "frontend/research-tasks.js").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_plan_projection_is_whitelisted_and_reuses_assistant_messages() -> None:
    start = APP.index("const RESEARCH_PLAN_FIELDS")
    end = APP.index("function updateConversationProcessing", start)
    renderer = APP[start:end]
    for field in ("objective", "scope", "work_items", "capabilities", "budget", "report_structure", "safety_summary"):
        assert field in renderer
    assert "research-plan" in renderer
    assert "textContent" in renderer
    assert "innerHTML" not in renderer
    assert "prompt" not in renderer.lower()
    assert "https?" in renderer
    assert "createAssistantMessage" in APP


def test_unified_commands_and_all_six_entry_points_are_present() -> None:
    for command in (
        "approve_plan", "revise_plan", "cancel_research",
        "approve_capability", "approve_resource_extension", "decline_request",
    ):
        assert command in APP
    assert "/api/research-sessions/${encodeURIComponent(sessionId)}/commands" in APP
    assert "subject_version" in APP
    assert "scope_json" in APP
    assert "idempotency_key" in APP


def test_approval_state_is_observable_and_recoverable() -> None:
    for marker in ("loading", "success", "error", "stale", "conflict", "aria-busy", "is-loading"):
        assert marker in APP
    assert "disabled" in APP
    assert "APPROVAL_STALE" in APP
    assert "APPROVAL_CONFLICT" in APP


def test_research_tab_has_session_plan_and_approval_projection() -> None:
    assert "research-session-plan-section" in INDEX
    assert "research-session-approvals" in INDEX
    assert "renderSessionPlan" in RESEARCH
    assert "renderSessionApprovals" in RESEARCH
    assert "/api/research-sessions/" in RESEARCH
    assert "approve_capability" in RESEARCH
    assert "approve_resource_extension" in RESEARCH
    assert "research-session-plan" in STYLES
    assert "task.research_session_id" in RESEARCH
    assert "task.session_plan" in RESEARCH
    assert "task.session_approvals" in RESEARCH


def test_research_tab_has_no_legacy_feedback_approval_bypass() -> None:
    assert "/api/research-tasks/${encodeURIComponent(taskId)}/feedback" not in RESEARCH
    assert "approveTask" not in RESEARCH
    assert "research-approve-button" not in INDEX


def test_unknown_approval_kind_fails_closed_and_stale_has_refresh_path() -> None:
    assert "Object.prototype.hasOwnProperty.call(RESEARCH_APPROVAL_LABELS, approval.kind)" in APP
    assert "addConversationResearchRefresh" in APP
    assert "addSessionRefreshAction" in RESEARCH
    assert "button.disabled = true" in APP[APP.index("async function submitResearchSessionCommand"):APP.index("function renderConversationApprovals")]
    assert "button.disabled = true" in RESEARCH[RESEARCH.index("async function submitSessionCommand"):RESEARCH.index("function renderSessionApprovals")]
    assert "conversation-research-refresh" in STYLES
    assert "research-session-refresh" in STYLES


def test_task04_consumes_backend_scope_and_safe_summary_names_first() -> None:
    assert "approval?.scope ?? approval?.requested_scope_json" in APP
    assert "approval?.scope ?? approval?.requested_scope_json" in RESEARCH
    assert "plan.safe_summary !== undefined" in APP
    assert "plan.safe_summary !== undefined" in RESEARCH
    assert "safe_summary" in APP
    assert "safe_summary" in RESEARCH


def test_assets_are_versioned_and_new_classes_have_scoped_css() -> None:
    assert "/assets/app.js?v=45" in INDEX
    assert "/assets/styles.css?v=45" in INDEX
    for class_name in ("conversation-research-plan", "conversation-research-approval", "research-session-plan", "research-session-approval"):
        assert f".{class_name}" in STYLES
