"""Static contracts for the Spec022 desktop conversation memory MVP."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_desktop_memory_dom_contract_is_present() -> None:
    for element_id in (
        "new-project-button",
        "project-tree-toggle",
        "project-list",
        "project-dialog",
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
        ".project-tree",
    ):
        assert css_selector in STYLES


def test_static_asset_versions_are_bumped_together() -> None:
    assert "/assets/app.js?v=31" in INDEX
    assert "/assets/styles.css?v=30" in INDEX
    assert "/assets/conversation-research.js?v=1" in INDEX


def test_rag_sources_are_deferred_and_capped() -> None:
    renderer = (ROOT / "frontend/conversation-research.js").read_text(encoding="utf-8")
    assert "eventData.type === 'sources'" in APP
    assert "generationCompleted" in APP
    assert "pendingSources" in APP
    assert "sources || eventData.citations" in APP
    assert "slice(0, MAX_SOURCES)" in renderer


def test_rag_source_details_are_safe_and_use_original_get_route() -> None:
    renderer = (ROOT / "frontend/conversation-research.js").read_text(encoding="utf-8")
    assert "textContent" in renderer
    assert "source_url" in renderer
    assert "SOURCE_ROUTE" in renderer
    assert "kb\\/documents" in renderer
    assert "/source" in renderer
    assert "innerHTML" not in renderer
    assert "aria-expanded" in renderer
    assert "conversation-source-detail" in renderer


def test_processing_statuses_and_reduced_motion_contract() -> None:
    assert "status === 'completed'" in APP
    assert "status === 'failed'" in APP
    assert "'skipped'" in APP
    assert "reconnect" in APP
    assert "prefers-reduced-motion" in STYLES
    assert "conversation-wave" in STYLES


def test_legacy_desktop_dom_and_markdown_contract_remains() -> None:
    for element_id in ("project-tree-toggle", "conversation-list", "memory-view", "kb-view", "papers-view", "messages"):
        assert f'id="{element_id}"' in INDEX
    assert "createMarkdownWriter" in APP
    assert "DOMPurify" in APP


def test_historical_processing_steps_hydrate_serially_and_safely() -> None:
    assert "/api/messages/${encodeURIComponent(messageId)}/processing-steps" in APP
    assert "hydrateConversationProcessing" in APP
    assert "enqueueConversationProcessingHydration" in APP
    assert "processingHydrationQueue" in APP
    assert "message_id" in APP
    assert "处理过程暂不可用" in APP
    assert "conversation-processing-degraded" in APP
    assert "textContent" in APP


def test_historical_hydrate_does_not_block_new_conversation_loads() -> None:
    assert "loadingConversationId" in APP
    assert "messageLoadToken" in APP
    assert "conversationState.messageLoadToken === loadToken" in APP
    assert "messageElement.dataset.messageId !== messageId" in APP
    assert "conversationState.conversationId !== conversationId" in APP
    assert "conversationState.streamGeneration !== loadGeneration" in APP
    assert "if (guard && !guard()) return;" in APP
    assert "消息加载失败" in APP
    load_start = APP.index("async function loadConversationMessages")
    load_end = APP.index("async function loadOlderConversationMessages", load_start)
    assert "enqueueConversationProcessingHydration" in APP[load_start:load_end]
    assert "await hydrateConversationProcessing" not in APP[load_start:load_end]
    queue_start = APP.index("function enqueueConversationProcessingHydration")
    queue_end = APP.index("function createConversationSources", queue_start)
    assert "processingHydrationQueue" in APP[queue_start:queue_end]
    assert ".catch(() => {})" in APP[queue_start:queue_end]


def test_open_conversation_guards_delayed_a_b_switch_results() -> None:
    assert "openToken" in APP
    assert "conversationState.openToken === openToken" in APP
    assert "const openGeneration = conversationState.streamGeneration" in APP
    assert "openGeneration" in APP
    assert "isCurrent" in APP
    open_start = APP.index("async function openConversation")
    open_end = APP.index("function beginDraft", open_start)
    open_fn = APP[open_start:open_end]
    assert open_fn.count("if (!isCurrent()) return;") >= 2
    assert "loadConversationList({ append: false, guard: isCurrent })" in open_fn
    assert "if (!isCurrent()) setConversationStatus" not in open_fn
    catch_fn = open_fn[open_fn.index("} catch (error)") :]
    assert "if (!isCurrent()) return;" in catch_fn


def test_stream_eof_without_done_is_interrupted_but_abort_is_silent() -> None:
    assert "doneReceived" in APP
    assert "!doneReceived" in APP
    assert "controller.signal.aborted" in APP
    assert "is-interrupted" in APP
    assert "流式连接中断" in APP
    assert "pendingSources = null" in APP


def test_reconnect_closes_as_degraded_status() -> None:
    assert "status: 'skipped'" in APP
    assert "连接中断，可重试" in APP
    assert "stopConversationProcessing" in APP
    assert "data-status=\"running\"" in STYLES or "data-status=\"skipped\"" in STYLES


def test_spec034_intake_events_use_the_existing_assistant_message_stream() -> None:
    assert "'skill_activation'" in APP
    assert "'intake'" in APP
    assert "eventData.type === 'skill_activation'" in APP
    assert "eventData.type === 'intake'" in APP
    assert "createConversationIntake" in APP
    assert "updateConversationIntake" in APP
    assert "conversation-intake" in STYLES
    assert "historicalIntake" in APP
    assert "content_hash" in APP
    assert "skill.version" in APP


def test_spec034_intake_summary_is_safe_and_contains_the_product_contract() -> None:
    start = APP.index("function createConversationIntake")
    end = APP.index("function updateConversationProcessing", start)
    renderer = APP[start:end]
    assert "createElement" in renderer
    assert "textContent" in renderer
    assert "value_json" in renderer
    assert "source" in renderer
    assert "confidence" in renderer
    assert "confirmation_status" in renderer
    assert "missing" in renderer
    assert "handleConversationIntakeChoice" in APP
    assert "conversation-intake-choice-status" in APP
    assert "cancel_research" in renderer
    for choice in ("modify_current", "cancel_then_new", "new_conversation"):
        assert choice in APP
    assert "innerHTML" not in renderer
    assert "prompt" not in renderer.lower()


def test_spec034_intake_terminal_state_is_collapsible_and_assets_are_bumped() -> None:
    assert "conversation-intake-toggle" in APP
    assert "conversation-intake-body" in APP
    assert "collapseConversationIntake" in APP
    assert "data-status=\"failed\"" in STYLES
    assert "/assets/app.js?v=53" in INDEX
    assert "/assets/styles.css?v=53" in INDEX


def test_spec034_pending_intake_stays_reachable_after_completed_sse_turn() -> None:
    start = APP.index("function finalizeConversationIntake")
    end = APP.index("function updateConversationProcessing", start)
    finalize = APP[start:end]
    assert "clarification" in finalize
    assert "active_conflict" in finalize
    assert "conversation-intake-missing" in finalize
    assert "conversation-intake-choice" in finalize
    assert "needsUserAction" in finalize
    assert "!needsUserAction" in finalize


def test_spec034_historical_intake_uses_the_same_terminal_collapse_rule() -> None:
    start = APP.index("function renderConversationMessage")
    end = APP.index("function createConversationProcessing", start)
    renderer = APP[start:end]
    assert "historicalIntake" in renderer
    assert "updateConversationIntake" in renderer
    assert "finalizeConversationIntake" in renderer
    assert "item.status === 'failed'" in renderer
