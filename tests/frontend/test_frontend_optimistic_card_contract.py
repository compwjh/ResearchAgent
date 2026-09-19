"""Spec 026 Task 04 — 前端乐观建卡、失败终态与错误文案分流（静态契约）。

覆盖 spec 026 §前端错误文案映射、边界 B5/B6/B7/B8/B15 与 Task 04 验收点：

- B5：`createAssistantMessage` 必须在 ``await fetch`` **之前**调用，卡内先挂「模型正在准备…」占位；
- B6：``meta`` 分支**不得**再建第二张卡，只填充既有卡片并清掉占位；
- B7：流失败时卡片就地转错误态（``renderConversationFailure``），不移除、不回填输入框；
- B8：409 文案含不支持档位名 + 支持档位列表，且**不出现**「连接失败」；
- B15：「重新检测能力」只带 ``refresh=1`` 重探能力，**不得**重发消息；
- 硬约束：五类错误文案中只有「真网络错误」一类允许出现「连接失败」字样。

`frontend/app.js` 是浏览器脚本、无模块导出，因此本文件沿用仓库既有做法
（``test_frontend_reasoning_panel_contract.py`` / ``test_frontend_conversation_contract.py``）
做静态源码契约断言，并按函数名抽取函数体以避免跨函数误匹配。
"""

import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")

MAPPED_CODES = (
    "REASONING_EFFORT_UNSUPPORTED",
    "MODEL_CAPABILITIES_UNAVAILABLE",
    "INVALID_REASONING_EFFORT",
    "MODEL_UNAVAILABLE",
)


def _function_source(name: str) -> str:
    """Return the source of ``function <name>(...) { ... }`` with balanced braces.

    参数表可能含解构默认值（``{ appendUser = true }``），因此必须先配对跳过
    ``(...)`` 再定位函数体起始的 ``{``。
    """
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


# --- 缺陷 B：错误文案按 code 分流 -------------------------------------------------


def test_error_text_for_covers_the_four_backend_codes() -> None:
    source = _function_source("errorTextFor")
    for code in MAPPED_CODES:
        assert f"'{code}'" in source, code


def _run_node(script_name: str) -> "subprocess.CompletedProcess":
    """Execute one of the Node runtime harnesses under tests/runtime/."""
    node = shutil.which("node")
    assert node, "node executable not found on PATH"
    script = ROOT / "tests" / "runtime" / script_name
    assert script.exists(), f"missing runtime harness {script}"
    return subprocess.run([node, str(script)], capture_output=True, text=True)


# 非网络内部错误：每个调用点必须显式带上 code，且该 code 在 errorTextFor 中映射到中性文案。
# 这里按「错误文案 + 期望 code」枚举（不依赖行号，抗源码位移），旧代码无 code → 断言失败。
INTERNAL_ERRORS = (
    ("本轮已中止", "ABORTED"),
    ("事件流中断：缺少有效事件序号", "STREAM_INTERRUPTED"),
    ("事件流中断", "STREAM_INTERRUPTED"),  # 精确匹配 new Error('事件流中断')，不含冒号后缀
    ("事件流中断：首个 meta 序号无效", "STREAM_INTERRUPTED"),
    ("事件流中断：首个 meta 未被接受", "STREAM_INTERRUPTED"),  # 评审 edge 用例（旧代码无 code，命中兜底）
)


def test_internal_error_call_sites_carry_explicit_code() -> None:
    for message, code in INTERNAL_ERRORS:
        # 只校验「new Error('<文案>'), { code: '<X'」这一前缀，容忍后续追加 retryable 等属性。
        snippet = f"new Error('{message}'), {{ code: '{code}'"
        assert snippet in APP, f"call site for '{message}' must tag Error with code '{code}'"


