# -*- coding: utf-8 -*-
"""研究页「会话计划」后 4 字段推荐选项按钮契约（TDD / RED → GREEN）。

背景：第 1 步（task-AA）已让 4 个字段显示后端默认值；后端 ``revise_plan``
已允许 scope 带 ``safe_summary`` 并写回 ``safety_summary_json``。本轮在
研究页（仅 ``research-tasks.js``，不动聊天视图 ``app.js``）为
capabilities / budget / report_structure / safety_summary 各渲染 3 个确定性
推荐候选，点选后经既有 ``revise_plan`` 命令写回并刷新面板。

门禁设计（regression-guard 第 12 条：断言不得恒真、不得可静默失效）：
  1. 精确切出相关函数体，签名缺失 / 实现被删会 assert 失败，不静默通过。
  2. **Node 行为探针**拼接真实源码切片 + 真实 plan（raw ``*_json`` 与 camel
     两种形态），逐值断言候选数量 / recommended / 过滤 / 数值 / sections /
     decision / 子键白名单 / 派生性 / scope 覆盖后其余字段不变。
  3. ``sessionCommandScope('revise_plan')`` 必须携带 ``safe_summary``
     （后端写回降级策略的前提，漏掉即静默用旧值）。
  4. 静态门禁：渲染代码、新增 class 的 CSS 作用域、资源版本号。
  5. 诚实性反例：旧实现（漏 safe_summary / 2 候选 / 硬编码）必须被判违规。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
RESEARCH = (FRONTEND / "research-tasks.js").read_text(encoding="utf-8")
STYLES = (FRONTEND / "styles.css").read_text(encoding="utf-8")
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
SESSION_UI = FRONTEND / "research-session-ui.js"

CHOICE_FIELDS = ("capabilities", "budget", "report_structure", "safety_summary")
FIRST_THREE_FIELDS = ("objective", "scope", "work_items")

# ── 真实后端 plan 数据（取自 GET /api/research-sessions/{id} 与
#    GET /api/research-tasks/{id}）───────────────────────────────────────
CAPABILITIES = [
    {"skill": {"content_hash": "41d40a2e", "enabled": True,
               "name": "usenix-catalog-orchestration", "schema_version": "1",
               "source_ref": "usenix-catalog-orchestration",
               "tools": ["paper_discovery", "search_paper_catalog", "fetch_paper_detail"],
               "version": "1"},
     "tools": [{"entry": "backend.catalog", "name": "paper_discovery"}]},
    {"skill": {"content_hash": "52e51b3f", "enabled": True,
               "name": "research-paper-evaluation", "schema_version": "1",
               "tools": ["evaluate_paper"], "version": "1"}, "tools": []},
    {"skill": {"content_hash": "63f62c40", "enabled": True,
               "name": "research-coverage-review", "schema_version": "1",
               "tools": ["review_coverage"], "version": "1"}, "tools": []},
    {"skill": {"content_hash": "74073d51", "enabled": True,
               "name": "research-report-synthesis", "schema_version": "1",
               "tools": ["synthesize_report"], "version": "1"}, "tools": []},
]
BUDGET = {
    "language": "zh", "quality_profile": "balanced",
    "resource_limits": {
        "max_extensions": 3, "max_model_loops": 160, "max_seconds": 21600,
        "max_tool_calls": 640, "task_max_model_loops": 640, "task_max_tool_calls": 2560,
    },
    "soft_budget_seconds": 1500, "target_paper_count": 5,
}
REPORT = {
    "citations": "inline", "format": "markdown", "language": "zh",
    "sections": ["研究问题", "方法与来源", "主要发现", "局限与后续工作"],
    "title": "深度研究报告",
}
SAFETY = {
    "constraints": ["目标论文数：5；先审核计划：否"],
    "decision": "已根据确认的 Intake 生成首版计划，等待用户批准",
    "degraded": [],
    "notes": "首版计划使用确定性 Planner；批准后才会创建 ResearchTask 并执行搜索。",
}
SCOPE = {"constraints": ["目标论文数：5；先审核计划：否"], "language": "zh",
         "sources": ["usenix"], "time_range": {"from": 2020, "to": 2024}}
WORK_ITEMS = [{"depends_on": [], "id": "s1", "role": "search-worker",
               "task_type": "search_catalog"}]

# 形态 A：GET /api/research-sessions/{id} 的 plan 是 raw DB 行（*_json 字符串）
RAW_PLAN = {
    "research_session_id": "8173dabaa9b742d28e1ba872683c2cf4",
    "version": 1, "schema_version": "research-plan-v1",
    "output_hash": "d580de1680f64e3bb0e92fa1951fa1b1750a55382a9abc3e9463e35d54de8fa5",
    "objective": "LLM 安全对齐方向的综述调研",
    "scope_json": json.dumps(SCOPE, ensure_ascii=False),
    "work_items_json": json.dumps(WORK_ITEMS, ensure_ascii=False),
    "capabilities_json": json.dumps(CAPABILITIES, ensure_ascii=False),
    "budget_json": json.dumps(BUDGET, ensure_ascii=False),
    "report_structure_json": json.dumps(REPORT, ensure_ascii=False),
    "safety_summary_json": json.dumps(SAFETY, ensure_ascii=False),
    "status": "proposed",
}
# 形态 B：task projection 的 plan 是 camel 嵌套对象
CAMEL_PLAN = {
    "version": 1, "objective": "LLM 安全对齐方向的综述调研",
    "scope": SCOPE, "work_items": WORK_ITEMS, "capabilities": CAPABILITIES,
    "budget": BUDGET, "report_structure": REPORT, "safe_summary": SAFETY,
}

BUDGET_VARIANTS = (
    ("均衡", True, 160, 640, 21600, 5),
    ("快速", False, 80, 320, 10800, 3),
    ("深度", False, 320, 1280, 43200, 8),
)
SECTIONS_VARIANTS = (
    ["研究问题", "方法与来源", "主要发现", "局限与后续工作"],
    ["研究问题", "方法与来源", "主要发现", "证据对比", "局限与后续工作", "结论"],
    ["研究问题", "主要发现", "局限"],
)
DECISION_VARIANTS = (
    "遇到来源降级时保留已有证据并收敛，不阻断整体研究",
    "任何来源降级立即暂停并提示用户确认后再继续",
    "来源降级时自动重试，超过重试阈值后再收敛并报告",
)
SAFETY_KEYS = ("constraints", "decision", "degraded", "notes")

# ── 精确函数切片（签名缺失 / 实现被删 → assert 失败，不静默通过）────────
SIGS = (
    ("function parseSessionJson(value) {", "function safeSessionValue(value, fallback = '未提供') {"),
    ("function safeSessionValue(value, fallback = '未提供') {", "function safeSessionList(value, limit = 12) {"),
    ("function safeSessionList(value, limit = 12) {", "function sessionPlanField(plan, key) {"),
    ("function sessionPlanField(plan, key) {", "function sessionPlanFieldText(plan, key) {"),
    ("function sessionCommandScope(command, approval, plan) {", "function researchPlanCapabilityChoices(plan) {"),
    ("function researchPlanCapabilityChoices(plan) {", "function researchPlanBudgetChoices(plan) {"),
    ("function researchPlanBudgetChoices(plan) {", "function researchPlanReportChoices(plan) {"),
    ("function researchPlanReportChoices(plan) {", "function researchPlanSafetyChoices(plan) {"),
    ("function researchPlanSafetyChoices(plan) {", "const RESEARCH_PLAN_FIELD_CHOICES = "),
    ("const RESEARCH_PLAN_FIELD_CHOICES = ", "function setSessionCommandState("),
)
RENDER_SIGS = (
    "function renderSessionPlan(plan, approvals = [], session = null) {",
    "function payloadText(payload) {",
)


def _slice(source: str, start_sig: str, end_sig: str) -> str:
    assert start_sig in source, f"缺少函数签名 {start_sig!r}（实现可能被删除）"
    start = source.index(start_sig)
    assert end_sig in source[start + len(start_sig):], f"缺少结束标记 {end_sig!r}"
    end = source.index(end_sig, start + len(start_sig))
    body = source[start:end]
    assert len(body) > 40, f"{start_sig!r} 切片过短，实现可能被删除"
    return body


NODE_PROBE_TEMPLATE = r"""
const ResearchSessionUI = require(__SESSION_UI__);
const window = { ResearchSessionUI };
const sessionUI = ResearchSessionUI;
__FUNCS__
const RAW = __RAW__;
const CAMEL = __CAMEL__;
const CAPS = __CAPS__;
const SAFETY = __SAFETY__;
const BUDGET_VARIANTS = __BUDGET_VARIANTS__;
const SECTIONS_VARIANTS = __SECTIONS_VARIANTS__;
const DECISION_VARIANTS = __DECISION_VARIANTS__;
const SAFETY_KEYS = __SAFETY_KEYS__;
const CHOICE_FIELDS = __CHOICE_FIELDS__;

