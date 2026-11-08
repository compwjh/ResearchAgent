# -*- coding: utf-8 -*-
"""任务 J：按前端评审 BLOCK 意见修复的契约（DOM/CSS 一致性 + 结构守卫 + 行为探针）。

纯静态文本断言 + subprocess 驱动 Node 行为探针，不依赖浏览器/后端。覆盖：
  - CRITICAL：项目记忆错误态 CSS 选择器与 DOM 元素 class / id **真一致**（防再次漂移）；
  - 对接后端任务 G 新字段：available === false / error 读取、「该项目记忆不可用」、
    全量展示、空串不渲染「0 字 / 空版本」、data-state=error 视觉强调；
  - MEDIUM2：selectTask 的 finally 纳入 generation 守卫；
  - MEDIUM3：refreshWorkspace 静默返回前校验选中项仍在 state.tasks，缺失时
    复用现有清理函数收尾（helper 定义在所有静态切片之外，保证静默契约不回归）；
  - 严格边界：新增代码零 innerHTML / insertAdjacentHTML / document.write；
    既有 DOM id 不删改；版本号本批次冻结不 bump（不放宽、不 skip、不 xfail）。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
APP = (FRONTEND / "app.js").read_text(encoding="utf-8")
STYLES = (FRONTEND / "styles.css").read_text(encoding="utf-8")
RESEARCH = (FRONTEND / "research-tasks.js").read_text(encoding="utf-8")
HARNESS = Path(__file__).resolve().parent / "test_frontend_task_j_behavior.js"


def _render_body() -> str:
    """取 renderMemoryProjectDocuments 函数体（到下一个顶层 function 之前）。"""
    start = APP.index("function renderMemoryProjectDocuments")
    end = APP.index("\nfunction ", start + 10)
    return APP[start:end]


def _select_fn() -> str:
    return RESEARCH[RESEARCH.index("async function selectTask"):RESEARCH.index("async function refreshWorkspace")]


def _refresh_fn() -> str:
    return RESEARCH[RESEARCH.index("async function refreshWorkspace"):RESEARCH.index("async function createTask")]


def _helper() -> str:
    start = RESEARCH.index("function clearStaleSelection")
    end = RESEARCH.index("function taskActionButton", start)
    return RESEARCH[start:end]


# ---- 1. CRITICAL：CSS 错误态选择器 ↔ DOM 元素 class / id 真一致 ----

def test_error_status_css_selector_matches_dom_class() -> None:
    """评审 CRITICAL：CSS 用的 class 必须真实出现在状态元素的 class 属性里。

    旧实现 CSS 是 `.memory-project-documents-status[data-state="error"]`，而元素
    class 只有 `conversation-status`（仅 id 同名），规则永不匹配、失败态不变红。
    本用例不比对两个字符串各自存在，而是**解析 CSS 选择器里的类名**与
    **解析 HTML 元素的 class 集合**做集合比对，防止任一处单独漂移。
    """
    rule = re.search(
        r'#memory-view\s+\.([A-Za-z0-9_-]+)\[data-state="error"\]\s*\{([^}]*)\}',
        STYLES,
    )
    assert rule, "styles.css 必须定义 #memory-view .<class>[data-state=\"error\"] 规则"
    css_class = rule.group(1)
    assert "color" in rule.group(2), "错误态必须有颜色强调（不只是空规则）"

    tag = re.search(r'<p\b[^>]*\bid="memory-project-documents-status"[^>]*>', INDEX)
    assert tag, "index.html 必须有 id=memory-project-documents-status 的状态元素"
    class_attr = re.search(r'\bclass="([^"]*)"', tag.group(0))
    assert class_attr, "状态元素必须有 class 属性"
    dom_classes = set(class_attr.group(1).split())
    assert css_class in dom_classes, (
        f"CSS 用 .{css_class} 命中错误态，但 DOM class={sorted(dom_classes)} 不含它，"
        "选择器永不匹配（评审 CRITICAL 回归）"
    )
    assert "conversation-status" in dom_classes, "既有 conversation-status class 不得删除"

    # 元素确实位于 #memory-view 作用域内，CSS 前缀限定才成立。
    assert INDEX.index('id="memory-view"') < INDEX.index('id="memory-project-documents-status"')
    # app.js 按 id 查询该元素，并真正把 data-state 置为 error（行为闭环）。
    assert "querySelector('#memory-project-documents-status')" in APP
    assert "memoryProjectDocumentsStatus.setAttribute('data-state', 'error')" in APP


# ---- 2. 对接后端任务 G 新字段 ----

def test_memory_project_documents_read_backend_availability_flags() -> None:
    body = _render_body()
    assert "item.available === false" in body, "必须读取失败项 available=false 标记"
    assert "item.error" in body, "必须读取失败项 error 字段"
    assert "该项目记忆不可用" in body, "失败项必须显示明确的不可用文案"
    assert "setAttribute('data-state', 'error')" in body, "失败项必须用 data-state=error 强调"
    assert "memoryProjectDocumentsState.items.forEach" in body, "全量遍历（用户裁决「都展示」）"


def test_memory_project_documents_no_misleading_empty_metadata() -> None:
    body = _render_body()
    assert "${Number(item.content_length) || 0} 字" not in body, "不得无条件把空内容渲染成「0 字」"
    assert "revisionFull" in body, "空 revision 需走占位分支，不渲染「空版本」"
    assert "textContent" in body, "动态文本只用 textContent"


def test_unavailable_state_css_is_view_scoped() -> None:
    assert '#memory-view .memory-project-doc[data-state="error"]' in STYLES, (
        "失败项强调规则必须被 #memory-view 限定，且钩子由 app.js 的 setAttribute 渲染"
    )


# ---- 3. MEDIUM2：finally 纳入 generation 守卫 ----

def test_select_task_finally_is_generation_guarded() -> None:
    select_fn = _select_fn()
    assert "} finally {" in select_fn
    finally_body = select_fn[select_fn.rindex("} finally {"):]
    assert "generation === state.taskGeneration" in finally_body, (
        "finally 必须用 generation 守卫包住渲染调用，否则 A 的迟到响应会移除 B 的骨架"
    )
    guard = finally_body[finally_body.index("if (generation === state.taskGeneration)"):]
    assert "setDetailLoading(false)" in guard, "setDetailLoading 必须在守卫块内"
    assert "renderRecordsEmptyState()" in guard, "renderRecordsEmptyState 必须在守卫块内"
    assert "state.selectTaskInFlight === target" in finally_body, "target 判断保持不变"


# ---- 4. MEDIUM3：静默刷新校验选中项，缺失时清理 ----

def test_refresh_workspace_validates_selection_survival() -> None:
    refresh_fn = _refresh_fn()
    assert "if (state.selectedTaskId || state.selectedSessionId)" in refresh_fn, "保留静默返回分支"
    assert "state.tasks.some(" in refresh_fn or "tasks.some(" in refresh_fn, (
        "静默返回前必须校验选中项仍在最新 state.tasks"
    )
    assert "clearStaleSelection()" in refresh_fn, "选中项缺失时必须调用清理函数"


def test_stale_selection_cleanup_reuses_existing_renderers() -> None:
    helper = _helper()
    for call in (
        "closeStream()",
        "state.selectedTaskId = null",
        "state.selectedSessionId = null",
        "state.report = null",
        "state.matrix = null",
        "renderMatrix(null)",
        "renderReportArtifacts([])",
        "renderReportCitations([])",
        "renderReportFormatTabs()",
        "renderTaskHeader(null)",
        "setDetailVisibility(false)",
        "renderRecordsEmptyState()",
    ):
        assert call in helper, f"清理 helper 必须复用现有函数/状态清理：{call}"
    # helper 定义在 refreshWorkspace 之前 → 落在 refresh_fn 切片之外，
    # 保证 test_research_view_stability_contract.py 的「静默刷新」契约不回归。
    assert RESEARCH.index("function clearStaleSelection") < RESEARCH.index("async function refreshWorkspace")
    refresh_fn = _refresh_fn()
    for forbidden in ("state.report = null", "renderMatrix(null)", "setDetailVisibility(false)", ".replaceChildren()"):
        assert forbidden not in refresh_fn, f"清理调用不得内联回 refreshWorkspace：{forbidden}"


# ---- 5. 严格边界 ----

def test_new_code_uses_text_only_and_preserves_dom_ids() -> None:
    for chunk in (_render_body(), _helper(), _refresh_fn()):
        for bad in ("innerHTML", "insertAdjacentHTML", "document.write", "outerHTML"):
            assert bad not in chunk, f"新增代码禁止 {bad}，动态文本只用 textContent/title/setAttribute"
    for dom_id in (
        "memory-project-documents", "memory-project-documents-status",
        "memory-project-documents-list", "memory-project-documents-empty",
        "memory-project-documents-refresh", "memory-status",
    ):
        assert f'id="{dom_id}"' in INDEX, f"既有 DOM id 不得删除：{dom_id}"


def test_asset_versions_are_frozen_for_this_release_batch() -> None:
    """本任务与 B/C/D/F 同属一个发布批次，共用同一组版本号，不单独 bump。"""
    for ref in (
        'href="/assets/styles.css?v=71"',
        'src="/assets/app.js?v=73"',
        'href="/assets/literature-maps.css?v=33"',
        'src="/assets/literature-maps.js?v=46"',
        'src="/assets/research-tasks.js?v=22"',
        'src="/assets/research-session-ui.js?v=3"',
        'src="/assets/conversation-research.js?v=3"',
    ):
        assert ref in INDEX, f"本批次版本号冻结：{ref}"


def test_node_behavior_harness_passes() -> None:
    """执行级：真实 renderMemoryProjectDocuments / selectTask / refreshWorkspace 行为。"""
    node = shutil.which("node")
    assert node, "node 必须在 PATH 上（本用例不 skip，缺 node 直接失败）"
    assert HARNESS.exists(), "缺少行为探针 test_frontend_task_j_behavior.js"
    env = dict(os.environ)
    env.setdefault("NODE_OPTIONS", "")
    result = subprocess.run(
        [node, str(HARNESS)], cwd=str(ROOT), capture_output=True, text=True, timeout=120, env=env,
    )
    assert result.returncode == 0, (
        "任务 J 行为探针失败：\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "task J behavior: PASS" in result.stdout, result.stdout
