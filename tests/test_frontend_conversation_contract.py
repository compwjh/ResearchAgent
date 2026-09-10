"""Static contracts for the Spec022 desktop conversation memory MVP."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_desktop_memory_dom_contract_is_present() -> None:
    for element_id in (
        "project-select",
        "new-project-button",
        "new-project-form",
        "project-name-input",
        "conversation-list",
        "conversation-status",
        "conversation-memory-status",
        "load-older-messages",
    ):
        assert f'id="{element_id}"' in INDEX


def test_conversation_api_and_stable_url_contract() -> None:
    assert "/api/projects" in APP
    assert "/api/conversations" in APP
    assert "/api/conversations/messages" in APP
    assert "target_chars" in APP
    assert "before" in APP
    assert "/c/" in APP
    assert "history.pushState" in APP
    assert "history.replaceState" in APP


def test_stream_and_switch_cancellation_contract() -> None:
    assert "AbortController" in APP
    assert "streamController.abort()" in APP
    for event_type in ("meta", "progress", "memory", "token", "error", "done"):
        assert f"eventData.type === '{event_type}'" in APP
    assert "createMarkdownWriter" in APP


def test_user_content_uses_safe_dom_boundaries() -> None:
    start = APP.index("function renderConversationMessage")
    end = APP.index("function createConversationProcessing", start)
    renderer = APP[start:end]
    assert "textContent" in renderer
    assert "setConversationAnswer" in renderer
    assert "innerHTML" not in renderer


def test_memory_and_processing_feedback_are_scoped() -> None:
    for css_selector in (
        ".conversation-processing",
        ".conversation-memory-notice",
        ".conversation-list",
        ".project-switcher",
    ):
        assert css_selector in STYLES


def test_static_asset_versions_are_bumped_together() -> None:
    assert "/assets/app.js?v=27" in INDEX
    assert "/assets/styles.css?v=27" in INDEX
