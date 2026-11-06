"""多选模式控件：不再提供任何色板，节点颜色一律跟随所属分组。

背景：本文件原本守「点『应用到 N 篇』保存成功后多选色板自动收起 / 失败保持可见」。
Spec043 节点分组化改造后，节点级与多选级调色整条链路（色板 DOM、`applyNodeColor`、
`selectionPalette`、`selectionPaletteDismissed`、`PATCH /node-styles`）已删除，因此两个浏览器
用例改写为**反向契约断言**（用例数不减少、断言强度不降低）：

1. 进入多选模式并选中节点后，画布上不得出现 `[data-target="selection"]` 或 `[data-target="node"]`
   色板，节点颜色仍等于分组色；
2. 选中多篇后再点击节点调整选择，仍然没有任何色板出现，且不产生任何 `PATCH /node-styles`；
3. 唯一允许出现的色板是分组色板（`[data-target="group"]`），且它只存在于 FAB 浮层的分组行内。

纯状态机分支不再需要浏览器驱动，改由
`test_frontend_selection_palette_dismiss_on_apply.js` 在 `node:vm` 沙箱里**真实执行**
新的 `renderMultiSelectControls()` / `toggleMultiSelectMode()` / `toggleMultiSelectNode()` 覆盖。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"
MODULE = (ROOT / "frontend/literature-maps.js").read_text(encoding="utf-8")

SELECTION_PALETTE = '.literature-map-color-palette[data-target="selection"]'
NODE_PALETTE = '.literature-map-color-palette[data-target="node"]'
GROUP_PALETTE = '.literature-map-color-palette[data-target="group"]'


def _launch(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - host dependent
        pytest.skip(f"真实浏览器阻塞，未将静态检查冒充通过: {type(exc).__name__}: {exc}")


def _open_map_and_multi_select(page) -> None:
    page.set_default_timeout(5000)
    page.goto(f"{FIXTURE.as_uri()}?palette", wait_until="load")
    page.locator('[data-map-id="map-fixture"]').click()
    page.wait_for_selector('[data-node-id="node-a"] circle')
    page.locator("#literature-map-multi-select-toggle").click()
    page.locator('[data-node-id="node-a"] circle').click()
    page.wait_for_function("document.querySelector('#literature-map-selected-count')?.textContent === '已选 1 篇'")


def test_multi_select_palette_is_removed_from_the_canvas() -> None:
    """反向契约：多选模式不再有色板，选中节点颜色只跟随分组色。"""
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map_and_multi_select(page)
        page.wait_for_timeout(150)

        assert page.locator(SELECTION_PALETTE).count() == 0, "多选模式不得再渲染 data-target=\"selection\" 色板"
        assert page.locator(NODE_PALETTE).count() == 0, "多选模式不得再渲染 data-target=\"node\" 色板"
        # 唯一允许的色板是分组色板，而且只存在于 FAB 浮层的分组行内。
        assert page.locator(GROUP_PALETTE).count() == page.locator(
            '#literature-map-groups-popover .literature-map-group-row ' + GROUP_PALETTE
        ).count()
        assert page.locator("#literature-map-node-selection-toolbar").is_visible(), "多选工具条仍须可见"
        assert page.locator("#literature-map-selected-count").text_content() == "已选 1 篇"
        assert page.locator('[data-node-id="node-a"] circle').get_attribute("fill") == "#3366cc", (
            "多选选中的节点颜色必须等于分组色"
        )
        assert page.evaluate("window.__nodeStyleBodies.length") == 0, "多选不得产生 PATCH /node-styles 请求"
        browser.close()


def test_multi_select_never_requests_node_style_writes_while_adjusting_selection() -> None:
    """反向契约：反复调整选择、退出多选，都不会发出节点样式写请求或冒出任何色板。"""
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map_and_multi_select(page)

        page.locator('[data-node-id="node-b"] circle').click()
        page.wait_for_function("document.querySelector('#literature-map-selected-count')?.textContent === '已选 2 篇'")
        assert page.locator(SELECTION_PALETTE).count() == 0, "调整选择后仍不得出现多选色板"
        assert page.locator(NODE_PALETTE).count() == 0
        assert page.locator('[data-node-id="node-b"] circle').get_attribute("fill") == "#8d80e6", (
            "未分组节点必须使用默认色，而不是任何节点级 override"
        )

        page.locator('[data-node-id="node-a"] circle').click()
        page.wait_for_function("document.querySelector('#literature-map-selected-count')?.textContent === '已选 1 篇'")
        page.locator("#literature-map-multi-select-toggle").click()
        page.locator('[data-node-id="node-a"] circle').click()
        page.wait_for_selector("#literature-map-detail .literature-map-detail-title")

        assert page.locator(SELECTION_PALETTE).count() == 0
        assert page.locator("#literature-map-detail .literature-map-node-color-section").count() == 0, (
            "节点详情不得再渲染单独调色区"
        )
        assert page.evaluate("window.__nodeStyleBodies.length") == 0, "全程不得产生节点样式写请求"
        assert page.evaluate(
            "window.__requestLog.filter(entry => entry.method === 'PATCH'"
            " || entry.method === 'PUT' || entry.method === 'POST')"
            ".filter(entry => !entry.path.includes('/analysis-queue/ensure')).length"
        ) == 0, "调整多选选择不得产生任何业务写请求"
        browser.close()


def test_selection_palette_api_is_deleted_from_the_module() -> None:
    """源码级反向契约：多选/节点调色的实现入口已彻底删除，分组色链路仍在。"""
    for removed in ("applyNodeColor", "selectionPalette", "selectionPaletteDismissed", "data-target = 'selection'"):
        assert removed not in MODULE, f"frontend/literature-maps.js 不得再出现 {removed}"
    assert "nodeDisplayColor" in MODULE
    assert "currentGroupColor" in MODULE
    assert "createColorPalette" in MODULE
