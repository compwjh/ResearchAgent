"""Static + behavioral contracts for readable evaluation strategy labels.

The backend returns ``strategy`` as an object (``{id, label, chunker, ...}``),
while ``model`` / ``dataset`` are strings. Rendering the object directly produced
the unreadable ``[object Object]`` in run history, run detail and the two
compare selects (reproduced in eval-initial.yaml / eval-scored.yaml).

These contracts (a) lock a single formatting helper, (b) lock all four render
sites to use it, and (c) execute the real module in node with an object-shaped
strategy and assert the rendered text never contains ``[object Object]`` and
always carries a readable label (or id).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "frontend/app.js"
APP = APP_PATH.read_text(encoding="utf-8")
INDEX = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
MODULE_MARKER = "// ===== 评测视图"
HELPER = "formatEvaluationStrategy"

# 真实后端快照里的对象形态 strategy（不是字符串）
OBJECT_STRATEGY = {
    "id": "topk-10",
    "label": "扩大召回（v1 / top_k=10 / reranker=off）",
    "chunker": "v1",
    "top_k": 10,
    "reranker": "off",
}
OBJECT_RUN = {
    "run_id": "eval-object-001",
    "strategy": OBJECT_STRATEGY,
    "model": "rag-retrieval",
    "dataset": "main-case",
    "created_at": "2026-11-10T03:00:00Z",
    "metrics": [],
}


def _module() -> str:
    assert MODULE_MARKER in APP, "评测模块缺失（实现被删除时此门禁必须失败）"
    return APP[APP.index(MODULE_MARKER):]


def _function_body(name: str) -> str:
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


# ---- (a) helper 契约：一律返回字符串，绝不把对象直接 String() ----


def test_strategy_helper_exists_and_never_stringifies_the_object() -> None:
    body = _function_body(HELPER)
    assert "label" in body and "id" in body, "对象形态必须优先取 label、回退 id"
    assert "'—'" in body, "空值 / 无 label+id 必须回退占位符"
    assert "typeof value === 'object'" in body or 'typeof value === "object"' in body
    assert "String(value)" not in body, "这正是 [object Object] 的根因"
    assert "return" in body


def test_helper_is_used_by_all_four_render_sites() -> None:
    renderers = (
        "renderEvaluationRunHead",       # 运行详情表
        "loadEvaluationRuns",            # 运行历史 meta
        "loadEvaluationRunDetail",       # 运行回看 head
        "fillEvaluationCompareSelects",  # 两次对比下拉
    )
    for name in renderers:
        body = _function_body(name)
        assert f"{HELPER}(" in body, f"{name} 未改用 helper"
        assert "String(run?.strategy" not in body, f"{name} 仍有裸 String(strategy)"
        assert "[run?.strategy, " not in body, f"{name} 仍把对象塞进数组插值"
    head = _function_body("renderEvaluationRunHead")
    assert "['策略', " in head
    assert "formatEvaluationStrategy(run.strategy)" in head
    assert "['策略', run.strategy]" not in head


def test_app_js_version_bumped_with_prior_exact_tag_retained() -> None:
    # 旧版本 v=74 以「纯属性 marker」形式逐字保留恰好 1 份：不得写成完整
    # <script src=...> 标签字面串，否则会被按 <script 前缀解析的 live-script
    # 静态契约误算为第二个 live 标签、污染当前版本语义。
    assert 'src="/assets/app.js?v=74"' in INDEX, "v=74 须以纯属性 marker 逐字保留"
    assert INDEX.count('src="/assets/app.js?v=74"') == 1, "v=74 纯属性 marker 须恰好 1 份"
    # 额外的加严：全文件唯一 live <script src="/assets/app.js?v=...> 标签
    # 恰好 1 个且为 v=78（含 v=75 的新兼容 marker 必须是纯属性片段、
    # 不再伪装成 live 标签，否则此断言失败）。
    live = re.findall(r'<script src="/assets/app\.js\?v=(\d+)"', INDEX)
    assert live == ["78"], f"live app.js 标签须恰好 1 个且为 v=78，实际 {live}"
    assert 'src="/assets/app.js?v=75"' in INDEX, "v=75 须以纯属性片段兼容 marker 保留"
    assert INDEX.count('src="/assets/app.js?v=73"') == 1, "旧精确标签须逐字保留恰好 1 份"
    assert 'src="/assets/app.js?v=72"' in INDEX, "legacy marker 一条都不能删"


# ---- (c) 真实执行：用对象形态 strategy 构造历史 / 详情 / 对比渲染文本 ----

_NODE_HARNESS = r"""
const fs = require('fs');
const APP = fs.readFileSync(process.argv[process.argv.length - 1], 'utf8');
const MARKER = '// ===== 评测视图';
const src = APP.slice(APP.indexOf(MARKER));
const RUN = __RUN_JSON__;
const RUNS = [RUN];

