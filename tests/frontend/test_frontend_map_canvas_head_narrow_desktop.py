"""D8：窄桌面视口下 canvas-head 不因长 meta 文本折行而增高。

任务 F 把 .literature-map-canvas-meta 的单行截断只放进
@media (max-width:760px)；桌面 >760px 但画布列被挤窄时（1024 / 900px）
同一段长文本仍会折行，撑高 flex:0 0 auto 的 canvas-head，把预览面板顶出画布。
本契约用静态兜底 + 真实浏览器几何断言锁定三条声明必须存在于基础规则。
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/frontend/fixtures/literature_map_component.html"
MAP_CSS = (ROOT / "frontend/literature-maps.css").read_text(encoding="utf-8")
LONG_META = (
    "图谱会在后台分阶段生成，包含非常长的说明文本用于验证窄桌面视口下画布标题列的截断行为，"
    "若基础规则缺少单行截断则这段文本会折行并撑高 canvas-head 容器进而挤压预览面板"
) * 3


def _launch(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - host dependent
        pytest.skip(f"真实浏览器阻塞，未将布局检查冒充通过: {type(exc).__name__}: {exc}")


def test_canvas_meta_single_line_truncation_is_in_base_rule() -> None:
    """静态兜底：三条声明必须在基础规则（首个 @media 块之前），不能只在 760px media 块里。"""
    lines = MAP_CSS.splitlines()
    # 文件注释里也会出现 "@media" 字样，必须按行首判定真正的 @media 块起点。
    first_media_index = next(
        (index for index, line in enumerate(lines) if line.lstrip().startswith("@media")),
        len(lines),
    )
    meta_rules = [
        line for line in lines[:first_media_index]
        if ".literature-map-canvas-meta" in line
    ]
    assert meta_rules, "基础规则（首个 @media 之前）必须存在 .literature-map-canvas-meta"
    assert any(
        all(decl in line for decl in ("overflow: hidden", "text-overflow: ellipsis", "white-space: nowrap"))
        for line in meta_rules
    ), "单行截断三条声明必须上移到基础规则，桌面与移动全覆盖"


@pytest.mark.parametrize("width", [1024, 900])
def test_canvas_head_height_does_not_grow_with_long_meta_on_narrow_desktop(width: int) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=1)
        page.goto(FIXTURE.as_uri(), wait_until="load")
        map_item = page.locator('[data-map-id="map-fixture"]')
        if not map_item.is_visible():
            page.locator("#literature-map-mobile-list-open").click()
        map_item.click()
        head = page.locator(".literature-map-canvas-head")
        head.wait_for(state="visible")
        before = head.evaluate("el => el.getBoundingClientRect().height")
        page.locator("#literature-map-current-meta").evaluate(
            "(el, text) => { el.textContent = text; }", LONG_META
        )
        after = head.evaluate("el => el.getBoundingClientRect().height")
        assert after <= before + 1, (
            f"{width}px 窄桌面视口下长 meta 文本撑高了 canvas-head：{before} → {after}"
        )
        page.close()
        browser.close()
