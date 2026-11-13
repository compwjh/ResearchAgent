"""文献地图页面级 tab 与刷新状态图标的静态契约（能力命名，无 spec/task 编号）。

纯源码断言，不依赖浏览器。覆盖：live 资源版本与末尾纯属性 marker、
tablist/tab/tabpanel + aria-* + data-map-tab 契约（默认 maps 选中 / create 隐藏）、
activateMapTab 只改属性不重建面板、刷新图标按钮（无可见文字 + aria-label + CSS 转圈）、
刷新图标 CSS 作用域与旋转 / reduced-motion 降级、header 其余作业按钮默认显隐。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
MAP_JS = (ROOT / "frontend/literature-maps.js").read_text(encoding="utf-8")
MAP_CSS = (ROOT / "frontend/literature-maps.css").read_text(encoding="utf-8")

VIEW_SCOPE = "#literature-maps-view"
HTML_COMMENTS = re.findall(r"<!--([\s\S]*?)-->", INDEX)


def _function_body(source: str, signature: str) -> str:
    """按花括号配对截取单个函数体，避免把后续函数的 replaceChildren 误算进来。"""
    start = source.find(signature)
    assert start != -1, f"找不到函数定义：{signature}"
    brace = source.index("{", start)
    depth = 0
    for offset in range(brace, len(source)):
        char = source[offset]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1:offset]
    raise AssertionError(f"函数花括号未配对：{signature}")


# ---- 1. live 资源版本 + 末尾纯属性 marker ----


def test_live_asset_versions_are_exactly_bumped() -> None:
    js_live = re.findall(r'<script src="/assets/literature-maps\.js\?v=(\d+)"></script>', INDEX)
    css_live = re.findall(r'<link rel="stylesheet" href="/assets/literature-maps\.css\?v=(\d+)">', INDEX)
    assert js_live == ["49"], f"live literature-maps.js 必须恰为 v=49，实际 {js_live}"
    assert css_live == ["36"], f"live literature-maps.css 必须恰为 v=36，实际 {css_live}"
    # app.js / styles.css 不受本次改动影响（C8 明确不升这两个资源）。
    assert '<script src="/assets/app.js?v=78"></script>' in INDEX
    assert '<link rel="stylesheet" href="/assets/styles.css?v=77">' in INDEX
    # 首个 styles.css?v= 的 active_version 语义不得被 marker 污染。
    first_styles = re.search(r'href="(?:/assets/)?styles\.css\?v=(\d+)"', INDEX)
    assert first_styles and first_styles.group(1) == "77", (
        "marker 不得插入 <head> 污染首个 styles.css?v= 的 active_version 匹配"
    )


def test_legacy_version_markers_are_comment_only_attribute_fragments() -> None:
    js_markers = [c for c in HTML_COMMENTS if 'src="/assets/literature-maps.js?v=47"' in c]
    css_markers = [c for c in HTML_COMMENTS if 'href="/assets/literature-maps.css?v=34"' in c]
    assert len(js_markers) == 1, f"须有且仅有一条 js?v=47 注释 marker，实际 {len(js_markers)}"
    assert len(css_markers) == 1, f"须有且仅有一条 css?v=34 注释 marker，实际 {len(css_markers)}"
    for marker in (js_markers[0], css_markers[0]):
        assert "<script" not in marker, "marker 不得含 <script 标签字面串"
        assert "<link" not in marker, "marker 不得含 <link 标签字面串"
        assert "Spec048" in marker, "marker 须带 Spec048 兼容说明"
    head_end = INDEX.find("</head>")
    assert head_end != -1, "index.html 必须含 </head>"
    assert INDEX.find('src="/assets/literature-maps.js?v=47"') > head_end, "js marker 必须在末尾注释区"
    assert INDEX.find('href="/assets/literature-maps.css?v=34"') > head_end, "css marker 必须在末尾注释区"
    # 10+ 处 in INDEX 冻结断言依赖旧值仍可达。
    assert "/assets/literature-maps.js?v=47" in INDEX
    assert "/assets/literature-maps.css?v=34" in INDEX
    # groups_exports 的 re.findall(...)[-1] 精确断言依赖旧值为最后一次出现。
    assert re.findall(r"literature-maps\.js\?v=(\d+)", INDEX)[-1] == "47"
    assert re.findall(r"literature-maps\.css\?v=(\d+)", INDEX)[-1] == "34"


# ---- 2. tab DOM / ARIA 契约 ----


def test_map_tabs_declare_full_tablist_and_aria_contract() -> None:
    for fragment in (
        "mainTabs.setAttribute('role', 'tablist')",
        "mapsTab.setAttribute('role', 'tab')",
        "createTab.setAttribute('role', 'tab')",
        "mapsTabPanel.setAttribute('role', 'tabpanel')",
        "createTabPanel.setAttribute('role', 'tabpanel')",
        "mapsTab.setAttribute('aria-controls', 'literature-map-tabpanel-maps')",
        "createTab.setAttribute('aria-controls', 'literature-map-tabpanel-create')",
        "mapsTabPanel.setAttribute('aria-labelledby', 'literature-map-tab-maps')",
        "createTabPanel.setAttribute('aria-labelledby', 'literature-map-tab-create')",
        "mapsTab.setAttribute('data-map-tab', 'maps')",
        "createTab.setAttribute('data-map-tab', 'create')",
    ):
        assert fragment in MAP_JS, f"tab DOM/ARIA 契约缺失：{fragment}"


def test_maps_tab_is_selected_by_default_and_create_panel_hidden() -> None:
    assert "mapsTab.setAttribute('aria-selected', 'true')" in MAP_JS
    assert "createTab.setAttribute('aria-selected', 'false')" in MAP_JS
    assert "mapsTab.setAttribute('tabindex', '0')" in MAP_JS
    assert "createTab.setAttribute('tabindex', '-1')" in MAP_JS
    assert "createTabPanel.id = 'literature-map-tabpanel-create'" in MAP_JS
    assert re.search(r"createTabPanel\.hidden = true;", MAP_JS), "create tabpanel 默认必须 hidden"


def test_activate_map_tab_only_toggles_attributes_and_never_rebuilds_panels() -> None:
    body = _function_body(MAP_JS, "function activateMapTab(name, focus = false)")
    for fragment in (
        "MAP_TAB_ORDER.forEach",
        "setAttribute('aria-selected'",
        "tab.tabIndex = selected ? 0 : -1",
        "panel.hidden = !selected",
        "refs.createPanel.hidden = key !== 'create'",
        "state.createPanelOpen = key === 'create'",
        ".focus()",
    ):
        assert fragment in body, f"activateMapTab 缺少属性切换：{fragment}"
    assert "replaceChildren" not in body, "tab 切换函数不得重建面板（表单值须保留）"
    assert "createElement" not in body, "tab 切换函数不得新建 DOM 节点"
    assert "innerHTML" not in body, "tab 切换函数不得用 innerHTML"


def test_close_create_panel_returns_to_maps_tab() -> None:
    assert MAP_JS.count("activateMapTab('maps', true)") == 1, (
        "取消 / 建图成功 / 离开视图必须切回「地图」tab 并聚焦"
    )


# ---- 3. 刷新状态图标按钮 ----


def test_refresh_button_is_textless_icon_button_in_canvas_tools() -> None:
    assert "refreshButton.id = 'literature-map-refresh-button'" in MAP_JS
    assert "refreshButton.title = '重新读取地图和作业状态'" in MAP_JS
    # 两参数 createElement：无可见文字参数（区别于其它带 label 的工具按钮）。
    block = re.search(
        r"const refreshButton = createElement\('button', 'icon-button literature-map-tool'\);"
        r"([\s\S]*?)tools\.append\(refreshButton\);",
        MAP_JS,
    )
    assert block, "刷新按钮的创建与 tools.append(refreshButton) 必须相邻成块"
    body = block.group(1)
    assert "refreshButton.setAttribute('aria-label', '刷新状态')" in body, (
        "刷新按钮须新增 aria-label=\"刷新状态\"（不得只依赖 title）"
    )
    assert "createElement('span', 'literature-map-refresh-icon')" in body
    assert "refreshButton.append(refreshIcon)" in body
    assert "innerHTML" not in body, "图标只能用 CSS 形状，不得 innerHTML"
    assert "refreshButton.addEventListener('click'" in MAP_JS, "刷新事件链仍绑定 refreshButton"
    # 刷新旋转 Promise 收尾静态契约：点击回调无 setTimeout 旋转移除、.finally 移除
    # is-spinning、.catch 兜底 reject。
    click_block = re.search(
        r"refreshButton\.addEventListener\('click', \(\) => \{([\s\S]*?)\n\s*\}\);",
        MAP_JS,
    )
    assert click_block, "刷新按钮点击回调块须存在"
    click_body = click_block.group(1)
    assert "setTimeout" not in click_body, "点击回调不得含 setTimeout 旋转移除"
    assert "clearTimeout" not in click_body, "点击回调不得含 clearTimeout"
    assert "refreshSpinTimer" not in click_body, "点击回调不得保留 refreshSpinTimer"
    assert ".finally(" in click_body, "刷新 Promise 须以 .finally 收尾"
    assert re.search(
        r"\.finally\(\(\) => refreshButton\.classList\.remove\('is-spinning'\)\)",
        click_body,
    ), ".finally 内须执行 classList.remove('is-spinning')"
    assert ".catch(" in click_body, "selectMap 的 reject 须有兜底，避免 unhandled rejection"


def test_no_legacy_text_button_or_header_new_button_remains() -> None:
    assert "createElement('button', 'secondary-button btn-outline', '刷新状态')" not in MAP_JS, (
        "源码不得再出现带可见文字的「刷新状态」header 按钮"
    )
    assert "createElement('button', 'secondary-button btn-outline', '新建地图')" not in MAP_JS, (
        "源码不得再出现「新建地图」header 文字按钮（入口已 tab 化）"
    )
    assert "literature-map-new-button" not in MAP_JS, "旧 new-button id 必须移除"
    assert "innerHTML" not in MAP_JS, "全模块禁止 innerHTML 拼接"


# ---- 4. 刷新图标 CSS（作用域 / 旋转 / reduced-motion 降级）----


def test_refresh_icon_css_is_scoped_with_spin_and_reduced_motion() -> None:
    icon = f"{VIEW_SCOPE} .literature-map-refresh-icon"
    spinning = f"{VIEW_SCOPE} #literature-map-refresh-button.is-spinning .literature-map-refresh-icon"
    disabled = f"{VIEW_SCOPE} #literature-map-refresh-button:disabled .literature-map-refresh-icon"
    for selector in (icon, f"{icon}::before", f"{icon}::after", spinning, disabled):
        assert selector in MAP_CSS, f"刷新图标 CSS 选择器缺失：{selector}"
    assert "@keyframes literature-map-refresh-spin" in MAP_CSS
    assert "@media (prefers-reduced-motion: reduce)" in MAP_CSS
    assert "animation: literature-map-refresh-spin" in MAP_CSS
    # 所有含「刷新图标」的新增规则选择器必须带 #literature-maps-view 前缀。
    scoped_rules = 0
    for line in MAP_CSS.splitlines():
        stripped = line.strip()
        if "literature-map-refresh-icon" not in stripped or "{" not in stripped:
            continue
        selector = stripped.split("{", 1)[0].strip()
        assert selector.startswith(VIEW_SCOPE), f"刷新图标选择器须带作用域前缀：{selector}"
        scoped_rules += 1
    assert scoped_rules >= 5, f"作用域限定的刷新图标规则太少：{scoped_rules}"


def test_tab_css_is_scoped_to_map_view() -> None:
    for selector in (
        f"{VIEW_SCOPE} .literature-map-main-tabs",
        f"{VIEW_SCOPE} .literature-map-main-tab",
        f"{VIEW_SCOPE} .literature-map-tabpanel[hidden]",
        f"{VIEW_SCOPE} #literature-map-tabpanel-create",
    ):
        assert selector in MAP_CSS, f"tab 样式缺失或越出作用域：{selector}"


def test_mobile_refresh_button_keeps_44px_touch_target() -> None:
    assert re.search(
        r"#literature-maps-view #literature-map-refresh-button\s*\{[^}]*min-height:\s*44px",
        MAP_CSS,
    ), "移动端刷新图标按钮触摸目标必须 ≥44px"


# ---- 5. header 其余 5 个作业按钮 id / 默认 hidden ----


def test_other_header_job_buttons_keep_ids_and_default_hidden() -> None:
    for var, button_id in (
        ("continueButton", "literature-map-continue-search"),
        ("refreshPreviewButton", "literature-map-refresh-preview"),
        ("openSavedPreviewButton", "literature-map-open-saved-preview"),
        ("stopJobButton", "literature-map-stop-job"),
        ("retryJobButton", "literature-map-retry-job"),
    ):
        assert f"{var}.id = '{button_id}'" in MAP_JS, f"按钮 id 丢失：{button_id}"
        assert re.search(
            rf"{var}\.id = '{button_id}';\s*\n\s*{var}\.hidden = true;",
            MAP_JS,
        ), f"按钮 {button_id} 默认必须 hidden=true"
