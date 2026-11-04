"""Browser journeys for literature map colors, node fill and export appearance."""

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"


def _launch(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - host dependent
        pytest.skip(f"真实浏览器阻塞，未将静态检查冒充通过: {type(exc).__name__}: {exc}")


def _open_map(page, query="palette"):
    page.set_default_timeout(5000)
    page.goto(f"{FIXTURE.as_uri()}?{query}", wait_until="load")
    page.locator('[data-map-id="map-fixture"]').click()
    page.wait_for_selector('[data-node-id="node-a"] circle')
    page.wait_for_function("document.querySelector('#literature-map-current-title')?.textContent.includes('边缘学习地图')")


def test_node_palette_previews_presets_and_hex_then_applies_and_remembers_color() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page)
        page.locator('[data-node-id="node-a"] circle').click()
        palette = page.locator('.literature-map-color-palette[data-target="node"]')
        palette.wait_for(state="visible")

        assert palette.locator('.literature-map-color-swatch').count() == 12
        initial_fill = page.locator('[data-node-id="node-a"] circle').get_attribute('fill')
        palette.locator('.literature-map-color-swatch[data-color="#ff6b6b"]').click()
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#ff6b6b'
        assert page.evaluate("window.__nodeStyleBodies.length") == 0
        palette.locator('.literature-map-color-cancel').click()
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == initial_fill
        assert page.evaluate("localStorage.getItem('literature-map-recent-colors:owner-fixture')") is None

        palette.locator('.literature-map-color-hex').fill('#12AbEf')
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#12abef'
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__nodeStyleBodies.length === 1")
        assert page.evaluate("window.__nodeStyleBodies[0]") == {
            "expected_revision": 3,
            "node_ids": ["node-a"],
            "color_override": "#12abef",
        }
        assert "颜色已保存" in (page.locator('#literature-map-status').text_content() or "")
        assert page.evaluate("JSON.parse(localStorage.getItem('literature-map-recent-colors:owner-fixture'))") == ["#12abef"]
        browser.close()


def test_saved_node_override_is_previewed_and_reset_can_be_cancelled() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page)
        page.locator('[data-node-id="node-a"] circle').click()
        palette = page.locator('.literature-map-color-palette[data-target="node"]')
        palette.locator('.literature-map-color-hex').fill('#12abef')
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__nodeStyleBodies.length === 1")
        circle = page.locator('[data-node-id="node-a"] circle')
        assert circle.get_attribute('fill') == '#12abef'

        palette.locator('.literature-map-color-swatch[data-color="#ff6b6b"]').click()
        assert circle.get_attribute('fill') == '#ff6b6b'
        assert page.evaluate("window.__nodeStyleBodies.length") == 1
        palette.locator('.literature-map-color-cancel').click()
        assert circle.get_attribute('fill') == '#12abef'

        palette.locator('.literature-map-node-color-follow-group').click()
        assert circle.get_attribute('fill') == '#3366cc'
        assert page.evaluate("window.__nodeStyleBodies.length") == 1
        palette.locator('.literature-map-color-cancel').click()
        assert circle.get_attribute('fill') == '#12abef'

        palette.locator('.literature-map-node-color-follow-group').click()
        assert circle.get_attribute('fill') == '#3366cc'
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__nodeStyleBodies.length === 2")
        assert page.evaluate("window.__nodeStyleBodies[1].color_override") is None
        assert page.evaluate("window.__mockNodes.find(node => node.node_id === 'node-a').group_id") == 'group-fixture'
        browser.close()


