"""Spec031 Task03: redacted routing observation and shadow replay.

This module deliberately sits beside the production router.  It records the
small, bounded decision contract and can replay a *candidate* policy, but it
never returns a model to the production execution path.  All persistence is
best effort at the observability seam; callers may continue when the store or
Langfuse is unavailable.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

MAX_FEATURES = 32
MAX_CANDIDATE_MODELS = 16
MAX_TEXT = 256
MAX_JSON = 8192
SERVER_MIN_SAMPLES = 1
SERVER_MIN_QUALITY_SCORE = 0.8
SERVER_MIN_SCHEMA_VALID_RATE = 1.0
_SENSITIVE_WORDS = (
    "prompt", "answer", "response", "completion", "thought", "reasoning",
    "chain", "credential", "password", "secret", "token", "authorization",
    "cookie", "api_key", "access_key",
)
_SENSITIVE_VALUE_RE = re.compile(
    r"(?:https?://|ftp://|www\.)"
    r"|\b(?:prompt|answer|response|completion|thought|reasoning|chain(?:\s+of\s+thought)?|"
    r"credential|password|secret|token|authorization|cookie|api[_ -]?key|access[_ -]?key|private[_ -]?key)\b"
    r"|\b(?:bearer\s+|sk-|ghp_|xox[baprs]-|eyJ)[A-Za-z0-9._~+/=-]{8,}",
    re.IGNORECASE,
)


def _contains_sensitive_value(text: str) -> bool:
    """Detect sensitive content across JSON/key-value and joined-word forms.

    ``\\b`` treats underscore as a word character, so a raw regex alone would
    miss values such as ``PRIVATE_RESPONSE`` or ``chain_of_thought``.  Check
    both the original text (for credential/token prefixes) and a normalized
    copy where underscore/hyphen joins become spaces.
    """
    normalized = re.sub(r"[_-]+", " ", text)
    return bool(_SENSITIVE_VALUE_RE.search(text) or _SENSITIVE_VALUE_RE.search(normalized))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _bounded_text(value: Any, *, name: str, limit: int = MAX_TEXT) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit:
        raise ValueError(f"{name} is empty or exceeds {limit} characters")
    lowered = name.casefold()
    if any(word in lowered for word in _SENSITIVE_WORDS) or _contains_sensitive_value(text):
        raise ValueError(f"{name} is not allowed in routing observation")
    return text


def _validate_routing_decision(decision: Any, *, idempotency_key: str | None = None) -> None:
    """Validate an already-created decision before any persistence boundary.

    The application service validates inputs before constructing the dataclass,
    but the store is also a public seam and can be called directly.  Rechecking
    here prevents a hand-built dataclass from bypassing the value-level guard.
    Error messages name only the rejected field, never its value.
    """
    _bounded_text(decision.decision_id, name="decision_id", limit=160)
    _bounded_text(decision.owner_id, name="owner_id", limit=160)
    _bounded_text(decision.task_type, name="task_type")
    _safe_features(decision.features)
    _safe_models(decision.candidate_models)
    _bounded_text(decision.chosen_model, name="chosen_model", limit=128)
    _bounded_text(decision.reason, name="reason")
    _bounded_text(decision.policy_version, name="policy_version", limit=80)
    _bounded_text(decision.created_at or _now(), name="created_at", limit=64)
    if idempotency_key:
        _bounded_text(idempotency_key, name="idempotency_key", limit=160)


def _safe_policy_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a bounded policy payload with value-level redaction checks."""
    if not isinstance(payload, Mapping):
        raise ValueError("routing policy must be a mapping")
    status = payload.get("status")
    if status not in {"draft", "shadow", "retired"}:
        raise ValueError("Task03 cannot activate a policy")
    raw_rules = payload.get("rules", [])
    if not isinstance(raw_rules, (list, tuple)) or len(raw_rules) > MAX_FEATURES:
        raise ValueError("policy rules must be a bounded list")
    safe_rules: list[dict[str, Any]] = []
    for rule in raw_rules:
        if not isinstance(rule, Mapping) or len(rule) > MAX_FEATURES:
            raise ValueError("policy rules must be bounded mappings")
        cleaned: dict[str, Any] = {}
        for raw_key, value in rule.items():
            key = str(raw_key).strip()
            if not key or len(key) > 64 or any(word in key.casefold() for word in _SENSITIVE_WORDS) or "url" in key.casefold():
                raise ValueError("policy rule contains a forbidden key")
            if key == "features":
                if not isinstance(value, Mapping):
                    raise ValueError("policy rule features must be a mapping")
                cleaned[key] = _safe_features(value)
            elif key in {"task_type", "model", "reason"}:
                cleaned[key] = _bounded_text(value, name=f"policy_{key}", limit=128)
            else:
                cleaned[key] = _safe_scalar(value, name=f"policy_{key}")
        safe_rules.append(cleaned)
    thresholds = payload.get("thresholds")
    safe_thresholds = _safe_features(thresholds if isinstance(thresholds, Mapping) else {})
    return {
        "version": _bounded_text(payload.get("version"), name="policy_version", limit=80),
        "profile": _bounded_text(payload.get("profile"), name="profile", limit=80),
        "rules": safe_rules,
        "thresholds": safe_thresholds,
        "status": status,
        "created_at": _bounded_text(payload.get("created_at") or _now(), name="created_at", limit=64),
    }


