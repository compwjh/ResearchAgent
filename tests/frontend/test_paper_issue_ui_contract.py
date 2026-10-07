"""Spec032 Task12 frontend contracts for source progress and issue recovery UI."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
RESEARCH = (ROOT / "frontend/research-tasks.js").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_source_progress_is_server_driven_and_exposes_coverage() -> None:
    assert "paperSourceProgressByKind" in APP
    assert "source_id || item.source_kind || item.source" in APP
    assert "paperSourceVerifiedYears" in APP
    assert "已验证年份" in APP
    assert "部分覆盖" in APP
    assert "host.replaceChildren()" in APP
    assert "source_kind === 'usenix' || source_kind === 'dblp'" not in APP
    assert 'id="paper-source-empty"' in INDEX
    assert "grid-template-columns: repeat(auto-fit" in STYLES


def test_issue_recovery_actions_are_status_scoped_and_upload_requires_confirmation() -> None:
    assert "/api/papers/issues/${encodeURIComponent(issueId)}/${action}" in RESEARCH
    assert "/api/papers/issues/${encodeURIComponent(issueId)}/upload?identity_verdict=confirmed&identity_confirmed=true" in RESEARCH
    assert "status === 'waiting_login'" in RESEARCH
    assert "new Set(['login', 'resume', 'upload'])" in RESEARCH
    assert "new Set(['retry', 'upload'])" in RESEARCH
    assert "我确认上传文件属于该候选论文" in RESEARCH
    assert "report_action === 'generate_new_version'" in RESEARCH
    assert 'id="research-issue-queue"' in INDEX
    assert "research-field-provenance" in RESEARCH
    assert ".innerHTML" not in RESEARCH


def test_report_failure_reconciles_task_acquisitions_before_resetting_report_state() -> None:
    start = RESEARCH.index("async function loadReport")
    catch_start = RESEARCH.index("} catch (error) {", start)
    catch_end = RESEARCH.index("\n    }\n  }", catch_start)
    failure_path = RESEARCH[catch_start:catch_end]
    assert "const acquisition = await loadAcquisitionStatus(taskId);" in failure_path
    assert failure_path.index("loadAcquisitionStatus(taskId)") < failure_path.index("state.acquisition.preview = []")
    assert "state.acquisition.issues = [];" not in failure_path
    # A missing batch is a normal pre-confirmation state, not an acquisition error.
    status_start = RESEARCH.index("async function loadAcquisitionStatus")
    status_end = RESEARCH.index("\n  function scheduleAcquisitionPoll", status_start)
    status_path = RESEARCH[status_start:status_end]
    assert "error.status !== 404 && error.code !== 'BATCH_NOT_FOUND'" in status_path


def test_report_action_uses_an_explicit_versioned_generation_button() -> None:
    action_start = RESEARCH.index("async function generateReportVersion")
    action_end = RESEARCH.index("\n  function issueState", action_start)
    action = RESEARCH[action_start:action_end]
    assert "/api/research-tasks/${encodeURIComponent(taskId)}/reports" in action
    assert "method: 'POST'" in action
    assert "JSON.stringify({ plan_version: planVersion })" in action
    post_start = action.index("result = await requestJson")
    post_end = action.index("});", post_start)
    assert "report_version" not in action[post_start:post_end]
    assert "generateReportVersion" in RESEARCH
    assert "readGeneratedReportVersion" in action
    assert "button.disabled = state.acquisition.reportActionInFlight" in RESEARCH
    assert "/assets/research-tasks.js?v=16" in INDEX


def test_upload_only_surfaces_report_action_and_does_not_generate_implicitly() -> None:
    upload_start = RESEARCH.index("async function uploadIssue")
    upload_end = RESEARCH.index("\n  function renderAcquisitionIssues", upload_start)
    upload_handler = RESEARCH[upload_start:upload_end]
    assert "/api/papers/issues/${encodeURIComponent(issueId)}/upload" in upload_handler
    assert "/api/research-tasks/${encodeURIComponent(taskId)}/reports" not in upload_handler
    assert "reportActionTaskIds" in upload_handler


def test_report_action_failure_restores_the_previous_report_for_retry() -> None:
    action_start = RESEARCH.index("async function generateReportVersion")
    action_end = RESEARCH.index("\n  function issueState", action_start)
    action = RESEARCH[action_start:action_end]
    assert "const previousReport = state.report" in action
    assert "state.report = previousReport" in action
    assert "旧报告保持不变" in action


def test_report_actions_and_version_selection_guard_delayed_responses() -> None:
    action_start = RESEARCH.index("async function generateReportVersion")
    action_end = RESEARCH.index("\n  const ISSUE_ACTION_LABELS", action_start)
    action = RESEARCH[action_start:action_end]
    assert "const requestGeneration = state.taskGeneration" in action
    assert "isCurrentTaskGeneration(taskId, requestGeneration)" in action
    assert "if (!isCurrent()) return null" in action
    assert "if (isCurrent())" in action
    assert "async function uploadIssue" in RESEARCH
    upload_start = RESEARCH.index("async function uploadIssue")
    upload_end = RESEARCH.index("\n  function renderAcquisitionIssues", upload_start)
    upload = RESEARCH[upload_start:upload_end]
    assert "const requestGeneration = state.taskGeneration" in upload
    assert "if (!isCurrent()) return null" in upload
    version_start = RESEARCH.index("async function selectReportVersion")
    version_end = RESEARCH.index("\n  async function loadMatrix", version_start)
    version = RESEARCH[version_start:version_end]
    assert "const requestId = ++state.reportVersionRequest" in version
    assert "const previousReportViews = new Map(state.reportViews || [])" in version
    assert "state.report = previousReport" in version
    assert "requestText" in version
    select_start = RESEARCH.index("async function selectTask")
    select_end = RESEARCH.index("\n  async function refreshWorkspace", select_start)
    selection = RESEARCH[select_start:select_end]
    assert "state.taskGeneration += 1" in selection
    assert "state.reportVersionRequest += 1" in selection
