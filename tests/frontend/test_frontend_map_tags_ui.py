# -*- coding: utf-8 -*-
"""FE-1a 地图级标签系统前端 UI 静态契约检查（Spec043 Task21）。

纯静态文本断言，不需要浏览器/后端。真实 API 与浏览器 E2E 属于任务验收门禁。
只验证「DOM 契约 / 必要符号 / 端点走 request 封装 / 无 innerHTML / +N 逻辑 / CSS 作用域」。
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = (ROOT / "frontend/literature-maps.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/literature-maps.css").read_text(encoding="utf-8")


def test_tags_ui_dom_contract_container_carries_data_map_id() -> None:
    # 卡片改为容器元素承载 data-map-id（保留属性与选图行为），不再是 <button>。
    assert "createElement('div', 'literature-map-list-item')" in MODULE
    assert "createElement('button', 'literature-map-list-item')" not in MODULE
    assert "item.dataset.mapId" in MODULE  # data-map-id 保留
    # ⋯ 是 <button> 触发按钮，点击 stopPropagation，不得触发 selectMap。
    assert "createElement('button', 'literature-map-card-menu-trigger', '⋯')" in MODULE
    assert "event.stopPropagation()" in MODULE


def test_tags_ui_safe_dom_no_innerhtml_and_color_via_style() -> None:
    assert "innerHTML" not in MODULE
    # 颜色只用于 style.setProperty（色点），不拼进 HTML。
    assert "style.setProperty" in MODULE
    # 标签名只用 textContent（createElement 第三参即 textContent）。
    assert "createElement('span', 'literature-map-tag-name'" in MODULE


def test_tags_ui_required_symbols_present() -> None:
    for symbol in (
        "function loadTags",
        "function renderTagFilterBar",
        "function openTagMenu",
        "function closeTagMenu",
        "function saveMapTags",
        "function createTag",
        "function renameTag",
        "function deleteTag",
        "MAP_CARD_TAG_LIMIT = 3",
    ):
        assert symbol in MODULE


def test_tags_ui_api_endpoints_reuse_request_helper() -> None:
    # 必须复用既有 request() 封装（禁止新增 fetch / 绕过 API_ROOT）。
    assert "request('/tags')" in MODULE          # GET /tags
    assert "method: 'POST'" in MODULE           # POST /tags
    assert "method: 'PUT'" in MODULE            # PUT /{map_id}/tags
    assert "method: 'PATCH'" in MODULE          # PATCH /tags/{id}
    assert "method: 'DELETE'" in MODULE         # DELETE /tags/{id}
    assert "/tags/${tag" in MODULE              # 单标签路径（PATCH/DELETE）
    assert "tag_ids" in MODULE                  # PUT 绑定请求体
    assert MODULE.count("fetch(") == 3          # 全模块仅 3 处 fetch（request/catalog/export）


def test_tags_ui_card_badge_plus_n_logic() -> None:
    # 最多显示 3 个，超出 +N，title/aria-label 列全部名称。
    assert "slice(0, MAP_CARD_TAG_LIMIT)" in MODULE
    assert "+${extra}" in MODULE
    assert "join('、')" in MODULE


def test_tags_ui_css_classes_scoped_to_view() -> None:
    for cls in (
        ".literature-map-list-tags",
        ".literature-map-tag-chip",
        ".literature-map-tag-dot",
        ".literature-map-tag-filter-bar",
        ".literature-map-tag-filter",
        ".literature-map-card-menu",
        ".literature-map-card-menu-trigger",
    ):
        assert cls in STYLES
    assert "#literature-maps-view" in STYLES


# ---- 卡片设置两级结构（Spec043 卡片设置列表 + 重命名/删除地图，T-9）----------
# 约定：一级列表恰好 3 项（设置标签 / 重命名地图 / 删除地图），不含导出；
# 点条目在同一浮层内替换为二级内容，二级有「← 返回」；重命名走 PATCH 必须带
# expected_revision + name；删除必须先经过「取消不发请求」的二次确认。

CARD_SETTINGS_ARRAY_START = "const CARD_MENU_SETTING_ITEMS = ["


def _section(start: str, end: str) -> str:
    """取 MODULE 中 [start, end) 之间的源码片段；缺失即断言失败（不得静默跳过）。"""
    begin = MODULE.find(start)
    assert begin >= 0, f"未找到起始标记：{start}"
    finish = MODULE.find(end, begin)
    assert finish > begin, f"未找到结束标记：{end}"
    return MODULE[begin:finish]


def _section_css(start: str, end: str) -> str:
    """取 STYLES 中 [start, end) 之间的 CSS 片段；缺失即断言失败（不得静默跳过）。"""
    begin = STYLES.find(start)
    assert begin >= 0, f"CSS 未找到起始标记：{start}"
    finish = STYLES.find(end, begin + len(start))
    assert finish > begin, f"CSS 未找到结束标记：{end}"
    return STYLES[begin:finish]


def test_card_settings_list_has_exactly_three_items() -> None:
    begin = MODULE.find(CARD_SETTINGS_ARRAY_START)
    assert begin >= 0, "一级「卡片设置」条目必须由数组 CARD_MENU_SETTING_ITEMS 驱动"
    finish = MODULE.find("];", begin)
    assert finish > begin
    block = MODULE[begin:finish]
    assert block.count("{ id:") == 3, "一级列表必须恰好 3 项"
    for label in ("设置标签", "重命名地图", "删除地图"):
        assert f"'{label}'" in block, f"一级列表缺少条目：{label}"
    # 不把顶部工具栏的导出搬进卡片设置列表（明确不做）。
    assert "导出" not in block
    assert "export" not in block.lower()


def test_card_settings_trigger_renamed_keeps_dom_contract() -> None:
    assert "`卡片设置：${mapTitle(map)}`" in MODULE
    assert "`设置标签：${mapTitle(map)}`" not in MODULE
    assert "trigger.setAttribute('aria-haspopup', 'menu')" in MODULE
    trigger_section = _section("const trigger = createElement('button', 'literature-map-card-menu-trigger'", "item.append(trigger);")
    assert "event.stopPropagation();" in trigger_section
    assert "openTagMenu(map.map_id, trigger)" in trigger_section
    # ⋯ 不得触发选图：trigger 段内不得出现 selectMap 调用。
    assert "selectMap(" not in trigger_section


def test_card_settings_two_level_menu_same_overlay_with_back() -> None:
    # 二级在「同一浮层」内替换内容，而不是叠加第二个浮层。
    assert "function showTagMenuView(" in MODULE
    assert "menu._view = view;" in MODULE
    assert "menu.replaceChildren(renderMenu());" in MODULE
    # 一级/二级视图共用同一个 refs.tagMenu 容器。
    assert "menu._view = 'settings';" in MODULE
    assert "refs.tagMenu = menu;" in MODULE
    # 二级「← 返回」回到一级。
    assert "'← 返回'" in MODULE
    back_section = _section("const back = createElement('button', 'literature-map-card-menu-back'", "head.append(back,")
    assert "showTagMenuView('settings');" in back_section
    # Esc：二级退回一级，再按一次才关闭浮层。
    esc_section = _section("function handleTagMenuKeyDown(event)", "function attachTagMenuDismiss(")
    assert "menu._view !== 'settings'" in esc_section
    assert "showTagMenuView('settings');" in esc_section
    assert "closeTagMenu(true);" in esc_section
    # 切换到二级时把菜单按钮区（三个条目）换掉，而不是追加。
    assert "CARD_MENU_VIEW_CLASS" in MODULE


def test_card_settings_rename_sends_expected_revision_and_name() -> None:
    assert "function renderMapRenameForm(" in MODULE
    assert "function submitMapRename(" in MODULE
    # 预填走 input.value，不拼 HTML。
    assert "input.value = mapTitle(map);" in MODULE
    rename_section = _section("async function submitMapRename(", "// 重命名成功后手动同步本地状态与视图")
    assert "input.value || '').trim()" in rename_section, "提交前必须 trim()"
    assert "if (!name) {" in rename_section, "空名称必须在前端拦下"
    assert "name.length > MAP_NAME_MAX_LENGTH" in rename_section, "超 200 字符必须在前端拦下"
    # 两次前端拦截都必须发生在发请求之前，且直接 return（不提交）。
    guard_block = rename_section[: rename_section.find("settlePendingViewSave(")]
    assert guard_block.count("return;") >= 2
    assert "request(" not in guard_block
    assert "expected_revision: mapRevisionFor(mapId)" in rename_section
    assert "name }" in rename_section or "name," in rename_section
    assert "method: 'PATCH'" in rename_section
    assert "`/${encodeURIComponent(mapId)}`" in rename_section
    # T-7：发起前先 flush 在途视图保存，再等同一张地图的 flush 落地。
    assert "await settlePendingViewSave(mapId);" in rename_section
    settle_section = _section("async function settlePendingViewSave(", "function mapRevisionFor(")
    assert "await flushPendingViewSave();" in settle_section
    assert "await waitForPendingViewFlush(mapId);" in settle_section
    # 409 用产品文案，不透传后端 /view 文案。
    assert "const MAP_RENAME_CONFLICT_NOTICE = '地图已在别处更新，请刷新后重试';" in MODULE
    assert "地图版本或作业状态已变化" not in MODULE
    rename_error = _section("function mapRenameErrorMessage(", "function mapDeleteErrorMessage(")
    assert "return MAP_RENAME_CONFLICT_NOTICE;" in rename_error
    assert "400" in rename_error
    assert "404" in rename_error
    assert "errorAction(" in rename_error


def test_card_settings_rename_updates_local_state_without_get() -> None:
    apply_section = _section("function applyMapRenameResult(", "async function submitMapDelete(")
    # 用 PATCH 返回体的 revision 覆盖，不再 GET。
    assert "Number(updated?.revision)" in apply_section
    assert "state.maps[index] = { ...state.maps[index], ...patch };" in apply_section
    assert "state.map.revision = revision;" in apply_section
    assert "refs.currentTitle.textContent = mapTitle(state.map);" in apply_section
    assert "renderCurrentMeta();" in apply_section
    assert "renderMapList();" in apply_section
    assert "renderTagFilterBar();" in apply_section
    submit_section = _section("async function submitMapRename(", "// 重命名成功后手动同步本地状态与视图")
    assert "applyMapRenameResult(mapId, name, updated);" in submit_section
    assert "loadMaps(" not in submit_section, "不得依赖 loadMaps 重设 state.map"


def test_card_settings_delete_requires_second_confirm_without_request_on_cancel() -> None:
    confirm_render = _section("function renderMapDeleteConfirm(", "// 重命名 / 删除发起前先收口在途的视图保存")
    # 二次确认区：显示地图名 + 不可恢复提示 + 取消/删除两个按钮。
    assert "mapTitle(map)" in confirm_render
    assert "'删除后不可恢复'" in confirm_render
    assert "'取消'" in confirm_render
    assert "'删除'" in confirm_render
    cancel_section = _section("cancel.addEventListener('click'", "const confirm = createElement(")
    # 取消分支：只回一级，零请求（不发任何 PATCH/DELETE）。
    assert "showTagMenuView('settings');" in cancel_section
    assert "request(" not in cancel_section
    assert "method: 'DELETE'" not in cancel_section
    confirm_section = _section("confirm.addEventListener('click'", "actions.append(cancel, confirm);")
    assert "submitMapDelete(mapId, cancel, confirm)" in confirm_section
    # 渲染确认区本身不发请求：唯一请求点在 submitMapDelete 内。
    assert "request(" not in confirm_render.replace("submitMapDelete(mapId, cancel, confirm)", "")
    submit_delete = _section("async function submitMapDelete(", "async function finalizeMapDeletion(")
    assert "await settlePendingViewSave(mapId);" in submit_delete
    assert "method: 'DELETE'" in submit_delete
    assert "`/${encodeURIComponent(mapId)}`" in submit_delete
    # 失败时不关闭菜单（列表不变、可重试）。
    assert "closeTagMenu();" in submit_delete
    assert submit_delete.find("catch (error)") < submit_delete.find("closeTagMenu();")


def test_card_settings_delete_clears_state_and_switches_selection() -> None:
    finalize_section = _section("async function finalizeMapDeletion(", "// 无其它地图时的显式空态")
    assert "state.maps = state.maps.filter((m) => m.map_id !== mapId);" in finalize_section
    assert "await selectMap(nextMap.map_id);" in finalize_section
    assert "applyEmptyMapSelection();" in finalize_section
    # 删除未选中图：移除 + 重绘 + 重取，不改 selectedMapId。
    # Q-3②：重取要拿返回值判断是否刷新成功，故为 `const refreshed = await loadMaps();`。
    assert "const refreshed = await loadMaps();" in finalize_section
    empty_section = _section("function applyEmptyMapSelection(", "function openTagMenu(")
    for symbol in (
        "state.selectedMapId = null;",
        "state.map = null;",
        "state.graph = null;",
        "state.groups = [];",
    ):
        assert symbol in empty_section
    assert "++state.mapRequest;" in empty_section
    # 标签筛选条保留，只重算命中（标签本身仍存在）。
    assert "renderTagFilterBar();" in finalize_section


def test_card_settings_delete_refresh_failure_has_dedicated_notice() -> None:
    """P1-01（Q-3②）：删除成功但列表刷新失败时，必须给「本地已移除 + 请点刷新」专属提示。

    只断言具体字面量与分支结构（非恒真）：`loadMaps` 必须返回布尔，
    `finalizeMapDeletion` 必须据 `refreshed === false` 追加专属文案。
    """
    load_maps = _section("async function loadMaps(options = {})", "function buildCreatePayload(")
    # 成功路径与 catch 分支都必须返回布尔（默认 undefined 会让调用方无法区分）。
    assert "return true;" in load_maps
    assert "return false;" in load_maps
    # 原有通用错误提示必须保留（其它调用方仍依赖它），不得被删。
    assert "地图列表加载失败" in load_maps
    # 结构顺序：return true 在 catch 之前；return false 在 catch 分支内（catch 之后）。
    assert load_maps.find("return true;") < load_maps.find("catch (error)")
    assert load_maps.find("catch (error)") < load_maps.find("return false;")

    finalize_section = _section("async function finalizeMapDeletion(", "// 无其它地图时的显式空态")
    assert "const refreshed = await loadMaps();" in finalize_section
    # 专属文案须同时含「本地已移除」与「刷新失败 / 点刷新」两层意思。
    notice = "地图已在本地移除，但列表刷新失败，请点击刷新重新加载地图列表。"
    assert f"'{notice}'" in finalize_section
    # 失败分支必须显式判断 returned false，且用 error 状态提示。
    guard = _section("if (refreshed === false) {", "// 无其它地图时的显式空态")
    assert f"'{notice}'" in guard
    assert "setStatus(" in guard
    assert "'error'" in guard
    # 通用提示仍在 loadMaps 内，不在 finalize 里重复实现。
    assert "地图列表加载失败" not in finalize_section


def test_card_settings_delete_rename_5xx_has_own_fallback_notice() -> None:
    """P2-②（Q-3）：删除/重命名的 5xx（含无 message 的 503）不得落到「保存视图」措辞。"""
    delete_error = _section("function mapDeleteErrorMessage(", "function renderMapRenameForm(")
    rename_error = _section("function mapRenameErrorMessage(", "function mapDeleteErrorMessage(")
    # 5xx 显式分支存在，且文案是各自场景的专属兜底。
    assert "status >= 500" in delete_error
    assert "'删除失败，服务暂时不可用，请稍后重试。'" in delete_error
    assert "status >= 500" in rename_error
    assert "'重命名失败，服务暂时不可用，请稍后重试。'" in rename_error
    # 既有 404/409/400-422 分支保持原样。
    for block, literals in (
        (delete_error, ("'地图不存在或已被删除，请刷新列表后重试。'", "MAP_RENAME_CONFLICT_NOTICE", "'删除地图的请求不合法，请刷新后重试。'")),
        (rename_error, ("'地图不存在或已被删除，请刷新列表后重试。'", "MAP_RENAME_CONFLICT_NOTICE", "'地图名称不合法，请检查后重试。'")),
    ):
        for literal in literals:
            assert literal in block, f"既有分支文案被改动：{literal}"
    # 兜底之前的 5xx 分支必须排在 errorAction 之前，否则仍会走到「保存视图」。
    assert delete_error.find("status >= 500") < delete_error.find("errorAction(")
    assert rename_error.find("status >= 500") < rename_error.find("errorAction(")
    # errorAction 本身不得改：仍保留其它调用方依赖的「保存视图」兜底。
    error_action = _section("function errorAction(error, fallback)", "class LiteratureMapError")
    assert "地图版本已变化，请重新打开地图后再保存视图。" in error_action
    assert "status >= 500" not in error_action


def test_card_settings_new_css_classes_scoped_to_view() -> None:
    for cls in (
        ".literature-map-card-menu-settings",
        ".literature-map-card-menu-list",
        ".literature-map-card-menu-entry",
        ".literature-map-card-menu-panel",
        ".literature-map-card-menu-back",
        ".literature-map-card-menu-mapform",
        ".literature-map-card-menu-confirm",
        ".literature-map-card-menu-cancel",
        ".literature-map-card-menu-view-tags",
        ".literature-map-card-menu-view-rename",
        ".literature-map-card-menu-view-delete",
    ):
        assert cls in STYLES, f"CSS 缺少类：{cls}"
        assert f"#literature-maps-view {cls}" in STYLES, f"{cls} 未被 #literature-maps-view 限定"
    # 二级面板缩小后的关键取值（T-11）。
    assert "width: 200px" in STYLES
    assert "max-width: min(200px, calc(100vw - 32px))" in STYLES
    assert "max-height: 140px" in STYLES
    assert "width: min(160px, calc(100vw - 32px))" in STYLES
    assert "min-height: 32px" in STYLES


def test_card_settings_tags_panel_empty_height_compaction_css() -> None:
    """T-11 高度回归：二级「设置标签」面板空态必须 ≤105px（Chromium 1440×900 实测）。

    量到的事实链：menu 高 = 16(padding) + panel + 2(border)，而 panel 内
    `new` 表单行 44px（按钮未压缩）+ 空态 `options` 白占 1 个 gap。故锁定三条
    使其达标的规则，且必须仍以 `#literature-maps-view` 限定（不得污染全局）。
    """
    # ① 空态 options 不占位、不占 panel 的 gap；有标签时仍显示（不得用 display:none 全禁）。
    assert (
        "#literature-maps-view .literature-map-card-menu-options:empty { display: none; }" in STYLES
    ), "空态标签列表必须 :empty 隐藏以省掉一个 gap"
    # ② 新建表单行（input + 取色 + 创建按钮）压到 ≤32px。
    assert "#literature-maps-view .literature-map-card-menu-new {" in STYLES
    new_row = _section_css(".literature-map-card-menu-new {", ".literature-map-card-menu-new input[type=\"text\"]")
    assert "padding-top: 4px;" in new_row, "new 行 padding-top 必须压到 4px"
    assert "padding-top: 8px" not in new_row
    create_rule = _section_css(
        "#literature-maps-view .literature-map-card-menu-create {",
        "#literature-maps-view .literature-map-card-menu-save {",
    )
    assert "max-height: 24px;" in create_rule, "创建并绑定按钮必须压到 max-height:24px"
    assert "font-size: 9px;" in create_rule
    assert "line-height: 1.2;" in create_rule
    # ③ 二级 panel 的纵向节奏 6px → 4px（只动二级，不影响一级列表）。
    assert (
        "#literature-maps-view .literature-map-card-menu-panel { display: grid; gap: 4px; min-width: 0; }" in STYLES
    ), "二级 panel gap 必须为 4px"
    # 已达标取值不得被顺手改坏（回归护栏，与 T-11 表一致）。
    assert "#literature-maps-view .literature-map-card-menu-save { width: 100%; max-height: 28px; padding: 4px 8px; }" in STYLES


def test_position_tag_menu_clears_stale_max_width_before_measuring() -> None:
    """一级 160px 的内联 max-width 不得压住二级 200px 面板（T-11 回归）。

    `positionTagMenu()` 每次都会把实测/夹取后的宽度写回 `menu.style.maxWidth`，
    所以测量前必须先清掉上一次写入的内联宽度约束，让视图类（一级 160px / 二级 200px）
    决定目标宽度；否则二级会被压回 160px，表单换行把高度顶到 105px 以上。
    """
    body = _section("function positionTagMenu(", "function handleTagMenuPointerDown(")
    # 清约束：至少清 maxWidth，并顺带清 minWidth / width（若曾写过）。
    assert "menu.style.maxWidth = '';" in body, "测量前必须重置内联 max-width"
    # 顺序断言：重置必须发生在读取 offsetWidth / offsetHeight 之前。
    reset_at = body.find("menu.style.maxWidth = '';")
    measure_at = body.find("offsetWidth")
    assert measure_at > reset_at, "必须先清内联 max-width，再读 offsetWidth 测量"
    assert body.find("menu.style.minWidth = '';") != -1
    assert body.find("offsetHeight") > body.find("menu.style.width = '';")
    # 测量之后仍要写回 maxWidth，定位逻辑其余部分不得被削弱。
    assert body.rfind("menu.style.maxWidth") > measure_at
    assert "menu.style.maxHeight" in body
    assert "menu.style.overflow = 'auto';" in body
