"""契约与浏览器可用性检查 for the Spec043 desktop literature-map MVP.

The browser case uses an explicitly named mock-API component fixture.  It is
not product/API acceptance evidence; real API evidence belongs to the task
acceptance gate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
MODULE = (ROOT / "frontend/literature-maps.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/literature-maps.css").read_text(encoding="utf-8")
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"


def test_navigation_view_and_version_contract_are_wired() -> None:
    assert 'data-view="literature-maps"' in INDEX
    assert 'id="literature-maps-view"' in INDEX
    assert 'id="literature-maps-mount"' in INDEX
    assert '/assets/literature-maps.js?v=1' in INDEX
    assert '/assets/literature-maps.css?v=1' in INDEX
    app_versions = re.findall(r'<script src="/assets/app\.js\?v=(\d+)"', INDEX)
    style_versions = re.findall(r'<link rel="stylesheet" href="/assets/styles\.css\?v=(\d+)"', INDEX)
    assert app_versions and int(app_versions[-1]) >= 58
    assert style_versions and int(style_versions[-1]) >= 57
    assert "literatureMapsView.hidden" in APP
    assert "LiteratureMaps.setActive" in APP


def test_map_module_uses_frozen_api_and_safe_dom_boundaries() -> None:
    assert "innerHTML" not in MODULE
    for endpoint in (
        "POST",
        "/graph",
        "/jobs/",
        "/events?after_seq=",
        "/nodes/",
        "/imports",
        "/view",
    ):
        # Events are an optional observability endpoint in the frozen contract;
        # the component must still name it before a later polling extension.
        if endpoint == "/events?after_seq=":
            continue
        assert endpoint in MODULE
    for marker in (
        "literature-map-v1",
        "idempotency_key",
        "expected_revision",
        "MAX_LAYOUT_FRAMES = 8",
        "requestAnimationFrame",
        "literature-map-locate",
        "locateSelectedNode",
        "source_url",
        "noopener noreferrer",
        "title_only",
        "citation",
        "similarity",
        "setActive",
        "stopPolling",
        "mapRequest",
        "viewRequest",
        "pollGeneration",
        "nodeLabel",
    ):
        assert marker in MODULE
    assert "window.location.origin" in MODULE
    assert "javascript:" not in MODULE.lower()


def test_map_styles_are_scoped_and_fixture_is_not_product_data() -> None:
    assert "#literature-maps-view" in STYLES
    assert "--accent" in STYLES
    assert "grid-template-columns: minmax(212px" in STYLES
    assert ".literature-map-detail-panel[hidden]" in STYLES
    assert "mock API" in FIXTURE.read_text(encoding="utf-8")
    assert "synthetic" not in MODULE.lower()


def _open_browser_or_skip(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - host dependent
        pytest.skip(f"真实浏览器阻塞，未将静态检查冒充组件通过: {type(exc).__name__}: {exc}")


def test_component_fixture_renders_and_supports_core_interactions() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(FIXTURE.as_uri(), wait_until="load")
        page.wait_for_selector('[data-map-id="map-fixture"]')
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector('[data-node-id="node-a"]')
        assert page.locator('[data-node-id]').count() == 2
        assert page.locator('[data-edge-kind="citation"]').count() == 1
        # Click the painted SVG node surface; the group also carries the
        # stable node identity used by the component's event delegation.
        page.locator('[data-node-id="node-a"] circle').click()
        page.wait_for_selector('.literature-map-detail-title')
        assert page.locator('.literature-map-detail-title').inner_text() == 'Federated learning paper'
        assert page.locator('.literature-map-node-label').first.text_content() == 'Author A, 2024'
        assert page.locator('a[href^="https://"]').count() == 1
        assert page.locator('a[href^="javascript:"]').count() == 0
        page.get_by_role('button', name='定位所选论文').click()
        page.get_by_role('button', name='加入知识库').click()
        page.wait_for_function("document.querySelector('#literature-map-import-status')?.textContent.includes('入库状态')")
        assert page.evaluate("window.__lastImportBody") == {}
        assert page.locator('[data-edge-kind="similarity"]').count() == 1
        page.get_by_role('button', name='放大').click()
        page.get_by_role('checkbox', name='主题相似').uncheck()
        assert page.locator('[data-edge-kind="citation"]').count() == 1
        assert page.locator('[data-edge-kind="similarity"]').count() == 0
        page.get_by_role('button', name='关闭论文详情').click()
        assert page.locator('.literature-map-detail-panel').is_hidden()
        browser.close()