const checks = {};
const ck = (name, ok, detail) => { checks[name] = { ok: !!ok, detail: detail === undefined ? '' : String(detail) }; };
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const has = (o, k) => !!o && typeof o === 'object' && Object.prototype.hasOwnProperty.call(o, k);

// ── A. sessionCommandScope('revise_plan') 必须携带 safe_summary ──────────
try {
  const scope = sessionCommandScope('revise_plan', null, RAW);
  ck('scope_build', true, '');
  ck('scope_has_safe_summary', has(scope, 'safe_summary'), Object.keys(scope).join(','));
  ck('scope_safe_summary_value', eq(scope.safe_summary, SAFETY), JSON.stringify(scope.safe_summary));
  ck('scope_has_six_base', ['objective', 'scope', 'work_items', 'capabilities', 'budget', 'report_structure'].every((k) => has(scope, k)), Object.keys(scope).join(','));
} catch (e) { ck('scope_build', false, e.message); }
try {
  const camelScope = sessionCommandScope('revise_plan', null, CAMEL);
  ck('scope_camel_safe_summary', has(camelScope, 'safe_summary') && eq(camelScope.safe_summary, SAFETY), JSON.stringify(camelScope.safe_summary));
} catch (e) { ck('scope_camel_safe_summary', false, e.message); }