def test_multi_select_applies_atomically_and_reset_follows_group_color() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page)
        page.locator('#literature-map-multi-select-toggle').click()
        page.locator('[data-node-id="node-a"] circle').click()
        page.locator('[data-node-id="node-b"] circle').click()
        assert page.locator('#literature-map-selected-count').text_content() == '已选 2 篇'

        palette = page.locator('.literature-map-color-palette[data-target="selection"]')
        palette.locator('.literature-map-color-swatch[data-color="#00c2a8"]').click()
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__nodeStyleBodies.length === 1")
        body = page.evaluate("window.__nodeStyleBodies[0]")
        assert body["expected_revision"] == 3
        assert set(body["node_ids"]) == {"node-a", "node-b"}
        assert body["color_override"] == "#00c2a8"
        assert page.evaluate("window.__mockNodes.filter(node => ['node-a', 'node-b'].includes(node.node_id)).map(node => node.group_id)") == ["group-fixture", None]

        page.locator('#literature-map-multi-select-toggle').click()
        page.locator('[data-node-id="node-a"] circle').click()
        page.locator('.literature-map-node-color-follow-group').click()
        page.locator('.literature-map-color-palette[data-target="node"] .literature-map-color-apply').click()
        page.wait_for_function("window.__nodeStyleBodies.length === 2")
        assert page.evaluate("window.__nodeStyleBodies[1].color_override") is None
        assert page.evaluate("window.__mockNodes.find(node => node.node_id === 'node-a').group_id") == "group-fixture"
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#3366cc'
        browser.close()


def test_group_palette_uses_shared_presets_and_preserves_node_override_priority() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-group-members")
        page.locator('[data-node-id="node-a"] circle').click()
        node_palette = page.locator('.literature-map-color-palette[data-target="node"]')
        node_palette.locator('.literature-map-color-hex').fill('#12abef')
        node_palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__nodeStyleBodies.length === 1")

        page.locator('[data-group-id="group-fixture"] .literature-map-group-color-trigger').click()
        group_palette = page.locator('.literature-map-color-palette[data-target="group"]')
        assert group_palette.locator('.literature-map-color-swatches .literature-map-color-swatch').count() == 12
        group_palette.locator('.literature-map-color-hex').fill('#f6bd60')
        assert page.locator('[data-node-id="node-b"] circle').get_attribute('fill') == '#f6bd60'
        assert page.evaluate("window.__groupBodies.length") == 0
        group_palette.locator('.literature-map-color-cancel').click()
        assert page.locator('[data-node-id="node-b"] circle').get_attribute('fill') == '#3366cc'

        page.locator('[data-group-id="group-fixture"] .literature-map-group-color-trigger').click()
        group_palette = page.locator('.literature-map-color-palette[data-target="group"]')
        group_palette.locator('.literature-map-color-hex').fill('#f6bd60')
        group_palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__groupBodies.some(body => body.color === '#f6bd60')")

        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#12abef'
        assert page.locator('[data-node-id="node-b"] circle').get_attribute('fill') == '#f6bd60'
        assert page.evaluate("window.__mockNodes.find(node => node.node_id === 'node-a').group_id") == "group-fixture"
        browser.close()


def test_lost_group_color_response_is_verified_and_keeps_or_clears_draft_by_result() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-group-timeout-before-save")
        page.locator('[data-group-id="group-fixture"] .literature-map-group-color-trigger').click()
        palette = page.locator('.literature-map-color-palette[data-target="group"]')
        palette.locator('.literature-map-color-hex').fill('#f6bd60')
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("document.querySelector('#literature-map-status')?.textContent.includes('草稿仍保留')")

        assert palette.locator('.literature-map-color-hex').input_value() == '#f6bd60'
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#f6bd60'
        assert page.evaluate("window.__groupBodies.length") == 1
        assert page.evaluate("window.__requestLog.some((entry, index, all) => entry.method === 'GET' && entry.path.endsWith('/groups') && index > all.findIndex(item => item.method === 'PATCH' && item.path.endsWith('/groups/group-fixture')))")

        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__groupBodies.length === 2")
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#f6bd60'
        browser.close()


