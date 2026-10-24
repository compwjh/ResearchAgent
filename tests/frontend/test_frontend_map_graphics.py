"""Browser contracts for map label edge cases and the production component scale."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"


def _launch(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - host dependent
        pytest.skip(f"真实浏览器阻塞，未将组件检查冒充通过: {type(exc).__name__}: {exc}")


def _positions(page):
    return page.locator("[data-node-id] circle").evaluate_all(
        "nodes => Object.fromEntries(nodes.map(node => [node.parentElement.dataset.nodeId, [node.getAttribute('cx'), node.getAttribute('cy')]]))"
    )


def test_long_labels_keep_contract_markers_visible() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?long-label", wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector('[data-node-id="node-long"]')
        label = page.locator('[data-node-id="node-long"] .literature-map-node-label').text_content() or ""
        assert len(label) <= 38
        assert "et al." in label
        assert "年份未知" in label
        assert "undefined" not in label.lower()
        assert "null" not in label.lower()
        preformatted = page.locator('[data-node-id="node-preformatted"] .literature-map-node-label').text_content() or ""
        assert preformatted.count("et al.") == 1
        page.close()
        browser.close()


def test_labels_keep_a_css_readability_floor_when_canvas_scales() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?graphics", wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector('[data-node-id="node-c"] .literature-map-node-label')

        def label_metrics():
            return page.locator('.literature-map-node-label').evaluate_all(
                """nodes => nodes.map(node => {
                    const rect = node.getBoundingClientRect();
                    const ctm = node.getScreenCTM();
                    return {
                        height: rect.height,
                        width: rect.width,
                        screenScale: ctm ? Math.hypot(ctm.a, ctm.b) : 0,
                    };
                })"""
            )

        # The real component must remain readable after the canvas is made
        # narrow and after a zoom-out; this is intentionally measured in CSS
        # pixels rather than SVG user units.
        page.set_viewport_size({"width": 900, "height": 720})
        page.locator('[data-node-id="node-c"] circle').click()
        page.wait_for_selector('.literature-map-detail-title')
        page.get_by_role('button', name='缩小').click()
        metrics = label_metrics()
        assert metrics
        assert min(item["height"] for item in metrics) >= 9, metrics
        assert min(item["screenScale"] for item in metrics) > 0
        page.close()
        browser.close()


def test_production_component_handles_two_hundred_nodes_without_position_mutation() -> None:
    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(f"{FIXTURE.as_uri()}?large-graph", wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector('[data-node-id="node-large-200"]')
        assert page.locator("[data-node-id]").count() == 200
        assert page.locator(".literature-map-node-label").count() == 200

        before = _positions(page)
        page.locator('[data-node-id="node-a"] circle').click()
        page.wait_for_selector('[data-node-id="node-a"].is-selected')
        render_duration = page.evaluate(
            """() => {
                const select = document.querySelector('#literature-map-label-mode');
                const start = performance.now();
                select.value = 'neighbors';
                select.dispatchEvent(new Event('change', { bubbles: true }));
                return performance.now() - start;
            }"""
        )
        page.wait_for_function("document.querySelectorAll('.literature-map-node-label').length === 2")
        assert isinstance(render_duration, (int, float))
        assert render_duration >= 0
        assert render_duration < 500
        assert _positions(page) == before
        assert page.locator('[data-node-id="node-large-200"] .literature-map-node-label').count() == 0
        page.wait_for_function("window.__viewBodies?.some(body => body.label_mode === 'neighbors')")
        saved = page.evaluate("window.__viewBodies.find(body => body.label_mode === 'neighbors')")
        assert saved["positions"]
        assert next(item for item in saved["positions"] if item["node_id"] == "node-a")["x"] == float(before["node-a"][0])

        page.locator('#literature-map-label-mode').select_option('hidden')
        assert page.locator("[data-node-id]").count() == 200
        assert page.locator(".literature-map-node-label").count() == 0
        page.locator('#literature-map-label-mode').select_option('all')
        assert page.locator("[data-node-id]").count() == 200
        assert page.locator(".literature-map-node-label").count() == 200
        assert page_errors == []
        page.close()
        browser.close()
