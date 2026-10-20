"""Contract and browser checks for Task06 map groups and exports."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
MODULE = (ROOT / "frontend/literature-maps.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/literature-maps.css").read_text(encoding="utf-8")
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"


def test_groups_and_export_contract_is_wired_without_html_injection() -> None:
    assert "/assets/literature-maps.js?v=12" in INDEX
    assert "/assets/literature-maps.css?v=8" in INDEX
    for endpoint in ("/groups", "/nodes/", "/group", "/export?format=json"):
        assert endpoint in MODULE
    for marker in (
        "literature-map-groups",
        "literature-map-group-create",
        "literature-map-group-name",
        "literature-map-group-color",
        "literature-map-node-group",
        "literature-map-export-json",
        "literature-map-export-png",
        "literature-map-export-v1",
        "XMLSerializer",
        "createObjectURL",
        "MAP_REVISION_CONFLICT",
    ):
        assert marker in MODULE
    assert "innerHTML" not in MODULE
    assert "textContent" in MODULE
    assert "literature-map-group-swatch" in STYLES


def test_export_asset_versions_are_synchronised() -> None:
    fixture = FIXTURE.read_text(encoding="utf-8")
    assert "/literature-maps.css?v=8" in fixture
    assert "/literature-maps.js?v=12" in fixture
    assert re.findall(r"literature-maps\.js\?v=(\d+)", INDEX)[-1] == "12"


def _open_browser_or_skip(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - host dependent
        pytest.skip(f"浏览器不可用，未将静态检查冒充通过: {type(exc).__name__}: {exc}")


def test_group_management_and_exports_in_browser() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _open_browser_or_skip(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{FIXTURE.as_uri()}?groups-export", wait_until="load")
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector('[data-node-id="node-a"]')
        page.wait_for_selector('#literature-map-groups [data-group-id="group-fixture"]')

        page.locator('#literature-map-group-name').fill('证据分组')
        page.locator('#literature-map-group-color').fill('#2266aa')
        page.locator('#literature-map-group-create').click()
        page.wait_for_function("window.__groupBodies?.some((body) => body.name === '证据分组')")
        assert page.evaluate("window.__groupBodies.at(-1).expected_revision") == 3

        page.locator('[data-node-id="node-a"] circle').click()
        page.wait_for_selector('#literature-map-node-group')
        page.locator('#literature-map-node-group').select_option('group-fixture')
        page.wait_for_function("window.__nodeGroupBodies?.at(-1)?.group_id === 'group-fixture'")
        assert page.evaluate("window.__nodeGroupBodies.at(-1).expected_revision") >= 3
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('data-group-color') == '#3366cc'

        page.locator('[data-group-id="group-fixture"] .literature-map-group-delete').click()
        page.wait_for_function("!Array.from(document.querySelectorAll('#literature-map-group-list [data-group-id]')).some((node) => node.dataset.groupId === 'group-fixture')")
        assert page.locator('[data-node-id="node-a"]').get_attribute('data-group-id') in (None, '')
        assert page.locator('[data-node-id="node-a"]').get_attribute('data-group-color') in (None, '')

        with page.expect_download() as json_download:
            page.locator('#literature-map-export-json').click()
        assert json_download.value.suggested_filename.endswith('.json')

        with page.expect_download() as png_download:
            page.locator('#literature-map-export-png').click()
        assert png_download.value.suggested_filename.endswith('.png')
        browser.close()
