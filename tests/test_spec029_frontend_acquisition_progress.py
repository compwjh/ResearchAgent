"""Spec029 Task05 acquisition progress/recovery UI contracts."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = (ROOT / "frontend/research-tasks.js").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_acquisition_preview_and_explicit_confirmation_contract() -> None:
    assert "/api/research-tasks/${encodeURIComponent(taskId)}/acquisition-preview" in RESEARCH
    assert "/api/research-tasks/${encodeURIComponent(taskId)}/acquisitions" in RESEARCH
    assert "selection_version" in RESEARCH
    assert "idempotency_key" in RESEARCH
    assert "confirmAcquisition" in RESEARCH
    assert "确认前不会下载" in INDEX
    assert "research-acquisition-confirm" in INDEX
    # Preview is the only automatic acquisition request; confirmation is bound
    # to the explicit button handler and must not use browser dialogs.
    assert "method: 'POST'" in RESEARCH
    assert "confirm(" not in RESEARCH
    assert "prompt(" not in RESEARCH


def test_candidate_editing_and_projected_statuses_are_visible() -> None:
    for marker in (
        "research-acquisition-candidates",
        "research-acquisition-selection-count",
        "selectedIds.add",
        "selectedIds.delete",
        "existing",
        "needs_login",
        "waiting_login",
        "failed",
        "请在既有浏览器会话完成登录",
    ):
        assert marker in RESEARCH or marker in INDEX
    assert "research-acquisition-items" in INDEX
    assert "research-acquisition-progress-summary" in INDEX
    assert "research-acquisition-refresh" in INDEX


def test_failure_retry_reuses_existing_import_item_endpoint() -> None:
    assert "/api/papers/import-items/${encodeURIComponent(itemId)}/retry" in RESEARCH
    assert "retryAcquisitionItem" in RESEARCH
    assert "导入状态" in RESEARCH
    assert "state.acquisition.retrying" in RESEARCH


def test_fulltext_locator_and_dom_xss_contract() -> None:
    assert "research-evidence-upgrades" in INDEX
    assert "research-evidence-locator" in RESEARCH
    assert "chunk_ids" in RESEARCH
    assert "jumpToKnowledgeBase" in RESEARCH
    assert ".innerHTML" not in RESEARCH
    for marker in (
        "research-acquisition-section",
        "research-acquisition-candidate",
        "research-acquisition-item[data-status=\"waiting_login\"]",
        "research-evidence-locator",
    ):
        assert marker in STYLES
