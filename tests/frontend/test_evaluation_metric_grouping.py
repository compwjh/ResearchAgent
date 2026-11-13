"""Static + runtime contracts for the grouped evaluation-metrics view.

Score responses now tag each ``metrics[]`` item (and each ``compare`` delta)
with a ``group``. The view must render 5 named groups + an ``other`` fallback
for legacy runs, keep every card visible (value=null -> em dash, degraded /
needs_ground_truth still show status + reason), use createElement/textContent
only (no innerHTML), bump asset versions while retaining every legacy marker,
and align the score timeout with the server's 300s budget.
"""
from __future__ import annotations

import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "frontend/app.js"
APP = APP_PATH.read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")
MODULE_MARKER = "// ===== 评测视图"

GROUP_ORDER = ("retrieval", "intent", "answer_quality", "generation", "safety", "other")
GROUP_LABELS = {
    "retrieval": "检索质量",
    "intent": "意图识别",
    "answer_quality": "回答质量",
    "generation": "生成可用性",
    "safety": "安全",
    "other": "其它维度",
}
GROUP_CLASSES = (
    "evaluation-metric-group",
    "evaluation-metric-group-title",
    "evaluation-metric-group-cards",
)

# 16 项带 group 的新指标 + 5 项历史无 group 指标 + 1 项未知 group 指标 = 22 张卡
_METRIC_GROUPS = (("retrieval", 3), ("intent", 2), ("answer_quality", 7), ("generation", 2), ("safety", 2))
GROUPED_METRICS = [
    {
        "key": f"{group}-{index}",
        "label": f"{group} 维度 {index}",
        "group": group,
        "status": "computed",
        "value": round(0.1 * (index + 1), 4),
        "sample_count": 3,
        "detail": {"note": "ok"},
    }
    for group, count in _METRIC_GROUPS
    for index in range(count)
]
LEGACY_METRICS = [
    {
        "key": f"legacy-{index}",
        "label": f"历史维度 {index}",
        "status": "computed",
        "value": 0.5,
        "sample_count": 3,
        "detail": {"note": "旧"},
    }
    for index in range(5)
]
XSS_REASON = "<script>alert(1)</script> 判官不可用"
UNKNOWN_METRIC = {
    "key": "unknown-group",
    "label": "未知分组维度",
    "group": "not_a_real_group",
    "status": "degraded",
    "value": None,
    "sample_count": 3,
    "detail": {"reason": XSS_REASON, "per_class": {"a": 1}},
}
METRICS = GROUPED_METRICS + LEGACY_METRICS + [UNKNOWN_METRIC]
DELTAS = [
    {"key": "d-retrieval", "label": "检索 delta", "group": "retrieval", "delta": 0.12},
    {"key": "d-intent", "label": "意图 delta", "group": "intent", "delta": -0.05},
    {"key": "d-legacy", "label": "历史 delta", "delta": 0.03},
]


def _module() -> str:
    assert MODULE_MARKER in APP, "评测模块缺失（实现被删除时此门禁必须失败）"
    return APP[APP.index(MODULE_MARKER):]


def _function(name: str) -> str:
    """Brace-balanced body of `(async )?function <name>(...)`."""
    source = _module()
    needle = f"function {name}("
    assert needle in source, f"缺少函数 {name}"
    start = source.index(needle)
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


# ---- (a) 分组常量与冻结标题文案 ----

def test_group_order_constant_lists_six_groups_in_order() -> None:
    module = _module()
    assert "const EVALUATION_GROUP_ORDER" in module
    start = module.index("const EVALUATION_GROUP_ORDER")
    block = module[start:module.index("]);", start) + 2]
    positions = [block.index(f"'{group}'") for group in GROUP_ORDER]
    assert positions == sorted(positions), positions


def test_group_label_constant_has_frozen_chinese_titles() -> None:
    module = _module()
    assert "const EVALUATION_GROUP_LABELS" in module
    start = module.index("const EVALUATION_GROUP_LABELS")
    block = module[start:module.index("});", start) + 3]
    for group, title in GROUP_LABELS.items():
        assert group in block, group
        assert f"'{title}'" in block, title


def test_evaluation_group_of_helper_falls_back_to_other() -> None:
    body = _function("evaluationGroupOf")
    assert "'other'" in body
    assert "EVALUATION_GROUP_ORDER" in body
    assert "String(" in body
    assert "innerHTML" not in body


# ---- (b) 分组渲染复用、无 innerHTML、CSS 双向一致 ----

def test_all_three_renderers_delegate_to_the_grouped_helper() -> None:
    for name in ("renderEvaluationMetrics", "loadEvaluationRunDetail", "renderEvaluationCompare"):
        assert "appendEvaluationGroupedRows(" in _function(name), name


