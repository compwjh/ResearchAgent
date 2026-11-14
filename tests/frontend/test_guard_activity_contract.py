"""Spec050 Task04 防护活动界面静态契约（纯源码，无浏览器）。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
JS = (FRONTEND / "guard-activity.js").read_text(encoding="utf-8")
CSS = (FRONTEND / "guard-activity.css").read_text(encoding="utf-8")
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")


def test_assets_mounted_once_after_app_js():
    assert 'href="/assets/guard-activity.css?v=2"' in INDEX
    assert 'src="/assets/guard-activity.js?v=2"' in INDEX
    assert INDEX.count('guard-activity.js?v=2') == 1
    assert INDEX.index('src="/assets/app.js?v=77"') < INDEX.index('src="/assets/guard-activity.js?v=2"')


def test_no_innerhtml_on_server_text():
    # 只禁止实际赋值/调用；注释里说明「不做 innerHTML 拼接」是允许的。
    assert not re.search(r"\.innerHTML\s*=|innerHTML\s*\(", JS)
    assert "document.write" not in JS
    assert "textContent" in JS


def test_all_server_text_escaped_via_textcontent():
    # 服务端字段只允许经过 safeText / el() 写入 DOM。
    for field in ("target_summary", "tool_name", "reason_code", "module", "event_id"):
        assert field in JS
    assert "el(" in JS and "safeText" in JS


def test_three_decisions_with_args_hash_binding():
    for choice in ("allow", "reject", "cancel"):
        assert f"'{choice}'" in JS
    assert "args_hash" in JS
    assert "DECISION_URL + encodeURIComponent(ref)" in JS


def test_refresh_recovery_reads_server_state():
    # 刷新恢复 = 重新从服务端拉取，不依赖内存中的动作状态。
    assert "refreshAll" in JS
    assert "fetchJson(ACTIONS_URL)" in JS
    assert "fetchJson(EVENTS_URL)" in JS
    assert "renderActions" in JS and "renderEvents" in JS


def test_event_deduplication_and_terminal_state_safety():
    # 批内去重；刷新后必须从服务端重建，不得因本地缓存丢失事件历史。
    assert "batchIds" in JS
    assert "if (batchIds[id]) return;" in JS
    assert "seenEventIds" not in JS
    assert "data-event-status" in JS


def test_unknown_status_and_reason_degrade_safely():
    assert "未知状态" in JS or "'未知状态'" in JS
    assert "未知原因" in JS
    assert "网络异常，请刷新后重试" in JS


def test_poll_is_bounded_and_interval_registered():
    assert "POLL_MS = 5000" in JS
    assert "setInterval" in JS
    assert "clearInterval" in JS


def test_css_scoped_to_root_only():
    selectors = [line.strip() for line in CSS.splitlines() if line.strip().startswith("#guard-activity-root")]
    assert selectors
    offenders = [
        line for line in CSS.splitlines()
        if re.match(r"^\.(guard|btn|secondary-button)", line.strip())
    ]
    assert offenders == []
    assert "#guard-activity-root .guard-activity-toggle" in CSS


def test_touch_targets_meet_minimum():
    toggle = re.search(r"\.guard-activity-toggle \{([^}]+)\}", CSS, re.S)
    buttons = re.search(r"\.guard-action-controls button \{([^}]+)\}", CSS, re.S)
    assert toggle and "min-height: 40px" in toggle.group(1)
    assert buttons and "min-height: 36px" in buttons.group(1)


def test_narrow_screen_rule_present():
    assert "@media (max-width: 600px)" in CSS


def test_guard_status_probe_and_stream_endpoint():
    # mount 先探测 /status，enabled 时才接实时流；端点与三态判断必须落盘。
    assert "'/api/guard/status'" in JS
    assert "'/api/guard/stream'" in JS
    assert "fetchJson(STATUS_URL)" in JS
    assert "enabled === true" in JS
    assert "enabled === false" in JS


def test_eventsource_subscription_and_guarded_fallback():
    # 只在 enabled 且浏览器提供 EventSource 时订阅 'guard'；无 EventSource 安全跳过、onerror 保留轮询回退。
    assert "EventSource" in JS
    assert "typeof ES !== 'function'" in JS
    assert "addEventListener('guard'" in JS
    assert "activeStream.close()" in JS
    assert "onerror" in JS
    assert "startPolling()" in JS


def test_stream_dedup_uses_scoped_collection():
    # SSE 去重集合用新名并随 resetForTests 清理；不得复用会丢刷新历史的全局 seenEventIds。
    assert "streamEventIds" in JS
    assert "streamEventIds = Object.create(null)" in JS
    assert "seenEventIds" not in JS
    assert "appendStreamEvent" in JS


def test_toast_and_disabled_state_present():
    assert "guard-activity-toast" in JS
    assert "#guard-activity-root .guard-activity-toast" in CSS
    assert "执行防护未启用" in JS
    assert "guard-activity-disabled" in JS
    assert "#guard-activity-root .guard-activity-disabled" in CSS
