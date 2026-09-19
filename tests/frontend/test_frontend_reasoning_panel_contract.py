"""Static contracts for the Spec024 visible reasoning controls."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    """Return the source of ``function <name>(...) { ... }`` with balanced braces."""
    start = APP.index(f"function {name}(")
    position = APP.index("(", start)
    depth = 0
    while position < len(APP):
        char = APP[position]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                break
        position += 1
    opening = APP.index("{", position)
    depth = 0
    for cursor in range(opening, len(APP)):
        char = APP[cursor]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return APP[start : cursor + 1]
    raise AssertionError(f"unbalanced braces while extracting {name}")


def test_reasoning_effort_picker_has_all_five_values_and_version_bump() -> None:
    assert 'id="reasoning-effort-select"' in INDEX
    for effort in ("off", "low", "medium", "high", "xhigh"):
        assert f'value="{effort}"' in INDEX
    assert "/assets/app.js?v=35" in INDEX
    assert "/assets/styles.css?v=35" in INDEX


def test_reasoning_options_and_session_patch_contract() -> None:
    assert "/api/chat/reasoning-options?model=" in APP
    assert "/api/conversations/${encodeURIComponent(conversationId)}/reasoning" in APP
    assert "reasoning_effort" in APP
    assert "selectedEffort" in APP


def test_reasoning_panel_is_separate_and_safe() -> None:
    assert "conversation-reasoning" in APP
    assert "reasoning_delta" in APP
    assert "reasoning_completed" in APP
    assert "document.createTextNode(visible)" in APP
    assert "conversation-reasoning-content" in STYLES
    renderer_start = APP.index("function renderConversationMessage")
    renderer_end = APP.index("function createConversationProcessing", renderer_start)
    assert "createConversationReasoning" in APP[renderer_start:renderer_end]


def test_reasoning_sequence_and_terminal_guards_contract() -> None:
    assert "lastEventSeq" in APP
    assert "acceptConversationEvent" in APP
    assert "sequenceGap" in APP
    assert "markConversationEventTerminal" in APP
    assert "dataset.terminal === 'true'" in APP


def test_reasoning_status_stops_animation_and_off_has_no_panel() -> None:
    assert "normalizeReasoningEffort(effort) === 'off'" in APP
    assert "data-status=\"running\"" in STYLES
    assert "prefers-reduced-motion" in STYLES
    assert "思考完成" in APP
    assert "思考已中止" in APP


def test_historical_reasoning_is_created_after_bubble_mount() -> None:
    renderer = APP[APP.index("function renderConversationMessage"):APP.index("function createConversationProcessing")]
    assert renderer.index("message.append(avatar, bubble)") < renderer.index("createConversationReasoning(message")
    assert "historicalReasoningContent" in renderer


def test_reasoning_filter_covers_wrappers_and_split_chunks() -> None:
    for marker in ("<think>", "</think>", "<analysis>", "</analysis>", "[INST]", "[/INST]", "<|assistant|>", "<|user|>", "<|system|>", "assistant:", "user:", "system:"):
        assert marker in APP
    assert "const reasoningFilters = new WeakMap()" in APP
    assert "let carry = ''" in APP
    assert "hasMarkerPrefix" in APP
    assert "flushConversationReasoningText" in APP


def test_event_gap_failure_and_abort_are_sticky_terminals() -> None:
    assert "assistantMessage.dataset.sequenceGap = 'true'" in APP
    assert "assistantMessage.dataset.terminal = 'true'" in APP
    assert "assistantMessage.dataset.errorSeen = 'true'" in APP
    assert "assistantMessage.dataset.doneSeen = 'true'" in APP
    assert "assistantMessage.dataset.streamActive = 'false'" in APP
    assert "markConversationEventTerminal(activeAssistant, 'interrupted')" in APP
    assert "if (assistantMessage.dataset.doneSeen === 'true') return false" in APP


def test_reasoning_options_failure_marks_unknown_without_faking_support() -> None:
    # spec 026 修订 spec 024：能力探测失败/未知不再编造 supported=['off']，
    # 改为 supported=null + loadState='unknown'（B12：不得伪装成「只支持关闭」）。
    load = _function_source("loadReasoningOptions")
    assert "reasoningOptionsState.supported = ['off']" not in load
    assert "reasoningOptionsState.supported = null" in load
    assert "reasoningOptionsState.loadState = 'unknown'" in load
    assert "reasoningOptionsState.defaultEffort = 'off'" in load
    assert "previousDefaultEffort" in APP
    assert "reasoningOptionsState.defaultEffort = previousDefaultEffort" in APP