def test_stream_interrupted_call_sites_are_retryable() -> None:
    # 内部事件流中断错误必须标 retryable:true：连接状态时间线（updateConversationProcessing 的
    # '连接失败' 分支按 !error.retryable 判定）对未标 retryable 的非网络错误会显示「连接失败」字样，
    # 违反 spec §前端错误文案映射「仅真网络错误允许出现网络类字样」硬约束。按调用点文案枚举，
    # 旧代码（无 retryable）下此断言失败。
    for message in (
        "事件流中断：缺少有效事件序号",
        "事件流中断",
        "事件流中断：首个 meta 序号无效",
        "事件流中断：首个 meta 未被接受",
    ):
        snippet = f"new Error('{message}'), {{ code: 'STREAM_INTERRUPTED', retryable: true }}"
        assert snippet in APP, f"STREAM_INTERRUPTED call site for '{message}' must be retryable"


def test_only_the_network_fallback_mentions_connection_failure() -> None:
    source = _function_source("errorTextFor")
    # 1) errorTextFor 内「连接失败」只可能出现在真网络兜底分支。
    assert source.count("连接失败") == 1
    fallback_at = source.index("连接失败")
    for code in MAPPED_CODES:
        assert source.index(f"'{code}'") < fallback_at, code
    # 2) 每个非网络内部 code 在 errorTextFor 中都有独立分支，且分支文案不含「连接失败」。
    for _, code in INTERNAL_ERRORS:
        assert f"if (code === '{code}')" in source, f"errorTextFor missing branch for {code}"
        idx = source.index(f"if (code === '{code}')")
        nxt = source.find("if (code ===", idx + 1)
        nxt = nxt if nxt != -1 else source.index("return { text: `连接失败")
        branch = source[idx:nxt]
        assert "连接失败" not in branch, f"errorTextFor branch '{code}' must not emit 连接失败"


def test_errorTextFor_mapping_runtime_no_connection_failure_for_internal_errors() -> None:
    # 运行时证据：在 Node 中真实执行抽取自 app.js 的 errorTextFor，断言内部错误文案不含
    # 「连接失败」，且只有真网络兜底才含该字样。旧代码下此脚本会失败（见验证记录）。
    result = _run_node("check_error_text_for.mjs")
    assert result.returncode == 0, result.stdout + result.stderr


def test_error_text_for_messages_match_the_spec_table() -> None:
    source = _function_source("errorTextFor")
    assert "该模型不支持" in source
    assert "，可选：" in source
    assert "'无法确认模型能力'" in source
    assert "'推理档位无效'" in source
    assert "'无法连接 Ollama 服务'" in source


def test_unsupported_effort_offers_switch_and_switch_only_actions() -> None:
    source = _function_source("errorTextFor")
    assert "'switch'" in source
    assert "'switchOnly'" in source
    assert "重发" in source
    assert "仅切换不重发" in source


def test_capabilities_unavailable_offers_recheck_only() -> None:
    source = _function_source("errorTextFor")
    recheck_branch = source.index("'MODEL_CAPABILITIES_UNAVAILABLE'")
    invalid_branch = source.index("'INVALID_REASONING_EFFORT'")
    branch = source[recheck_branch:invalid_branch]
    assert "'recheck'" in branch
    assert "'重新检测能力'" in branch
    assert "'retry'" not in branch
    assert "'switch'" not in branch


def test_invalid_reasoning_effort_has_no_action_buttons() -> None:
    source = _function_source("errorTextFor")
    invalid_branch = source.index("'INVALID_REASONING_EFFORT'")
    model_unavailable_branch = source.index("'MODEL_UNAVAILABLE'")
    branch = source[invalid_branch:model_unavailable_branch]
    assert "actions: []" in branch


def test_reasoning_effort_labels_map_all_five_efforts() -> None:
    match = re.search(r"const REASONING_EFFORT_LABELS = \{(.*?)\};", APP, re.S)
    assert match, "missing REASONING_EFFORT_LABELS"
    block = match.group(1)
    for effort, label in (
        ("off", "关闭"),
        ("low", "低"),
        ("medium", "中"),
        ("high", "高"),
        ("xhigh", "极高"),
    ):
        assert f"{effort}: '{label}'" in block, effort


