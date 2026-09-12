"""Static contracts for the Spec022 Task09 desktop project tree."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_single_project_tree_replaces_legacy_switcher() -> None:
    assert INDEX.count("项目") >= 1
    for legacy in ('id="project-select"', 'id="new-project-form"', 'class="governance-actions"'):
        assert legacy not in INDEX
    for marker in ("project-tree-toggle", "project-tree-menu-button", "project-list", "conversation-list"):
        assert f'id="{marker}"' in INDEX


def test_project_tree_has_nested_pagination_and_recent_conversation_limits() -> None:
    assert "limit: '10'" in APP
    assert "limit: '20'" in APP
    assert "loadProjectConversations" in APP
    assert "project-conversation-list" in APP
    assert "projectState.expandedProjectId" in APP
    assert "last_activity_at" in APP


def test_conversation_list_requests_use_frozen_status_scopes() -> None:
    project_start = APP.index("async function loadProjectConversations")
    project_end = APP.index("function openActionDialog", project_start)
    project_body = APP[project_start:project_end]
    assert "project_id: projectId, status: 'active', limit: '10'" in project_body

    recent_start = APP.index("async function loadConversationList")
    recent_end = APP.index("async function loadProjects", recent_start)
    recent_body = APP[recent_start:recent_end]
    assert "status: conversationListState.showArchived ? 'archived' : 'active'" in recent_body
    assert "params.set('unbound_only', 'true')" in recent_body
    assert "!conversationListState.showArchived" in recent_body


def test_move_dialog_uses_independent_active_projects_and_project_id_values() -> None:
    start = APP.index("function activeMoveProjects")
    end = APP.index("async function moveConversation", start)
    move_ui = APP[start:end]
    assert "item.status === 'active'" in move_ui
    assert "item.project_id !== excludeProjectId" in move_ui
    assert "option.value = item.project_id" in move_ui
    assert "visibleProjects(projectState.items)" not in move_ui
    assert "conversation-action-project-search" in INDEX


def test_uses_dialogs_and_central_overlay_menus() -> None:
    for marker in ("conversation-action-dialog", "conversation-confirm-dialog", "showModal()", "openFloatingMenu", "floating-menu", "closeFloatingMenu"):
        assert marker in (INDEX + APP + STYLES)
    task09_start = APP.index("function renderProjectOptions")
    task09_end = APP.index("async function loadConversationMessages")
    task09 = APP[task09_start:task09_end]
    assert "window.prompt" not in task09
    assert "window.confirm" not in task09
    assert "confirm_move" in task09
    assert "include_prior_history" in APP
    assert "from_binding" in APP


def test_dialog_cancel_paths_cannot_dispatch_actions() -> None:
    for handler in ("createProject", "submitActionDialog", "submitConfirmDialog"):
        start = APP.index(f"async function {handler}")
        end = APP.find("\nasync function ", start + 1)
        body = APP[start:] if end < 0 else APP[start:end]
        assert "event.submitter?.value === 'cancel'" in body
        assert "preventDefault()" in body
        assert ".close()" in body
    assert "addEventListener('cancel'" in APP
    assert "function closeDialogFromCancelClick" in APP
    assert "dialogForm?.addEventListener('click', closeDialogFromCancelClick)" in APP


def test_move_and_delete_clear_context_and_project_rows_have_independent_archive_filter() -> None:
    move_start = APP.index("async function moveConversation")
    move_end = APP.index("async function loadConversationList", move_start)
    move_body = APP[move_start:move_end]
    assert "conversationState.draftProjectId = updated.project_id || null" in move_body
    assert "projectState.expandedProjectId = updated.project_id" in move_body
    assert "entry.items = (entry.items || []).filter" in move_body
    delete_start = APP.index("async function submitConfirmDialog")
    delete_end = APP.index("const MEMORY_STATUS_LABELS", delete_start)
    delete_body = APP[delete_start:delete_end]
    assert "conversationState.draftProjectId = null" in delete_body
    assert "projectState.conversations.delete(target.project_id)" in delete_body
    assert "owner === 'recent' ? conversationListState.showArchived : false" in APP


def test_dynamic_tree_content_uses_text_content_not_html_concatenation() -> None:
    start = APP.index("function renderProjectOptions")
    end = APP.index("async function loadConversationMessages")
    renderer = APP[start:end]
    assert "textContent" in renderer
    assert "innerHTML" not in renderer


def test_menu_and_asset_contract() -> None:
    assert "pointerdown" in APP
    assert "event.key === 'Escape'" in APP
    assert "getBoundingClientRect" in APP
    assert "position: fixed" in STYLES
    assert "/assets/app.js?v=31" in INDEX
    assert "/assets/styles.css?v=30" in INDEX
