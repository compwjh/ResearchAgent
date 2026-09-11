"""spec-025 Task05 — 输入框上下文占比与手动压缩按钮前端契约。

静态契约，避免浏览器依赖：保护 composer 区域的 DOM 边界、资源版本号同步、
CSS 作用域、动态文本只用 textContent、按钮 in-flight 保护与刷新时机。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_context_meter_dom_ids_exist() -> None:
    for element_id in {
        "context-meter",
        "context-progress",
        "context-progress-fill",
        "context-meter-text",
        "context-compact-button",
        "context-status",
    }:
        assert f'id="{element_id}"' in INDEX


def test_context_meter_classes_are_styled() -> None:
    for class_name in {
        "composer-context",
        "context-progress",
        "context-progress-fill",
        "context-meter-text",
        "context-compact-button",
        "context-status",
    }:
        assert f".{class_name}" in STYLES


def test_asset_version_bumped_for_spec025() -> None:
    assert "/assets/app.js?v=34" in INDEX
    assert "/assets/styles.css?v=34" in INDEX


def test_context_meter_inside_composer_form() -> None:
    start = INDEX.index('class="composer" id="chat-form"')
    end = INDEX.index("</form>", start)
    block = INDEX[start:end]
    assert 'id="context-meter"' in block
    assert 'id="context-compact-button"' in block
    assert 'id="context-status"' in block


def test_progressbar_has_accessible_attributes() -> None:
    start = INDEX.index('id="context-progress"')
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
    assert "contextMeterText.textContent" in block
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