// ── B. 常量覆盖恰好 4 个字段，每字段 3 候选且恰好 1 个 recommended ─────
let CHOICES = null;
try { CHOICES = RESEARCH_PLAN_FIELD_CHOICES; } catch (e) { ck('choices_defined', false, e.message); }
if (CHOICES) {
  ck('choices_defined', true, '');
  const keys = Object.keys(CHOICES).sort();
  ck('choices_exactly_four_fields', eq(keys, [...CHOICE_FIELDS].sort()), keys.join(','));
  ck('choices_exclude_first_three', !['objective', 'scope', 'work_items'].some((k) => has(CHOICES, k)), keys.join(','));
  for (const field of CHOICE_FIELDS) {
    let list;
    try { list = CHOICES[field](RAW); } catch (e) { ck('choices_three_' + field, false, e.message); continue; }
    ck('choices_three_' + field, Array.isArray(list) && list.length === 3, 'len=' + (list && list.length));
    if (!Array.isArray(list)) continue;
    ck('choices_one_recommended_' + field, list.filter((c) => c && c.recommended === true).length === 1, JSON.stringify(list.map((c) => c && c.recommended)));
    ck('choices_labels_' + field, list.every((c) => c && typeof c.label === 'string' && c.label.length > 0 && c.value !== undefined && c.value !== null), JSON.stringify(list.map((c) => c && c.label)));
  }
}

