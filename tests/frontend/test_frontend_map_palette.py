"""Browser journeys for literature map group colors, node fill and export appearance.

Spec043 起，论文节点不再支持单独调色（节点颜色一律跟随所属分组），多选模式也不再提供
色板；分组改色的唯一入口是画布左下角的 FAB（`#literature-map-groups-fab`）展开的浮层
（`#literature-map-groups-popover`）内的 `.literature-map-group-row[data-group-id]`。

因此本文件里的用例分两类：
1. 已删除能力的用例改写为**反向契约断言**（节点详情没有调色区、多选没有 selection 色板、
   不产生任何 `PATCH /node-styles`、源码里没有 `applyNodeColor`/`updateGraphColorOverrides`、
   节点 `circle` 的 `fill` 只取分组色，即使 fixture 给了 `color_override` 也忽略）；
2. 仍然保留的「分组改色 / recent colors / 丢失响应复核 / 409 冲突 / 视图级 fill_mode /
   JSON 导出 / 导出拦截」用例**迁移到 FAB 新入口**，能力断言强度不降低。
"""

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"
MODULE = (ROOT / "frontend/literature-maps.js").read_text(encoding="utf-8")

GROUP_PALETTE = '.literature-map-color-palette[data-target="group"]'
NODE_PALETTE = '.literature-map-color-palette[data-target="node"]'
SELECTION_PALETTE = '.literature-map-color-palette[data-target="selection"]'


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


def _open_groups_popover(page):
    """通过画布左下角 FAB 展开分组浮层（唯一入口）。"""
    fab = page.locator('#literature-map-groups-fab')
    fab.wait_for(state="visible")
    if fab.get_attribute('aria-expanded') != 'true':
        fab.click()
    popover = page.locator('#literature-map-groups-popover')
    popover.wait_for(state="visible")
    assert fab.get_attribute('aria-expanded') == 'true'
    return popover


def _open_group_palette(page, group_id="group-fixture"):
    """展开浮层并点开该组的「改色」按钮，返回该行内的分组色板 locator。

    色块（`.literature-map-group-color-trigger`）自 Spec043 起只负责**高亮**，
    改色入口是独立的 `.literature-map-group-color-open`，两者不得混用。
    """
    popover = _open_groups_popover(page)
    row = popover.locator(f'.literature-map-group-row[data-group-id="{group_id}"]')
    row.wait_for(state="visible")
    row.locator('.literature-map-group-color-open').click()
    # renderGroups() 会重建整行，旧的 locator 句柄会失效；重新定位并等待色板可见。
    palette = page.locator(
        f'.literature-map-group-row[data-group-id="{group_id}"] {GROUP_PALETTE}'
    )
    palette.wait_for(state="visible")
    return palette


def _apply_group_color(page, color, group_id="group-fixture"):
    palette = _open_group_palette(page, group_id)
    palette.locator('.literature-map-color-hex').fill(color)
    palette.locator('.literature-map-color-apply').click()
    page.wait_for_function(
        f"window.__groupBodies.some(body => body.color === {color!r})",
    )
    return palette


def test_node_level_color_api_is_removed_from_the_module() -> None:
    """反向契约（源码级）：节点级调色 API 必须彻底删除，只剩 group-only 实现。"""
    for removed in ('applyNodeColor', 'updateGraphColorOverrides', 'renderNodeColorControls'):
        assert MODULE.count(removed) == 0, f'frontend/literature-maps.js 不得再出现 {removed}'
    assert 'nodeColorDraft' not in MODULE
    assert "data-target = 'node'" not in MODULE
    assert "target: 'selection'" not in MODULE
    # 仍然保留的能力入口。
    assert 'function createColorPalette(groupId' in MODULE
    assert 'function applyGroupColor(' in MODULE
    assert "palette.dataset.target = 'group'" in MODULE
    assert 'function nodeDisplayColor(node)' in MODULE
    assert 'return currentGroupColor(node?.group_id);' in MODULE


