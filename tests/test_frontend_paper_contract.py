"""Static contracts for the security paper discovery UI.

These checks intentionally avoid a browser dependency.  They protect the DOM
boundary between the paper renderer and its scoped stylesheet while keeping
paper metadata out of HTML string injection paths.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_paper_view_has_stable_render_targets() -> None:
    required_ids = {
        "papers-view",
        "paper-search-form",
        "paper-conference-list",
        "paper-results",
        "paper-results-toolbar",
        "paper-import-panel",
        "paper-import-items",
        "paper-login-queue",
        "paper-login-items",
        "paper-conference-dialog",
        "paper-search-progress",
        "paper-source-usenix",
        "paper-source-dblp",
        "paper-pagination",
        "paper-prev-page",
        "paper-next-page",
    }
    for element_id in required_ids:
        assert f'id="{element_id}"' in INDEX


def test_paper_content_renderer_uses_safe_dom_text_boundary() -> None:
    start = APP.index("function renderPaperResults")
    end = APP.index("function jumpToKnowledgeBase", start)
    results_renderer = APP[start:end]
    assert "innerHTML" not in results_renderer
    for field in ("paper-result-title", "paper-result-meta", "paper-result-abstract"):
        assert field in results_renderer
    assert "title.textContent" in results_renderer
    assert "meta.textContent" in results_renderer
    assert "abstract.textContent" in results_renderer

    batch_start = APP.index("function renderPaperBatch")
    batch_end = APP.index("async function paperLogin", batch_start)
    batch_renderer = APP[batch_start:batch_end]
    assert "innerHTML" not in batch_renderer
    assert "title.textContent" in batch_renderer
    assert "error.textContent" in batch_renderer


def test_async_search_uses_frozen_server_pagination_contract() -> None:
    assert "fetch('/api/papers/searches'" in APP
    assert "conference_ids: conferenceIds" in APP
    assert "body: JSON.stringify({ query, conference_ids: conferenceIds, years })" in APP
    assert "/api/papers/searches/${encodeURIComponent(searchId)}/results?page=" in APP
    assert "total_pages" in APP
    assert "has_next" in APP
    assert "generation" in APP
    assert "/api/papers/search'" not in APP
    assert "cached: '已使用缓存'" in APP
    assert "checking_cache: '正在检查本地目录'" in APP
    assert "fetching: '正在从该来源获取'" in APP
    assert "merging: '正在整理元数据'" in APP


def test_paper_error_text_covers_missing_codes_and_range_details() -> None:
    # 补齐的错误码映射必须出现在前端，避免回退到无信息量的固定兜底句。
    for code in (
        "UNSUPPORTED_CONFERENCE:",
        "SEARCH_NO_RESULTS:",
        "INVALID_PAGE:",
        "CATALOG_NOT_READY:",
        "CONFERENCE_NOT_FOUND:",
        "INVALID_ACCEPTED_YEAR:",
    ):
        assert code in APP
    # showPaperError 必须能消费后端下发的年份范围，渲染"仅支持 XXXX-XXXX"。
    assert "details.min_year" in APP
    assert "details.max_year" in APP


def test_paper_app_version_bumped() -> None:
    # 改动 app.js 后必须同步递增 ?v= 版本号，确保浏览器刷新缓存（回归护栏 A7）。
    assert "/assets/app.js?v=20" in INDEX
    assert "/assets/styles.css?v=20" in INDEX


def test_paper_import_status_resets_per_round() -> None:
    # P1-1/P1-2 回归：每次导入动作必须重置本轮累加器，且汇总只聚合本轮批次，
    # 避免同会话重复"添加到知识库"时成功数翻倍、旧批次污染汇总。
    import_start = APP.index("async function importPaperCandidates")
    import_end = APP.index("function paperBatchTerminal", import_start)
    import_fn = APP[import_start:import_end]

    # P1-1：directSuccess 必须在导入起始重置块内归零。
    assert "paperState.directSuccess = 0;" in import_fn
    # 本轮其余累加器同样在起始重置（skippedImports / failedGroups / lastImportError）。
    assert "paperState.skippedImports = skipped;" in import_fn

    # P1-2：必须记录本轮 batch_id 集合，供汇总过滤旧批次。
    assert "paperState.currentRoundBatchIds" in import_fn

    # renderImportSummary 必须按本轮集合过滤，而非聚合整个 batches Map。
    summary_start = APP.index("function renderImportSummary")
    summary_end = APP.index("async function changePaperPage", summary_start)
    summary_fn = APP[summary_start:summary_end]
    assert "paperState.currentRoundBatchIds" in summary_fn


def test_paper_error_notice_and_status_states_have_css() -> None:
    # 错误提示升级为告警条，且整体状态语义色 class 必有对应 CSS 规则（regression-guard）。
    assert "#papers-view .paper-error" in STYLES
    assert "border-left: 3px solid #b42318" in STYLES
    for kind in ("running", "completed", "partial", "failed"):
        assert f"#papers-view .paper-status.is-{kind}" in STYLES


def test_paper_source_initial_placeholder_is_neutral() -> None:
    # 来源初始占位不再使用"等待开始"，改为中性"未开始"（避免与进度状态混淆）。
    assert "等待开始" not in INDEX
    assert "未开始" in INDEX


def test_paper_styles_cover_long_content_scrolling_and_focus() -> None:
    selectors = (
        "#papers-view .paper-search-form",
        "#papers-view .paper-conference-list",
        "#papers-view .paper-results",
        "#papers-view .paper-result-title",
        "#papers-view .paper-result-meta",
        "#papers-view .paper-import-items",
        "#papers-view .paper-login-queue",
        ".paper-conference-dialog",
        ".paper-conference-dialog .paper-managed-conferences",
        "#papers-view :is(button, input, textarea, select, [tabindex]):focus-visible",
    )
    for selector in selectors:
        assert selector in STYLES

    assert "overflow-wrap: anywhere" in STYLES
    assert "overflow-y: auto" in STYLES
    assert "@media (max-width: 760px)" in STYLES
    assert "@media (max-width: 430px)" in STYLES