def _safe_scalar(value: Any, *, name: str) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, str):
        return _bounded_text(value, name=name)
    raise ValueError(f"{name} must be a bounded scalar value")


def _safe_features(features: Mapping[str, Any] | None) -> dict[str, Any]:
    if features is None:
        return {}
    if not isinstance(features, Mapping) or len(features) > MAX_FEATURES:
        raise ValueError("features must be a bounded mapping")
    safe: dict[str, Any] = {}
    for raw_key, raw_value in features.items():
        key = str(raw_key).strip()
        if not key or len(key) > 64 or any(word in key.casefold() for word in _SENSITIVE_WORDS):
            raise ValueError("features contain a forbidden key")
        if isinstance(raw_value, bool):
            value = raw_value
        elif isinstance(raw_value, int) and not isinstance(raw_value, bool):
            value = raw_value
        elif isinstance(raw_value, float) and math.isfinite(raw_value):
            value = raw_value
        elif isinstance(raw_value, str) and len(raw_value) <= MAX_TEXT:
            value = _bounded_text(raw_value, name=f"feature_{key}")
        else:
            raise ValueError("features values must be bounded scalar values")
        safe[key] = value
    return safe


def _safe_models(models: Sequence[str]) -> list[str]:
    if not isinstance(models, (list, tuple)) or len(models) > MAX_CANDIDATE_MODELS:
        raise ValueError("candidate_models must be a bounded list")
    result: list[str] = []
    for model in models:
        name = _bounded_text(model, name="model", limit=128)
        if name not in result:
            result.append(name)
    return result


def _json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded) > MAX_JSON:
        raise ValueError("routing observation payload is too large")
    return encoded


@dataclass(frozen=True)
class RoutingDecision:
    decision_id: str
    owner_id: str
    task_type: str
    features: dict[str, Any]
    candidate_models: list[str]
    chosen_model: str
    reason: str
    policy_version: str
    created_at: str = ""

    def public(self) -> dict[str, Any]:
        """Return exactly the redacted decision contract (no owner/idempotency)."""
        return {
            "task_type": self.task_type,
            "features": dict(self.features),
            "candidate_models": list(self.candidate_models),
            "chosen_model": self.chosen_model,
            "reason": self.reason,
            "policy_version": self.policy_version,
        }

    to_dict = public


