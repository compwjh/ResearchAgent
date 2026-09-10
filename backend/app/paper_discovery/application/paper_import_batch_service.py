"""Orchestration for durable, isolated paper-import batches.

The batch store owns all durable state and compare-and-set transitions.  This
module deliberately owns only orchestration: validating a server-side search
snapshot, claiming an item, invoking the single-paper importer, and recording
the resulting state.  In particular, a login failure is an item-level result,
never a reason to stop processing the other items in the batch.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import secrets
import sqlite3
import time
import uuid
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

from backend.app.paper_discovery.application.entry import (
    BROWSER_SESSION_EXPIRED,
    BROWSER_SESSION_REQUIRED,
)
from backend.app.paper_discovery.application.paper_import import (
    LOGIN_REQUIRED,
    import_candidate,
    safe_import_error_code,
    safe_import_error_message,
)
from backend.app.paper_discovery.domain.paper_discovery_normalization import normalize_title
from backend.app.paper_discovery.domain.paper_import_batch import (
    ITEM_COMPLETED,
    ITEM_DOWNLOADING,
    ITEM_INDEXING,
    ITEM_QUEUED,
    ITEM_VALIDATING,
    ITEM_WAITING_LOGIN,
    PaperImportBatch,
    PaperImportItem,
)
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.paper_discovery.infrastructure.paper_import_batch_store import (
    BATCH_NOT_FOUND,
    DATABASE_LOCKED,
    INVALID_STATE_TRANSITION,
    SNAPSHOT_REBUILD_REQUIRED,
    PaperImportBatchStore,
    PaperImportBatchStoreError,
)

IMPORT_FAILED = "IMPORT_FAILED"
INVALID_SEARCH_SNAPSHOT = "INVALID_SEARCH_SNAPSHOT"
SEARCH_NOT_FOUND = "SEARCH_NOT_FOUND"
SEARCH_EXPIRED = "SEARCH_EXPIRED"
CANDIDATE_NOT_FOUND = "CANDIDATE_NOT_FOUND"
COMPENSATION_PENDING = "COMPENSATION_PENDING"
BATCH_NOT_FOUND_ERROR = BATCH_NOT_FOUND
CLAIM_WAIT_TIMEOUT_SECONDS = 2.0
CLAIM_WAIT_INTERVAL_SECONDS = 0.01


class PaperImportBatchServiceError(ValueError):
    """Stable service-level error suitable for an API error body."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.error_code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)


