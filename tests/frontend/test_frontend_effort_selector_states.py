"""Spec 026 Task 05 — 前端档位选择器四态与选中值校正（静态契约）。

覆盖 spec 026 §数据模型（前端 reasoningOptionsState 增量）、边界 B9–B14、B11：

- 四态：loadState ∈ {loading, known, stale, unknown}，按 data.source 映射；
  失败分支不得编造 supported=['off']，改为 supported=null / loadState='unknown'（B12）。
- B12 unknown：除 off 外全禁用 + 「能力未确认」+「重新检测」。
- B13 stale：按旧 supported 禁用 + 「沿用 X 前的能力检测结果」+「重新检测」。
- B14 loading：整体禁用 + 「检测能力中…」。
- B9/B10 校正：loadReasoningOptions 成功且非用户显式触发时，选中档不在 supported 内
  → 改为最高支持档并触发一次性提示「已因模型能力从『X』调整为『Y』」。
- B11 红线：reasoningEffortSelect 的 change 事件（用户显式选择）路径不得被校正。

frontend/app.js 是浏览器脚本、无模块导出，沿用仓库既有做法做静态源码契约断言，
按函数名抽取函数体以避免跨函数误匹配。
"""

import re
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


def _live_asset_version(asset_name: str) -> int:
    match = re.search(rf'(?:href|src)="/assets/{re.escape(asset_name)}\?v=(\d+)"', INDEX)
    assert match, f"missing live asset tag for {asset_name}"
    return int(match.group(1))


# --- 四态：state 增量 -------------------------------------------------------------


def test_load_state_and_stale_cached_at_declared() -> None:
    assert "loadState" in APP
    assert "staleCachedAt" in APP


def test_load_reasoning_options_maps_source_to_load_state() -> None:
    body = _function_source("loadReasoningOptions")
    # 成功分支按 data.source 驱动 loadState 三态：
    # stale→stale、unknown→unknown、其余（ollama_probe/cache）→known
    assert "data?.source" in body
    assert "loadState = 'known'" in body
    assert "loadState = 'stale'" in body
    assert "loadState = 'unknown'" in body
    # stale 保留旧 cached_at
    assert "staleCachedAt" in body


# --- B12/B13/B14：四态渲染 --------------------------------------------------------


def test_failure_branch_no_longer_fabricates_off_only() -> None:
    body = _function_source("loadReasoningOptions")
    assert "reasoningOptionsState.supported = ['off']" not in body, "fabrication must be removed (B12)"
    assert "reasoningOptionsState.supported = null" in body
    assert "reasoningOptionsState.loadState = 'unknown'" in body
    # 安全默认仍保留（不会把 unknown 伪装成只支持关闭）
    assert "reasoningOptionsState.defaultEffort = 'off'" in body


def test_sync_options_handles_four_states() -> None:
    body = _function_source("syncReasoningEffortOptions")
    assert "loadState" in body
    # unknown 时仅 off 可用（对禁用项给出“能力未确认”提示，而非“该模型不支持”）
    assert "能力未确认" in body or "loadState === 'unknown'" in body


def test_render_reasoning_effort_state_texts() -> None:
    body = _function_source("renderReasoningEffortState")
    assert "检测能力中" in body          # B14 loading
    assert "能力未确认" in body          # B12 unknown
    assert "沿用" in body and "前的能力检测结果" in body  # B13 stale
    # 重新检测按钮由 appendRecheckButton 注入（B12/B13/B15：只重探能力，不重发）
    recheck = _function_source("appendRecheckButton")
    assert "重新检测" in recheck
    assert "loadReasoningOptions(activeModel, { refresh: true })" in recheck
    assert "sendConversationMessage(" not in recheck


def test_loading_disables_the_whole_selector() -> None:
    body = _function_source("syncReasoningEffortOptions")
    # loading 态下每个 option 都被禁用
    assert "loadState === 'loading'" in body


def test_recheck_button_only_refreshes_capabilities() -> None:
    body = _function_source("appendRecheckButton")
    assert "loadReasoningOptions(activeModel, { refresh: true })" in body
    assert "sendConversationMessage(" not in body  # B15：不重发


# --- B9/B10 校正 + B11 红线 --------------------------------------------------------


def test_reconcile_corrects_unsupported_but_respects_user_explicit() -> None:
    body = _function_source("reconcileEffortWithCapabilities")
    # B11：用户显式选择（reason==='user'）一律不改档
    assert "reason === 'user'" in body
    # unknown 态不校正（交后端 409）
    assert "loadState === 'unknown'" in body
    # 校正落到最高支持档
    assert "highestSupportedReasoningEffort()" in body
    # 校正时触发一次性提示（文案在 showEffortCorrectionNotice 中）
    assert "showEffortCorrectionNotice(" in body
    notice = _function_source("showEffortCorrectionNotice")
    assert "已因模型能力从" in notice
    assert "调整为" in notice


def test_change_handler_does_not_invoke_reconcile() -> None:
    # change 监听体只做 setReasoningEffort + persist，不调 reconcile（守住 B11）
    start = APP.index("reasoningEffortSelect?.addEventListener('change'")
    end = APP.index("function conversationError(", start)
    handler = APP[start:end]
    assert "reconcileEffortWithCapabilities" not in handler
    assert "setReasoningEffort(" in handler


# --- B11 红线：去掉 xhigh 硬编码兜底 ----------------------------------------------


def test_normalize_reasoning_effort_defaults_to_off_not_xhigh() -> None:
    assert "function normalizeReasoningEffort(value, fallback = 'off')" in APP


def test_set_reasoning_effort_no_xhigh_hardcode() -> None:
    assert "reasoningOptionsState.defaultEffort || 'xhigh'" not in APP


def test_default_effort_uses_backend_value_then_highest_then_off() -> None:
    body = _function_source("loadReasoningOptions")
    # 成功分支：default_effort 取后端值；为空则最高档；再空回落 off
    assert "highestSupportedReasoningEffort()" in body


# --- 三项自查 ---------------------------------------------------------------------


def test_new_dom_contract_classes_exist_in_stylesheet() -> None:
    for selector in (
        ".reasoning-effort-state",
        ".reasoning-effort-recheck",
        ".reasoning-effort-notice",
    ):
        assert selector in STYLES, selector


def test_new_dom_elements_present_in_index() -> None:
    assert 'id="reasoning-effort-state"' in INDEX
    assert 'id="reasoning-effort-notice"' in INDEX


def test_live_asset_versions_bumped_and_history_markers_kept() -> None:
    assert _live_asset_version("app.js") >= 37
    assert _live_asset_version("styles.css") >= 37
    # 历史合同（spec024）仍要求这两个字符串出现在 index.html 中。
    assert "/assets/app.js?v=35" in INDEX
    assert "/assets/styles.css?v=35" in INDEX
