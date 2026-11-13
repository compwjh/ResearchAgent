# -*- coding: utf-8 -*-
"""「选了项目记忆后 MEMORY.md 再也看不到」前端修复静态契约（TDD / RED → GREEN）。

纯静态文本断言（不依赖浏览器/后端）+ subprocess 驱动 node:vm 行为探针。
覆盖修复要求 1–6 与「契约测试」清单：

  - 显式返回入口：编辑器头部「返回全局 MEMORY.md」按钮（默认 hidden、仅 project 显示）、
    列表头部「跳到编辑器」锚点、列表「收起/展开」按钮（默认展开）。
  - 可读标题：memoryDocumentLabelFor 用项目名 / 短 ID，不再输出 projects/<32位id>.md。
  - 点击反馈：切换完成后滚动 + #memory-status 明确提示「返回全局」。
  - 状态同步：option 缺失时补 option、切回 global 清残留值、renderMemoryDocument 同步按钮/标题。
  - 版本号：app.js?v=78 / styles.css?v=77；其余 5 行与历史 marker 不动。
  - 护栏：不新增 <script>、不新增 innerHTML/insertAdjacentHTML/document.write、不删既有 DOM id、
    项目记忆列表默认仍展开且全量列出、既有 OCC/保存/409/作用域切换契约不回归。
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
HARNESS = Path(__file__).resolve().parent / "test_memory_return_global_behavior.js"


def _function_source(name: str, source: str = APP) -> str:
    """按花括号配平切出 app.js 中某个顶层函数源码。"""
    found = re.search(r"(?:function|async function)\s+" + re.escape(name) + r"\s*\(", source)
    assert found, f"app.js 必须定义函数 {name}"
    brace = source.index("{", found.start())
    depth = 0
    for i in range(brace, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[found.start():i + 1]
    raise AssertionError(f"unbalanced braces while extracting {name}")


def _index_region(start_id: str, end_marker: str) -> str:
    start = INDEX.index(f'id="{start_id}"')
    end = INDEX.index(end_marker, start)
    return INDEX[start:end]


# ---- 1. 显式返回入口 / 跳到编辑器 / 收起-展开 --------------------------------

def test_back_to_global_button_in_editor_header_is_hidden_by_default() -> None:
    # 按钮在记忆文档编辑器头部（memory-document-panel 内），而不是页面最顶部。
    panel = INDEX[INDEX.index('class="memory-document-panel"'):INDEX.index("</section>", INDEX.index('class="memory-document-panel"'))]
    assert 'id="memory-back-to-global"' in panel, "「返回全局 MEMORY.md」按钮必须在编辑器面板内"
    button = re.search(r'<button[^>]*id="memory-back-to-global"[^>]*>', panel)
    assert button, "返回按钮开标签"
    assert "hidden" in button.group(0), "默认隐藏（仅 scope=project 时显示）"
    assert "返回全局" in panel and "MEMORY.md" in panel, "按钮文案点明返回全局 MEMORY.md"
    # 需求 1：点击走既有 switchMemoryDocument('global', null)。
    assert "switchMemoryDocument('global', null)" in APP, "返回按钮必须复用既有切换函数"


def test_jump_to_editor_anchor_in_project_list_header() -> None:
    head = INDEX[INDEX.index('class="memory-project-documents-head"'):INDEX.index("</header>", INDEX.index('class="memory-project-documents-head"'))]
    assert 'id="memory-jump-to-editor"' in head, "项目记忆列表头部需有「跳到编辑器」锚点按钮"
    assert "编辑器" in head, "锚点文案点明跳到编辑器"
    assert "scrollIntoView" in APP, "点击锚点须把编辑器滚入视野"


def test_collapse_toggle_defaults_expanded_and_list_still_visible() -> None:
    # 用户裁决：项目记忆列表默认可见、所有 active 项目一次性列出，不隐藏、不改成下拉选择项目。
    block = re.search(r'<section[^>]*id="memory-project-documents"[^>]*>', INDEX)
    assert block, "项目记忆区块仍在"
    assert "hidden" not in block.group(0), "区块默认可见，不得 hidden"
    toggle = re.search(r'<button[^>]*id="memory-project-documents-toggle"[^>]*>', INDEX)
    assert toggle, "列表需有「收起/展开」按钮（默认展开）"
    assert 'aria-expanded="true"' in toggle.group(0), "默认展开 aria-expanded=true"
    list_tag = re.search(r'<ul[^>]*id="memory-project-documents-list"[^>]*>', INDEX)
    assert list_tag and "hidden" not in list_tag.group(0), "列表默认展开（ul 不带 hidden）"
    # 全量列出：遍历 items，不按 projectId 短路、不截断。
    assert re.search(r"memoryProjectDocumentsState\.items\.forEach|for \(const item of memoryProjectDocumentsState\.items\)", APP), \
        "仍一次性遍历全部 active 项目"
    assert "memoryProjectDocumentsState.items.slice(" not in APP, "不得截断列表"
    # 不改成「手动先选项目」：既有单文档项目下拉仍在，但列表不依赖它。
    assert 'id="memory-project-select"' in INDEX, "不删除既有项目下拉"


def test_existing_dom_ids_not_removed() -> None:
    for dom_id in (
        "memory-scope-select", "memory-project-select", "memory-project-label",
        "memory-document-editor", "memory-document-save-button", "memory-document-label",
        "memory-status", "memory-refresh-button", "system-rule-card",
        "memory-project-documents", "memory-project-documents-list",
        "memory-project-documents-empty", "memory-project-documents-status",
        "memory-project-documents-refresh",
    ):
        assert f'id="{dom_id}"' in INDEX, f"既有 DOM id 不得删除：{dom_id}"


# ---- 2. 可读标题 -------------------------------------------------------------

def test_label_uses_project_name_instead_of_raw_document_path() -> None:
    body = _function_source("memoryDocumentLabelFor")
    assert "项目记忆" in body, "project 标题标明「项目记忆」"
    assert "全局记忆" in body, "global 标题标明「全局记忆」"
    assert "MEMORY.md" in body
    assert "projects/" not in body, "不得再拼接 projects/<id>.md 长串"
    assert "projectState" in body, "项目名取自 projectState.items"
    assert "memoryProjectDocumentsState" in body, "项目名取自 memoryProjectDocumentsState.items"
    assert "formatShortHash" in body, "取不到项目名才 fallback 短 ID"
    # 32 位 ID 不得作为标题主体输出。
    assert "return `projects/${projectId}.md`" not in body


def test_click_feedback_scrolls_and_announces_back_path() -> None:
    body = _function_source("renderMemoryProjectDocuments")
    assert "scroll" in body.lower() or "announceOpenedProjectMemory" in body, "点击后须触发滚动反馈"
    assert "requestAnimationFrame" in APP or ".finally(" in APP, "滚动/反馈不得阻塞切换"
    # 明确状态提示含「返回全局」。
    assert "返回全局" in APP, "状态提示须告知返回路径"
    assert "已打开项目记忆" in APP, "状态提示须点明当前打开的是项目记忆"


# ---- 3. 状态同步 -------------------------------------------------------------

def test_state_sync_option_guard_and_clear_residual_value() -> None:
    guard = _function_source("ensureMemoryProjectOption")
    assert "option" in guard.lower(), "确认/补 option"
    assert "createElement('option')" in guard, "option 不存在时补一个"
    assert "memoryProjectSelect.value" in guard, "设值前确认 option 存在"
    # 切回全局清理残留。
    assert re.search(r"memoryProjectSelect\.value\s*=\s*''", APP), "切回全局清掉 memoryProjectSelect 残留"
    assert "memoryScopeSelect.value = 'global'" in APP, "作用域控件同步"
    assert "memoryProjectLabel.hidden = true" in APP, "项目标签隐藏"


def test_render_memory_document_syncs_back_button_and_label() -> None:
    body = _function_source("renderMemoryDocument")
    assert "memoryBackToGlobal" in body, "renderMemoryDocument 同步「返回全局」按钮显示状态"
    assert "hidden" in body, "按钮显隐随 scope 切换"
    assert "memoryDocumentLabelFor" in body, "同步当前文档标题"


# ---- 4. XSS / DOM 契约 / CSS 作用域（前端四项自查）---------------------------

def test_new_code_has_no_html_injection() -> None:
    for name in (
        "memoryDocumentLabelFor", "renderMemoryProjectDocuments", "renderMemoryDocument",
        "ensureMemoryProjectOption", "clearMemoryProjectSelection",
        "announceOpenedProjectMemory", "scrollMemoryDocumentIntoView",
        "backToGlobalMemoryDocument", "toggleMemoryProjectDocuments",
    ):
        body = _function_source(name)
        assert "innerHTML" not in body, f"{name} 禁止 innerHTML"
        assert "insertAdjacentHTML" not in body, f"{name} 禁止 insertAdjacentHTML"
        assert "document.write" not in body, f"{name} 禁止 document.write"


def test_new_classes_exist_in_scoped_css() -> None:
    # 新增 class 必须在 styles.css 存在且被 #memory-view 限定（DOM 契约 + CSS 作用域）。
    for css_class in (
        ".memory-back-to-global",
        ".memory-jump-to-editor",
        ".memory-project-documents-toggle",
        ".memory-project-documents-actions",
    ):
        assert f"#memory-view {css_class}" in STYLES, f"{css_class} 必须被 #memory-view 限定"
    # 反向：这些 class 在 index.html 被渲染。
    for css_class in ("memory-back-to-global", "memory-jump-to-editor", "memory-project-documents-toggle", "memory-project-documents-actions"):
        assert css_class in INDEX, f"{css_class} 必须在 index.html 被渲染"


def test_no_new_script_tag_and_button_count_guard() -> None:
    assert INDEX.count("<script src=") == 10, "不得新增外部 <script>"
    # 新增按钮用 .btn-outline，不引入 bare secondary-button（既有 token 计数冻结）。
    for new_id in ("memory-back-to-global", "memory-jump-to-editor", "memory-project-documents-toggle"):
        tag = re.search(r'<button[^>]*id="' + new_id + r'"[^>]*>', INDEX)
        assert tag, f"{new_id} 按钮存在"
        assert "secondary-button" not in tag.group(0), f"{new_id} 不得引入 secondary-button token"


# ---- 5. 版本号 ---------------------------------------------------------------

def test_asset_versions_bumped_and_five_others_unchanged() -> None:
    assert 'src="/assets/app.js?v=78"' in INDEX, "app.js 77 → 78"
    assert 'href="/assets/styles.css?v=77"' in INDEX, "styles.css 76 → 77"
    # 其余 5 行保持
    for ref in (
        'href="/assets/literature-maps.css?v=34"',
        'src="/assets/literature-maps.js?v=47"',
        'src="/assets/research-tasks.js?v=28"',
        'src="/assets/research-session-ui.js?v=4"',
        'src="/assets/conversation-research.js?v=3"',
    ):
        assert ref in INDEX, f"其余资源版本不得改动：{ref}"
    # 历史 marker 注释不动（保留旧兼容断言）。
    assert "app.js?v=31" in INDEX and "styles.css?v=62" in INDEX, "历史兼容 marker 不动"


def test_live_tags_no_longer_reference_old_versions() -> None:
    live_app = re.findall(r'<script src="/assets/app\.js\?v=(\d+)"', INDEX)
    live_css = re.findall(r'<link rel="stylesheet" href="/assets/styles\.css\?v=(\d+)"', INDEX)
    # 合并后生效 app.js 为 v=78、styles.css 为 v=77；评测视图各旧版本（v=74/v=75/v=76/v=77 等）
    # 仅以纯属性兼容 marker 保留在注释中，不写成完整 <script>/<link> 标签字面串。
    assert live_app == ["78"], f"生效 app.js 版本唯一且为 78：{live_app}"
    assert live_css == ["77"], f"生效 styles.css 版本唯一且为 77：{live_css}"


# ---- 6. 既有 OCC / 保存 / 409 / 作用域切换契约不回归 -------------------------

def test_existing_occ_save_conflict_scope_contracts_intact() -> None:
    # 不改 loadMemoryDocument / saveMemoryDocument / OCC / 409 契约。
    for symbol in ("loadMemoryDocument", "saveMemoryDocument", "memoryDocumentRequestMatches"):
        assert f"function {symbol}" in APP or f"async function {symbol}" in APP, f"缺失：{symbol}"
    assert "MEMORY_DOCUMENT_CONFLICT" in APP, "409 冲突码契约"
    assert "showMemoryDocumentConflict" in APP, "冲突副本展示"
    assert "refreshMemoryDocumentKeepingDraft" in APP, "保留草稿读取最新版本"
    assert "memoryDocumentQuery" in APP and "project_id" in APP, "作用域查询参数"
    assert "switchMemoryDocument('project'" in APP, "作用域切换到项目"
    assert "renderMemoryDocument()" in APP, "渲染函数仍被调用"


# ---- 7. 执行级行为探针（node:vm 真实源码）------------------------------------

def test_node_behavior_harness_passes() -> None:
    node = shutil.which("node")
    assert node, "node 必须在 PATH 上（本用例不 skip，缺 node 直接失败）"
    assert HARNESS.exists(), "缺少行为探针 test_memory_return_global_behavior.js"
    env = dict(os.environ)
    env.setdefault("NODE_OPTIONS", "")
    result = subprocess.run(
        [node, str(HARNESS)], cwd=str(ROOT), capture_output=True, text=True,
        timeout=120, env=env,
    )
    assert result.returncode == 0, (
        "记忆返回全局行为探针失败：\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "memory return-global contract: PASS" in result.stdout, result.stdout
