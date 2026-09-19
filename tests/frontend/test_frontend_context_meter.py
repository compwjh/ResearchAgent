"""spec-025 Task05 — 输入框上下文占比与手动压缩按钮前端契约。

静态契约，避免浏览器依赖：保护 composer 区域的 DOM 边界、资源版本号同步、
CSS 作用域、动态文本只用 textContent、按钮 in-flight 保护与刷新时机。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_context_meter_dom_ids_exist() -> None:
    for element_id in {
        "context-meter",
        "context-ring",
        "context-ring-fill",
        "context-meter-text",
        "context-compact-button",
        "context-status",
    }:
        assert f'id="{element_id}"' in INDEX


def test_context_meter_classes_are_styled() -> None:
    for class_name in {
        "composer-context",
        "context-ring",
        "context-ring-track",
        "context-ring-fill",
        "context-meter-text",
        "context-compact-button",
        "context-status",
    }:
        assert f".{class_name}" in STYLES


def test_asset_version_bumped_for_spec025() -> None:
    assert "/assets/app.js?v=49" in INDEX
    assert "/assets/styles.css?v=49" in INDEX


def test_context_meter_lives_in_composer_footer_right_side() -> None:
    # 占比区必须与「Enter 发送」提示同排，且位于发送按钮之前（右下）。
    start = INDEX.index('<div class="composer-footer">')
    end = INDEX.index("</form>", start)
    footer = INDEX[start:end]
    assert 'id="context-meter"' in footer
    assert 'class="composer-tip"' in footer
    assert footer.index('class="composer-tip"') < footer.index('id="context-meter"')
    assert footer.index('id="context-meter"') < footer.index('id="send-button"')
    # 状态行移出表单，位于 composer 底部右下
    assert INDEX.index("</form>") < INDEX.index('id="context-status"')


def test_input_is_at_least_three_rows_and_grows() -> None:
    assert 'id="question"' in INDEX
    assert 'rows="3"' in INDEX
    assert ".composer textarea" in STYLES
    assert "min-height: 66px" in STYLES
    assert "max-height: 176px" in STYLES
    assert "autoGrowInput" in APP
    assert "COMPOSER_INPUT_MAX_HEIGHT" in APP


def test_idle_placeholder_keeps_layout_stable() -> None:
    # 无会话时用 visibility 占位，不用 hidden，避免底部行抖动。
    assert "is-idle" in INDEX
    assert ".composer-context.is-idle" in STYLES
    assert "visibility: hidden" in STYLES
    start = APP.index("function renderContextUsage")
    end = APP.index("async function loadContextUsage", start)
    block = APP[start:end]
    assert "classList.toggle('is-idle'" in block
    assert "contextMeter.hidden" not in block


def test_ring_is_svg_circle_not_bar() -> None:
    start = INDEX.index('id="context-ring"')
    end = INDEX.index("</div>", start)
    block = INDEX[start:end]
    assert "<svg" in block
    assert "context-ring-track" in block
    assert "context-ring-fill" in block
    assert 'aria-hidden="true"' in block
    # 旧的进度条实现不得残留
    assert "context-progress" not in INDEX
    assert "context-progress-fill" not in INDEX


def test_ring_dash_offset_driven_by_ratio() -> None:
    start = APP.index("function renderContextUsage")
    end = APP.index("async function loadContextUsage", start)
    block = APP[start:end]
    assert "CONTEXT_RING_CIRCUMFERENCE" in block
    assert "strokeDashoffset" in block
    assert "Math.min(1, Math.max(0, ratio))" in block
    assert "aria-valuenow" in block


def test_context_meter_inside_composer_form() -> None:
    start = INDEX.index('class="composer" id="chat-form"')
    end = INDEX.index("</form>", start)
    block = INDEX[start:end]
    assert 'id="context-meter"' in block
    assert 'id="context-compact-button"' in block


def test_progressbar_has_accessible_attributes() -> None:
    start = INDEX.index('id="context-ring"')
    end = INDEX.index(">", start)
    block = INDEX[start:end]
    assert 'role="progressbar"' in block
    assert 'aria-valuenow' in block
    assert 'aria-valuemin="0"' in block
    assert 'aria-valuemax="100"' in block


def test_status_region_is_live() -> None:
    start = INDEX.index('id="context-status"')
    end = INDEX.index(">", start)
    block = INDEX[start:end]
    assert 'role="status"' in block
    assert 'aria-live="polite"' in block


def test_context_usage_endpoints_used() -> None:
    assert "/context-usage" in APP
    assert "/compactions" in APP
    assert 'method: \'POST\'' in APP or 'method: "POST"' in APP


def test_compact_button_has_inflight_guard() -> None:
    start = APP.index("async function compactConversationContext")
    end = APP.index("if (contextCompactButton) contextCompactButton.addEventListener", start)
    block = APP[start:end]
    assert "contextState.inflight" in block
    assert "contextCompactButton.disabled = true" in block
    assert "finally" in block
    assert "contextCompactButton.disabled = false" in block


def test_no_innerhtml_in_context_meter_code() -> None:
    start = APP.index("/* ---------- Spec025：上下文占比与手动压缩 ----------")
    end = APP.index("function setConversationStatus", start)
    block = APP[start:end]
    assert "innerHTML" not in block
    # 动态文本只允许 textContent
    assert "contextMeterValue.textContent" in block
    assert "contextStatus.textContent" in block


def test_ratio_is_clamped_before_render() -> None:
    start = APP.index("function renderContextUsage")
    end = APP.index("async function loadContextUsage", start)
    block = APP[start:end]
    assert "Math.min(1, Math.max(0, ratio))" in block
    assert "aria-valuenow" in block


def test_refresh_only_on_load_and_after_message() -> None:
    # 只允许「加载会话后」与「每轮消息完成后」两个刷新点，不得常驻轮询。
    calls = [m.start() for m in re.finditer(r"loadContextUsage\(\)", APP)]
    assert len(calls) >= 2
    assert "setInterval" not in APP.split("Spec025：上下文占比与手动压缩")[1][:6000]


def test_no_event_source_or_websocket_added() -> None:
    assert "EventSource" not in APP
    assert "WebSocket" not in APP


def test_context_breakdown_popover_exists() -> None:
    # Spec025 扩展：圆圈 hover/点击弹出的占比明细容器与样式。
    assert 'id="context-breakdown"' in INDEX
    assert ".context-breakdown" in STYLES
    assert ".context-breakdown.is-open" in STYLES


def test_context_breakdown_renders_with_dom_api() -> None:
    # 明细必须纯 DOM 构建（textContent / createElement），禁止 innerHTML。
    start = APP.index("function renderContextBreakdown")
    end = APP.index("function openContextBreakdown", start)
    block = APP[start:end]
    assert "createElement" in block
    assert "textContent" in block
    assert "innerHTML" not in block
