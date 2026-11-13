"""文献地图顶部操作按钮的可读性与尺寸契约（静态样式 + DOM 契约）。

背景：真实 Chromium 实测 `#literature-maps-view` 顶部 4 个按钮只有 58×28、
`font-size:10px`、文字/背景对比度 3.01:1（低于 WCAG AA 4.5:1）、触摸目标 28px。
根因是 `frontend/literature-maps.css` 把 `.literature-map-job-actions button`
的 `padding` / `font-size` 压到 `7px 9px` / `10px`，覆盖了全局 `.secondary-button`。

本用例守三件事：
1. 作用域限定的新规则存在且取值符合裁决（字号 12px / ≥36px 高 / 高对比配色 / 三态 / ≤760px 触摸 44px）；
2. **全局 `.secondary-button` 基础规则不被改动**（该 class 被会话、项目、论文、技能等视图复用）；
3. 4 个按钮的 id / 文案 / 默认显隐与事件绑定不变（只改样式，不改交互）；
4. 资源版本号已同步到生产页与同名 fixture，当前生效值见下方常量：
   `MAP_CSS_VERSION`（literature-maps.css?v=36，spec-048 升级且与 fixture 一致）、
   `APP_JS_VERSION`（app.js?v=78，合并后生产页唯一生效值）、
   `STYLES_VERSION`（styles.css?v=77，因新增 `#kb-view` 失败态/提示样式）。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")
MAP_CSS = (ROOT / "frontend/literature-maps.css").read_text(encoding="utf-8")
MAP_JS = (ROOT / "frontend/literature-maps.js").read_text(encoding="utf-8")
MAP_CSS_VERSION = 36
APP_JS_VERSION = 78
# styles.css 本批次新增 #kb-view 失败态/提示样式，生效引用现为 77。
STYLES_VERSION = 77
HEADER_ACTION_IDS = (
    "literature-map-refresh-button",
    "literature-map-continue-search",
    "literature-map-refresh-preview",
)


# 去掉 /* ... */ 注释，避免注释里的「.secondary-button」「10px」等字样参与选择器/取值解析。
MAP_CSS_NO_COMMENTS = re.sub(r"/\*[\s\S]*?\*/", "", MAP_CSS)


def _media_spans() -> list[tuple[int, int]]:
    """返回每个 @media 块的 [起始, 结束) 偏移（按花括号配对，支持嵌套）。

    简单 `@media ... { ... \n}` 正则在块内含嵌套花括号时边界会算错，故这里手工配对。
    """
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"@media[^{]*\{", MAP_CSS_NO_COMMENTS):
        depth = 0
        start = match.start()
        for index in range(match.end() - 1, len(MAP_CSS_NO_COMMENTS)):
            char = MAP_CSS_NO_COMMENTS[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    spans.append((start, index + 1))
                    break
    return spans


def _iter_rules():
    """Yield (selector, declaration block) for every flat rule in the map stylesheet."""
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", MAP_CSS_NO_COMMENTS):
        selector = match.group(1).strip()
        yield selector, match.group(2)


def _rule_blocks(selector: str, *, exact: bool = False) -> list[str]:
    """Return declaration blocks whose selector list contains ``selector``.

    ``exact=True`` 时要求选择器列表中存在**逐字相等**的单项（用于基态 vs :hover/:disabled 区分）；
    默认用子串匹配（用于「作用域内任意命中」的宽松断言）。
    """
    blocks: list[str] = []
    for whole, block in _iter_rules():
        selectors = [part.strip() for part in whole.split(",")]
        if exact:
            if selector in selectors:
                blocks.append(block)
        elif any(selector in part for part in selectors):
            blocks.append(block)
    return blocks


SCOPED_BUTTON = "#literature-maps-view .literature-map-job-actions button"
SCOPED_BUTTON_HOVER = f"{SCOPED_BUTTON}:hover"
SCOPED_BUTTON_FOCUS = f"{SCOPED_BUTTON}:focus-visible"
SCOPED_BUTTON_DISABLED = f"{SCOPED_BUTTON}:disabled"
MOBILE_BREAKPOINT = "@media (max-width: 760px)"


def _decl_of(selector: str, prop: str) -> str | None:
    """Exact-selector lookup (declaration order preserved; later blocks win)."""
    value = None
    for block in _rule_blocks(selector, exact=True):
        found = _decl(block, prop)
        if found is not None:
            value = found
    return value


def _header_action_blocks() -> list[str]:
    """All blocks targeting the header action buttons inside the map view scope."""
    return _rule_blocks(SCOPED_BUTTON, exact=False)


def _desktop_effective(prop: str) -> str | None:
    """取**桌面**（断点外）作用域按钮规则里最后声明的属性值（CSS 后者覆盖前者）。

    第 171 行的旧规则与新增覆盖规则同在选择器，后写的覆盖先写的；移动端 @media 里的
    再次覆盖不属于桌面生效值，由移动端用例单独断言。
    """
    media_spans = _media_spans()
    value = None
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", MAP_CSS_NO_COMMENTS):
        start = match.start()
        if any(lo <= start < hi for lo, hi in media_spans):
            continue
        selectors = [part.strip() for part in match.group(1).split(",")]
        if SCOPED_BUTTON not in selectors:
            continue
        found = _decl(match.group(2), prop)
        if found is not None:
            value = found
    return value


def _mobile_view_block() -> str:
    """返回 @media (max-width: 760px) 块的正文（排除注释）。"""
    match = re.search(
        r"@media\s*\(max-width:\s*760px\)\s*\{([\s\S]*?)\n\}",
        MAP_CSS_NO_COMMENTS,
    )
    assert match, "必须存在 @media (max-width: 760px) 断点"
    return match.group(1)


def _decl(block: str, prop: str) -> str | None:
    match = re.search(r"(?:^|;)\s*" + re.escape(prop) + r"\s*:\s*([^;}]+)", block)
    return match.group(1).strip() if match else None


# ---- 1. 作用域限定覆盖：尺寸 / 排版 ----


def test_header_action_buttons_meet_readable_size_and_weight():
    assert _header_action_blocks(), f"必须存在 `{SCOPED_BUTTON}` 作用域规则"
    assert _desktop_effective("font-size") == "12px", "顶部按钮最终生效字号必须为 12px（原被压到 10px）"
    assert _desktop_effective("font-weight") == "600", "顶部按钮需加粗到 600，提高可读性"
    assert _desktop_effective("padding") == "9px 14px", "顶部按钮最终生效 padding 必须为 9px 14px"
    assert _desktop_effective("min-height") == "36px", "桌面触摸目标下限必须为 36px（原实测 28px）"
    assert _desktop_effective("white-space") == "nowrap", "按钮文字不得折行（保持单行可读）"


def test_header_action_buttons_high_contrast_palette():
    assert _desktop_effective("color") == "#4a4560"
    assert _desktop_effective("background") == "#fff"
    assert _desktop_effective("border") == "1px solid #d8d2ff"
    assert _desktop_effective("border-radius") == "8px"


def test_header_action_buttons_hover_focus_and_disabled_states():
    assert _decl_of(SCOPED_BUTTON_HOVER, "background") == "#f0edff", "hover 背景必须是 #f0edff"
    assert _decl_of(SCOPED_BUTTON_HOVER, "border-color") == "var(--accent)", (
        "hover 必须同时把边框换成 var(--accent)"
    )

    assert _decl_of(SCOPED_BUTTON_FOCUS, "box-shadow") == "0 0 0 3px var(--accent-soft)", (
        "键盘 Tab 必须有可见焦点环 0 0 0 3px var(--accent-soft)"
    )

    # disabled 保留既有灰态：至少要有 opacity 或 not-allowed 之一。
    disabled_block = " ".join(_rule_blocks(SCOPED_BUTTON_DISABLED, exact=True))
    assert "opacity" in disabled_block or "not-allowed" in disabled_block, (
        "disabled 必须保留既有灰态（opacity / cursor:not-allowed 任一）"
    )


# ---- 2. 移动端：≥44px 触摸目标 + 容器收窄 gap ----


def test_mobile_breakpoint_keeps_44px_touch_target_and_tightens_gap():
    body = _mobile_view_block()
    # 断点内必须同时覆盖按钮与容器（任意一条 @media 760px 块都可能承载，故在全文里断言取值）。
    assert re.search(
        r"#literature-maps-view \.literature-map-job-actions button\s*\{[^}]*min-height:\s*44px",
        body,
    ), "移动端顶部按钮触摸目标必须 ≥44px"
    assert "#literature-maps-view .literature-map-header-actions" in body, "移动端必须收窄按钮容器"
    assert re.search(
        r"#literature-maps-view \.literature-map-header-actions\s*\{[^}]*gap:\s*6px",
        body,
    ), "移动端容器 gap 必须从 8px 收到 6px，保证 4 个按钮不溢出抽屉"
    assert re.search(
        r"#literature-maps-view \.literature-map-header-actions\s*\{[^}]*flex-wrap:\s*wrap",
        body,
    ), "移动端允许按钮换行（不横向溢出）"


# ---- 3. 全局 .secondary-button 基类不被污染 ----


def _styles_secondary_button_block() -> str:
    # styles.css 是压缩过的长行，`.secondary-button {` 前面可能是 `}` 而不是换行。
    match = re.search(r"(?:^|[\n}])\.secondary-button\s*\{([^}]*)\}", STYLES)
    assert match, "styles.css 必须保留全局 .secondary-button 基础规则"
    return match.group(1)


def test_global_secondary_button_base_rule_untouched():
    block = _styles_secondary_button_block()
    # 原值：border-radius 7px / padding 9px 12px / background var(--paper) / color var(--muted) / font-size 12px
    assert _decl(block, "padding") == "9px 12px", "全局 .secondary-button padding 不得被本次改动修改"
    # 回归点：颜色/字号仍取全局变量，说明没人把地图专属配色写进基类
    assert "var(--muted)" in block and "var(--paper)" in block
    assert _decl(block, "font-size") == "12px"


def test_map_overrides_never_target_bare_secondary_button():
    for whole, _block in _iter_rules():
        for selector in whole.split(","):
            selector = selector.strip()
            if ".secondary-button" not in selector:
                continue
            assert selector.startswith("#literature-maps-view"), (
                f"literature-maps.css 中对 .secondary-button 的覆盖必须限定在 #literature-maps-view 作用域内：{selector}"
            )


# ---- 4. 4 个按钮的 id / 文案 / 默认显隐 / 事件绑定不变 ----


def test_four_header_buttons_keep_id_text_and_hidden_contract():
    assert "createElement('div', 'literature-map-header-actions literature-map-job-actions')" in MAP_JS
    expected = {
        "literature-map-continue-search": ("继续搜索", True),
        "literature-map-refresh-preview": ("刷新预览", True),
    }
    for button_id, (text, hidden) in expected.items():
        assert f"id = '{button_id}'" in MAP_JS, f"按钮 id 契约被破坏：{button_id}"
        # 任务 C 以「追加类」方式给真实可用按钮加了 `.btn-outline`；任务 J 显式
        # 冻结该组合（评审 LOW：二选一正则删掉 btn-outline 仍会放过），删掉
        # btn-outline 会让按钮退回不可用观感。id/文案/显隐/事件仍逐字校验。
        assert re.search(
            rf"createElement\('button', 'secondary-button btn-outline', '{re.escape(text)}'\)",
            MAP_JS,
        ), f"按钮 {button_id} 必须显式带 `secondary-button btn-outline` 且文案仍为「{text}」"
        hidden_expr = "true" if hidden else None
        if hidden_expr is not None:
            assert re.search(
                rf"id = '{button_id}';\s*\n\s*\w+\.hidden = true;",
                MAP_JS,
            ), f"按钮 {button_id} 默认必须仍是 hidden=true"
    # C6：刷新按钮从 header 文字按钮改为画布工具区「无可见文字 + aria-label」图标按钮。
    # 原逐字正则 createElement('button','secondary-button btn-outline','刷新状态')
    # 按新契约改写为下列三条（均逐字比对真实源码，可失败，非恒真）。
    assert re.search(
        r"const refreshButton = createElement\('button', 'icon-button literature-map-tool'\);",
        MAP_JS,
    ), "刷新按钮必须以两参数 createElement 创建（无可见文字参数）"
    assert "createElement('button', 'secondary-button btn-outline', '刷新状态')" not in MAP_JS, (
        "header 不得再出现带可见文字的「刷新状态」文字按钮"
    )
    assert re.search(
        r"refreshButton\.setAttribute\('aria-label', '刷新状态'\);",
        MAP_JS,
    ), '刷新按钮必须新增 aria-label="刷新状态" 作为可访问名称'
    for button_id in HEADER_ACTION_IDS:
        assert button_id in MAP_JS


def test_header_button_event_bindings_are_unchanged():
    # 样式改动不得顺手改事件绑定：4 个按钮仍绑定到既有处理函数。
    pairs = {
        "literature-map-refresh-button": "refreshButton",
        "literature-map-continue-search": "continueButton",
        "literature-map-refresh-preview": "refreshPreviewButton",
    }
    for _button_id, variable in pairs.items():
        assert re.search(rf"{variable}\.addEventListener\('click'", MAP_JS), (
            f"{variable} 的 click 绑定被移除或改写"
        )


# ---- 5. 资源版本号 ----


def test_index_pins_updated_asset_versions():
    assert f'/assets/literature-maps.css?v={MAP_CSS_VERSION}"' in INDEX
    assert f'src="/assets/app.js?v={APP_JS_VERSION}"' in INDEX
    # styles.css 本批次新增了 #kb-view 的失败态/提示样式，生效引用现为 77。
    assert f'/assets/styles.css?v={STYLES_VERSION}"' in INDEX, (
        f"styles.css 内容已变，生效引用必须同步升至 {STYLES_VERSION}"
    )


def test_styles_version_bumped_whenever_kb_item_states_are_styled():
    """改 CSS 不升版本号会让浏览器继续命中旧缓存，新样式等于没交付。

    `#kb-view .kb-item-hint` 是本批次新增的提示态样式；只要它还在 styles.css 里，
    生效引用 `styles.css?v=` 就必须严格大于 68（它引入之前的版本），否则新增样式不会生效。
    """
    if "#kb-view .kb-item-hint" not in STYLES:
        # 样式被移除时可以自由回退版本号；此处只保证「有样式就必须升版本」这条不变式。
        return
    match = re.search(r'href="(?:/assets/)?styles\.css\?v=(\d+)"', INDEX)
    assert match, "index.html 缺少生效的 styles.css 引用"
    active_version = int(match.group(1))
    assert active_version > 68, (
        f"styles.css 含 #kb-view .kb-item-hint，生效版本必须 > 68，实际为 {active_version}"
    )


def test_component_fixture_pins_same_map_css_version():
    fixture = (ROOT / "tests/frontend/fixtures/literature_map_component.html").read_text(encoding="utf-8")
    assert f"literature-maps.css?v={MAP_CSS_VERSION}" in fixture
