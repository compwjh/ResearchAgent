"""spec-023 Task08 — Skill / Tool 管理页面前端契约。

静态契约，避免浏览器依赖：保护 skill-tool 视图的 DOM 边界，并确保动态文本
（尤其 Skill body）只走 textContent，杜绝 innerHTML 注入；同时约束启用/禁用
开关走 PATCH，且 CSS 作用域限定在本视图。
"""

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
    # 改动 app.js 后必须同步递增 ?v= 版本号（回归护栏）。
    assert "/assets/app.js?v=33" in INDEX


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
