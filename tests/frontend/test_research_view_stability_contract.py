"""任务 B：深度研究页稳定性静态契约（TDD）。

覆盖：
  - 主 tab（研究任务 / 创建研究会话）结构、默认选中、创建面板迁入 tab；
  - 既有 DOM id 全部保留（不新增/删除）；
  - 防闪烁：selectTask 保留旧详情、generation token、key 化 diff、静默刷新；
  - 空态与耗时：暂无研究任务 / 暂无执行记录 / 不显示 0.0 秒 / hydrateSession 可诊断；
  - CSS 作用域：#research-view 作用域 tab 规则，内联 style 与 styles.css 两处同步；
  - 静态资源版本号冻结（本次不 bump）。
"""
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
STYLES = (FRONTEND / "styles.css").read_text(encoding="utf-8")
RESEARCH = (FRONTEND / "research-tasks.js").read_text(encoding="utf-8")
SESSION_UI = (FRONTEND / "research-session-ui.js").read_text(encoding="utf-8")
HARNESS = Path(__file__).resolve().parent / "test_research_view_stability.js"


def _inline_style() -> str:
    """取 index.html 内联 <style id="research-tasks-inline-style"> 的内容。"""
    start = INDEX.index('<style id="research-tasks-inline-style">')
    end = INDEX.index("</style>", start)
    return INDEX[start:end]


# ---- 1. 主 tab 结构 ------------------------------------------------------
def test_research_view_has_primary_tabs_with_default_tasks_tab():
    assert 'id="research-main-tabs"' in INDEX
    assert 'role="tablist"' in INDEX
    assert 'id="research-tab-tasks"' in INDEX
    assert 'id="research-tab-create"' in INDEX
    assert '>研究任务</button>' in INDEX
    assert '>创建研究会话</button>' in INDEX
    # 默认选中「研究任务」，创建面板默认隐藏
    tasks_tab = INDEX[INDEX.index('id="research-tab-tasks"') - 200:INDEX.index('id="research-tab-tasks"') + 220]
    assert 'aria-selected="true"' in tasks_tab
    create_tab = INDEX[INDEX.index('id="research-tab-create"') - 200:INDEX.index('id="research-tab-create"') + 220]
    assert 'aria-selected="false"' in create_tab
    assert 'aria-controls="research-tabpanel-tasks"' in INDEX
    assert 'aria-controls="research-tabpanel-create"' in INDEX


def test_create_form_moved_into_tab_panel_and_existing_ids_preserved():
    # 创建面板成为 tabpanel，且标题迁入面板内
    assert 'id="research-tabpanel-create"' in INDEX
    assert 'role="tabpanel"' in INDEX
    create_marker = INDEX.index('id="research-tabpanel-create"')
    grid_marker = INDEX.index('id="research-tabpanel-tasks"')
    assert create_marker < grid_marker, "创建 tab 面板应位于三栏面板之前（顶部主 tab 顺序）"
    # 标题与所有既有 id 全部保留
    for dom_id in (
        "research-create-title", "research-create-form", "research-goal",
        "research-create-button", "research-create-status", "research-year-from",
        "research-year-to", "research-quality", "research-target-count",
        "research-language", "research-review-plan", "research-refresh-button",
        "research-task-list", "research-list-empty", "research-list-status",
        "research-detail-empty", "research-detail-status", "research-detail-title",
        "research-detail-meta", "research-report-markdown", "research-report-raw",
        "research-evidence-matrix-body", "research-timeline", "research-plan-section",
        "research-matrix-section", "research-summary-list",
    ):
        assert f'id="{dom_id}"' in INDEX, f"既有 DOM id {dom_id} 不得删除"
    # 底部独立创建面板占位已删除（research-create-panel 不再是独立 section）
    assert '<section class="research-create-panel"' not in INDEX


# ---- 2. CSS 作用域与两处同步 --------------------------------------------
def test_research_scoped_tab_css_exists_in_both_stylesheets():
    inline = _inline_style()
    for css in (STYLES, inline):
        assert "#research-view .research-main-tabs" in css, "两处 CSS 都要有 #research-view 作用域 tab 规则"
        assert 'aria-selected="true"' in css, "两处 CSS 都要有选中态 tab 规则"
        assert ".research-tabpanel[hidden]" in css, "两处 CSS 都要定义 tabpanel[hidden] 隐藏"
        assert ".is-loading" in css, "两处 CSS 都要有加载骨架态"
    assert "[data-error]" in STYLES, "hydrateSession 可诊断标记需有 CSS"
    # 不污染全局：tab 规则必须限定 #research-view
    assert "#research-view .research-main-tabs" in STYLES


# ---- 3. 防闪烁：selectTask / renderTaskList / applyEvent / refreshWorkspace -
def test_tab_switch_only_toggles_attributes_without_rebuilding_dom():
    assert "function activateResearchTab" in RESEARCH
    assert "function bindResearchTabs" in RESEARCH
    assert "aria-selected" in RESEARCH
    assert "tabIndex" in RESEARCH
    # 不重建 DOM：activateResearchTab 只改 hidden/aria-selected/tabIndex
    fn = RESEARCH[RESEARCH.index("function activateResearchTab"):RESEARCH.index("function activateResearchTab") + 1400]
    assert "replaceChildren" not in fn
    assert "createElement" not in fn
    assert "innerHTML" not in fn
    # 键盘导航
    assert "Home" in RESEARCH and "End" in RESEARCH
    assert "ArrowRight" in RESEARCH and "ArrowLeft" in RESEARCH