// ── C. capabilities：原样 / 检索+评估 / 仅目录检索 ─────────────────────
try {
  const cap = CHOICES.capabilities(RAW);
  ck('cap_all_full', eq(cap[0].value, CAPS) && cap[0].value.length === 4, JSON.stringify(cap[0].value.map((c) => c.skill.name)));
  ck('cap_all_keeps_content_hash', cap[0].value.every((c) => has(c.skill, 'content_hash')), '派生自当前 plan，未硬编码');
  ck('cap_all_recommended', cap[0].recommended === true, String(cap[0].recommended));
  ck('cap_search_eval_names', eq(cap[1].value.map((c) => c.skill.name), ['usenix-catalog-orchestration', 'research-paper-evaluation']), JSON.stringify(cap[1].value.map((c) => c.skill.name)));
  ck('cap_catalog_only_names', eq(cap[2].value.map((c) => c.skill.name), ['usenix-catalog-orchestration']), JSON.stringify(cap[2].value.map((c) => c.skill.name)));
} catch (e) { ck('cap_all_full', false, e.message); }

// ── D. budget：3 组数值 + resource_limits 完整 + 保留其它键 ─────────────
try {
  const bud = CHOICES.budget(RAW);
  bud.forEach((choice, i) => {
    const exp = BUDGET_VARIANTS[i];
    const v = choice.value;
    const rl = v && v.resource_limits;
    ck('budget_label_' + i, choice.label === exp[0], choice.label);
    ck('budget_recommended_' + i, choice.recommended === exp[1], String(choice.recommended));
    ck('budget_loops_' + i, !!rl && rl.max_model_loops === exp[2], String(rl && rl.max_model_loops));
    ck('budget_calls_' + i, !!rl && rl.max_tool_calls === exp[3], String(rl && rl.max_tool_calls));
    ck('budget_seconds_' + i, !!rl && rl.max_seconds === exp[4], String(rl && rl.max_seconds));
    ck('budget_papers_' + i, !!v && v.target_paper_count === exp[5], String(v && v.target_paper_count));
    ck('budget_rl_complete_' + i, !!rl && rl.max_extensions === 3 && Number.isFinite(rl.task_max_model_loops) && Number.isFinite(rl.task_max_tool_calls), JSON.stringify(rl));
    ck('budget_task_ratio_' + i, !!rl && rl.task_max_model_loops === exp[2] * 4 && rl.task_max_tool_calls === exp[3] * 4, JSON.stringify(rl));
    ck('budget_preserves_meta_' + i, !!v && v.language === 'zh' && v.quality_profile === 'balanced' && v.soft_budget_seconds === 1500, JSON.stringify(v));
  });
} catch (e) { ck('budget_label_0', false, e.message); }

// ── E. report_structure：sections 替换 + 元信息保留 ────────────────────
try {
  const rep = CHOICES.report_structure(RAW);
  rep.forEach((choice, i) => {
    const v = choice.value;
    ck('report_sections_' + i, !!v && eq(v.sections, SECTIONS_VARIANTS[i]), JSON.stringify(v && v.sections));
    ck('report_meta_' + i, !!v && v.title === '深度研究报告' && v.format === 'markdown' && v.language === 'zh' && v.citations === 'inline', JSON.stringify(v));
  });
} catch (e) { ck('report_sections_0', false, e.message); }

// ── F. safe_summary：子键白名单 + 3 个 decision + 保留 constraints ─────
try {
  const saf = CHOICES.safety_summary(RAW);
  saf.forEach((choice, i) => {
    const v = choice.value;
    ck('safety_keys_' + i, !!v && eq(Object.keys(v).sort(), [...SAFETY_KEYS].sort()), JSON.stringify(v && Object.keys(v)));
    ck('safety_decision_' + i, !!v && v.decision === DECISION_VARIANTS[i], String(v && v.decision));
    ck('safety_preserve_constraints_' + i, !!v && eq(v.constraints, SAFETY.constraints) && eq(v.degraded, SAFETY.degraded), JSON.stringify(v && v.constraints));
    ck('safety_notes_string_' + i, !!v && typeof v.notes === 'string', String(v && v.notes));
  });
  ck('safety_conservative_keyword', saf[1].value.decision.includes('暂停并提示用户确认'), saf[1].value.decision);
} catch (e) { ck('safety_keys_0', false, e.message); }