def test_grouped_helper_uses_safe_dom_and_empty_groups_render_no_title() -> None:
    body = _function("appendEvaluationGroupedRows")
    assert "EVALUATION_GROUP_ORDER.forEach" in body
    assert "evaluationGroupOf(" in body
    assert "createElement(" in body
    assert "textContent" in body
    assert "String(" in body
    assert "groupRows.length === 0" in body, "空组不渲染标题"
    assert "innerHTML" not in body
    assert "renderEvaluationMetricCard" in _module(), "卡片渲染函数必须复用"


def test_evaluation_module_never_uses_innerhtml() -> None:
    module = _module()
    assert "innerHTML" not in module
    for safe in ("createElement(", "textContent", "replaceChildren()", "createElementNS("):
        assert safe in module, safe


def test_group_css_classes_are_bidirectional_and_scoped() -> None:
    module = _module()
    for name in GROUP_CLASSES:
        assert f"className = '{name}'" in module, f"app.js 未动态渲染 {name}"
        assert f"#evaluation-view .{name}" in STYLES, f"styles.css 缺少 {name} 作用域规则"
    css_new = set(re.findall(r"#evaluation-view \.(evaluation-metric-group[\w-]*)", STYLES))
    for name in css_new:
        assert f"className = '{name}'" in module or name in INDEX, name
    unscoped = re.findall(r"(?m)^\.(evaluation-metric-group[\w-]*)", STYLES)
    assert not unscoped, unscoped


def test_group_cards_grid_wraps_on_narrow_viewports() -> None:
    rule = re.search(
        r"#evaluation-view \.evaluation-metric-group-cards\s*\{([^}]*)\}", STYLES
    )
    assert rule, "缺少分组卡片网格规则"
    body = rule.group(1)
    assert "minmax(min(160px, 100%), 1fr)" in body, "分组卡网格须同步缩到 160px"
    assert "minmax(min(230px, 100%), 1fr)" not in body, "旧 230px 网格不得残留"
    assert "overflow" in body or "min-width" in body, "窄屏须用 min() 防止横向溢出"


# ---- (c) 资源版本 / 旧兼容 marker / 超时对齐 ----

def test_live_asset_versions_bumped_to_77_and_76() -> None:
    assert INDEX.count('<script src="/assets/app.js?v=78"></script>') == 1
    assert INDEX.count('<link rel="stylesheet" href="/assets/styles.css?v=77">') == 1
    # 升版前的两个精确 live 值降级为纯属性片段兼容 marker（不含 <script/<link 标签字面串）
    assert 'src="/assets/app.js?v=75"' in INDEX
    assert 'href="/assets/styles.css?v=72"' in INDEX


def test_legacy_markers_retained_and_prior_live_tags_downgraded() -> None:
    for signature in (
        "Task09/Task10 compatibility markers retained for older static contracts",
        "Legacy asset-version markers:",
        "Spec037 compatibility markers:",
        "Evaluation strategy-label fix compatibility marker",
        'href="/assets/styles.css?v=70"',
        'src="/assets/app.js?v=72"',
        'src="/assets/app.js?v=73"',
    ):
        assert signature in INDEX, signature
    # 升版前生效的两个精确标签值仍逐字作为兼容 marker 保留（旧静态合同断言）
    assert INDEX.count('href="/assets/styles.css?v=71"') == 1
    assert 'src="/assets/app.js?v=74"' in INDEX
    assert INDEX.count("<!--") >= 8


def test_score_timeout_aligned_with_server_900s() -> None:
    module = _module()
    assert "900000" in module
    assert "300000" not in module, "前端超时须与服务端 900.0s 对齐"
    score = _function("submitEvaluationScore")
    assert "900000" in score
    assert "120000" not in score
    assert "120000" not in module
    assert "多维打分可能耗时数分钟" in module
    assert "100 条样本真实打分" in module, "等待文案须补 100 条样本"
    assert "批量生成 + 批量判官" in module
    assert "评分中…" in module and "正在" in module


# ---- (d) 真实执行：22 卡按组、other 兜底、降级可见、compare 按组 ----