def test_group_color_lost_response_is_confirmed_before_recent_color_is_saved() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-group-timeout-after-save")
        page.locator('[data-group-id="group-fixture"] .literature-map-group-color-trigger').click()
        palette = page.locator('.literature-map-color-palette[data-target="group"]')
        palette.locator('.literature-map-color-hex').fill('#f6bd60')
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("document.querySelector('#literature-map-status')?.textContent.includes('重新读取核实')")

        assert page.evaluate("window.__groupBodies.length") == 1
        assert page.evaluate("window.__mockGroups.find(group => group.group_id === 'group-fixture').color") == '#f6bd60'
        assert page.evaluate("JSON.parse(localStorage.getItem('literature-map-recent-colors:owner-fixture'))") == ['#f6bd60']
        browser.close()


def test_delayed_group_color_success_remembers_original_owner_only() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-owners&palette-delay-group-save")
        page.locator('[data-group-id="group-fixture"] .literature-map-group-color-trigger').click()
        palette = page.locator('.literature-map-color-palette[data-target="group"]')
        palette.locator('.literature-map-color-hex').fill('#f6bd60')
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__requestLog.some(entry => entry.method === 'PATCH' && entry.path.endsWith('/groups/group-fixture'))")
        page.locator('[data-map-id="map-fixture-b"]').click()
        page.wait_for_function("document.querySelector('#literature-map-current-title')?.textContent.includes('第二张地图')")
        page.wait_for_function("localStorage.getItem('literature-map-recent-colors:owner-fixture') !== null")

        assert page.evaluate("JSON.parse(localStorage.getItem('literature-map-recent-colors:owner-fixture'))") == ['#f6bd60']
        assert page.evaluate("localStorage.getItem('literature-map-recent-colors:owner-fixture-b')") is None
        assert page.locator('#literature-map-current-title').text_content() == '第二张地图'
        browser.close()


def test_color_revision_conflict_keeps_draft_until_user_reapplies() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-conflict")
        page.locator('[data-node-id="node-a"] circle').click()
        palette = page.locator('.literature-map-color-palette[data-target="node"]')
        palette.locator('.literature-map-color-hex').fill('#b8de6f')
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__nodeStyleBodies.length === 1")
        page.wait_for_function("document.querySelector('#literature-map-status')?.textContent.includes('草稿仍保留')")

        assert palette.locator('.literature-map-color-hex').input_value() == '#b8de6f'
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#b8de6f'
        assert page.evaluate("window.__nodeStyleBodies.length") == 1
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__nodeStyleBodies.length === 2")
        assert page.evaluate("window.__nodeStyleBodies[1].expected_revision") > page.evaluate("window.__nodeStyleBodies[0].expected_revision")
        browser.close()


def test_lost_color_response_is_verified_by_reading_graph_before_reporting_success() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-timeout-after-save&usable-saved-view")
        page.locator('[data-node-id="node-a"] circle').click()
        palette = page.locator('.literature-map-color-palette[data-target="node"]')
        palette.locator('.literature-map-color-hex').fill('#f6bd60')
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("document.querySelector('#literature-map-status')?.textContent.includes('颜色已保存')")

        assert page.evaluate("window.__nodeStyleBodies.length") == 1
        assert page.evaluate("window.__mockNodes.find(node => node.node_id === 'node-a').color_override") == '#f6bd60'
        assert page.evaluate("window.__requestLog.some((entry, index, all) => entry.method === 'GET' && entry.path.endsWith('/graph') && index > all.findIndex(item => item.path.endsWith('/node-styles')))")
        assert page.evaluate("JSON.parse(localStorage.getItem('literature-map-recent-colors:owner-fixture'))") == ["#f6bd60"]
        browser.close()


def test_late_timeout_verification_does_not_replace_a_newly_selected_map() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-owners&palette-timeout-after-save&palette-delay-verification")
        page.locator('[data-node-id="node-a"] circle').click()
        palette = page.locator('.literature-map-color-palette[data-target="node"]')
        palette.locator('.literature-map-color-hex').fill('#f6bd60')
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__requestLog.some(entry => entry.path.endsWith('/node-styles'))")
        page.wait_for_function("window.__requestLog.some((entry, index, all) => entry.method === 'GET' && entry.path.endsWith('/graph') && index > all.findIndex(item => item.path.endsWith('/node-styles')))")

        page.locator('[data-map-id="map-fixture-b"]').click()
        page.wait_for_function("document.querySelector('#literature-map-current-title')?.textContent.includes('第二张地图')")
        page.wait_for_timeout(400)

        assert page.locator('#literature-map-current-title').text_content() == '第二张地图'
        assert page.locator('#literature-map-status').text_content() != '颜色已保存（已重新读取核实）。'
        assert page.evaluate("localStorage.getItem('literature-map-recent-colors:owner-fixture')") is None
        browser.close()


