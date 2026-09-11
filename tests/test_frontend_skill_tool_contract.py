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
    assert "/assets/app.js?v=26" in INDEX
