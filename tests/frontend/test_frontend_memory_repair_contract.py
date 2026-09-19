"""Static contracts for the Spec022 Task05 frontend remediation round."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_turn_order_uses_parent_relationship_and_stable_pagination() -> None:
    assert "function orderConversationMessages" in APP
    assert "parent_message_id" in APP
    assert "orderConversationMessages(data.messages || [])" in APP
    assert "data-parent-message-id" in APP or "dataset.parentMessageId" in APP


def test_memory_placeholder_is_populated_and_batch_contract_is_aligned() -> None:
    assert "if (!section) {" in APP
    assert "memoryBatchDecision = 'save_suggested'" in APP
    assert "state.failures = Array.isArray(data.failed) ? data.failed : [];" in APP


def test_processing_is_inserted_before_answer_and_terminal_animation_stops() -> None:
    assert "bubble.insertBefore(processing, answer)" in APP
    assert "data-status=\"running\"" in STYLES
    assert "data-status=\"interrupted\"" in STYLES
    assert ".conversation-processing-list[hidden] { display: none !important; }" in STYLES
    assert "stopConversationProcessing(processing" in APP


def test_async_memory_analysis_contract_is_non_blocking_and_paginated() -> None:
    assert "/memory-analysis?" in APP
    assert "limit: '10'" in APP
    assert "/memory-analysis/items/" in APP
    assert "/memory-analysis/decisions" in APP
    assert "startMemoryAnalysisPolling" in APP
    assert "data-memory-decision" in APP
    assert "data-memory-batch-decision" in APP
    assert "save_suggested" in APP
    assert "data.failed" in APP
    assert "data.job || data.analysis" in APP
    assert "conversation-memory-results" in STYLES
    assert "conversation-memory-results-failures" in STYLES
    assert "Live assistant messages and hydrated history both start with an empty" in APP


def test_flat_sidebar_is_keyboard_reachable_and_versioned() -> None:
    for element_id in ("project-list", "project-tree-menu-button", "project-dialog", "project-dialog-form", "conversation-archived-button"):
        assert f'id="{element_id}"' in INDEX
    assert "conversation_project_sort" in APP
    assert "focus-within" in STYLES
    assert "/assets/app.js?v=31" in INDEX
    assert "/assets/styles.css?v=30" in INDEX
    assert ".conversation-actions { display: none" in STYLES
    assert "item.click();" in APP


def test_project_selection_never_moves_an_open_conversation() -> None:
    start = APP.index("function selectProjectContext")
    end = APP.index("async function loadProjectConversations", start)
    selector = APP[start:end]
    assert "moveConversation(" not in selector
    assert "renderProjectList(projectState.items)" in selector
    assert "conversation-item-menu" in APP
    assert "aria-expanded" in APP[APP.index("function renderConversationRow") : APP.index("function renderProjectList")]
    move_start = APP.index("async function moveConversation")
    move_end = APP.index("async function loadConversationList", move_start)
    move_fn = APP[move_start:move_end]
    assert "confirm_move" in move_fn
    assert "include_prior_history" in move_fn


def test_processing_running_state_is_aggregated_from_all_steps() -> None:
    assert "function syncConversationProcessingState" in APP
    assert ".conversation-processing-item[data-status=\"running\"]" in APP
    assert "syncConversationProcessingState(processing)" in APP


def test_all_meta_events_share_the_event_sequence_acceptor() -> None:
    stream_start = APP.index("const handleSse = (chunk) => {")
    stream_end = APP.index("    while (true)", stream_start)
    stream = APP[stream_start:stream_end]
    meta_start = stream.index("if (eventData.type === 'meta')")
    meta_end = stream.index("      } else if", meta_start)
    meta_branch = stream[meta_start:meta_end]
    assert "acceptConversationEvent(assistantMessage, eventData)" in meta_branch
    assert "assistantMessage.dataset.lastEventSeq =" not in meta_branch
    # spec-026 Task04 修订：卡片改为「乐观建卡」（在 await fetch 之前创建），
    # meta 分支只负责填充既有卡片，**不得**再建第二张。
    # 原断言 `assistantMessage = createAssistantMessage` 表达的「卡片在 meta 分支创建」
    # 已被 spec 026 边界 B5/B6 取代，故此处改为断言新合同。
    assert "assistantMessage = createAssistantMessage" not in meta_branch
    assert "createAssistantMessage(" not in meta_branch
    assert "assistantMessage.dataset.metaSeen = 'true'" in meta_branch
    accept_start = APP.index("function acceptConversationEvent")
    accept_end = APP.index("function markConversationEventTerminal", accept_start)
    assert "eventData.type === 'meta' && assistantMessage.dataset.metaSeen === 'true'" in APP[accept_start:accept_end]


def test_invalid_event_sequence_is_interrupted_and_not_accepted() -> None:
    accept_start = APP.index("function acceptConversationEvent")
    accept_end = APP.index("function markConversationEventTerminal", accept_start)
    acceptor = APP[accept_start:accept_end]
    assert "Number.isInteger(seq)" in acceptor
    assert "assistantMessage.dataset.sequenceGap = 'true'" in acceptor
    assert "return false" in acceptor
    assert "if (!Number.isInteger(seq) || seq < 1) return true" not in acceptor


def test_final_event_sequence_gap_remains_interrupted() -> None:
    accept_start = APP.index("function acceptConversationEvent")
    accept_end = APP.index("function markConversationEventTerminal", accept_start)
    acceptor = APP[accept_start:accept_end]
    assert "seq > last + 1" in acceptor
    assert "seq > last + 1 && !finalEnvelope" not in acceptor
    stream_start = APP.index("const handleSse = (chunk) => {")
    stream_end = APP.index("    while (true)", stream_start)
    stream = APP[stream_start:stream_end]
    assert "assistantMessage?.dataset.sequenceGap === 'true'" in stream
    assert "doneStatus =" in stream


def test_memory_and_sidebar_renderers_use_safe_text_boundaries() -> None:
    start = APP.index("function renderMemoryAnalysisResult")
    end = APP.index("async function decideMemoryAnalysisItem", start)
    assert "textContent" in APP[start:end]
    assert "innerHTML" not in APP[start:end]
    start = APP.index("function renderProjectList")
    end = APP.index("function selectProjectContext", start)
    assert "textContent" in APP[start:end]
    assert "innerHTML" not in APP[start:end]
