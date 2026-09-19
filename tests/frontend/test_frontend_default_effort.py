"""Spec 026 Task 05 补丁 — 首屏默认档位缺陷修复（静态契约）。

修复：全新页面首次加载且从未手动改过档位时，desired 链中 lastEffort（初值 'off'）
错误压过后端 default_effort，导致首屏选中 off 而非「该模型支持的最高档」。

三条语义（static contract，沿用仓库既有函数体抽取做法）：
1. 首次加载 / 切换模型 / 载入会话，且用户未显式选过 → 选中 default_effort（=支持的最高档），
   不沿用 lastEffort（其初值为 'off' 会在全新页面首次加载时压过低档）。
2. 重新检测能力（refresh）重载 → 保留用户当前选中的档位（lastEffort），由 reconcile 校正越界。
3. 载入已有会话 → 优先用会话保存的 reasoning_effort（调用方经 selectedEffort 传入）。

B11 红线不在本补丁改动范围：change 监听体仍不调用 reconcile（见 task05_selector_states 测试）。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")


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


def test_load_reasoning_options_accepts_source_param() -> None:
    # 区分调用来源：函数签名支持 source 入参
    assert "async function loadReasoningOptions(model, { selectedEffort = null, refresh = false, source = null } = {})" in APP


def test_desired_chain_prefers_default_effort_on_first_load_not_last_effort() -> None:
    body = _function_source("loadReasoningOptions")
    # 首屏（initial）分支：selectedEffort 优先，否则 default_effort（支持最高档）
    assert "selectedEffort || reasoningOptionsState.defaultEffort || 'off'" in body
    # 首屏分支不得沿用“切换前选中的档位”（reasoningOptionsState.lastEffort），
    # 否则其初值 'off' 会在全新页面首次加载时压过低档（Task05 缺陷根因）。
    initial_seg = body[body.index("callSource === 'initial'"):].split("} else {", 1)[0]
    assert "reasoningOptionsState.lastEffort" not in initial_seg
    # 切换模型 / 载入会话（else 分支）必须沿用切换前的选中档位（lastEffort），
    # 交由 reconcile 校正到新模型支持的最高档并弹一次性提示（B9 修复：静默降档）。
    assert "selectedEffort || reasoningOptionsState.lastEffort || reasoningOptionsState.defaultEffort || 'off'" in body
    # 用来源标识区分三类路径
    assert "callSource === 'refresh'" in body
    assert "callSource === 'initial'" in body


def test_refresh_keeps_current_selection_via_last_effort() -> None:
    body = _function_source("loadReasoningOptions")
    # 重新检测路径保留用户当前选中档位（lastEffort 优先于 defaultEffort）
    assert "selectedEffort || reasoningOptionsState.lastEffort" in body


def test_session_load_uses_saved_reasoning_effort_first() -> None:
    body = _function_source("loadReasoningOptions")
    # 两个分支都优先 selectedEffort（载入会话时由调用方传入会话保存档）
    assert "selectedEffort || reasoningOptionsState.lastEffort" in body
    assert "selectedEffort || reasoningOptionsState.defaultEffort" in body


def test_recheck_derives_refresh_source_without_explicit_source() -> None:
    # appendRecheckButton / 错误动作重检只传 refresh:true，callSource 须推断为 'refresh'
    body = _function_source("loadReasoningOptions")
    assert "source || (refresh ? 'refresh' : 'initial')" in body


def test_callers_tag_their_source() -> None:
    # 首次加载（引导）、切换模型、载入会话分别标注来源，保留旧契约的 refresh:true 重检串
    assert "loadReasoningOptions(activeModel, { source: 'initial' })" in APP
    assert "loadReasoningOptions(activeModel, { source: 'model-switch' })" in APP
    assert "loadReasoningOptions(activeModel, { selectedEffort: conversationState.conversation?.reasoning_effort || null, source: 'session' })" in APP
    assert "loadReasoningOptions(activeModel, { refresh: true })" in APP


def test_live_asset_version_bumped_for_app_js_and_history_markers_kept() -> None:
    import re
    match = re.search(r'src="/assets/app.js\?v=(\d+)"', INDEX)
    assert match, "missing live app.js asset tag"
    assert int(match.group(1)) >= 39
    # 历史合同（spec024）仍要求 v=35 标记存在
    assert "/assets/app.js?v=35" in INDEX
    assert "/assets/styles.css?v=35" in INDEX
