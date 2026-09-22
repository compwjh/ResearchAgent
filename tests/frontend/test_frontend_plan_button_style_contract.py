"""Static contract for compact research-plan decision buttons."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_chat_and_workbench_plan_commands_share_compact_button_metrics() -> None:
    match = re.search(
        r"\.conversation-research-command, \.research-session-command\s*\{([^}]*)\}",
        STYLES,
    )
    assert match, "both research-plan button classes must have one shared rule"
    declarations = match.group(1)
    assert "min-height: 28px" in declarations
    assert "padding: 5px 8px" in declarations
    assert "font: 10px/1.35 'DM Mono', monospace" in declarations