def test_recent_colors_are_scoped_by_map_owner() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-owners&usable-saved-view")
        page.locator('[data-node-id="node-a"] circle').click()
        palette = page.locator('.literature-map-color-palette[data-target="node"]')
        palette.locator('.literature-map-color-hex').fill('#12abef')
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__nodeStyleBodies.length === 1")

        page.locator('[data-map-id="map-fixture-b"]').click()
        page.wait_for_selector('[data-node-id="node-a"] circle')
        page.locator('[data-node-id="node-a"] circle').click()
        other_palette = page.locator('.literature-map-color-palette[data-target="node"]')
        assert other_palette.locator('.literature-map-color-recent[data-color="#12abef"]').count() == 0

        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector('[data-node-id="node-a"] circle')
        page.locator('[data-node-id="node-a"] circle').click()
        palette = page.locator('.literature-map-color-palette[data-target="node"]')
        assert palette.locator('.literature-map-color-recent[data-color="#12abef"]').count() == 1
        browser.close()


def test_delayed_success_remembers_color_for_the_original_owner_only() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-owners&palette-delay-color-save")
        page.locator('[data-node-id="node-a"] circle').click()
        palette = page.locator('.literature-map-color-palette[data-target="node"]')
        palette.locator('.literature-map-color-hex').fill('#12abef')
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__requestLog.some(entry => entry.path.endsWith('/node-styles'))")
        page.locator('[data-map-id="map-fixture-b"]').click()
        page.wait_for_function("document.querySelector('#literature-map-current-title')?.textContent.includes('第二张地图')")
        page.wait_for_timeout(400)

        assert page.evaluate("JSON.parse(localStorage.getItem('literature-map-recent-colors:owner-fixture'))") == ['#12abef']
        assert page.evaluate("localStorage.getItem('literature-map-recent-colors:owner-fixture-b')") is None
        browser.close()


def test_recent_colors_are_deduplicated_and_limited_to_eight_applied_colors() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page)
        page.locator('[data-node-id="node-a"] circle').click()
        palette = page.locator('.literature-map-color-palette[data-target="node"]')
        colors = [f'#1000{index:02x}' for index in range(1, 10)]
        colors.append(colors[0])
        for index, color in enumerate(colors, start=1):
            palette.locator('.literature-map-color-hex').fill(color)
            palette.locator('.literature-map-color-apply').click()
            page.wait_for_function(f"window.__nodeStyleBodies.length === {index}")

        recent = page.evaluate("JSON.parse(localStorage.getItem('literature-map-recent-colors:owner-fixture'))")
        assert recent == [colors[0], *reversed(colors[2:9])]
        assert len(recent) == 8
        browser.close()