def test_node_palette_is_gone_and_nodes_only_follow_their_group_color() -> None:
    """反向契约：节点详情不再有单独调色区，节点颜色只取分组色，且不产生任何写库请求。"""
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page)
        page.locator('[data-node-id="node-a"] circle').click()
        page.wait_for_selector('#literature-map-detail .literature-map-detail-title')
        # node-a 属于 group-fixture(#3366cc)，node-b 未分组 → 默认色。
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#3366cc'
        assert page.locator('[data-node-id="node-b"] circle').get_attribute('fill') == '#8d80e6'

        detail = page.locator('#literature-map-detail')
        assert detail.locator('.literature-map-node-color-section').count() == 0, '节点详情不得再渲染单独调色区'
        assert detail.locator(NODE_PALETTE).count() == 0, '节点详情不得再渲染节点级色板'
        assert detail.locator('.literature-map-node-color-follow-group').count() == 0, '「恢复跟随分组」按钮随节点调色一起删除'
        # 仍保留的能力：切换所属分组。
        assert detail.locator('#literature-map-node-group').count() == 1

        assert page.locator(NODE_PALETTE).count() == 0
        assert page.locator(SELECTION_PALETTE).count() == 0
        assert page.evaluate("window.__nodeStyleBodies.length") == 0, '不得产生任何 PATCH /node-styles 请求'
        assert page.evaluate(
            "window.__requestLog.filter(entry => entry.method !== 'GET'"
            " && !entry.path.includes('/analysis-queue/ensure')).length"
        ) == 0, '仅点击节点不得产生任何写请求（analysis-queue/ensure 是夹具基线请求）'
        assert page.evaluate("localStorage.getItem('literature-map-recent-colors:owner-fixture')") is None
        browser.close()


def test_saved_node_color_override_is_ignored_by_the_graph_renderer() -> None:
    """反向契约：即使数据里残留 color_override，渲染也只认分组色、不写库。"""
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page)
        page.evaluate(
            "(color) => { window.__mockNodes.forEach((node) => { node.color_override = color; }); }",
            '#ff6b6b',
        )
        page.locator('#literature-map-refresh-button').click()
        page.wait_for_function(
            "window.__mockNodes.every(node => node.color_override === '#ff6b6b')"
        )
        page.wait_for_selector('[data-node-id="node-b"] circle')

        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#3366cc', (
            '分组内节点的 fill 必须等于分组色，忽略残留的 color_override'
        )
        assert page.locator('[data-node-id="node-b"] circle').get_attribute('fill') != '#ff6b6b', (
            '未分组节点必须回到默认色，忽略残留的 color_override'
        )
        assert page.locator(NODE_PALETTE).count() == 0
        assert page.evaluate("window.__nodeStyleBodies.length") == 0
        assert page.evaluate(
            "window.__requestLog.filter(entry => entry.path.includes('/node-styles')).length"
        ) == 0, '刷新图谱不得产生 node-styles 写请求'
        browser.close()


def test_multi_select_has_no_palette_and_only_keeps_selection_count() -> None:
    """反向契约：多选模式不再有色板，选中的节点颜色仍只跟随分组。"""
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page)
        page.locator('#literature-map-multi-select-toggle').click()
        page.locator('[data-node-id="node-a"] circle').click()
        page.locator('[data-node-id="node-b"] circle').click()
        assert page.locator('#literature-map-selected-count').text_content() == '已选 2 篇'
        assert page.locator('#literature-map-node-selection-toolbar').is_visible(), '多选工具条仍须可见'

        assert page.locator(SELECTION_PALETTE).count() == 0, '多选模式不得再渲染 data-target="selection" 色板'
        assert page.locator(NODE_PALETTE).count() == 0
        assert page.locator('.literature-map-color-palette').count() == page.evaluate(
            "document.querySelectorAll('.literature-map-color-palette[data-target=\"group\"]').length"
        ), '画布上残留的色板必须全部是分组色板'
        assert page.evaluate("window.__nodeStyleBodies.length") == 0, '多选不得产生 PATCH /node-styles 请求'
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#3366cc'
        assert page.locator('[data-node-id="node-b"] circle').get_attribute('fill') == '#8d80e6'

        # 退出多选后节点详情仍可用，但没有节点调色区。
        page.locator('#literature-map-multi-select-toggle').click()
        page.locator('[data-node-id="node-a"] circle').click()
        page.wait_for_selector('#literature-map-detail .literature-map-detail-title')
        assert page.locator('#literature-map-detail .literature-map-node-color-section').count() == 0
        browser.close()


def test_group_palette_uses_shared_presets_and_overrides_node_color_fields() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-group-members")
        # 组内节点即便残留 color_override，也必须跟随分组色（旧的节点级 override 优先级已删除）。
        page.evaluate(
            "(color) => { const node = window.__mockNodes.find((item) => item.node_id === 'node-a'); node.color_override = color; }",
            '#12abef',
        )
        page.locator('#literature-map-refresh-button').click()
        page.wait_for_selector('[data-node-id="node-a"] circle')
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#3366cc'

        palette = _open_group_palette(page)
        assert palette.locator('.literature-map-color-swatches .literature-map-color-swatch').count() == 12
        palette.locator('.literature-map-color-hex').fill('#f6bd60')
        assert page.locator('[data-node-id="node-b"] circle').get_attribute('fill') == '#f6bd60'
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#f6bd60'
        assert page.evaluate("window.__groupBodies.length") == 0
        palette.locator('.literature-map-color-cancel').click()
        assert page.locator('[data-node-id="node-b"] circle').get_attribute('fill') == '#3366cc'
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#3366cc'

        _apply_group_color(page, '#f6bd60')
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#f6bd60'
        assert page.locator('[data-node-id="node-b"] circle').get_attribute('fill') == '#f6bd60'
        assert page.evaluate("window.__mockNodes.find(node => node.node_id === 'node-a').group_id") == "group-fixture"
        assert page.evaluate("window.__mockGroups.find(group => group.group_id === 'group-fixture').color") == '#f6bd60'
        browser.close()