@dataclass(frozen=True)
class ModelOutcome:
    decision_id: str
    schema_valid: bool | None = None
    quality_score: float | None = None
    ttft: float | None = None
    duration: float | None = None
    tokens: int | None = None
    error_code: str | None = None
    created_at: str = ""

    def public(self) -> dict[str, Any]:
        return {
            "schema_valid": self.schema_valid,
            "quality_score": self.quality_score,
            "ttft": self.ttft,
            "duration": self.duration,
            "tokens": self.tokens,
            "error_code": self.error_code,
        }

    to_dict = public


@dataclass(frozen=True)
class ResourceObservation:
    snapshot_id: str
    owner_id: str
    available_memory: int | None
    loaded_models: list[str]
    estimated_kv: int | None
    active_workers: int | None
    captured_at: str
    probe_error: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "available_memory": self.available_memory,
            "loaded_models": list(self.loaded_models),
            "estimated_kv": self.estimated_kv,
            "active_workers": self.active_workers,
            "captured_at": self.captured_at,
            "probe_error": self.probe_error,
        }

    to_dict = public


@dataclass(frozen=True)
class ShadowReplay:
    decision_id: str
    original_chosen_model: str
    shadow_model: str | None
    policy_version: str
    reason: str

    def public(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "chosen_model": self.original_chosen_model,
            "shadow_model": self.shadow_model,
            "policy_version": self.policy_version,
            "reason": self.reason,
        }


