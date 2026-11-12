"""Static + runtime contracts for showing real dataset sample counts in the
evaluation dataset <select> options.

`GET /api/evaluation/options` returns `datasets[].item_count` (real per-dataset
sample counts, all >= 100). The dataset dropdown must surface that number in
each option's visible text, e.g. ``RAG 检索召回（128 条样本）``, while keeping
``option.value`` equal to ``item.id`` (the score request body is unchanged) and
leaving the strategy / model dropdowns byte-for-byte identical (they carry no
``item_count``).

Only object items whose ``item_count`` is a non-negative integer get the
suffix; string items, missing counts and non-integer / negative counts must not
be changed. All text stays ``String(...)`` + ``textContent`` (no innerHTML).
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
MODULE_MARKER = "// ===== 评测视图"

# 与 /api/evaluation/options 实测一致的选项形态：datasets 带 item_count，
# strategies / models 不带（故其下拉文本逐字不变）。
OPTIONS = {
    "strategies": [
        {"id": "baseline", "label": "基线策略（v1 / top_k=5 / reranker=off）"},
        {"id": "topk-10", "label": "扩大召回（v1 / top_k=10 / reranker=off）"},
    ],
    "models": [
        {"id": "gpt-4o-mini", "label": "GPT-4o mini"},
        {"id": "local-llm", "label": "本地判官模型"},
    ],
    "datasets": [
        {"id": "rag-retrieval", "label": "RAG 检索召回", "item_count": 128},
        {"id": "intent-classification", "label": "意图识别分类", "item_count": 120},
        {"id": "chat-quality", "label": "回答质量（既有判官轨迹）", "item_count": 120},
    ],
}


def _module() -> str:
    assert MODULE_MARKER in APP, "评测模块缺失（实现被删除时此门禁必须失败）"
    return APP[APP.index(MODULE_MARKER):]


def _function(name: str) -> str:
    """Brace-balanced body of `function <name>(...)`."""
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


# ---- (a) 静态契约：对象分支读取 item_count、文案带「条样本」、value 仍是 id ----

def test_object_branch_appends_item_count_text_and_keeps_id_value() -> None:
    body = _function("fillEvaluationSelect")
    assert "item.item_count" in body, "对象分支须读取 item_count"
    assert "条样本" in body, "样本数文案须带「条样本」"
    assert "Number.isInteger(" in body, "仅非负整数才追加，须做整数校验"
    assert "option.value = String(item.id" in body, "option.value 须仍是 item.id，不得污染 POST 请求体"
    assert "String(" in body, "所有文本仍须 String(...) + textContent"
    assert "textContent" in body
    assert "innerHTML" not in body, "禁 innerHTML 拼接"


def test_dataset_count_bumps_live_app_js_and_adds_pure_attribute_marker() -> None:
    assert INDEX.count('<script src="/assets/app.js?v=77"></script>') == 1
    # 合并远程 main 后 live CSS 为 v=75；v=73 保留在下方纯属性兼容 marker
    assert INDEX.count('<link rel="stylesheet" href="/assets/styles.css?v=76">') == 1
    lines = [line for line in INDEX.splitlines() if "app.js?v=76" in line]
    assert len(lines) == 1, "升版前的 v=76 须降级为恰好 1 条兼容 marker"
    marker = lines[0]
    assert "<!--" in marker and "-->" in marker, "marker 须位于 HTML 注释内"
    assert 'src="/assets/app.js?v=76"' in marker
    assert 'href="/assets/styles.css?v=73"' in marker
    assert "<script" not in marker, "注释内不得含 <script 标签字面串"
    assert "<link" not in marker, "注释内不得含 <link 标签字面串"


# ---- (b) 真实执行：走 loadEvaluationOptions() 真实路径 + 边界直接调用 ----

_NODE_HARNESS = r"""
const fs = require('fs');
const APP = fs.readFileSync(process.argv[process.argv.length - 1], 'utf8');
const MARKER = '// ===== 评测视图';
const src = APP.slice(APP.indexOf(MARKER));
const OPTIONS = __OPTIONS_JSON__;