def test_highest_supported_effort_follows_the_canonical_order() -> None:
    assert "const REASONING_EFFORTS = ['off', 'low', 'medium', 'high', 'xhigh']" in APP
    source = _function_source("supportedReasoningEfforts")
    assert "REASONING_EFFORTS.filter" in source
    assert "supported.includes(effort)" in source
    assert "reasoningOptionsState.supported" in source
    highest = _function_source("highestSupportedReasoningEffort")
    assert "supportedReasoningEfforts()" in highest
    assert ".at(-1)" in highest


def test_hardcoded_connection_failure_wording_is_gone() -> None:
    for name in ("addConversationError", "addConversationErrorNotice"):
        source = _function_source(name)
        assert "请确认后重新发送" not in source, name
        assert "连接失败" not in source, name


def test_error_renderers_never_build_markup_from_user_input() -> None:
    for name in (
        "errorTextFor",
        "addConversationError",
        "addConversationErrorNotice",
        "renderConversationFailure",
        "setConversationPending",
        "clearConversationPending",
        "attachConversationErrorAction",
        "handleConversationErrorAction",
    ):
        assert "innerHTML" not in _function_source(name), name


# --- 缺陷 A：乐观建卡 -------------------------------------------------------------


def test_assistant_card_is_created_before_the_request_is_sent() -> None:
    body = _function_source("sendConversationMessage")
    create_at = body.index("createAssistantMessage(")
    fetch_at = body.index("await fetch(")
    assert create_at < fetch_at
    assert body.index("setConversationPending(") < fetch_at


def test_meta_fills_the_optimistic_card_without_creating_a_second_one() -> None:
    body = _function_source("sendConversationMessage")
    meta_at = body.index("eventData.type === 'meta'")
    meta_branch_end = body.index("} else if (!acceptConversationEvent(", meta_at)
    meta_branch = body[meta_at:meta_branch_end]
    assert "createAssistantMessage(" not in meta_branch
    assert "clearConversationPending(" in meta_branch
    assert "assistantMessage.dataset.metaSeen = 'true'" in meta_branch


def test_pending_placeholder_text_is_the_spec_wording() -> None:
    source = _function_source("setConversationPending")
    assert "模型正在准备…" in source
    assert "conversation-pending" in source
    cleared = _function_source("clearConversationPending")
    assert "conversation-pending" in cleared


def test_send_guards_against_a_card_when_there_is_nothing_to_send() -> None:
    body = _function_source("sendConversationMessage")
    guard_at = body.index("if (!String(question || '').trim()) return;")
    assert guard_at < body.index("createAssistantMessage(")


# --- 缺陷 A/B：失败终态就地转换 ---------------------------------------------------


def test_failure_keeps_the_card_and_renders_actions_in_place() -> None:
    body = _function_source("sendConversationMessage")
    catch_at = body.index("} catch (error) {")
    tail = body[catch_at:]
    assert "renderConversationFailure(assistantMessage" in tail
    assert "assistantMessage.remove()" not in tail
    assert "input.value = question" not in body
    assert "input.value = text" not in body


def test_failure_renderer_clears_pending_and_marks_the_card() -> None:
    source = _function_source("renderConversationFailure")
    assert "clearConversationPending(message)" in source
    assert "is-failed" in source
    assert "conversation-error-actions" in source
    assert "conversation-error-notice" in source


def test_send_path_propagates_the_backend_error_code() -> None:
    body = _function_source("sendConversationMessage")
    assert "error.code = " in body
    assert "error.status = response.status" in body


# --- B15：按钮语义 ---------------------------------------------------------------


def test_recheck_action_only_refreshes_capabilities() -> None:
    source = _function_source("handleConversationErrorAction")
    recheck_at = source.index("action.kind === 'recheck'")
    switch_at = source.index("action.kind === 'switch'", recheck_at)
    recheck_branch = source[recheck_at:switch_at]
    assert "sendConversationMessage(" not in recheck_branch
    assert "refresh: true" in recheck_branch
    assert "return;" in recheck_branch


def test_switch_only_never_resends() -> None:
    source = _function_source("handleConversationErrorAction")
    switch_only_at = source.index("action.kind === 'switchOnly'")
    resend_at = source.index("sendConversationMessage(")
    assert switch_only_at < resend_at
    switch_branch = source[source.index("action.kind === 'switch'", source.index("action.kind === 'recheck'")):switch_only_at]
    assert "sendConversationMessage(" not in switch_branch


