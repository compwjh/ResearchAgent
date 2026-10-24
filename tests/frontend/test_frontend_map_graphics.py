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


def _viewport_metrics(page):
    return page.evaluate(
        """() => {
            const svg = document.querySelector('#literature-map-svg');
            const svgRect = svg.getBoundingClientRect();
            const circles = [...document.querySelectorAll('[data-node-id] circle')]
                .map((node) => node.getBoundingClientRect());
            const labels = [...document.querySelectorAll('.literature-map-node-label')]
                .map((node) => node.getBoundingClientRect());
            const bounds = (rects) => rects.length ? {
                left: Math.min(...rects.map((rect) => rect.left)),
                right: Math.max(...rects.map((rect) => rect.right)),
                top: Math.min(...rects.map((rect) => rect.top)),
                bottom: Math.max(...rects.map((rect) => rect.bottom)),
            } : null;
            const nodeBounds = bounds(circles);
            const contentBounds = bounds([...circles, ...labels]);
            const viewBox = svg.viewBox.baseVal;
            const baseScale = Math.min(svgRect.width / viewBox.width, svgRect.height / viewBox.height);
            const visibleBounds = {
                left: svgRect.left + (svgRect.width - viewBox.width * baseScale) / 2,
                right: svgRect.right - (svgRect.width - viewBox.width * baseScale) / 2,
                top: svgRect.top + (svgRect.height - viewBox.height * baseScale) / 2,
                bottom: svgRect.bottom - (svgRect.height - viewBox.height * baseScale) / 2,
            };
            let labelOverlaps = 0;
            for (let index = 0; index < labels.length; index += 1) {
                for (let other = index + 1; other < labels.length; other += 1) {
                    if (labels[index].left < labels[other].right && labels[index].right > labels[other].left
                        && labels[index].top < labels[other].bottom && labels[index].bottom > labels[other].top) labelOverlaps += 1;
                }
            }
            const transform = document.querySelector('#literature-map-viewport')?.getAttribute('transform') || '';
            const scale = Number(transform.match(/scale\\(([-+0-9.e]+)\\)/)?.[1] || 0);
            return {
                svg: { width: svgRect.width, height: svgRect.height },
                nodes: nodeBounds ? { width: nodeBounds.right - nodeBounds.left, height: nodeBounds.bottom - nodeBounds.top } : null,
                margins: contentBounds ? {
                    left: contentBounds.left - visibleBounds.left,
                    right: visibleBounds.right - contentBounds.right,
                    top: contentBounds.top - visibleBounds.top,
                    bottom: visibleBounds.bottom - contentBounds.bottom,
                } : null,
                scale,
                labelOverlaps,
            };
        }"""
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


def test_first_open_fits_a_tiny_saved_view_to_the_real_canvas() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?tiny-saved-view", wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector('[data-node-id="node-b"]')
        metrics = _viewport_metrics(page)
        assert metrics["scale"] > 1
        assert metrics["nodes"]["width"] / metrics["svg"]["width"] >= 0.25, metrics
        assert metrics["nodes"]["height"] / metrics["svg"]["height"] >= 0.1, metrics
        assert min(metrics["margins"].values()) >= 43, metrics
        assert metrics["labelOverlaps"] == 0, metrics
        assert page.evaluate("window.__viewBodies") == []
        page.close()
        browser.close()


def test_first_open_fit_keeps_large_graph_labels_inside_a_narrow_canvas() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 900, "height": 720}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?large-graph", wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector('[data-node-id="node-large-200"]')
        assert page.locator('[data-node-id] circle').count() == 200
        assert page.locator('.literature-map-node-label').count() == 200
        metrics = _viewport_metrics(page)
        assert metrics["margins"]
        assert min(metrics["margins"].values()) >= 43, metrics
        page.close()
        browser.close()


def test_first_open_fits_the_backend_default_view_to_the_real_canvas() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(FIXTURE.as_uri(), wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector('[data-node-id="node-b"]')
        metrics = _viewport_metrics(page)
        assert metrics["scale"] > 1
        assert metrics["nodes"]["width"] / metrics["svg"]["width"] >= 0.25, metrics
        assert metrics["nodes"]["height"] / metrics["svg"]["height"] >= 0.1, metrics
        assert min(metrics["margins"].values()) >= 43, metrics
        assert metrics["labelOverlaps"] == 0, metrics
        assert page.evaluate("window.__viewBodies") == []
        page.close()
        browser.close()


def test_usable_saved_view_is_restored_without_initial_refit_or_save() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?usable-saved-view", wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector('[data-node-id="node-b"]')
        transform = page.locator('#literature-map-viewport').get_attribute('transform') or ''
        assert 'translate(-24 -32) scale(1.25)' in transform
        assert page.evaluate("window.__viewBodies") == []
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
