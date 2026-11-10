# -*- coding: utf-8 -*-
"""深度研究页主 tab 切换宽度稳定性静态契约（TDD / RED → GREEN）。

背景（真实 Chromium 1440×900 / 1280×800 实测）：
  #research-view .research-workspace 是 display:grid 却未声明
  grid-template-columns，隐式 auto 列宽由「当前可见子项」的 max-content 决定：
  「研究任务」态被三列 minmax() 撑到容器宽（标题 x=270）；「创建研究会话」态
  只剩窄卡片 → 列收缩到约 566px 并在 margin:0 auto 下居中（标题 x=558），
  页头 / tab 条整体水平位移；内容加载前后同一 tab 内也会漂。

修复：显式单列 grid-template-columns: minmax(0, 1fr)，列宽恒等于容器宽，
  两个 tab 的页头与创建面板都与三栏加总等宽、整体靠左稳定。

本文件只做静态文本断言（不依赖浏览器/后端），守四件事：
  1. styles.css 的主 workspace 规则含显式单列声明；
  2. index.html 内联 workspace 规则无 display:grid → 不受隐式 auto 列影响、
     无需同步单列声明（历史独立交付只镜像主 tab 规则），且不覆盖 styles.css 修复；
  3. 两处 CSS 的 .research-create-panel 规则不得再加让面板变窄的规则；
  4. 静态资源版本号 styles.css?v=73 / app.js?v=74 与 index.html 生效引用一致。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")

WORKSPACE_SELECTOR = "#research-view .research-workspace"
CREATE_PANEL_SELECTOR = "#research-view .research-create-panel"


def _inline_style() -> str:
    """取 index.html 内联 <style id="research-tasks-inline-style"> 的内容。"""
    start = INDEX.index('<style id="research-tasks-inline-style">')
    end = INDEX.index("</style>", start)
    return INDEX[start:end]


def _selector_blocks(css: str, selector: str) -> list[str]:
    """返回所有『选择器含 selector』的规则块内容（按花括号配对，支持 @media 内嵌）。

    只在目标选择器上取块，避免「全文件搜 minmax(0, 1fr)」这类恒真断言：
    styles.css 里 .project-item / .conversation-item 等许多无关规则本就含该取值。
    """
    blocks: list[str] = []
    for match in re.finditer(r"\{", css):
        open_brace = match.start()
        prev = max(css.rfind("}", 0, open_brace), css.rfind("{", 0, open_brace))
        head = css[prev + 1:open_brace]
        if selector not in head:
            continue
        depth = 0
        for index in range(open_brace, len(css)):
            if css[index] == "{":
                depth += 1
            elif css[index] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(css[open_brace + 1:index])
                    break
    return blocks


# ---- 1. 主样式表：workspace 固定单列 ----------------------------------------
def test_workspace_grid_declares_explicit_single_column_in_styles_css():
    blocks = _selector_blocks(STYLES, WORKSPACE_SELECTOR)
    assert blocks, "styles.css 必须存在 #research-view .research-workspace 规则"
    main = blocks[0]
    assert "display: grid" in main, "workspace 仍是 grid 容器（隐式 auto 列正是本缺陷根因）"
    assert "grid-template-columns:" in main, (
        "workspace 必须显式声明 grid-template-columns，否则隐式 auto 列宽会随"
        "当前可见 tab 内容收缩，页头在 margin:0 auto 下整体水平位移"
    )
    assert "minmax(0, 1fr)" in main, (
        "单列须为 minmax(0, 1fr)：列宽恒等于容器宽，创建面板与「研究任务」"
        "三列加总等宽且整体靠左"
    )
    assert "align-content: start" in main, (
        "行按内容排布，避免 min-height 剩余空间拉伸 header/tabs 行造成"
        "create 态标题垂直位移（1440x900 实测 120 → 158.3）"
    )


# ---- 2. 内联样式：无 display:grid → 无需同步单列声明 ------------------------
def test_inline_workspace_has_no_grid_so_no_single_column_sync_needed():
    """第 2 条结论固化为契约。

    内联 workspace 规则没有 display:grid，因而不存在隐式 auto 列，不会随可见
    tab 内容收缩，无需同步单列声明；它也没有 grid-template-columns，不会以更高
    层叠顺序覆盖 styles.css 的修复。历史模块独立交付只镜像「主 tab」规则（见
    test_research_view_stability_contract.py 的两处同步断言），workspace 内联版本
    本就是简化版（gap 18px vs 20px），从未逐条镜像。
    """
    blocks = _selector_blocks(_inline_style(), WORKSPACE_SELECTOR)
    assert blocks, "内联样式仍须保留 #research-view .research-workspace 规则"
    for block in blocks:
        assert "display: grid" not in block, (
            "内联 workspace 一旦变成 grid 就会重新引入隐式 auto 列，须同步单列声明"
        )
        assert "grid-template-columns" not in block, (
            "内联样式不应另行声明列宽，避免以更高层叠顺序覆盖 styles.css 的修复"
        )


# ---- 3. 创建面板不得重新变窄 ------------------------------------------------
NARROWING_DECLARATIONS = ("max-width", "justify-self: center", "width: fit-content")


def test_create_panel_has_no_width_narrowing_declarations_in_both_stylesheets():
    for name, css in (("styles.css", STYLES), ("index.html 内联样式", _inline_style())):
        blocks = _selector_blocks(css, CREATE_PANEL_SELECTOR)
        assert blocks, f"{name} 必须保留 .research-create-panel 规则"
        for block in blocks:
            for declaration in NARROWING_DECLARATIONS:
                assert declaration not in block, (
                    f"{name} 的 .research-create-panel 不得含 {declaration}，"
                    "否则创建面板会比「研究任务」三列加总窄，重新引入不等宽/位移"
                )


# ---- 4. 静态资源版本号 ------------------------------------------------------
def test_static_asset_versions_match_index_html():
    assert 'href="/assets/styles.css?v=73"' in INDEX, "styles.css 改动后须升到 ?v=73"
    assert 'src="/assets/app.js?v=74"' in INDEX, "app.js 未改动，保持 ?v=74 不无谓 bump"
    assert 'href="/assets/styles.css?v=72"' not in INDEX, "旧版 ?v=72 生效引用须已同步"
