"""Static contracts for the evaluation view: DOM ids, hash deeplink, scoped CSS
and safe text boundaries.

Reads frontend source text only (no browser needed). The ids and the navigation
hash locked here are the selectors used by the E2E acceptance flow: choose a
strategy / model / dataset in the UI, press score, read per-dimension cards.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")

VIEW_HASH = "#evaluation-view"
VIEW_ID = "evaluation-view"
SELECT_IDS = (
    "evaluation-strategy-select",
    "evaluation-model-select",
    "evaluation-dataset-select",
)
SCORE_BUTTON_ID = "evaluation-score-button"
METRICS_ID = "evaluation-metrics"
MODULE_MARKER = "// ===== 评测视图"


def module_text() -> str:
    assert MODULE_MARKER in APP, "评测模块缺失（实现被删除时此门禁必须失败）"
    return APP[APP.index(MODULE_MARKER):]


def test_ninth_view_nav_item_and_container_exist() -> None:
    assert 'data-view="evaluation"' in INDEX
    assert f'href="{VIEW_HASH}"' in INDEX
    assert f'id="{VIEW_ID}"' in INDEX
    # 原 8 个视图一个都不能少
    for view in ("chat", "research", "models", "kb", "memory", "papers", "literature-maps", "skill-tool"):
        assert f'data-view="{view}"' in INDEX, view
    # hash 深链、互斥显隐接入既有 showView / MAIN_AREA_VIEW_IDS
    assert f"'{VIEW_HASH}': 'evaluation'" in APP
    assert "'evaluation-view'" in APP
    assert "nextView !== 'evaluation'" in APP


def test_three_selects_button_and_result_containers_exist() -> None:
    for element_id in (
        *SELECT_IDS,
        SCORE_BUTTON_ID,
        METRICS_ID,
        "evaluation-status",
        "evaluation-spinner",
        "evaluation-runs-list",
        "evaluation-runs-refresh",
        "evaluation-run-detail",
        "evaluation-compare-a",
        "evaluation-compare-b",
        "evaluation-compare-button",
        "evaluation-compare-result",
    ):
        assert f'id="{element_id}"' in INDEX, element_id
    assert "开始评分" in INDEX
    assert "运行历史" in INDEX
    assert "两次对比" in INDEX


def test_evaluation_endpoints_are_wired_from_the_ui() -> None:
    for endpoint in (
        "/api/evaluation/options",
        "/api/evaluation/score",
        "/api/evaluation/runs",
        "/api/evaluation/compare",
    ):
        assert endpoint in APP, endpoint
    assert "strategy_id" in APP and "dataset_id" in APP
    assert "method: 'POST'" in APP


def test_evaluation_js_never_uses_innerhtml() -> None:
    module = module_text()
    assert "innerHTML" not in module
    for safe in ("createElement(", "textContent", "replaceChildren()", "createElementNS("):
        assert safe in module, safe


def test_evaluation_classes_are_bidirectional_between_dom_and_css() -> None:
    module = module_text()
    # 正向：HTML 静态出现的 evaluation-* class 必须在 CSS 有 #evaluation-view 作用域规则
    html_classes = set()
    for match in re.finditer(r'class="([^"]+)"', INDEX):
        for token in match.group(1).split():
            if token.startswith("evaluation-"):
                html_classes.add(token)
    assert len(html_classes) >= 8, html_classes
    for name in html_classes:
        assert f"#evaluation-view .{name}" in STYLES, name

    # JS 动态创建的 class 同样必须在 CSS 中存在
    js_classes = set(re.findall(r"className = '(evaluation-[\w-]+)'", module))
    js_classes.update(re.findall(r"classList\.add\('(evaluation-[\w-]+)'\)", module))
    assert js_classes, "评测模块未动态创建任何 class"
    for name in js_classes:
        assert f"#evaluation-view .{name}" in STYLES, name

    # 反向：CSS 里的每个作用域 class 必须在 HTML 或 JS 渲染侧有对应
    css_classes = set(re.findall(r"#evaluation-view \.(evaluation-[\w-]+)", STYLES))
    assert len(css_classes) >= 8, css_classes
    for name in css_classes:
        assert name in INDEX or name in js_classes, name


def test_evaluation_css_is_scoped_and_hides_when_hidden() -> None:
    assert f"#{VIEW_ID}[hidden]" in STYLES
    unscoped = re.findall(r"(?m)^\.(evaluation-[\w-]+)", STYLES)
    assert not unscoped, unscoped


def test_svg_is_drawn_without_chart_library() -> None:
    module = module_text()
    for lib in ("chart.js", "Chart.js", "recharts", "echarts", "d3.", "vendor"):
        assert lib not in module, lib
    assert "http://www.w3.org/2000/svg" in module
