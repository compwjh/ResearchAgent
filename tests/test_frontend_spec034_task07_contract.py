"""Static contracts for Spec034 Task07 shared processing-tree UI."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
TREE = (ROOT / "frontend/processing-tree.js").read_text(encoding="utf-8")
RESEARCH = (ROOT / "frontend/research-tasks.js").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_shared_tree_is_loaded_and_research_tab_reuses_it() -> None:
    assert 'src="/assets/processing-tree.js?v=1"' in INDEX
    assert "ProcessingTree" in APP
    assert "ProcessingTree.createProcessingTree" in RESEARCH
    assert 'id="research-processing-tree"' in INDEX
    assert "processingTreeTaskId" in RESEARCH


def test_tree_contract_covers_adjacency_idempotency_and_legacy_steps() -> None:
    for marker in ("parent_step_id", "node_type", "node_key", "source_event_id", "schema_version", "upsertMany", "aliases"):
        assert marker in TREE
    assert "out-of-order child" in TREE
    assert "terminalBarrier" in TREE
    assert "normalizeStep" in TREE


def test_tree_display_and_error_contract_is_safe_and_accessible() -> None:
    assert "textContent" in TREE
    assert "innerHTML" not in TREE
    for marker in ("aria-expanded", "aria-label", "trace_syncing", "轨迹同步中"):
        assert marker in TREE
    for marker in ("conversation-processing-node", "conversation-processing-node-children", "conversation-processing-syncing", "prefers-reduced-motion"):
        assert marker in STYLES
    assert "localStorage" in TREE


def test_conversation_sse_accepts_non_cursor_processing_frames_without_raw_duplication() -> None:
    assert "processing_step" in APP
    assert "eventData.type !== 'processing_step' && !acceptConversationEvent" in APP
    assert "eventData.step && typeof eventData.step === 'object'" in APP
    assert "TRACE_PROJECTION_FAILED" in APP


def test_research_sse_accepts_processing_step_without_advancing_event_cursor() -> None:
    assert "'processing_step'" in RESEARCH
    assert "if (type === 'processing_step')" in RESEARCH
    assert "applyProcessingStepFrame" in RESEARCH
    assert "const seq = Number(data.event_seq);" in RESEARCH
    assert "The projector appends the terminal processing_step/upsert" in RESEARCH
    timeline_start = RESEARCH.index("function renderTimeline")
    timeline_end = RESEARCH.index("function applyProcessingStepFrame", timeline_start)
    assert ".upsert(" not in RESEARCH[timeline_start:timeline_end], "raw ResearchEvent payloads must not become tree nodes"


def test_assets_are_versioned_and_changes_are_scoped() -> None:
    assert "/assets/app.js?v=46" in INDEX
    assert "/assets/styles.css?v=46" in INDEX
    assert "?v=45" in INDEX  # compatibility marker for prior static contracts


def test_terminal_barrier_and_real_scroll_container_are_explicit() -> None:
    assert "currentTerminal" in TREE
    assert "current.status !== incoming.status" in TREE
    assert "status: current.status" in TREE
    assert "partial" in TREE and "cancelled" in TREE
    assert "research-column-body" in TREE
    assert "scrollHeight <= scroll.clientHeight + scroll.scrollTop + 24" in TREE
    assert "logical_sequence" in TREE
    assert "aria-disabled" in TREE
