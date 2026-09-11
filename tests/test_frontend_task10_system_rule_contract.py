"""Static contracts for Spec022 Task10 desktop navigation and system rules."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_system_rule_card_and_dialog_are_independent_from_memories() -> None:
    for marker in (
        'id="system-rule-card"',
        'id="system-rule-input"',
        'id="system-rule-edit-button"',
        'id="system-rule-toggle-button"',
        'id="system-rule-clear-button"',
        'id="system-rule-clear-dialog"',
    ):
        assert marker in INDEX
    for endpoint in ("/api/system-rule", "method: 'PUT'", "method: 'PATCH'", "method: 'DELETE'"):
        assert endpoint in APP
    assert "12000" in INDEX + APP
    assert "Array.from(systemRuleInput.value).length" in APP


def test_memory_navigation_switches_to_chat_before_opening_and_snapshots_state() -> None:
    start = APP.index("function openConversationFromWorkspace")
    end = APP.index("function renderMemoryProjectOptions", start)
    body = APP[start:end]
    assert "captureMemoryViewState()" in body
    assert "showView('chat')" in body
    assert "openConversation(conversationId)" in body
    for marker in ("memoryNavigationSnapshot.scope", "scrollTop", "expandedProjectId", "restoreMemoryViewState"):
        assert marker in APP


def test_project_rows_are_single_column_and_folder_svg_is_accessible() -> None:
    assert "grid-template-columns: minmax(0, 1fr);" in STYLES
    assert "createProjectFolderIcon" in APP
    assert 'setAttribute(\'aria-hidden\', \'true\')' in APP
    assert "setAttribute('aria-expanded'" in APP
    assert "project-item-toggle" not in APP
    assert "▰" not in APP
    assert "项目</span><span aria-hidden=\"true\">▼" in INDEX


def test_unbound_pending_memory_requires_existing_project_choice() -> None:
    render_start = APP.index("function renderMemoryAnalysisResult")
    render_end = APP.index("async function decideMemoryAnalysisItem", render_start)
    renderer = APP[render_start:render_end]
    assert "选择已有 active 项目" in renderer
    assert "data-memory-project" in APP
    assert "item.suggested_scope === 'global'" in renderer
    decision_start = APP.index("async function decideMemoryAnalysisItem")
    decision_end = APP.index("async function decideMemoryAnalysisBatch", decision_start)
    assert "selectedProjectId" in APP[decision_start:decision_end]


def test_system_rule_suggestion_never_saves_automatically_and_processing_is_deduped() -> None:
    assert "systemRuleSuggestionFromText" in APP
    assert "预填系统规则编辑器" in APP
    assert "openSystemRuleEditor(suggestion)" in APP
    assert "system-rule-applied" in APP
    assert "已应用系统规则" in APP


def test_task10_asset_versions_and_safe_dynamic_content() -> None:
    assert "/assets/app.js?v=31" in INDEX
    assert "/assets/styles.css?v=31" in INDEX
    assert "textContent" in APP
    assert "memory-open-conversation" in APP
