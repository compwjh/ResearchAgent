"""多选模式颜色面板的用户可见行为：保存成功后收起，失败保持可见，再次选节点重新出现。

背景（真实浏览器人工验收发现的缺陷）：进入多选模式选中节点后，颜色面板
`.literature-map-color-palette[data-target="selection"]` 会出现在画布上；点「应用到 N 篇」
后端已保存成功，但面板仍挡住刚上好色的节点，用户必须手动退出多选才能继续看图。

期望的用户可见结果：
1. 保存成功后面板不可见（不是仅改了内部状态），且多选模式与已选论文保持不变；
2. 保存失败（409 冲突）时面板必须保持可见，用户能直接重试；
3. 用户再次点击节点调整选择时，面板必须重新出现——收起不等于永久关闭。

纯状态机分支（含「已重新读取核实」成功分支）由
`test_frontend_selection_palette_dismiss_on_apply.js` 在 `node:vm` 沙箱里执行真实实现覆盖。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"

SELECTION_PALETTE = '.literature-map-color-palette[data-target="selection"]'
STATUS = "#literature-map-status"


def _launch(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - host dependent
        pytest.skip(f"真实浏览器阻塞，未将静态检查冒充通过: {type(exc).__name__}: {exc}")


def _open_map_and_select(page, query: str = "palette") -> None:
    page.set_default_timeout(5000)
    page.goto(f"{FIXTURE.as_uri()}?{query}", wait_until="load")
    page.locator('[data-map-id="map-fixture"]').click()
    page.wait_for_selector('[data-node-id="node-a"] circle')
    page.locator("#literature-map-multi-select-toggle").click()
    page.locator('[data-node-id="node-a"] circle').click()
    page.locator(SELECTION_PALETTE).wait_for(state="visible")


def test_selection_palette_hides_after_apply_and_reappears_on_reselecting_a_node() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map_and_select(page)
        palette = page.locator(SELECTION_PALETTE)
        assert palette.locator(".literature-map-color-apply").text_content() == "应用到 1 篇"

        palette.locator(".literature-map-color-hex").fill("#12abef")
        palette.locator(".literature-map-color-apply").click()
        page.wait_for_function("window.__nodeStyleBodies.length === 1")
        page.wait_for_timeout(150)

        assert palette.is_hidden(), "「应用到 N 篇」保存成功后颜色设置面板必须收起（不得继续挡住画布）"
        status = page.locator(STATUS).text_content() or ""
        assert "颜色已保存，设置面板已收起。" in status, f"保存成功后必须说明面板已收起，实际：{status!r}"
        assert page.locator("#literature-map-multi-select-toggle").text_content() == "退出多选模式", (
            "收起面板不得顺带退出多选模式"
        )
        assert page.locator("#literature-map-selected-count").text_content() == "已选 1 篇", (
            "收起面板不得清空已选论文"
        )
        assert page.locator('[data-node-id="node-a"] circle').get_attribute("fill") == "#12abef", (
            "收起面板不得影响刚保存的颜色"
        )

        # 再次点击节点调整选择 → 面板重新出现，用户能继续上色。
        page.locator('[data-node-id="node-b"] circle').click()
        page.wait_for_function(
            "(selector) => { const el = document.querySelector(selector);"
            " return el && !el.hidden && el.getBoundingClientRect().width > 0; }",
            arg=SELECTION_PALETTE,
        )
        assert palette.is_visible(), "用户再次点节点调整选择后，颜色设置面板必须重新出现"
        assert palette.locator(".literature-map-color-apply").text_content() == "应用到 2 篇"
        browser.close()


def test_selection_palette_stays_visible_when_save_conflicts_so_user_can_retry() -> None:
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map_and_select(page, "palette&palette-conflict")
        palette = page.locator(SELECTION_PALETTE)

        palette.locator(".literature-map-color-hex").fill("#f6bd60")
        palette.locator(".literature-map-color-apply").click()
        page.wait_for_function("window.__nodeStyleBodies.length === 1")
        page.wait_for_function(
            "document.querySelector('#literature-map-status')?.textContent.includes('草稿仍保留')"
        )

        assert palette.is_visible(), "409 冲突属非成功路径，颜色设置面板必须保持可见以便重试"
        assert palette.locator(".literature-map-color-hex").input_value() == "#f6bd60", (
            "409 后颜色草稿必须原样保留"
        )
        browser.close()
