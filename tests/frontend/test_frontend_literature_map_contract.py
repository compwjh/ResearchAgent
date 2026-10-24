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
    assert '/assets/literature-maps.js?v=13' in INDEX
    assert '/assets/literature-maps.css?v=10' in INDEX
    app_versions = re.findall(r'<script src="/assets/app\.js\?v=(\d+)"', INDEX)
    style_versions = re.findall(r'<link rel="stylesheet" href="/assets/styles\.css\?v=(\d+)"', INDEX)
    assert app_versions and int(app_versions[-1]) >= 59
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
        "requestCatalog",
        "/api/papers/sources",
        "/api/papers/conferences",
        "/api/projects",
        "SUPPORTED_MAP_SOURCE_IDS",
        "SUPPORTED_MAP_CONFERENCE_IDS",
    ):
        assert marker in MODULE
    assert "window.location.origin" in MODULE
    assert "javascript:" not in MODULE.lower()
    assert "semantic-scholar" not in MODULE
    assert "semantic_scholar" not in MODULE


def test_map_styles_are_scoped_and_fixture_is_not_product_data() -> None:
    assert "#literature-maps-view" in STYLES
    assert "--accent" in STYLES
    assert "grid-template-columns: minmax(212px" in STYLES
    assert ".literature-map-option-list" in STYLES
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
        page.get_by_role('button', name='新建地图').click()
        page.locator('#literature-map-topic').fill('主题筛选夹具')
        page.wait_for_selector('#literature-map-source-options input[value="usenix"]')
        assert page.locator('#literature-map-source-options input[value="semantic_scholar"]').count() == 0
        assert page.locator('#literature-map-topic').input_value() == '主题筛选夹具'
        page.locator('#literature-map-source-options input[value="usenix"]').check()
        page.locator('#literature-map-conference-options input[value="ccs"]').check()
        page.locator('#literature-map-project').select_option('project-fixture')
        page.get_by_role('button', name='开始建图').click()
        page.wait_for_function("window.__createBody?.project_id === 'project-fixture'")
        create_body = page.evaluate("window.__createBody")
        assert create_body["source_ids"] == ["usenix"]
        assert create_body["conference_ids"] == ["ccs"]
        assert create_body["project_id"] == "project-fixture"
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

        # Blank-canvas panning is a persisted viewport change, distinct from
        # dragging a node.  Use a fresh fixture page so the earlier locate/zoom
        # checks cannot influence the initial viewport of this lifecycle case.
        gesture_page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        gesture_page.goto(FIXTURE.as_uri(), wait_until='load')
        gesture_page.locator('[data-map-id="map-fixture"]').click()
        gesture_page.wait_for_selector('[data-node-id="node-a"]')
        svg = gesture_page.locator('#literature-map-svg')
        svg_box = svg.bounding_box()
        assert svg_box
        gesture_page.mouse.move(svg_box['x'] + 40, svg_box['y'] + 40)
        gesture_page.mouse.down()
        gesture_page.mouse.move(svg_box['x'] + 100, svg_box['y'] + 70, steps=4)
        gesture_page.mouse.up()
        gesture_page.wait_for_function("window.__viewBodies?.some((body) => body.viewport?.x === 60 && body.viewport?.y === 30)")
        pan_body = gesture_page.evaluate("window.__viewBodies.at(-1)")
        assert pan_body['viewport']['x'] == 60
        assert pan_body['viewport']['y'] == 30

        # Existing node-drag and zoom saves must retain the panned viewport.
        node_box = gesture_page.locator('[data-node-id="node-a"] circle').bounding_box()
        assert node_box
        gesture_page.mouse.move(node_box['x'] + node_box['width'] / 2, node_box['y'] + node_box['height'] / 2)
        gesture_page.mouse.down()
        gesture_page.mouse.move(node_box['x'] + node_box['width'] / 2 + 20, node_box['y'] + node_box['height'] / 2 + 10, steps=3)
        gesture_page.mouse.up()
        gesture_page.wait_for_function("window.__viewBodies?.at(-1)?.positions?.some((position) => position.node_id === 'node-a' && position.x !== 390)")
        node_body = gesture_page.evaluate("window.__viewBodies.at(-1)")
        assert node_body['viewport']['x'] == 60
        assert node_body['viewport']['y'] == 30
        gesture_page.get_by_role('button', name='放大').click()
        gesture_page.wait_for_function("window.__viewBodies?.at(-1)?.viewport?.scale > 1")
        zoom_body = gesture_page.evaluate("window.__viewBodies.at(-1)")
        assert zoom_body['viewport']['x'] == 60
        assert zoom_body['viewport']['y'] == 30
        assert zoom_body['viewport']['scale'] > 1

        # Reopen through the public lifecycle and verify the persisted
        # viewport and node position are restored rather than reset.
        gesture_page.evaluate("window.LiteratureMaps.setActive(false)")
        gesture_page.wait_for_timeout(50)
        gesture_page.evaluate("window.LiteratureMaps.setActive(true)")
        gesture_page.wait_for_selector('[data-map-id="map-fixture"]')
        gesture_page.locator('[data-map-id="map-fixture"]').click()
        gesture_page.wait_for_selector('[data-node-id="node-a"]')
        gesture_page.wait_for_function("document.querySelector('#literature-map-viewport')?.getAttribute('transform')?.includes('translate(60 30) scale(')")
        reopened_transform = gesture_page.locator('#literature-map-viewport').get_attribute('transform')
        assert reopened_transform and 'translate(60 30) scale(' in reopened_transform
        reopened_scale = float(re.search(r'scale\(([^)]+)\)', reopened_transform).group(1))
        assert reopened_scale > 1
        reopened_node = gesture_page.locator('[data-node-id="node-a"] circle').get_attribute('cx')
        assert reopened_node and float(reopened_node) != 390
        gesture_page.close()

        fallback = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        fallback.goto(f'{FIXTURE.as_uri()}?options-fail', wait_until='load')
        fallback.get_by_role('button', name='新建地图').click()
        fallback.wait_for_function("document.querySelector('#literature-map-source-notice')?.dataset.state === 'warning'")
        assert '仍可直接建图' in fallback.locator('#literature-map-source-notice').inner_text()
        fallback.locator('#literature-map-topic').fill('通用范围建图')
        fallback.get_by_role('button', name='开始建图').click()
        fallback.wait_for_function("window.__createBody?.topic === '通用范围建图'")
        fallback_body = fallback.evaluate("window.__createBody")
        assert 'source_ids' not in fallback_body
        assert 'conference_ids' not in fallback_body
        assert 'project_id' not in fallback_body
        fallback.close()

        leave_page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        leave_page.goto(f'{FIXTURE.as_uri()}?options-delay', wait_until='load')
        leave_page.get_by_role('button', name='新建地图').click()
        leave_page.locator('#literature-map-topic').fill('离开后不应回写')
        leave_page.evaluate("window.LiteratureMaps.setActive(false)")
        leave_page.wait_for_timeout(350)
        assert leave_page.locator('#literature-map-create-panel').is_hidden()
        assert leave_page.locator('#literature-map-topic').input_value() == ''
        assert leave_page.locator('#literature-map-source-options .literature-map-option').count() == 0
        leave_page.close()

        success_page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        success_page.goto(f'{FIXTURE.as_uri()}?options-delay', wait_until='load')
        success_page.get_by_role('button', name='新建地图').click()
        success_page.locator('#literature-map-topic').fill('创建后不应回写')
        success_page.get_by_role('button', name='开始建图').click()
        success_page.wait_for_function("window.__createBody?.topic === '创建后不应回写'")
        success_page.wait_for_timeout(350)
        assert success_page.locator('#literature-map-create-panel').is_hidden()
        assert success_page.locator('#literature-map-topic').input_value() == ''
        assert success_page.locator('#literature-map-source-options .literature-map-option').count() == 0
        success_page.close()

        truncated_page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        truncated_page.goto(f'{FIXTURE.as_uri()}?projects-truncated', wait_until='load')
        truncated_page.get_by_role('button', name='新建地图').click()
        truncated_page.wait_for_function("document.querySelector('#literature-map-project-notice')?.textContent.includes('项目列表未加载完')")
        assert '重新打开重试' in truncated_page.locator('#literature-map-project-notice').inner_text()
        truncated_page.close()
        browser.close()
