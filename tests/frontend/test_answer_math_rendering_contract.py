"""Static contracts for Spec044 answer math (KaTeX) rendering, security and fallback."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")
KATEX_DIR = ROOT / "frontend/vendor/katex"


def _slice_function(source, name):
    """Return the brace-balanced body of `function <name>(...)`."""
    marker = "function " + name + "("
    start = source.index(marker)
    brace_start = source.index("{", start)
    depth = 0
    for i in range(brace_start, len(source)):
        char = source[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace_start:i + 1]
    raise AssertionError("unbalanced braces for " + name)


def test_katex_assets_are_local_and_loaded_before_app():
    assert "/assets/vendor/katex/katex.min.css?v=1" in INDEX
    assert "/assets/vendor/katex/katex.min.js?v=1" in INDEX

    katex_js = INDEX.index('src="/assets/vendor/katex/katex.min.js?v=1"')
    app_js = INDEX.index("src=\"/assets/app.js?v=73\"")
    assert katex_js < app_js

    assert "cdn.jsdelivr.net" not in INDEX
    assert "unpkg.com" not in INDEX
    # 唯一允许的 http(s) 出现在 KaTeX 字体/资源本地路径前缀之外不应存在外链脚本。
    assert "https://cdn" not in INDEX and "http://cdn" not in INDEX


def test_katex_vendor_files_ship_locally():
    assert (KATEX_DIR / "katex.min.js").is_file()
    assert (KATEX_DIR / "katex.min.css").is_file()
    fonts = KATEX_DIR / "fonts"
    assert fonts.is_dir()
    assert any(fonts.glob("*.woff2"))
    assert (KATEX_DIR / "LICENSE").is_file()


def test_answer_math_api_and_frozen_options_present():
    for symbol in (
            "extractAnswerMath",
            "injectAnswerMath",
            "katex.renderToString",
            "answerMathTokens",
            "data-math-token",
            "answer-math-source-popover",
            "showAnswerMathPopover",
            "hideAnswerMathPopover",
    ):
        assert symbol in APP

    for option in (
            "trust: false",
            "maxExpand: 1000",
            "maxSize: 10",
            "throwOnError: false",
            "output: 'htmlAndMathml'",
    ):
        assert option in APP


def test_answer_math_fallback_copy_and_forbidden_style_kept():
    assert "公式渲染不可用，已显示源码" in APP
    assert "公式无法渲染，已显示源码" in APP
    # style 未被 DOMPurify 放开：FORBID_ATTR 名单中仍保留 'style'（XSS 底线）。
    forbid_attr = APP.split("FORBID_ATTR:")[1]
    forbid_attrs_block = forbid_attr.split("]")[0]
    assert "'style'" in forbid_attrs_block


def test_render_markdown_orders_math_extraction_around_sanitize():
    body = re.search(r"function renderMarkdown\([\s\S]*?\n\}", APP).group(0)
    i_extract = body.index("extractAnswerMath")
    i_parse = body.index("marked.parse")
    i_sanitize = body.index("DOMPurify.sanitize")
    i_inject = body.index("injectAnswerMath")
    assert i_extract < i_parse < i_sanitize < i_inject


def test_answer_math_styles_and_motion_contract():
    assert ".answer-math-inline" in STYLES
    assert ".answer-math-block" in STYLES
    assert ".answer-math-source-popover" in STYLES
    assert "prefers-reduced-motion" in STYLES
    assert "@media (max-width: 760px)" in STYLES