def test_lost_group_color_response_is_verified_and_keeps_or_clears_draft_by_result() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-group-timeout-before-save")
        palette = _open_group_palette(page)
        palette.locator('.literature-map-color-hex').fill('#f6bd60')
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("document.querySelector('#literature-map-status')?.textContent.includes('草稿仍保留')")

        assert page.locator(f'{GROUP_PALETTE} .literature-map-color-hex').input_value() == '#f6bd60'
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#f6bd60'
        assert page.evaluate("window.__groupBodies.length") == 1
        assert page.evaluate("window.__requestLog.some((entry, index, all) => entry.method === 'GET' && entry.path.endsWith('/groups') && index > all.findIndex(item => item.method === 'PATCH' && item.path.endsWith('/groups/group-fixture')))")

        page.locator(f'{GROUP_PALETTE} .literature-map-color-apply').click()
        page.wait_for_function("window.__groupBodies.length === 2")
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#f6bd60'
        browser.close()


def test_group_color_lost_response_is_confirmed_before_recent_color_is_saved() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-group-timeout-after-save")
        palette = _open_group_palette(page)
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
        palette = _open_group_palette(page)
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


def test_group_color_revision_conflict_keeps_draft_until_user_reapplies() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-conflict")
        # 收集状态变化历史，避免因后续操作覆盖文本内容导致超时。
        page.evaluate("""() => {
          window.__statusHistory = [];
          const el = document.querySelector('#literature-map-status');
          if (el) {
            window.__statusHistory.push(el.textContent);
            new MutationObserver(() => window.__statusHistory.push(el.textContent))
              .observe(el, { childList: true, subtree: true, characterData: true });
          }
        }""")
        palette = _open_group_palette(page)
        palette.locator('.literature-map-color-hex').fill('#b8de6f')
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__groupBodies.length === 1")
        page.wait_for_function("window.__statusHistory.some(text => (text || '').includes('地图版本已变化'))")

        # 409 会触发重新读图；浮层与草稿都必须保留，用户可直接重试。
        page.wait_for_function("document.querySelector('#literature-map-groups-popover')?.hidden === false")
        assert page.locator(f'{GROUP_PALETTE} .literature-map-color-hex').input_value() == '#b8de6f'
        assert page.evaluate("window.__groupBodies.length") == 1
        page.locator(f'{GROUP_PALETTE} .literature-map-color-apply').click()
        page.wait_for_function("window.__groupBodies.length === 2")
        assert page.evaluate("window.__groupBodies[1].expected_revision") > page.evaluate("window.__groupBodies[0].expected_revision")
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#b8de6f'
        browser.close()


def test_lost_color_response_is_verified_by_reading_groups_before_reporting_success() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-group-timeout-after-save&usable-saved-view")
        palette = _open_group_palette(page)
        palette.locator('.literature-map-color-hex').fill('#f6bd60')
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("document.querySelector('#literature-map-status')?.textContent.includes('分组颜色已保存')")

        assert page.evaluate("window.__groupBodies.length") == 1
        assert page.evaluate("window.__mockGroups.find(group => group.group_id === 'group-fixture').color") == '#f6bd60'
        assert page.evaluate("window.__requestLog.some((entry, index, all) => entry.method === 'GET' && entry.path.endsWith('/groups') && index > all.findIndex(item => item.path.endsWith('/groups/group-fixture') && item.method === 'PATCH'))")
        assert page.evaluate("JSON.parse(localStorage.getItem('literature-map-recent-colors:owner-fixture'))") == ['#f6bd60']
        browser.close()


def test_late_group_color_timeout_verification_does_not_replace_a_newly_selected_map() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-owners&palette-group-timeout-after-save")
        palette = _open_group_palette(page)
        palette.locator('.literature-map-color-hex').fill('#f6bd60')
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__requestLog.some(entry => entry.method === 'PATCH' && entry.path.endsWith('/groups/group-fixture'))")

        page.locator('[data-map-id="map-fixture-b"]').click()
        page.wait_for_function("document.querySelector('#literature-map-current-title')?.textContent.includes('第二张地图')")
        page.wait_for_timeout(400)

        assert page.locator('#literature-map-current-title').text_content() == '第二张地图'
        assert page.locator('#literature-map-status').text_content() != '分组颜色已保存（已重新读取核实）。'
        browser.close()


