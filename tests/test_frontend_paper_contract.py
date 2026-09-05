"""Static contracts for the security paper discovery UI.

These checks intentionally avoid a browser dependency.  They protect the DOM
boundary between the paper renderer and its scoped stylesheet while keeping
paper metadata out of HTML string injection paths.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_paper_view_has_stable_render_targets() -> None:
    required_ids = {
        "papers-view",
        "paper-search-form",
        "paper-conference-list",
        "paper-results",
        "paper-results-toolbar",
        "paper-import-panel",
        "paper-import-items",
        "paper-login-queue",
        "paper-login-items",
        "paper-conference-dialog",
    }
    for element_id in required_ids:
        assert f'id="{element_id}"' in INDEX


def test_paper_content_renderer_uses_safe_dom_text_boundary() -> None:
    start = APP.index("function renderPaperResults")
    end = APP.index("function jumpToKnowledgeBase", start)
    results_renderer = APP[start:end]
    assert "innerHTML" not in results_renderer
    for field in ("paper-result-title", "paper-result-meta", "paper-result-abstract"):
        assert field in results_renderer
    assert "title.textContent" in results_renderer
    assert "meta.textContent" in results_renderer
    assert "abstract.textContent" in results_renderer

    batch_start = APP.index("function renderPaperBatch")
    batch_end = APP.index("async function paperLogin", batch_start)
    batch_renderer = APP[batch_start:batch_end]
    assert "innerHTML" not in batch_renderer
    assert "title.textContent" in batch_renderer
    assert "error.textContent" in batch_renderer


def test_paper_styles_cover_long_content_scrolling_and_focus() -> None:
    selectors = (
        "#papers-view .paper-search-form",
        "#papers-view .paper-conference-list",
        "#papers-view .paper-results",
        "#papers-view .paper-result-title",
        "#papers-view .paper-result-meta",
        "#papers-view .paper-import-items",
        "#papers-view .paper-login-queue",
        ".paper-conference-dialog",
        ".paper-conference-dialog .paper-managed-conferences",
        "#papers-view :is(button, input, textarea, select, [tabindex]):focus-visible",
    )
    for selector in selectors:
        assert selector in STYLES

    assert "overflow-wrap: anywhere" in STYLES
    assert "overflow-y: auto" in STYLES
    assert "@media (max-width: 760px)" in STYLES
    assert "@media (max-width: 430px)" in STYLES
