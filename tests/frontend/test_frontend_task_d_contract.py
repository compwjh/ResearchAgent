# -*- coding: utf-8 -*-
"""任务 D 前端静态契约：标签下拉多选 + 记忆治理项目记忆列表 + E2E 适配。

纯静态文本断言，不依赖浏览器/后端。覆盖：
  - 标签筛选：Set 多选 / OR 过滤 / 下拉浮层 / 选中优先 / 不折行 / 版本号冻结护栏。
  - 项目记忆列表：新增 DOM 区块、默认可见、调用 GET /api/memory-documents/projects、
    全量渲染、字段、空态、可诊断错误、showView('memory') 刷新、点击接线、XSS、CSS 作用域。
  - E2E：_fill_and_create 在 fill 前先点「创建研究会话」tab。
  - 严格边界：本批次版本号为冻结点；后续改 CSS 必须 bump 并同步本断言、index.html、fixture；不新增 <script>。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = (ROOT / "frontend/literature-maps.js").read_text(encoding="utf-8")
LM_CSS = (ROOT / "frontend/literature-maps.css").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
E2E = (ROOT / "tests/e2e/test_research_lifecycle_e2e.py").read_text(encoding="utf-8")


# ---- 1. 标签筛选：Set 多选 + OR 过滤 + 下拉浮层 ----

def test_tag_filter_state_is_a_set_and_or_matching() -> None:
    assert "listTagIds: new Set()" in MODULE, "筛选态必须是 Set（多选）"
    # 命中任一（OR）：集合非空时，任一已选标签命中即通过。
    assert "!state.listTagIds.size" in MODULE, "空集合不过滤"
    assert "state.listTagIds.has(tag?.tag_id)" in MODULE, "matchesTag 用 .has 做 OR 命中"
    # 再点取消语义：toggle 走 .delete / .add，不再用标量 === 覆盖。
    assert "state.listTagIds.delete(tagId)" in MODULE
    assert "state.listTagIds.add(tagId)" in MODULE
    # 切图 / 删图 / 删标签清空逻辑同步适配 Set（不得残留标量赋值）。
    assert "state.listTagIds.clear()" in MODULE
    assert "state.listTagIds.delete(tag.tag_id)" in MODULE
    assert "state.listTagId = null" not in MODULE, "不得残留标量 listTagId 赋值"
    assert "state.listTagId ===" not in MODULE


def test_tag_filter_dropdown_reuses_multiselect_panel_and_dismiss() -> None:
    for symbol in (
        "function openTagFilterMenu",
        "function closeTagFilterMenu",
        "function renderTagFilterMenu",
        "function handleTagFilterMenuPointerDown",
        "function handleTagFilterMenuKeyDown",
        "function setTagFilter",
        "function renderTagFilterBar",
        "function toggleTagFilter",
    ):
        assert symbol in MODULE, f"缺少函数：{symbol}"
    # 下拉按钮用 .btn-outline；浮层复用 checkbox 多选面板样式类。
    assert "btn-outline literature-map-tag-filter-more" in MODULE
    assert "literature-map-card-menu-options" in MODULE, "复用 checkbox 面板容器类"
    assert "'aria-expanded'" in MODULE, "更多按钮维护 aria-expanded"
    # 离开视图时关闭浮层，避免监听残留抢 Esc。
    assert "closeTagFilterMenu(false);" in MODULE
    # +N 折叠范式沿用（renderMapCardTags 的 +N 契约不破坏）。
    assert "MAP_CARD_TAG_LIMIT = 3" in MODULE
    assert "slice(0, MAP_CARD_TAG_LIMIT)" in MODULE
    assert "+${extra}" in MODULE
    assert "join('、')" in MODULE


def test_tag_filter_xss_and_request_helpers_intact() -> None:
    assert "innerHTML" not in MODULE, "literature-maps.js 全程禁止 innerHTML"
    assert MODULE.count("fetch(") == 3, "不得新增 fetch（标签多选不引入新接口）"
    assert "request('/tags')" in MODULE, "标签 CRUD 契约不变"


def test_tag_filter_css_no_wrap_and_dropdown_scoped() -> None:
    import re
    m = re.search(r"literature-map-tag-filter-list\s*\{[^}]*\}", LM_CSS)
    assert m, "缺少 .literature-map-tag-filter-list 规则"
    assert "flex-wrap: nowrap" in m.group(0), "收起态不折行"
    for cls in (
        ".literature-map-tag-filter-more",
        ".literature-map-tag-filter-count",
        ".literature-map-tag-filter-menu",
    ):
        assert f"#literature-maps-view {cls}" in LM_CSS, f"{cls} 必须被 #literature-maps-view 限定"


# ---- 2. 项目记忆列表：DOM / 接口 / 渲染 / 刷新 / 点击 ----

def test_memory_project_documents_dom_block_is_visible_by_default() -> None:
    assert 'id="memory-project-documents"' in INDEX, "新增项目记忆列表区块"
    assert 'id="memory-project-documents-list"' in INDEX
    assert 'id="memory-project-documents-empty"' in INDEX
    assert 'id="memory-project-documents-status"' in INDEX
    # 进入视图默认可见：区块不能带 hidden 属性。
    import re
    block = re.search(r'<section[^>]*id="memory-project-documents"[^>]*>', INDEX)
    assert block, "未找到项目记忆区块开标签"
    assert "hidden" not in block.group(0), "进入视图默认可见，不得 hidden"
    # 既有 DOM id 不删不改：全局编辑器 / 系统规则卡 / 作用域下拉仍在。
    for existing in ("memory-scope-select", "memory-project-select", "memory-document-editor",
                     "memory-document-save-button", "system-rule-card", "memory-refresh-button"):
        assert f'id="{existing}"' in INDEX, f"既有 DOM id 被破坏：{existing}"


def test_memory_project_documents_calls_new_endpoint() -> None:
    assert 'conversationFetch(\'/api/memory-documents/projects\')' in APP, \
        "必须调用 GET /api/memory-documents/projects（任务 A 已上线的接口）"
    for symbol in (
        "function loadMemoryProjectDocuments",
        "function renderMemoryProjectDocuments",
        "switchMemoryDocument('project'",
    ):
        assert symbol in APP, f"缺少：{symbol}"
    # 不做逐个手选：不得用单文档 projectId 分支短路隐藏列表。
    assert "memoryProjectDocumentsState" in APP


def test_memory_project_documents_render_all_active_projects_and_fields() -> None:
    # 全量渲染：遍历 items，不做 slice/截断。
    assert "memoryProjectDocumentsState.items.forEach" in APP or \
           "for (const item of memoryProjectDocumentsState.items)" in APP, \
        "必须遍历全部返回项一次性列出"
    for field in ("project_name", "document", "updated_at", "content_excerpt",
                  "content_length", "revision"):
        assert field in APP, f"缺少字段渲染：{field}"
    # 内容简版 clamp-3 + 悬浮全文；复用任务 C 工具。
    assert "clamp-3" in APP
    assert "withTooltip(" in APP
    assert "formatShortHash(" in APP


def test_memory_project_documents_empty_and_diagnosable_error() -> None:
    assert "暂无项目记忆" in APP or "暂无项目记忆" in INDEX, "空态文案"
    # 失败不得静默 catch：状态区显示可诊断错误（含 message/状态码）。
    assert "memoryProjectDocumentsState.error" in APP
    # 任务 J：把近似恒真的 `assert "'error'" in APP` 换成具体行为断言——
    # 失败态必须真正调用 setAttribute('data-state', 'error')，与 CSS 错误态钩子闭环。
    assert "memoryProjectDocumentsStatus.setAttribute('data-state', 'error')" in APP, \
        "失败态必须真正设置 data-state=error，不能只断言字符串 error 存在"
    assert "项目记忆加载失败" in APP
    assert "console.error" in APP or "console.warn" in APP, "失败需可诊断（至少 console 记录）"


def test_memory_project_documents_xss_textcontent_only() -> None:
    # 渲染函数体内不得出现 innerHTML；动态文本走 textContent。
    start = APP.find("function renderMemoryProjectDocuments(")
    assert start >= 0
    # 取到下一个顶层 function 之前的片段（粗粒度但足够覆盖渲染体）。
    nxt = APP.find("\nfunction ", start + 10)
    body = APP[start:nxt if nxt > 0 else len(APP)]
    assert "innerHTML" not in body, "项目记忆列表不得用 innerHTML 拼接"
    assert "textContent" in body, "项目名/文档名/简版用 textContent"


def test_memory_project_documents_css_scoped() -> None:
    for cls in (
        ".memory-project-documents",
        ".memory-project-documents-list",
        ".memory-project-doc",
        ".memory-project-doc-name",
        ".memory-project-doc-excerpt",
        ".memory-project-doc-open",
    ):
        assert f"#memory-view {cls}" in STYLES, f"{cls} 必须被 #memory-view 限定（不污染全局）"


def test_show_view_memory_refreshes_project_documents() -> None:
    # showView('memory') 进入时刷新列表。
    start = APP.find("if (nextView === 'memory')")
    assert start >= 0
    block = APP[start:start + 1200]
    assert "loadMemoryProjectDocuments()" in block, "进入记忆视图时刷新项目记忆列表"


# ---- 3. E2E：fill 前先点「创建研究会话」tab ----

def test_e2e_clicks_create_tab_before_fill() -> None:
    start = E2E.find("def _fill_and_create(")
    assert start >= 0
    end = E2E.find("page.fill(\"#research-goal\"", start)
    assert end >= 0, "仍存在 page.fill('#research-goal')"
    head = E2E[start:end]
    assert 'page.click("#research-tab-create")' in head or \
           "get_by_role(\"tab\"" in head, \
        "fill 之前必须先点击「创建研究会话」tab（默认 hidden 的创建面板）"


# ---- 4. 严格边界：本批次冻结点（后续改 CSS 须 bump 并同步本断言/index.html/fixture）、不新增 script 标签 ----

def test_static_asset_versions_frozen() -> None:
    freeze_note = "本批次冻结点；后续改 CSS 必须 bump 并同步本断言、index.html、fixture"
    assert 'href="/assets/styles.css?v=75"' in INDEX, freeze_note
    assert 'src="/assets/app.js?v=74"' in INDEX, freeze_note
    assert 'href="/assets/literature-maps.css?v=34"' in INDEX, freeze_note
    assert 'src="/assets/literature-maps.js?v=47"' in INDEX, freeze_note


def test_no_new_script_tag_for_memory_list() -> None:
    # 项目记忆列表不得引入新的外部 <script>（复用 app.js 内既有函数）。
    for line in INDEX.splitlines():
        if "<script" in line:
            assert "memory-project" not in line, "不得为项目记忆新增 script 标签"
