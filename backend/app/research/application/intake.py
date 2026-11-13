"""Conversation-layer Deep Research intake.

This module is deliberately a small coordinator: it discovers and activates the
registered Skill, persists the Intake projection, and never creates a
ResearchTask or AgentRun.  The ResearchStore remains the sole research-store
writer and MemoryRepository remains the sole conversation-store writer.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.app.research.application.session_plan_generation import (
    extract_paper_count_constraints,
    resolve_paper_count_constraints,
)
from backend.app.research.domain.contracts import SESSION_TERMINAL
from backend.app.research.domain.models import IntakeField, ResearchSession
from backend.app.research.infrastructure.research_store import (
    ResearchSessionActiveConflict,
)

DEEP_RESEARCH_SKILL = "deep-research-orchestration"
BLOCKING_FIELDS = ("topic", "objective", "time_range")
DEFAULT_FIELDS: dict[str, Any] = {
    "language": "zh",
    "sources": ["usenix"],
    "depth": "balanced",
    "output": "markdown",
    "citations": "inline",
    "constraints": [],
    # 逐轮引导式询问新增的 4 个计划偏好：值 = 契约 2.2 各项 ★ 推荐值。
    # 均为简单字符串枚举，禁止嵌套对象。
    "capability_profile": "full",
    "budget_profile": "balanced",
    "report_profile": "standard",
    "degradation_policy": "balanced",
}

# 契约 2.2 新增的 4 个计划偏好字段。改前创建的历史会话没有它们；
# derive_guided_state 据此识别老会话，避免把「缺字段」误判成待询问。
_PROFILE_FIELDS = frozenset({
    "capability_profile", "budget_profile", "report_profile", "degradation_policy",
})

# ---------------------------------------------------------------------------
# 逐轮引导式询问：9 轮问题目录（确定性常量，零 LLM 调用）。
#
# 目录既驱动 projection 的 ``prompt``（契约 2.4），也驱动 ``[intake:...]``
# 回答协议（契约 2.5）的 choice_id → 目标字段值映射，两端共用同一份事实，
# 避免出现第二套候选/推荐实现。9 轮的 ``fields`` 合并后恰好覆盖
# ``INTAKE_FIELDS`` 的全部 13 个字段，重叠字段只问一次。
#
# ``values[choice_id]`` 只在后端使用，不会进入对外 projection；``custom``
# 入口不在此字典中，协议侧特判 ``custom:<文本>``（不允许无文本的 custom）。
# ---------------------------------------------------------------------------
_PROMPT_PUBLIC_KEYS = (
    "key", "index", "total", "label", "question", "choices",
    "allow_custom", "custom_label",
)

GUIDED_QUESTIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "q_topic", "index": 1, "total": 9,
        "label": "研究主题", "question": "这次要研究什么主题？",
        "fields": ("topic",), "custom_field": "topic",
        "allow_custom": True, "custom_label": "自定义（直接输入）",
        "choices": (
            {"id": "keep", "label": "沿用我刚才的描述（推荐，未指定则用默认）", "recommended": True},
            {"id": "custom", "label": "自定义输入", "recommended": False},
        ),
        "values": {"keep": {"topic": "深度研究主题"}},
    },
    {
        "key": "q_objective", "index": 2, "total": 9,
        "label": "研究目标", "question": "这次研究希望达成什么目标？",
        "fields": ("objective",), "custom_field": "objective",
        "allow_custom": True, "custom_label": "自定义（直接输入）",
        "choices": (
            {"id": "keep", "label": "沿用我刚才的描述（推荐，未指定则用默认）", "recommended": True},
            {"id": "custom", "label": "自定义输入", "recommended": False},
        ),
        "values": {"keep": {"objective": "梳理研究目标"}},
    },
    {
        "key": "q_time_range", "index": 3, "total": 9,
        "label": "时间范围", "question": "这次研究覆盖哪段时间范围？",
        "fields": ("time_range",), "custom_field": "time_range",
        "allow_custom": True, "custom_label": "自定义（直接输入）",
        "choices": (
            {"id": "recent_3y", "label": "近 3 年", "recommended": True},
            {"id": "recent_5y", "label": "近 5 年", "recommended": False},
            {"id": "all_time", "label": "不限", "recommended": False},
        ),
        # 契约 2.2：当前日期 2026-11-13，沿用 {"from":...,"to":...} 编码。
        "values": {
            "recent_3y": {"time_range": {"from": 2023, "to": 2026}},
            "recent_5y": {"time_range": {"from": 2021, "to": 2026}},
            "all_time": {"time_range": {"from": 1900, "to": 2026}},
        },
    },
    {
        "key": "q_language", "index": 4, "total": 9,
        "label": "报告语言", "question": "报告希望用什么语言撰写？",
        "fields": ("language",), "custom_field": "language",
        "allow_custom": True, "custom_label": "自定义（直接输入）",
        "choices": (
            {"id": "zh", "label": "中文", "recommended": True},
            {"id": "en", "label": "英文", "recommended": False},
            {"id": "bilingual", "label": "中英混合", "recommended": False},
        ),
        "values": {
            "zh": {"language": "zh"},
            "en": {"language": "en"},
            "bilingual": {"language": "bilingual"},
        },
    },
    {
        "key": "q_sources_capabilities", "index": 5, "total": 9,
        "label": "来源与能力", "question": "这次研究要从哪些来源检索、启用哪些能力？",
        "fields": ("sources", "capability_profile"), "custom_field": "capability_profile",
        "allow_custom": True, "custom_label": "自定义（直接输入）",
        "choices": (
            {"id": "full", "label": "全部能力", "recommended": True},
            {"id": "search_eval", "label": "检索+评估", "recommended": False},
            {"id": "catalog_only", "label": "仅目录检索", "recommended": False},
        ),
        "values": {
            "full": {"sources": ["usenix"], "capability_profile": "full"},
            "search_eval": {"sources": ["usenix"], "capability_profile": "search_eval"},
            "catalog_only": {"sources": ["usenix"], "capability_profile": "catalog_only"},
        },
    },
    {
        "key": "q_budget_depth", "index": 6, "total": 9,
        "label": "预算 / 研究深度", "question": "这次研究希望投入多少预算、做多深？",
        "fields": ("depth", "budget_profile"), "custom_field": "budget_profile",
        "allow_custom": True, "custom_label": "自定义（直接输入）",
        "choices": (
            {"id": "balanced", "label": "均衡", "recommended": True},
            {"id": "fast", "label": "快速", "recommended": False},
            {"id": "deep", "label": "深度", "recommended": False},
        ),
        "values": {
            "balanced": {"depth": "balanced", "budget_profile": "balanced"},
            "fast": {"depth": "speed", "budget_profile": "fast"},
            "deep": {"depth": "quality", "budget_profile": "deep"},
        },
    },
    {
        "key": "q_paper_count", "index": 7, "total": 9,
        "label": "目标论文数", "question": "希望以多少篇论文为目标？",
        "fields": ("constraints",), "custom_field": "constraints",
        "allow_custom": True, "custom_label": "自定义（直接输入）",
        "choices": (
            {"id": "p5", "label": "5 篇", "recommended": True},
            {"id": "p3", "label": "3 篇", "recommended": False},
            {"id": "p10", "label": "10 篇", "recommended": False},
        ),
        # 契约硬约束：沿用 resolve_paper_count_constraints 依赖的既有编码。
        "values": {
            "p5": {"constraints": ["target_paper_count:5"]},
            "p3": {"constraints": ["target_paper_count:3"]},
            "p10": {"constraints": ["target_paper_count:10"]},
        },
    },
    {
        "key": "q_report_structure", "index": 8, "total": 9,
        "label": "报告结构", "question": "希望生成什么结构的报告？",
        "fields": ("output", "citations", "report_profile"), "custom_field": "report_profile",
        "allow_custom": True, "custom_label": "自定义（直接输入）",
        "choices": (
            {"id": "standard", "label": "标准综述", "recommended": True},
            {"id": "deep", "label": "深度报告", "recommended": False},
            {"id": "brief", "label": "简报", "recommended": False},
        ),
        "values": {
            "standard": {"output": "markdown", "citations": "inline", "report_profile": "standard"},
            "deep": {"output": "markdown", "citations": "inline", "report_profile": "deep"},
            "brief": {"output": "markdown", "citations": "inline", "report_profile": "brief"},
        },
    },
    {
        "key": "q_degradation", "index": 9, "total": 9,
        "label": "降级策略", "question": "遇到来源不足时希望如何降级？",
        "fields": ("degradation_policy",), "custom_field": "degradation_policy",
        "allow_custom": True, "custom_label": "自定义（直接输入）",
        "choices": (
            {"id": "balanced", "label": "平衡", "recommended": True},
            {"id": "conservative", "label": "保守", "recommended": False},
            {"id": "flexible", "label": "弹性", "recommended": False},
        ),
        "values": {
            "balanced": {"degradation_policy": "balanced"},
            "conservative": {"degradation_policy": "conservative"},
            "flexible": {"degradation_policy": "flexible"},
        },
    },
)

QUICK_ACTIONS: tuple[dict[str, str], ...] = (
    {"id": "use_recommended", "label": "用推荐"},
    {"id": "use_all_recommended", "label": "都按推荐"},
)

ACTIVATE_SKILL_SCHEMA = {
    "type": "object",
    "properties": {"skill_name": {"type": "string"}},
    "required": ["skill_name"],
    "additionalProperties": False,
}
ACTIVATE_SKILL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "skill": {"type": "object"},
        "schema_version": {"type": "string"},
    },
    "required": ["skill", "schema_version"],
}
BEGIN_RESEARCH_INTAKE_SCHEMA = {
    "type": "object",
    "properties": {
        "conversation_id": {"type": "string"},
        "message_id": {"type": "string"},
        "fields": {"type": "object"},
    },
    "required": ["conversation_id", "message_id", "fields"],
    "additionalProperties": False,
}
BEGIN_RESEARCH_INTAKE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "research_session_id": {"type": "string"},
        "intake_draft_id": {"type": "string"},
        "fields": {"type": "array"},
        "missing": {"type": "array"},
    },
    "required": ["research_session_id", "intake_draft_id", "fields", "missing"],
}
REGISTERED_CAPABILITIES = {
    "activate_skill": {
        "input_schema": ACTIVATE_SKILL_SCHEMA,
        "output_schema": ACTIVATE_SKILL_OUTPUT_SCHEMA,
    },
    "begin_research_intake": {
        "input_schema": BEGIN_RESEARCH_INTAKE_SCHEMA,
        "output_schema": BEGIN_RESEARCH_INTAKE_OUTPUT_SCHEMA,
    },
}


# ---------------------------------------------------------------------------
# Intake 意图路由：判断一条进入研究会话的用户消息是
#   (a) 「在回答 Intake 提问」  → 喂给抽取器（既有主流程）
#   (b) 「在提问 / 元问题 / 下命令」 → 走普通对话/命令通道，不喂抽取器
#
# **默认取向（fail-open）**：默认归为 (a)（喂抽取器）。只有当消息被**明确识别**
# 为提问或命令时才归为 (b)。理由（与需求方拍板一致）：宁可偶尔把一句提问当成
# 回答，也绝不让正常填写流程被漏掉；这样不会破坏既有主流程。任何未匹配规则
# 的消息都回落到 (a)。
#
# 实现选择：规则 / 确定性判定，零依赖、可注入、可单测、不加延迟。仓库已有
# ``backend/app/skills/intent.py``（Skill 调用意图）与 ``classify_memory_intent``
# （memory 存储意图），两者服务完全不同的领域、且含 LLM 调用，不适用于本场景；
# 因此此处新增一个独立的规则分类器，并不重复既有 LLM 意图实现（项目红线）。
# ---------------------------------------------------------------------------
_INTENT_QUESTION_END = "？?"
_INTENT_QUESTION_PREFIXES = (
    "哪些", "什么", "怎么", "怎样", "为什么", "为何", "能否", "能不能",
    "可不可以", "有没有", "多少", "何时", "哪个", "哪几个", "谁", "啥",
    "几点", "哪儿", "哪里", "如何", "有哪些", "有什么", "这些是",
)
_INTENT_COMMAND_PREFIXES = (
    "取消", "重来", "重新开始", "重新做", "重新来", "换主题", "换个主题",
    "换个", "不要了", "中止", "退出研究", "结束研究", "结束", "算了",
    "别做", "别再", "先暂停", "暂停", "退出", "停止", "停一下",
)
# 元问题短句：命中即 (b)。覆盖「有哪些研究目标能给我选」「这是什么意思」等。
_INTENT_META_SUBSTRINGS = (
    "能给我选", "给我选", "是什么意思", "什么意思", "刚才填", "之前填",
    "我填的", "填的是", "刚才说的", "之前说的", "有什么区别", "怎么理解",
)
# 礼貌 / 主语前缀：判定「是否以疑问词开头」前先剥掉，避免「我想问…」漏判。
_INTENT_LEADING_POLITE = (
    "请", "那", "你就", "你看", "我想问", "我想知道", "请问", "帮我看看",
    "帮我说说", "我想", "我", "你", "它", "这",     "那我们",
)

# 单篇论文解读负向特征（B 文本兜底）：命中即归 ordinary，覆盖把「关于本篇提问」
# 草稿粘贴到普通会话、或纯文本无法获知会话绑定时，把「解读这篇论文 / 基于全文
# 分析 / 使用RAG」误判为深度研究的情形。分类器纯规则、确定性、可单测、零 LLM 调用。
_SINGLE_PAPER_MARKERS = (
    "这篇论文", "这一篇", "基于全文", "证据等级", "全文索引片段",
    "使用rag", "关于本篇",
)
# 「研究 / 分析」作动词时，其后两字不应是这些名词后缀，否则只是名词短语
# （研究问题 / 研究目标 / 研究方法 …），不触发显式深度研究。
_RESEARCH_NOUN_SUFFIXES = frozenset(
    {
        "问题", "目标", "方向", "现状", "结论", "意义", "背景", "综述",
        "进展", "热点", "趋势", "框架", "范式", "方法", "结果", "思路",
        "价值", "空白", "难点", "挑战", "贡献", "局限", "摘要", "定义",
        "分类", "对比", "差异",
    }
)
# 礼貌前缀：判定「显式研究 / 分析」动词前先剥掉，避免「我想问…」漏判；
# 与 classify_intake_intent 的剥前缀思路一致，但此处用于显式深度研究信号。
_EXPLICIT_PREFIXES = ("请帮我", "帮我", "请")


def _explicit_verb_match(text: str) -> bool:
    """收紧过的「显式研究 / 分析」判定：仅动词用法命中，名词短语不命中。

    在礼貌前缀后的 12 字窗口内遍历所有「研究 / 分析」，只要存在一个其后两字
    不是常见名词后缀、且确有后续内容（与原正则 ``.{2,}`` 一致）的动词用法，
    即判显式；避免「研究问题 / 研究目标」等名词短语误触发深度研究。
    """
    for prefix in _EXPLICIT_PREFIXES:
        idx = text.find(prefix)
        if idx == -1:
            continue
        start = idx + len(prefix)
        window = text[start:start + 12]
        for vm in re.finditer(r"(?:研究|分析)", window):
            v_end = start + vm.end()
            after = text[v_end:v_end + 2]
            if len(after) >= 2 and after not in _RESEARCH_NOUN_SUFFIXES:
                return True
    return False


def classify_intake_intent(message: str) -> str:
    """Return ``"answer"`` (a) or ``"question_or_command"`` (b).

    Default (fail-open) is ``"answer"`` — see module note above.  The logic is
    intentionally regex/keyword based so it is deterministic, dependency-free,
    and unit-testable; a model-backed classifier can be injected instead via
    ``ResearchIntakeCoordinator(intent_classifier=...)`` without touching callers.
    """
    text = (message or "").strip()
    if not text:
        return "answer"
    # (b) 强信号：以问号结尾
    if text[-1] in _INTENT_QUESTION_END:
        return "question_or_command"
    # 剥掉礼貌 / 主语前缀后，若以疑问词开头 → (b)
    head = text
    changed = True
    while changed:
        changed = False
        for prefix in _INTENT_LEADING_POLITE:
            if head.startswith(prefix):
                head = head[len(prefix):]
                changed = True
                break
    if any(head.startswith(q) for q in _INTENT_QUESTION_PREFIXES):
        return "question_or_command"
    # (b) 命令：以命令词开头
    if any(text.startswith(c) for c in _INTENT_COMMAND_PREFIXES):
        return "question_or_command"
    # (b) 元问题短句
    if any(s in text for s in _INTENT_META_SUBSTRINGS):
        return "question_or_command"
    # 其余一律归为 (a)，维持既有填写流程
    return "answer"


@dataclass
class IntakeResult:
    status: str
    session: ResearchSession | None = None
    fields: list[IntakeField] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    activation: dict[str, Any] | None = None
    choices: list[dict[str, str]] = field(default_factory=list)
    error: dict[str, Any] | None = None
    question: str | None = None
    # 逐轮引导式询问（契约 2.4）：由 derive_guided_state(saved) 确定性推导，
    # 旧字段（status/session/fields/missing/activation/choices/error/question）
    # 类型与语义一律不变。
    prompt: dict[str, Any] | None = None
    quick_actions: list[dict[str, str]] = field(default_factory=list)
    progress: dict[str, int] | None = None


# ---------------------------------------------------------------------------
# 逐轮引导式询问：纯确定性推导 + 回答协议解析（零 LLM、零 DB 访问）。
# ---------------------------------------------------------------------------
_INTAKE_PROTOCOL_RE = re.compile(r"\[intake:([^\]]+)\]")
# 带标记但解析失败的消息也必须走「拒绝」路径，绝不能落回抽取器被当成
# BLOCKING 字段的补充文本（契约 2.5：解析失败不写库、当前轮不变、不抛 500）。
_INTAKE_MARKER_RE = re.compile(r"\[intake:", re.IGNORECASE)
_CUSTOM_MAX_LEN = 400
# 除控制字符外，协议边界符与「伪造参数」分隔符一律拒绝，避免借 custom 注入。
_CUSTOM_FORBIDDEN_CHARS = frozenset("[];")


def _public_prompt(question: dict[str, Any]) -> dict[str, Any]:
    """Return only the contract-2.4 keys; never leak the value mapping."""
    prompt = {key: question[key] for key in _PROMPT_PUBLIC_KEYS}
    prompt["choices"] = [dict(choice) for choice in question["choices"]]
    return prompt


def _round_answered(question: dict[str, Any], by_name: dict[str, IntakeField]) -> bool:
    """契约 2.1 状态表：user_explicit / confirmed / 历史 not_required 均已回答。"""
    for name in question["fields"]:
        item = by_name.get(name)
        if item is None:
            return False
        if item.confirmation_status in {"confirmed", "not_required"}:
            continue
        if item.source == "user_explicit":
            continue
        return False
    return True


def derive_guided_state(fields: list[IntakeField]) -> dict[str, Any]:
    """From persisted fields, derive the first pending round and progress.

    Pure function: refresh/replay always yields the same prompt for the same
    field provenance; no extra state table and no LLM call is involved.
    """
    by_name = {item.field_name: item for item in fields}
    # 契约 2.1 / 5.1 历史兼容：改前创建的历史会话没有 4 个新 profile 字段，
    # 其默认值是 not_required（新会话写 unconfirmed）。若按「缺字段即待问」
    # 推导，老会话会被重新追问，/plans/generate 也会误判为引导未收齐而拒绝
    # 生成计划。此类会话整体视为已收齐（prompt=None），历史回放同理。
    is_legacy = (
        bool(fields)
        and not any(item.field_name in _PROFILE_FIELDS for item in fields)
        and not any(item.confirmation_status == "unconfirmed" for item in fields)
    )
    pending = (
        []
        if is_legacy
        else [item for item in GUIDED_QUESTIONS if not _round_answered(item, by_name)]
    )
    answered = len(GUIDED_QUESTIONS) - len(pending)
    seen: set[str] = set()
    pending_fields: list[str] = []
    for question in pending:
        for name in question["fields"]:
            if name not in seen:
                seen.add(name)
                pending_fields.append(name)
    return {
        "prompt": _public_prompt(pending[0]) if pending else None,
        "quick_actions": [dict(action) for action in QUICK_ACTIONS],
        "progress": {"answered": answered, "total": len(GUIDED_QUESTIONS)},
        "pending_fields": pending_fields,
        "pending_questions": pending,
    }


def _recommended_choice(question: dict[str, Any]) -> dict[str, Any]:
    return next(choice for choice in question["choices"] if choice["recommended"])


def sanitize_custom_text(text: str) -> str | None:
    """Validate ``custom:`` text (≤400, no control/protocol-injection chars).

    契约 2.5 要求限长并去掉换行与控制字符；此处采用更保守的「检出即拒绝」，
    使恶意输入整体不落库（任务验收要求），而非静默剥离后写入用户不可见的文本。
    """
    if not isinstance(text, str) or len(text) > _CUSTOM_MAX_LEN:
        return None
    for char in text:
        code = ord(char)
        if code < 32 or code == 127 or char in _CUSTOM_FORBIDDEN_CHARS:
            return None
    return text.strip() or None


def _parse_intake_answer(message: str) -> dict[str, Any] | None:
    """Parse the contract-2.5 ``[intake:key=value]`` answer protocol.

    Returns ``None`` for anything that is not exactly one well-formed marker;
    the caller then leaves the store untouched and re-emits the current prompt.
    """
    matches = _INTAKE_PROTOCOL_RE.findall(message or "")
    if len(matches) != 1:
        return None
    token = matches[0].strip()
    if "=" not in token:
        return None
    key, value = (part.strip() for part in token.split("=", 1))
    if not key or not value:
        return None
    by_key = {question["key"]: question for question in GUIDED_QUESTIONS}
    if value == "use_all_recommended":
        return {"action": "use_all", "key": key}
    if key not in by_key:
        return None
    if value == "use_recommended":
        return {"action": "use_recommended", "key": key}
    if value == "custom" or value.startswith("custom:"):
        text = value[len("custom:"):] if value.startswith("custom:") else ""
        return {"action": "custom", "key": key, "text": sanitize_custom_text(text)}
    return {"action": "choice", "key": key, "choice_id": value}


def _resolve_protocol_answer(
    parsed: dict[str, Any], state: dict[str, Any]
) -> list[tuple[str, Any, str]] | None:
    """Map one parsed answer to ``(field_name, value, source)`` writes.

    Only the answered round's declared target fields are ever written; an
    unknown key / choice / invalid custom text yields ``None`` (no writes).
    """
    action = parsed["action"]
    # 契约 5.2：除 __all__（「都按推荐」）外，回答 key 必须等于当前轮
    # prompt.key。聊天历史里每条 intake 消息都有自己的引导按钮，点到旧消息
    # 的按钮会带旧轮次 key，一律按无效输入处理（不写库、不抛 500、当前轮
    # 不变可重试），避免覆盖已确认字段或错乱推进；9 轮全收齐后 prompt 为
    # None，同样拒绝。
    current_prompt = state.get("prompt")
    if parsed["key"] != "__all__" and (
        current_prompt is None or parsed["key"] != current_prompt["key"]
    ):
        return None
    if action == "use_all":
        entries: list[tuple[str, Any, str]] = []
        for question in state["pending_questions"]:
            recommended = _recommended_choice(question)
            entries.extend(
                (name, value, "system_default")
                for name, value in question["values"][recommended["id"]].items()
            )
        return entries or None
    by_key = {question["key"]: question for question in GUIDED_QUESTIONS}
    question = by_key.get(parsed["key"])
    if question is None:
        return None
    if action == "use_recommended":
        recommended = _recommended_choice(question)
        return [
            (name, value, "system_default")
            for name, value in question["values"][recommended["id"]].items()
        ]
    if action == "choice":
        values = question["values"].get(parsed["choice_id"])
        if values is None:
            return None
        return [(name, value, "user_explicit") for name, value in values.items()]
    if action == "custom":
        text = parsed.get("text")
        if text is None:
            return None
        recommended = _recommended_choice(question)
        values = dict(question["values"][recommended["id"]])
        # custom 只写该轮声明的目标字段：主字段用净化文本，同轮其余字段用推荐值。
        values[question["custom_field"]] = text
        return [(name, value, "user_explicit") for name, value in values.items()]
    return None


class ResearchIntakeCoordinator:
    """Classify a turn and maintain one resumable Intake per conversation."""

    def __init__(self, store, memory_repository, skill_registry, tool_registry=None, intent_classifier=None) -> None:
        self.store = store
        self.memory_repository = memory_repository
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry
        # 意图路由判定器，默认用内置规则分类器；可注入替换（如模型版）便于单测。
        self.intent_classifier = intent_classifier or classify_intake_intent

    @staticmethod
    def classify(message: str) -> str:
        text = (message or "").strip().lower()
        # 单篇解读负向特征优先：命中即 ordinary（至少不判 explicit），覆盖把
        # 「关于本篇提问」草稿粘贴到普通会话、或纯文本无法获知会话绑定时，把
        # 「解读这篇论文 / 基于全文分析 / 使用RAG」误判为深度研究的情形。
        if any(marker in text for marker in _SINGLE_PAPER_MARKERS):
            return "ordinary"
        explicit = (
            "深度研究" in text
            or "deep research" in text
            or "研究报告" in text
            or _explicit_verb_match(text)
        )
        if explicit:
            return "explicit"
        if any(token in text for token in ("查一下", "查查", "研究一下", "搜一下")):
            return "ambiguous"
        return "ordinary"

    def activate_skill(self, skill_name: str = DEEP_RESEARCH_SKILL) -> dict[str, Any]:
        """Perform the summary → enabled check → full body activation gate."""
        if skill_name != DEEP_RESEARCH_SKILL:
            return {
                "ok": False,
                "error": {"code": "CAPABILITY_NOT_AUTHORIZED", "message": "仅允许激活 Deep Research Skill"},
            }
        summary = next(
            (item for item in self.skill_registry.list_skills() if item.name == skill_name),
            None,
        )
        if summary is None:
            return {
                "ok": False,
                "error": {"code": "CAPABILITY_NOT_AUTHORIZED", "message": "Skill 不存在"},
            }
        if not summary.enabled:
            return {
                "ok": False,
                "error": {"code": "SKILL_DISABLED", "message": "Deep Research Skill 已禁用"},
            }
        detail = self.skill_registry.get_skill(skill_name)
        if detail is None:
            return {
                "ok": False,
                "error": {"code": "CAPABILITY_NOT_AUTHORIZED", "message": "Skill 正文不可用"},
            }
        declared_tools = tuple(detail.tools)
        if self.tool_registry is not None:
            for tool_name in declared_tools:
                tool = self.tool_registry.get_tool(tool_name)
                if tool is None or not tool.enabled:
                    return {
                        "ok": False,
                        "error": {
                            "code": "CAPABILITY_NOT_AUTHORIZED",
                            "message": f"Skill 声明的 Tool 不可用：{tool_name}",
                        },
                    }
        elif declared_tools:
            return {
                "ok": False,
                "error": {"code": "CAPABILITY_NOT_AUTHORIZED", "message": "Skill Tool Registry 不可用"},
            }
        content_hash = hashlib.sha256(detail.body.encode("utf-8")).hexdigest()
        return {
            "ok": True,
            "skill": {
                "name": detail.name,
                "description": detail.description,
                "tools": list(detail.tools),
                "body": detail.body,
                "schema_version": "1",
                "skill_id": detail.name,
                "version": "1",
                "content_hash": content_hash,
            },
            "schema_version": "1",
        }

    def begin_research_intake(
        self,
        conversation_id: str,
        owner_id: str,
        message_id: str,
        fields: dict[str, Any] | None = None,
    ) -> IntakeResult:
        """Explicit capability entry point used by a conversation Agent.

        ``handle_message`` is the HTTP-facing classifier; this method is the
        structured capability it delegates to and is intentionally limited to
        Session/Draft persistence.
        """
        active = self._active_session(conversation_id, owner_id)
        if active is not None:
            return self._active_conflict(active)
        activation = self.activate_skill()
        if not activation["ok"]:
            return IntakeResult(status="error", error=activation["error"])
        session = ResearchSession(
            research_session_id=uuid.uuid4().hex,
            owner_id=owner_id,
            conversation_id=conversation_id,
            trigger_message_id=message_id,
            intake_draft_id=uuid.uuid4().hex,
            status="intake_pending",
        )
        try:
            session = self.store.create_session(session, memory_repository=self.memory_repository)
        except ResearchSessionActiveConflict:
            return self._active_conflict(self._active_session(conversation_id, owner_id))
        self._persist_fields(session, fields or {}, message_id, owner_id)
        saved = self.store.list_intake_fields(session.intake_draft_id, owner_id)
        return self._finalize_turn(session, owner_id, saved, activation)

    def handle_message(
        self, conversation_id: str, owner_id: str, message_id: str, message: str
    ) -> IntakeResult:
        # 契约 2.5：任何带 [intake: 标记的消息都在「最开头」特判，跳过
        # classify() / intent_classifier() / active_conflict / draft-complete
        # 分支。解析失败时 parsed 为 None，由 _handle_intake_answer 走「不写库、
        # 当前轮不变、可重试」的拒绝路径；这也让「BLOCKING 已齐但 9 轮尚未问完」
        # 的会话仍能逐轮回答。
        if _INTAKE_MARKER_RE.search(message or ""):
            return self._handle_intake_answer(
                conversation_id, owner_id, message_id, _parse_intake_answer(message)
            )
        classification = self.classify(message)
        active = self._active_session(conversation_id, owner_id)
        if active is None and classification == "ordinary":
            return IntakeResult(status="ordinary")
        if active is None and classification == "ambiguous":
            return IntakeResult(
                status="clarification",
                question="你是想让我进行深度研究，还是只查找一条信息？请说明研究主题、目标和时间范围。",
            )

        # A second explicit research request in the same conversation is a
        # new-intent attempt, not an Intake answer.  Preserve the active
        # projection and return the product's three explicit choices.
        if active is not None and classification == "explicit" and message_id != active.trigger_message_id:
            return self._active_conflict(active)

        activation = self.activate_skill()
        if not activation["ok"]:
            return IntakeResult(status="error", error=activation["error"])

        if active is None:
            fields = self._extract_fields(message)
            session = ResearchSession(
                research_session_id=uuid.uuid4().hex,
                owner_id=owner_id,
                conversation_id=conversation_id,
                trigger_message_id=message_id,
                intake_draft_id=uuid.uuid4().hex,
                status="intake_pending",
            )
            try:
                session = self.store.create_session(session, memory_repository=self.memory_repository)
            except ResearchSessionActiveConflict:
                active = self._active_session(conversation_id, owner_id)
                return self._active_conflict(active)
            self._persist_fields(session, fields, message_id, owner_id)
        else:
            session = active
            # ① 收齐即停：draft 已 complete（参数齐全或计划已生成）后，后续用户
            # 消息不再进入抽取器，改为走普通对话/命令通道，避免污染已确认字段。
            draft = self.store.get_intake_draft(session.research_session_id, owner_id)
            if draft is not None and draft.status == "complete":
                return IntakeResult(status="ordinary")
            # Replaying the trigger message returns the durable projection and
            # does not create another session or rewrite field provenance.
            if message_id != session.trigger_message_id:
                # ② 意图判定：默认归为「回答 intake」（喂抽取器）；只有被明确识别为
                # 提问 / 元问题 / 命令时才走普通通道（b），不污染 Intake 字段。
                if self.intent_classifier(message) == "question_or_command":
                    return IntakeResult(status="ordinary")
                self._persist_fields(session, self._extract_follow_up(session, message), message_id, owner_id)

        saved = self.store.list_intake_fields(session.intake_draft_id, owner_id)
        return self._finalize_turn(session, owner_id, saved, activation)

    def _handle_intake_answer(
        self,
        conversation_id: str,
        owner_id: str,
        message_id: str,
        parsed: dict[str, Any] | None,
    ) -> IntakeResult:
        """Apply one protocol answer, then recompute missing/prompt (契约 2.5)."""
        session = self._active_session(conversation_id, owner_id)
        if session is None:
            return IntakeResult(status="ordinary")
        saved = self.store.list_intake_fields(session.intake_draft_id, owner_id)
        state = derive_guided_state(saved)
        entries = _resolve_protocol_answer(parsed, state) if parsed is not None else None
        if entries is not None:
            for name, value, source in entries:
                self.store.upsert_intake_field(
                    IntakeField(
                        intake_draft_id=session.intake_draft_id,
                        field_name=name,
                        value_json=json.dumps(value, ensure_ascii=False),
                        source=source,
                        confidence=1.0,
                        confirmation_status="confirmed",
                        updated_by_message_id=message_id,
                        updated_at="",
                    ),
                    owner_id,
                )
            saved = self.store.list_intake_fields(session.intake_draft_id, owner_id)
        # 解析失败/非法输入：不写库、不抛 500，返回当前轮不变（可重试）。
        try:
            activation = self.activate_skill()
        except Exception:
            activation = None
        return self._finalize_turn(session, owner_id, saved, activation)

    def _finalize_turn(
        self,
        session: ResearchSession,
        owner_id: str,
        saved: list[IntakeField],
        activation: dict[str, Any] | None,
    ) -> IntakeResult:
        """Complete the draft only when both legacy fields and all 9 rounds are done."""
        missing = self._missing_fields(saved)
        state = derive_guided_state(saved)
        # 契约 5.1：draft complete 必须同时满足 BLOCKING 齐备且 9 轮引导全部
        # 收齐（prompt 为 null）。否则首句说全 topic/objective/time_range 时
        # missing 为空但引导还有 6 轮，计划会提前用默认值生成并被 replay 缓存。
        if not missing and state["prompt"] is None:
            draft = self.store.get_intake_draft(session.research_session_id, owner_id)
            if draft is not None and draft.status == "collecting":
                self.store.update_intake_status(draft.intake_draft_id, owner_id, "complete")
        # 契约 2.4「旧字段类型与语义一律不变」：question 保持既有 _question
        # 语义（BLOCKING / constraints 待澄清时「请补充：…」，收齐后 None）；
        # 当前这一轮的问句由新增的 prompt.question 承载，前端引导区块读它。
        # 这样旧前端的 editable 逻辑、finalize_intake_message 的「参数齐全」
        # 文案与历史回放契约都不回归。
        return IntakeResult(
            status="intake",
            session=session,
            fields=saved,
            missing=missing,
            activation=activation,
            question=self._question(missing),
            prompt=state["prompt"],
            quick_actions=state["quick_actions"],
            progress=state["progress"],
        )

    def _active_session(self, conversation_id: str, owner_id: str) -> ResearchSession | None:
        finder = getattr(self.store, "get_active_session", None)
        if finder is not None:
            return finder(conversation_id, owner_id)
        sessions = self.store.list_sessions(owner_id)
        return next(
            (
                item
                for item in sessions
                if item.conversation_id == conversation_id and item.status not in SESSION_TERMINAL
            ),
            None,
        )

    @staticmethod
    def _active_conflict(session: ResearchSession | None) -> IntakeResult:
        return IntakeResult(
            status="active_conflict",
            session=session,
            choices=[
                {"id": "modify_current", "label": "修改当前研究"},
                {"id": "cancel_then_new", "label": "取消后新建"},
                {"id": "new_conversation", "label": "在新会话研究"},
            ],
            error={
                "code": "RESEARCH_SESSION_ACTIVE_CONFLICT",
                "message": "当前会话已有进行中的研究 Intake",
                "retryable": False,
            },
        )

    def _persist_fields(self, session, values: dict[str, Any], message_id: str, owner_id: str) -> None:
        existing = {item.field_name: item for item in self.store.list_intake_fields(session.intake_draft_id, owner_id)}
        for name, value in {**DEFAULT_FIELDS, **values}.items():
            if name in existing and existing[name].updated_by_message_id == message_id:
                continue
            source = "user_explicit" if name in values else "system_default"
            # 契约 2.1：新会话默认字段写 unconfirmed（待询问），用户明确写
            # confirmed。已确认（用推荐 / 都按推荐 / 点候选）或历史 not_required
            # 的默认值不能被后续消息重置回 unconfirmed，否则用户的选择会丢失、
            # 历史会话会被重新追问。
            if source == "system_default" and name in existing:
                previous = existing[name]
                if previous.confirmation_status in {"confirmed", "not_required"}:
                    continue
            confirmation = "confirmed" if source == "user_explicit" else "unconfirmed"
            self.store.upsert_intake_field(
                IntakeField(
                    intake_draft_id=session.intake_draft_id,
                    field_name=name,
                    value_json=json.dumps(value, ensure_ascii=False),
                    source=source,
                    confidence=1.0,
                    confirmation_status=confirmation,
                    updated_by_message_id=message_id,
                    updated_at="",
                ),
                owner_id,
            )

    @staticmethod
    def _extract_fields(message: str) -> dict[str, Any]:
        text = (message or "").strip()
        values: dict[str, Any] = {}
        topic = ResearchIntakeCoordinator._capture(text, r"主题(?:是|为)[:：]?(.+?)(?:，|,|。|；|;|$)")
        if topic is None:
            topic = ResearchIntakeCoordinator._capture(text, r"关于\s*(.+?)(?:的深度研究|进行深度研究|研究|，|,|。|$)")
        if topic is None:
            topic = ResearchIntakeCoordinator._capture(text, r"(?:^|[，,。；;])研究\s*(.+?)(?:，|,|。|；|;|$)")
        if topic:
            values["topic"] = topic.strip()
        objective = ResearchIntakeCoordinator._capture(text, r"目标(?:是|为)[:：]?(.+?)(?:，|,|。|；|;|$)")
        if objective is None:
            objective = ResearchIntakeCoordinator._capture(text, r"(?:总结|分析|梳理)(.{2,}?)(?:，|,|。|；|;|$)")
        if objective:
            values["objective"] = objective.strip()
        years = re.search(r"(20\d{2})\s*(?:-|–|—|~|至|到)\s*(20\d{2})", text)
        if years:
            values["time_range"] = {"from": int(years.group(1)), "to": int(years.group(2))}
        constraints = extract_paper_count_constraints(text)
        if constraints:
            values["constraints"] = constraints
        return values

    def _extract_follow_up(self, session: ResearchSession, message: str) -> dict[str, Any]:
        values = self._extract_fields(message)
        saved = {item.field_name for item in self.store.list_intake_fields(session.intake_draft_id, session.owner_id)}
        missing = [name for name in BLOCKING_FIELDS if name not in saved]
        plain = (message or "").strip()
        if len(missing) == 1 and plain and missing[0] not in values:
            values[missing[0]] = plain
        return values

    @staticmethod
    def _capture(text: str, pattern: str) -> str | None:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        return match.group(1).strip() if match else None

    @staticmethod
    def _has_value(fields: list[IntakeField], name: str) -> bool:
        return any(item.field_name == name and item.value_json not in ("", "null", "[]") for item in fields)

    @classmethod
    def _missing_fields(cls, fields: list[IntakeField]) -> list[str]:
        missing = [name for name in BLOCKING_FIELDS if not cls._has_value(fields, name)]
        constraints = next((item for item in fields if item.field_name == "constraints"), None)
        if constraints is not None:
            try:
                value = json.loads(constraints.value_json or "null")
            except (TypeError, ValueError):
                value = None
            resolution = resolve_paper_count_constraints(value)
            if resolution["has_count_constraint"] and not resolution["valid"]:
                missing.append("constraints")
        return missing

    @staticmethod
    def _question(missing: list[str]) -> str | None:
        labels = {
            "topic": "研究主题",
            "objective": "研究目标",
            "time_range": "时间范围",
            "constraints": "论文数量约束",
        }
        return "请补充：" + "、".join(labels[item] for item in missing) if missing else None


__all__ = [
    "ACTIVATE_SKILL_SCHEMA",
    "ACTIVATE_SKILL_OUTPUT_SCHEMA",
    "BEGIN_RESEARCH_INTAKE_SCHEMA",
    "BEGIN_RESEARCH_INTAKE_OUTPUT_SCHEMA",
    "REGISTERED_CAPABILITIES",
    "BLOCKING_FIELDS",
    "DEFAULT_FIELDS",
    "GUIDED_QUESTIONS",
    "QUICK_ACTIONS",
    "derive_guided_state",
    "sanitize_custom_text",
    "ResearchIntakeCoordinator",
    "IntakeResult",
    "classify_intake_intent",
]
