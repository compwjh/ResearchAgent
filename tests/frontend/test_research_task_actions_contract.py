"""Static contracts for Spec028 Task05 pause/resume/approval task actions."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = (ROOT / "frontend/research-tasks.js").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_task_action_endpoints_and_state_projection_are_wired() -> None:
    for marker in ("pause: 'pause'", "resume: 'resume'", "approve: 'feedback'", "cancel: 'cancel'"):
        assert marker in RESEARCH
    for marker in (
        "/api/research-tasks/${encodeURIComponent(taskId)}/pause",
        "/api/research-tasks/${encodeURIComponent(taskId)}/resume",
        "/api/research-tasks/${encodeURIComponent(taskId)}/cancel",
        "research-task-pause-button",
        "research-task-resume-button",
        "research-task-approve-button",
        "research-cancel-button",
        "research-recovery-notice",
    ):
        assert marker in INDEX or marker in RESEARCH
    for marker in ("paused", "waiting_approval", "TASK_ACTION_STATUSES", "submitTaskAction", "renderTaskActionControls"):
        assert marker in RESEARCH
    assert "state.selectedTask = { ...state.selectedTask, ...result" in RESEARCH


def test_task_actions_are_confirmed_idempotent_and_error_recoverable() -> None:
    for marker in ("再次点击确认", "taskActionInFlight", "aria-busy", "提交失败，重试", "状态已变化，请刷新"):
        assert marker in RESEARCH
    assert "confirm(" not in RESEARCH
    assert "prompt(" not in RESEARCH
    assert "button.disabled = !available || state.taskActionInFlight" in RESEARCH
    assert "TASK_TERMINAL_CONFLICT" in RESEARCH
    assert "PLAN_VERSION_STALE" in RESEARCH


def test_task_action_dom_and_css_are_safe_scoped_and_versioned() -> None:
    assert ".innerHTML" not in RESEARCH
    for marker in ("research-task-action", "research-recovery-notice", "data-status=\"paused\""):
        assert marker in STYLES
    assert '/assets/research-tasks.js?v=3' in INDEX
    assert '/assets/styles.css?v=50' in INDEX
    assert '/assets/app.js?v=50' in INDEX
    assert '/assets/research-tasks.js?v=2' in INDEX  # compatibility marker
