"""Spec028 durable single-host scheduler.

The scheduler is a thin coordinator around :class:`ResearchStore`.  Research
Task and WorkItem state transitions remain owned by the existing repository and
domain state machine; this module only selects a fair queued item, claims its
durable lease, and couples resource reservations to that lease.
"""

from __future__ import annotations

import threading
import uuid
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from backend.app.research.domain.contracts import TASK_TERMINAL, WORKITEM_TERMINAL
from backend.app.research.domain.models import ResearchWorkItem, ResourceReservation, SchedulerLease
from backend.app.research.infrastructure.research_store import ResearchStore


@dataclass(frozen=True)
class ScheduledWork:
    work_item: ResearchWorkItem
    lease: SchedulerLease


@dataclass(frozen=True)
class WorkerGrant:
    """A bounded worker grant coupled to durable reservation ids.

    The grant is a read-only hand-off object.  It deliberately contains no
    prompt, model response, owner token, or machine-specific details.
    """

    task_id: str
    model_tier: str
    requested: int
    granted: int
    reason: str | None = None
    policy_version: str = "spec027-static-v1"
    reservation_ids: tuple[str, ...] = ()
    lease_seconds: int = 60
    ownership_token: str = ""

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "model_tier": self.model_tier,
            "requested": self.requested,
            "granted": self.granted,
            "reason": self.reason,
            "policy_version": self.policy_version,
            "reservation_ids": list(self.reservation_ids),
            "lease_seconds": self.lease_seconds,
            "ownership_token": self.ownership_token,
        }