def test_recent_colors_are_scoped_by_map_owner() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-owners&usable-saved-view")
        _apply_group_color(page, '#12abef')

        page.locator('[data-map-id="map-fixture-b"]').click()
        page.wait_for_selector('[data-node-id="node-a"] circle')
        page.wait_for_function("document.querySelector('#literature-map-current-title')?.textContent.includes('第二张地图')")
        other_palette = _open_group_palette(page)
        assert other_palette.locator('.literature-map-color-recent[data-color="#12abef"]').count() == 0, (
            '另一张地图的最近颜色必须相互隔离'
        )

        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_selector('[data-node-id="node-a"] circle')
        page.wait_for_function("document.querySelector('#literature-map-current-title')?.textContent.includes('边缘学习地图')")
        palette = _open_group_palette(page)
        assert palette.locator('.literature-map-color-recent[data-color="#12abef"]').count() == 1
        browser.close()


def test_delayed_group_color_success_remembers_color_for_the_original_owner_only() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&palette-owners&palette-delay-group-save")
        palette = _open_group_palette(page)
        palette.locator('.literature-map-color-hex').fill('#12abef')
        palette.locator('.literature-map-color-apply').click()
        page.wait_for_function("window.__requestLog.some(entry => entry.method === 'PATCH' && entry.path.endsWith('/groups/group-fixture'))")
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
        colors = [f'#1000{index:02x}' for index in range(1, 10)]
        colors.append(colors[0])
        palette = _open_group_palette(page)
        for index, color in enumerate(colors, start=1):
            palette.locator('.literature-map-color-hex').fill(color)
            palette.locator('.literature-map-color-apply').click()
            page.wait_for_function(f"window.__groupBodies.length === {index}")
            # 每次保存后浮层与色板保持展开，草稿被清空；重新点开色块继续下一次。
            if not palette.is_visible():
                palette = _open_group_palette(page)

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


def test_json_export_preserves_saved_node_override_field_and_default_style() -> None:
    """还保留的能力：导出 JSON 仍原样带出节点上的 color_override 字段（非空时照抄）。

    节点级调色入口已删除，但导出契约不变：只要数据里存在 `color_override`，导出必须
    原样带出，不得被视图层的「颜色跟随分组」规则悄悄抹掉。
    """
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&usable-saved-view")
        page.evaluate(
            "(color) => { const node = window.__mockNodes.find((item) => item.node_id === 'node-a'); node.color_override = color; }",
            '#12abef',
        )
        page.locator('#literature-map-refresh-button').click()
        page.wait_for_selector('[data-node-id="node-a"] circle')
        # 视图层忽略 override（颜色仍跟分组），但导出必须保留原字段。
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#3366cc'
        assert page.evaluate("window.__nodeStyleBodies.length") == 0

        with page.expect_download() as json_download:
            page.locator('#literature-map-export-json').click()
        export_path = json_download.value.path()
        assert export_path
        exported = Path(export_path).read_text(encoding='utf-8')
        assert '"color_override": "#12abef"' in exported
        assert '"node_style": {' in exported and '"fill_mode": "filled"' in exported and '"fill_opacity": 0.3' in exported
        assert 'owner_id' not in exported and 'recent_colors' not in exported and 'preview' not in exported
        browser.close()


def test_exports_are_blocked_while_group_color_or_style_preview_is_unapplied() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page, "palette&usable-saved-view")
        palette = _open_group_palette(page)
        palette.locator('.literature-map-color-swatch[data-color="#ff6b6b"]').click()
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#ff6b6b', (
            '分组色草稿必须先实时预览到节点上'
        )
        page.locator('#literature-map-export-json').click()
        page.wait_for_function("document.querySelector('#literature-map-status')?.textContent.includes('取消预览')")
        assert page.evaluate("window.__requestLog.some(entry => entry.path.includes('/export?format=json'))") is False
        # 点导出按钮会被「点浮层外部即收起」的 capture 监听关掉浮层；重新展开后色板与草稿仍在。
        page.locator('#literature-map-groups-fab').click()
        page.wait_for_function("!document.querySelector('#literature-map-groups-popover')?.hidden")
        palette = page.locator(
            '.literature-map-group-row[data-group-id="group-fixture"] .literature-map-color-palette[data-target="group"]'
        )
        palette.wait_for(state="visible")
        palette.locator('.literature-map-color-cancel').click()
        assert page.locator('[data-node-id="node-a"] circle').get_attribute('fill') == '#3366cc'

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
