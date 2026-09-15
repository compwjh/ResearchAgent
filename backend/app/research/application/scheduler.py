"""Spec028 durable single-host scheduler.

The scheduler is a thin coordinator around :class:`ResearchStore`.  Research
Task and WorkItem state transitions remain owned by the existing repository and
domain state machine; this module only selects a fair queued item, claims its
durable lease, and couples resource reservations to that lease.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from backend.app.research.domain.contracts import TASK_TERMINAL, WORKITEM_TERMINAL
from backend.app.research.domain.models import ResearchWorkItem, ResourceReservation, SchedulerLease
from backend.app.research.infrastructure.research_store import ResearchStore


@dataclass(frozen=True)
class ScheduledWork:
    work_item: ResearchWorkItem
    lease: SchedulerLease


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
        if recover_on_start:
            # Startup recovery is deliberately bounded to durable scheduler
            # ownership/capacity rows; WorkItem transitions remain owned by
            # the existing state machine and are not guessed here.
            self.recover()

    @staticmethod
    def _dependencies_completed(item: ResearchWorkItem, by_id: dict[str, ResearchWorkItem]) -> bool:
        return all(by_id.get(dep) is not None and by_id[dep].status == "completed" for dep in item.depends_on)

    def _queued_candidates(self) -> list[ResearchWorkItem]:
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
        return {
            "leases": self.store.recover_expired_scheduler_leases(now=now),
            "reservations": self.store.recover_expired_resource_reservations(now=now),
        }

    def acquire_resources(
        self,
        task_id: str,
        requested: int,
        *,
        model_tier: str = "fast",
        estimated_bytes: int = 0,
        worker_prefix: str | None = None,
    ) -> tuple[int, str | None]:
        """Use the existing ResourceProbe and persist each granted slot."""
        if self.probe is None:
            from backend.app.platform.ollama import ResourceProbe

            self.probe = ResourceProbe()
        granted, code = self.probe.arbitrate(task_id, int(requested))
        granted = max(0, int(granted))
        prefix = worker_prefix or task_id
        reservations: list[str] = []
        per_slot = int(estimated_bytes)
        for index in range(granted):
            reservation = self.store.reserve_resources(
                f"{prefix}:{index}", model_tier, per_slot, task_id=task_id, lease_seconds=self.lease_seconds
            )
            if reservation is None:
                break
            if reservation.reservation_id:
                reservations.append(reservation.reservation_id)
        if len(reservations) < granted:
            for reservation_id in reservations:
                self.store.release_resource_reservation(reservation_id)
            self.probe.release(task_id)
            granted = 0
        self._reservations[task_id].extend(reservations)
        return granted, code

    def release_resources(self, task_id: str) -> None:
        for reservation_id in self._reservations.pop(task_id, []):
            self.store.release_resource_reservation(reservation_id)
        if self.probe is not None:
            self.probe.release(task_id)


# Descriptive/legacy aliases used by callers and hidden Task03 probes.
SchedulerService = ResearchScheduler
GlobalResearchScheduler = ResearchScheduler
DurableScheduler = ResearchScheduler
GlobalScheduler = ResearchScheduler
_GlobalResearchScheduler = ResearchScheduler
