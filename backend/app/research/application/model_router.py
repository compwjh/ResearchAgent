"""模型路由（Spec027 §动态模型和 Worker）。

Spec027 要求「fast 模型输出不合法或低置信度时重试一次，仍失败升级 strong，并发出
可见 ``model_escalated`` 事件」。Task02 门禁用 ``FakeModelRouter``
（``tests/test_spec027_runtime_contract.py:268``）冻结了该出口分支（fast 始终非法 ->
升级 strong + ``MODEL_ESCALATED`` 事件）；本模块是该分支的**真实落地**，语义与
``FakeModelRouter.execute`` 同构：

- fast 成功 -> 返回 fast 选择，events 为空；
- fast 失败 -> 重试一次同样的 fast 模型；重试成功 -> 返回 fast，events 为空；
- 重试仍失败 -> 升级 strong，发出 ``{"type": "model", "code": "MODEL_ESCALATED",
  "from_tier": "fast", "to_tier": "strong", "reason": ...}`` 事件，返回 strong 选择。

模型清单唯一来源是 ``backend.app.platform.ollama.get_available_models``（Spec027 复用
接缝：禁止第二套模型客户端）。具体模型名不硬编码，仅用「参数量关键词」从可用清单解析档位。

档位匹配以模型名里的「尺寸 token」（``\\d+b``，如 ``9b`` / ``27b``）为单位，避免
``27b`` 被误判命中 fast 的 ``7b`` 关键词——这是门禁断言要求的精确语义。
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional, Tuple

from backend.app.platform.ollama import get_available_models
from backend.app.research.domain.contracts import ERROR_CODES, ROLE_WHITELIST

FAST_TIER = "fast"
STRONG_TIER = "strong"

# 角色默认档位（Spec027：Planner/Critic/Synthesizer 默认 strong；查询扩展、初筛、
# 结构化抽取默认 fast）。
DEFAULT_TIER_BY_ROLE = {
    "planner": STRONG_TIER,
    "search-worker": FAST_TIER,
    "paper-evaluator": FAST_TIER,
    "research-critic": STRONG_TIER,
    "synthesizer": STRONG_TIER,
}

# 从可用清单解析档位的参数量关键词（只是「匹配规则」，不是硬编码模型名）。
FAST_MODEL_HINTS = ("1b", "3b", "7b", "9b")
STRONG_MODEL_HINTS = ("27b", "32b", "70b")

# 模型名里的尺寸 token，如 "qwen3.5:9b" -> {"9b"}，"qwen2.5:70b" -> {"70b"}。
_SIZE_TOKEN_RE = re.compile(r"(\d+b)")


def _size_tokens(name: str) -> set[str]:
    return {tok.lower() for tok in _SIZE_TOKEN_RE.findall(name.lower())}


class ModelChoice:
    """一次模型解析结果：档位、模型名、可读原因。"""

    __slots__ = ("tier", "model", "reason")

    def __init__(self, tier: str, model: Optional[str], reason: str) -> None:
        self.tier = tier
        self.model = model
        self.reason = reason

    def __repr__(self) -> str:
        return f"ModelChoice(tier={self.tier!r}, model={self.model!r}, reason={self.reason!r})"


def escalation_event(from_tier: str, to_tier: str, reason: str) -> dict:
    """构造模型升级可见事件；code 必须是冻结词表里的 ``MODEL_ESCALATED``。"""
    if "MODEL_ESCALATED" not in ERROR_CODES:
        # 防御：词表变更时必须同步 tests/test_spec027_runtime_contract.py。
        raise RuntimeError("MODEL_ESCALATED missing from contracts.ERROR_CODES")
    return {
        "type": "model",
        "code": "MODEL_ESCALATED",
        "from_tier": from_tier,
        "to_tier": to_tier,
        "reason": reason,
    }


class ModelRouter:
    """按角色与档位从可用模型清单解析实际模型，并实现 fast->重试->升级 strong 分支。"""

    def __init__(self, *, available_models_provider: Optional[Callable[[], List[str]]] = None,
                 fallback_model: Optional[str] = None, observation_service=None,
                 observation=None, policy_version: str = "spec027-static-v1") -> None:
        # available_models_provider 默认 backend.app.platform.ollama.get_available_models
        # （Spec027 复用接缝：禁止第二套模型客户端，模型清单只能来自这里）。
        self._provider = available_models_provider or get_available_models
        self._fallback_model = fallback_model
        # Optional Task03 seam.  It is strictly write-only observation and is
        # never consulted when choosing the production model.
        self._observation = observation_service or observation
        self._policy_version = policy_version

    def _available_models(self) -> List[str]:
        """取可用模型清单；任何异常都降级为空列表，不向上冒泡。"""
        try:
            models = self._provider()
            return list(models) if models else []
        except Exception:
            return []

    def _pick_model(self, tier: str, models: List[str]) -> Tuple[Optional[str], str]:
        """按 tier 在可用清单里找第一个尺寸 token 命中任一 hint 的模型。"""
        hints = STRONG_MODEL_HINTS if tier == STRONG_TIER else FAST_MODEL_HINTS
        for model in models:
            tokens = _size_tokens(model)
            matched = [h for h in hints if h in tokens]
            if matched:
                return model, f"{tier} tier resolved to {model!r} via hint {matched[0]!r}"
        # 找不到 hint 命中：回退 fallback_model 或清单第一个。
        if self._fallback_model:
            return self._fallback_model, (
                f"{tier} tier: no hint match, using fallback_model {self._fallback_model!r}"
            )
        if models:
            return models[0], f"{tier} tier: no hint match, using first available model {models[0]!r}"
        return None, f"{tier} tier: no available models to resolve from"

    def resolve(self, *, role: str, task_type: Optional[str] = None,
                tier: Optional[str] = None, owner_id: Optional[str] = None,
                features: Optional[dict] = None) -> ModelChoice:
        if role not in ROLE_WHITELIST:
            raise ValueError(f"role {role!r} not in ROLE_WHITELIST")
        effective_tier = tier or DEFAULT_TIER_BY_ROLE.get(role, FAST_TIER)
        models = self._available_models()
        model, reason = self._pick_model(effective_tier, models)
        choice = ModelChoice(effective_tier, model, reason)
        observer = self._observation
        if observer is not None and owner_id and hasattr(observer, "record_decision"):
            # Observation failure is intentionally isolated from the routing
            # contract.  candidate_models is a bounded provider allowlist,
            # not a new source of model selection.
            try:
                candidates = list(models[:16])
                if model and model not in candidates:
                    candidates = (candidates + [model])[:16]
                observer.record_decision(
                    owner_id=owner_id,
                    task_type=task_type or role,
                    features={"role": role, "tier": effective_tier, **(features or {})},
                    candidate_models=candidates,
                    chosen_model=model or "unresolved",
                    reason=reason,
                    policy_version=self._policy_version,
                )
            except Exception:
                pass
        return choice

    def execute(self, *, role: str, task_type: Optional[str] = None,
                invoke: Callable[[Optional[str]], Tuple[bool, object]]
                ) -> Tuple[ModelChoice, object, List[dict]]:
        """按 Spec027 与 Task02 FakeModelRouter 同构的出口分支执行模型调用。

        ``invoke`` 签名：``invoke(model_name: str | None) -> (bool, object)``；第一返回值
        表示输出是否合法 / 置信度是否可接受。
        """
        choice = self.resolve(role=role, task_type=task_type)

        if choice.tier == STRONG_TIER:
            ok, value = invoke(choice.model)
            return choice, value, []

        # FAST_TIER：第一次尝试。
        ok, value = invoke(choice.model)
        if ok:
            return choice, value, []

        # fast 失败 -> 重试一次同样的 fast 模型。
        ok, value = invoke(choice.model)
        if ok:
            return choice, value, []

        # 仍失败 -> 升级 strong，发出可见 model_escalated 事件（与 Task02 门禁同构）。
        strong_choice = self.resolve(role=role, task_type=task_type, tier=STRONG_TIER)
        ok, value = invoke(strong_choice.model)
        event = escalation_event(
            from_tier=FAST_TIER,
            to_tier=STRONG_TIER,
            reason="fast output invalid after one retry",
        )
        return strong_choice, value, [event]
