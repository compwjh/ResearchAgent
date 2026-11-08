"""Static contracts for the Markdown memory document editor."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
        "memory-project-label",
        "memory-document-editor",
        "memory-document-save-button",
        "memory-document-revision",
        "memory-document-conflict",
        "memory-document-conflict-copy",
        "memory-document-conflict-refresh-button",
        "memory-document-count",
        "memory-refresh-button",
        "memory-status",
    ):
        assert f'id="{element_id}"' in INDEX
    assert 'data-view="memory"' in INDEX
    for removed_id in ("memory-status-select", "memory-create-button", "memory-list", "memory-empty"):
        assert f'id="{removed_id}"' not in INDEX


def test_management_api_and_confirmation_contract() -> None:
    for endpoint in (
        "/api/projects",
        "/api/conversations",
        "confirm_move",
        "include_prior_history",
        "from_binding",
    ):
        assert endpoint in APP
    assert "/api/memory-documents" in APP
    assert "/api/memories" not in APP
    assert "method: 'PUT'" in APP
    for marker in ("scope", "project_id", "revision", "MEMORY_DOCUMENT_CONFLICT"):
        assert marker in APP


def test_memory_scope_and_document_actions_are_rendered() -> None:
    for marker in (
        "全局记忆",
        "项目记忆",
        "文档内容",
        "保存文档",
        "正在读取记忆文档",
        "服务器已有新版本",
        "读取最新版本并保留草稿",
        "65536",
    ):
        assert marker in INDEX or marker in APP


def test_document_renderer_uses_safe_text_boundaries() -> None:
    for function_name in ("renderMemoryDocument", "loadMemoryDocument", "saveMemoryDocument"):
        assert function_name in APP
    start = APP.index("function renderMemoryDocument")
    end = APP.index("function appendConversationEvent", start)
    renderer = APP[start:end]
    assert "textContent" in renderer
    assert ".value" in renderer
    assert "innerHTML" not in renderer
    assert "Array.from" in renderer


def test_keeps_static_asset_versions_and_scoped_css() -> None:
    assert 'href="/assets/styles.css?v=71"' in INDEX
    assert 'src="/assets/app.js?v=73"' in INDEX
    assert "#memory-view" in STYLES
    assert "#memory-document-editor" in STYLES
    assert "#memory-document-conflict" in STYLES


def test_document_navigation_protects_dirty_draft_and_builds_fixed_scope_query() -> None:
    for marker in (
        "memoryState.dirty",
        "window.confirm",
        "project_id",
        "new URLSearchParams",
        "scope === 'project'",
        "memoryDocumentDraft",
    ):
        assert marker in APP
    assert "current_content" in APP
    assert "memoryDocumentConflictCopy.textContent" in APP


def test_memory_refresh_and_switch_races_keep_one_canonical_target() -> None:
    options_start = APP.index("function renderMemoryProjectOptions")
    options_end = APP.index("const MEMORY_DOCUMENT_LIMIT", options_start)
    options = APP[options_start:options_end]
    assert "emptyOption.textContent = '请选择项目'" in options
    assert "emptyOption.value = ''" in options
    assert "emptyOption.disabled = true" in options
    assert "memoryState.projectId" in options
    assert "memoryProjectSelect.value = memoryState.projectId" in options
    assert "memoryProjectSelect.value = ''" in options
    assert "memoryState.requestGeneration += 1" in options
    assert "memoryState.projectId = null" in options
    assert "当前项目已失效，请重新选择 active 项目。" in options

    loader_start = APP.index("async function loadMemoryDocument")
    loader_end = APP.index("async function saveMemoryDocument", loader_start)
    loader = APP[loader_start:loader_end]
    assert loader.count("memoryDocumentRequestMatches") >= 3
    stale_guard = "if (!memoryDocumentRequestMatches(requestGeneration, requestKey)) return;"
    assert stale_guard in loader
    assert loader.index(stale_guard) < loader.index("const content =")

    saver_start = APP.index("async function saveMemoryDocument")
    saver_end = APP.index("function memoryDocumentCanDiscardDraft", saver_start)
    saver = APP[saver_start:saver_end]
    assert "const stateKey = memoryDocumentKey(memoryState.scope, memoryState.projectId)" in saver
    assert "memoryDocumentKey(selectedScope, selectedProjectId) !== stateKey" in saver
    assert saver.count("memoryDocumentRequestMatches") >= 3
    assert "memoryState.requestGeneration" in saver


def test_new_memory_css_is_scoped_to_memory_view() -> None:
    new_selectors = (
        ".memory-workspace",
        ".memory-page-header",
        ".memory-filters",
        ".memory-document-panel",
        ".memory-document-header",
        ".memory-document-meta",
        ".memory-document-field",
        ".memory-document-help",
        ".memory-document-count",
        ".memory-document-actions",
        ".memory-document-empty",
        "#memory-document-editor",
        "#memory-document-conflict",
    )
    for selector in new_selectors:
        assert f"#memory-view {selector}" in STYLES


def test_conflict_refresh_keeps_draft_and_rotates_revision_for_save() -> None:
    assert "memoryDocumentConflictRefreshButton.addEventListener('click', refreshMemoryDocumentKeepingDraft)" in APP
    refresh_start = APP.index("async function refreshMemoryDocumentKeepingDraft")
    refresh_end = APP.index("function renderMemoryDocument", refresh_start)
    refresh = APP[refresh_start:refresh_end]
    assert "const draft = memoryDocumentDraft()" in refresh
    assert "const projectId = scope === 'project' ? memoryState.projectId : null" in refresh
    assert "const params = memoryDocumentQuery(scope, projectId)" in refresh
    assert "memoryDocumentEditor.value = draft" in refresh
    assert "memoryState.content = latestContent" in refresh
    assert "memoryState.revision = typeof data?.revision === 'string'" in refresh
    assert "memoryState.dirty = true" in refresh
    assert refresh.count("memoryDocumentRequestMatches") >= 3
    assert "conversationState.projectId" not in refresh
    catch_start = refresh.index("} catch (error)")
    catch_end = refresh.index("} finally", catch_start)
    assert "memoryState.revision =" not in refresh[catch_start:catch_end]
    assert "memoryDocumentEditor.value =" not in refresh[catch_start:catch_end]

    save_start = APP.index("async function saveMemoryDocument")
    save_end = APP.index("function memoryDocumentCanDiscardDraft", save_start)
    save = APP[save_start:save_end]
    assert "revision: memoryState.revision" in save


def test_memory_navigation_is_keyboard_activatable() -> None:
    assert "item.addEventListener('keydown'" in APP
    assert "event.key !== 'Enter' && event.key !== ' '" in APP
    assert "showView(item.dataset.view);" in APP
