"""Static contracts for Spec022 Task03 desktop governance UI."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_management_dom_contract_is_present() -> None:
    for element_id in (
        "project-tree-menu-button",
        "conversation-action-dialog",
        "conversation-confirm-dialog",
        "memory-view",
        "memory-scope-select",
        "memory-project-select",
        "memory-list",
        "memory-status",
    ):
        assert f'id="{element_id}"' in INDEX
    assert 'data-view="memory"' in INDEX


def test_management_api_and_confirmation_contract() -> None:
    for endpoint in (
        "/api/projects",
        "/api/conversations",
        "/api/memories",
        "/evidence",
        "/confirm",
        "/disable",
        "/undo",
        "confirm_move",
        "include_prior_history",
        "from_binding",
    ):
        assert endpoint in APP


def test_memory_scope_and_governance_actions_are_rendered() -> None:
    for marker in (
        "scope",
        "candidate",
        "superseded",
        "active",
        "disabled",
        "deleted",
        "查看来源",
        "编辑为新版本",
        "撤销",
    ):
        assert marker in APP


def test_governance_renderers_use_safe_text_boundaries() -> None:
    for function_name in ("renderMemoryList", "renderMemoryEvidence"):
        assert function_name in APP
    start = APP.index("function renderMemoryList")
    end = APP.index("async function loadMemories", start)
    renderer = APP[start:end]
    assert "textContent" in renderer
    assert "innerHTML" not in renderer


def test_keeps_static_asset_versions_and_scoped_css() -> None:
    assert "/assets/app.js?v=31" in INDEX
    assert "/assets/styles.css?v=30" in INDEX
    assert "#memory-view" in STYLES
    assert ".memory-item" in STYLES


def test_memory_navigation_is_keyboard_activatable() -> None:
    assert "item.addEventListener('keydown'" in APP
    assert "event.key !== 'Enter' && event.key !== ' '" in APP
    assert "showView(item.dataset.view);" in APP
