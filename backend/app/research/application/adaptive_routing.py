"""Spec031 Task04 adaptive routing facade.

The module composes the existing ``ModelRouter`` and ``ResearchScheduler``;
it does not contain another model client, queue, or resource probe.  Resource
grants are acquired before an external model invocation and released by the
caller in ``finally`` (``execute`` does this automatically).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from backend.app.research.application.routing_observation import PolicyActivationError
from backend.app.research.application.scheduler import ResearchScheduler, WorkerGrant


@dataclass(frozen=True)
class AdaptiveRoute:
    choice: Any
    grant: WorkerGrant

    def to_dict(self) -> dict:
        choice = self.choice
        return {
            "tier": getattr(choice, "tier", None),
            "model": getattr(choice, "model", None),
            "reason": getattr(choice, "reason", ""),
            "worker_grant": self.grant.granted,
            "worker_reason": self.grant.reason,
            "policy_version": self.grant.policy_version,
        }


class AdaptiveRoutingService:
    """Resource-aware composition around the legacy router.

    ``resolve`` calls the legacy router before acquiring a slot, so provider
    discovery is never performed while the scheduler/store critical section is
    held.  If the probe is unavailable, the existing one-worker fallback is
    preserved and the model choice itself is unchanged.
    """

    def __init__(self, router, scheduler: ResearchScheduler, *, observation=None, policy_version: str = "spec027-static-v1"):
        self.router = router
        self.scheduler = scheduler
        self.observation = observation
        self.policy_version = policy_version

    def resolve(
        self,
        *,
        owner_id: str | None,
        task_id: str,
        role: str,
        task_type: str | None = None,
        tier: str | None = None,
        requested_workers: int = 1,
        estimated_bytes: int = 0,
        features: Mapping[str, Any] | None = None,
    ) -> tuple[Any, WorkerGrant]:
        # owner_id is intentionally not passed to the legacy observer: this
        # service writes one complete decision including the grant below.
        try:
            choice = self.router.resolve(
                role=role, task_type=task_type, tier=tier, features=features
            )
        except TypeError:
            # Preserve the tiny legacy FakeModelRouter seam used by Spec027
            # tests, whose resolve method only accepts ``role`` and ``tier``.
            choice = self.router.resolve(role=role, tier=tier)
        model_tier = getattr(choice, "tier", None) or tier or "fast"
        grant = self.scheduler.grant_workers(
            task_id,
            requested_workers,
            model_tier=model_tier,
            estimated_bytes=estimated_bytes,
            policy_version=self.policy_version,
        )
        if self.observation is not None and owner_id and hasattr(self.observation, "record_decision"):
            model = getattr(choice, "model", None) or "unresolved"
            candidates = [model] if model != "unresolved" else []
            safe_features = {
                "role": role,
                "tier": str(model_tier),
                "worker_grant": grant.granted,
                "worker_requested": max(0, int(requested_workers)),
                "resource_reason": grant.reason or "ok",
                **dict(features or {}),
            }
            try:
                self.observation.record_decision(
                    owner_id=owner_id,
                    task_type=task_type or role,
                    features=safe_features,
                    candidate_models=candidates,
                    chosen_model=model,
                    reason=f"{getattr(choice, 'reason', 'router choice')}; worker_grant={grant.granted}; resource={grant.reason or 'ok'}",
                    policy_version=self.policy_version,
                )
            except Exception:
                pass
        return choice, grant

    route = resolve

    def release(self, grant: WorkerGrant | None) -> None:
        self.scheduler.release_grant(grant)

    def execute(
        self,
        *,
        owner_id: str | None,
        task_id: str,
        role: str,
        invoke: Callable[[Any], Any],
        task_type: str | None = None,
        tier: str | None = None,
        requested_workers: int = 1,
        estimated_bytes: int = 0,
        features: Mapping[str, Any] | None = None,
    ) -> tuple[Any, Any, WorkerGrant]:
        """Acquire, invoke outside all scheduler locks, and release safely."""
        choice, grant = self.resolve(
            owner_id=owner_id, task_id=task_id, role=role, task_type=task_type,
            tier=tier, requested_workers=requested_workers,
            estimated_bytes=estimated_bytes, features=features,
        )
        try:
            value = invoke(getattr(choice, "model", None))
            return choice, value, grant
        finally:
            self.release(grant)


# Descriptive aliases make the application seam discoverable without creating
# a second implementation or changing old ModelRouter imports.
AdaptiveWorkerRouter = AdaptiveRoutingService
ResourceAwareRouter = AdaptiveRoutingService
AdaptiveWorkerScheduler = ResearchScheduler

__all__ = [
    "AdaptiveRoute", "AdaptiveRoutingService", "AdaptiveWorkerRouter",
    "ResourceAwareRouter", "AdaptiveWorkerScheduler", "PolicyActivationError",
    "WorkerGrant",
]
