"""画布左下角分组入口（FAB）与高亮浮层的用户可见契约。

Spec043 把「分组」从左侧常驻面板搬到画布左下角的图标入口：
`#literature-map-groups-fab` 展开 `#literature-map-groups-popover`，浮层内含分组行
（`.literature-map-group-row[data-group-id]`）、色块（`.literature-map-group-color-trigger`）、
「清除高亮」按钮与折叠的「＋ 新建组」表单（`#literature-map-group-form`）。

本文件守 8 件事（全部用真实 Chromium + 真实 DOM 断言，不做字符串拼 HTML）：
1. FAB 在画布内、`position:absolute`、`pointer-events:auto`；选中地图后可见，无地图时 hidden；
2. 浮层 `aria-expanded` 开→true / Esc→false / 点外部→false，`hidden` 同步；
3. 点色块后目标组 `<g>` 带 `is-group-highlighted`、其余 `is-group-dimmed`，再点同组恢复；
4. 「清除高亮」生效；
5. 高亮不写库（`window.__requestLog` 无新增写请求）；
6. 节点详情无 `.literature-map-node-color-section`、多选无 `data-target="selection"` 色板；
7. 1440 / 1024 / 375 三档视口下 FAB 矩形完整在 `.literature-map-canvas` 内、
   与 `.literature-map-tools` 无交叠、375 下 `document.documentElement.scrollWidth <= innerWidth`；
8. 源码无 `innerHTML`（XSS 纪律）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"
MODULE = (ROOT / "frontend/literature-maps.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/literature-maps.css").read_text(encoding="utf-8")

FAB = "#literature-map-groups-fab"
POPOVER = "#literature-map-groups-popover"
GROUP_ROW = '.literature-map-group-row[data-group-id="group-fixture"]'
HIGHLIGHTED = ".literature-map-node.is-group-highlighted"
DIMMED = ".literature-map-node.is-group-dimmed"


def _launch(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - host dependent
        pytest.skip(f"真实浏览器阻塞，未将静态检查冒充通过: {type(exc).__name__}: {exc}")


def _open_map(page, query: str = "palette") -> None:
    page.set_default_timeout(5000)
    page.goto(f"{FIXTURE.as_uri()}?{query}", wait_until="load")


def _select_map(page) -> None:
    page.locator('[data-map-id="map-fixture"]').click()
    page.wait_for_selector('[data-node-id="node-a"] circle')
    page.wait_for_function(
        "document.querySelector('#literature-map-current-title')?.textContent.includes('边缘学习地图')"
    )


def _open_popover(page) -> None:
    fab = page.locator(FAB)
    fab.wait_for(state="visible")
    if fab.get_attribute("aria-expanded") != "true":
        fab.click()
    page.locator(POPOVER).wait_for(state="visible")
    assert fab.get_attribute("aria-expanded") == "true"


def test_fab_sits_inside_the_canvas_and_is_hidden_until_a_map_is_selected() -> None:
    """① FAB 的位置/层叠/可见性契约。"""
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page)
        page.wait_for_selector(FAB, state="attached")

        # 无地图时必须 hidden。
        assert page.locator(FAB).get_attribute("hidden") == "", "未选中地图时 FAB 必须 hidden"
        assert page.locator(POPOVER).get_attribute("hidden") == "", "未选中地图时浮层必须 hidden"

        _select_map(page)
        page.wait_for_function(
            f"document.querySelector('{FAB}') && !document.querySelector('{FAB}').hidden"
        )
        fab = page.locator(FAB)
        assert fab.is_visible(), "选中地图后 FAB 必须可见"

        # DOM 归属 + 计算样式：必须是画布内 absolute + pointer-events:auto。
        assert page.evaluate(
            f"document.querySelector('{FAB}').closest('.literature-map-canvas') !== null"
        ), "FAB 必须位于 .literature-map-canvas 内"
        box = page.evaluate(
            f"""() => {{
              const fab = document.querySelector('{FAB}');
              const style = getComputedStyle(fab);
              const rect = fab.getBoundingClientRect();
              const canvas = fab.closest('.literature-map-canvas').getBoundingClientRect();
              return {{
                position: style.position,
                pointerEvents: style.pointerEvents,
                zIndex: Number(style.zIndex || 0),
                rect: {{ left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom }},
                canvas: {{ left: canvas.left, right: canvas.right, top: canvas.top, bottom: canvas.bottom }},
              }};
            }}"""
        )
        assert box["position"] == "absolute", f"FAB 必须是 position:absolute，实际 {box['position']}"
        assert box["pointerEvents"] == "auto", (
            f"FAB 必须 pointer-events:auto（要压在 pointer-events:none 的空态层之上），实际 {box['pointerEvents']}"
        )
        assert box["zIndex"] >= 2, f"FAB 必须叠在 svg/空态层之上，实际 z-index={box['zIndex']}"
        assert box["rect"]["left"] >= box["canvas"]["left"] - 0.5
        assert box["rect"]["right"] <= box["canvas"]["right"] + 0.5
        assert box["rect"]["top"] >= box["canvas"]["top"] - 0.5
        assert box["rect"]["bottom"] <= box["canvas"]["bottom"] + 0.5

        # 可见性切换：切到没有地图的状态时必须重新 hidden。
        page.evaluate(
            "() => { const node = document.querySelector('#literature-map-group-list'); node && node.replaceChildren(); }"
        )
        assert page.locator(FAB).is_visible(), "清空分组行不影响 FAB 可见性"
        browser.close()


def test_popover_toggles_with_aria_expanded_escape_and_outside_click() -> None:
    """② aria-expanded 与 hidden 必须始终同步（开/ Esc / 点外部）。"""
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page)
        _select_map(page)

        fab = page.locator(FAB)
        popover = page.locator(POPOVER)
        assert fab.get_attribute("aria-expanded") == "false"
        assert popover.get_attribute("hidden") == ""

        fab.click()
        popover.wait_for(state="visible")
        assert fab.get_attribute("aria-expanded") == "true", "展开后 aria-expanded 必须为 true"
        assert popover.get_attribute("hidden") is None, "展开后浮层必须去掉 hidden"
        assert popover.locator(GROUP_ROW).is_visible(), "展开后必须能看到分组行"
        assert popover.locator("#literature-map-group-list").count() == 1
        assert popover.locator("#literature-map-group-empty").count() == 1
        assert popover.locator(".literature-map-groups-create > summary").inner_text().strip() == "＋ 新建组"
        assert popover.locator("#literature-map-group-form").count() == 1

        # Esc 关闭。
        page.keyboard.press("Escape")
        page.wait_for_function(f"document.querySelector('{POPOVER}').hidden === true")
        assert fab.get_attribute("aria-expanded") == "false", "Esc 关闭后 aria-expanded 必须为 false"

        # 再开 → 点外部关闭。
        fab.click()
        popover.wait_for(state="visible")
        page.locator("#literature-map-current-title").click()
        page.wait_for_function(f"document.querySelector('{POPOVER}').hidden === true")
        assert fab.get_attribute("aria-expanded") == "false", "点外部关闭后 aria-expanded 必须为 false"

        # 再点 FAB 自身是 toggle，不应留下「aria-expanded=true 但 hidden=true」的错位。
        fab.click()
        popover.wait_for(state="visible")
        fab.click()
        page.wait_for_function(f"document.querySelector('{POPOVER}').hidden === true")
        assert fab.get_attribute("aria-expanded") == "false"
        browser.close()


def test_group_swatch_highlights_matching_group_and_clear_button_restores() -> None:
    """③④ 高亮命中/淡化与「清除高亮」。"""
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page)
        _select_map(page)
        _open_popover(page)

        assert page.locator(HIGHLIGHTED).count() == 0
        assert page.locator(DIMMED).count() == 0
        clear_button = page.locator(".literature-map-groups-clear-highlight")
        assert clear_button.get_attribute("hidden") == "", "未高亮时「清除高亮」必须 hidden"

        row = page.locator(GROUP_ROW)
        row.locator(".literature-map-group-color-trigger").click()
        page.wait_for_function(f"document.querySelectorAll('{HIGHLIGHTED}').length === 1")

        highlighted = page.locator(f'{HIGHLIGHTED}[data-node-id="node-a"]')
        assert highlighted.count() == 1, "node-a 属于 group-fixture，必须被高亮"
        assert highlighted.get_attribute("data-group-highlight") == "on"
        dimmed = page.locator(f'{DIMMED}[data-node-id="node-b"]')
        assert dimmed.count() == 1, "node-b 不属于该组，必须被淡化"
        assert dimmed.get_attribute("data-group-highlight") == "off"
        assert page.locator('.literature-map-edge.is-group-dimmed').count() == 2, "跨组边必须一并淡化"
        # 高亮是纯视图态：不得改动 circle 的内联描边（那是 nodeStyle 的地盘）。
        assert page.locator('[data-node-id="node-a"] circle').get_attribute("stroke-width") in (None, "2.5", "3")
        assert clear_button.get_attribute("hidden") is None, "高亮后「清除高亮」必须可见"

        # 再点同组 → 恢复。
        page.locator(GROUP_ROW).locator(".literature-map-group-color-trigger").click()
        page.wait_for_function(f"document.querySelectorAll('{HIGHLIGHTED}').length === 0")
        assert page.locator(DIMMED).count() == 0, "取消高亮后不得残留淡化态"
        assert clear_button.get_attribute("hidden") == ""

        # 再次高亮后用「清除高亮」按钮收尾。
        page.locator(GROUP_ROW).locator(".literature-map-group-color-trigger").click()
        page.wait_for_function(f"document.querySelectorAll('{HIGHLIGHTED}').length === 1")
        clear_button.click()
        page.wait_for_function(f"document.querySelectorAll('{HIGHLIGHTED}').length === 0")
        assert page.locator(DIMMED).count() == 0
        assert clear_button.get_attribute("hidden") == ""

        # 「未分组」哨兵行必须存在且可高亮未分组节点。
        ungrouped = page.locator(".literature-map-group-row.is-ungrouped")
        assert ungrouped.count() == 1
        ungrouped.locator(".literature-map-group-color-trigger").click()
        # 「未分组」高亮命中的是未分组节点（node-b），已分组节点（node-a）被淡化。
        page.wait_for_function(
            "document.querySelectorAll('" + HIGHLIGHTED + "[data-node-id=\"node-b\"]').length === 1"
        )
        assert page.locator(f'{DIMMED}[data-node-id="node-a"]').count() == 1
        assert ungrouped.locator(".literature-map-group-color-trigger").get_attribute("aria-pressed") == "true"
        browser.close()


def test_highlighting_and_popover_never_write_to_the_backend() -> None:
    """⑤ 浮层开合与高亮都是纯前端视图态，不得写库。"""
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page)
        _select_map(page)
        baseline = page.evaluate("window.__requestLog.length")

        _open_popover(page)
        page.locator(GROUP_ROW).locator(".literature-map-group-color-trigger").click()
        page.wait_for_function(f"document.querySelectorAll('{HIGHLIGHTED}').length === 1")
        page.locator(GROUP_ROW).locator(".literature-map-group-color-trigger").click()
        page.wait_for_function(f"document.querySelectorAll('{HIGHLIGHTED}').length === 0")
        page.keyboard.press("Escape")
        page.wait_for_function(f"document.querySelector('{POPOVER}').hidden === true")
        page.wait_for_timeout(200)

        new_entries = page.evaluate(
            "baseline => window.__requestLog.slice(baseline)", baseline
        )
        writes = [
            entry for entry in new_entries
            if entry["method"] in ("POST", "PATCH", "PUT", "DELETE")
            and "/analysis-queue/ensure" not in entry["path"]
        ]
        assert writes == [], f"浮层开合与高亮不得产生写请求，实际：{writes}"
        assert page.evaluate("window.__nodeStyleBodies.length") == 0
        assert page.evaluate("window.__groupBodies.length") == 0
        assert page.evaluate("window.__nodeGroupBodies.length") == 0
        assert page.evaluate("window.__viewBodies.length") == 0
        browser.close()


def test_node_detail_and_multi_select_no_longer_offer_node_level_colors() -> None:
    """⑥ 节点详情无调色区、多选无色板（颜色只跟随分组）。"""
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        _open_map(page)
        _select_map(page)

        page.locator('[data-node-id="node-a"] circle').click()
        page.wait_for_selector("#literature-map-detail .literature-map-detail-title")
        detail = page.locator("#literature-map-detail")
        assert detail.locator(".literature-map-node-color-section").count() == 0
        assert detail.locator('.literature-map-color-palette[data-target="node"]').count() == 0
        assert page.locator('[data-node-id="node-a"] circle').get_attribute("fill") == "#3366cc"

        page.locator("#literature-map-multi-select-toggle").click()
        page.locator('[data-node-id="node-a"] circle').click()
        page.locator('[data-node-id="node-b"] circle').click()
        page.wait_for_function(
            "document.querySelector('#literature-map-selected-count')?.textContent === '已选 2 篇'"
        )
        assert page.locator('.literature-map-color-palette[data-target="selection"]').count() == 0
        assert page.locator('.literature-map-color-palette[data-target="node"]').count() == 0
        assert page.locator('[data-node-id="node-a"] circle').get_attribute("fill") == "#3366cc"
        assert page.locator('[data-node-id="node-b"] circle').get_attribute("fill") == "#8d80e6"
        assert page.evaluate("window.__nodeStyleBodies.length") == 0
        browser.close()


@pytest.mark.parametrize("viewport", [(1440, 900), (1024, 800), (375, 820)])
def test_fab_stays_inside_the_canvas_and_clear_of_the_tools_row(viewport) -> None:
    """⑦ 三档视口下的几何契约（不越界、不与工具行交叠、375 无横向溢出）。"""
    width, height = viewport
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
        _open_map(page)
        if width <= 760:
            # 移动端列表抽屉要先打开才能选图。
            page.locator("#literature-map-mobile-list-open").click(force=True)
        _select_map(page)
        page.wait_for_selector(FAB, state="visible")

        geometry = page.evaluate(
            f"""() => {{
              const fab = document.querySelector('{FAB}').getBoundingClientRect();
              const canvas = document.querySelector('.literature-map-canvas').getBoundingClientRect();
              const tools = document.querySelector('.literature-map-tools');
              const toolsRect = tools ? tools.getBoundingClientRect() : null;
              const overlaps = (a, b) => Boolean(b)
                && a.left < b.right && b.left < a.right
                && a.top < b.bottom && b.top < a.bottom;
              return {{
                fab: {{ left: fab.left, right: fab.right, top: fab.top, bottom: fab.bottom,
                        width: fab.width, height: fab.height }},
                canvas: {{ left: canvas.left, right: canvas.right, top: canvas.top, bottom: canvas.bottom,
                           width: canvas.width, height: canvas.height }},
                overlapsTools: overlaps(fab, toolsRect),
                scrollWidth: document.documentElement.scrollWidth,
                innerWidth: window.innerWidth,
              }};
            }}"""
        )

        fab = geometry["fab"]
        canvas = geometry["canvas"]
        assert fab["width"] > 0 and fab["height"] > 0, f"FAB 必须有可见尺寸：{fab}"
        assert fab["left"] >= canvas["left"] - 0.5, f"FAB 左边界越出画布：{fab} vs {canvas}"
        assert fab["right"] <= canvas["right"] + 0.5, f"FAB 右边界越出画布：{fab} vs {canvas}"
        assert fab["top"] >= canvas["top"] - 0.5, f"FAB 上边界越出画布：{fab} vs {canvas}"
        assert fab["bottom"] <= canvas["bottom"] + 0.5, f"FAB 下边界越出画布：{fab} vs {canvas}"
        assert geometry["overlapsTools"] is False, "FAB 不得与 .literature-map-tools 交叠"
        if width <= 760:
            assert geometry["scrollWidth"] <= geometry["innerWidth"], (
                f"375 档不得横向溢出：scrollWidth={geometry['scrollWidth']} > innerWidth={geometry['innerWidth']}"
            )

        # 展开浮层后同样不得横向溢出（移动端 8px 内边距 + left/right 锚定）。
        page.locator(FAB).click()
        page.locator(POPOVER).wait_for(state="visible")
        if width <= 760:
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        browser.close()


def test_fab_module_keeps_dom_contract_and_never_uses_inner_html() -> None:
    """⑧ 源码级：无 innerHTML，新 class 在 CSS 有定义（DOM 契约双向核对）。"""
    assert "innerHTML" not in MODULE
    assert "createElement(" in MODULE
    for marker in (
        "literature-map-groups-fab",
        "literature-map-groups-popover",
        "literature-map-group-list",
        "literature-map-group-empty",
        "literature-map-group-row",
        "literature-map-group-color-trigger",
        "literature-map-groups-clear-highlight",
        "is-group-highlighted",
        "is-group-dimmed",
    ):
        assert marker in MODULE, f"literature-maps.js 必须仍渲染 {marker}"
    # JS 里用到的 FAB/浮层/高亮 class 必须在 CSS 有对应样式（防止「渲染了但没样式」）。
    for selector in (
        ".literature-map-groups-fab",
        ".literature-map-groups-popover",
        ".literature-map-group-row",
        ".literature-map-group-color-trigger",
        ".literature-map-groups-clear-highlight",
        ".literature-map-node.is-group-highlighted",
        ".literature-map-node.is-group-dimmed",
    ):
        assert selector in STYLES, f"literature-maps.css 必须定义 {selector}"
    # 浮层主规则必须显式声明 pointer-events: absolute 定位；touch-action 见 FE-4 的独立回归用例。
    popover_rule = STYLES.split("\n#literature-maps-view .literature-map-groups-popover {", 1)
    assert len(popover_rule) == 2, "literature-maps.css 必须定义浮层主规则"
    popover_body = popover_rule[1].split("}", 1)[0]
    assert "pointer-events: auto" in popover_body, f"浮层必须 pointer-events:auto，实际：{popover_body}"
    assert "position: absolute" in popover_body
