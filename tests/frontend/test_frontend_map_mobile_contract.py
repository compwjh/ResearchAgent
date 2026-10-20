"""Mobile map contracts and real Chromium input simulations.

The fixture uses a synthetic API and is not real API acceptance evidence. The
browser checks use Chromium DevTools touch input (not page-level
``dispatchEvent`` calls), so they exercise browser pointer and scroll paths.
They remain simulator evidence rather than physical-device evidence.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pytest
from playwright.sync_api import Page, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
MODULE = (ROOT / "frontend/literature-maps.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/literature-maps.css").read_text(encoding="utf-8")
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"


def _touch(cdp, event_type: str, points: Iterable[tuple[int, float, float]]) -> None:
    cdp.send(
        "Input.dispatchTouchEvent",
        {
            "type": event_type,
            "touchPoints": [{"id": point_id, "x": x, "y": y} for point_id, x, y in points],
            "modifiers": 0,
        },
    )


def _transform(page: Page) -> tuple[float, float, float]:
    value = page.locator("#literature-map-viewport").get_attribute("transform") or ""
    match = re.search(r"translate\(([-+0-9.e]+)\s+([-+0-9.e]+)\)\s+scale\(([-+0-9.e]+)\)", value)
    assert match, value
    return tuple(float(item) for item in match.groups())


def _select_map(page: Page) -> None:
    page.locator('[data-map-id="map-fixture"]').click()
    page.wait_for_selector('[data-node-id="node-a"]')
    page.wait_for_function("document.querySelector('#literature-map-current-title')?.textContent && !document.querySelector('#literature-map-current-title').textContent.includes('选择一张地图')")
    page.wait_for_timeout(180)
    page.evaluate("window.__viewBodies = []")


def test_mobile_map_contract_is_versioned_scoped_and_touch_safe() -> None:
    assert "/assets/literature-maps.js?v=12" in INDEX
    assert "/assets/literature-maps.css?v=8" in INDEX
    assert "/literature-maps.js?v=12" in FIXTURE.read_text(encoding="utf-8")
    assert "/literature-maps.css?v=8" in FIXTURE.read_text(encoding="utf-8")
    for marker in (
        "literature-map-mobile-list-open",
        "literature-map-mobile-backdrop",
        "literature-map-list-close",
        "openMobilePanel",
        "closeMobilePanel",
        "restoreMobileFocus",
        "pointercancel",
        "visibilitychange",
        "MIN_MAP_SCALE",
        "MAX_MAP_SCALE",
        "pointers",
        "literature-map-detail",
        "literature-map-list-panel.is-open",
    ):
        assert marker in MODULE or marker in STYLES
    assert "innerHTML" not in MODULE
    assert "touch-action: none" in STYLES
    assert "touch-action: pan-y" in STYLES
    assert re.findall(r"literature-maps\.js\?v=(\d+)", INDEX)[-1] == "12"


@pytest.mark.parametrize("width", [375, 390])
def test_mobile_map_drawers_single_pan_and_desktop_boundary(width: int) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": 820}, has_touch=True, is_mobile=True)
        page.goto(FIXTURE.as_uri(), wait_until="load")

        list_open = page.locator("#literature-map-mobile-list-open")
        list_close = page.locator("#literature-map-list-close")
        list_panel = page.locator(".literature-map-list-panel")
        list_open.click()
        page.wait_for_function("document.querySelector('.literature-map-list-panel')?.classList.contains('is-open')")
        assert list_panel.get_attribute("aria-hidden") == "false"
        list_close.click()
        page.wait_for_function("!document.querySelector('.literature-map-list-panel')?.classList.contains('is-open')")
        assert page.evaluate("document.activeElement?.id") == "literature-map-mobile-list-open"

        list_open.click()
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector('[data-node-id="node-a"]')
        page.wait_for_function("!document.querySelector('.literature-map-list-panel')?.classList.contains('is-open')")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        svg = page.locator("#literature-map-svg")
        svg_box = svg.bounding_box()
        assert svg_box is not None
        before = _transform(page)
        cdp = page.context.new_cdp_session(page)
        x = svg_box["x"] + svg_box["width"] * 0.32
        y = svg_box["y"] + svg_box["height"] * 0.48
        _touch(cdp, "touchStart", [(1, x, y)])
        _touch(cdp, "touchMove", [(1, x + 56, y + 24)])
        _touch(cdp, "touchEnd", [])
        after = _transform(page)
        assert after[:2] != before[:2]
        page.wait_for_function("window.__viewBodies.length >= 1", timeout=3000)

        node = page.locator('[data-node-id="node-a"] circle')
        node_box = node.bounding_box()
        assert node_box is not None
        page.touchscreen.tap(node_box["x"] + node_box["width"] / 2, node_box["y"] + node_box["height"] / 2)
        page.wait_for_function("document.querySelector('.literature-map-detail-panel')?.classList.contains('is-open')")
        detail = page.locator(".literature-map-detail")
        assert page.evaluate("getComputedStyle(document.querySelector('.literature-map-detail')).touchAction") == "pan-y"
        assert detail.is_visible()
        page.locator("#literature-map-detail-close").click()
        page.wait_for_function("document.querySelector('.literature-map-detail-panel')?.hidden === true")
        assert page.evaluate("document.activeElement?.dataset?.nodeId") == "node-a"

        page.close()
        desktop = browser.new_page(viewport={"width": 1440, "height": 900})
        desktop.goto(FIXTURE.as_uri(), wait_until="load")
        _select_map(desktop)
        assert desktop.locator(".literature-map-grid").evaluate("el => getComputedStyle(el).display") == "grid"
        desktop.locator('[data-node-id="node-a"] circle').click()
        assert desktop.locator(".literature-map-detail-panel").is_visible()
        desktop.close()
        browser.close()


def test_mobile_pinch_center_bounds_switch_and_blur_cleanup() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 820}, has_touch=True, is_mobile=True)
        page.goto(FIXTURE.as_uri(), wait_until="load")
        page.locator("#literature-map-mobile-list-open").evaluate("el => el.click()")
        _select_map(page)

        svg = page.locator("#literature-map-svg")
        svg_box = svg.bounding_box()
        assert svg_box is not None
        cdp = page.context.new_cdp_session(page)
        cx = svg_box["x"] + svg_box["width"] / 2
        cy = svg_box["y"] + svg_box["height"] / 2
        before = _transform(page)
        svg_x = (cx - svg_box["x"]) * 960 / svg_box["width"]
        svg_y = (cy - svg_box["y"]) * 680 / svg_box["height"]
        before_world = ((svg_x - before[0]) / before[2], (svg_y - before[1]) / before[2])

        _touch(cdp, "touchStart", [(1, cx - 45, cy), (2, cx + 45, cy)])
        _touch(cdp, "touchMove", [(1, cx - 75, cy), (2, cx + 75, cy)])
        pinch_transform = _transform(page)
        assert pinch_transform[2] > before[2]
        after_world = ((svg_x - pinch_transform[0]) / pinch_transform[2], (svg_y - pinch_transform[1]) / pinch_transform[2])
        assert after_world == pytest.approx(before_world, abs=0.8)
        _touch(cdp, "touchEnd", [])
        page.wait_for_function("window.__viewBodies.length >= 1", timeout=3000)
        page.wait_for_timeout(650)
        assert len(page.evaluate("window.__viewBodies")) == 1

        page.evaluate("window.__viewBodies = []")
        _touch(cdp, "touchStart", [(3, svg_box["x"] + 4, cy), (4, svg_box["x"] + svg_box["width"] - 4, cy)])
        _touch(cdp, "touchMove", [(3, cx - 2, cy), (4, cx + 2, cy)])
        _touch(cdp, "touchEnd", [])
        assert _transform(page)[2] <= 2.8 + 1e-6
        _touch(cdp, "touchStart", [(5, cx - 2, cy), (6, cx + 2, cy)])
        _touch(cdp, "touchMove", [(5, svg_box["x"] + 4, cy), (6, svg_box["x"] + svg_box["width"] - 4, cy)])
        _touch(cdp, "touchEnd", [])
        assert _transform(page)[2] >= 0.35 - 1e-6

        page.evaluate("window.__viewBodies = []")
        page.evaluate(
            """() => {
                const svg = document.querySelector('#literature-map-svg');
                window.__touchEvents = [];
                ['pointerdown', 'pointermove', 'pointerup', 'pointercancel'].forEach((type) => {
                    svg.addEventListener(type, (event) => window.__touchEvents.push({ type, id: event.pointerId, pointerType: event.pointerType }));
                });
            }"""
        )
        _touch(cdp, "touchStart", [(7, cx - 44, cy), (8, cx + 44, cy)])
        _touch(cdp, "touchMove", [(7, cx - 62, cy), (8, cx + 62, cy)])
        after_pinch_move = _transform(page)
        _touch(cdp, "touchEnd", [(8, cx + 62, cy)])
        after_first_up = _transform(page)
        _touch(cdp, "touchMove", [(7, cx - 10, cy + 20)])
        after_switch_move = _transform(page)
        assert after_first_up == pytest.approx(after_pinch_move, abs=0.01)
        assert after_switch_move == pytest.approx(after_first_up, abs=0.01)
        _touch(cdp, "touchEnd", [])
        touch_events = page.evaluate("window.__touchEvents")
        assert any(event["type"] == "pointerup" and event["pointerType"] == "touch" for event in touch_events), touch_events
        assert any(event["type"] == "pointermove" and event["pointerType"] == "touch" for event in touch_events), touch_events
        assert any(
            event["type"] == "pointerup"
            and event["pointerType"] == "touch"
            and any(
                later["type"] == "pointermove"
                and later["pointerType"] == "touch"
                and later["id"] != event["id"]
                for later in touch_events[index + 1 :]
            )
            for index, event in enumerate(touch_events)
        ), touch_events
        page.wait_for_function("window.__viewBodies.length >= 1", timeout=3000)
        page.wait_for_timeout(650)
        assert len(page.evaluate("window.__viewBodies")) == 1

        _touch(cdp, "touchStart", [(9, cx, cy)])
        page.evaluate("window.dispatchEvent(new Event('blur'))")
        _touch(cdp, "touchEnd", [])
        node = page.locator('[data-node-id="node-a"] circle')
        node_box = node.bounding_box()
        assert node_box is not None
        page.touchscreen.tap(node_box["x"] + node_box["width"] / 2, node_box["y"] + node_box["height"] / 2)
        page.wait_for_function("document.querySelector('.literature-map-detail-panel')?.classList.contains('is-open')")
        browser.close()


def test_mobile_drawer_and_detail_scroll_use_real_touch_gestures() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 375, "height": 820}, has_touch=True, is_mobile=True)
        page.goto(f"{FIXTURE.as_uri()}?mobile-long", wait_until="load")
        page.locator("#literature-map-mobile-list-open").click(force=True)
        _select_map(page)
        page.locator("#literature-map-mobile-list-open").evaluate("el => el.click()")
        groups = page.locator("#literature-map-groups")
        page.wait_for_function("!document.querySelector('#literature-map-groups')?.hidden")
        page.wait_for_timeout(240)
        assert groups.evaluate("el => el.scrollHeight > el.clientHeight")
        group_box = groups.bounding_box()
        assert group_box is not None
        cdp = page.context.new_cdp_session(page)
        scroll_before = groups.evaluate("el => el.scrollTop")
        x = group_box["x"] + group_box["width"] / 2
        _touch(cdp, "touchStart", [(10, x, group_box["y"] + group_box["height"] - 20)])
        _touch(cdp, "touchMove", [(10, x, group_box["y"] + group_box["height"] - 110)])
        _touch(cdp, "touchMove", [(10, x, group_box["y"] + group_box["height"] - 200)])
        _touch(cdp, "touchEnd", [])
        page.wait_for_function("document.querySelector('#literature-map-groups')?.scrollTop > 0", timeout=3000)
        assert groups.evaluate("el => el.scrollTop") > scroll_before
        page.wait_for_timeout(240)

        page.locator("#literature-map-list-close").click()
        page.wait_for_function("!document.querySelector('.literature-map-list-panel')?.classList.contains('is-open')")
        node = page.locator('[data-node-id="node-a"] circle')
        node_box = node.bounding_box()
        assert node_box is not None
        page.touchscreen.tap(node_box["x"] + node_box["width"] / 2, node_box["y"] + node_box["height"] / 2)
        page.wait_for_function("document.querySelector('.literature-map-detail-panel')?.classList.contains('is-open')")
        page.wait_for_timeout(240)
        detail = page.locator("#literature-map-detail")
        assert detail.evaluate("el => el.scrollHeight > el.clientHeight")
        detail_box = detail.bounding_box()
        assert detail_box is not None
        detail_before = detail.evaluate("el => el.scrollTop")
        x = detail_box["x"] + detail_box["width"] / 2
        _touch(cdp, "touchStart", [(11, x, detail_box["y"] + detail_box["height"] - 20)])
        _touch(cdp, "touchMove", [(11, x, detail_box["y"] + detail_box["height"] - 130)])
        page.wait_for_function("document.querySelector('#literature-map-detail')?.scrollTop > 0", timeout=3000)
        detail_mid_scroll = detail.evaluate("el => el.scrollTop")
        _touch(cdp, "touchMove", [(11, x, detail_box["y"] + detail_box["height"] - 220)])
        _touch(cdp, "touchEnd", [])
        assert detail_mid_scroll > detail_before
        browser.close()


def test_desktop_mouse_node_drag_saves_changed_position() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(FIXTURE.as_uri(), wait_until="load")
        _select_map(page)
        node = page.locator('[data-node-id="node-a"] circle')
        box = node.bounding_box()
        assert box is not None
        page.evaluate("window.__viewBodies = []")
        start_x = box["x"] + box["width"] / 2
        start_y = box["y"] + box["height"] / 2
        page.mouse.move(start_x, start_y)
        page.mouse.down()
        page.mouse.move(start_x + 64, start_y + 28, steps=3)
        page.mouse.up()
        page.wait_for_function("window.__viewBodies.length >= 1", timeout=3000)
        body = page.evaluate("window.__viewBodies.at(-1)")
        position = next(item for item in body["positions"] if item["node_id"] == "node-a")
        assert (position["x"], position["y"]) != (390, 300)
        browser.close()