class PolicyActivationError(ValueError):
    """A policy failed one of Task04's explicit activation gates."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _validate_outcome(value: Any, *, field: str) -> Any:
    if value is None:
        return None
    if field == "schema_valid":
        if not isinstance(value, bool):
            raise ValueError("schema_valid must be boolean")
        return value
    if field == "tokens":
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("tokens must be a non-negative integer")
        return value
    if field == "error_code":
        return _bounded_text(value, name="error_code", limit=80)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) < 0:
        raise ValueError(f"{field} must be a non-negative finite number")
    return float(value)


class RoutingObservationService:
    """Persistence and replay facade for Task03.

    ``store`` is intentionally duck-typed so tests can use a small fake.  A
    store failure is swallowed by ``try_*`` helpers and never changes routing.
    """

    def __init__(self, store, *, observability=None):
        self.store = store
        self._observability = observability

    @staticmethod
    def _effective_gate_thresholds(
        policy: Mapping[str, Any], *, min_samples: int = SERVER_MIN_SAMPLES,
        min_quality_score: float = SERVER_MIN_QUALITY_SCORE,
        min_schema_valid_rate: float = SERVER_MIN_SCHEMA_VALID_RATE,
    ) -> tuple[int, float, float]:
        """Return server/policy floors; caller values can only raise them."""
        thresholds = policy.get("thresholds") if isinstance(policy, Mapping) else {}
        thresholds = thresholds if isinstance(thresholds, Mapping) else {}
        try:
            policy_samples = int(thresholds.get("min_samples", SERVER_MIN_SAMPLES))
        except (TypeError, ValueError):
            policy_samples = SERVER_MIN_SAMPLES
        try:
            policy_quality = float(thresholds.get("min_quality_score", SERVER_MIN_QUALITY_SCORE))
        except (TypeError, ValueError):
            policy_quality = SERVER_MIN_QUALITY_SCORE
        try:
            policy_schema = float(thresholds.get("min_schema_valid_rate", SERVER_MIN_SCHEMA_VALID_RATE))
        except (TypeError, ValueError):
            policy_schema = SERVER_MIN_SCHEMA_VALID_RATE
        return (
            max(SERVER_MIN_SAMPLES, policy_samples, int(min_samples)),
            max(SERVER_MIN_QUALITY_SCORE, policy_quality, float(min_quality_score)),
            max(SERVER_MIN_SCHEMA_VALID_RATE, policy_schema, float(min_schema_valid_rate)),
        )

    def record_decision(
        self,
        *,
        owner_id: str,
        task_type: str,
        features: Mapping[str, Any] | None,
        candidate_models: Sequence[str],
        chosen_model: str,
        reason: str,
        policy_version: str,
        decision_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> RoutingDecision | None:
        decision = RoutingDecision(
            decision_id=_bounded_text(decision_id or f"routing-decision:{uuid.uuid4().hex}", name="decision_id", limit=160),
            owner_id=_bounded_text(owner_id, name="owner_id", limit=160),
            task_type=_bounded_text(task_type, name="task_type"),
            features=_safe_features(features),
            candidate_models=_safe_models(candidate_models),
            chosen_model=_bounded_text(chosen_model, name="chosen_model", limit=128),
            reason=_bounded_text(reason, name="reason"),
            policy_version=_bounded_text(policy_version, name="policy_version", limit=80),
            created_at=_now(),
        )
        if decision.chosen_model not in decision.candidate_models and decision.candidate_models:
            raise ValueError("chosen_model must be present in candidate_models")
        safe_idempotency_key = None
        if idempotency_key:
            safe_idempotency_key = _bounded_text(idempotency_key, name="idempotency_key", limit=160)
        try:
            saved = self.store.save_routing_decision(decision, idempotency_key=safe_idempotency_key)
        except Exception:
            return None
        # Reuse the existing Langfuse seam as a second, independent best-effort
        # sink.  Import lazily so the research application remains importable
        # when observability dependencies are absent or disabled.
        if self._observability is not None:
            try:
                self._observability(**decision.public())
            except Exception:
                pass
        return saved

    def record_outcome(
        self,
        *,
        owner_id: str,
        decision_id: str,
        schema_valid: bool | None = None,
        quality_score: float | None = None,
        ttft: float | None = None,
        duration: float | None = None,
        tokens: int | None = None,
        error_code: str | None = None,
    ) -> ModelOutcome | None:
        _bounded_text(owner_id, name="owner_id", limit=160)
        outcome = ModelOutcome(
            decision_id=_bounded_text(decision_id, name="decision_id", limit=160),
            schema_valid=_validate_outcome(schema_valid, field="schema_valid"),
            quality_score=_validate_outcome(quality_score, field="quality_score"),
            ttft=_validate_outcome(ttft, field="ttft"),
            duration=_validate_outcome(duration, field="duration"),
            tokens=_validate_outcome(tokens, field="tokens"),
            error_code=_validate_outcome(error_code, field="error_code"),
            created_at=_now(),
        )
        try:
            return self.store.save_model_outcome(outcome, owner_id=owner_id)
        except Exception:
            return None

    def capture_resource_snapshot(
        self,
        *,
        owner_id: str,
        probe: Any,
        active_workers: int | None = None,
        snapshot_id: str | None = None,
    ) -> ResourceObservation | None:
        captured_at = _now()
        safe_owner_id = _bounded_text(owner_id, name="owner_id", limit=160)
        try:
            raw = probe.snapshot()
            available = getattr(raw, "available_memory_bytes", None)
            footprint = getattr(raw, "model_footprint_bytes", None)
            count = getattr(raw, "loaded_model_count", None)
            if isinstance(raw, Mapping):
                available = raw.get("available_memory", raw.get("available_memory_bytes"))
                footprint = raw.get("estimated_kv", raw.get("model_footprint_bytes"))
                count = raw.get("active_workers", raw.get("loaded_model_count"))
            if available is None or int(available) <= 0 or footprint is None or int(footprint) <= 0:
                raise RuntimeError("RESOURCE_PROBE_FAILED")
            loaded_models = [f"loaded:{max(0, int(count or 0))}"] if count else []
            observation = ResourceObservation(
                snapshot_id=snapshot_id or f"resource-snapshot:{uuid.uuid4().hex}",
                owner_id=safe_owner_id,
                available_memory=int(available), loaded_models=loaded_models,
                estimated_kv=int(footprint), active_workers=active_workers,
                captured_at=captured_at,
            )
        except Exception as exc:
            observation = ResourceObservation(
                snapshot_id=snapshot_id or f"resource-snapshot:{uuid.uuid4().hex}",
                owner_id=safe_owner_id,
                available_memory=None, loaded_models=[], estimated_kv=None,
                active_workers=active_workers, captured_at=captured_at,
                probe_error="RESOURCE_PROBE_FAILED",
            )
        try:
            return self.store.save_resource_snapshot(observation)
        except Exception:
            return None

    def register_shadow_policy(
        self, *, version: str, profile: str, rules: Sequence[Mapping[str, Any]],
        thresholds: Mapping[str, Any] | None = None, status: str = "shadow",
    ) -> dict[str, Any] | None:
        payload = _safe_policy_payload({
            "version": version, "profile": profile, "rules": list(rules),
            "thresholds": thresholds, "status": status, "created_at": _now(),
        })
        try:
            return self.store.save_routing_policy(payload)
        except Exception:
            return None

    def issue_activation_evidence(
        self,
        *,
        version: str,
        probe: Any,
        min_samples: int = 1,
        min_quality_score: float = 0.0,
        min_schema_valid_rate: float = 1.0,
    ) -> dict[str, Any]:
        """Create server-owned evidence bound to outcomes and a probe snapshot.

        Callers receive only an opaque evidence id.  The activation API never
        trusts caller-supplied booleans or measurement mappings.
        """
        policy = self.store.get_routing_policy(version)
        if not policy or policy.get("status") not in {"draft", "shadow"}:
            raise PolicyActivationError("POLICY_STATUS_INVALID")
        required_samples, required_quality, required_schema = self._effective_gate_thresholds(
            policy,
            min_samples=min_samples,
            min_quality_score=min_quality_score,
            min_schema_valid_rate=min_schema_valid_rate,
        )
        summary = self.store.routing_quality_summary(version)
        if (
            summary["samples"] < required_samples
            or summary["quality_score"] < required_quality
            or summary["schema_valid_rate"] < required_schema
        ):
            raise PolicyActivationError("QUALITY_GATE_FAILED")
        snapshot = self.capture_resource_snapshot(owner_id="routing-gate", probe=probe)
        if snapshot is None or snapshot.probe_error or snapshot.available_memory is None or snapshot.estimated_kv is None:
            raise PolicyActivationError("RESOURCE_GATE_FAILED")
        try:
            available = int(snapshot.available_memory)
            footprint = int(snapshot.estimated_kv)
            workers = max(1, int((available * 0.8) // footprint))
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            raise PolicyActivationError("RESOURCE_GATE_FAILED") from exc
        evidence = {
            "evidence_id": f"routing-gate:{uuid.uuid4().hex}",
            "policy_version": version,
            "quality_samples": summary["samples"],
            "quality_score": summary["quality_score"],
            "schema_valid_rate": summary["schema_valid_rate"],
            "resource_snapshot_id": snapshot.snapshot_id,
            "resource_workers": workers,
            "created_at": _now(),
        }
        try:
            return self.store.save_routing_gate_evidence(evidence)
        except Exception as exc:
            raise PolicyActivationError("GATE_EVIDENCE_UNAVAILABLE") from exc

    def activate_policy(
        self,
        *,
        version: str,
        manual_confirmation: bool = False,
        quality_gate: Any = None,
        resource_gate: Any = None,
        gate_evidence: str | Mapping[str, Any] | None = None,
        evidence_id: str | None = None,
        confirm: bool | None = None,
        quality_ok: bool | None = None,
        resource_ok: bool | None = None,
        expected_status: str | None = None,
    ) -> dict[str, Any]:
        """Activate a draft/shadow policy only after all explicit gates pass.

        The store owns the final atomic status transition.  This method never
        changes a policy status on a failed gate and never turns a Task03
        shadow replay into a production choice implicitly.
        """
        if confirm is not None:
            manual_confirmation = bool(confirm)
        if not manual_confirmation:
            raise PolicyActivationError("MANUAL_CONFIRMATION_REQUIRED")
        # Legacy boolean/mapping gate arguments are deliberately rejected;
        # only an opaque server-issued evidence handle is authoritative.
        if evidence_id is None and isinstance(gate_evidence, str):
            evidence_id = gate_evidence
        elif evidence_id is None and isinstance(gate_evidence, Mapping):
            evidence_id = gate_evidence.get("evidence_id")
        if not evidence_id or quality_ok is not None or resource_ok is not None:
            raise PolicyActivationError("GATE_EVIDENCE_REQUIRED")
        policy = self.store.get_routing_policy(version)
        if not policy:
            raise PolicyActivationError("POLICY_NOT_FOUND")
        if policy.get("status") not in {"draft", "shadow"}:
            raise PolicyActivationError("POLICY_STATUS_INVALID")
        evidence = self.store.get_routing_gate_evidence(str(evidence_id))
        if evidence is None or evidence.get("policy_version") != version:
            raise PolicyActivationError("GATE_EVIDENCE_INVALID")
        required_samples, required_quality, required_schema = self._effective_gate_thresholds(policy)
        if (
            int(evidence.get("quality_samples", 0)) < required_samples
            or float(evidence.get("quality_score", 0.0)) < required_quality
            or float(evidence.get("schema_valid_rate", 0.0)) < required_schema
        ):
            raise PolicyActivationError("QUALITY_GATE_FAILED")
        if (
            int(evidence.get("resource_workers", 0)) < 1
            or not evidence.get("resource_snapshot_id")
            or evidence.get("probe_error")
            or int(evidence.get("available_memory", 0) or 0) <= 0
            or int(evidence.get("estimated_kv", 0) or 0) <= 0
        ):
            raise PolicyActivationError("RESOURCE_GATE_FAILED")
        try:
            return self.store.activate_routing_policy(version, expected_status=expected_status)
        except Exception as exc:
            raise PolicyActivationError("POLICY_ACTIVATION_CONFLICT") from exc

    def replay_shadow(self, *, owner_id: str, policy_version: str, limit: int = 100) -> list[dict[str, Any]]:
        policy = self.store.get_routing_policy(policy_version)
        if not policy:
            return []
        decisions = self.store.list_routing_decisions(owner_id=owner_id, limit=max(1, min(int(limit), 500)))
        results: list[dict[str, Any]] = []
        for decision in decisions:
            selected: str | None = None
            for rule in policy.get("rules", []):
                if not isinstance(rule, Mapping):
                    continue
                if rule.get("task_type") and rule.get("task_type") != decision.task_type:
                    continue
                required = rule.get("features", {})
                if isinstance(required, Mapping) and any(decision.features.get(k) != v for k, v in required.items()):
                    continue
                model = rule.get("model")
                if isinstance(model, str) and model in decision.candidate_models:
                    selected = model
                    break
            if selected is None:
                selected = decision.candidate_models[0] if decision.candidate_models else None
            results.append(ShadowReplay(decision.decision_id, decision.chosen_model, selected, policy_version, "shadow-only candidate; production choice unchanged").public())
        return results

    # Explicitly best-effort aliases used at integration seams.
    try_record_decision = record_decision
    try_record_outcome = record_outcome
    record_model_outcome = record_outcome
    record_result = record_outcome
    replay_policy = replay_shadow


RoutingPolicy = dict
ResourceSnapshot = ResourceObservation

__all__ = ["RoutingDecision", "ModelOutcome", "ResourceObservation", "ResourceSnapshot", "RoutingPolicy", "ShadowReplay", "PolicyActivationError", "RoutingObservationService", "_bounded_text", "_safe_features", "_safe_models", "_safe_scalar", "_safe_policy_payload", "_validate_routing_decision"]