def test_retry_and_switch_resend_without_duplicating_the_user_bubble() -> None:
    source = _function_source("handleConversationErrorAction")
    assert "sendConversationMessage(context.question, { appendUser: false" in source


def test_reasoning_options_supports_forced_refresh() -> None:
    source = _function_source("loadReasoningOptions")
    assert "refresh = false" in source
    assert "refresh=1" in source


# --- 三项自查 ---------------------------------------------------------------------


def test_new_dom_contract_classes_exist_in_stylesheet() -> None:
    for selector in (
        ".conversation-pending",
        ".conversation-error-card",
        ".conversation-error-actions",
        ".conversation-error-action",
    ):
        assert selector in STYLES, selector


def test_live_asset_versions_are_bumped_and_history_markers_kept() -> None:
    assert _live_asset_version("app.js") >= 36
    assert _live_asset_version("styles.css") >= 36
    # 历史合同（spec024）仍要求这两个字符串出现在 index.html 中。
    assert "/assets/app.js?v=35" in INDEX
    assert "/assets/styles.css?v=35" in INDEX


# --- 缺陷 C（P1-1）：loading 窗口内不得发出未确认支持的档位 ----------------------------


def test_no_hardcoded_selected_effort_in_index_html() -> None:
    # index.html 不得预选未确认档位（spec024 已保证五个 option 都在），否则首屏/切模型
    # loading 期间发送会直接发出 xhigh → 后端 409（缺陷 C 残留）。
    assert 'value="xhigh" selected' not in INDEX
    assert 'reasoning-effort-select' in INDEX


def test_send_payload_uses_safe_effort_during_loading() -> None:
    body = _function_source("sendConversationMessage")
    # payload 不再直接读 reasoningEffortSelect?.value，而是经过 pickSendReasoningEffort
    # （loading 期间回落到安全档位 'off'），杜绝窗口内发出未确认档位。
    assert "function pickSendReasoningEffort(loadState, selectValue, lastEffort)" in APP
    assert "pickSendReasoningEffort(reasoningOptionsState.loadState, reasoningEffortSelect?.value, reasoningOptionsState.lastEffort)" in body
    # 直接把 select 值拼进 reasoning_effort 的旧写法必须消失。
    assert "normalizeReasoningEffort(reasoningEffortSelect?.value || reasoningOptionsState.lastEffort || 'off')" not in body


def test_send_reasoning_effort_runtime_safe_during_loading() -> None:
    # 运行时证据：在 Node 中真实执行 pickSendReasoningEffort，断言 loading 期间恒为 'off'。
    result = _run_node("check_send_effort.mjs")
    assert result.returncode == 0, result.stdout + result.stderr


# --- 缺陷（P1-2）：重发路径必须绑定正确的用户气泡，不得把新 messageId 写旧气泡 ---------


def test_resend_threads_the_correct_user_bubble() -> None:
    # sendConversationMessage 接受 userBubble，appendUser:false 时优先用它而非「最后一个 .message.user」。
    assert "async function sendConversationMessage(question, { appendUser = true, userBubble = null } = {})" in APP
    body = _function_source("sendConversationMessage")
    assert "userBubble || [...messages.querySelectorAll('.message.user')].at(-1)" in body
    # 失败渲染把当前用户气泡一并存入 context，供重发定位，保证气泡↔messageId 一一对应。
    assert "renderConversationFailure(assistantMessage, error, { question, userMessage })" in body
    # messageId 仍写到解析出的 userMessage（透传后即为正确气泡）。
    assert "if (userMessageId) userMessage.dataset.messageId = userMessageId;" in body
    # 重发按钮必须把卡片对应的用户气泡透传进去（而非重新取最后一个气泡）。
    hcea = _function_source("handleConversationErrorAction")
    assert "sendConversationMessage(context.question, { appendUser: false, userBubble: context.userMessage })" in hcea
