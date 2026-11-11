"""Static contracts for the needs_ground_truth metric grey-out (pure CSS).

The grey-out is layered after the base evaluation-card rules and is scoped to
`[data-status="needs_ground_truth"]` on every selector. It must not hide cards,
fade them via opacity/filter, touch the other status colours, change the :root
palette, or require any DOM/JS change.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")

GREY_PREFIX = '#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"]'
STATUS_LIMIT = '[data-status="needs_ground_truth"]'


def _grey_block() -> str:
    """Return the 5 appended grey-out rules, anchored by the unique V1 colour."""
    lines = CSS.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if "#c9cbd3" in line and STATUS_LIMIT in line),
        None,
    )
    assert start is not None, "缺少 V1 灰化卡片规则（#c9cbd3 + needs_ground_truth 状态限定）"
    return "\n".join(lines[start : start + 5])


def _live_versions(asset: str) -> list[int]:
    if asset == "app.js":
        found = re.findall(r'<script src="/assets/app\.js\?v=(\d+)"', INDEX)
    else:
        found = re.findall(r'<link rel="stylesheet" href="/assets/styles\.css\?v=(\d+)"', INDEX)
    assert found, f"missing live asset tag for {asset}"
    return [int(value) for value in found]


def _linearize(channel: int) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def _contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = _relative_luminance(fg), _relative_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# ---- 1. 五条灰化规则与状态限定 -------------------------------------------
def test_five_status_scoped_grey_rules_exist() -> None:
    block = _grey_block()
    assert block.count(STATUS_LIMIT) == 5, "须恰好 5 条规则，每条都带 needs_ground_truth 状态限定"
    assert block.count(GREY_PREFIX) == 5, "每条选择器都以评测卡片状态限定开头"
    for line in block.splitlines():
        assert line.strip().startswith(GREY_PREFIX), f"灰化规则未带状态限定前缀: {line}"


def test_child_selectors_reuse_existing_classes() -> None:
    block = _grey_block()
    for selector in (
        ".evaluation-metric-status",
        ".evaluation-metric-label",
        ".evaluation-metric-value",
        ".evaluation-metric-params > summary",
    ):
        assert selector in block, f"缺少子选择器 {selector}"


# ---- 2. V1–V6 色值 -------------------------------------------------------
def test_v1_to_v6_grey_colours() -> None:
    block = _grey_block()
    flat = block.replace(" ", "")
    assert "border-left-color:#c9cbd3" in flat, "V1 左边框灰"
    assert "background:#f6f6f8" in flat, "V2 卡片浅灰底"
    assert "background:#e9eaee" in flat, "V3 徽章灰底"
    assert "color:#5f626c" in flat, "V3 徽章文字（§13 裁决达标色值）"
    assert block.count("var(--muted-strong)") == 2, "V4 标题 + V6 summary 用 --muted-strong"
    assert block.count("var(--muted)") == 1, "V5 数值用 --muted"


def test_deprecated_badge_colour_is_absent() -> None:
    assert "#6b6e78" not in _grey_block(), "§3 作废的 #6b6e78（4.2330:1）不得出现在灰化规则中"


def test_grey_block_has_no_hiding_or_fading() -> None:
    flat = _grey_block().lower().replace(" ", "")
    for banned in ("opacity", "grayscale", "filter", "display:none", "visibility:hidden"):
        assert banned not in flat, f"灰化规则不得含 {banned}"


# ---- 3. 三状态 / 四条基础规则逐字仍在 ------------------------------------
def test_base_status_rules_are_unchanged() -> None:
    for rule in (
        '#evaluation-view .evaluation-metric-card[data-status="computed"] { border-left: 4px solid #287c43; }',
        '#evaluation-view .evaluation-metric-card[data-status="degraded"] { border-left: 4px solid #c8871a; background: #fffdf7; }',
        '#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"] { border-left: 4px solid #6d5dfc; background: #faf9ff; }',
        '#evaluation-view .evaluation-metric-card[data-status="unavailable"] { border-left: 4px solid #b13a3a; background: #fff8f8; }',
    ):
        assert rule in CSS, f"基础状态规则被改动: {rule}"


# ---- 4. WCAG 2.x 相对亮度复算 ---------------------------------------------
def test_wcag_aa_contrast_for_badge_and_title() -> None:
    badge = _contrast_ratio("#5f626c", "#e9eaee")
    title = _contrast_ratio("#5a5d66", "#f6f6f8")
    assert badge >= 4.5, f"V3 徽章对比度 {badge:.4f}:1 未达 AA"
    assert title >= 4.5, f"V4 标题对比度 {title:.4f}:1 未达 AA"
    # 锁定到 §13 裁决复算值，防止公式写错却仍「>=4.5」的恒真通过
    assert abs(badge - 5.0630) < 0.02, f"V3 比值偏离裁决 5.0630:1，实得 {badge:.4f}"
    assert abs(title - 6.0947) < 0.02, f"V4 比值偏离裁决 6.0947:1，实得 {title:.4f}"


# ---- 5. 版本契约与纯属性 marker ------------------------------------------
def test_live_asset_versions_and_compat_marker() -> None:
    assert _live_versions("styles.css") == [76], "styles.css 生效版本唯一且为 76"
    assert _live_versions("app.js") == [77], "app.js 未改，仍为 77"
    marker = 'Merge compatibility marker: href="/assets/styles.css?v=75"'
    marker_lines = [line for line in INDEX.splitlines() if marker in line]
    assert len(marker_lines) == 1, "v=75 纯属性兼容 marker 须恰好 1 条"
    line = marker_lines[0]
    assert "<!--" in line and "-->" in line, "marker 须位于 HTML 注释内"
    assert "<link" not in line and "<script" not in line, "marker 不得含 <link/<script 标签字面串"
    assert marker not in INDEX.split("</head>")[0], "marker 不得插入 <head>（避免污染 active_version）"


# ---- 6. app.js DOM 渲染契约零改动 -----------------------------------------
def test_app_js_metric_card_dom_contract_unchanged() -> None:
    assert "card.className = 'evaluation-metric-card'" in APP
    assert "card.dataset.status = String(metric.status" in APP, "needs_ground_truth 状态仍由 dataset.status 渲染"