_NODE_HARNESS = r"""
const fs = require('fs');
const APP = fs.readFileSync(process.argv[process.argv.length - 1], 'utf8');
const MARKER = '// ===== 评测视图';
const src = APP.slice(APP.indexOf(MARKER));
const METRICS = __METRICS_JSON__;
const DELTAS = __DELTAS_JSON__;

function makeEl() {
  return {
    _children: [], childNodes: [],
    className: '', textContent: '', value: '', hidden: false,
    dataset: {}, style: {},
    classList: { add() {}, remove() {}, toggle() {} },
    replaceChildren(...args) { this._children = []; args.forEach((c) => this.appendChild(c)); },
    appendChild(c) { this._children.push(c); this.childNodes = this._children.slice(); return c; },
    append(...args) { args.forEach((c) => this.appendChild(c)); },
    setAttribute() {}, addEventListener() {}, removeEventListener() {},
    querySelector() { return null; }, querySelectorAll() { return []; },
    focus() {}, remove() {},
  };
}
const BY_ID = {};
function byId(id) { if (!BY_ID[id]) BY_ID[id] = makeEl(); return BY_ID[id]; }
global.document = {
  getElementById: byId,
  createElement: () => makeEl(),
  createElementNS: () => makeEl(),
  querySelector: () => makeEl(),
  querySelectorAll: () => [],
  addEventListener() {},
};
global.window = { location: { hash: '' }, addEventListener() {} };
global.fetch = async () => ({ ok: true, json: async () => ({}) });

const collect = (el) => {
  const own = typeof el.textContent === 'string' ? el.textContent : '';
  const kids = (el._children || []).map(collect).join('');
  return own + kids;
};
const snapshotGroups = (containerId) => document.getElementById(containerId)._children
  .filter((el) => el.className === 'evaluation-metric-group')
  .map((section) => {
    const title = section._children.find((c) => c.className === 'evaluation-metric-group-title');
    const body = section._children.find((c) => c.className === 'evaluation-metric-group-cards');
    return {
      cls: section.className,
      group: section.dataset.group,
      title: title ? collect(title) : '',
      cards: body ? body._children.length : 0,
      text: collect(section),
    };
  });

const program = src + `
;(async () => {
  renderEvaluationMetrics(METRICS);
  const groups = snapshotGroups('evaluation-metrics');
  const metricsAll = collect(document.getElementById('evaluation-metrics'));
  renderEvaluationCompare({ deltas: DELTAS }, null);
  const cmpGroups = snapshotGroups('evaluation-compare-result');
  const cmpAll = collect(document.getElementById('evaluation-compare-result'));
  renderEvaluationCompare({ comparable: false, reason: '跨 dataset' }, null);
  const notComparable = collect(document.getElementById('evaluation-compare-result'));
  const fallback = {
    missing: evaluationGroupOf({}),
    unknown: evaluationGroupOf({ group: 'bogus' }),
    retrieval: evaluationGroupOf({ group: 'retrieval' }),
    other: evaluationGroupOf({ group: 'other' }),
  };
  process.stdout.write(JSON.stringify({ groups, metricsAll, cmpGroups, cmpAll, notComparable, fallback }));
})().catch((e) => { console.error(String((e && e.stack) || e)); process.exit(1); });
`;
eval(program);
"""


@lru_cache(maxsize=1)
def _run_node_harness() -> dict:
    js = _NODE_HARNESS.replace("__METRICS_JSON__", json.dumps(METRICS, ensure_ascii=False))
    js = js.replace("__DELTAS_JSON__", json.dumps(DELTAS, ensure_ascii=False))
    proc = subprocess.run(
        ["node", "-e", js, str(APP_PATH)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"node harness 失败：{proc.stderr}"
    assert proc.stdout.strip(), "node harness 无输出"
    return json.loads(proc.stdout.strip())


def test_runtime_renders_22_cards_in_six_groups_without_dropping_any() -> None:
    result = _run_node_harness()
    groups = result["groups"]
    assert [g["group"] for g in groups] == list(GROUP_ORDER), groups
    assert [g["title"] for g in groups] == [GROUP_LABELS[g] for g in GROUP_ORDER]
    assert all(g["cls"] == "evaluation-metric-group" for g in groups)
    assert sum(g["cards"] for g in groups) == 22, groups
    for metric in METRICS:
        assert metric["label"] in result["metricsAll"], metric["label"]


def test_runtime_legacy_and_unknown_groups_fold_into_other() -> None:
    result = _run_node_harness()
    other = result["groups"][-1]
    assert other["group"] == "other"
    assert other["title"] == GROUP_LABELS["other"]
    assert other["cards"] == 6, other
    fb = result["fallback"]
    assert fb["missing"] == "other"
    assert fb["unknown"] == "other"
    assert fb["retrieval"] == "retrieval"
    assert fb["other"] == "other"


def test_runtime_degraded_status_reason_and_null_value_stay_visible() -> None:
    result = _run_node_harness()
    text = result["groups"][-1]["text"]
    assert "降级" in text, "degraded 卡片不得隐藏成关闭态"
    assert "原因" in text
    assert XSS_REASON in text, "后端文本须原样经 textContent 渲染，不得执行"
    assert "—" in text, "value=null 须显示占位符"
    assert "0.0000" not in text, "value=null 不得显示 0"


def test_runtime_compare_groups_deltas_and_keeps_not_comparable_branch() -> None:
    result = _run_node_harness()
    groups = result["cmpGroups"]
    assert [g["group"] for g in groups] == ["retrieval", "intent", "other"], groups
    assert [g["title"] for g in groups] == ["检索质量", "意图识别", "其它维度"]
    for delta_text in ("delta +0.1200", "delta -0.0500", "delta +0.0300"):
        assert delta_text in result["cmpAll"], delta_text
    assert "不可比" in result["notComparable"]
    assert "+0.1200" not in result["notComparable"]
