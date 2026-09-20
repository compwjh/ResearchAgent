from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "frontend/index.html").read_text()
APP = (ROOT / "frontend/app.js").read_text()
CSS = (ROOT / "frontend/styles.css").read_text()


def test_mobile_drawer_has_single_shared_sidebar_and_focus_contract():
    assert 'id="mobile-nav-toggle"' in HTML
    assert 'id="mobile-nav-backdrop"' in HTML
    assert 'id="mobile-nav-close"' in HTML
    assert "function openMobileDrawer" in APP
    assert "function closeMobileDrawer" in APP
    assert "restoreFocus" in APP
    assert "mobileDrawerState.open" in APP
    assert "mobileTriggerIsVisible" in APP
    assert ".mobile-nav-backdrop" in CSS
    assert ".sidebar.mobile-nav-open" in CSS


def test_mobile_drawer_reuses_existing_project_and_conversation_handlers():
    assert "mobileSidebar?.addEventListener('click'" in APP
    assert "openConversationFromWorkspace" in APP
    assert "selectProjectContext" in APP
    assert "closeMobileDrawer(true)" in APP
    assert "loadProjects().then" in APP


def test_mobile_retry_and_history_contracts_preserve_existing_api_paths():
    assert "conversation-retry-button" in APP
    assert "setConversationRetryStatus" in APP
    assert "loadConversationMessages(conversationId)" in APP
    assert "loadOlderConversationMessages()" in APP
    # spec-026 Task04 修订：错误卡片内的「重新发送 / 用『Y』重发」改为用户点击触发，
    # 复用 `appendUser: false` 重发同一条问题（不重复插入 user 气泡）。
    # 原断言 `sendConversationMessage(question, { appendUser: false })` 不在 APP 中，
    # 与 spec 026 §前端错误文案映射「快捷操作」列直接冲突，故改为断言新合同。
    assert "sendConversationMessage(question, { appendUser: false })" not in APP
    # 重发复用 appendUser:false + context.question（不重复插入 user 气泡）；Task06 修复 P1-2 时
    # 额外透传 userBubble: context.userMessage 以绑定正确气泡（避免 messageId 写错卡片），
    # 故此处用前缀匹配，保留「重发不复制气泡」合同又容纳 userBubble 参数。
    assert "sendConversationMessage(context.question, { appendUser: false" in APP
    # spec-026 要求错误文案按 error.code 分流，禁止再出现硬编码的「请确认后重新发送」。
    assert "请确认后重新发送" not in APP
    assert "renderConversationFailure(assistantMessage, error, { question" in APP
    assert "conversation-error-notice" in APP
    assert "loadOlderConversationMessages" in APP
    assert "before: conversationState.messageCursor" in APP
    assert "/api/conversations/${encodeURIComponent(conversationId)}/messages?${params}" in APP


def test_mobile_focus_restores_visible_trigger_after_drawer_or_menu_close():
    assert "closeFloatingMenu(true); closeMobileDrawer(true); handler();" in APP
    assert "if (event.target.closest('#new-project-button')) { closeMobileDrawer(false); return; }" in APP
    assert "if (restoreFocus && target?.isConnected) target.focus();" in APP
    assert "dialogState.restoreFocus = mobileTriggerIsVisible() ? mobileNavToggle : newProjectButton" in APP


def test_mobile_touch_safe_area_sources_and_reduced_motion_contracts():
    assert "env(safe-area-inset-bottom" in CSS
    assert "100dvh" in CSS
    assert ".conversation-source-button" in CSS
    assert "min-width: 44px" in CSS
    assert ".project-tree-toggle" in CSS
    assert ".conversation-list-menu-trigger" in CSS
    assert "#new-project-button" in CSS
    assert "max-height: min(42vh" in CSS
    assert "@media (prefers-reduced-motion: reduce)" in CSS
    assert "overflow-x: hidden" in CSS
