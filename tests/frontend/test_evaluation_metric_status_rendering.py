"""Static contracts for evaluation metric rendering.

Every metric status (computed / degraded / needs_ground_truth / unavailable)
must be shown truthfully: value=null is never rendered as 0, the reason is
always visible, and an EVAL_NOT_COMPARABLE comparison never renders deltas.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
MODULE_MARKER = "// ===== 评测视图"


def _module() -> str:
    assert MODULE_MARKER in APP, "评测模块缺失（实现被删除时此门禁必须失败）"
    return APP[APP.index(MODULE_MARKER):]


def _function(name: str) -> str:
    """Return the brace-balanced body of `function <name>(...)`."""
    source = _module()
    start = source.index(f"function {name}(")
    brace = source.index("{", start)
    depth = 0
    for i in range(brace, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[brace:i + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def _const_block(name: str) -> str:
    source = _module()
    start = source.index(f"const {name} =")
    end = source.index("});", start)
    return source[start:end]


def test_every_metric_status_has_an_explicit_label() -> None:
    labels = _const_block("EVALUATION_STATUS_LABELS")
    for status in ("computed", "degraded", "needs_ground_truth", "unavailable"):
        assert f"{status}:" in labels, status
    assert "已计算" in labels and "降级" in labels and "缺少标注" in labels and "不可用" in labels
    assert "evaluationStatusLabel" in _module()


def test_null_value_is_never_rendered_as_zero() -> None:
    body = _function("formatEvaluationMetricValue")
    assert "metric.value === null" in body
    assert "'—'" in body
    assert "metric.status !== 'computed'" in body
    for fake_zero in ("|| 0", "?? 0", "|| 0.0", "value || 0", "Number(metric.value) || 0"):
        assert fake_zero not in body, fake_zero
    # 卡片渲染必须走这个格式化函数，不能自己兜底出 0
    card = _function("renderEvaluationMetricCard")
    assert "formatEvaluationMetricValue(metric)" in card


def test_metric_card_shows_value_status_sample_count_and_detail() -> None:
    card = _function("renderEvaluationMetricCard")
    for symbol in (
        "formatEvaluationMetricValue(metric)",
        "evaluationStatusLabel(",
        "sample_count",
        "detail",
        "reason",
        "textContent",
        "dataset.status",
    ):
        assert symbol in card, symbol
    # 不可信文本一律 textContent，不拼接进 innerHTML
    assert "innerHTML" not in card


def test_non_computed_statuses_are_visible_not_hidden_or_skipped() -> None:
    renderer = _function("renderEvaluationMetrics")
    assert "continue;" not in renderer, "不得跳过任何维度"
    assert "status !== 'computed'" not in renderer, "不得过滤掉非 computed 维度"
    assert "card.hidden" not in renderer, "不得隐藏降级维度卡片"
    for status in ("degraded", "needs_ground_truth", "unavailable"):
        assert status in _module(), status


def test_stable_error_codes_map_to_chinese_hints_and_allow_retry() -> None:
    texts = _const_block("EVALUATION_ERROR_TEXT")
    for code in (
        "EVAL_OPTION_NOT_FOUND",
        "EVAL_DATASET_INVALID",
        "EVAL_BACKEND_UNAVAILABLE",
        "EVAL_SCORE_TIMEOUT",
        "EVAL_NOT_COMPARABLE",
    ):
        assert f"{code}:" in texts, code
    assert "重试" in texts
    assert "evaluationErrorText" in _module()
    assert "disabled = false" in _module(), "失败后按钮必须恢复可重试"


def test_not_comparable_shows_reason_without_delta() -> None:
    body = _function("renderEvaluationCompare")
    assert "EVAL_NOT_COMPARABLE" in body
    assert "不可比" in body
    not_comparable_at = body.index("EVAL_NOT_COMPARABLE")
    return_at = body.index("return;", not_comparable_at)
    delta_at = body.index("delta", return_at)
    assert not_comparable_at < return_at < delta_at, "不可比分支必须早于任何 delta 渲染"
    # 不得用恒 0 delta 冒充可比结果
    assert "delta: 0" not in body and "delta || 0" not in body


def test_score_button_enters_busy_state_with_spinner_and_progress() -> None:
    module = _module()
    assert "评分中…" in module
    assert "disabled = true" in module
    assert "evaluation-spinner" in module
    assert "正在" in module
    assert "finally" in module, "无论成功失败都要解除禁用态"


def test_score_request_has_timeout_guard_not_infinite_wait() -> None:
    module = _module()
    assert "AbortController" in module
    assert "EVAL_SCORE_TIMEOUT" in module
    assert "setTimeout" in module


# ---- 追加范围三：紧凑卡片 + <details> 折叠分层静态契约 ----


def _css_rule(selector: str) -> str:
    match = re.search(
        r"#evaluation-view \." + re.escape(selector) + r"\s*\{([^}]*)\}", CSS
    )
    assert match, f"styles.css 缺少 #evaluation-view .{selector} 规则"
    return match.group(1)


def test_compact_metric_card_css_sizes() -> None:
    metrics = _css_rule("evaluation-metrics")
    assert "minmax(160px, 1fr)" in metrics, "主网格须缩到 160px"
    assert "gap: 8px" in metrics, "主网格 gap 须为 8px"
    card = _css_rule("evaluation-metric-card")
    assert "padding: 8px" in card, "卡片 padding 须为 8px"
    assert "gap: 5px" in card, "卡片 gap 须为 5px"
    assert "padding: 14px" not in card, "旧 14px padding 不得残留"
    assert "18px" in _css_rule("evaluation-metric-value"), "数值字号须为 18px"
    assert "12px" in _css_rule("evaluation-metric-label"), "标签字号须为 12px"
    assert "height: 6px" in _css_rule("evaluation-metric-bar"), "分数条须为 6px"
    group_cards = _css_rule("evaluation-metric-group-cards")
    assert "minmax(min(160px, 100%), 1fr)" in group_cards, "分组卡网格须同步"
    assert "minmax(230px, 1fr)" not in CSS, "旧 230px 网格不得残留"
    assert "minmax(min(230px, 100%), 1fr)" not in CSS, "旧分组 230px 网格不得残留"


def test_metric_card_collapses_params_in_native_details() -> None:
    card = _function("renderEvaluationMetricCard")
    assert "createElement('details')" in card, "须用原生 <details>"
    assert "createElement('summary')" in card, "须用原生 <summary>"
    assert "参数与明细" in card, "摘要文案须固定为「参数与明细」"
    # 默认收起：源码不得把 details 设成展开态（不设展开属性）
    assert ".open" not in card
    assert "open>" not in card
    assert "'open'" not in card and '"open"' not in card
    assert "setAttribute('open'" not in card
    # 按后端实际返回 key 遍历，不白名单丢弃新增字段；逐项 String(key)+textContent
    assert "Object.entries(" in card
    assert "String(key)" in card
    assert "textContent" in card
    assert "innerHTML" not in card


def test_key_information_stays_outside_details() -> None:
    card = _function("renderEvaluationMetricCard")
    assert "createElement('details')" in card
    details_at = card.index("createElement('details')")
    assert card.index("样本数：") < details_at, "sample_count 须在 details 外、始终可见"
    assert card.index("原因：") < details_at, "reason 须在 details 外、始终可见"
    assert card.index("judge_sample_count") < details_at, "判官样本数差异提示须在 details 外"
    assert "formatEvaluationMetricValue(metric)" in card
    assert "evaluationStatusLabel(" in card
    assert "key !== 'reason'" in card, "reason 须提升为始终可见、不塞进折叠区"


def test_new_param_classes_are_bidirectional_and_scoped() -> None:
    for name in (
        "evaluation-metric-params",
        "evaluation-metric-param-row",
        "evaluation-metric-detail",
        "evaluation-metric-detail-row",
    ):
        assert f"className = '{name}'" in _module(), f"app.js 未渲染 {name}"
        assert f"#evaluation-view .{name}" in CSS, f"styles.css 缺少 {name} 作用域规则"
    unscoped = re.findall(
        r"(?m)^\.(evaluation-metric-params|evaluation-metric-param-row)", CSS
    )
    assert not unscoped, f"新增 class 脱离 #evaluation-view 作用域：{unscoped}"
    params = _css_rule("evaluation-metric-params")
    assert "overflow-wrap" in params or "overflow-wrap" in _css_rule(
        "evaluation-metric-param-row"
    ), "展开明细须防横向溢出"
    assert "11px" in params or "12px" in params, "摘要字号须 ≤12px"


def test_score_request_timeout_is_900000ms() -> None:
    module = _module()
    assert "900000" in _function("submitEvaluationScore")
    assert "300000" not in module, "前端超时须与服务端 900.0s 对齐"
    assert "100 条样本真实打分" in module, "等待文案须补 100 条样本"
    assert "批量生成 + 批量判官" in module
    assert "评分中…" in module and "正在" in module, "不得打断 busy 态文案契约"


def test_new_param_rendering_uses_only_safe_dom_and_plain_text() -> None:
    card = _function("renderEvaluationMetricCard")
    for safe in (
        "createElement('details')",
        "createElement('summary')",
        "createElement('div')",
        "textContent",
    ):
        assert safe in card, safe
    # label / reason / 参数值含 <script> 时也必须纯文本展示，绝不 innerHTML
    assert "label.textContent = String(" in card
    assert "innerHTML" not in card
    assert "createElement(" in card


def test_empty_params_do_not_render_empty_details() -> None:
    card = _function("renderEvaluationMetricCard")
    assert "paramEntries.length" in card, "无参数时不得渲染空 <details>"


def test_compaction_keeps_null_emdash_and_degraded_visible() -> None:
    value = _function("formatEvaluationMetricValue")
    assert "metric.value === null" in value and "'—'" in value
    card = _function("renderEvaluationMetricCard")
    assert "formatEvaluationMetricValue(metric)" in card
    assert "|| 0" not in card and "?? 0" not in card, "不得把 null 兜底成 0"
    renderer = _function("renderEvaluationMetrics")
    assert "continue;" not in renderer and "card.hidden" not in renderer
    for status in ("degraded", "needs_ground_truth", "unavailable"):
        assert status in _module(), status
