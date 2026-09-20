"""spec-023 Task08 — Skill / Tool 管理页面前端契约。

静态契约，避免浏览器依赖：保护 skill-tool 视图的 DOM 边界，并确保动态文本
（尤其 Skill body）只走 textContent，杜绝 innerHTML 注入；同时约束启用/禁用
开关走 PATCH，且 CSS 作用域限定在本视图。

spec-034 Task03 追加：Tool 列表「代码」按钮与只读源码弹窗的静态契约
（新弹窗 id 存在 + 源码只走 textContent + 无 innerHTML + 复用既有 class 不新增 CSS）。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_skill_tool_view_has_stable_render_targets() -> None:
    required_ids = {
        "skill-tool-view",
        "st-skill-list",
        "st-skill-empty",
        "st-tool-list",
        "st-tool-empty",
        "st-skill-dialog",
        "st-detail-name",
        "st-detail-desc",
        "st-detail-body",
        # spec-034 Task03：Tool 代码弹窗的渲染目标。
        "st-tool-code-dialog",
        "st-code-title",
        "st-code-name",
        "st-code-entry",
        "st-code-location",
        "st-code-body",
    }
    for element_id in required_ids:
        assert f'id="{element_id}"' in INDEX


def test_skill_tool_nav_item_present() -> None:
    # 导航项与视图切换必须接线。
    assert 'data-view="skill-tool"' in INDEX
    assert "skill-tool-view" in APP


def test_skill_renderer_uses_safe_text_boundary_no_innerhtml() -> None:
    start = APP.index("function renderSkillList")
    end = APP.index("async function loadTools", start)
    renderer = APP[start:end]
    assert "innerHTML" not in renderer
    assert "name.textContent" in renderer
    assert "desc.textContent" in renderer
    assert "tools.textContent" in renderer


def test_skill_body_rendered_as_text_not_html() -> None:
    start = APP.index("async function openSkillDetail")
    end = APP.index("async function loadTools", start)
    detail = APP[start:end]
    assert "stDetailBody" in detail
    assert "stDetailBody.textContent" in detail
    assert "innerHTML" not in detail


def test_skill_tool_toggle_calls_patch_with_enabled() -> None:
    assert "/api/skills/${encodeURIComponent(skill.name)}" in APP
    assert "/api/tools/${encodeURIComponent(tool.name)}" in APP
    assert "method: 'PATCH'" in APP
    assert "body: JSON.stringify({ enabled:" in APP


def test_skill_tool_css_scoped_to_view() -> None:
    for selector in (
        "#skill-tool-view .st-list",
        "#skill-tool-view .st-item",
        "#skill-tool-view .st-name",
        "#skill-tool-view .st-desc",
        "#skill-tool-view .st-tools",
        "#skill-tool-view .st-actions",
        "#skill-tool-view .st-status",
        "#skill-tool-view .st-empty",
        ".st-detail-dialog .st-detail-body",
    ):
        assert selector in STYLES
    # 正文需保留换行且允许长内容滚动，禁止溢出污染全局。
    assert "white-space: pre-wrap" in STYLES


def test_skill_tool_app_version_bumped() -> None:
    # 改动 app.js 后必须同步递增 ?v= 版本号（回归护栏）。spec-034 Task03：44 → 45 → 46 → 48。
    assert "/assets/app.js?v=55" in INDEX


def test_skill_detail_request_aborts_previous_inflight() -> None:
    # spec-023.1 F1：每次打开详情都中止上一次在途请求，避免并发详情请求堆积。
    start = APP.index("async function openSkillDetail")
    end = APP.index("async function loadTools", start)
    detail = APP[start:end]
    assert "AbortController" in detail
    assert "stState.detailController.abort()" in detail
    assert "signal: controller.signal" in detail
    # 请求未返回期间按钮保持禁用，防止连点。
    assert "button.disabled = false;" in detail


def test_skill_detail_discards_stale_response_writes() -> None:
    # spec-023.1 F1：慢响应后到（序号已过期或已被 abort）绝不可写 DOM。
    start = APP.index("async function openSkillDetail")
    end = APP.index("async function loadTools", start)
    detail = APP[start:end]
    # 写入前必须有令牌校验：请求序号自增、比对后才渲染。
    assert "const seq = ++stState.detailSeq;" in detail
    assert "stState.detailSeq !== seq || controller.signal.aborted" in detail
    # 成功与失败两条路径都必须先做同一身份校验再写 DOM。
    assert detail.count("stState.detailSeq !== seq || controller.signal.aborted") >= 2
    # 被中止的请求由 stFetchJson 归一化为中文「请求已取消」，不暴露英文 AbortError。
    assert "AbortError" not in detail
    assert "AbortError" in APP


def test_skill_detail_list_button_has_inflight_loading_state() -> None:
    # spec-023.1 F1：详情按钮点击后立即进入 loading 态（禁用 + 文案），避免并发重复请求。
    start = APP.index("function renderSkillList")
    end = APP.index("async function loadTools", start)
    renderer = APP[start:end]
    assert "openSkillDetail(skill.name, detailBtn)" in renderer
    assert "button.disabled = true;" in renderer
    assert "textContent = '加载中…';" in renderer


def test_fetch_helper_distinguishes_network_error_from_business_error() -> None:
    # spec-023.1 F2：fetch 抛错（断网）必须是中文可读提示，不得把 "Failed to fetch" 原文塞进状态文案。
    start = APP.index("async function stFetchJson")
    end = APP.index("// 模型库/知识库视图", start)
    helper = APP[start:end]
    # fetch 抛错分支必须重写为用户可读中文，且标记 network 供调用处区分。
    assert "await fetch(input, init)" in helper
    assert "无法连接本地服务，请确认后端已启动" in helper
    assert "networkError.network = true;" in helper
    # 主动取消走独立分支，不冒充网络错误（连点详情/切换视图时静默忽略）。
    assert "error?.name === 'AbortError'" in helper
    assert "aborted.network = false;" in helper
    # 业务错误仍沿用 stJson，保留后端 message 与 error_code。
    assert "return stJson(response);" in helper
    assert "error_code" in APP[APP.index("async function stJson"):start + len(helper)]
    # 前端任何位置都不得出现底层异常原文。
    assert "Failed to fetch" not in APP


def test_skill_detail_failure_marks_all_fields() -> None:
    # spec-023.1 F3：详情请求失败时 body/desc/tools 三个字段统一展示失败态。
    start = APP.index("async function openSkillDetail")
    end = APP.index("async function loadTools", start)
    detail = APP[start:end]
    # 失败渲染必须集中在同一分支，且三个字段都回填同一失败文案。
    assert "const failure = `加载失败：${error.message}`;" in detail
    catch_start = detail.index("catch (error)")
    catch_block = detail[catch_start:]
    for field in ("stDetailBody", "stDetailDesc", "stDetailTools"):
        assert f"{field}) {field}.textContent = failure;" in catch_block


# ===== spec-034 Task03：Tool 列表「代码」按钮与只读源码弹窗 =====

TOOL_CODE_DIALOG_MARKER = '<dialog class="settings-dialog st-detail-dialog" id="st-tool-code-dialog"'
SKILL_DIALOG_MARKER = '<dialog class="settings-dialog st-detail-dialog" id="st-skill-dialog"'


def _dialog_block(marker: str) -> str:
    start = INDEX.index(marker)
    end = INDEX.index("</dialog>", start)
    return INDEX[start:end]


def _class_tokens(block: str) -> set:
    tokens = set()
    for value in re.findall(r'class="([^"]+)"', block):
        tokens.update(value.split())
    return tokens


def _open_tool_code_source() -> str:
    start = APP.index("async function openToolCode")
    end = APP.index("function refreshModelOptions", start)
    return APP[start:end]


def test_tool_code_dialog_is_declared_and_reuses_skill_dialog_structure() -> None:
    # spec-034 Task03：新弹窗复用 Skill 详情弹窗的 class 与 <form method="dialog"> 结构。
    block = _dialog_block(TOOL_CODE_DIALOG_MARKER)
    assert 'aria-labelledby="st-code-title"' in block
    assert '<form method="dialog" class="settings-form"' in block
    assert 'value="cancel"' in block
    assert '<pre class="st-detail-body" id="st-code-body"></pre>' in block
    for element_id in ("st-code-title", "st-code-name", "st-code-entry", "st-code-location", "st-code-body"):
        assert f'id="{element_id}"' in block


def test_tool_code_dialog_introduces_no_new_class_needing_css() -> None:
    # spec-034 M-02④：新弹窗的 class 必须全部是既有 Skill 弹窗已用过的 class，
    # 因此 styles.css 无需新增规则（新增 class 未配 CSS 即回归清单第 1 条违规）。
    new_classes = _class_tokens(_dialog_block(TOOL_CODE_DIALOG_MARKER))
    existing_classes = _class_tokens(_dialog_block(SKILL_DIALOG_MARKER))
    assert new_classes, "tool code dialog must declare classes"
    assert new_classes <= existing_classes, f"unexpected new classes: {sorted(new_classes - existing_classes)}"
    # 正文样式仍由 .st-detail-dialog 作用域提供（含滚动，长源码不溢出）。
    assert ".st-detail-dialog .st-detail-body" in STYLES
    assert "max-height: 50vh" in STYLES


def test_tool_code_button_precedes_toggle_and_is_disabled_without_name() -> None:
    # spec-034 Task03：「代码」按钮位于启停按钮之前；tool.name 为空时禁用。
    start = APP.index("function renderToolList")
    end = APP.index("async function toggleTool", start)
    renderer = APP[start:end]
    assert "openToolCode(tool.name, codeBtn)" in renderer
    assert "codeBtn.disabled = !tool.name;" in renderer
    assert "actions.append(codeBtn, toggle);" in renderer
    assert renderer.index("codeBtn") < renderer.index("toggle")
    # 点击后立即进入 loading 态（禁用 + 文案），避免并发重复请求。
    assert "codeBtn.disabled = true;" in renderer
    assert "codeBtn.textContent = '加载中…';" in renderer


def test_tool_code_renderer_uses_safe_text_boundary_no_innerhtml() -> None:
    # spec-034 M-02②：源码 / entry / file:lineno 只走 textContent，禁止 innerHTML 拼接。
    source = _open_tool_code_source()
    assert "innerHTML" not in source
    assert "/api/tools/${encodeURIComponent(name)}/code" in source
    for field in ("stCodeName", "stCodeEntry", "stCodeLocation", "stCodeBody"):
        assert f"{field}.textContent" in source
    # 加载中占位文案。
    assert "stCodeBody.textContent = '加载中…';" in source


def test_tool_code_failure_marks_all_fields_with_same_message() -> None:
    # spec-034：失败时名称 / entry / location / body 统一展示同一失败文案，
    # 禁止出现「有名称 + 空白代码」的割裂展示。
    source = _open_tool_code_source()
    assert "const failure = `加载失败：${error.message}`;" in source
    catch_block = source[source.index("catch (error)"):]
    for field in ("stCodeName", "stCodeEntry", "stCodeLocation", "stCodeBody"):
        assert f"{field}.textContent = failure;" in catch_block


def test_tool_code_request_aborts_previous_inflight_and_discards_stale() -> None:
    # spec-034：连续切换不同 Tool 时，用自增序号 + AbortController 丢弃过期响应（防串台）。
    source = _open_tool_code_source()
    assert "const seq = ++stState.codeSeq;" in source
    assert "stState.codeController.abort()" in source
    assert "signal: controller.signal" in source
    # 成功与失败两条路径都必须先做同一身份校验再写 DOM。
    assert source.count("stState.codeSeq !== seq || controller.signal.aborted") >= 2
    # 被中止的请求由 stFetchJson 归一化，不在本函数内暴露英文 AbortError。
    assert "AbortError" not in source
    # 请求结束后恢复按钮可用态并清掉 controller 引用。
    assert "button.disabled = false; button.textContent = '代码';" in source
    assert "stState.codeController = null;" in source
