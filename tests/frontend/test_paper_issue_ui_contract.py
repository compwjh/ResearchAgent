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
