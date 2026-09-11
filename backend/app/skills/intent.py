"""对话链路中的 Skill 意图识别（spec-023 Task06，只做识别与路由，不做执行）。

双触发策略（来自 task-02 RESULT.md 的可行性结论）：
1. 第一跳：规则匹配（词边界 + 指令性动词）—— 零成本、确定性；命中即返回，省一次推理。
2. 第二跳：规则未命中且消息值得判断时才调用 LLM 做 3 选 1 意图识别
   （temperature=0，可选 ``<技能名>`` 或 ``none``）。

硬约束（RESULT.md R2/R3/R4）：
- 规则必须**词边界** + **指令性动词**，避免「听说过 / 关于 / 是什么」等假阳性；
  单纯提及、拼写错误（如 papper）不得触发。
- LLM 调用 ``trust_env=False``、``timeout >= 60s``、带 1 次重试；任何失败/超时都
  **降级为 none**，绝不影响对话、绝不抛异常。
- thinking 模型必须显式 ``think: false``，否则 ``content`` 为空。
- 地址/模型取自 ``backend.app.platform.config``，不硬编码。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

import httpx

from backend.app.platform.config import MODEL_NAME
from backend.app.platform.ollama_direct import chat_direct_stream
from backend.app.skills.models import SkillSummary

logger = logging.getLogger(__name__)

# 指令性动词：点名调用 Skill 时才算「意图」。不含单纯提及/疑问用词。
# 注意：裸「用」也会被当作触发词，但左侧边界校验（见 _VERB_PATTERN）会排除
# 「很好用」「用户用」等嵌在词中的情况；且第二跳仅在「已知技能名被提及」或
# 「动词 + 类技能名 token」时才触发，避免对普通消息额外调用 LLM。
INSTRUCTION_VERBS = (
    "帮我用",
    "请使用",
    "帮我调用",
    "请用",
    "使用",
    "调用",
    "运行",
    "执行",
    "启用",
    "开启",
    "启动",
    "用",
)
_VERB_PATTERN = re.compile(
    r"(?<![A-Za-z0-9一-鿿])(" + "|".join(map(re.escape, INSTRUCTION_VERBS)) + r")(?![一-鿿])"
)
# 类技能名 token：带连字符的 ascii 词，如 usenix-paper-catalog-search / foobar-skill。
_LOOSE_SKILL_TOKEN = re.compile(
    r"(?<![A-Za-z0-9-])([A-Za-z0-9]+(?:-[A-Za-z0-9]+)+)(?![A-Za-z0-9-])"
)

LLM_TIMEOUT_SECONDS = 60.0
LLM_RETRY = 1


@dataclass
class SkillDecision:
    """Skill 识别结果。

    status:
      - ``matched``   命中且可用（enabled=true）
      - ``disabled``  命中但已禁用（enabled=false）
      - ``not_found`` 明确点名了某个技能，但该名称不存在于可用列表
      - ``ambiguous`` 同时命中多个技能
      - ``none``      无 Skill 意图
    skill:    命中的技能名（none/ambiguous 时为 None）
    source:   命中来源 ``rule`` | ``llm`` | None
    requested:用户尝试点名的原始名称（not_found 时用于提示）
    """

    status: str
    skill: Optional[str] = None
    source: Optional[str] = None
    requested: Optional[str] = None

    def is_usable(self) -> bool:
        return self.status == "matched" and self.skill is not None


def _name_token_pattern(name: str) -> "re.Pattern[str]":
    # 词边界：技能名前后不得是 [A-Za-z0-9-]（CJK 视为分隔符，避免 usenix-papper 误命中 usenix-paper）。
    return re.compile(r"(?<![A-Za-z0-9-])" + re.escape(name) + r"(?![A-Za-z0-9-])")


def _mentions_name(message: str, name: str) -> bool:
    return bool(_name_token_pattern(name).search(message))


def _verb_before_name(message: str, name: str) -> bool:
    match = _name_token_pattern(name).search(message)
    if not match:
        return False
    # 指令性动词必须出现在技能名之前（同句/同消息内）。
    return bool(_VERB_PATTERN.search(message[: match.start()]))


def detect_skill(message: str, available_skills: Sequence[SkillSummary]) -> SkillDecision:
    """识别用户消息是否点名了某个 Skill，以及命中来源。

    第一跳规则命中即返回；否则仅在「消息提及已知技能名」或「含动词 + 类技能名
    token」时才调 LLM（避免对普通消息额外推理）。可用列表为空直接返回 none。
    """
    available = list(available_skills)
    if not available:
        return SkillDecision(status="none")

    # ---------- 第一跳：规则匹配 ----------
    matched = [s for s in available if _verb_before_name(message, s.name)]
    if len(matched) == 1:
        skill = matched[0]
        return SkillDecision(
            status="matched" if skill.enabled else "disabled",
            skill=skill.name,
            source="rule",
        )
    if len(matched) > 1:
        return SkillDecision(status="ambiguous", source="rule")

    # ---------- 是否值得调用 LLM ----------
    mentions_known = any(_mentions_name(message, s.name) for s in available)
    loose = _LOOSE_SKILL_TOKEN.search(message)
    has_invocation = bool(_VERB_PATTERN.search(message))
    worth_llm = mentions_known or (has_invocation and loose is not None)
    if not worth_llm:
        # 未点名任何 Skill：行为与改动前完全一致，且不调用 LLM。
        return SkillDecision(status="none")

    # ---------- 第二跳：LLM 意图识别 ----------
    llm_name = _llm_detect(message, [s.name for s in available])
    if llm_name is None:
        return SkillDecision(status="none")

    by_name = {s.name: s for s in available}
    if llm_name in by_name:
        skill = by_name[llm_name]
        return SkillDecision(
            status="matched" if skill.enabled else "disabled",
            skill=skill.name,
            source="llm",
        )
    # 用户点名了不在列表里的技能 -> 不存在。
    return SkillDecision(status="not_found", requested=llm_name, source="llm")


def _llm_detect(message: str, available_names: Sequence[str]) -> Optional[str]:
    """调用 LLM 做 3 选 1 意图识别；任何失败/超时都返回 None（降级为 none）。"""
    prompt = _build_intent_prompt(message, available_names)
    try:
        raw = _call_intent_model(prompt)
    except Exception as error:  # 连接/超时/解析异常一律降级，不影响对话
        logger.warning("Skill 意图识别 LLM 调用失败，降级为 none：%s", error)
        return None
    return _parse_intent_response(raw, available_names)


def _call_intent_model(prompt: str) -> str:
    """直连 Ollama 做意图分类；trust_env=False、think:false、timeout=60s、1 次重试。"""
    messages = [{"role": "user", "content": prompt}]
    last_error: Optional[Exception] = None
    for _ in range(LLM_RETRY + 1):
        try:
            stream = chat_direct_stream(
                messages,
                MODEL_NAME,
                timeout=LLM_TIMEOUT_SECONDS,
                think=False,
                options={"temperature": 0.0},
            )
            parts: List[str] = []
            for event in stream:
                if isinstance(event, dict) and event.get("type") == "token":
                    parts.append(event.get("content") or "")
            return "".join(parts)
        except (httpx.HTTPError, RuntimeError) as error:
            last_error = error
            continue
    if last_error is not None:
        raise last_error
    return ""


def _build_intent_prompt(message: str, available_names: Sequence[str]) -> str:
    lines = [
        "你是对话路由助手。判断用户是否明确想要“使用 / 调用 / 运行”下列某个技能（Skill）。",
        "",
    ]
    if available_names:
        lines.append("可用技能：")
        for name in available_names:
            lines.append(f"- {name}")
        lines.append("")
    lines += [
        "判定规则：",
        "1. 仅当用户明确想要使用 / 调用 / 运行某个技能时才返回该技能名称；",
        "2. 单纯提及、询问（是什么 / 怎么用）、听说过、评价（很好用）等情况，返回 none；",
        "3. 如果用户点名的技能不在上面列表里，原样返回用户点名的技能名称；",
        "4. 否则返回 none。",
        "",
        "只输出一行：技能名称 或 none。不要任何解释或标点。",
        "",
        f"用户消息：{message}",
    ]
    return "\n".join(lines)


def _parse_intent_response(raw: str, available_names: Sequence[str]) -> Optional[str]:
    if not raw:
        return None
    text = raw.strip().strip("`\"'").strip()
    first = text.splitlines()[0].strip().strip("`\"'").strip() if text else ""
    if not first or first.lower() == "none":
        return None
    lowered = {name.lower(): name for name in available_names}
    if first.lower() in lowered:
        return lowered[first.lower()]
    # 若返回的不是「像技能名」的 token（含中文 / 空格 / 标点），当作 none 降级，
    # 避免把 LLM 的闲聊文本误判为「点名了不存在的技能」。
    if re.fullmatch(r"[A-Za-z0-9-]+", first):
        # 当作用户点名的原始技能名（可能不存在 → 上层映射为 not_found）。
        return first
    return None


def build_skill_prompt(question: str, skill_body: str) -> str:
    """把技能正文注入为本次对话上下文（Q5：由模型读正文自行编排）。"""
    return (
        "你正在使用一个技能。请严格遵循下面「技能正文」的指引来回答用户问题，"
        "不要偏离该技能的用途。\n\n"
        "===== 技能正文开始 =====\n"
        f"{skill_body}\n"
        "===== 技能正文结束 =====\n\n"
        f"用户问题：{question}"
    )


def to_intent_event(
    decision: SkillDecision, available_names: Optional[Sequence[str]] = None
) -> Optional[dict]:
    """构造 SSE intent 事件（前端已有 ``showSkillHint`` 消费 ``skill`` 字段）。

    none 时返回 None —— 即不发出任何额外事件，保持对话行为完全不变。
    """
    if decision.status == "matched":
        return {
            "type": "intent",
            "intent": decision.skill,
            "skill": decision.skill,
            "source": decision.source,
            "confidence": 1.0,
        }
    if decision.status == "disabled":
        return {
            "type": "intent",
            "intent": "disabled",
            "skill": None,
            "requested": decision.skill,
            "message": f"技能 {decision.skill} 已禁用，无法使用。",
            "confidence": 1.0,
        }
    if decision.status == "not_found":
        names = list(available_names or [])
        listing = "、".join(names) if names else "（当前没有可用技能）"
        return {
            "type": "intent",
            "intent": "not_found",
            "skill": None,
            "requested": decision.requested,
            "message": f"未找到名为「{decision.requested}」的技能。可用技能：{listing}",
            "confidence": 1.0,
        }
    if decision.status == "ambiguous":
        return {
            "type": "intent",
            "intent": "ambiguous",
            "skill": None,
            "message": "同时命中多个技能，请明确指定其中一个。",
            "confidence": 1.0,
        }
    return None


def format_skill_hint(
    decision: SkillDecision, available_names: Optional[Sequence[str]] = None
) -> Optional[str]:
    """返回需要直接展示给用户的提示文本（disabled / not_found / ambiguous 时）。

    matched / none 返回 None（matched 由模型正常回答，none 不提示）。
    """
    if decision.status == "disabled":
        return f"技能 {decision.skill} 已禁用，无法使用。"
    if decision.status == "not_found":
        names = list(available_names or [])
        listing = "、".join(names) if names else "（当前没有可用技能）"
        return f"未找到名为「{decision.requested}」的技能。可用技能：{listing}"
    if decision.status == "ambiguous":
        return "同时命中多个技能，请明确指定其中一个。"
    return None