def test_style_preview_does_not_write_until_apply_and_png_uses_saved_outline_style() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&usable-saved-view")
        page.locator('[data-node-id="node-a"] circle').click()
        # 节点样式浮层默认折叠（用户要求点击后才弹出），这里显式展开后再调外观。
        style_disclosure = page.locator('.literature-map-node-style-disclosure')
        assert style_disclosure.get_attribute('open') is None
        style_disclosure.locator('summary').click()
        style = page.locator('#literature-map-node-style')
        style.wait_for(state="visible")
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill-opacity') == '0.3'
        style.locator('input[name="fill_mode"][value="outline"]').check()
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill-opacity') == '0'
        style.locator('input[name="fill_opacity"]').evaluate("input => { input.value = '0.65'; input.dispatchEvent(new Event('input', { bubbles: true })); }")
        circle = page.locator('[data-node-id="node-a"] circle')
        assert circle.get_attribute('fill') in ('none', 'transparent')
        assert circle.get_attribute('fill-opacity') == '0'
        assert page.evaluate("window.__viewBodies.length") == 0

        style.locator('.literature-map-node-style-apply').click()
        page.wait_for_function("window.__viewBodies.length === 1")
        body = page.evaluate("window.__viewBodies[0]")
        assert body["node_style"] == {"fill_mode": "outline", "fill_opacity": 0.65}
        assert "positions" not in body and "viewport" not in body

        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_function("document.querySelector('#literature-map-current-title')?.textContent.includes('边缘学习地图')")
        assert style.locator('input[name="fill_mode"][value="outline"]').is_checked()
        assert style.locator('input[name="fill_opacity"]').input_value() == '0.65'
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') in ('none', 'transparent')

        with page.expect_download() as download:
            page.locator('#literature-map-export-png').click()
        assert download.value.suggested_filename.endswith('.png')
        png_path = download.value.path()
        assert png_path and Path(png_path).stat().st_size > 0
        exported = page.evaluate("window.__serializedExportSvg")
        assert 'fill="none"' in exported
        assert 'fill-opacity="0"' in exported

        with page.expect_download() as json_download:
            page.locator('#literature-map-export-json').click()
        assert json_download.value.suggested_filename.endswith('.json')
        json_payload = json_download.value.path()
        assert json_payload
        exported_json = Path(json_payload).read_text(encoding='utf-8')
        assert 'literature-map-export-v2' in exported_json
        assert '"node_style": {' in exported_json and '"fill_mode": "outline"' in exported_json
        assert '"color_override": null' in exported_json
        assert 'owner_id' not in exported_json and 'recent_colors' not in exported_json and 'preview' not in exported_json
        browser.close()


def test_json_export_preserves_saved_node_override_and_default_style() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&usable-saved-view")
        page.locator('[data-node-id="node-a"] circle').click()
        palette = page.locator('.literature-map-color-palette[data-target="node"]')
        palette.locator('.literature-map-color-hex').fill('#12abef')
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__nodeStyleBodies.length === 1")

        with page.expect_download() as json_download:
            page.locator('#literature-map-export-json').click()
        export_path = json_download.value.path()
        assert export_path
        exported = Path(export_path).read_text(encoding='utf-8')
        assert '"color_override": "#12abef"' in exported
        assert '"node_style": {' in exported and '"fill_mode": "filled"' in exported and '"fill_opacity": 0.3' in exported
        assert 'owner_id' not in exported and 'recent_colors' not in exported and 'preview' not in exported
        browser.close()


def test_exports_are_blocked_while_color_or_style_preview_is_unapplied() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&usable-saved-view")
        page.locator('[data-node-id="node-a"] circle').click()
        palette = page.locator('.literature-map-color-palette[data-target="node"]')
        palette.locator('.literature-map-color-swatch[data-color="#ff6b6b"]').click()
        page.locator('#literature-map-export-json').click()
        page.wait_for_function("document.querySelector('#literature-map-status')?.textContent.includes('取消预览')")
        assert page.evaluate("window.__requestLog.some(entry => entry.path.includes('/export?format=json'))") is False
        palette.locator('.literature-map-color-cancel').click()

        # 节点样式浮层默认折叠（用户要求点击后才弹出），这里显式展开后再改外观。
        style_disclosure = page.locator('.literature-map-node-style-disclosure')
        assert style_disclosure.get_attribute('open') is None
        style_disclosure.locator('summary').click()
        style = page.locator('#literature-map-node-style')
        style.wait_for(state="visible")
        style.locator('input[name="fill_mode"][value="outline"]').check()
        page.locator('#literature-map-export-png').click()
        page.wait_for_function("document.querySelector('#literature-map-status')?.textContent.includes('取消预览')")
        assert page.evaluate("window.__serializedExportSvg || null") is None
        assert page.evaluate("window.__viewBodies.length") == 0
        browser.close()
