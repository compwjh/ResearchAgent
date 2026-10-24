"""Browser contracts for rendered and safely degraded map analysis Markdown."""

from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"


def _open_analysis_node(page, query: str) -> None:
    page.goto(f"{FIXTURE.as_uri()}?{query}", wait_until="load")
    page.locator('[data-map-id="map-fixture"]').click()
    page.locator('[data-node-id="node-a"] circle').click()
    page.wait_for_selector(".literature-map-analysis-result")


def test_map_analysis_markdown_renders_content_tabs_and_history_safely() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _open_analysis_node(page, "analysis-markdown&full-ready")

        assert page.evaluate("window.__markdownRendererReady") is True
        panel = page.locator(".literature-map-analysis")
        summary = panel.locator(".literature-map-analysis-summary")
        assert summary.locator("h1").inner_text() == "自动主题分析"
        assert summary.locator("strong").inner_text() == "关键结论"
        assert summary.locator("ul li").all_inner_texts() == ["证据一", "证据二"]
        assert [text.strip() for text in summary.locator("code").all_inner_texts()] == ["inline-code", 'print("ok")']
        assert summary.locator("a[href='https://example.org/citation']").count() == 1
        hrefs = summary.locator("a").evaluate_all("nodes => nodes.map((node) => node.getAttribute('href') || '')")
        assert all(not href.lower().startswith("javascript:") for href in hrefs)
        assert summary.locator("script, img").count() == 0
        assert panel.locator(".literature-map-analysis-result-meta b").count() == 0
        assert "<b>abstract</b>" in panel.locator(".literature-map-analysis-result-meta").inner_text()
        assert "<img src=x onerror=alert(1)>" in panel.locator(".literature-map-analysis-citations").inner_text()
        assert panel.locator(".literature-map-analysis-citations img").count() == 0

        panel.locator(".literature-map-analysis-history-button").filter(has_text="v0").click()
        page.wait_for_function("document.querySelector('.literature-map-analysis-summary h2') !== null")
        history_summary = panel.locator(".literature-map-analysis-summary")
        assert history_summary.locator("h2").inner_text() == "历史摘要"
        assert history_summary.locator("strong").inner_text() == "旧版本"
        assert history_summary.locator("ul li").inner_text() == "旧证据"

        panel.get_by_role("tab", name="全文").click()
        page.wait_for_function("document.querySelector('.literature-map-analysis-summary h3') !== null")
        full_summary = panel.locator(".literature-map-analysis-summary")
        assert full_summary.locator("h3").inner_text() == "全文分析"
        assert full_summary.locator("strong").inner_text() == "全文结论"
        assert full_summary.locator("ul li").inner_text() == "全文证据"
        browser.close()


def test_map_analysis_markdown_falls_back_to_text_when_renderer_is_unavailable() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _open_analysis_node(page, "analysis-markdown-no-renderer")

        assert page.evaluate("window.__markdownRendererReady") is False
        summary = page.locator(".literature-map-analysis-summary")
        raw = summary.evaluate("node => node.textContent")
        assert "# 自动主题分析" in raw
        assert "**关键结论**" in raw
        assert "- 证据一" in raw
        assert "[恶意链接](javascript:alert(1))" in raw
        assert summary.locator("h1, strong, ul, li, code, a, script, img").count() == 0
        browser.close()