def test_select_task_keeps_old_detail_until_new_data_arrives():
    assert "const generation = state.taskGeneration" in RESEARCH, "需用 generation token 丢弃过期响应"
    assert "generation !== state.taskGeneration" in RESEARCH
    assert "setDetailLoading" in RESEARCH, "加载中只加 is-loading，不隐藏容器"
    assert "is-loading" in RESEARCH
    # 切换任务时不再同步清空详情 / 报告
    select_fn = RESEARCH[RESEARCH.index("async function selectTask"):RESEARCH.index("async function refreshWorkspace")]
    assert "setDetailVisibility(false)" not in select_fn, "selectTask 开头不得隐藏详情容器"
    assert "renderTaskHeader(null)" not in select_fn, "selectTask 开头不得清空详情头部"


def test_render_task_list_is_keyed_diff_not_full_rebuild():
    assert "function updateTaskCard" in RESEARCH
    assert "function createTaskCard" in RESEARCH
    render_fn = RESEARCH[RESEARCH.index("function renderTaskList"):RESEARCH.index("async function hydrateSession")]
    assert "clearNode(list)" not in render_fn, "renderTaskList 不得全量 replaceChildren"
    assert "existing" in render_fn or "byTaskId" in render_fn, "需按 taskId 复用已有节点"
    # 契约测试既有静态断言仍须保留
    assert "title.textContent = text(task.goal_excerpt" in RESEARCH
    assert "details.textContent = [" in RESEARCH
    assert ".innerHTML" not in RESEARCH


def test_apply_event_only_updates_affected_card_and_selected_detail():
    apply_fn = RESEARCH[RESEARCH.index("function applyEvent"):RESEARCH.index("function handleSseEvent")]
    assert "renderTaskList()" not in apply_fn, "SSE 每帧不得全量 renderTaskList"
    assert "updateTaskCard(" in apply_fn or "renderTaskList({ only" in apply_fn


def test_refresh_workspace_is_silent():
    """静默刷新 = 已有选中时不再重新 selectTask、不重置报告/artifacts/citations、不清空界面。

    首次进入（无选中）时的初始选中是既有 deeplink 契约（见
    test_report_action_race.js:testCurrentConversationLoadsSessionOutsideFirstHundred），
    必须保留；这里精确断言"刷新"路径的静默不变量。
    """
    refresh_fn = RESEARCH[RESEARCH.index("async function refreshWorkspace"):RESEARCH.index("async function createTask")]
    # 清空界面的元凶：这些语句一旦回归就会闪白屏 / 丢报告。
    assert "state.report = null" not in refresh_fn, "静默刷新不得重置报告"
    assert "renderMatrix(null)" not in refresh_fn, "静默刷新不得清空矩阵"
    assert "renderReportArtifacts([])" not in refresh_fn, "静默刷新不得清空 artifacts"
    assert "renderReportCitations([])" not in refresh_fn, "静默刷新不得清空 citations"
    assert "renderTaskHeader(null)" not in refresh_fn, "静默刷新不得清空详情头部"
    assert "setDetailVisibility(false)" not in refresh_fn, "静默刷新不得隐藏详情容器"
    assert "renderReportFormatTabs()" not in refresh_fn, "静默刷新不得重置报告 tabs"
    assert ".replaceChildren()" not in refresh_fn, "静默刷新不得清空报告正文"
    # 已有选中即静默返回（不重新 selectTask），且保留 in-flight 竞态保护。
    assert "if (state.selectedTaskId || state.selectedSessionId)" in refresh_fn, "已有选中必须静默返回"
    assert "if (state.selectTaskInFlight) return" in RESEARCH, "竞态保护必须保留"
    assert 'research-refresh-button' in RESEARCH, "手动刷新按钮保留"


# ---- 4. 空态与耗时 -------------------------------------------------------
def test_empty_states_are_visible_text_not_hidden_blocks():
    assert "暂无研究任务" in INDEX or "暂无研究任务" in RESEARCH
    assert "暂无执行记录" in RESEARCH
    assert "research-list-empty" in RESEARCH
    # 报告与详情区不再整体 hidden 造成空白
    assert "research-detail-empty" in RESEARCH


def test_duration_text_never_renders_zero_seconds_in_both_files():
    for source in (SESSION_UI, RESEARCH):
        assert "duration > 0" in source, "duration_ms 必须为正才显示"
        assert "end > start" in source, "时间差必须为正才显示"
        assert "0.0 秒" not in source
        assert "'—'" in source or '"—"' in source


def test_hydrate_session_errors_are_diagnosable():
    hydrate_fn = RESEARCH[RESEARCH.index("async function hydrateSession"):RESEARCH.index("async function loadTasks")]
    assert "catch (_) { /*" not in hydrate_fn, "不得静默吞错"
    assert "data-error" in hydrate_fn or "console.warn" in hydrate_fn, "需可诊断标记"
    assert "state.hydrateErrors" in RESEARCH or "data-error" in RESEARCH


# ---- 5. 版本号冻结 -------------------------------------------------------
def test_static_asset_versions_are_unchanged():
    assert "styles.css?v=71" in INDEX
    assert "app.js?v=73" in INDEX
    assert "research-tasks.js?v=25" in INDEX
    assert "research-session-ui.js?v=3" in INDEX


def test_node_behavior_harness_passes():
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node executable not found on PATH")
    assert HARNESS.exists()
    env = dict(os.environ)
    env.setdefault("NODE_OPTIONS", "")
    result = subprocess.run(
        [node, str(HARNESS)], cwd=str(ROOT), capture_output=True, text=True, timeout=120, env=env,
    )
    assert result.returncode == 0, (
        "research view stability harness 失败：\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "ok - research view stability behavior contract" in result.stdout, result.stdout
