"""spec-032.1 Task05 — 前端 Skill 遗留（legacy）标记契约。

静态契约，避免浏览器依赖：约束 `GET /api/skills` / `GET /api/skills/{name}`
返回的布尔字段 `legacy` 在列表与详情中渲染为「遗留（待迁移）」标记。

边界：
- legacy === true 才渲染标记，false / 缺失 一律不渲染（后端未改造时容错）；
- 标记必须用 document.createElement + textContent 构造，渲染路径不得出现 innerHTML；
- 标记是纯展示，不得影响启用/禁用行为（无 hidden / disabled / 过滤逻辑）；
- CSS 作用域限定在 #skill-tool-view 与 .st-detail-dialog 内。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")

LEGACY_TEXT = "遗留（待迁移）"
BADGE_CLASS = "st-legacy-badge"


def _skill_list_renderer() -> str:
    start = APP.index("function renderSkillList")
    end = APP.index("async function loadTools", start)
    return APP[start:end]


def _skill_detail_renderer() -> str:
    start = APP.index("async function openSkillDetail")
    end = APP.index("async function loadTools", start)
    return APP[start:end]


def _legacy_helper() -> str:
    """提取共享的标记构造 helper，仅取函数体（不含解释性注释，避免误判）。"""
    start = APP.index("function buildLegacyBadge")
    end = APP.index("function renderSkillList", start)
    body = APP[start:end]
    # 去掉 // 行注释后再做「无 innerHTML」检查，注释里出现该词不算违规。
    return "\n".join(
        line for line in body.splitlines() if not line.strip().startswith("//")
    )


def test_legacy_renderer_is_shared_text_only_helper() -> None:
    """标记渲染必须集中在唯一 helper 中，且只用 textContent / DOM API。"""
    assert f"'{LEGACY_TEXT}'" in APP or f'"{LEGACY_TEXT}"' in APP
    helper = _legacy_helper()
    assert "document.createElement" in helper
    assert "classList.add('st-legacy-badge')" in helper
    assert "textContent = " in helper
    # 实现代码（非注释）不得出现 innerHTML / insertAdjacentHTML 拼接。
    assert "innerHTML" not in helper
    assert "insertAdjacentHTML" not in helper


def test_skill_list_renders_legacy_badge_for_true_only() -> None:
    renderer = _skill_list_renderer()
    # 唯一判定入口：legacy === true。
    assert "legacy === true" in renderer
    # 列表项必须挂载标记，且渲染路径无 innerHTML 拼接。
    assert BADGE_CLASS in renderer
    assert "innerHTML" not in renderer


def test_skill_detail_renders_legacy_badge_from_response_flag() -> None:
    detail = _skill_detail_renderer()
    assert "legacy === true" in detail
    assert BADGE_CLASS in detail
    # 详情标记挂在既有的 #st-detail-name 旁，不改动既有 DOM id。
    assert "stDetailName" in detail
    assert "innerHTML" not in detail


def test_legacy_field_missing_treated_as_false() -> None:
    """后端未返回 legacy 时按 false 处理：判定必须是严格 === true 等值，
    绝不能用 truthy 判断（避免 undefined/'false'/'0' 误判为真）。"""
    for renderer in (_skill_list_renderer(), _skill_detail_renderer()):
        assert "legacy === true" in renderer
        assert "Boolean(skill.legacy)" not in renderer
        assert "Boolean(data.legacy)" not in renderer
        assert re.search(r"if\s*\(\s*skill\.legacy\s*\)", renderer) is None
        assert re.search(r"if\s*\(\s*data\.legacy\s*\)", renderer) is None


def test_legacy_badge_does_not_alter_toggle_behaviour() -> None:
    """标记只是展示：不得让 legacy Skill 隐藏、禁用或改变开关语义。"""
    renderer = _skill_list_renderer()
    # 仍遍历全部 skill，不按 legacy 过滤。
    assert "for (const skill of stSkills)" in renderer
    # 启停按钮文案只看 enabled，与 legacy 无关。
    assert "skill.enabled ? '停用' : '启用'" in renderer
    # 开关按钮的 disabled 判定只依赖 name，不受 legacy 影响。
    assert "toggle.disabled = !skill.name;" in renderer


def test_legacy_badge_uses_text_content_not_html() -> None:
    """新增标记的文案必须走 textContent，不得用 innerHTML 写入。"""
    helper = _legacy_helper()
    # 标记文案通过 textContent 赋值（不是 innerHTML）。
    assert re.search(r"textContent = .*遗留", helper) is not None
    assert "innerHTML" not in helper


def test_legacy_badge_css_scoped_to_skill_tool_view() -> None:
    # 列表标记作用域限定在 #skill-tool-view 内。
    assert f"#skill-tool-view .{BADGE_CLASS}" in STYLES
    # 详情标记作用域限定在 .st-detail-dialog 内。
    assert f".st-detail-dialog .{BADGE_CLASS}" in STYLES


def test_skill_legacy_app_version_bumped() -> None:
    # 改动 app.js / styles.css 后必须同步递增 ?v=（回归护栏）。
    # spec-032.1 起点为 v39；合并时保留 origin/main 的前端契约版本（v43），旧版标记保留供历史契约消费。
    match = re.search(
        r'(?:href|src)="/assets/app\.js\?v=(\d+)"',
        INDEX,
    )
    assert match, "missing live app.js asset tag"
    assert int(match.group(1)) >= 40
    assert "/assets/app.js?v=55" in INDEX