function makeEl() {
  return {
    _children: [], childNodes: [],
    className: '', textContent: '', value: '', hidden: false,
    dataset: {}, style: {},
    classList: { add() {}, remove() {}, toggle() {} },
    replaceChildren(...args) {
      this._children = [];
      args.forEach((c) => this.appendChild(c));
    },
    appendChild(c) {
      this._children.push(c);
      this.childNodes = this._children.slice();
      return c;
    },
    append(...args) { args.forEach((c) => this.appendChild(c)); },
    setAttribute() {}, addEventListener() {}, removeEventListener() {},
    querySelector() { return null; }, querySelectorAll() { return []; },
    focus() {}, remove() {},
  };
}
const BY_ID = {};
function byId(id) {
  if (!BY_ID[id]) BY_ID[id] = makeEl();
  return BY_ID[id];
}
global.document = {
  getElementById: byId,
  createElement: () => makeEl(),
  createElementNS: () => makeEl(),
  querySelector: () => makeEl(),
  querySelectorAll: () => [],
  addEventListener() {},
};
global.window = { location: { hash: '' }, addEventListener() {} };
global.fetch = async (url) => ({
  ok: true,
  json: async () => (String(url).indexOf('/runs/') >= 0 ? RUN : RUNS),
});

const collect = (el) => {
  const own = typeof el.textContent === 'string' ? el.textContent : '';
  const kids = (el._children || []).map(collect).join('');
  return own + kids;
};

const program = src + `
;(async () => {
  await loadEvaluationRuns();
  const metas = [];
  document.getElementById('evaluation-runs-list')._children.forEach((item) => {
    item._children.forEach((child) => {
      if (child.className === 'evaluation-run-item-meta') metas.push(collect(child));
    });
  });
  const opts = [];
  ['evaluation-compare-a', 'evaluation-compare-b'].forEach((id) => {
    document.getElementById(id)._children.forEach((o) => opts.push(collect(o)));
  });
  renderEvaluationRunHead(RUN);
  const runHead = document.getElementById('evaluation-run-head')._children
    .map(collect).join(' | ');
  await loadEvaluationRunDetail(RUN.run_id);
  const detail = document.getElementById('evaluation-run-detail')._children
    .filter((c) => c.className === 'evaluation-detail-head')
    .map(collect).join(' | ');

  const helperShapes = typeof formatEvaluationStrategy === 'function'
    ? [
        { shape: 'object-with-label', v: formatEvaluationStrategy(RUN.strategy) },
        { shape: 'object-id-only', v: formatEvaluationStrategy({ id: 'topk-10' }) },
        { shape: 'object-empty', v: formatEvaluationStrategy({}) },
        { shape: 'null', v: formatEvaluationStrategy(null) },
        { shape: 'undefined', v: formatEvaluationStrategy(undefined) },
        { shape: 'string', v: formatEvaluationStrategy('legacy-string') },
      ].map((r) => ({ shape: r.shape, type: typeof r.v, text: r.v }))
    : null;

  process.stdout.write(JSON.stringify({ metas, opts, runHead, detail, helperShapes }));
})().catch((e) => { console.error(String((e && e.stack) || e)); process.exit(1); });
`;
eval(program);
"""


def _run_node_harness() -> dict:
    js = _NODE_HARNESS.replace("__RUN_JSON__", json.dumps(OBJECT_RUN, ensure_ascii=False))
    proc = subprocess.run(
        ["node", "-e", js, str(APP_PATH)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"node harness 失败：{proc.stderr}"
    assert proc.stdout.strip(), "node harness 无输出"
    return json.loads(proc.stdout.strip())


def test_object_strategy_history_detail_compare_text_is_readable() -> None:
    result = _run_node_harness()
    label, sid = OBJECT_STRATEGY["label"], OBJECT_STRATEGY["id"]
    metas = result["metas"]
    option_texts = [t for t in result["opts"] if "eval-object-001" in t]
    assert metas, "运行历史未渲染任何 meta 文本"
    assert option_texts, "对比下拉未渲染对象形态运行"
    rendered = metas + option_texts + [result["runHead"], result["detail"]]
    assert all(isinstance(t, str) for t in rendered)
    for text in rendered:
        assert "[object Object]" not in text, f"仍显示 [object Object]：{text}"
        assert (label in text) or (sid in text), f"文本缺少可读策略名：{text}"


def test_helper_formats_every_shape_as_plain_string() -> None:
    result = _run_node_harness()
    shapes = result["helperShapes"]
    assert shapes is not None, "缺少 formatEvaluationStrategy helper"
    by_shape = {entry["shape"]: entry for entry in shapes}
    for name, entry in by_shape.items():
        assert entry["type"] == "string", f"{name} 返回值不是字符串"
        assert "[object Object]" not in entry["text"], name
    assert by_shape["object-with-label"]["text"] == OBJECT_STRATEGY["label"]
    assert by_shape["object-id-only"]["text"] == "topk-10"
    assert by_shape["object-empty"]["text"] == "—"
    assert by_shape["null"]["text"] == "—"
    assert by_shape["undefined"]["text"] == "—"
    assert by_shape["string"]["text"] == "legacy-string"