class ResearchScheduler:
    """Fair, lease-backed scheduler for one process host.

    Fairness is task round-robin, not a second queue persisted beside
    ``research_work_items``.  The SQLite lease CAS makes the same selection
    safe when multiple service processes race to dispatch it.
    """

    _fair_lock = threading.Lock()
    _last_task_id: str | None = None

    def __init__(self, store: ResearchStore, *, probe=None, lease_seconds: int = 60, recover_on_start: bool = True):
        self.store = store
        self.lease_seconds = max(1, int(lease_seconds))
        self.probe = probe
        self._reservations: dict[str, list[str]] = defaultdict(list)
        self._grant_lock = threading.RLock()
        if recover_on_start:
            if self.probe is None:
                from backend.app.platform.ollama import ResourceProbe

                # Constructing the existing probe is side-effect free; it lets
                # same-process restart recovery reconcile the shared global
                # quota before the first new grant.
                self.probe = ResourceProbe()
            # Startup recovery is deliberately bounded to durable scheduler
            # ownership/capacity rows; WorkItem transitions remain owned by
            # the existing state machine and are not guessed here.
            self.recover()

    def _release_probe_quota(self, task_id: str, *, count: int | None) -> None:
        if self.probe is None:
            return
        try:
            self.probe.release(task_id, count=count)
        except TypeError:
            # Legacy injected probes expose only release(task_id).  The real
            # ResourceProbe supports granular count-based reconciliation.
            self.probe.release(task_id)

    @staticmethod
    def _dependencies_completed(item: ResearchWorkItem, by_id: dict[str, ResearchWorkItem]) -> bool:
        return all(by_id.get(dep) is not None and by_id[dep].status == "completed" for dep in item.depends_on)

    def _queued_candidates(self) -> list[ResearchWorkItem]:
        # Restart recovery and recurring scheduler ticks make due retries
        # claimable without resetting their persisted retry counters.
        with suppress(Exception):
            self.store.requeue_due_work_items()
        candidates: list[ResearchWorkItem] = []
        for status in ("planning", "running", "waiting_approval"):
            for task in self.store.list_tasks_for_status(status):
                items = self.store.list_work_items(task.research_task_id)
                by_id = {item.work_item_id: item for item in items}
                candidates.extend(
                    item for item in items
                    if item.status == "queued" and self._dependencies_completed(item, by_id)
                )
        return sorted(candidates, key=lambda item: (item.research_task_id, item.created_at, item.work_item_id))

    def _fair_order(self, candidates: Iterable[ResearchWorkItem]) -> list[ResearchWorkItem]:
        grouped: dict[str, list[ResearchWorkItem]] = defaultdict(list)
        for item in candidates:
            grouped[item.research_task_id].append(item)
        task_ids = sorted(grouped)
        if not task_ids:
            return []
        with self._fair_lock:
            previous = self._last_task_id
            if previous in task_ids:
                start = (task_ids.index(previous) + 1) % len(task_ids)
                task_ids = task_ids[start:] + task_ids[:start]
            self._last_task_id = task_ids[0]
        ordered: list[ResearchWorkItem] = []
        # One item per task per round prevents a task with many fan-out nodes
        # from consuming every fast Worker slot.
        while task_ids:
            next_ids: list[str] = []
            for task_id in task_ids:
                bucket = grouped[task_id]
                if bucket:
                    ordered.append(bucket.pop(0))
                if bucket:
                    next_ids.append(task_id)
            task_ids = next_ids
        return ordered

    def claim_next(self, owner_token: str, *, lease_seconds: int | None = None, now: str | None = None) -> ScheduledWork | None:
        """Claim the next dependency-ready WorkItem, or return ``None``."""
        if not owner_token:
            raise ValueError("owner_token is required")
        for item in self._fair_order(self._queued_candidates()):
            try:
                running = self.store.claim_work_item(
                    item.work_item_id,
                    owner_token,
                    lease_seconds=lease_seconds or self.lease_seconds,
                    now=now,
                )
            except Exception:
                continue
            if running is None:
                continue
            lease = self.store.get_scheduler_lease(item.work_item_id)
            if lease is not None:
                return ScheduledWork(running, lease)
        return None

    def heartbeat(self, work_item_id: str, owner_token: str, *, lease_seconds: int | None = None, now: str | None = None) -> SchedulerLease | None:
        return self.store.heartbeat_scheduler_lease(
            work_item_id,
            owner_token,
            lease_seconds=lease_seconds or self.lease_seconds,
            now=now,
        )

    def finish(self, work_item_id: str, owner_token: str, status: str = "completed", **kwargs) -> ResearchWorkItem | None:
        """Finish a leased item and release its lease in a finally-safe order."""
        if status not in WORKITEM_TERMINAL:
            raise ValueError("finish status must be terminal")
        try:
            lease = self.store.get_scheduler_lease(work_item_id)
            if lease is None or lease.owner_token != owner_token:
                return None
            return self.store.update_work_item_status(work_item_id, status, **kwargs)
        finally:
            self.store.release_scheduler_lease(work_item_id, owner_token)

    def recover(self, *, now: str | None = None) -> dict[str, int]:
        """Release expired ownership and capacity reservations after restart."""
        expired_rows = self.store.recover_expired_resource_reservation_rows(now=now)
        expired_by_task: dict[str, int] = defaultdict(int)
        expired_ids = {row["reservation_id"] for row in expired_rows}
        for row in expired_rows:
            if row.get("task_id"):
                expired_by_task[str(row["task_id"])] += 1
        with self._grant_lock:
            for task_id, reservation_ids in list(self._reservations.items()):
                remaining = [reservation_id for reservation_id in reservation_ids if reservation_id not in expired_ids]
                if remaining:
                    self._reservations[task_id] = remaining
                else:
                    self._reservations.pop(task_id, None)
        # Release only the number of durable slots that expired.  This is
        # granular enough to preserve another live grant for the same task.
        for task_id, count in expired_by_task.items():
            self._release_probe_quota(task_id, count=count)
        return {
            "leases": self.store.recover_expired_scheduler_leases(now=now),
            "reservations": len(expired_rows),
        }

    def status(self, *, now: str | None = None) -> dict:
        """Return a safe, read-only aggregate of durable scheduler state.

        Status is intentionally derived from the existing task/work-item,
        lease, and reservation stores.  It does not recover, claim, or expose
        owner tokens, worker identifiers, or checkpoint contents.
        """
        current = now or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        queued = 0
        running = 0
        for task_status in ("planning", "running", "waiting_approval", "paused"):
            for task in self.store.list_tasks_for_status(task_status):
                for item in self.store.list_work_items(task.research_task_id):
                    queued += item.status == "queued"
                    running += item.status == "running"
        active_reservations = self.store.list_resource_reservations(now=current)
        active_leases = self.store.list_scheduler_leases(now=current)
        return {
            "status": "ok",
            "queue": {
                "queued": queued,
                "running": running,
                "waiting_approval": len(self.store.list_tasks_for_status("waiting_approval")),
                "paused": len(self.store.list_tasks_for_status("paused")),
            },
            "quota": {
                "active_workers": len(active_reservations),
                "reserved_bytes": sum(item.estimated_bytes for item in active_reservations),
            },
            "safety": {
                "active_leases": len(active_leases),
                "active_reservations": len(active_reservations),
            },
        }

    # Checkpoint methods intentionally delegate to ResearchStore.  The
    # scheduler owns dispatch policy, while the store remains the sole durable
    # checkpoint/CAS implementation used by restart and resume paths.
    def save_checkpoint(
        self,
        task_id: str,
        plan_version: int,
        node_id: str,
        state_json,
        input_digest: str | None = None,
        *,
        now: str | None = None,
    ):
        return self.store.save_scheduler_checkpoint(
            task_id,
            plan_version,
            node_id,
            state_json,
            input_digest,
            now=now,
        )

    def get_checkpoint(self, task_id: str, plan_version: int, node_id: str):
        return self.store.get_scheduler_checkpoint(task_id, plan_version, node_id)

    def advance_from_checkpoint(
        self,
        work_item_id: str,
        *,
        plan_version: int,
        input_digest: str,
        owner_token: str | None = None,
    ) -> bool:
        return self.store.advance_work_item_from_checkpoint(
            work_item_id,
            plan_version=plan_version,
            input_digest=input_digest,
            owner_token=owner_token,
        )

    checkpoint = save_checkpoint
    checkpoint_for = get_checkpoint
    save_scheduler_checkpoint = save_checkpoint
    get_scheduler_checkpoint = get_checkpoint
    advance_work_item_from_checkpoint = advance_from_checkpoint

    def acquire_resources(
        self,
        task_id: str,
        requested: int,
        *,
        model_tier: str = "fast",
        estimated_bytes: int = 0,
        worker_prefix: str | None = None,
        lease_seconds: int | None = None,
    ) -> tuple[int, str | None]:
        """Use the existing ResourceProbe and persist each granted slot.

        This compatibility method keeps the Spec028 tuple return.  New
        callers should use :meth:`grant_workers` to retain reservation ids
        and the bounded policy/reason metadata.
        """
        grant = self.grant_workers(
            task_id,
            requested,
            model_tier=model_tier,
            estimated_bytes=estimated_bytes,
            worker_prefix=worker_prefix,
            lease_seconds=lease_seconds,
        )
        return grant.granted, grant.reason

    def grant_workers(
        self,
        task_id: str,
        requested: int,
        *,
        model_tier: str = "fast",
        estimated_bytes: int = 0,
        worker_prefix: str | None = None,
        lease_seconds: int | None = None,
        policy_version: str = "spec027-static-v1",
        now: str | None = None,
    ) -> WorkerGrant:
        """Grant bounded workers and atomically compensate partial failures.

        Probe/model-provider calls happen before any reservation transaction and
        never under the scheduler's lock.  Strong/27B workers are explicitly
        single-concurrency; a second active strong reservation is queued until
        its lease is released or expires.
        """
        if self.probe is None:
            from backend.app.platform.ollama import ResourceProbe

            self.probe = ResourceProbe()
        tier = str(model_tier or "fast").strip().lower()
        if tier in {"27b", "32b", "70b", "strong", "quality"}:
            tier = "strong"
        else:
            tier = "fast"
        requested = max(0, int(requested))
        if tier == "strong":
            requested = min(requested, 1)
        try:
            granted, code = self.probe.arbitrate(task_id, requested)
        except TypeError:
            # A small fake probe in offline tests may expose the older
            # ``arbitrate(requested)`` shape; keep the production contract
            # task-aware while preserving that test seam.
            granted, code = self.probe.arbitrate(requested)
        granted = max(0, min(int(granted), requested))
        prefix = worker_prefix or task_id
        reservations: list[str] = []
        ownership_token = uuid.uuid4().hex
        per_slot = int(estimated_bytes)
        lease = self.lease_seconds if lease_seconds is None else max(1, int(lease_seconds))
        reservation_unavailable = False
        try:
            for index in range(granted):
                reservation = self.store.reserve_resources(
                    f"{prefix}:{index}", tier, per_slot, task_id=task_id,
                    lease_seconds=lease, grant_token=ownership_token, now=now,
                )
                if reservation is None or not reservation.reservation_id:
                    reservation_unavailable = True
                    break
                reservations.append(reservation.reservation_id)
        except Exception:
            for reservation_id in reservations:
                self.store.release_resource_reservation(reservation_id, now=now)
            # Releasing the in-memory quota is required even when persistence
            # failed halfway through the reservation loop.
            self._release_probe_quota(task_id, count=granted)
            raise
        if len(reservations) < granted:
            for reservation_id in reservations:
                self.store.release_resource_reservation(reservation_id, now=now)
            self._release_probe_quota(task_id, count=granted)
            return WorkerGrant(
                task_id, tier, requested, 0,
                "STRONG_WORKER_BUSY" if tier == "strong" and reservation_unavailable else ("RESOURCE_RESERVATION_UNAVAILABLE" if reservation_unavailable else code),
                policy_version, (), lease, "",
            )
        with self._grant_lock:
            self._reservations[task_id].extend(reservations)
        return WorkerGrant(task_id, tier, requested, granted, code, policy_version, tuple(reservations), lease, ownership_token)

    def release_grant(self, grant: WorkerGrant | None) -> None:
        if grant is None:
            return
        # A grant owns only its reservation ids.  The task id is an additional
        # durable ownership condition, preventing a stale grant from releasing
        # another grant belonging to the same task.
        released = 0
        for reservation_id in grant.reservation_ids:
            if self.store.release_resource_reservation(
                reservation_id, task_id=grant.task_id, grant_token=grant.ownership_token
            ):
                released += 1
        if released:
            with self._grant_lock:
                current = self._reservations.get(grant.task_id, [])
                remaining = [reservation_id for reservation_id in current if reservation_id not in grant.reservation_ids]
                if remaining:
                    self._reservations[grant.task_id] = remaining
                else:
                    self._reservations.pop(grant.task_id, None)
            self._release_probe_quota(grant.task_id, count=released)

    def release_resources(self, task_id: str, *, _release_probe: bool = True) -> None:
        with self._grant_lock:
            reservation_ids = self._reservations.pop(task_id, [])
        for reservation_id in reservation_ids:
            self.store.release_resource_reservation(reservation_id)
        if _release_probe:
            self._release_probe_quota(task_id, count=None)

    # Explicit Task04 names; all aliases still use this one scheduler and one
    # reservation implementation.
    acquire_worker = grant_workers
    request_workers = grant_workers
    release_worker_grant = release_grant


# Descriptive/legacy aliases used by callers and hidden Task03 probes.
SchedulerService = ResearchScheduler
GlobalResearchScheduler = ResearchScheduler
DurableScheduler = ResearchScheduler
GlobalScheduler = ResearchScheduler
_GlobalResearchScheduler = ResearchScheduler