if (typeof AbortController === 'undefined') {
  global.AbortController = class { constructor() { this.signal = {}; } abort() {} };
}

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
global.fetch = async () => ({ ok: true, json: async () => OPTIONS });

const snapshot = (id) => document.getElementById(id)._children.map((o) => ({
  value: o.value,
  text: typeof o.textContent === 'string' ? o.textContent : '',
}));

const program = src + `
;(async () => {
  await loadEvaluationOptions();
  const dataset = snapshot('evaluation-dataset-select');
  const strategy = snapshot('evaluation-strategy-select');
  const model = snapshot('evaluation-model-select');

  fillEvaluationSelect(document.getElementById('evaluation-dataset-select'), [
    { id: 'no-count', label: '无样本数字段' },
    { id: 'neg', label: '负数', item_count: -1 },
    { id: 'frac', label: '小数', item_count: 1.5 },
    { id: 'str', label: '字符串', item_count: '128' },
    { id: 'null', label: '空值', item_count: null },
    { id: 'zero', label: '零样本', item_count: 0 },
    { id: 'big', label: '大样本', item_count: 128 },
    '纯字符串项',
  ], '评测集');
  const edge = snapshot('evaluation-dataset-select');

  process.stdout.write(JSON.stringify({ dataset, strategy, model, edge }));
})().catch((e) => { console.error(String((e && e.stack) || e)); process.exit(1); });
`;
eval(program);
"""


@lru_cache(maxsize=1)
def _run_node_harness() -> dict:
    js = _NODE_HARNESS.replace("__OPTIONS_JSON__", json.dumps(OPTIONS, ensure_ascii=False))
    proc = subprocess.run(
        ["node", "-e", js, str(APP_PATH)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"node harness 失败：{proc.stderr}"
    assert proc.stdout.strip(), "node harness 无输出"
    return json.loads(proc.stdout.strip())


def test_runtime_dataset_options_show_real_counts_and_keep_id_values() -> None:
    result = _run_node_harness()
    options = result["dataset"]
    assert options[0]["value"] == "" and options[0]["text"] == "请选择评测集"
    real = options[1:]
    assert [(o["value"], o["text"]) for o in real] == [
        ("rag-retrieval", "RAG 检索召回（128 条样本）"),
        ("intent-classification", "意图识别分类（120 条样本）"),
        ("chat-quality", "回答质量（既有判官轨迹）（120 条样本）"),
    ]
    # spec §8 ①：选项区直接可见真实样本数且 >= 100
    for option in real:
        assert "条样本" in option["text"]
        match = re.search(r"（(\d+) 条样本）", option["text"])
        assert match and int(match.group(1)) >= 100, option["text"]


def test_runtime_strategy_and_model_option_text_is_unchanged() -> None:
    result = _run_node_harness()
    for key in ("strategy", "model"):
        for option in result[key]:
            assert "条样本" not in option["text"], f"{key} 下拉不得追加样本数"
    assert result["strategy"][1]["value"] == "baseline"
    assert result["strategy"][1]["text"] == "基线策略（v1 / top_k=5 / reranker=off）"
    assert result["model"][1]["value"] == "gpt-4o-mini"
    assert result["model"][1]["text"] == "GPT-4o mini"


def test_runtime_missing_or_invalid_item_count_does_not_append() -> None:
    result = _run_node_harness()
    by_value = {o["value"]: o["text"] for o in result["edge"]}
    assert by_value["no-count"] == "无样本数字段", "缺 item_count 不追加"
    assert by_value["neg"] == "负数", "负数不追加"
    assert by_value["frac"] == "小数", "小数不追加"
    assert by_value["str"] == "字符串", "字符串型不追加"
    assert by_value["null"] == "空值", "null 不追加"
    assert by_value["zero"] == "零样本（0 条样本）", "0 是非负整数，合法追加"
    assert by_value["big"] == "大样本（128 条样本）"
    assert "纯字符串项" in [o["text"] for o in result["edge"]], "字符串项逐字不变"