def _value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _call_supported(function: Callable[..., Any], positional: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Keep injected test doubles convenient without weakening the normal API."""
    try:
        parameters = inspect.signature(function).parameters.values()
    except (TypeError, ValueError):
        return function(*positional, **kwargs)
    accepts_kwargs = any(item.kind == inspect.Parameter.VAR_KEYWORD for item in parameters)
    accepted = kwargs if accepts_kwargs else {key: value for key, value in kwargs.items() if key in inspect.signature(function).parameters}
    positional_parameters = [
        item for item in parameters
        if item.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return function(*positional[: len(positional_parameters)], **accepted)


def _candidate_ids(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate_id = _value(value, "candidate_id", value if isinstance(value, str) else None)
        if not candidate_id:
            raise PaperImportBatchServiceError(INVALID_SEARCH_SNAPSHOT, "候选快照缺少 candidate_id")
        candidate_id = str(candidate_id)
        if candidate_id not in seen:
            seen.add(candidate_id)
            result.append(candidate_id)
    return result


class PaperImportBatchService:
    """Create and execute durable paper-import batches."""

    def __init__(
        self,
        store: Optional[PaperImportBatchStore] = None,
        discovery_store: Optional[PaperDiscoveryStore] = None,
        *,
        importer: Callable[..., Any] = import_candidate,
        settings: Any = None,
        allowed_hosts: Iterable[str] = (),
        allowed_hosts_resolver: Optional[Callable[[Any], Iterable[str]]] = None,
        conference_short_name_resolver: Optional[Callable[[Any], Optional[str]]] = None,
        max_workers: int = 3,
        lease_seconds: int = 15 * 60,
        compensator: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.store = store or PaperImportBatchStore()
        self.discovery_store = discovery_store
        self.importer = importer
        self.settings = settings
        self.allowed_hosts = tuple(allowed_hosts)
        self.allowed_hosts_resolver = allowed_hosts_resolver
        self.conference_short_name_resolver = conference_short_name_resolver
        self.max_workers = max(1, min(int(max_workers), 3))
        self.lease_seconds = int(lease_seconds)
        self.compensator = compensator
        # Candidate snapshots are intentionally process-local.  A restarted
        # worker must be given the server snapshot again; it cannot reconstruct
        # an import from client-provided IDs or URLs.
        self._snapshots: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _store_call(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Retry transient SQLite writer contention between item workers."""
        for attempt in range(8):
            try:
                return function(*args, **kwargs)
            except PaperImportBatchStoreError as error:
                if error.code != DATABASE_LOCKED:
                    raise
                if attempt == 7:
                    raise PaperImportBatchServiceError(
                        DATABASE_LOCKED, str(error), retryable=True,
                    ) from error
                time.sleep(0.01 * (attempt + 1))
            except sqlite3.OperationalError as error:
                if "locked" not in str(error).lower():
                    raise
                if attempt == 7:
                    raise PaperImportBatchServiceError(
                        DATABASE_LOCKED, "批次状态库正忙，请稍后重试", retryable=True,
                    ) from error
                time.sleep(0.01 * (attempt + 1))
        raise AssertionError("unreachable")

    def _server_snapshot(
        self,
        search_id: str,
        search_session: Any = None,
        candidates: Optional[Iterable[Any]] = None,
    ) -> tuple[Any, dict[str, Any]]:
        session = search_session
        if session is None and self.discovery_store is not None:
            session = self.discovery_store.get_search_session(search_id)
        if session is None:
            raise PaperImportBatchServiceError(SEARCH_NOT_FOUND, "搜索会话不存在")
        if str(_value(session, "search_id")) != str(search_id):
            raise PaperImportBatchServiceError(INVALID_SEARCH_SNAPSHOT, "搜索会话与候选快照不匹配")
        expires_at = _parse_time(_value(session, "expires_at"))
        if expires_at is None:
            raise PaperImportBatchServiceError(INVALID_SEARCH_SNAPSHOT, "搜索会话过期时间无效")
        if expires_at <= _utcnow():
            raise PaperImportBatchServiceError(SEARCH_EXPIRED, "搜索会话已过期")

        values = list(candidates or [])
        if not values and self.discovery_store is not None:
            values = list(self.discovery_store.get_candidates(search_id))
        snapshots: dict[str, Any] = {}
        for candidate in values:
            candidate_id = _value(candidate, "candidate_id")
            candidate_search = _value(candidate, "search_id")
            if not candidate_id or str(candidate_search) != str(search_id):
                raise PaperImportBatchServiceError(INVALID_SEARCH_SNAPSHOT, "候选快照不属于当前搜索会话")
            if str(candidate_id) in snapshots:
                raise PaperImportBatchServiceError(INVALID_SEARCH_SNAPSHOT, "候选快照包含重复 candidate_id")
            snapshots[str(candidate_id)] = candidate
        if not snapshots:
            raise PaperImportBatchServiceError(CANDIDATE_NOT_FOUND, "未提供候选快照")
        return session, snapshots

    def create_batch(
        self,
        search_id: Any,
        candidate_ids: Iterable[Any] = (),
        *,
        search_session: Any = None,
        candidates: Optional[Iterable[Any]] = None,
        idempotency_key: Optional[str] = None,
        auto_run: bool = False,
    ) -> PaperImportBatch:
        """Validate server snapshots and persist a queued batch.

        ``candidate_ids`` may be IDs or candidate objects.  If objects are
        supplied they are also the server-side snapshots used for execution;
        otherwise ``candidates`` must contain those snapshots (or the injected
        discovery store is queried).
        """
        # Accept ``create_batch(session, candidates)`` as a convenience for
        # route adapters while retaining the explicit search_id form.
        if not isinstance(search_id, str):
            if search_session is not None:
                raise PaperImportBatchServiceError(INVALID_SEARCH_SNAPSHOT, "重复提供搜索会话")
            search_session = search_id
            search_id = _value(search_session, "search_id")
        candidate_values = list(candidates) if candidates is not None else None
        requested = list(candidate_ids)
        if not requested and candidate_values is not None:
            requested = candidate_values
        requested_ids = _candidate_ids(requested)
        snapshot_values = list(candidate_values or [])
        if not snapshot_values and requested and not all(isinstance(value, str) for value in requested):
            snapshot_values = requested
        _, snapshots = self._server_snapshot(search_id, search_session, snapshot_values)
        missing = [candidate_id for candidate_id in requested_ids if candidate_id not in snapshots]
        if missing:
            raise PaperImportBatchServiceError(CANDIDATE_NOT_FOUND, "候选快照不存在")
        item_snapshots = [snapshots[candidate_id] for candidate_id in requested_ids]
        persistable_items = [self._persistable_snapshot(item) for item in item_snapshots]
        search_expires_at = _value(search_session, "expires_at")
        if search_expires_at is None and self.discovery_store is not None:
            search_expires_at = _value(self.discovery_store.get_search_session(search_id), "expires_at")
        try:
            batch = self.store.create_batch(
                search_id, persistable_items, idempotency_key=idempotency_key,
                search_expires_at=search_expires_at,
            )
        except PaperImportBatchStoreError as error:
            raise PaperImportBatchServiceError(error.code, str(error)) from error
        self._snapshots[batch.batch_id] = {str(_value(item, "candidate_id")): item for item in item_snapshots}
        if auto_run:
            self.run_batch(batch.batch_id)
            batch = self.store.get_batch(batch.batch_id) or batch
        return batch

    @staticmethod
    def _snapshot_json(candidate: Any) -> str:
        if isinstance(candidate, Mapping):
            snapshot = dict(candidate)
        elif hasattr(candidate, "model_dump"):
            snapshot = dict(candidate.model_dump())
        else:
            snapshot = dict(getattr(candidate, "__dict__", {}) or {})
        snapshot.setdefault("candidate_id", _value(candidate, "candidate_id"))
        snapshot.setdefault("search_id", _value(candidate, "search_id"))
        snapshot["normalized_title"] = _value(candidate, "normalized_title") or normalize_title(_value(candidate, "title"))
        return json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

    @staticmethod
    def _persistable_snapshot(candidate: Any) -> dict[str, Any]:
        """Copy only server metadata needed by the durable item identity.

        Search results created by older callers may not have populated
        ``normalized_title`` yet.  Deriving it here prevents a blank value
        from collapsing otherwise distinct title identities in the store;
        execution still uses the original server snapshot held in memory.
        """
        fields = {
            name: _value(candidate, name)
            for name in ("candidate_id", "doi", "dblp_key", "year", "conference_id", "idempotency_key", "stored_name")
        }
        fields["normalized_title"] = _value(candidate, "normalized_title") or normalize_title(_value(candidate, "title"))
        # JSON is the durable server snapshot; default=str keeps legacy
        # dataclass/enums serializable without accepting client URLs later.
        encoded = PaperImportBatchService._snapshot_json(candidate)
        fields["snapshot_json"] = encoded
        fields["snapshot_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        return fields

    def _snapshots_for(self, batch_id: str, candidates: Optional[Iterable[Any]]) -> dict[str, Any]:
        batch = self.store.get_batch(batch_id)
        if batch is None:
            raise PaperImportBatchServiceError(BATCH_NOT_FOUND_ERROR, "导入批次不存在")
        # Retry/resume must not revive an item from an expired search.  Keep
        # this check in the service as well as the HTTP route so direct callers
        # and background workers observe the same boundary.
        if self.discovery_store is not None:
            session = self.discovery_store.get_search_session(batch.search_id)
            if session is not None:
                expires_at = _parse_time(_value(session, "expires_at"))
                if expires_at is None or expires_at <= _utcnow():
                    raise PaperImportBatchServiceError(SEARCH_EXPIRED, "搜索会话已过期")
        stored_expires = _parse_time(getattr(batch, "search_expires_at", None))
        if stored_expires is None:
            raise PaperImportBatchServiceError(SNAPSHOT_REBUILD_REQUIRED, "批次搜索快照过期时间缺失")
        if stored_expires <= _utcnow():
            raise PaperImportBatchServiceError(SEARCH_EXPIRED, "搜索会话已过期")
        items = self.store.get_items(batch_id)
        if candidates is None:
            # The in-process copy is only an execution convenience.  Every
            # item is still required to have a valid durable snapshot below;
            # a restarted worker therefore takes the SQLite branch.
            local = self._snapshots.get(batch_id, {})
            snapshots = {}
            for item in items:
                try:
                    snapshot = self.store.get_snapshot(item.item_id)
                except PaperImportBatchStoreError as error:
                    if error.code == SNAPSHOT_REBUILD_REQUIRED:
                        raise PaperImportBatchServiceError(SNAPSHOT_REBUILD_REQUIRED, str(error)) from error
                    raise
                if snapshot is not None:
                    local_candidate = local.get(item.candidate_id)
                    if local_candidate is not None:
                        try:
                            local_encoded = self._snapshot_json(local_candidate)
                            local_digest = hashlib.sha256(local_encoded.encode("utf-8")).hexdigest()
                        except (TypeError, ValueError):
                            local_digest = None
                        # A same-process object is only a convenience cache;
                        # the durable, hash-verified SQLite snapshot wins if
                        # it was mutated or cannot be serialized.
                        snapshots[item.candidate_id] = (
                            local_candidate if local_digest == item.snapshot_hash else snapshot
                        )
                    else:
                        snapshots[item.candidate_id] = snapshot
            if len(snapshots) != len(items):
                raise PaperImportBatchServiceError(SNAPSHOT_REBUILD_REQUIRED, "批次候选快照需要重建")
            return snapshots
        values = list(candidates)
        if self.discovery_store is not None:
            _, supplied = self._server_snapshot(batch.search_id, None, values)
        else:
            supplied = {}
            for value in values:
                candidate_id = _value(value, "candidate_id")
                candidate_search = _value(value, "search_id")
                if not candidate_id or str(candidate_search) != str(batch.search_id):
                    raise PaperImportBatchServiceError(INVALID_SEARCH_SNAPSHOT, "候选快照不属于当前搜索会话")
                if str(candidate_id) in supplied:
                    raise PaperImportBatchServiceError(INVALID_SEARCH_SNAPSHOT, "候选快照包含重复 candidate_id")
                supplied[str(candidate_id)] = value
        snapshots = {}
        for item in items:
            value = supplied.get(item.candidate_id)
            if value is None:
                raise PaperImportBatchServiceError(CANDIDATE_NOT_FOUND, "批次缺少服务端候选快照")
            persisted = self.store.get_snapshot(item.item_id)
            if persisted is None:
                raise PaperImportBatchServiceError(SNAPSHOT_REBUILD_REQUIRED, "批次候选快照需要重建")
            encoded = self._snapshot_json(value)
            if hashlib.sha256(encoded.encode("utf-8")).hexdigest() != item.snapshot_hash:
                raise PaperImportBatchServiceError(INVALID_SEARCH_SNAPSHOT, "候选快照与持久化版本不一致")
            snapshots[item.candidate_id] = value
        return snapshots

    def _import_one(
        self,
        item: PaperImportItem,
        candidate: Any,
        owner: str,
        *,
        attempt_owner: Optional[str] = None,
        attempt_token: Optional[str] = None,
        downloader: Optional[Callable[..., Any]] = None,
        context: Any = None,
    ) -> PaperImportItem:
        try:
            hosts = self.allowed_hosts_resolver(candidate) if self.allowed_hosts_resolver else self.allowed_hosts
            short_name = self.conference_short_name_resolver(candidate) if self.conference_short_name_resolver else None
            importer_kwargs = {"conference_short_name": short_name} if short_name else {}
            # The capability credential is generated by the durable claim and
            # must be forwarded unchanged to the single-paper importer.  The
            # supported-call shim intentionally drops these kwargs for legacy
            # test doubles that have not adopted the extended contract.
            if attempt_owner is not None:
                importer_kwargs["attempt_owner"] = attempt_owner
            if attempt_token is not None:
                importer_kwargs["attempt_token"] = attempt_token
            if downloader is not None:
                importer_kwargs["downloader"] = downloader
            if context is not None:
                importer_kwargs["context"] = context
            result = _call_supported(
                self.importer,
                (candidate, self.settings, hosts),
                importer_kwargs,
            )
        except Exception as error:
            code = str(getattr(error, "code", getattr(error, "error_code", "")) or "")
            if code == LOGIN_REQUIRED:
                try:
                    self._store_call(self.store.transition_item,
                        item.item_id, ITEM_WAITING_LOGIN, expected_state=ITEM_DOWNLOADING,
                        lease_owner=owner, error_code=LOGIN_REQUIRED,
                        error_message=safe_import_error_message(LOGIN_REQUIRED),
                    )
                except PaperImportBatchStoreError as store_error:
                    if store_error.code != INVALID_STATE_TRANSITION:
                        raise
            else:
                self._mark_failed(
                    item.item_id, error, owner=owner,
                    capability=getattr(error, "resource_capability", None),
                    cleanup_status=getattr(error, "cleanup_status", None),
                )
            return self.store.get_item(item.item_id) or item

        status = str(_value(result, "status", ""))
        result_error = _value(result, "error_code")
        if status in {"waiting_login", LOGIN_REQUIRED} or result_error == LOGIN_REQUIRED:
            try:
                self._store_call(self.store.transition_item,
                    item.item_id, ITEM_WAITING_LOGIN, expected_state=ITEM_DOWNLOADING,
                    lease_owner=owner, error_code=LOGIN_REQUIRED,
                    error_message=safe_import_error_message(LOGIN_REQUIRED),
                )
            except PaperImportBatchStoreError as store_error:
                if store_error.code != INVALID_STATE_TRANSITION:
                    raise
            return self.store.get_item(item.item_id) or item
        if status not in {"indexed", "completed"} and not bool(_value(result, "existing", False)):
            self._mark_failed(
                item.item_id, result_error or IMPORT_FAILED, _value(result, "message"), owner=owner,
                capability=_value(result, "resource_capability"),
                cleanup_status=_value(result, "cleanup_status"),
            )
            return self.store.get_item(item.item_id) or item

        paper_id = _value(result, "paper_id")
        stored_name = _value(result, "stored_name")
        capability = _value(result, "resource_capability")
        if capability is not None:
            self._store_call(
                self.store.record_attempt_resource, item.item_id, capability,
                lease_owner=owner, cleanup_status=_value(result, "cleanup_status"),
            )
        try:
            self._store_call(self.store.transition_item, item.item_id, ITEM_VALIDATING, expected_state=ITEM_DOWNLOADING, lease_owner=owner)
            self._store_call(self.store.transition_item, item.item_id, ITEM_INDEXING, expected_state=ITEM_VALIDATING, lease_owner=owner)
            self._store_call(self.store.transition_item,
                item.item_id, ITEM_COMPLETED, expected_state=ITEM_INDEXING,
                lease_owner=owner, paper_id=paper_id, stored_name=stored_name,
            )
        except PaperImportBatchStoreError as error:
            if error.code == INVALID_STATE_TRANSITION:
                return self.store.get_item(item.item_id) or item
            raise
        return self.store.get_item(item.item_id) or item

    def _mark_failed(
        self, item_id: str, error: Any, message: Optional[str] = None, *, owner: str,
        capability: Any = None, cleanup_status: Optional[str] = None,
    ) -> None:
        code = str(error if isinstance(error, str) else getattr(error, "code", getattr(error, "error_code", "")) or IMPORT_FAILED)
        if code == LOGIN_REQUIRED:
            code = IMPORT_FAILED
        code = safe_import_error_code(code, IMPORT_FAILED)
        # Never persist importer/transport exception text.  The code is the
        # only durable error detail and maps to a fixed safe message.
        safe_message = safe_import_error_message(code, message)
        try:
            if capability is not None:
                self._store_call(
                    self.store.record_attempt_resource, item_id, capability,
                    lease_owner=owner, cleanup_status=cleanup_status or "cleanup_pending",
                )
            self._store_call(self.store.mark_failed, item_id, code, safe_message, lease_owner=owner)
        except PaperImportBatchStoreError as store_error:
            # Another worker may have completed or claimed the item.  The CAS
            # store is authoritative, so a loser must not overwrite its state.
            if store_error.code != INVALID_STATE_TRANSITION:
                raise

    def _compensate_item(self, item: PaperImportItem) -> bool:
        """Drive a persisted capability without confusing it with lease_owner."""
        capability = item.resource_capability
        if not capability or item.cleanup_status in {None, "completed"}:
            return True
        owner = str(capability.get("owner") or "")
        token = str(capability.get("token") or "")
        if not owner or not token or owner != item.attempt_owner or token != item.attempt_token:
            raise PaperImportBatchServiceError("COMPENSATION_DENIED", "补偿能力不匹配")
        if self.compensator is None:
            return False
        try:
            result = _call_supported(self.compensator, (capability,), {})
        except Exception:
            return False
        if result not in {True, "completed", "already_completed"}:
            return False
        try:
            self._store_call(self.store.complete_compensation, item.item_id, capability)
        except PaperImportBatchStoreError as error:
            raise PaperImportBatchServiceError(error.code, str(error)) from error
        return True

    def _wait_for_claim_winner(self, item_id: str, fallback: PaperImportItem) -> PaperImportItem:
        """Observe a competing worker's CAS result without running the importer.

        A losing process/resume call should normally return the winner's final
        state, not a transient ``downloading`` snapshot.  The wait is read-only
        and bounded so a crashed worker cannot make the caller hang forever.
        """
        deadline = time.monotonic() + CLAIM_WAIT_TIMEOUT_SECONDS
        while True:
            current = self.store.get_item(item_id)
            if current is None:
                return fallback
            if current.status not in {ITEM_DOWNLOADING, ITEM_VALIDATING, ITEM_INDEXING}:
                return current
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return current
            time.sleep(min(CLAIM_WAIT_INTERVAL_SECONDS, remaining))

    def process_item(self, item_id: str, *, candidates: Optional[Iterable[Any]] = None, lease_owner: Optional[str] = None) -> PaperImportItem:
        item = self.store.get_item(item_id)
        if item is None:
            raise PaperImportBatchServiceError("ITEM_NOT_FOUND", "导入条目不存在")
        snapshots = self._snapshots_for(item.batch_id, candidates)
        owner = lease_owner or uuid.uuid4().hex
        attempt_owner = f"paper-import:{uuid.uuid4().hex}"
        attempt_token = secrets.token_urlsafe(32)
        try:
            self._store_call(
                self.store.claim_item, item.item_id, owner,
                lease_seconds=self.lease_seconds,
                attempt_owner=attempt_owner,
                attempt_token=attempt_token,
            )
        except PaperImportBatchStoreError as error:
            if error.code != INVALID_STATE_TRANSITION:
                raise PaperImportBatchServiceError(error.code, str(error)) from error
            return self._wait_for_claim_winner(item.item_id, item)
        claimed = self.store.get_item(item.item_id) or item
        return self._import_one(
            claimed, snapshots[item.candidate_id], owner,
            attempt_owner=claimed.attempt_owner or attempt_owner,
            attempt_token=claimed.attempt_token or attempt_token,
        )

    def run_batch(self, batch_id: str, *, candidates: Optional[Iterable[Any]] = None) -> PaperImportBatch:
        """Process queued items concurrently; a login item never blocks peers."""
        batch = self.store.get_batch(batch_id)
        if batch is None:
            raise PaperImportBatchServiceError(BATCH_NOT_FOUND_ERROR, "导入批次不存在")
        snapshots = self._snapshots_for(batch_id, candidates)
        items = [item for item in self.store.get_items(batch_id) if item.status == ITEM_QUEUED]
        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(items)))) as executor:
            futures = [executor.submit(self.process_item, item.item_id, candidates=list(snapshots.values())) for item in items]
            for future in as_completed(futures):
                future.result()
        return self.store.get_batch(batch_id) or batch

    process_batch = run_batch
    execute_batch = run_batch
    start_batch = run_batch

    def retry_batch(self, batch_id: str, *, candidates: Optional[Iterable[Any]] = None) -> PaperImportBatch:
        current = self.store.get_batch(batch_id)
        if current is None:
            raise PaperImportBatchServiceError(BATCH_NOT_FOUND_ERROR, "导入批次不存在")
        for item in self.store.get_items(batch_id):
            if (
                item.status in {"failed", "cancelled"}
                and item.cleanup_status not in {None, "completed"}
                and not self._compensate_item(item)
            ):
                return current
        try:
            self._store_call(self.store.retry_batch, batch_id)
        except PaperImportBatchStoreError as error:
            raise PaperImportBatchServiceError(error.code, str(error)) from error
        return self.run_batch(batch_id, candidates=candidates)

    def retry_item(self, item_id: str, *, candidates: Optional[Iterable[Any]] = None) -> PaperImportItem:
        current = self.store.get_item(item_id)
        if current is None:
            raise PaperImportBatchServiceError("ITEM_NOT_FOUND", "导入条目不存在")
        if current.cleanup_status not in {None, "completed"} and not self._compensate_item(current):
            return current
        try:
            self._store_call(self.store.retry_item, item_id)
        except PaperImportBatchStoreError as error:
            raise PaperImportBatchServiceError(error.code, str(error)) from error
        return self.process_item(item_id, candidates=candidates)

    def resume_item(
        self,
        item_id: str,
        *,
        candidates: Optional[Iterable[Any]] = None,
        lease_owner: Optional[str] = None,
        downloader: Optional[Callable[..., Any]] = None,
        context: Any = None,
    ) -> PaperImportItem:
        item = self.store.get_item(item_id)
        if item is None:
            raise PaperImportBatchServiceError("ITEM_NOT_FOUND", "导入条目不存在")
        snapshots = self._snapshots_for(item.batch_id, candidates)
        if item.status == "failed" and item.cleanup_status not in {None, "completed"} and not self._compensate_item(item):
            return item
        owner = lease_owner or uuid.uuid4().hex
        attempt_owner = f"paper-import:{uuid.uuid4().hex}"
        attempt_token = secrets.token_urlsafe(32)
        try:
            self._store_call(
                self.store.resume_item, item_id, owner,
                lease_seconds=self.lease_seconds,
                attempt_owner=attempt_owner,
                attempt_token=attempt_token,
            )
        except PaperImportBatchStoreError as error:
            if error.code != INVALID_STATE_TRANSITION:
                raise PaperImportBatchServiceError(error.code, str(error)) from error
            return self._wait_for_claim_winner(item_id, item)
        resumed = self.store.get_item(item_id) or item
        return self._import_one(
            resumed, snapshots[resumed.candidate_id], owner,
            attempt_owner=resumed.attempt_owner or attempt_owner,
            attempt_token=resumed.attempt_token or attempt_token,
            downloader=downloader, context=context,
        )

    def cancel_batch(self, batch_id: str) -> PaperImportBatch:
        try:
            self._store_call(self.store.cancel_batch, batch_id)
        except PaperImportBatchStoreError as error:
            raise PaperImportBatchServiceError(error.code, str(error)) from error
        for item in self.store.get_items(batch_id):
            if item.cleanup_status not in {None, "completed"}:
                self._compensate_item(item)
        return self.store.get_batch(batch_id)  # type: ignore[return-value]

    cancel = cancel_batch

    def cancel_item(self, item_id: str) -> PaperImportItem:
        try:
            self._store_call(self.store.cancel_item, item_id)
        except PaperImportBatchStoreError as error:
            raise PaperImportBatchServiceError(error.code, str(error)) from error
        item = self.store.get_item(item_id)
        if item is None:
            raise PaperImportBatchServiceError("ITEM_NOT_FOUND", "导入条目不存在")
        if item.cleanup_status not in {None, "completed"}:
            self._compensate_item(item)
            item = self.store.get_item(item_id) or item
        return item

    def recover_expired_leases(self, *, now: Any = None) -> int:
        expired = self.store.list_expired_items(now=now)
        count = self.store.recover_expired_leases(now=now)
        for item in expired:
            current = self.store.get_item(item.item_id)
            if current is not None and current.cleanup_status not in {None, "completed"}:
                self._compensate_item(current)
        return count

    recover_expired = recover_expired_leases

    def get_status(self, batch_id: str) -> dict[str, Any]:
        batch = self.store.get_batch(batch_id)
        if batch is None:
            raise PaperImportBatchServiceError(BATCH_NOT_FOUND_ERROR, "导入批次不存在")
        return {"batch": batch.to_dict(), "items": [item.to_dict() for item in self.store.get_items(batch_id)]}

    status = get_status


__all__ = [
    "IMPORT_FAILED", "INVALID_SEARCH_SNAPSHOT", "SEARCH_NOT_FOUND", "SEARCH_EXPIRED",
    "CANDIDATE_NOT_FOUND", "COMPENSATION_PENDING", "SNAPSHOT_REBUILD_REQUIRED",
    "BROWSER_SESSION_EXPIRED", "BROWSER_SESSION_REQUIRED",
    "PaperImportBatchService", "PaperImportBatchServiceError",
]