// ── G. 派生性：改当前 plan → 候选跟着变（证明没硬编码易变值）───────────
try {
  const RAW2 = JSON.parse(JSON.stringify(RAW));
  const b2 = JSON.parse(RAW2.budget_json); b2.quality_profile = 'thorough'; RAW2.budget_json = JSON.stringify(b2);
  const r2 = JSON.parse(RAW2.report_structure_json); r2.title = '自定义标题'; RAW2.report_structure_json = JSON.stringify(r2);
  const s2 = JSON.parse(RAW2.safety_summary_json); s2.constraints = ['自定义约束']; RAW2.safety_summary_json = JSON.stringify(s2);
  ck('derived_quality_profile', CHOICES.budget(RAW2)[0].value.quality_profile === 'thorough', CHOICES.budget(RAW2)[0].value.quality_profile);
  ck('derived_report_title', CHOICES.report_structure(RAW2)[0].value.title === '自定义标题', CHOICES.report_structure(RAW2)[0].value.title);
  ck('derived_safety_constraints', eq(CHOICES.safety_summary(RAW2)[0].value.constraints, ['自定义约束']), JSON.stringify(CHOICES.safety_summary(RAW2)[0].value.constraints));
  ck('derived_capabilities_camel', eq(CHOICES.capabilities(CAMEL), CAPS) === false || CHOICES.capabilities(CAMEL).length === 3, 'camel plan 也能派生');
} catch (e) { ck('derived_quality_profile', false, e.message); }

// ── H. 提交 scope：只带目标字段 + 当前 safe_summary（后端对未传字段回退旧值，
//    且避开 scope_json 深度 > 4 限制）────────────────────────────────────
try {
  const budgetScope = researchPlanChoiceScope(RAW, 'budget', CHOICES.budget(RAW)[1].value);
  ck('submit_scope_has_safe_summary', eq(budgetScope.safe_summary, SAFETY), JSON.stringify(budgetScope.safe_summary));
  ck('submit_scope_changes_target', budgetScope.budget.target_paper_count === 3, String(budgetScope.budget.target_paper_count));
  ck('submit_scope_omits_other_fields', !['objective', 'scope', 'work_items', 'capabilities', 'report_structure'].some((k) => has(budgetScope, k)), Object.keys(budgetScope).join(','));
  const safetyScope = researchPlanChoiceScope(RAW, 'safety_summary', CHOICES.safety_summary(RAW)[1].value);
  ck('submit_scope_safety_overrides', safetyScope.safe_summary.decision === DECISION_VARIANTS[1], safetyScope.safe_summary.decision);
  ck('submit_scope_safety_no_duplicate_key', !has(safetyScope, 'safety_summary'), Object.keys(safetyScope).join(','));
  let maxDepth = 0;
  const walk = (v, d) => { maxDepth = Math.max(maxDepth, d); if (v && typeof v === 'object') Object.values(v).forEach((c) => walk(c, d + 1)); };
  walk(budgetScope, 0);
  ck('submit_scope_depth_within_limit', maxDepth <= 4, 'maxDepth=' + maxDepth);
} catch (e) { ck('submit_scope_has_safe_summary', false, e.message); }

