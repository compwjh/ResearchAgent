"""隐藏性契约：文献地图「节点样式」浮层折叠时必须真的看不见，展开后恢复布局。

背景（真实浏览器复测发现的缺陷）：`<details class="literature-map-node-style-disclosure">`
折叠态 `open === false` 是对的，但 `frontend/literature-maps.css` 里
`.literature-map-node-style { display: flex; ... }` 是作者样式，会压过 UA 对
`details:not([open])` 非 summary 子元素的隐藏，导致浮层内容以一个竖条继续渲染在画布上方。

因此本文件断言的是**用户可见性**（computed style / 元素矩形），而不是 `open` 属性——
只断言 `open` 的用例在本次缺陷下会误报通过。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"
STYLES = (ROOT / "frontend/literature-maps.css").read_text(encoding="utf-8")

DISCLOSURE = ".literature-map-node-style-disclosure"
FIELD = "#literature-map-node-style"

# 折叠态下 `#literature-map-node-style` 的可见性快照：display / visibility / 矩形面积。
_VISIBILITY_JS = """
(selector => {
  const element = typeof selector === 'string' ? document.querySelector(selector) : selector;
  if (!element) return null;
  const style = getComputedStyle(element);
  const rect = element.getBoundingClientRect();
  return {
    display: style.display,
    visibility: style.visibility,
    opacity: style.opacity,
    width: Math.round(rect.width),
    height: Math.round(rect.height),
    area: Math.round(rect.width) * Math.round(rect.height),
  };
})
"""


def _launch(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - host dependent
        pytest.skip(f"真实浏览器阻塞，未将静态检查冒充通过: {type(exc).__name__}: {exc}")


def _is_hidden(snapshot: dict) -> bool:
    """折叠态「完全不可见」的判据：display:none / visibility 不可见 / 零面积。"""
    if snapshot["display"] == "none":
        return True
    if snapshot["visibility"] in {"hidden", "collapse"}:
        return True
    if float(snapshot["opacity"]) == 0:
        return True
    return snapshot["area"] == 0


def _open_map(page, query: str = "palette&usable-saved-view", mobile: bool = False) -> None:
    page.set_default_timeout(5000)
    page.goto(f"{FIXTURE.as_uri()}?{query}", wait_until="load")
    if mobile:
        # 移动视口下列表是抽屉，必须先打开抽屉才能选中地图（与 mobile 契约用例同路径）。
        page.locator("#literature-map-mobile-list-open").click()
        page.locator('[data-map-id="map-fixture"]').click()
        page.wait_for_function(
            "!document.querySelector('.literature-map-list-panel')?.classList.contains('is-open')"
        )
    else:
        page.locator('[data-map-id="map-fixture"]').click()
    page.wait_for_selector('[data-node-id="node-a"] circle')


@pytest.mark.parametrize("width", [1440, 390])
def test_collapsed_node_style_fieldset_is_not_rendered_until_summary_is_clicked(width: int) -> None:
    """默认折叠：fieldset 真的看不见；点 summary 后恢复原有 flex 布局。"""
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        mobile = width < 760
        page = browser.new_page(
            viewport={"width": width, "height": 800},
            has_touch=mobile,
            is_mobile=mobile,
        )
        _open_map(page, mobile=mobile)
        page.locator('[data-node-id="node-a"] circle').click()

        disclosure = page.locator(DISCLOSURE)
        assert disclosure.get_attribute("open") is None, "前置：节点样式浮层默认折叠"

        collapsed = page.eval_on_selector(FIELD, _VISIBILITY_JS)
        assert collapsed is not None, "节点样式 fieldset 必须存在于 DOM（折叠仅隐藏，不销毁）"
        assert _is_hidden(collapsed), (
            "折叠态 #literature-map-node-style 必须完全不可见（display:none / 零面积），"
            f"实际 computed style 与矩形为 {collapsed}；"
            "作者样式 display:flex 压过了 UA 对 details:not([open]) 子元素的隐藏"
        )

        disclosure.locator("summary").click()
        page.wait_for_function(
            "(selector) => document.querySelector(selector)?.getBoundingClientRect().width > 0",
            arg=FIELD,
        )
        assert disclosure.get_attribute("open") == "", "点击 summary 后 details 必须已展开"

        expanded = page.eval_on_selector(FIELD, _VISIBILITY_JS)
        assert expanded["display"] == "flex", f"展开后必须恢复原有 flex 布局，实际 {expanded}"
        assert expanded["visibility"] == "visible", f"展开后必须可见，实际 {expanded}"
        # 桌面 1280/1440 下为约 416×47 的单行面板；移动 390 下内部换行成 342×73，故按视口放宽阈值。
        assert expanded["width"] >= (380 if width >= 760 else 300), f"展开后 fieldset 宽度异常，实际 {expanded}"
        assert expanded["height"] >= (30 if width >= 760 else 60), f"展开后 fieldset 高度异常，实际 {expanded}"

        browser.close()


def test_node_style_fieldset_visibility_survives_viewport_switch() -> None:
    """用户点开后再切换视口：仍可见；切回并收起后才隐藏（开合不被视口改写）。"""
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 800})
        _open_map(page)
        disclosure = page.locator(DISCLOSURE)
        disclosure.locator("summary").click()
        page.wait_for_function(
            "(selector) => document.querySelector(selector)?.getBoundingClientRect().width > 0",
            arg=FIELD,
        )

        page.set_viewport_size({"width": 390, "height": 800})
        page.wait_for_timeout(120)
        assert disclosure.get_attribute("open") == "", "切到移动视口不得强制折叠用户已展开的浮层"
        assert not _is_hidden(page.eval_on_selector(FIELD, _VISIBILITY_JS)), "用户展开的面板在移动视口仍须可见"

        page.set_viewport_size({"width": 1440, "height": 800})
        page.wait_for_timeout(120)
        assert not _is_hidden(page.eval_on_selector(FIELD, _VISIBILITY_JS)), "切回桌面仍须可见"

        disclosure.locator("summary").click()
        page.wait_for_function(
            "(selector) => {"
            "  const element = document.querySelector(selector);"
            "  if (!element) return false;"
            "  const style = getComputedStyle(element);"
            "  const rect = element.getBoundingClientRect();"
            "  return style.display === 'none' || rect.width * rect.height === 0;"
            "}",
            arg=FIELD,
        )
        assert _is_hidden(page.eval_on_selector(FIELD, _VISIBILITY_JS)), "用户收起后必须重新隐藏"

        browser.close()


def test_hide_rule_is_scoped_to_the_disclosure_container() -> None:
    """静态护栏：隐藏规则必须带容器限定的 :not([open]) 前置条件，不能全局误伤。"""
    rules = [
        line.strip()
        for line in STYLES.splitlines()
        if "literature-map-node-style-disclosure:not([open])" in line
        and "display: none" in line
    ]
    assert rules, (
        "literature-maps.css 必须存在折叠态隐藏规则："
        "#literature-maps-view .literature-map-node-style-disclosure:not([open]) > .literature-map-node-style { display: none; }"
    )
    rule = rules[0]
    assert rule.startswith("#literature-maps-view "), f"隐藏规则必须限定在 #literature-maps-view 作用域内，实际：{rule}"
    assert "display: none" in rule and "!important" not in rule, f"隐藏规则不应依赖 !important，实际：{rule}"
    assert re.search(r">\s*\.literature-map-node-style\s*\{", rule), f"隐藏规则必须直接命中 fieldset 子元素，实际：{rule}"
