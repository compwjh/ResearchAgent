"""Small Task04 routing-control API; no frontend coupling."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from backend.app.platform.ollama import ResourceProbe
from backend.app.research.application.entry import build_research_store
from backend.app.research.application.routing_observation import (
    PolicyActivationError,
    RoutingObservationService,
)

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
