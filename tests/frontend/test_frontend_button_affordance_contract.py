"""Static contracts for the site-wide button affordance + short-text/tooltip pass.

Task C (spec-regression/task-global-button-ux):
  * real, handler-bound buttons must look available (`.btn-outline`), not greyed out;
  * long IDs / hashes / versions show a short form and reveal the full text on hover;
  * asset versions stay frozen (bumped by the closing task, not here).

Pure source contracts: no browser, no DOM, no network.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"

STYLES = (FRONTEND / "styles.css").read_text(encoding="utf-8")
MAPS_CSS = (FRONTEND / "literature-maps.css").read_text(encoding="utf-8")
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
APP = (FRONTEND / "app.js").read_text(encoding="utf-8")
RESEARCH = (FRONTEND / "research-tasks.js").read_text(encoding="utf-8")
MAPS = (FRONTEND / "literature-maps.js").read_text(encoding="utf-8")
CONV = (FRONTEND / "conversation-research.js").read_text(encoding="utf-8")

BUTTON_SOURCES = {
    "index.html": INDEX,
    "app.js": APP,
    "research-tasks.js": RESEARCH,
    "literature-maps.js": MAPS,
}
TEXT_SOURCES = {
    "app.js": APP,
    "research-tasks.js": RESEARCH,
    "literature-maps.js": MAPS,
    "conversation-research.js": CONV,
}

# Independent `secondary-button` token: excludes `.secondary-button` selectors,
# `my-secondary-button`, `secondary-button-foo`; the trailing look-ahead makes
# the decoration idempotent.
TOKEN = re.compile(r"(?<![\w.-])secondary-button(?![\w-])")
UNDECORATED = re.compile(r"(?<![\w.-])secondary-button(?![\w-])(?!\s+btn-outline)")
BASELINE_COUNTS = {
    "index.html": 25,
    "app.js": 29,
    "research-tasks.js": 11,
    "literature-maps.js": 58,
}


def _declarations(css: str, selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css, re.S)
    assert match, f"missing CSS rule for {selector}"
    return match.group(1)


# ---- 1. shared available-state button class --------------------------------
def test_btn_outline_base_rule_uses_white_purple_palette() -> None:
    decl = _declarations(STYLES, ".btn-outline")
    for expected in (
        "background: #fff",
        "1px solid #d8d2ff",
        "color: #4a4560",
        "border-radius: 8px",
        "font-weight: 600",
    ):
        assert expected in decl, f".btn-outline must declare {expected!r}"


def test_btn_outline_has_hover_focus_and_disabled_states() -> None:
    hover = _declarations(STYLES, ".btn-outline:hover")
    focus = _declarations(STYLES, ".btn-outline:focus-visible")
    disabled = _declarations(STYLES, ".btn-outline:disabled")
    assert "background: #f0edff" in hover and "var(--accent)" in hover
    assert "box-shadow: 0 0 0 3px var(--accent-soft)" in focus
    assert "cursor: not-allowed" in disabled and "color: var(--muted)" in disabled


def test_btn_outline_wins_over_secondary_base_by_source_order() -> None:
    base = STYLES.find(".secondary-button { border-radius: 7px")
    outline = STYLES.find(".btn-outline {")
    assert base > 0, "the .secondary-button base rule must still exist"
    assert outline > base, ".btn-outline must come after the base rule to win on equal specificity"


def test_secondary_base_and_primary_send_button_are_untouched() -> None:
    assert ".secondary-button { border-radius: 7px; padding: 9px 12px; background: var(--paper); color: var(--muted); font-size: 12px; }" in STYLES
    assert ".send-button { border-radius: 7px; padding: 9px 12px; background: var(--accent); color: white; font-size: 12px; }" in STYLES


def test_every_real_button_carries_btn_outline() -> None:
    for name, source in BUTTON_SOURCES.items():
        offenders = [m.start() for m in UNDECORATED.finditer(source)]
        assert not offenders, f"{name} still has {len(offenders)} bare secondary-button token(s)"


def test_btn_outline_is_not_applied_twice() -> None:
    for name, source in BUTTON_SOURCES.items():
        assert "secondary-button btn-outline btn-outline" not in source, name


def test_button_count_is_frozen() -> None:
    for name, expected in BASELINE_COUNTS.items():
        actual = len(TOKEN.findall(BUTTON_SOURCES[name]))
        assert actual == expected, f"{name}: {actual} secondary-button tokens, expected {expected}"


# ---- 2. shared short-text CSS -----------------------------------------------
def test_truncate_hash_inline_and_clamp_classes_exist() -> None:
    truncate = _declarations(STYLES, ".truncate")
    for expected in ("min-width: 0", "overflow: hidden", "text-overflow: ellipsis", "white-space: nowrap"):
        assert expected in truncate, f".truncate must declare {expected!r}"
    assert "monospace" in _declarations(STYLES, ".hash-inline")
    assert "-webkit-line-clamp: 3" in _declarations(STYLES, ".clamp-3")


def test_new_css_classes_are_rendered_by_frontend_sources() -> None:
    rendered = "\n".join(TEXT_SOURCES.values()) + INDEX
    for css_class in ("btn-outline", "truncate", "hash-inline", "clamp-3"):
        assert css_class in rendered, f"{css_class} is defined in CSS but never rendered"


def test_map_id_rows_no_longer_expand_with_overflow_wrap() -> None:
    lines = MAPS_CSS.splitlines()
    for marker in (
        ".literature-map-analysis-version",
        ".literature-map-analysis-history-button {",
        ".literature-map-analysis-result-meta,",
        ".literature-map-analysis-citations {",
    ):
        line = next((row for row in lines if marker in row), None)
        assert line is not None, f"missing ID row rule containing {marker}"
        assert "overflow-wrap: anywhere" not in line, f"{marker} must use .truncate instead"


def test_long_summary_and_report_are_not_blanket_truncated() -> None:
    summary = next(row for row in MAPS_CSS.splitlines() if ".literature-map-analysis-summary {" in row)
    assert "white-space: normal" in summary, "long analysis summaries must keep normal wrapping"
    raw = next(row for row in STYLES.splitlines() if ".research-report-raw {" in row)
    assert "max-height: 560px" in raw and "overflow: auto" in raw, "reports keep limited height + inner scroll"


# ---- 3. JS helpers -----------------------------------------------------------
def test_text_helpers_defined_in_every_js_entry() -> None:
    for name, source in TEXT_SOURCES.items():
        assert re.search(r"function\s+formatShortHash\s*\(", source), f"{name}: missing formatShortHash"
        assert re.search(r"function\s+withTooltip\s*\(", source), f"{name}: missing withTooltip"


def test_withtooltip_uses_native_title_and_aria_label_without_innerhtml() -> None:
    for name, source in TEXT_SOURCES.items():
        start = source.index("function withTooltip(")
        brace = source.index("{", start)
        depth = 0
        body = ""
        for i in range(brace, len(source)):
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    body = source[brace:i + 1]
                    break
        assert body, f"{name}: unbalanced withTooltip body"
        assert ".title" in body, f"{name}: withTooltip must set el.title"
        assert "aria-label" in body, f"{name}: withTooltip must set aria-label"
        assert "innerHTML" not in body, f"{name}: withTooltip must not touch innerHTML"


def test_short_hash_and_tooltip_are_actually_called() -> None:
    minimum_calls = {
        "literature-maps.js": 3,
        "research-tasks.js": 4,
        "app.js": 3,
        "conversation-research.js": 3,
    }
    for name, minimum in minimum_calls.items():
        source = TEXT_SOURCES[name]
        calls = source.count("formatShortHash(") - source.count("function formatShortHash(")
        assert calls >= minimum, f"{name}: only {calls} formatShortHash call(s), need >= {minimum}"
        assert "withTooltip(" in source, f"{name}: withTooltip is never used"


def test_xss_sensitive_textcontent_is_kept_verbatim() -> None:
    # Fixture-driven browser contracts assert the full literal text of these two
    # nodes (test_frontend_map_analysis_markdown.py:37-38, conversation JS probe:77).
    # They are visually shortened with CSS, never rewritten through formatShortHash.
    assert "metadataText(value, '受控来源引用')" in MAPS
    assert "metadataText(record.source_version, '未提供')" in MAPS
    assert "appendDetail(documentRef, fields, '正文', source.text)" in CONV


# ---- 4. task boundaries ------------------------------------------------------
def test_asset_versions_are_frozen() -> None:
    for marker in (
        'href="/assets/styles.css?v=75"',
        'src="/assets/app.js?v=74"',
        'src="/assets/research-tasks.js?v=25"',
        'src="/assets/literature-maps.js?v=47"',
        'src="/assets/conversation-research.js?v=3"',
        'href="/assets/literature-maps.css?v=34"',
    ):
        assert marker in INDEX, f"{marker} must stay frozen (closing task bumps versions)"


def test_no_new_script_tags() -> None:
    assert INDEX.count("<script src=") == 10, "no extra <script> file may be introduced"
