"""研究页「会话计划」/ 聊天「研究计划」面板 4 字段显示契约（TDD）。

背景：后端 ``/api/research-tasks/{id}`` 的 ``plan`` 已是 camel 嵌套结构
（``capabilities[].skill.{name,tools}``、``budget.resource_limits.*``、
``report_structure.{title,format,language,sections}``、
``safe_summary.{decision,degraded,constraints}``），但两个格式化函数
``sessionPlanFieldText`` / ``researchPlanFieldText`` 仍按旧结构取值，匹配不上
就回退「未提供」。本轮让「来源与能力 / 预算 / 报告结构 / 降级策略」显示后端默认值。

门禁设计（regression-guard 第 12 条：断言不得恒真、不得可静默失效）：
1. 精确切出两个函数体与 4 个 key 分支；签名缺失 / 分支被删会报错，不静默通过。
2. 静态断言 4 个分支按新结构取值、旧结构白名单消失。
3. 两处 4 个分支归一化后逐字一致（对称修复）。
4. ``work_items`` / ``objective`` / ``scope`` 分支保持原样（本轮不动）。
5. **Node 行为探针**：拼接两处真实源码切片 + 真实 plan 数据，断言 4 字段输出
   不含「未提供」且含预期关键字（不是只查源码字符串）。
6. 诚实性反例：旧实现被门禁判违规，证明检测器能抓回归、非恒真。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
APP = (FRONTEND / "app.js").read_text(encoding="utf-8")
RESEARCH = (FRONTEND / "research-tasks.js").read_text(encoding="utf-8")
SESSION_UI = FRONTEND / "research-session-ui.js"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")

TARGET_KEYS = ("capabilities", "budget", "report_structure", "safety_summary")
BRANCH_ORDER = (
    "objective", "scope", "work_items", "capabilities",
    "budget", "report_structure", "safety_summary",
)

# 真实后端 plan 结构（取自 /api/research-tasks/{id}，camel 键、已解析）。
REAL_PLAN = {
    "capabilities": [
        {"skill": {
            "name": "usenix-catalog-orchestration",
            "tools": ["paper_discovery", "search_paper_catalog", "fetch_paper_detail"],
            "version": "1",
        }},
    ],
    "budget": {
        "language": "zh",
        "quality_profile": "balanced",
        "resource_limits": {
            "max_extensions": 3,
            "max_model_loops": 160,
            "max_seconds": 21600,
            "max_tool_calls": 640,
            "task_max_model_loops": 640,
            "task_max_tool_calls": 2560,
        },
        "soft_budget_seconds": 1500,
        "target_paper_count": 5,
    },
    "report_structure": {
        "citations": "inline",
        "format": "markdown",
        "language": "zh",
        "sections": ["研究问题", "方法与来源", "主要发现", "局限与后续工作"],
        "title": "深度研究报告",
    },
    "safe_summary": {
        "constraints": [],
        "decision": "已根据确认的 Intake 生成首版计划，等待用户批准",
        "degraded": [],
        "notes": "首版计划使用确定性 Planner；批准后才会创建 ResearchTask 并执行搜索。",
    },
}

# 每个字段输出必须含的关键字（证明显示的是后端默认值，而非空串或兜底）。
EXPECT = {
    "capabilities": "usenix-catalog-orchestration",
    "budget": "模型循环≤160",
    "report_structure": "深度研究报告",
    "safety_summary": "已根据确认的 Intake 生成首版计划",
}

# 新结构特征串：4 个分支在两处源码中都必须出现。
NEW_MARKERS = {
    "capabilities": (
        "item?.skill || {}", "skill.tools", "（工具：", "未知能力", "未提供来源策略",
    ),
    "budget": (
        "budget.resource_limits", "limits.max_model_loops", "limits.max_tool_calls",
        "limits.max_seconds", "budget.target_paper_count", "budget.quality_profile",
        "模型循环≤", "工具调用≤", "时长≤", "目标论文", "质量档",
    ),
    "report_structure": (
        "report.sections", "report.title", "report.format", "report.language",
        "sections.join('/')", "filter(Boolean)",
    ),
    "safety_summary": (
        "safety.decision", "safety.degraded", "safety.constraints",
        "降级源：", "约束：",
    ),
}

# 旧结构特征串：对应分支中必须消失（work_items 分支仍合法使用 list，故按分支判定）。
LEGACY_MARKERS = {
    "capabilities": ("safeSessionList(value)", "safeResearchList(value)", "source.sources"),
    "budget": ("'model_loops', 'tool_calls'", "'worker_count', 'max_results'"),
    "report_structure": ("safeSessionList(value)", "safeResearchList(value)"),
    "safety_summary": ("'degraded_sources', 'fallback'", "'stop_reason', 'limitations'"),
}

# 旧实现反例：用于证明门禁确实会失败、不是恒真断言。
LEGACY_BODY = """
    if (key === 'work_items' || key === 'capabilities' || key === 'report_structure') return safeSessionList(value).join('；') || safeSessionValue(value);
    if (key === 'budget') {
      const budget = parseSessionJson(value);
      return ['model_loops', 'tool_calls', 'seconds', 'worker_count', 'max_results']
        .filter((name) => budget[name] !== undefined).map((name) => `${name}: ${safeSessionValue(budget[name], '')}`).join(' · ') || safeSessionValue(value);
    }
    if (key === 'safety_summary') {
      const safety = parseSessionJson(value);
      return ['degraded_sources', 'fallback', 'fallback_strategy', 'stop_reason', 'limitations']
        .filter((name) => safety[name] !== undefined).map((name) => `${name}: ${safeSessionValue(safety[name], '')}`).join(' · ') || safeSessionValue(value);
    }
