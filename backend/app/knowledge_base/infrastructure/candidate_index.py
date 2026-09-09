"""Explicit destination port for Spec018 candidate collection rebuilds.

The legacy ``index.py`` helpers intentionally target the live ``KB_COLLECTION``
and delete the document before writing.  A rebuild must never call those
helpers: it needs a destination collection and document id on every write, and
must not mutate metadata or the current collection.  This module contains the
small port used by the rebuild service plus an in-memory FakeQdrant for tests.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from qdrant_client import models

from backend.app.platform.config import EMBED_DIM

__all__ = [
    "CandidateIndexError",
    "CandidatePoint",
    "CandidateIndexPort",
    "QdrantCandidateIndexPort",
    "FakeQdrant",
    "FakeCandidateIndexPort",
]


class CandidateIndexError(RuntimeError):
    """Stable, path-free error raised by the candidate port."""

    def __init__(self, message: str, *, code: str = "CANDIDATE_INDEX_FAILED") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CandidatePoint:
    """Portable point representation shared by Qdrant and FakeQdrant."""

    id: str
    vector: Dict[str, Any]
    payload: Dict[str, Any]


class CandidateIndexPort(Protocol):
    """The only index surface the candidate rebuild service may use."""

    def collection_inventory(self) -> Dict[str, Any]: ...

    def ensure_collection(self, destination: str, *, dense_dim: int) -> None: ...

    def delete_collection(self, destination: str) -> None: ...

    def upsert_document(
        self,
        destination: str,
        document_id: str,
        points: Sequence[CandidatePoint],
    ) -> None: ...

    def scroll_points(
        self,
        destination: str,
        *,
        offset: Optional[str] = None,
        limit: int = 256,
    ) -> Tuple[List[CandidatePoint], Optional[str]]: ...

    def count(self, destination: str) -> int: ...

    def search(
        self,
        destination: str,
        vector_name: str,
        vector: Any,
        *,
        limit: int = 1,
    ) -> List[CandidatePoint]: ...

    def create_alias(self, alias: str, destination: str, *, replace: bool = False) -> None: ...

    def delete_alias(self, alias: str) -> None: ...

    def alias_target(self, alias: str) -> Optional[str]: ...

    def bind_candidate(self, candidate: str, *, source_collection: str, alias: str, run_token: str, retire_capability: object) -> None: ...

    def authorize_retire(self, collection: str, *, run_token: str, expected_target: str, capability: object) -> None: ...


def _validate_name(value: str, *, label: str) -> str:
    text = str(value or "")
    if not text or len(text) > 128 or text[0] not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        raise CandidateIndexError("INVALID_CANDIDATE_NAME", code="INVALID_CANDIDATE_NAME")
    if any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in text):
        raise CandidateIndexError("INVALID_CANDIDATE_NAME", code="INVALID_CANDIDATE_NAME")
    return text


def _vector_dimension(vector: Any) -> int:
    if isinstance(vector, models.SparseVector):
        return len(vector.indices)
    if isinstance(vector, dict) and "indices" in vector:
        return len(vector.get("indices") or [])
    try:
        return len(vector)
    except TypeError:
        return 0


def _dot(left: Any, right: Any) -> float:
    if isinstance(left, models.SparseVector):
        left = dict(zip(left.indices, left.values, strict=True))
    if isinstance(right, models.SparseVector):
        right = dict(zip(right.indices, right.values, strict=True))
    if isinstance(left, dict) and isinstance(right, dict):
        return float(sum(float(value) * float(right.get(key, 0.0)) for key, value in left.items()))
    try:
        return float(sum(float(a) * float(b) for a, b in zip(left, right, strict=True)))
    except (TypeError, ValueError):
        return 0.0


class QdrantCandidateIndexPort:
    """Qdrant adapter with explicit destination/document writes.

    The adapter never imports ``KB_COLLECTION`` and never calls legacy delete
    or metadata helpers.  It is intentionally not instantiated by Task02A
    tests; Task06 may provide the real client after its maintenance gate.
    """

    def __init__(self, client: Any, *, dense_dim: int = EMBED_DIM) -> None:
        self.client = client
        self.dense_dim = int(dense_dim)
        self._candidate: Optional[str] = None
        self._source_collection: Optional[str] = None
        self._alias: Optional[str] = None
        self._run_token: Optional[str] = None
        self._retire_capability: Optional[object] = None
        self._retire_allowlist = set()

    def bind_candidate(self, candidate: str, *, source_collection: str, alias: str, run_token: str, retire_capability: object) -> None:
        self._candidate = _validate_name(candidate, label="candidate")
        self._source_collection = _validate_name(source_collection, label="source_collection")
        self._alias = _validate_name(alias, label="alias")
        self._run_token = _validate_name(run_token, label="run_token")
        self._retire_capability = retire_capability
        self._retire_allowlist = set()

    def authorize_retire(self, collection: str, *, run_token: str, expected_target: str, capability: object) -> None:
        collection = _validate_name(collection, label="collection")
        expected_target = _validate_name(expected_target, label="expected_target")
        if (
            self._candidate is None
            or self._run_token is None
            or self._retire_capability is None
            or run_token != self._run_token
            or capability is not self._retire_capability
            or collection != expected_target
            or collection == self._candidate
        ):
            raise CandidateIndexError("RETIRE_TARGET_INVALID", code="RETIRE_TARGET_INVALID")
        self._retire_allowlist.add(collection)

    def _assert_destination(self, destination: str, *, allow_retire: bool = False) -> str:
        destination = _validate_name(destination, label="destination")
        if self._candidate is None:
            raise CandidateIndexError("CANDIDATE_PORT_NOT_BOUND", code="CANDIDATE_PORT_NOT_BOUND")
        if destination != self._candidate and not (allow_retire and destination in self._retire_allowlist):
            raise CandidateIndexError("CANDIDATE_DESTINATION_FORBIDDEN", code="CANDIDATE_DESTINATION_FORBIDDEN")
        return destination

    def _assert_alias(self, alias: str) -> str:
        alias = _validate_name(alias, label="alias")
        if self._alias is not None and alias != self._alias:
            raise CandidateIndexError("CANDIDATE_ALIAS_FORBIDDEN", code="CANDIDATE_ALIAS_FORBIDDEN")
        return alias

    def collection_inventory(self) -> Dict[str, Any]:
        collections = []
        try:
            response = self.client.get_collections()
            raw_collections = getattr(response, "collections", response or ())
            for item in raw_collections:
                name = str(getattr(item, "name", item))
                count = self.count(name)
                vector_names: List[str] = []
                try:
                    info = self.client.get_collection(name)
                    vectors = getattr(getattr(info, "config", None), "params", None)
                    configured = getattr(vectors, "vectors", None)
                    if isinstance(configured, dict):
                        vector_names = sorted(str(key) for key in configured)
                except Exception:
                    vector_names = []
                collections.append({"name": name, "kind": "physical", "exists": True, "point_count": count, "vector_names": vector_names})
        except Exception as error:
            raise CandidateIndexError("QDRANT_INVENTORY_FAILED", code="QDRANT_INVENTORY_FAILED") from error
        aliases = []
        try:
            response = self.client.get_aliases()
            raw_aliases = getattr(response, "aliases", response or ())
            for item in raw_aliases:
                aliases.append({"alias": str(getattr(item, "alias_name", "")), "targets": [str(getattr(item, "collection_name", ""))]})
        except Exception as error:
            raise CandidateIndexError("QDRANT_ALIAS_INVENTORY_FAILED", code="QDRANT_ALIAS_INVENTORY_FAILED") from error
        return {"collections": collections, "aliases": aliases}

    def ensure_collection(self, destination: str, *, dense_dim: int) -> None:
        destination = self._assert_destination(destination)
        if self.client.collection_exists(destination):
            return
        self.client.create_collection(
            collection_name=destination,
            vectors_config={"dense": models.VectorParams(size=int(dense_dim), distance=models.Distance.COSINE)},
            sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )

    def delete_collection(self, destination: str) -> None:
        destination = self._assert_destination(destination, allow_retire=True)
        if self.client.collection_exists(destination):
            self.client.delete_collection(collection_name=destination)

    def upsert_document(self, destination: str, document_id: str, points: Sequence[CandidatePoint]) -> None:
        destination = self._assert_destination(destination)
        document_id = str(document_id)
        if not document_id:
            raise CandidateIndexError("INVALID_DOCUMENT_ID", code="INVALID_DOCUMENT_ID")
        if any(str(point.payload.get("document_id")) != document_id for point in points):
            raise CandidateIndexError("DOCUMENT_ID_PAYLOAD_MISMATCH", code="DOCUMENT_ID_PAYLOAD_MISMATCH")
        self.ensure_collection(destination, dense_dim=self.dense_dim)
        self.client.upsert(
            collection_name=destination,
            points=[models.PointStruct(id=point.id, vector=point.vector, payload=point.payload) for point in points],
        )

    def scroll_points(self, destination: str, *, offset: Optional[str] = None, limit: int = 256) -> Tuple[List[CandidatePoint], Optional[str]]:
        records, next_offset = self.client.scroll(
            collection_name=self._assert_destination(destination),
            offset=offset,
            limit=int(limit),
            with_payload=True,
            with_vectors=True,
        )
        result = [CandidatePoint(str(item.id), dict(item.vector or {}), dict(item.payload or {})) for item in records]
        return result, next_offset

    def count(self, destination: str) -> int:
        destination = _validate_name(destination, label="destination")
        if not self.client.collection_exists(destination):
            return 0
        return int(self.client.count(collection_name=destination).count)

    def search(self, destination: str, vector_name: str, vector: Any, *, limit: int = 1) -> List[CandidatePoint]:
        name = self._assert_destination(destination)
        if hasattr(self.client, "search"):
            response = self.client.search(collection_name=name, query_vector=(vector_name, vector), limit=int(limit), with_payload=True, with_vectors=True)
        else:
            response = self.client.query_points(collection_name=name, query=vector, using=vector_name, limit=int(limit), with_payload=True, with_vectors=True)
            response = getattr(response, "points", response)
        return [CandidatePoint(str(item.id), dict(item.vector or {}), dict(item.payload or {})) for item in response]

    def create_alias(self, alias: str, destination: str, *, replace: bool = False) -> None:
        alias = self._assert_alias(alias)
        destination = self._assert_destination(destination)
        operations: List[Any] = []
        if replace and self.alias_target(alias):
            operations.append(models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias)))
        operations.append(models.CreateAliasOperation(create_alias=models.CreateAlias(collection_name=destination, alias_name=alias)))
        self.client.update_collection_aliases(change_aliases_operations=operations)

    def delete_alias(self, alias: str) -> None:
        alias = self._assert_alias(alias)
        if self.alias_target(alias):
            self.client.update_collection_aliases(
                change_aliases_operations=[models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias))]
            )

    def alias_target(self, alias: str) -> Optional[str]:
        for item in self.collection_inventory().get("aliases", ()):
            if item.get("alias") == alias:
                targets = item.get("targets") or []
                return str(targets[0]) if len(targets) == 1 and targets[0] else None
        return None


class FakeQdrant:
    """Deterministic in-memory Qdrant double with operation fault injection."""

    def __init__(self, *, default_alias: str = "papers", dense_dim: int = 4) -> None:
        self.default_alias = default_alias
        self.dense_dim = int(dense_dim)
        self.collections: Dict[str, List[CandidatePoint]] = {}
        self.aliases: Dict[str, str] = {}
        self.calls: List[Tuple[str, str]] = []
        self._failures: Dict[str, List[BaseException]] = {}
        self._post_failures: Dict[str, List[BaseException]] = {}
        self._lock = threading.RLock()
        self._candidate: Optional[str] = None
        self._source_collection: Optional[str] = None
        self._alias: Optional[str] = None
        self._run_token: Optional[str] = None
        self._retire_capability: Optional[object] = None
        self._retire_allowlist = set()

    def bind_candidate(self, candidate: str, *, source_collection: str, alias: str, run_token: str, retire_capability: object) -> None:
        with self._lock:
            self._candidate = _validate_name(candidate, label="candidate")
            self._source_collection = _validate_name(source_collection, label="source_collection")
            self._alias = _validate_name(alias, label="alias")
            self._run_token = _validate_name(run_token, label="run_token")
            self._retire_capability = retire_capability
            self._retire_allowlist = set()

    def authorize_retire(self, collection: str, *, run_token: str, expected_target: str, capability: object) -> None:
        collection = _validate_name(collection, label="collection")
        expected_target = _validate_name(expected_target, label="expected_target")
        with self._lock:
            if (
                self._candidate is None
                or self._run_token is None
                or self._retire_capability is None
                or run_token != self._run_token
                or capability is not self._retire_capability
                or collection != expected_target
                or collection == self._candidate
            ):
                raise CandidateIndexError("RETIRE_TARGET_INVALID", code="RETIRE_TARGET_INVALID")
            self._retire_allowlist.add(collection)

    def _assert_destination(self, destination: str, *, allow_retire: bool = False) -> str:
        destination = _validate_name(destination, label="destination")
        if self._candidate is None:
            raise CandidateIndexError("CANDIDATE_PORT_NOT_BOUND", code="CANDIDATE_PORT_NOT_BOUND")
        if destination != self._candidate and not (allow_retire and destination in self._retire_allowlist):
            raise CandidateIndexError("CANDIDATE_DESTINATION_FORBIDDEN", code="CANDIDATE_DESTINATION_FORBIDDEN")
        return destination

    def _assert_alias(self, alias: str) -> str:
        alias = _validate_name(alias, label="alias")
        if self._alias is not None and alias != self._alias:
            raise CandidateIndexError("CANDIDATE_ALIAS_FORBIDDEN", code="CANDIDATE_ALIAS_FORBIDDEN")
        return alias

    def inject_failure(self, operation: str, error: Optional[BaseException] = None, *, times: int = 1) -> None:
        failure = error or CandidateIndexError("INJECTED_FAILURE", code="INJECTED_FAILURE")
        self._failures.setdefault(operation, []).extend([failure] * max(1, int(times)))

    def inject_post_failure(self, operation: str, error: Optional[BaseException] = None, *, times: int = 1) -> None:
        failure = error or CandidateIndexError("INJECTED_POST_FAILURE", code="INJECTED_POST_FAILURE")
        self._post_failures.setdefault(operation, []).extend([failure] * max(1, int(times)))

    def seed_collection(self, name: str, *, dense_dim: Optional[int] = None) -> None:
        """Seed pre-existing topology in tests without exposing a write port."""
        name = _validate_name(name, label="seed_collection")
        with self._lock:
            if self._candidate is not None:
                raise CandidateIndexError("CANDIDATE_PORT_ALREADY_BOUND", code="CANDIDATE_PORT_ALREADY_BOUND")
            self.collections.setdefault(name, [])
            if dense_dim is not None:
                self.dense_dim = int(dense_dim)

    def _before(self, operation: str, target: str = "") -> None:
        self.calls.append((operation, target))
        failures = self._failures.get(operation) or []
        if failures:
            raise failures.pop(0)

    def _after(self, operation: str) -> None:
        failures = self._post_failures.get(operation) or []
        if failures:
            raise failures.pop(0)

    def collection_inventory(self) -> Dict[str, Any]:
        with self._lock:
            self._before("inventory")
            return {
                "collections": [
                    {"name": name, "kind": "physical", "exists": True, "point_count": len(points), "vector_names": ["dense", "sparse"]}
                    for name, points in sorted(self.collections.items())
                ],
                "aliases": [{"alias": alias, "targets": [target]} for alias, target in sorted(self.aliases.items())],
            }

    def ensure_collection(self, destination: str, *, dense_dim: int) -> None:
        destination = self._assert_destination(destination)
        with self._lock:
            self._before("ensure_collection", destination)
            self.collections.setdefault(destination, [])
            self.dense_dim = int(dense_dim)

    def delete_collection(self, destination: str) -> None:
        destination = self._assert_destination(destination, allow_retire=True)
        with self._lock:
            self._before("delete_collection", destination)
            self.collections.pop(destination, None)
            for alias, target in list(self.aliases.items()):
                if target == destination:
                    self.aliases.pop(alias, None)
            self._after("delete_collection")

    def upsert_document(self, destination: str, document_id: str, points: Sequence[CandidatePoint]) -> None:
        destination = self._assert_destination(destination)
        with self._lock:
            self._before("upsert_document", destination)
            if destination not in self.collections:
                raise CandidateIndexError("COLLECTION_NOT_FOUND", code="COLLECTION_NOT_FOUND")
            if any(str(point.payload.get("document_id")) != str(document_id) for point in points):
                raise CandidateIndexError("DOCUMENT_ID_PAYLOAD_MISMATCH", code="DOCUMENT_ID_PAYLOAD_MISMATCH")
            by_id = {point.id: point for point in self.collections[destination]}
            by_id.update({point.id: point for point in points})
            self.collections[destination] = list(by_id.values())
            self._after("upsert_document")

    def scroll_points(self, destination: str, *, offset: Optional[str] = None, limit: int = 256) -> Tuple[List[CandidatePoint], Optional[str]]:
        destination = self._assert_destination(destination)
        with self._lock:
            self._before("scroll", destination)
            points = list(self.collections.get(destination, ()))
            start = int(offset or 0)
            end = min(len(points), start + int(limit))
            return points[start:end], (str(end) if end < len(points) else None)

    def count(self, destination: str) -> int:
        with self._lock:
            self._before("count", destination)
            return len(self.collections.get(destination, ()))

    def search(self, destination: str, vector_name: str, vector: Any, *, limit: int = 1) -> List[CandidatePoint]:
        destination = self._assert_destination(destination)
        with self._lock:
            self._before("search", destination)
            points = self.collections.get(destination, ())
            return sorted(points, key=lambda point: _dot(point.vector.get(vector_name), vector), reverse=True)[: int(limit)]

    def create_alias(self, alias: str, destination: str, *, replace: bool = False) -> None:
        alias = self._assert_alias(alias)
        destination = self._assert_destination(destination)
        with self._lock:
            self._before("create_alias", alias)
            if destination not in self.collections:
                raise CandidateIndexError("COLLECTION_NOT_FOUND", code="COLLECTION_NOT_FOUND")
            if alias in self.aliases and not replace:
                raise CandidateIndexError("ALIAS_EXISTS", code="ALIAS_EXISTS")
            self.aliases[alias] = destination
            self._after("create_alias")

    def delete_alias(self, alias: str) -> None:
        alias = self._assert_alias(alias)
        with self._lock:
            self._before("delete_alias", alias)
            self.aliases.pop(alias, None)

    def alias_target(self, alias: str) -> Optional[str]:
        with self._lock:
            self._before("alias_target", alias)
            return self.aliases.get(alias)


FakeCandidateIndexPort = FakeQdrant
