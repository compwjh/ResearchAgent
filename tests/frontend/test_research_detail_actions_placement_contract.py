# -*- coding: utf-8 -*-
"""深度研究页任务操作按钮迁移到「研究任务详情卡片」右上角的静态契约（TDD / RED → GREEN）。

单次一事的回归契约：把整组 `.research-page-actions`（6 个 button）从
`.research-page-header` 迁入 `#research-detail-head` 右上角。纯静态文本断言，
不依赖浏览器 / 后端 / 网络；守五件事：

  1. 按钮组位于 #research-detail-head 内（作为最后一个子元素），
     且 .research-page-header 内不再有 actions 占位；
  2. 6 个 button id 全部保留、顺序不变、全文唯一（不复制第二份按钮），
     且 type / hidden / aria-hidden / disabled 关键属性不丢；
  3. 内联 <style id="research-tasks-inline-style"> 与 styles.css 两处主规则
     都含右上角布局声明（两列 grid + 按钮组第 2 列靠右顶部对齐）；
  4. 两处 <=760px 断点都有单列覆盖（内联主规则层叠顺序更高，不同步会压住窄屏）；
  5. 静态资源版本号 styles.css?v=75 / app.js?v=74 生效引用唯一且一致，
     旧生效引用已同步、历史兼容 marker 不被误改。

已知行为变化（如实保留，不补偿）：按钮组随 #research-tabpanel-tasks 一起，
切到「创建研究会话」tab 时 hidden；本契约故意不复制按钮、不加第二份按钮，
也不改 activateResearchTab。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")

EXPECTED_BUTTON_IDS = (
    "research-refresh-button",
    "research-task-pause-button",
    "research-task-resume-button",
    "research-task-recover-button",
    "research-task-approve-button",
    "research-cancel-button",
)
HEAD_SELECTOR = "#research-view .research-detail-head"
ACTIONS_SELECTOR = ".research-detail-head > .research-page-actions"


def _inline_style() -> str:
    """取 index.html 内联 <style id="research-tasks-inline-style"> 的内容。"""
    start = INDEX.index('<style id="research-tasks-inline-style">')
    end = INDEX.index("</style>", start)
    return INDEX[start:end]


def _block_after(html: str, marker: str) -> str:
    """取 marker 所在 div 开始标签之后、配对闭合 </div> 之前的内部内容（按 div 计数）。

    head 内只有一层嵌套 div（actions），按 <div / </div> 计数即可精确配对，
    避免「全文件找下一个 </div>」误命中 actions 自身的闭合。
    """
    start = html.index(marker)
    tag_end = html.index(">", start) + 1
    depth = 1
    for token in re.finditer(r"<(/?)div\b", html[tag_end:]):
        depth += -1 if token.group(1) == "/" else 1
        if depth == 0:
            return html[tag_end:tag_end + token.start()]
    raise AssertionError(f"未找到 {marker} 所在元素的配对闭合标签")


def _selector_blocks(css: str, selector: str) -> list[str]:
    """返回所有『选择器含 selector』的规则块内容（按花括号配对，支持 @media 内嵌）。

    只取目标选择器块，避免「全文件搜 grid-template-columns」这类恒真断言：
    styles.css 里无关规则本就含该属性。块不存在时由调用方 assert blocks 显式失败。
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


def _media_blocks(css: str, query: str) -> list[str]:
    """返回 @media (query) { ... } 的内容（按花括号配对）。"""
    blocks: list[str] = []
    pattern = r"@media\s*\(" + re.escape(query) + r"\)\s*\{"
    for match in re.finditer(pattern, css):
        open_brace = css.index("{", match.start())
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


# ---- 1. DOM 位置迁移 -------------------------------------------------------
def test_actions_container_moved_into_detail_head():
    header_start = INDEX.index('class="research-page-header"')
    header_end = INDEX.index("</header>", header_start)
    header_block = INDEX[header_start:header_end]
    head_start = INDEX.index('id="research-detail-head"')

    assert "research-page-actions" not in header_block, (
        "按钮组须整体迁出 .research-page-header，且不留空 actions 占位"
    )
    assert header_end < head_start, "详情页头在页头之后（基线不变量）"
    head_inner = _block_after(INDEX, 'id="research-detail-head"')
    assert 'class="research-page-actions"' in head_inner, (
        "按钮组须位于 #research-detail-head 内部"
    )
    # 作为 head 最后一个子元素：actions 闭合之后只剩空白
    tail = head_inner[head_inner.index('class="research-page-actions"'):]
    after_actions = tail[tail.index("</div>") + len("</div>"):]
    assert after_actions.strip() == "", "按钮组须是 head 的最后一个子元素（右上角）"


# ---- 2. 六个按钮 id / 顺序 / 关键属性不变 ----------------------------------
def test_all_six_action_buttons_keep_ids_order_and_attributes():
    actions_inner = _block_after(INDEX, 'class="research-page-actions"')
    found = re.findall(r'<button\b[^>]*\bid="([^"]+)"', actions_inner)
    assert found == list(EXPECTED_BUTTON_IDS), (
        f"6 个 button id 与顺序必须原样保留，实际为 {found}"
    )
    for dom_id in EXPECTED_BUTTON_IDS:
        assert INDEX.count(f'id="{dom_id}"') == 1, (
            f"{dom_id} 全文必须唯一：不复制按钮、不加第二份按钮（第 5 条行为变化）"
        )
    assert actions_inner.count('type="button"') == 6, "6 个 button 的 type 不变"
    assert actions_inner.count('aria-hidden="true"') == 4, "4 个默认隐藏按钮的 aria-hidden 不变"
    assert actions_inner.count("disabled") == 1, "取消按钮的 disabled 默认态不变"