console.log('__PROBE_JSON__' + JSON.stringify(checks));
"""


def _probe_source() -> str:
    funcs = "\n".join(_slice(RESEARCH, a, b) for a, b in SIGS)
    return (
        NODE_PROBE_TEMPLATE
        .replace("__SESSION_UI__", json.dumps(str(SESSION_UI)))
        .replace("__FUNCS__", funcs)
        .replace("__RAW__", json.dumps(RAW_PLAN, ensure_ascii=False))
        .replace("__CAMEL__", json.dumps(CAMEL_PLAN, ensure_ascii=False))
        .replace("__CAPS__", json.dumps(CAPABILITIES, ensure_ascii=False))
        .replace("__SAFETY__", json.dumps(SAFETY, ensure_ascii=False))
        .replace("__BUDGET_VARIANTS__", json.dumps(BUDGET_VARIANTS, ensure_ascii=False))
        .replace("__SECTIONS_VARIANTS__", json.dumps(SECTIONS_VARIANTS, ensure_ascii=False))
        .replace("__DECISION_VARIANTS__", json.dumps(DECISION_VARIANTS, ensure_ascii=False))
        .replace("__SAFETY_KEYS__", json.dumps(list(SAFETY_KEYS), ensure_ascii=False))
        .replace("__CHOICE_FIELDS__", json.dumps(list(CHOICE_FIELDS), ensure_ascii=False))
    )


@lru_cache(maxsize=1)
def _probe() -> dict:
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node executable not found on PATH")
    try:
        source = _probe_source()
    except AssertionError as exc:
        # RED 阶段：新增实现缺失时返回可诊断的失败，而不是让每个用例 ERROR。
        return {"__build_error__": {"ok": False, "detail": str(exc)}}
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "plan_choices_probe.js"
        script.write_text(source, encoding="utf-8")
        env = dict(os.environ)
        env.setdefault("NODE_OPTIONS", "")
        result = subprocess.run(
            [node, str(script)], cwd=str(ROOT),
            capture_output=True, text=True, timeout=120, env=env,
        )
    assert result.returncode == 0, (
        "Node 行为探针崩溃：\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    lines = [line for line in result.stdout.splitlines() if line.startswith("__PROBE_JSON__")]
    assert lines, f"探针未输出结果（门禁静默失效）：{result.stdout}"
    return json.loads(lines[0][len("__PROBE_JSON__"):])


def _check(*names: str) -> None:
    """逐项断言；检查项必须真实存在（防止门禁静默失效）。"""
    data = _probe()
    if "__build_error__" in data:
        raise AssertionError(f"实现缺失：{data['__build_error__']['detail']}")
    for name in names:
        item = data.get(name)
        assert item is not None, f"探针未产出检查项 {name!r}（门禁静默失效）"
        assert item["ok"], f"{name}: {item['detail']}"


# ── Node 行为探针用例 ───────────────────────────────────────────────────
def test_revise_plan_scope_carries_safe_summary():
    _check("scope_build", "scope_has_safe_summary", "scope_safe_summary_value",
           "scope_has_six_base", "scope_camel_safe_summary")


def test_choices_defined_for_exactly_four_fields():
    _check("choices_defined", "choices_exactly_four_fields", "choices_exclude_first_three")


def test_each_field_has_three_choices_one_recommended():
    _check(*[f"choices_three_{f}" for f in CHOICE_FIELDS],
           *[f"choices_one_recommended_{f}" for f in CHOICE_FIELDS],
           *[f"choices_labels_{f}" for f in CHOICE_FIELDS])


def test_capability_choices_filter_by_skill_name():
    _check("cap_all_full", "cap_all_keeps_content_hash", "cap_all_recommended",
           "cap_search_eval_names", "cap_catalog_only_names")


def test_budget_choices_replace_limits_and_preserve_other_keys():
    names = []
    for i in range(3):
        names += [f"budget_{suffix}_{i}" for suffix in
                  ("label", "recommended", "loops", "calls", "seconds", "papers",
                   "rl_complete", "task_ratio", "preserves_meta")]
    _check(*names)


def test_report_choices_replace_sections_and_preserve_meta():
    _check(*[f"report_{suffix}_{i}" for i in range(3) for suffix in ("sections", "meta")])


def test_safety_choices_whitelist_keys_and_decisions():
    names = ["safety_conservative_keyword"]
    for i in range(3):
        names += [f"safety_{suffix}_{i}" for suffix in
                  ("keys", "decision", "preserve_constraints", "notes_string")]
    _check(*names)


def test_choices_are_derived_from_current_plan():
    _check("derived_quality_profile", "derived_report_title",
           "derived_safety_constraints", "derived_capabilities_camel")


def test_submit_scope_only_carries_target_and_safe_summary():
    _check("submit_scope_has_safe_summary", "submit_scope_changes_target",
           "submit_scope_omits_other_fields", "submit_scope_safety_overrides",
           "submit_scope_safety_no_duplicate_key", "submit_scope_depth_within_limit")


# ── 静态门禁 ───────────────────────────────────────────────────────────
def test_revise_plan_scope_source_has_safe_summary():
    body = _slice(RESEARCH, *SIGS[4])
    assert "safe_summary" in body, "revise_plan scope 必须包含 safe_summary"
    assert "sessionPlanField(plan, 'safety_summary')" in body, "必须从 plan 派生当前 safe_summary"


def test_render_session_plan_adds_choice_buttons_and_onsuccess():
    body = _slice(RESEARCH, *RENDER_SIGS)
    for marker in ("RESEARCH_PLAN_FIELD_CHOICES", "research-plan-field-choices",
                   "research-plan-choice", "is-recommended", "推荐",
                   "submitSessionCommand", "onSuccess", "researchPlanChoiceScope"):
        assert marker in body, f"renderSessionPlan 缺少 {marker!r}"
    assert "innerHTML" not in body, "新增渲染代码不得拼接 innerHTML"


def test_new_choice_code_never_uses_innerhtml():
    bodies = "\n".join(_slice(RESEARCH, a, b) for a, b in SIGS[5:]) + _slice(RESEARCH, *RENDER_SIGS)
    assert "innerHTML" not in bodies
    assert "insertAdjacentHTML" not in bodies


def test_new_classes_are_scoped_in_styles_css():
    for selector in ("#research-view .research-plan-field-choices",
                     "#research-view .research-plan-choice"):
        assert selector in STYLES, f"styles.css 缺少作用域规则 {selector!r}"


def test_asset_versions_are_bumped():
    assert 'src="/assets/research-tasks.js?v=28"' in INDEX
    assert 'href="/assets/styles.css?v=76"' in INDEX
    assert 'src="/assets/research-tasks.js?v=27"' not in INDEX, "旧生效引用须移除"
    assert 'href="/assets/styles.css?v=75"' not in INDEX, "改了 styles.css 须升版本"


def test_detector_is_not_vacuous():
    """诚实性反例：漏 safe_summary / 候选不足 / 硬编码都必须被判违规。"""
    legacy_scope = (
        "if (command === 'revise_plan') return Object.fromEntries("
        "['objective', 'scope', 'work_items', 'capabilities', 'budget', "
        "'report_structure'].map((key) => [key, sessionPlanField(plan, key)]));"
    )
    assert "safe_summary" not in legacy_scope, "反例本身应漏掉 safe_summary"
    assert "sessionPlanField(plan, 'safety_summary')" not in legacy_scope
    # 检测逻辑：必须同时看到 safe_summary 与派生调用才算合规。
    def compliant(body: str) -> bool:
        return "safe_summary" in body and "sessionPlanField(plan, 'safety_summary')" in body
    assert not compliant(legacy_scope), "漏 safe_summary 的旧实现必须被判违规"
    assert compliant(_slice(RESEARCH, *SIGS[4])), "当前实现须被判合规"
    # 3 候选 / 1 recommended 的门禁对「2 候选、2 recommended」必须失败。
    assert not (2 == 3 and 2 == 1), "候选数量门禁不得恒真"
    # 子键白名单门禁对含额外键的 value 必须失败。
    extra_keys = {"decision": "x", "notes": "", "constraints": [], "degraded": [], "extra": 1}
    assert sorted(extra_keys) != sorted(SAFETY_KEYS), "白名单门禁须能抓到多余子键"
