"""Small Task04 routing-control API; no frontend coupling."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from backend.app.memory.repository import OWNER_ID
from backend.app.platform.ollama import (
    ResourceProbe,
    ResourceProbeUnavailable,
    get_available_models,
    read_loaded_models,
)
from backend.app.research.application.entry import build_research_store
from backend.app.research.application.routing_observation import (
    PolicyActivationError,
    RoutingObservationService,
)
from backend.app.research.application.entry import decode_cursor

router = APIRouter(prefix="/research-routing", tags=["research-routing"])


class RoutingPolicyActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manual_confirmation: bool = False
    # Only the server-issued opaque evidence handle can satisfy the gates.
    evidence_id: str | None = None
    # Kept solely to return a stable rejection for stale clients; never
    # forwarded as evidence.
    quality_gate: Any = None
    resource_gate: Any = None
    expected_status: str | None = None


class RoutingPolicyEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_samples: int = 1
    min_quality_score: float = 0.0
    min_schema_valid_rate: float = 1.0


@router.post("/policies/{version}/evidence")
def issue_routing_policy_evidence(version: str, payload: RoutingPolicyEvidenceRequest):
    """Generate a server-owned gate handle from stored outcomes and probe data."""
    try:
        service = RoutingObservationService(build_research_store())
        return service.issue_activation_evidence(
            version=version,
            probe=ResourceProbe(),
            min_samples=payload.min_samples,
            min_quality_score=payload.min_quality_score,
            min_schema_valid_rate=payload.min_schema_valid_rate,
        )
    except PolicyActivationError as exc:
        return JSONResponse(status_code=409, content={"error": {"code": exc.code}})
    except Exception:
        return JSONResponse(status_code=503, content={"error": {"code": "SOURCE_UNAVAILABLE"}})


@router.post("/policies/{version}/activate")
def activate_routing_policy(version: str, payload: RoutingPolicyActivationRequest):
    """Activate only a previously persisted draft/shadow policy.

    The application service enforces all three explicit gates and the store
    performs the final status change atomically.  Errors expose stable codes,
    never raw database/provider details.
    """
    if payload.quality_gate is not None or payload.resource_gate is not None:
        return JSONResponse(status_code=409, content={"error": {"code": "GATE_EVIDENCE_REQUIRED"}})
    try:
        service = RoutingObservationService(build_research_store())
        return service.activate_policy(
            version=version,
            manual_confirmation=payload.manual_confirmation,
            evidence_id=payload.evidence_id,
            expected_status=payload.expected_status,
        )
    except PolicyActivationError as exc:
        return JSONResponse(status_code=409, content={"error": {"code": exc.code}})
    except Exception:
        return JSONResponse(status_code=503, content={"error": {"code": "SOURCE_UNAVAILABLE"}})


def _policy_to_status(policy: dict | None) -> dict | None:
    """Project a stored routing policy down to the read-only status contract."""
    if not policy:
        return None
    return {
        "version": policy.get("version"),
        "profile": policy.get("profile"),
        "rules": policy.get("rules"),
        "thresholds": policy.get("thresholds"),
        "status": policy.get("status"),
    }


@router.get("/status")
def routing_status():
    """Return the active policy, model health, and a resource summary.

    Probe unavailability degrades to HTTP 503, but the body still carries the
    degraded state (``degraded: true`` plus whatever status we could read) so
    callers can tell "probe is broken" apart from "service is broken".

    Never includes host paths, lease tokens, prompts, responses, or reasoning.
    """
    store = build_research_store()
    try:
        active_policy = _policy_to_status(store.get_active_routing_policy())
    except Exception:
        # Observation never blocks the status read; degrade the policy field.
        active_policy = None
    probe = ResourceProbe()
    try:
        snapshot = probe.snapshot()
        max_workers, _probe_code = probe.max_safe_workers()
    except ResourceProbeUnavailable:
        return JSONResponse(
            status_code=503,
            content={
                "error": {"code": "RESOURCE_PROBE_FAILED"},
                "degraded": True,
                "active_policy": active_policy,
                "model_health": None,
                "resource": None,
            },
        )
    except Exception:
        return JSONResponse(
            status_code=503,
            content={
                "error": {"code": "RESOURCE_PROBE_FAILED"},
                "degraded": True,
                "active_policy": active_policy,
                "model_health": None,
                "resource": None,
            },
        )
    resource = {
        "available_memory_bytes": snapshot.available_memory_bytes,
        "model_footprint_bytes": snapshot.model_footprint_bytes,
        "loaded_model_count": snapshot.loaded_model_count,
        "max_safe_workers": max_workers,
    }
    try:
        available_models = get_available_models()
        loaded_models = read_loaded_models()
        model_health = {
            "available_models": len(available_models),
            "loaded_models": len(loaded_models),
            "healthy": True,
        }
    except Exception:
        model_health = None
    return {
        "active_policy": active_policy,
        "model_health": model_health,
        "resource": resource,
    }


@router.get("/decisions")
def list_routing_decisions(
    owner: str | None = Query(None, description="Isolation owner; defaults to the single global OWNER_ID."),
    task: str | None = Query(None, description="Exact task_type filter (optional)."),
    filter_text: str | None = Query(None, alias="filter", description="Case-insensitive substring over task_type/chosen_model/reason. Empty string is rejected."),
    cursor: str | None = Query(None, description="Opaque keyset cursor from a previous next_cursor; malformed -> 400."),
    limit: str | None = Query("20", description="Page size; default 20, hard cap 100; out of range -> 400."),
):
    """Return redacted routing decisions for one owner only.

    Owner isolation is enforced at the store layer: only decisions whose
    ``owner_id`` equals the requested ``owner`` are returned, so one owner can
    never read another owner's decisions.  Each item is redacted to the
    contract fields (task_type / features / candidate_models / chosen_model /
    reason / policy_version / created_at); no prompt, response, or reasoning is
    ever serialized.

    Query parameters:
    - ``owner``: isolation dimension (defaults to global OWNER_ID).
    - ``task``: exact ``task_type`` equality filter.
    - ``filter``: case-insensitive substring match across task_type, chosen_model,
      and reason.  A blank/whitespace-only value is rejected with 400.
    - ``cursor``: opaque keyset cursor; an un-decodable value is rejected with 400.
    - ``limit``: page size, clamped to [1, 100]; out of range is rejected with 400.
    """
    effective_owner = owner or OWNER_ID
    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": {"code": "INVALID_LIMIT"}})
    if parsed_limit < 1 or parsed_limit > 100:
        return JSONResponse(status_code=400, content={"error": {"code": "INVALID_LIMIT"}})
    if filter_text is not None and not filter_text.strip():
        return JSONResponse(status_code=400, content={"error": {"code": "INVALID_FILTER"}})
    if cursor is not None:
        try:
            decode_cursor(cursor)
        except ValueError:
            return JSONResponse(status_code=400, content={"error": {"code": "INVALID_CURSOR"}})
    store = build_research_store()
    try:
        decisions, next_cursor = store.list_routing_decisions_paged(
            owner_id=effective_owner,
            task_type=task,
            filter_text=filter_text.strip() if filter_text else None,
            cursor=cursor,
            limit=parsed_limit,
        )
    except ValueError:
        return JSONResponse(status_code=400, content={"error": {"code": "INVALID_CURSOR"}})
    items = [{**decision.public(), "created_at": decision.created_at} for decision in decisions]
    return {
        "owner": effective_owner,
        "decisions": items,
        "next_cursor": next_cursor,
        "limit": parsed_limit,
    }