# ---- 3. 两处 CSS 主规则含右上角布局声明 ------------------------------------
def test_both_stylesheets_declare_top_right_layout():
    for name, css in (("styles.css", STYLES), ("index.html 内联样式", _inline_style())):
        head_blocks = _selector_blocks(css, HEAD_SELECTOR)
        assert head_blocks, f"{name} 必须保留 {HEAD_SELECTOR} 规则"
        assert any(
            "grid-template-columns:" in block and "minmax(0, 1fr) auto" in block
            for block in head_blocks
        ), f"{name} 的 head 须声明两列 grid（左侧 1fr + 右侧 auto 放按钮组）"

        action_blocks = _selector_blocks(css, ACTIONS_SELECTOR)
        assert action_blocks, f"{name} 必须保留 {ACTIONS_SELECTOR} 规则"
        main = "".join(action_blocks)
        for declaration in (
            "grid-column: 2",        # 按钮组占第 2 列
            "justify-self: end",     # 右端贴 head 右边界
            "align-self: start",     # 顶部与徽章第一行对齐
            "justify-content: flex-end",
        ):
            assert declaration in main, f"{name} 的按钮组规则须含 {declaration}"


# ---- 3b. 几何语义：标题/meta 跨两列占满整行，按钮组只占首行 -----------------
def test_head_content_spans_full_width_and_actions_only_take_first_row():
    """回归：按钮组曾以 grid-row: 1 / -1 独占右列，把标题/meta 压到窄左列折行。

    修法要求两处样式表（styles.css + 内联 <style>）都满足：
      - h2/meta/recovery-notice 跨两列（grid-column: 1 / -1）→ 恢复整卡宽度；
      - 按钮组只占首行（grid-row: 1），不得再跨所有行；
      - badge 留在首行左列（grid-column: 1; grid-row: 1），与按钮组并排。
    只取目标选择器块，避免「全文件搜 grid-column: 1 / -1」恒真。
    """
    span_selector = "> :not(.research-page-actions):not(.research-badge)"
    badge_selector = "> .research-badge"
    for name, css in (("styles.css", STYLES), ("index.html 内联样式", _inline_style())):
        span_blocks = _selector_blocks(css, span_selector)
        assert span_blocks, f"{name} 须保留『标题/meta 跨两列』规则（{span_selector}）"
        assert any("grid-column: 1 / -1" in block for block in span_blocks), (
            f"{name} 的标题/meta/notice 须 grid-column: 1 / -1，恢复整卡宽度"
        )

        badge_blocks = _selector_blocks(css, badge_selector)
        assert badge_blocks, f"{name} 须保留 badge 首行左列规则"
        assert any(
            "grid-column: 1" in block and "grid-row: 1" in block for block in badge_blocks
        ), f"{name} 的 badge 须留在首行左列（grid-column: 1; grid-row: 1）"

        action_blocks = _selector_blocks(css, ACTIONS_SELECTOR)
        main = "".join(action_blocks)
        assert "grid-row: 1;" in main, f"{name} 的按钮组须只占首行（grid-row: 1）"
        assert "grid-row: 1 / -1" not in main, (
            f"{name} 的按钮组不得再跨所有行独占右列（会挤压标题/meta）"
        )


# ---- 4. 两处窄屏断点改回单列（防横向溢出 / 挤压标题） ------------------------
def test_both_stylesheets_collapse_head_to_single_column_on_narrow_screens():
    for name, css in (("styles.css", STYLES), ("index.html 内联样式", _inline_style())):
        narrow = _media_blocks(css, "max-width: 760px")
        assert narrow, f"{name} 必须保留 <=760px 断点"
        assert any(
            HEAD_SELECTOR in block
            and "grid-template-columns: minmax(0, 1fr);" in block
            for block in narrow
        ), (
            f"{name} 的 <=760px 断点须把 head 改回单列；内联主规则层叠顺序更高，"
            "若不覆盖会压住 styles.css 的单列声明，343px 中间列将横向溢出"
        )


# ---- 5. 版本号一致 ---------------------------------------------------------
def test_asset_versions_are_synchronised():
    assert 'href="/assets/styles.css?v=75"' in INDEX, "改了 styles.css，生效引用须升到 ?v=75"
    assert 'src="/assets/app.js?v=74"' in INDEX, "app.js 未改，保持 ?v=74 不无谓 bump"
    assert 'href="/assets/styles.css?v=74"' not in INDEX, "旧生效引用 ?v=74 须已同步"
    live_css = re.findall(r'<link rel="stylesheet" href="/assets/styles\.css\?v=(\d+)"', INDEX)
    live_app = re.findall(r'<script src="/assets/app\.js\?v=(\d+)"', INDEX)
    assert live_css == ["75"], f"生效 styles.css 版本唯一且为 75：{live_css}"
    assert live_app == ["74"], f"生效 app.js 版本唯一且为 74：{live_app}"
    # 历史兼容 marker 注释保持原样（不因升版本被误删）
    assert "styles.css?v=62" in INDEX and "app.js?v=31" in INDEX, "历史兼容 marker 不动"