"""

# 精确切出函数源码：签名缺失 / 实现被删会抛异常，不静默通过。
APP_SIGS = (
    ("function parseResearchProjection(value) {", "function safeResearchScalar(value, fallback = '未提供') {"),
    ("function safeResearchScalar(value, fallback = '未提供') {", "function safeResearchList(value, limit = 12) {"),
    ("function safeResearchList(value, limit = 12) {", "function researchPlanField(plan, key) {"),
    ("function researchPlanField(plan, key) {", "function researchPlanFieldText(plan, key) {"),
    ("function researchPlanFieldText(plan, key) {", "function createConversationResearchPlan(assistantMessage) {"),
)
RESEARCH_SIGS = (
    ("function parseSessionJson(value) {", "function safeSessionValue(value, fallback = '未提供') {"),
    ("function safeSessionValue(value, fallback = '未提供') {", "function safeSessionList(value, limit = 12) {"),
    ("function safeSessionList(value, limit = 12) {", "function sessionPlanField(plan, key) {"),
    ("function sessionPlanField(plan, key) {", "function sessionPlanFieldText(plan, key) {"),
    ("function sessionPlanFieldText(plan, key) {", "function sessionCommandScope(command, approval, plan) {"),
)

# 两处仅辅助函数名不同；归一化后 4 个目标分支应逐字一致。
NORMALIZE = (
    ("safeResearchScalar", "safeSessionValue"),
    ("parseResearchProjection", "parseSessionJson"),
    ("safeResearchList", "safeSessionList"),
    ("researchPlanField", "sessionPlanField"),
)

NODE_PROBE_TEMPLATE = r"""
const ResearchSessionUI = require(__SESSION_UI__);
const window = { ResearchSessionUI };
const sessionUI = ResearchSessionUI;
__APP_FUNCS__
__RESEARCH_FUNCS__
const PLAN = __PLAN_JSON__;
const KEYS = __KEYS__;
const EXPECT = __EXPECT__;
let failed = false;
for (const fnName of ['researchPlanFieldText', 'sessionPlanFieldText']) {
  const fn = fnName === 'researchPlanFieldText' ? researchPlanFieldText : sessionPlanFieldText;
  for (const key of KEYS) {
    const out = fn(PLAN, key);
    if (typeof out !== 'string' || out.includes('未提供')) {
      console.error('FAIL', fnName, key, '=>', out);
      failed = true;
    } else if (!out.includes(EXPECT[key])) {
      console.error('FAIL(expected)', fnName, key, '=>', out);
      failed = true;
    } else {
      console.log('OK', fnName, key, '=>', out);
    }
  }
}
if (failed) process.exit(1);
console.log('ok - research plan field display contract');
"""


def _slice(source: str, start_sig: str, end_sig: str) -> str:
    """切出单个函数体；签名缺失或实现被删会抛异常，不静默通过。"""
    start = source.index(start_sig)
    end = source.index(end_sig, start + len(start_sig))
    body = source[start:end]
    assert len(body) > 40, f"{start_sig} 函数体切片过短，实现可能被删除"
    return body


def _bodies() -> dict[str, str]:
    return {
        "app.js::researchPlanFieldText": _slice(APP, *APP_SIGS[-1]),
        "research-tasks.js::sessionPlanFieldText": _slice(RESEARCH, *RESEARCH_SIGS[-1]),
    }


def _branches(body: str) -> dict[str, str]:
    """按 key 切出 7 个分支；缺任一独立分支即报错（旧实现的合并分支会在此暴露）。"""
    positions = [body.find(f"if (key === '{key}')") for key in BRANCH_ORDER]
    assert all(pos >= 0 for pos in positions), (
        f"缺少独立分支，4 个目标字段必须各有自己的 if 分支：{BRANCH_ORDER} / {positions}"
    )
    out: dict[str, str] = {}
    for i, key in enumerate(BRANCH_ORDER):
        start = positions[i]
        end = positions[i + 1] if i + 1 < len(BRANCH_ORDER) else body.find("return safe", start)
        assert end > start, f"{key} 分支切片异常"
        out[key] = body[start:end]
    return out


def _normalize(text: str) -> str:
    for app_name, research_name in NORMALIZE:
        text = text.replace(app_name, research_name)
    # 两处函数分别位于模块顶层与 IIFE 内，缩进层级天然不同。忽略无语义的
    # 缩进/空行，但保留全部换行、标点、字符串字面量与代码内容（不是弱化为恒真）。
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _node_probe_source() -> str:
    app_funcs = "\n".join(_slice(APP, a, b) for a, b in APP_SIGS)
    research_funcs = "\n".join(_slice(RESEARCH, a, b) for a, b in RESEARCH_SIGS)
    return (
        NODE_PROBE_TEMPLATE
        .replace("__SESSION_UI__", json.dumps(str(SESSION_UI)))
        .replace("__APP_FUNCS__", app_funcs)
        .replace("__RESEARCH_FUNCS__", research_funcs)
        .replace("__PLAN_JSON__", json.dumps(REAL_PLAN, ensure_ascii=False))
        .replace("__KEYS__", json.dumps(list(TARGET_KEYS)))
        .replace("__EXPECT__", json.dumps(EXPECT, ensure_ascii=False))
    )


def test_detector_is_not_vacuous() -> None:
    """诚实性：旧实现必须被门禁判为违规，证明断言能抓回归、非恒真。"""
    assert "'model_loops', 'tool_calls'" in LEGACY_BODY
    assert "'degraded_sources', 'fallback'" in LEGACY_BODY
    assert "safeSessionList(value).join('；')" in LEGACY_BODY
    assert "resource_limits" not in LEGACY_BODY
    assert "safety.decision" not in LEGACY_BODY
    assert "item?.skill" not in LEGACY_BODY
    for key, markers in NEW_MARKERS.items():
        assert not all(marker in LEGACY_BODY for marker in markers), (
            f"{key} 的新结构门禁在旧实现上恒真，检测器失效"
        )


def test_four_branches_read_new_backend_shape_in_both_files() -> None:
    """4 个分支在两处源码中都按 camel 嵌套结构取值。"""
    for name, body in _bodies().items():
        branches = _branches(body)
        for key, markers in NEW_MARKERS.items():
            for marker in markers:
                assert marker in branches[key], f"{name} 的 {key} 分支缺少新结构特征串 {marker!r}"


def test_legacy_whitelist_markers_are_gone_from_target_branches() -> None:
    """旧白名单（顶层 model_loops / degraded_sources / list 兜底）从目标分支消失。"""
    for name, body in _bodies().items():
        branches = _branches(body)
        for key, markers in LEGACY_MARKERS.items():
            for marker in markers:
                assert marker not in branches[key], f"{name} 的 {key} 分支仍含旧结构串 {marker!r}"


def test_symmetry_detector_is_not_vacuous() -> None:
    """一致性比较忽略缩进/空行，但真实文本差异仍必须被抓到（非恒真）。"""
    app_style = "if (key === 'budget') {\n  const limits = budget.resource_limits || {};\n  return parts.join(' · ');\n}"
    iife_style = "if (key === 'budget') {\n    const limits = budget.resource_limits || {};\n    return parts.join(' · ');\n  }"
    assert _normalize(app_style) == _normalize(iife_style), "缩进差异不应判为行为不一致"
    drifted = iife_style.replace("parts.join(' · ')", "parts.join('；')")
    assert _normalize(app_style) != _normalize(drifted), "真实文本差异必须被检测器抓到"


def test_two_formatters_are_symmetric_for_four_target_branches() -> None:
    """两处 4 个目标分支归一化后逐字一致（对称修复，行为不漂移）。"""
    bodies = _bodies()
    app_branches = _branches(bodies["app.js::researchPlanFieldText"])
    research_branches = _branches(bodies["research-tasks.js::sessionPlanFieldText"])
    for key in TARGET_KEYS:
        assert _normalize(app_branches[key]) == _normalize(research_branches[key]), (
            f"{key} 分支在 app.js 与 research-tasks.js 中不一致"
        )


def test_untouched_branches_keep_original_behavior() -> None:
    """objective / scope / work_items 已正常，本轮保持各自原样不动。"""
    bodies = _bodies()
    app_branches = _branches(bodies["app.js::researchPlanFieldText"])
    research_branches = _branches(bodies["research-tasks.js::sessionPlanFieldText"])
    assert "safeResearchScalar(value)" in app_branches["objective"]
    assert "safeSessionValue(value)" in research_branches["objective"]
    for scope in (app_branches["scope"], research_branches["scope"]):
        assert "包含：" in scope and "排除：" in scope and "方向：" in scope
    assert "safeResearchList(value).join('；') || '未提供研究方向'" in app_branches["work_items"]
    assert "safeSessionList(value).join('；') || safeSessionValue(value)" in research_branches["work_items"]


def test_safe_summary_compat_and_text_only_rendering() -> None:
    """plan.safe_summary 兼容仍在；两个格式化函数只返回文本，不碰 DOM / innerHTML。"""
    for source in (APP, RESEARCH):
        assert "plan.safe_summary !== undefined" in source
    for name, body in _bodies().items():
        assert "innerHTML" not in body, f"{name} 不得拼接 innerHTML"
        assert "document." not in body, f"{name} 不得直接操作 DOM"


def test_node_probe_four_plan_fields_show_backend_defaults() -> None:
    """运行时行为：真实源码切片 + 真实 plan 数据，4 字段不得显示「未提供」。"""
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node executable not found on PATH")
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "plan_field_probe.js"
        script.write_text(_node_probe_source(), encoding="utf-8")
        env = dict(os.environ)
        env.setdefault("NODE_OPTIONS", "")
        result = subprocess.run(
            [node, str(script)], cwd=str(ROOT),
            capture_output=True, text=True, timeout=120, env=env,
        )
    assert result.returncode == 0, (
        "研究计划 4 字段仍显示「未提供」或缺少后端默认值：\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "ok - research plan field display contract" in result.stdout, result.stdout
