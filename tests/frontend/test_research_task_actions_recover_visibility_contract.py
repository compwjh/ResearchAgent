"""Static contract for the Spec028 "检查并恢复" (recover) button visibility.

`tests/e2e/test_research_lifecycle_e2e.py` can only observe the ``running``
state, where it asserts ``#research-task-recover-button`` is hidden. E2E cannot
cheaply construct an interrupted task, so this contract locks the *full* state
semantics that back that assertion:

- Product spec: ``docs/sdd/specs/028-research-task-durable-scheduling.md:67``
  「任务处于 ``interrupted`` 或 ``recovery_required`` 时点击"检查并恢复"」；
  ``:34`` recover 在「有有效 owner」时返回 409（running 不应提供恢复入口）。
- Implementation: ``frontend/research-tasks.js`` ``TASK_ACTION_STATUSES.recover``
  and ``renderTaskActionControls`` (``button.hidden = !available``).

Keeping this as a source-level contract prevents the E2E assertion from being
silently "fixed" back to visible, and fails loudly if the allowlist is widened
(e.g. to include ``running``) or the button is hard-coded visible.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = (ROOT / "frontend/research-tasks.js").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")

RECOVER_STATES = frozenset({"interrupted", "recovery_required"})


def _action_statuses(source: str) -> dict:
    """Parse the ``TASK_ACTION_STATUSES`` literal into a plain dict of sets."""
    block = re.search(
        r"const TASK_ACTION_STATUSES\s*=\s*Object\.freeze\(\{(.*?)\}\);",
        source,
        re.S,
    )
    assert block, "TASK_ACTION_STATUSES literal must exist in research-tasks.js"
    result = {}
    for key, values in re.findall(
        r"(\w+):\s*new Set\(\[([^\]]*)\]\)", block.group(1)
    ):
        result[key] = {
            value.strip().strip("'\"") for value in values.split(",") if value.strip()
        }
    return result


def test_recover_allowlist_is_exactly_interrupted_states() -> None:
    statuses = _action_statuses(RESEARCH)
    # Fails loudly (not silently) if the allowlist is removed or widened.
    assert statuses.get("recover") == RECOVER_STATES, (
        "recover 只能在 interrupted / recovery_required 显示；"
        f"实际为 {statuses.get('recover')!r}"
    )
    assert "running" in statuses["pause"], "running 必须是 pause 的可用状态"
    assert "running" not in statuses["recover"], "running 绝不能出现 recover 按钮"


def test_recover_visibility_is_driven_by_action_statuses_and_defaults_hidden() -> None:
    # 显隐必须由状态白名单驱动，而不是把 recover 按钮硬编码为可见。
    assert re.search(
        r"const available\s*=\s*Boolean\(taskId\)\s*&&\s*"
        r"TASK_ACTION_STATUSES\[action\]\.has\(status\)",
        RESEARCH,
    ), "按钮显隐必须查 TASK_ACTION_STATUSES[action].has(status)"
    assert "button.hidden = !available;" in RESEARCH
    assert re.search(
        r"const visible\s*=\s*status === 'interrupted'\s*\|\|\s*"
        r"status === 'recovery_required'",
        RESEARCH,
    ), "恢复提示条须与按钮使用同一状态语义"
    # DOM 契约：状态未加载前按钮默认 hidden，避免闪现。
    assert re.search(
        r'id="research-task-recover-button"[^>]*\bhidden\b', INDEX
    ), "recover 按钮必须在 index.html 默认 hidden"
