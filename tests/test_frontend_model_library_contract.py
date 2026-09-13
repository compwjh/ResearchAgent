"""Static contracts for Spec035 Task06 model-library grouping (端侧 / 线上).

Reads frontend source text and asserts the DOM/CSS contract without a browser.
Mirrors the style of tests/test_frontend_management_contract.py.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")

ASSET_VERSION = 46


def test_model_library_fetches_grouped_models() -> None:
    assert "/api/models?probe=1" in APP
    assert "loadModelLibrary" in APP
    assert "getModelGroups" in APP
    assert "renderModelListItem" in APP


def test_model_library_groups_are_rendered() -> None:
    # 分组容器与标题 class 必须在 CSS 中存在（与 JS 输出逐一对应）
    assert ".model-group" in STYLES
    assert ".model-group-title" in STYLES
    # CSS 选择器带 #models-view 前缀隔离
    assert "#models-view .model-group" in STYLES
    assert "#models-view .model-group-title" in STYLES
    # 下拉使用 optgroup 分组，option.value 仍为真实 id
    assert "createElement('optgroup')" in APP
    assert "opt.value = m.id" in APP
    assert "端侧模型" in APP
    assert "线上模型" in APP


def test_model_library_status_badges_exist() -> None:
    # 状态徽标 class 必须在 CSS 中存在
    assert ".model-badge.online" in STYLES
    assert ".model-badge.failed" in STYLES
    assert "#models-view .model-badge.online" in STYLES
    assert "#models-view .model-badge.failed" in STYLES
    # 状态文案（ready / unreachable / unknown）
    assert "已连通" in APP
    assert "连接失败" in APP
    assert "未探测" in APP


def test_model_library_static_asset_version_bumped() -> None:
    assert f"/assets/app.js?v={ASSET_VERSION}" in INDEX
    assert f"/assets/styles.css?v={ASSET_VERSION}" in INDEX


def test_model_library_empty_group_shows_hint() -> None:
    # 空分组不再整组隐藏，而是始终渲染「端侧 / 线上」两个分组并给出提示
    assert ".model-group-empty" in STYLES
    assert "#models-view .model-group-empty" in STYLES
    assert "未配置线上模型" in APP
    assert "没有可用的端侧模型" in APP
    # renderModelList 内不得用 continue 跳过空分组（下拉 optgroup 的 continue 不在此列）
    start = APP.index("function renderModelList")
    end = APP.index("// ===== 知识库视图")
    renderer = APP[start:end]
    assert "continue;" not in renderer


def test_model_library_renderers_use_safe_text_boundaries() -> None:
    # renderModelList 区域（含 renderModelListItem）禁止 innerHTML 拼接模型名
    start = APP.index("function renderModelList")
    end = APP.index("// ===== 知识库视图")
    renderer = APP[start:end]
    assert "textContent" in renderer
    assert "innerHTML" not in renderer
    # 下拉构建区域同样禁止 innerHTML 拼接模型名
    opt_start = APP.index("function refreshModelOptions")
    opt_end = APP.index("function setAlias")
    optgroup_renderer = APP[opt_start:opt_end]
    assert "createElement('optgroup')" in optgroup_renderer
    assert "innerHTML" not in optgroup_renderer
    kb_start = APP.index("function refreshKbModelOptions")
    kb_end = APP.index("// 顶部 modelSelect")
    kb_renderer = APP[kb_start:kb_end]
    assert "createElement('optgroup')" in kb_renderer
    assert "innerHTML" not in kb_renderer
