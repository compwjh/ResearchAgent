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
    assert "/assets/literature-maps.js?v=46" in INDEX
    assert "/assets/literature-maps.css?v=33" in INDEX
    for endpoint in ("/groups", "/nodes/", "/group", "/export?format=json"):
        assert endpoint in MODULE
    for marker in (
        # Spec043 起分组入口搬到画布左下角 FAB 浮层，原 `#literature-map-groups` 面板已删除。
        "literature-map-groups-fab",
        "literature-map-groups-popover",
        "literature-map-group-list",
        "literature-map-group-empty",
        "literature-map-group-form",
        "literature-map-group-row",
        "literature-map-group-color-trigger",
        "literature-map-group-name",
        "literature-map-node-group",
        "literature-map-export-json",
        "literature-map-export-png",
        "literature-map-export-v2",
        "XMLSerializer",
        "createObjectURL",
        "MAP_REVISION_CONFLICT",
    ):
        assert marker in MODULE
    # 已删除的旧面板容器不得再出现（防止 FAB 改造被回退成双入口）。
    assert "literature-map-groups'" not in MODULE
    assert "innerHTML" not in MODULE
    assert "textContent" in MODULE
    assert "literature-map-group-swatch" in STYLES
    assert ".literature-map-groups-fab" in STYLES
    assert ".literature-map-groups-popover" in STYLES


def test_export_asset_versions_are_synchronised() -> None:
    fixture = FIXTURE.read_text(encoding="utf-8")
    assert "/literature-maps.css?v=33" in fixture
    assert "/literature-maps.js?v=46" in fixture
    assert re.findall(r"literature-maps\.js\?v=(\d+)", INDEX)[-1] == "46"
    assert re.findall(r"literature-maps\.css\?v=(\d+)", INDEX)[-1] == "33"


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

        # 分组入口只能通过画布左下角 FAB 展开的浮层进入。
        fab = page.locator('#literature-map-groups-fab')
        fab.wait_for(state="visible")
        assert page.locator('#literature-map-groups').count() == 0, '旧的左侧分组面板必须已删除'
        fab.click()
        popover = page.locator('#literature-map-groups-popover')
        popover.wait_for(state="visible")
        assert fab.get_attribute('aria-expanded') == 'true'
        popover.locator('.literature-map-group-row[data-group-id="group-fixture"]').wait_for(state="visible")
        assert popover.locator('.literature-map-group-row[data-group-id="group-fixture"] .literature-map-group-color-trigger').count() == 1

        # 新建分组表单折叠在「＋ 新建组」summary 内。
        create_details = popover.locator('.literature-map-groups-create')
        assert create_details.get_attribute('open') is None
        create_details.locator('summary').click()
        page.locator('#literature-map-group-name').fill('证据分组')
        page.locator('#literature-map-group-color').fill('#2266aa')
        page.locator('#literature-map-group-create').click()
        page.wait_for_function("window.__groupBodies?.some((body) => body.name === '证据分组')")
        assert page.evaluate("window.__groupBodies.at(-1).expected_revision") == 3
        page.wait_for_function(
            "Array.from(document.querySelectorAll('#literature-map-group-list [data-group-id]')).some("
            "(node) => (node.querySelector('.literature-map-group-name')?.textContent || '') === '证据分组')"
        )

        page.locator('[data-node-id="node-a"] circle').click()
        page.wait_for_selector('#literature-map-node-group')
        # 点画布属于「点外部」，浮层会收起；这里验证收起行为后重新展开再删除分组。
        page.wait_for_function("document.querySelector('#literature-map-groups-popover')?.hidden === true")
        assert fab.get_attribute('aria-expanded') == 'false'
        page.locator('#literature-map-node-group').select_option('group-fixture')
        page.wait_for_function("window.__nodeGroupBodies?.at(-1)?.group_id === 'group-fixture'")
        assert page.evaluate("window.__nodeGroupBodies.at(-1).expected_revision") >= 3
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('data-group-color') == '#3366cc'

        fab.click()
        popover.wait_for(state="visible")
        page.locator('#literature-map-groups-popover .literature-map-group-row[data-group-id="group-fixture"] .literature-map-group-delete').click()
        page.wait_for_function("!Array.from(document.querySelectorAll('#literature-map-group-list [data-group-id]')).some((node) => node.dataset.groupId === 'group-fixture')")
        # 删除分组后「未分组」项仍然存在（这是唯一允许保留的哨兵行）。
        assert page.locator('#literature-map-group-list .literature-map-group-row.is-ungrouped').count() == 1
        assert page.locator('[data-node-id="node-a"]').get_attribute('data-group-id') in (None, '')
        assert page.locator('[data-node-id="node-a"]').get_attribute('data-group-color') in (None, '')

        with page.expect_download() as json_download:
            page.locator('#literature-map-export-json').click()
        assert json_download.value.suggested_filename.endswith('.json')

        with page.expect_download() as png_download:
            page.locator('#literature-map-export-png').click()
        assert png_download.value.suggested_filename.endswith('.png')
        browser.close()
