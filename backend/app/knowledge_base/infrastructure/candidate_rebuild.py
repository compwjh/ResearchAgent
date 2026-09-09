"""Candidate collection rebuild protocol for Spec018 Task02A-D.

This module deliberately owns orchestration only.  Parsing and chunking are
delegated to the existing provenance/chunker entry points and all index writes
go through :class:`CandidateIndexPort` with an explicit destination.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import tempfile
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from backend.app.knowledge_base.infrastructure.candidate_index import CandidateIndexPort, CandidatePoint
from backend.app.knowledge_base.infrastructure.embed import SPARSE_DIM, embed_texts, encode_sparse
from backend.app.knowledge_base.infrastructure.index import point_id
from backend.app.knowledge_base.infrastructure.inspection import (
    InspectionError,
    InspectionManifest,
    build_inspection_manifest,
)
from backend.app.knowledge_base.infrastructure.manifest_store import (
    FinalizeBundleStore,
    ManifestStoreError,
)
from backend.app.knowledge_base.infrastructure.markdown import extract_markdown_provenance
from backend.app.knowledge_base.infrastructure.parse import extract_pdf_provenance
from backend.app.knowledge_base.infrastructure.provenance import build_source_provenance_bundle
from backend.app.knowledge_base.infrastructure.store import record_id
from backend.app.platform.config import (
    CHUNK_V2_LLM_MODEL,
    EMBED_DIM,
    EMBED_MODEL,
    KB_META_PATH,
    KB_PAPERS_DIR,
    QDRANT_PATH,
)

RUN_SCHEMA = "candidate-rebuild-run-v1"
VALIDATION_SCHEMA = "candidate-validation-v1"
TOPOLOGY_SCHEMA = "topology-inventory-v1"
_ARTIFACT_DIR = Path(__file__).resolve().parents[4] / "docs" / "sdd" / "plans" / "018" / "artifacts" / "task-02a"
CHUNKERS = ("v1", "v2")
STATUSES = (
    "preflight", "building", "validating", "ready_to_switch", "switching",
    "finalizing", "finalize_pending", "cleanup_pending", "cleaned", "completed", "failed",
)
_ALLOWED_TRANSITIONS = {
    "preflight": {"building", "failed"},
    "building": {"building", "validating", "failed"},
    "validating": {"ready_to_switch", "failed"},
    "ready_to_switch": {"switching", "failed"},
    "switching": {"finalizing", "switching"},
    "finalizing": {"completed", "finalize_pending", "finalizing"},
    "finalize_pending": {"finalizing", "completed"},
    "failed": {"cleanup_pending", "failed"},
    "cleanup_pending": {"cleaned", "cleanup_pending"},
    "cleaned": set(),
    "completed": set(),
}


class RebuildError(RuntimeError):
    """Stable, path-free error surfaced by the maintenance command."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = str(code)
        super().__init__(message or self.code)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _safe_digest_value(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, Mapping):
        return {str(key): _safe_digest_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_digest_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    return repr(value)


def _vector_digest_input(vector: Any) -> Any:
    if hasattr(vector, "indices") and hasattr(vector, "values"):
        return _safe_digest_value({"indices": list(vector.indices), "values": list(vector.values)})
    return _safe_digest_value(vector)


def _payload_digest_projection(payload: Mapping[str, Any]) -> Dict[str, Any]:
    projection = {str(key): _safe_digest_value(value) for key, value in payload.items() if key != "text"}
    projection["text_digest"] = _fingerprint(_safe_digest_value(payload.get("text")))
    return projection


def _sparse_components(vector: Any) -> Tuple[Optional[List[Any]], Optional[List[Any]]]:
    """Read both Qdrant SparseVector and mapping doubles without dict.values traps."""
    if isinstance(vector, Mapping):
        if "indices" not in vector or "values" not in vector:
            return None, None
        indices, values = vector.get("indices"), vector.get("values")
    else:
        indices, values = getattr(vector, "indices", None), getattr(vector, "values", None)
        if indices is None or values is None:
            return None, None
    try:
        return list(indices), list(values)
    except (TypeError, ValueError):
        return None, None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise RebuildError("SOURCE_READ_FAILED") from error
    return digest.hexdigest()


def _safe_id(value: Any) -> str:
    result = str(value or "").strip()
    if not result or len(result) > 256 or any(ord(char) < 32 for char in result):
        raise RebuildError("METADATA_INVALID")
    return result


@dataclass
class RunState:
    run_id: str
    source_collection: Optional[str]
    candidate_collection: str
    dry_run: bool
    status: str = "preflight"
    progress: int = 0
    document_counts: Dict[str, int] = field(default_factory=lambda: {"authoritative": 0, "orphan": 0})
    point_counts: Dict[str, int] = field(default_factory=lambda: {"v1": 0, "v2": 0, "total": 0})
    new_fingerprint: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None
    intent: Optional[Dict[str, Any]] = None
    observed: Optional[Dict[str, Any]] = None
    previous_target: Optional[str] = None
    initial_topology_digest: Optional[str] = None
    validated_topology_digest: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": RUN_SCHEMA,
            "run_id": self.run_id,
            "source_collection": self.source_collection,
            "candidate_collection": self.candidate_collection,
            "chunkers": list(CHUNKERS),
            "status": self.status,
            "progress": int(self.progress),
            "dry_run": bool(self.dry_run),
            "document_counts": dict(self.document_counts),
            "point_counts": dict(self.point_counts),
            "new_fingerprint": dict(self.new_fingerprint),
            "error_code": self.error_code,
            "intent": self.intent,
            "observed": self.observed,
            "previous_target": self.previous_target,
            "initial_topology_digest": self.initial_topology_digest,
            "validated_topology_digest": self.validated_topology_digest,
        }


class _RuntimeStore:
    """Atomic run state and redacted event log."""

    def __init__(self, root: Path, run_id: str) -> None:
        self.directory = Path(root) / run_id
        self.state_path = self.directory / "state.json"
        self.events_path = self.directory / "events.jsonl"

    def initialize(self, state: RunState) -> None:
        self.directory.mkdir(parents=True, exist_ok=False)
        self.write(state)

    def write(self, state: RunState) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        _validate_schema_instance("candidate-rebuild-run.schema.json", state.to_dict())
        encoded = (_canonical(state.to_dict()) + "\n").encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(prefix="state-", suffix=".tmp", dir=str(self.directory))
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.state_path)
            _fsync_directory(self.directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def read(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RebuildError("RUN_STATE_UNAVAILABLE") from error
        if not isinstance(data, dict) or data.get("schema_version") != RUN_SCHEMA:
            raise RebuildError("RUN_STATE_INVALID")
        try:
            _validate_schema_instance("candidate-rebuild-run.schema.json", data)
        except RebuildError as error:
            raise RebuildError("RUN_STATE_INVALID") from error
        return data

    def read_json(self, filename: str) -> Dict[str, Any]:
        try:
            data = json.loads((self.directory / filename).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RebuildError("RUN_STATE_UNAVAILABLE") from error
        if not isinstance(data, dict):
            raise RebuildError("RUN_STATE_INVALID")
        return data

    def event(self, event: Mapping[str, Any]) -> None:
        safe = {str(key): value for key, value in event.items() if key not in {"path", "source", "text", "vector"}}
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(_canonical(safe) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def write_json(self, filename: str, value: Mapping[str, Any]) -> None:
        target = self.directory / filename
        descriptor, temporary = tempfile.mkstemp(prefix=f"{target.stem}-", suffix=".tmp", dir=str(self.directory))
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write((_canonical(value) + "\n").encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            _fsync_directory(self.directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class _ExclusiveLock:
    SCHEMA_VERSION = "rebuild-lock-v1"

    def __init__(self, root: Path, *, run_id: str, command: str, recover_stale_run_id: Optional[str] = None, recovery_check: Optional[Callable[[Mapping[str, Any]], None]] = None) -> None:
        self.root = Path(root)
        self.path = self.root / "rebuild.lock"
        self.run_id = str(run_id)
        self.command = str(command)
        self.recover_stale_run_id = recover_stale_run_id
        self.recovery_check = recovery_check
        self.token = uuid.uuid4().hex

    def acquire(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        now = _now()
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "run_id": self.run_id,
            "owner": f"pid:{os.getpid()}@{socket.gethostname()}",
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "token": self.token,
            "command": self.command,
            "started_at": now,
            "heartbeat_at": now,
        }
        try:
            descriptor = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if not self.recover_stale_run_id:
                raise RebuildError("REBUILD_LOCK_HELD") from None
            self._prove_stale(self.recover_stale_run_id)
            try:
                self.path.unlink()
            except OSError as error:
                raise RebuildError("STALE_LOCK_RECOVERY_FAILED") from error
            descriptor = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write((_canonical(payload) + "\n").encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            _fsync_directory(self.root)
        except Exception:
            with suppress(OSError):
                self.path.unlink()
            raise

    def _read(self) -> Dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise RebuildError("REBUILD_LOCK_AMBIGUOUS") from error
        required = {"schema_version", "run_id", "owner", "pid", "host", "token", "command", "started_at", "heartbeat_at"}
        if not isinstance(value, dict) or set(value) != required or value.get("schema_version") != self.SCHEMA_VERSION:
            raise RebuildError("REBUILD_LOCK_AMBIGUOUS")
        string_fields = ("run_id", "owner", "host", "token", "command", "started_at", "heartbeat_at")
        if any(not isinstance(value.get(field), str) or not value[field] for field in string_fields):
            raise RebuildError("REBUILD_LOCK_AMBIGUOUS")
        if isinstance(value.get("pid"), bool) or not isinstance(value.get("pid"), int) or value["pid"] <= 0:
            raise RebuildError("REBUILD_LOCK_AMBIGUOUS")
        return value

    def _prove_stale(self, requested_run_id: str) -> None:
        value = self._read()
        if str(value.get("run_id")) != str(requested_run_id):
            raise RebuildError("REBUILD_LOCK_AMBIGUOUS")
        try:
            os.kill(int(value["pid"]), 0)
        except ProcessLookupError:
            pass
        except (PermissionError, OSError, ValueError, TypeError) as error:
            raise RebuildError("REBUILD_LOCK_AMBIGUOUS") from error
        else:
            raise RebuildError("REBUILD_LOCK_AMBIGUOUS")
        if self.recovery_check is None:
            raise RebuildError("REBUILD_LOCK_AMBIGUOUS")
        self.recovery_check(value)

    def heartbeat(self) -> None:
        try:
            value = self._read()
            if value.get("token") != self.token:
                raise RebuildError("REBUILD_LOCK_LOST")
            value["heartbeat_at"] = _now()
            _atomic_write(self.path, (_canonical(value) + "\n").encode("utf-8"))
        except RebuildError:
            raise
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise RebuildError("REBUILD_LOCK_LOST") from error

    def release(self) -> None:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if value.get("token") == self.token:
                self.path.unlink()
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise RebuildError("RUNTIME_FSYNC_FAILED") from error


def _atomic_write(path: Path, data: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _validate_schema_instance(filename: str, instance: Mapping[str, Any]) -> None:
    try:
        from jsonschema import Draft202012Validator
        schema = json.loads((_ARTIFACT_DIR / filename).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda item: list(item.path))
    except (ImportError, OSError, json.JSONDecodeError) as error:
        raise RebuildError("SCHEMA_VALIDATOR_UNAVAILABLE") from error
    if errors:
        raise RebuildError("SCHEMA_INSTANCE_INVALID")


def topology_inventory(
    index: CandidateIndexPort,
    *,
    alias: str = "papers",
    source_collection: str = "papers",
    candidate_prefix: str = "papers_rebuild_",
    runtime_root: Optional[Path] = None,
    state_override: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a closed, digestable and fail-closed topology inventory."""
    try:
        raw = index.collection_inventory()
        raw_collections = raw["collections"]
        raw_aliases = raw["aliases"]
    except Exception as error:
        raise RebuildError("INDEX_TOPOLOGY_AMBIGUOUS") from error
    if not isinstance(raw_collections, list) or not isinstance(raw_aliases, list):
        raise RebuildError("INDEX_TOPOLOGY_AMBIGUOUS")
    collections: List[Dict[str, Any]] = []
    names = set()
    for raw_item in raw_collections:
        if not isinstance(raw_item, Mapping) or not raw_item.get("name"):
            raise RebuildError("INDEX_TOPOLOGY_AMBIGUOUS")
        name = str(raw_item["name"])
        if name in names:
            raise RebuildError("INDEX_TOPOLOGY_AMBIGUOUS")
        names.add(name)
        collections.append({
            "name": name,
            "kind": "candidate" if name.startswith(candidate_prefix) else "physical",
            "exists": bool(raw_item.get("exists", True)),
            "point_count": int(raw_item.get("point_count", 0)),
            "vector_names": sorted(str(item) for item in (raw_item.get("vector_names") or [])),
        })
    aliases: List[Dict[str, str]] = []
    alias_names = set()
    for raw_item in raw_aliases:
        if not isinstance(raw_item, Mapping):
            raise RebuildError("INDEX_TOPOLOGY_AMBIGUOUS")
        name = str(raw_item.get("name") or raw_item.get("alias") or "")
        targets = raw_item.get("targets")
        target = raw_item.get("target")
        if target is None and isinstance(targets, list) and len(targets) == 1:
            target = targets[0]
        if not name or name in alias_names or not target or (isinstance(targets, list) and len(targets) != 1):
            raise RebuildError("INDEX_TOPOLOGY_AMBIGUOUS")
        target = str(target)
        if target not in names:
            raise RebuildError("INDEX_TOPOLOGY_AMBIGUOUS")
        alias_names.add(name)
        aliases.append({"name": name, "target": target})
    aliases.sort(key=lambda item: item["name"])
    collections.sort(key=lambda item: item["name"])
    physical = [item for item in collections if item["kind"] == "physical"]
    candidates = [item for item in collections if item["kind"] == "candidate"]
    run_directories: List[str] = []
    if runtime_root and Path(runtime_root).exists():
        run_directories = sorted(item.name for item in Path(runtime_root).iterdir() if item.is_dir())
    state = dict(state_override or {})
    if not state and runtime_root and len(run_directories) == 1:
        try:
            state = _RuntimeStore(Path(runtime_root), run_directories[0]).read()
        except RebuildError as error:
            raise RebuildError("INDEX_TOPOLOGY_AMBIGUOUS") from error
    default_targets = [item["target"] for item in aliases if item["name"] == alias]
    source_exists = any(item["name"] == source_collection and item["exists"] for item in physical)
    default_state = "ambiguous" if len(default_targets) != 1 and default_targets else "alias" if default_targets else "physical" if source_exists else "missing"
    candidate_state = "ambiguous" if len(candidates) > 1 else "single" if candidates else "missing"
    state_candidate = state.get("candidate_collection")
    active_is_candidate = bool(default_targets and default_targets[0] in {item["name"] for item in candidates})
    legal_switch_pair = bool(state_candidate and state_candidate in {item["name"] for item in candidates} and active_is_candidate and len(candidates) == 2)
    matrix = {"default_state": default_state, "candidate_state": candidate_state, "safe_to_switch": default_state != "ambiguous" and (candidate_state != "ambiguous" or legal_switch_pair)}
    inventory: Dict[str, Any] = {
        "schema_version": TOPOLOGY_SCHEMA,
        "default_alias": alias,
        "physical_collections": physical,
        "candidate_collections": candidates,
        "collections": collections,
        "aliases": aliases,
        "run_directories": run_directories,
        "active_generation": default_targets[0] if default_targets else source_collection if source_exists else None,
        "state_run_id": state.get("run_id"),
        "state_status": state.get("status"),
        "state_candidate": state.get("candidate_collection"),
        "matrix": matrix,
    }
    inventory["inventory_digest"] = _fingerprint({
        "schema_version": inventory["schema_version"],
        "default_alias": inventory["default_alias"],
        "physical_collections": inventory["physical_collections"],
        "candidate_collections": inventory["candidate_collections"],
        "collections": inventory["collections"],
        "aliases": inventory["aliases"],
        "active_generation": inventory["active_generation"],
        "matrix": inventory["matrix"],
    })
    _validate_schema_instance("topology-inventory.schema.json", inventory)
    return inventory


class CandidateRebuildService:
    """Build and optionally switch a fully validated candidate collection."""

    def __init__(
        self,
        *,
        metadata_path: Path = KB_META_PATH,
        papers_dir: Path = KB_PAPERS_DIR,
        index: CandidateIndexPort,
        runtime_root: Optional[Path] = None,
        source_collection: str = "papers",
        alias: str = "papers",
        dense_dim: int = EMBED_DIM,
        embedder: Optional[Callable[[Sequence[str]], Sequence[Sequence[float]]]] = None,
        llm: Optional[Callable[[str], str]] = None,
        finalizer: Optional[Callable[[Mapping[str, Any]], None]] = None,
        finalize_store: Optional[FinalizeBundleStore] = None,
        run_id_factory: Optional[Callable[[], str]] = None,
        lock_ttl_seconds: int = 900,
    ) -> None:
        self.metadata_path = Path(metadata_path)
        self.papers_dir = Path(papers_dir)
        self.index = index
        self.runtime_root = Path(runtime_root or (Path(QDRANT_PATH).parent / "rebuild-runs"))
        self.source_collection = source_collection
        self.alias = alias
        self.dense_dim = int(dense_dim)
        self.embedder = embedder or embed_texts
        self.llm = llm
        self._uses_default_finalizer = finalizer is None
        self.finalizer = finalizer or self._finalize_bundle
        self.finalize_store = finalize_store or FinalizeBundleStore(self._finalize_root())
        self.run_id_factory = run_id_factory or (lambda: uuid.uuid4().hex)
        self.lock_ttl_seconds = lock_ttl_seconds
        self._state: Optional[RunState] = None
        self._store: Optional[_RuntimeStore] = None
        self._lock: Optional[_ExclusiveLock] = None
        self._action_sequence = 0
        self._retire_capability: Optional[object] = None
        self._finalize_metadata: List[Dict[str, Any]] = []
        self._finalize_manifests: Dict[Tuple[str, str], InspectionManifest] = {}

    def _finalize_root(self) -> Path:
        """Resolve the project root without assuming tests use ``data/kb``."""
        parent = self.metadata_path.parent
        if parent.name == "kb" and parent.parent.name == "data":
            return parent.parent.parent
        return parent

    def _load_metadata(self) -> List[Dict[str, Any]]:
        if not self.metadata_path.exists():
            return []
        try:
            raw = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RebuildError("METADATA_INVALID") from error
        if not isinstance(raw, list):
            raise RebuildError("METADATA_INVALID")
        records: List[Dict[str, Any]] = []
        seen = set()
        for item in raw:
            if not isinstance(item, Mapping):
                raise RebuildError("METADATA_INVALID")
            document_id = _safe_id(record_id(item))
            if document_id in seen:
                raise RebuildError("DUPLICATE_DOCUMENT_ID")
            seen.add(document_id)
            record = dict(item)
            record["document_id"] = document_id
            records.append(record)
        return records

    def _source_path(self, record: Mapping[str, Any]) -> Path:
        filename = str(record.get("stored_name") or record.get("file_name") or f"{record['document_id']}.pdf")
        candidate = Path(filename)
        if candidate.name != filename or filename in {"", ".", ".."}:
            raise RebuildError("SOURCE_PATH_INVALID")
        return self.papers_dir / candidate

    def _preflight(self) -> Tuple[List[Tuple[Dict[str, Any], Path, Any]], List[str]]:
        records = self._load_metadata()
        if not records:
            raise RebuildError("NO_DOCUMENTS_TO_REBUILD")
        known = set()
        parsed: List[Tuple[Dict[str, Any], Path, Any]] = []
        for record in records:
            path = self._source_path(record)
            known.add(path.name)
            if not path.exists() or not path.is_file():
                raise RebuildError("SOURCE_MISSING")
            before = _sha256(path)
            supplied = record.get("source_sha256") or record.get("sha256")
            if supplied is not None and str(supplied).lower() != before:
                raise RebuildError("SOURCE_HASH_MISMATCH")
            media_type = str(record.get("media_type") or ("text/markdown" if path.suffix.lower() in {".md", ".markdown"} else "application/pdf"))
            if media_type not in {"application/pdf", "text/markdown"}:
                raise RebuildError("SOURCE_MEDIA_TYPE_UNSUPPORTED")
            try:
                provenance = extract_markdown_provenance(path, document_id=record["document_id"], source_sha256=before) if media_type == "text/markdown" else extract_pdf_provenance(path, document_id=record["document_id"], source_sha256=before)
            except Exception as error:
                raise RebuildError(getattr(error, "code", "SOURCE_PARSE_FAILED")) from error
            after = _sha256(path)
            if before != after:
                raise RebuildError("SOURCE_CHANGED_DURING_PREFLIGHT")
            parsed.append((record, path, provenance))
        orphan = sorted(path.name for path in self.papers_dir.iterdir() if path.is_file() and path.name not in known) if self.papers_dir.exists() else []
        return parsed, orphan

    def _new_state(self, *, dry_run: bool) -> RunState:
        run_id = _safe_id(self.run_id_factory())
        return RunState(run_id=run_id, source_collection=self.source_collection, candidate_collection=f"papers_rebuild_{run_id}", dry_run=dry_run)

    def _preflight_snapshot(self) -> Tuple[Optional[str], str]:
        lock_path = self.runtime_root / "rebuild.lock"
        try:
            lock_digest = hashlib.sha256(lock_path.read_bytes()).hexdigest() if lock_path.exists() else None
        except OSError as error:
            raise RebuildError("PREFLIGHT_STALE") from error
        inventory = topology_inventory(self.index, alias=self.alias, source_collection=self.source_collection, runtime_root=self.runtime_root)
        return lock_digest, str(inventory["inventory_digest"])

    def _assert_new_build_topology(self, inventory: Mapping[str, Any]) -> None:
        matrix = inventory.get("matrix") or {}
        candidate_state = matrix.get("candidate_state")
        active_generation = inventory.get("active_generation")
        if candidate_state not in {"missing", "single"} or (candidate_state == "single" and active_generation not in {item.get("name") for item in inventory.get("candidate_collections", ())}):
            raise RebuildError("INDEX_TOPOLOGY_AMBIGUOUS")
        if matrix.get("default_state") not in {"physical", "alias", "missing"}:
            raise RebuildError("INDEX_TOPOLOGY_AMBIGUOUS")
        for directory in inventory.get("run_directories", ()):
            try:
                state = _RuntimeStore(self.runtime_root, directory).read()
            except RebuildError as error:
                raise RebuildError("INDEX_TOPOLOGY_AMBIGUOUS") from error
            if state.get("status") not in {"completed", "cleaned"}:
                raise RebuildError("INDEX_TOPOLOGY_AMBIGUOUS")

    def _transition(self, status: str, *, progress: Optional[int] = None, error: Optional[str] = None) -> None:
        if self._state is None:
            raise RebuildError("RUN_STATE_INVALID")
        if status not in STATUSES:
            raise RebuildError("FSM_INVALID_TRANSITION")
        if status != self._state.status and status not in _ALLOWED_TRANSITIONS.get(self._state.status, set()):
            raise RebuildError("FSM_INVALID_TRANSITION")
        if progress is not None and int(progress) < self._state.progress:
            raise RebuildError("FSM_PROGRESS_REGRESSION")
        self._state.status = status
        if progress is not None:
            self._state.progress = min(100, int(progress))
        if error is not None:
            self._state.error_code = error
        if self._store:
            self._store.write(self._state)
            self._store.event({"event": "state", "status": status, "progress": self._state.progress, "error_code": error})

    def _action(self, action: str, operation: str, callback: Callable[[], Any], *, previous_target_override: Optional[str] = None) -> Any:
        if self._state is None or self._store is None:
            raise RebuildError("RUN_STATE_INVALID")
        self._action_sequence += 1
        before = topology_inventory(self.index, alias=self.alias, source_collection=self.source_collection, runtime_root=self.runtime_root, state_override=self._state.to_dict())
        previous_target = next((item["target"] for item in before.get("aliases", ()) if item["name"] == self.alias), None)
        intent = {
            "sequence": self._action_sequence,
            "action": action,
            "candidate": self._state.candidate_collection,
            "previous_target": previous_target_override or previous_target or (self.source_collection if before["matrix"]["default_state"] == "physical" else None),
            "expected_topology_digest": before["inventory_digest"],
            "started_at": _now(),
        }
        self._state.intent = intent
        self._store.write(self._state)
        self._store.event({"event": "intent", **intent, "phase": "before"})
        try:
            result = callback()
        except Exception as error:
            self._state.error_code = getattr(error, "code", type(error).__name__)
            observed_topology = self._observe_topology()
            fresh_summary = {"schema_version": TOPOLOGY_SCHEMA, "inventory_digest": observed_topology["inventory_digest"]} if observed_topology else None
            self._state.observed = {"sequence": self._action_sequence, "action": action, "phase": "after", "outcome": "error" if observed_topology else "unknown", "previous_target": intent["previous_target"], "expected_topology_digest": intent["expected_topology_digest"], "fresh_topology": fresh_summary, "topology_digest": observed_topology.get("inventory_digest") if observed_topology else None, "error_code": getattr(error, "code", type(error).__name__), "completed_at": _now()}
            self._store.write(self._state)
            self._store.event({"event": "observed", **self._state.observed})
            raise
        observed_topology = self._observe_topology()
        fresh_summary = {"schema_version": TOPOLOGY_SCHEMA, "inventory_digest": observed_topology["inventory_digest"]} if observed_topology else None
        self._state.observed = {"sequence": self._action_sequence, "action": action, "phase": "after", "outcome": "ok" if observed_topology else "unknown", "previous_target": intent["previous_target"], "expected_topology_digest": intent["expected_topology_digest"], "fresh_topology": fresh_summary, "topology_digest": observed_topology.get("inventory_digest") if observed_topology else None, "completed_at": _now()}
        if not observed_topology:
            self._state.error_code = "ACTION_RESULT_UNKNOWN"
        self._store.write(self._state)
        self._store.event({"event": "observed", **self._state.observed})
        if not observed_topology:
            raise RebuildError("ACTION_RESULT_UNKNOWN")
        if self._lock:
            self._lock.heartbeat()
        return result

    def _observe_topology(self) -> Dict[str, Any]:
        if self._state is None:
            return {}
        try:
            return topology_inventory(self.index, alias=self.alias, source_collection=self.source_collection, runtime_root=self.runtime_root, state_override=self._state.to_dict())
        except RebuildError:
            return {}

    def _validate_instance(self, filename: str, instance: Mapping[str, Any]) -> None:
        _validate_schema_instance(filename, instance)

    def _bind_port(self, candidate: str) -> None:
        binder = getattr(self.index, "bind_candidate", None)
        if binder is None or not callable(binder):
            raise RebuildError("CANDIDATE_PORT_NOT_BOUND")
        run_token = self._state.run_id if self._state is not None else ""
        self._retire_capability = object()
        try:
            binder(candidate, source_collection=self.source_collection, alias=self.alias, run_token=run_token, retire_capability=self._retire_capability)
        except Exception as error:
            raise RebuildError(getattr(error, "code", "CANDIDATE_PORT_NOT_BOUND")) from error

    def _recovery_check(self, lock_value: Mapping[str, Any]) -> None:
        run_id = str(lock_value.get("run_id") or "")
        state = _RuntimeStore(self.runtime_root, run_id).read()
        if state.get("run_id") != run_id or state.get("status") not in {"ready_to_switch", "switching", "finalizing", "finalize_pending", "cleanup_pending"}:
            raise RebuildError("REBUILD_LOCK_AMBIGUOUS")
        observed = state.get("observed") or {}
        intent = state.get("intent") or {}
        if intent and (
            not observed
            or observed.get("phase") != "after"
            or observed.get("sequence") != intent.get("sequence")
            or observed.get("action") != intent.get("action")
            or observed.get("outcome") == "unknown"
        ):
            raise RebuildError("REBUILD_LOCK_AMBIGUOUS")
        inventory = topology_inventory(self.index, alias=self.alias, source_collection=self.source_collection, runtime_root=self.runtime_root, state_override=state)
        if inventory.get("state_run_id") != run_id or inventory.get("state_candidate") != state.get("candidate_collection"):
            raise RebuildError("REBUILD_LOCK_AMBIGUOUS")
        if intent and observed.get("topology_digest") != inventory.get("inventory_digest"):
            raise RebuildError("REBUILD_LOCK_AMBIGUOUS")
        if not (inventory.get("matrix") or {}).get("safe_to_switch"):
            raise RebuildError("REBUILD_LOCK_AMBIGUOUS")

    def _authorize_retire(self, collection: str) -> None:
        authorizer = getattr(self.index, "authorize_retire", None)
        if self._state is None or self._store is None or not callable(authorizer):
            raise RebuildError("CANDIDATE_RETIRE_AUTHORIZATION_REQUIRED")
        intent = self._state.intent or {}
        if intent.get("previous_target") != collection or self._state.previous_target not in {None, collection}:
            raise RebuildError("RETIRE_TARGET_INVALID")
        try:
            inventory = topology_inventory(
                self.index,
                alias=self.alias,
                source_collection=self.source_collection,
                runtime_root=self.runtime_root,
                state_override=self._state.to_dict(),
            )
        except RebuildError as error:
            raise RebuildError("RETIRE_TOPOLOGY_MISMATCH") from error
        names = {item["name"] for item in inventory.get("collections", ())}
        referenced = {item["target"] for item in inventory.get("aliases", ())}
        if collection == self._state.candidate_collection or collection not in names or collection in referenced:
            raise RebuildError("RETIRE_TOPOLOGY_MISMATCH")
        try:
            if self._retire_capability is None:
                raise RebuildError("CANDIDATE_RETIRE_AUTHORIZATION_REQUIRED")
            authorizer(collection, run_token=self._state.run_id, expected_target=collection, capability=self._retire_capability)
        except Exception as error:
            raise RebuildError(getattr(error, "code", "CANDIDATE_RETIRE_AUTHORIZATION_FAILED")) from error

    def _retire_authorized(self, collection: str, *, action: str) -> None:
        if self._state is None:
            raise RebuildError("RUN_STATE_INVALID")

        def delete() -> Any:
            self._authorize_retire(collection)
            return self.index.delete_collection(collection)

        self._action(action, "delete_collection", delete, previous_target_override=collection)

    def _point_payload(self, record: Mapping[str, Any], bundle: Any, chunk: Mapping[str, Any]) -> Dict[str, Any]:
        anchor_digest = _fingerprint(list(bundle.anchors))
        return {
            "document_id": record["document_id"],
            "file_name": str(record.get("file_name") or record.get("stored_name") or ""),
            "page": chunk.get("page"),
            "page_end": chunk.get("page_end"),
            "section": str(chunk.get("section") or ""),
            "chunker": chunk["chunker"],
            "is_citation": False,
            "chunk_index": int(chunk["chunk_index"]),
            "text": str(chunk["text"]),
            "uploaded_at": str(record.get("uploaded_at") or ""),
            "source_sha256": bundle.source_sha256,
            "text_digest": _fingerprint(str(chunk["text"])),
            "payload_schema_version": bundle.payload_schema_version,
            "anchor_digest": anchor_digest,
            "anchor_count": int(len(bundle.anchors)),
            "unmapped_count": int(bundle.unmapped_count),
            "chunker_config_fingerprint": bundle.chunker_config_fingerprint,
            "embedding_config_fingerprint": _fingerprint({"model": EMBED_MODEL, "dimension": self.dense_dim}),
            "model_config_fingerprint": _fingerprint({"model": CHUNK_V2_LLM_MODEL if chunk["chunker"] == "v2" else None, "llm_used": bundle.llm_used}),
            "llm_used": bool(bundle.llm_used),
        }

    def _build(self, parsed: Sequence[Tuple[Dict[str, Any], Path, Any]]) -> Dict[str, Any]:
        if self._state is None:
            raise RebuildError("RUN_STATE_INVALID")
        candidate = self._state.candidate_collection
        self._finalize_metadata = [dict(record) for record, _path, _provenance in parsed]
        self._finalize_manifests = {}
        self._action("create_candidate", "ensure_collection", lambda: self.index.ensure_collection(candidate, dense_dim=self.dense_dim))
        self._transition("building", progress=5)
        expected: Dict[str, Dict[str, Any]] = {}
        for position, (record, _path, provenance) in enumerate(parsed, start=1):
            document_id = record["document_id"]
            expected[document_id] = {
                "media_type": provenance.media_type,
                "source_sha256": provenance.source_sha256,
                "indexed_source_sha256": provenance.source_sha256,
                "parser_version": provenance.source_parser_version,
                "chunkers": {},
            }
            for chunker in CHUNKERS:
                try:
                    bundle = build_source_provenance_bundle(provenance, chunker=chunker, llm=self.llm)
                except Exception as error:
                    raise RebuildError(getattr(error, "code", "PROVENANCE_BUILD_FAILED")) from error
                if bundle.status == "failed" or not bundle.chunks:
                    raise RebuildError("PROVENANCE_BUILD_FAILED")
                if chunker == "v2" and (not bundle.llm_used or bundle.degradation_diagnostics):
                    raise RebuildError("V2_RULES_ONLY_LLM_NOT_USED")
                texts = [str(chunk["text"]) for chunk in bundle.chunks]
                try:
                    vectors = list(self.embedder(texts))
                except Exception as error:
                    raise RebuildError("EMBEDDING_FAILED") from error
                if len(vectors) != len(texts) or any(len(vector) != self.dense_dim for vector in vectors):
                    raise RebuildError("DENSE_DIMENSION_MISMATCH")
                points = [
                    CandidatePoint(
                        id=point_id(document_id, int(chunk["chunk_index"]), chunker),
                        vector={"dense": list(vectors[index]), "sparse": encode_sparse(texts[index])},
                        payload=self._point_payload(record, bundle, chunk),
                    )
                    for index, chunk in enumerate(bundle.chunks)
                ]
                try:
                    self._finalize_manifests[(document_id, chunker)] = build_inspection_manifest(
                        record,
                        bundle,
                        [point.payload for point in points],
                    )
                except InspectionError as error:
                    raise RebuildError(error.code) from error
                self._action("upsert_document", "upsert_document", lambda points=points, document_id=document_id: self.index.upsert_document(candidate, document_id, points))
                payload_projection = [_payload_digest_projection(point.payload) for point in points]
                text_digest = _fingerprint([projection["text_digest"] for projection in payload_projection])
                dense_vector_digest = _fingerprint(_vector_digest_input([point.vector["dense"] for point in points]))
                sparse_vector_digest = _fingerprint(_vector_digest_input([_vector_digest_input(point.vector["sparse"]) for point in points]))
                expected[document_id]["chunkers"][chunker] = {
                    "chunk_count": len(points),
                    "point_ids": [point.id for point in points],
                    "chunk_indexes": [int(point.payload["chunk_index"]) for point in points],
                    "payload_schema_version": bundle.payload_schema_version,
                    "chunker_config_fingerprint": bundle.chunker_config_fingerprint,
                    "embedding_config_fingerprint": _fingerprint({"model": EMBED_MODEL, "dimension": self.dense_dim}),
                    "model_config_fingerprint": _fingerprint({"model": CHUNK_V2_LLM_MODEL if chunker == "v2" else None, "llm_used": bundle.llm_used}),
                    "llm_used": bool(bundle.llm_used),
                    "anchor_count": int(len(bundle.anchors)),
                    "unmapped_count": int(bundle.unmapped_count),
                    "payload_digest": _fingerprint(payload_projection),
                    "text_digest": text_digest,
                    "anchor_digest": _fingerprint(list(bundle.anchors)),
                    "dense_vector_digest": dense_vector_digest,
                    "sparse_vector_digest": sparse_vector_digest,
                }
                self._state.point_counts[chunker] += len(points)
                self._state.point_counts["total"] += len(points)
            self._state.document_counts["authoritative"] = position
            self._transition("building", progress=5 + int(65 * position / max(1, len(parsed))))
        return expected

    def _scroll_all(self, destination: str) -> List[CandidatePoint]:
        points: List[CandidatePoint] = []
        offset: Optional[str] = None
        while True:
            batch, offset = self.index.scroll_points(destination, offset=offset, limit=256)
            points.extend(batch)
            if offset is None:
                return points

    def _recompute_candidate_fingerprint(self) -> Tuple[str, int]:
        """Recompute the candidate digest from the collection, not JSON state.

        Resume paths use this as the independent trust root.  The run state and
        validation artifact may agree with one another after a coordinated edit,
        but neither can manufacture a digest for changed candidate points.
        """
        if self._state is None:
            raise RebuildError("RUN_STATE_INVALID")
        try:
            points = self._scroll_all(self._state.candidate_collection)
        except Exception as error:
            raise RebuildError("CANDIDATE_VALIDATION_FAILED") from error
        rows: List[Dict[str, Any]] = []
        errors: List[str] = []
        seen: set[str] = set()
        required_payload = {"document_id", "file_name", "page", "page_end", "section", "chunker", "is_citation", "chunk_index", "text", "uploaded_at", "source_sha256"}
        allowed_payload = required_payload | {"text_digest", "payload_schema_version", "anchor_digest", "anchor_count", "unmapped_count", "chunker_config_fingerprint", "embedding_config_fingerprint", "model_config_fingerprint", "llm_used"}
        for point in points:
            if point.id in seen:
                errors.append("DUPLICATE_POINT_ID")
            seen.add(point.id)
            payload = point.payload if isinstance(point.payload, Mapping) else {}
            if not isinstance(point.payload, Mapping) or set(payload) < required_payload or set(payload) - allowed_payload:
                errors.append("PAYLOAD_INVALID")
            document_id = payload.get("document_id")
            chunker = payload.get("chunker")
            chunk_index = payload.get("chunk_index")
            if not isinstance(document_id, str) or not document_id or not isinstance(chunker, str) or chunker not in CHUNKERS:
                errors.append("PAYLOAD_INVALID")
                continue
            if isinstance(chunk_index, bool) or not isinstance(chunk_index, int) or chunk_index < 0 or point.id != point_id(document_id, chunk_index, chunker):
                errors.append("POINT_ID_MISMATCH")
                continue
            if not isinstance(payload.get("text"), str) or payload.get("text_digest") != _fingerprint(_safe_digest_value(payload.get("text"))):
                errors.append("PAYLOAD_TEXT_DIGEST_MISMATCH")
            if not isinstance(payload.get("source_sha256"), str) or any(not isinstance(payload.get(name), str) or not payload.get(name) for name in ("anchor_digest", "chunker_config_fingerprint", "embedding_config_fingerprint", "model_config_fingerprint")):
                errors.append("PAYLOAD_METADATA_INVALID")
            if not isinstance(payload.get("llm_used"), bool):
                errors.append("PAYLOAD_METADATA_INVALID")
            expected_embedding = _fingerprint({"model": EMBED_MODEL, "dimension": self.dense_dim})
            expected_model = _fingerprint({"model": CHUNK_V2_LLM_MODEL if chunker == "v2" else None, "llm_used": payload.get("llm_used")})
            expected_chunkers = {
                _fingerprint({"chunk_size": 1000, "overlap": 200}),
                _fingerprint({"max_chars": 1200, "llm": "disabled"}),
                _fingerprint({"max_chars": 1200, "llm": "injected"}),
            }
            if payload.get("embedding_config_fingerprint") != expected_embedding or payload.get("model_config_fingerprint") != expected_model or payload.get("chunker_config_fingerprint") not in expected_chunkers:
                errors.append("BUNDLE_CONFIG_MISMATCH")
            if not isinstance(point.vector, Mapping) or "dense" not in point.vector or "sparse" not in point.vector:
                errors.append("DENSE_SPARSE_MISSING")
                continue
            dense = point.vector["dense"]
            dense_finite = isinstance(dense, (list, tuple)) and len(dense) == self.dense_dim and all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in dense)
            sparse_indices, sparse_values = _sparse_components(point.vector["sparse"])
            if sparse_indices is None or sparse_values is None:
                sparse_indices, sparse_values = [], []
                errors.append("SPARSE_VECTOR_INVALID")
            try:
                sorted_unique = sparse_indices == sorted(sparse_indices) and len(sparse_indices) == len(set(sparse_indices))
            except (TypeError, ValueError):
                sorted_unique = False
            sparse_valid = len(sparse_indices) == len(sparse_values) and sorted_unique and all(isinstance(index, int) and not isinstance(index, bool) and 0 <= index < SPARSE_DIM for index in sparse_indices) and all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in sparse_values)
            if not dense_finite:
                errors.append("DENSE_VECTOR_INVALID")
            if not sparse_valid:
                errors.append("SPARSE_VECTOR_INVALID")
            rows.append({"document_id": document_id, "chunker": chunker, "chunk_index": chunk_index, "point_id": point.id, "dense_dimension": len(dense) if isinstance(dense, (list, tuple)) else 0, "dense_finite": dense_finite, "dense_digest": _fingerprint(_vector_digest_input(dense)), "sparse_nnz": len(sparse_indices), "sparse_digest": _fingerprint(_vector_digest_input({"indices": sparse_indices, "values": sparse_values})), "payload_digest": _fingerprint(_payload_digest_projection(payload)), "anchor_digest": payload.get("anchor_digest"), "chunker_config_fingerprint": payload.get("chunker_config_fingerprint"), "embedding_config_fingerprint": payload.get("embedding_config_fingerprint"), "model_config_fingerprint": payload.get("model_config_fingerprint"), "llm_used": payload.get("llm_used")})
        if not points or errors:
            raise RebuildError("CANDIDATE_VALIDATION_FAILED")
        rows.sort(key=lambda item: (item["document_id"], item["chunker"], item["chunk_index"], item["point_id"]))
        return _fingerprint(rows), len(points)

    def _validate(self, expected: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
        if self._state is None:
            raise RebuildError("RUN_STATE_INVALID")
        try:
            self._transition("validating", progress=75)
            points = self._scroll_all(self._state.candidate_collection)
        except RebuildError:
            raise
        except Exception as error:
            raise RebuildError("CANDIDATE_VALIDATION_FAILED") from error
        errors: List[str] = []
        ids = [point.id for point in points]
        if len(ids) != len(set(ids)):
            errors.append("DUPLICATE_POINT_ID")
        by_doc_chunker: Dict[Tuple[str, str], List[int]] = {}
        by_point: Dict[Tuple[str, str], List[CandidatePoint]] = {}
        collection_rows: List[Dict[str, Any]] = []
        required_payload = {"document_id", "file_name", "page", "page_end", "section", "chunker", "is_citation", "chunk_index", "text", "uploaded_at", "source_sha256"}
        allowed_payload = required_payload | {"text_digest", "payload_schema_version", "anchor_digest", "anchor_count", "unmapped_count", "chunker_config_fingerprint", "embedding_config_fingerprint", "model_config_fingerprint", "llm_used"}
        for point in points:
            payload = point.payload if isinstance(point.payload, Mapping) else {}
            if not isinstance(point.payload, Mapping):
                errors.append("PAYLOAD_TYPE_INVALID")
            document_id = str(payload.get("document_id") or "")
            chunker = str(payload.get("chunker") or "")
            if document_id not in expected or chunker not in CHUNKERS:
                errors.append("UNEXPECTED_POINT")
                continue
            if set(payload) < required_payload:
                errors.append("PAYLOAD_REQUIRED_FIELD_MISSING")
            if set(payload) - allowed_payload:
                errors.append("PAYLOAD_UNKNOWN_FIELD")
            raw_index = payload.get("chunk_index", -1)
            if isinstance(raw_index, bool) or not isinstance(raw_index, int):
                errors.append("CHUNK_INDEX_INVALID")
                continue
            chunk_index = int(raw_index)
            if point.id != point_id(document_id, chunk_index, chunker):
                errors.append("POINT_ID_MISMATCH")
            by_doc_chunker.setdefault((document_id, chunker), []).append(chunk_index)
            by_point.setdefault((document_id, chunker), []).append(point)
            if payload.get("source_sha256") != expected[document_id].get("source_sha256"):
                errors.append("SOURCE_HASH_MISMATCH")
            if (
                not isinstance(payload.get("document_id"), str)
                or not isinstance(payload.get("file_name"), str)
                or not isinstance(payload.get("section"), str)
                or not isinstance(payload.get("chunker"), str)
                or not isinstance(payload.get("text"), str)
                or not isinstance(payload.get("uploaded_at"), str)
                or not isinstance(payload.get("source_sha256"), str)
                or not isinstance(payload.get("is_citation"), bool)
                or any(payload.get(field) is not None and (isinstance(payload.get(field), bool) or not isinstance(payload.get(field), int)) for field in ("page", "page_end"))
            ):
                errors.append("PAYLOAD_TYPE_INVALID")
            try:
                if payload.get("text_digest") != _fingerprint(_safe_digest_value(payload.get("text"))):
                    errors.append("PAYLOAD_TEXT_DIGEST_MISMATCH")
            except Exception:
                errors.append("PAYLOAD_TEXT_DIGEST_MISMATCH")
            version = expected[document_id]["chunkers"].get(chunker, {})
            expected_payload_fields = {"payload_schema_version": version.get("payload_schema_version"), "anchor_digest": version.get("anchor_digest"), "chunker_config_fingerprint": version.get("chunker_config_fingerprint"), "embedding_config_fingerprint": version.get("embedding_config_fingerprint"), "model_config_fingerprint": version.get("model_config_fingerprint"), "llm_used": version.get("llm_used")}
            for field_name in expected_payload_fields:
                if payload.get(field_name) != expected_payload_fields[field_name]:
                    errors.append("BUNDLE_DIGEST_OR_CONFIG_MISMATCH")
            if payload.get("anchor_count") != version.get("anchor_count") or payload.get("unmapped_count") != version.get("unmapped_count"):
                errors.append("ANCHOR_METADATA_MISMATCH")
            if not isinstance(point.vector, Mapping) or "dense" not in point.vector or "sparse" not in point.vector:
                errors.append("DENSE_SPARSE_MISSING")
                continue
            dense = point.vector["dense"]
            dense_finite = isinstance(dense, (list, tuple)) and len(dense) == self.dense_dim and all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in dense)
            if not dense_finite:
                errors.append("DENSE_VECTOR_INVALID")
            sparse_indices, sparse_values = _sparse_components(point.vector["sparse"])
            if sparse_indices is None or sparse_values is None:
                errors.append("SPARSE_VECTOR_INVALID")
                sparse_indices, sparse_values = [], []
            try:
                sorted_unique = sparse_indices == sorted(sparse_indices) and len(sparse_indices) == len(set(sparse_indices))
            except (TypeError, ValueError):
                sorted_unique = False
            sparse_valid = (
                len(sparse_indices) == len(sparse_values)
                and sorted_unique
                and all(isinstance(index, int) and not isinstance(index, bool) and 0 <= index < SPARSE_DIM for index in sparse_indices)
                and all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in sparse_values)
            )
            if not sparse_valid:
                errors.append("SPARSE_VECTOR_INVALID")
            dense_digest = _fingerprint(_vector_digest_input(dense))
            sparse_digest = _fingerprint(_vector_digest_input({"indices": sparse_indices, "values": sparse_values}))
            collection_rows.append({"document_id": document_id, "chunker": chunker, "chunk_index": chunk_index, "point_id": point.id, "dense_dimension": len(dense) if isinstance(dense, (list, tuple)) else 0, "dense_finite": dense_finite, "dense_digest": dense_digest, "sparse_nnz": len(sparse_indices), "sparse_digest": sparse_digest, "payload_digest": _fingerprint(_payload_digest_projection(payload)), "anchor_digest": payload.get("anchor_digest"), "chunker_config_fingerprint": payload.get("chunker_config_fingerprint"), "embedding_config_fingerprint": payload.get("embedding_config_fingerprint"), "model_config_fingerprint": payload.get("model_config_fingerprint"), "llm_used": payload.get("llm_used")})
        for document_id, info in expected.items():
            for chunker in CHUNKERS:
                indices = sorted(by_doc_chunker.get((document_id, chunker), []))
                expected_version = info["chunkers"].get(chunker, {})
                expected_count = int(expected_version.get("chunk_count", 0))
                if indices != list(range(expected_count)) or len(indices) != len(set(indices)):
                    errors.append("CHUNK_INDEX_GAP")
        if len(points) != self._state.point_counts["total"]:
            errors.append("POINT_COUNT_MISMATCH")
        documents: List[Dict[str, Any]] = []
        for document_id, info in sorted(expected.items()):
            document = {"document_id": document_id, "media_type": info["media_type"], "source_sha256": info["source_sha256"], "indexed_source_sha256": info["indexed_source_sha256"], "parser_version": info["parser_version"]}
            for chunker in CHUNKERS:
                version = info["chunkers"][chunker]
                chunk_points = by_point.get((document_id, chunker), [])
                dense_values = [point.vector.get("dense") for point in chunk_points if isinstance(point.vector, Mapping)]
                sparse_values = [point.vector.get("sparse") for point in chunk_points if isinstance(point.vector, Mapping)]
                sparse_pairs: List[Dict[str, Any]] = []
                all_indices_sorted = True
                all_values_finite = True
                total_nnz = 0
                for sparse in sparse_values:
                    indices, values = _sparse_components(sparse)
                    if indices is None or values is None:
                        all_indices_sorted = False
                        all_values_finite = False
                        indices, values = [], []
                    try:
                        all_indices_sorted = all_indices_sorted and indices == sorted(indices) and len(indices) == len(set(indices))
                    except (TypeError, ValueError):
                        all_indices_sorted = False
                    all_values_finite = all_values_finite and all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in values)
                    total_nnz += len(indices)
                    sparse_pairs.append({"indices": indices, "values": values})
                dense_finite = all(isinstance(vector, (list, tuple)) and len(vector) == self.dense_dim and all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in vector) for vector in dense_values) and len(dense_values) == len(chunk_points)
                payload_digest = _fingerprint([_payload_digest_projection(point.payload) for point in chunk_points])
                text_digest = _fingerprint([_payload_digest_projection(point.payload).get("text_digest") for point in chunk_points])
                actual_dense_digest = _fingerprint(_vector_digest_input(dense_values))
                actual_sparse_digest = _fingerprint(_vector_digest_input(sparse_pairs))
                actual_anchor_digests = {point.payload.get("anchor_digest") for point in chunk_points}
                if payload_digest != version["payload_digest"] or text_digest != version["text_digest"] or actual_dense_digest != version["dense_vector_digest"] or actual_sparse_digest != version["sparse_vector_digest"] or actual_anchor_digests != {version["anchor_digest"]} or not version["llm_used"] and chunker == "v2":
                    errors.append("BUNDLE_DIGEST_OR_VECTOR_MISMATCH")
                document[chunker] = {"chunk_count": len(chunk_points), "point_ids": [point.id for point in chunk_points], "chunk_indexes": sorted(by_doc_chunker.get((document_id, chunker), [])), "payload_schema_version": version["payload_schema_version"], "chunker_config_fingerprint": version["chunker_config_fingerprint"], "embedding_config_fingerprint": version["embedding_config_fingerprint"], "model_config_fingerprint": version["model_config_fingerprint"], "llm_used": version["llm_used"], "anchor_count": version["anchor_count"], "unmapped_count": version["unmapped_count"], "dense": {"name": "dense", "dimension": self.dense_dim, "all_finite": dense_finite, "vector_digest": actual_dense_digest}, "sparse": {"name": "sparse", "point_count": len(sparse_values), "all_indices_sorted": all_indices_sorted, "all_values_finite": all_values_finite, "total_nnz": total_nnz, "vector_digest": actual_sparse_digest}, "payload_digest": payload_digest, "text_digest": text_digest, "anchor_digest": version["anchor_digest"]}
            documents.append(document)
        query_probes: Dict[str, Any] = {}
        if points:
            first = points[0]
            for vector_name in ("dense", "sparse"):
                vector = first.vector.get(vector_name) if isinstance(first.vector, Mapping) else None
                query_digest = _fingerprint(_vector_digest_input(vector))
                try:
                    results = self.index.search(self._state.candidate_collection, vector_name, vector, limit=3)
                    top_ids = [str(item.payload.get("document_id")) for item in results]
                    query_probes[vector_name] = {"query_digest": query_digest, "top_document_ids": top_ids, "candidate_hit": any(item in expected for item in top_ids)}
                    if not query_probes[vector_name]["candidate_hit"]:
                        errors.append(f"{vector_name.upper()}_QUERY_MISS")
                except Exception:
                    query_probes[vector_name] = {"query_digest": query_digest, "top_document_ids": [], "candidate_hit": False}
                    errors.append(f"{vector_name.upper()}_QUERY_FAILED")
        topology = self._observe_topology()
        topology_digest = topology.get("inventory_digest") or _fingerprint({"topology": "unavailable", "run_id": self._state.run_id})
        self._state.validated_topology_digest = topology_digest
        collection_fingerprint = _fingerprint(sorted(collection_rows, key=lambda item: (item["document_id"], item["chunker"], item["chunk_index"], item["point_id"])))
        first_document = next(iter(expected.values()), {})
        validation = {"schema_version": VALIDATION_SCHEMA, "run_id": self._state.run_id, "candidate_collection": self._state.candidate_collection, "topology_digest": topology_digest, "status": "failed" if errors else "passed", "documents": documents, "collection_totals": {"document_count": len(expected), "point_count": len(points), "v1_point_count": self._state.point_counts["v1"], "v2_point_count": self._state.point_counts["v2"]}, "config_fingerprints": {"embedding": _fingerprint({"model": EMBED_MODEL, "dimension": self.dense_dim}), "v1_chunker": first_document.get("chunkers", {}).get("v1", {}).get("chunker_config_fingerprint", _fingerprint({})), "v2_chunker": first_document.get("chunkers", {}).get("v2", {}).get("chunker_config_fingerprint", _fingerprint({})), "model": _fingerprint(CHUNK_V2_LLM_MODEL)}, "query_probes": query_probes, "collection_fingerprint": collection_fingerprint, "validated_at": _now(), "errors": sorted(set(errors))}
        if self._store:
            self._store.write_json("validation.json", validation)
        self._validate_instance("candidate-validation.schema.json", validation)
        artifact_sha256 = _sha256(self._store.directory / "validation.json") if self._store else _fingerprint(validation)
        self._state.new_fingerprint = {"sha256": collection_fingerprint, "point_count": len(points), "validation_artifact_sha256": artifact_sha256}
        if self._store:
            self._store.write(self._state)
        if validation["errors"]:
            raise RebuildError("CANDIDATE_VALIDATION_FAILED")
        self._stage_finalize_inputs(validation)
        self._transition("ready_to_switch", progress=85)
        return validation

    def _load_validation_artifact(self, *, require_candidate: bool = True) -> Dict[str, Any]:
        if self._state is None or self._store is None:
            raise RebuildError("RUN_STATE_INVALID")
        try:
            validation = self._store.read_json("validation.json")
            self._validate_instance("candidate-validation.schema.json", validation)
            topology_artifact = self._store.read_json("topology.json")
            self._validate_instance("topology-inventory.schema.json", topology_artifact)
        except RebuildError as error:
            raise RebuildError("VALIDATION_ARTIFACT_MISMATCH") from error
        if validation.get("run_id") != self._state.run_id or validation.get("candidate_collection") != self._state.candidate_collection:
            raise RebuildError("VALIDATION_ARTIFACT_MISMATCH")
        collection_fingerprint = validation.get("collection_fingerprint")
        if not isinstance(collection_fingerprint, str) or not collection_fingerprint:
            raise RebuildError("VALIDATION_ARTIFACT_MISMATCH")
        if self._state.new_fingerprint.get("sha256") != collection_fingerprint:
            raise RebuildError("VALIDATION_ARTIFACT_MISMATCH")
        if validation.get("status") != "passed" or validation.get("topology_digest") != self._state.validated_topology_digest:
            raise RebuildError("VALIDATION_ARTIFACT_MISMATCH")
        validation_path = self._store.directory / "validation.json"
        try:
            validation_sha256 = _sha256(validation_path)
        except RebuildError as error:
            raise RebuildError("VALIDATION_ARTIFACT_MISMATCH") from error
        if self._state.new_fingerprint.get("validation_artifact_sha256") != validation_sha256:
            raise RebuildError("VALIDATION_ARTIFACT_MISMATCH")
        if topology_artifact.get("inventory_digest") != validation.get("topology_digest"):
            raise RebuildError("VALIDATION_ARTIFACT_MISMATCH")
        topology_path = self._store.directory / "topology.json"
        if self._state.new_fingerprint.get("topology_artifact_sha256"):
            try:
                topology_sha256 = _sha256(topology_path)
            except RebuildError as error:
                raise RebuildError("VALIDATION_ARTIFACT_MISMATCH") from error
            if self._state.new_fingerprint.get("topology_artifact_sha256") != topology_sha256:
                raise RebuildError("VALIDATION_ARTIFACT_MISMATCH")
        fresh = topology_inventory(self.index, alias=self.alias, source_collection=self.source_collection, runtime_root=self.runtime_root, state_override=self._state.to_dict())
        observed_digest = (self._state.observed or {}).get("topology_digest")
        if not isinstance(observed_digest, str) or fresh.get("inventory_digest") != observed_digest:
            raise RebuildError("RESUME_TOPOLOGY_DRIFT")
        candidate_rows = {item["name"]: item for item in fresh.get("candidate_collections", ())}
        candidate = candidate_rows.get(self._state.candidate_collection)
        totals = validation.get("collection_totals") or {}
        if require_candidate and (candidate is None or int(candidate.get("point_count", -1)) != int(totals.get("point_count", -2))):
            raise RebuildError("VALIDATION_ARTIFACT_MISMATCH")
        if candidate is not None and int(candidate.get("point_count", -1)) != int(totals.get("point_count", -2)):
            raise RebuildError("VALIDATION_ARTIFACT_MISMATCH")
        if candidate is not None:
            try:
                recomputed_fingerprint, recomputed_count = self._recompute_candidate_fingerprint()
            except RebuildError as error:
                raise RebuildError("CANDIDATE_VALIDATION_FAILED") from error
            if recomputed_count != int(totals.get("point_count", -2)) or recomputed_fingerprint != collection_fingerprint:
                raise RebuildError("CANDIDATE_VALIDATION_FAILED")
        return validation

    def _persist_topology_artifact(self, inventory: Mapping[str, Any], validation: Mapping[str, Any]) -> None:
        if self._store is None or self._state is None:
            raise RebuildError("RUN_STATE_INVALID")
        path = self._store.directory / "topology.json"
        if path.exists():
            existing = self._store.read_json("topology.json")
            self._validate_instance("topology-inventory.schema.json", existing)
            if existing.get("inventory_digest") != validation.get("topology_digest"):
                raise RebuildError("TOPOLOGY_ARTIFACT_MISMATCH")
        else:
            if inventory.get("inventory_digest") != validation.get("topology_digest"):
                raise RebuildError("TOPOLOGY_ARTIFACT_MISMATCH")
            self._store.write_json("topology.json", dict(inventory))
        self._state.new_fingerprint["topology_artifact_sha256"] = _sha256(path)
        self._store.write(self._state)

    def _obsolete_manifests(self) -> List[Dict[str, str]]:
        """List only validated old manifest paths for the bundle cleanup set."""
        live_root = self.finalize_store.live_root / "manifests"
        if not live_root.exists():
            return []
        current = set(self._finalize_manifests)
        obsolete: List[Dict[str, str]] = []
        for path in sorted(live_root.glob("*/*.json")):
            if not path.is_file() or len(path.parts) < 2:
                continue
            document_id = path.parent.name
            chunker = path.stem
            if (document_id, chunker) in current:
                continue
            if chunker not in CHUNKERS:
                raise RebuildError("FINALIZE_OBSOLETE_MANIFEST_INVALID")
            try:
                digest = _sha256(path)
            except RebuildError as error:
                raise RebuildError("FINALIZE_OBSOLETE_MANIFEST_INVALID") from error
            obsolete.append({
                "document_id": document_id,
                "chunker": chunker,
                "live_path": f"data/kb/manifests/{document_id}/{chunker}.json",
                "sha256": digest,
            })
        return obsolete

    def _stage_finalize_inputs(self, validation: Mapping[str, Any]) -> None:
        """Persist runtime-only finalize inputs before alias/live mutation."""
        if not self._uses_default_finalizer:
            return
        if self._state is None:
            raise RebuildError("RUN_STATE_INVALID")
        collection_fingerprint = validation.get("collection_fingerprint")
        if not isinstance(collection_fingerprint, str) or not collection_fingerprint:
            raise RebuildError("FINALIZE_INPUT_INVALID")
        if not self._finalize_metadata or not self._finalize_manifests:
            raise RebuildError("FINALIZE_INPUT_MISSING")
        try:
            self.finalize_store.stage(
                self._state.run_id,
                candidate_collection=self._state.candidate_collection,
                metadata=self._finalize_metadata,
                manifests=self._finalize_manifests,
                collection_fingerprint=collection_fingerprint,
                alias_name=self.alias,
                obsolete_manifests=self._obsolete_manifests(),
            )
        except ManifestStoreError as error:
            raise RebuildError(error.code) from error

    def _finalize_bundle(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Stage and commit the run-scoped bundle, with marker written last."""
        run_id = str(payload.get("run_id") or "")
        candidate = str(payload.get("candidate_collection") or "")
        validation = payload.get("validation")
        if not run_id or not candidate or not isinstance(validation, Mapping):
            raise RebuildError("FINALIZE_INPUT_INVALID")
        collection_fingerprint = validation.get("collection_fingerprint")
        if not isinstance(collection_fingerprint, str) or not collection_fingerprint:
            raise RebuildError("FINALIZE_INPUT_INVALID")
        bundle_path = self.finalize_store.run_root(run_id) / "bundle.json"
        try:
            if not bundle_path.exists():
                raise RebuildError("FINALIZE_INPUT_MISSING")
            bundle = self.finalize_store.read_bundle(run_id)
            if (
                bundle.get("run_id") != run_id
                or bundle.get("alias_name") != self.alias
                or bundle.get("candidate_collection") != candidate
                or bundle.get("collection_fingerprint") != collection_fingerprint
            ):
                raise RebuildError("FINALIZE_INPUT_MISMATCH")
            marker = self.finalize_store.commit(run_id)
            verified = self.finalize_store.require_generation(finalize_pending=True)
        except RebuildError:
            raise
        except ManifestStoreError as error:
            raise RebuildError(error.code) from error
        except Exception as error:
            raise RebuildError(getattr(error, "code", "FINALIZE_FAILED")) from error
        if (
            verified.get("run_id") != run_id
            or verified.get("alias_name") != self.alias
            or verified.get("alias_target") != candidate
            or verified.get("collection_fingerprint") != collection_fingerprint
            or marker != verified
        ):
            raise RebuildError("FINALIZE_COMMIT_VERIFY_FAILED")
        return verified

    def _invoke_finalize_and_commit(self, validation: Mapping[str, Any]) -> None:
        if self._state is None or self._store is None:
            raise RebuildError("RUN_STATE_INVALID")
        finalizer_result = self._action(
            "finalize",
            "finalizer",
            lambda: self.finalizer({
                "run_id": self._state.run_id,
                "candidate_collection": self._state.candidate_collection,
                "validation": dict(validation),
            }),
        )
        if self._uses_default_finalizer:
            if not isinstance(finalizer_result, Mapping):
                raise RebuildError("FINALIZE_COMMIT_VERIFY_FAILED")
            if (
                finalizer_result.get("run_id") != self._state.run_id
                or finalizer_result.get("alias_target") != self._state.candidate_collection
                or finalizer_result.get("collection_fingerprint") != validation.get("collection_fingerprint")
            ):
                raise RebuildError("FINALIZE_COMMIT_VERIFY_FAILED")
        commit = {
            "schema_version": "candidate-commit-v1",
            "run_id": self._state.run_id,
            "candidate_collection": self._state.candidate_collection,
            "collection_fingerprint": validation.get("collection_fingerprint"),
            "committed_at": _now(),
        }
        self._store.write_json("commit.json", commit)
        stored_commit = self._store.read_json("commit.json")
        if stored_commit != commit or stored_commit.get("collection_fingerprint") != validation.get("collection_fingerprint"):
            raise RebuildError("FINALIZE_COMMIT_VERIFY_FAILED")

    def _switch_and_finalize(self, validation: Mapping[str, Any]) -> None:
        if self._state is None:
            raise RebuildError("RUN_STATE_INVALID")
        collection_fingerprint = validation.get("collection_fingerprint")
        if not isinstance(collection_fingerprint, str) or not collection_fingerprint or self._state.new_fingerprint.get("sha256") != collection_fingerprint:
            raise RebuildError("VALIDATION_ARTIFACT_MISMATCH")
        self._transition("switching", progress=88)
        inventory = topology_inventory(self.index, alias=self.alias, source_collection=self.source_collection, runtime_root=self.runtime_root, state_override=self._state.to_dict())
        self._persist_topology_artifact(inventory, validation)
        matrix = inventory["matrix"]
        if not matrix["safe_to_switch"]:
            raise RebuildError("INDEX_TOPOLOGY_AMBIGUOUS")
        current = self.index.alias_target(self.alias)
        if current:
            prior_intent = dict(self._state.intent or {})
            expected_previous = prior_intent.get("previous_target") or self._state.previous_target
            if current != self._state.candidate_collection and expected_previous and current != expected_previous:
                raise RebuildError("RETIRE_TOPOLOGY_MISMATCH")
            if current == self._state.candidate_collection and not expected_previous:
                raise RebuildError("RETIRE_TOPOLOGY_MISMATCH")
            self._action("switch_alias", "create_alias", lambda: self.index.create_alias(self.alias, self._state.candidate_collection, replace=True))
            retire_target = current
            if current == self._state.candidate_collection:
                retire_target = str(expected_previous)
            if retire_target != self._state.candidate_collection and any(item.get("name") == retire_target for item in inventory["collections"]):
                self._retire_authorized(retire_target, action="retire_current_collection")
        elif any(item.get("name") == self.source_collection for item in inventory["collections"]):
            self._retire_authorized(self.source_collection, action="retire_physical_current")
            self._action("create_default_alias", "create_alias", lambda: self.index.create_alias(self.alias, self._state.candidate_collection))
        else:
            self._action("create_default_alias", "create_alias", lambda: self.index.create_alias(self.alias, self._state.candidate_collection))
        self._transition("finalizing", progress=94)
        try:
            self._invoke_finalize_and_commit(validation)
        except Exception as error:
            self._transition("finalize_pending", error=getattr(error, "code", "FINALIZE_FAILED"))
            raise RebuildError(getattr(error, "code", "FINALIZE_FAILED")) from error
        self._state.error_code = None
        self._transition("completed", progress=100)

    def run(self, *, dry_run: bool = True, confirm_replace: bool = False) -> Dict[str, Any]:
        state = self._new_state(dry_run=dry_run)
        self._state = state
        before_snapshot = self._preflight_snapshot()
        initial_inventory = topology_inventory(
            self.index,
            alias=self.alias,
            source_collection=self.source_collection,
            runtime_root=self.runtime_root,
        )
        state.initial_topology_digest = str(initial_inventory["inventory_digest"])
        state.previous_target = next(
            (item["target"] for item in initial_inventory.get("aliases", ()) if item["name"] == self.alias),
            None,
        )
        if state.previous_target is None and initial_inventory.get("matrix", {}).get("default_state") == "physical":
            state.previous_target = self.source_collection
        parsed, orphan = self._preflight()
        state.document_counts["authoritative"] = len(parsed)
        state.document_counts["orphan"] = len(orphan)
        if dry_run:
            after_snapshot = self._preflight_snapshot()
            if before_snapshot[0] is not None or after_snapshot[0] is not None or before_snapshot != after_snapshot:
                raise RebuildError("PREFLIGHT_STALE")
            state.progress = 100
            state.status = "completed"
            return {**state.to_dict(), "orphan_files": orphan, "topology": topology_inventory(self.index, alias=self.alias, source_collection=self.source_collection, runtime_root=self.runtime_root)}
        if not confirm_replace:
            raise RebuildError("CONFIRM_REPLACE_REQUIRED")
        if (self.runtime_root / state.run_id).exists():
            raise RebuildError("RUN_ID_COLLISION")
        self._assert_new_build_topology(topology_inventory(self.index, alias=self.alias, source_collection=self.source_collection, runtime_root=self.runtime_root))
        self._lock = _ExclusiveLock(self.runtime_root, run_id=state.run_id, command="confirm-replace")
        self._lock.acquire()
        self._store = _RuntimeStore(self.runtime_root, state.run_id)
        try:
            if before_snapshot[1] != topology_inventory(self.index, alias=self.alias, source_collection=self.source_collection, runtime_root=self.runtime_root)["inventory_digest"]:
                raise RebuildError("PREFLIGHT_STALE")
            self._store.initialize(state)
            self._bind_port(state.candidate_collection)
            expected = self._build(parsed)
            validation = self._validate(expected)
            self._switch_and_finalize(validation)
            return {**state.to_dict(), "validation": validation, "orphan_files": orphan}
        except Exception as raw_error:
            error = raw_error if isinstance(raw_error, RebuildError) else RebuildError(getattr(raw_error, "code", "REBUILD_FAILED"))
            if self._state.status not in {"switching", "finalizing", "finalize_pending", "completed"}:
                self._transition("failed", error=error.code)
                try:
                    self._action("cleanup_unvalidated_candidate", "delete_collection", lambda: self.index.delete_collection(self._state.candidate_collection))
                except Exception:
                    self._transition("cleanup_pending", error="CLEANUP_FAILED")
            raise error from raw_error
        finally:
            if self._lock:
                self._lock.release()

    def _resume_state(self, run_id: str) -> RunState:
        store = _RuntimeStore(self.runtime_root, _safe_id(run_id))
        raw = store.read()
        state = RunState(run_id=raw["run_id"], source_collection=raw.get("source_collection"), candidate_collection=raw["candidate_collection"], dry_run=bool(raw.get("dry_run")), status=raw["status"], progress=int(raw.get("progress", 0)), document_counts=dict(raw.get("document_counts") or {}), point_counts=dict(raw.get("point_counts") or {}), new_fingerprint=dict(raw.get("new_fingerprint") or {}), error_code=raw.get("error_code"), intent=raw.get("intent"), observed=raw.get("observed"), previous_target=raw.get("previous_target"), initial_topology_digest=raw.get("initial_topology_digest"), validated_topology_digest=raw.get("validated_topology_digest"))
        self._state, self._store = state, store
        self._bind_port(state.candidate_collection)
        return state

    def resume_switch(self, run_id: str, *, recover_stale_lock: bool = False) -> Dict[str, Any]:
        state = self._resume_state(run_id)
        if state.status not in {"ready_to_switch", "switching"}:
            raise RebuildError("RESUME_SWITCH_NOT_ALLOWED")
        validation = self._load_validation_artifact()
        self._lock = _ExclusiveLock(self.runtime_root, run_id=state.run_id, command="resume-switch", recover_stale_run_id=state.run_id if recover_stale_lock else None, recovery_check=self._recovery_check)
        self._lock.acquire()
        try:
            self._switch_and_finalize(validation)
            return state.to_dict()
        finally:
            self._lock.release()

    def resume_finalize(self, run_id: str, *, recover_stale_lock: bool = False) -> Dict[str, Any]:
        state = self._resume_state(run_id)
        if state.status not in {"finalizing", "finalize_pending"}:
            raise RebuildError("RESUME_FINALIZE_NOT_ALLOWED")
        validation = self._load_validation_artifact()
        if self.index.alias_target(self.alias) != state.candidate_collection:
            raise RebuildError("FINALIZE_TOPOLOGY_MISMATCH")
        self._lock = _ExclusiveLock(self.runtime_root, run_id=state.run_id, command="resume-finalize", recover_stale_run_id=state.run_id if recover_stale_lock else None, recovery_check=self._recovery_check)
        self._lock.acquire()
        try:
            self._transition("finalizing", progress=max(state.progress, 94))
            try:
                commit_path = self._store.directory / "commit.json"
                if commit_path.exists():
                    commit = self._store.read_json("commit.json")
                    if commit.get("run_id") != state.run_id or commit.get("candidate_collection") != state.candidate_collection or commit.get("collection_fingerprint") != validation.get("collection_fingerprint"):
                        raise RebuildError("FINALIZE_COMMIT_VERIFY_FAILED")
                    if self._uses_default_finalizer:
                        try:
                            marker = self.finalize_store.require_generation(finalize_pending=True)
                        except ManifestStoreError as error:
                            raise RebuildError(error.code) from error
                        if marker.get("run_id") != state.run_id or marker.get("alias_target") != state.candidate_collection or marker.get("collection_fingerprint") != validation.get("collection_fingerprint"):
                            raise RebuildError("FINALIZE_COMMIT_VERIFY_FAILED")
                else:
                    self._invoke_finalize_and_commit(validation)
            except Exception as error:
                self._transition("finalize_pending", error=getattr(error, "code", "FINALIZE_FAILED"))
                raise RebuildError(getattr(error, "code", "FINALIZE_FAILED")) from error
            state.error_code = None
            self._transition("completed", progress=100)
            return state.to_dict()
        finally:
            self._lock.release()

    def cleanup_failed(self, run_id: str, *, recover_stale_lock: bool = False) -> Dict[str, Any]:
        state = self._resume_state(run_id)
        if state.status not in {"failed", "cleanup_pending"}:
            raise RebuildError("CLEANUP_NOT_ALLOWED")
        if (self._store.directory / "validation.json").exists():
            self._load_validation_artifact(require_candidate=False)
        else:
            topology_inventory(self.index, alias=self.alias, source_collection=self.source_collection, runtime_root=self.runtime_root, state_override=state.to_dict())
        self._lock = _ExclusiveLock(self.runtime_root, run_id=state.run_id, command="cleanup-failed", recover_stale_run_id=state.run_id if recover_stale_lock else None, recovery_check=self._recovery_check)
        self._lock.acquire()
        try:
            inventory = topology_inventory(self.index, alias=self.alias, source_collection=self.source_collection, runtime_root=self.runtime_root, state_override=state.to_dict())
            candidate = state.candidate_collection
            candidate_names = {item["name"] for item in inventory.get("candidate_collections", ())}
            referenced = {item["target"] for item in inventory.get("aliases", ())}
            if candidate in referenced or len(candidate_names - {candidate}) > 0:
                raise RebuildError("INDEX_TOPOLOGY_AMBIGUOUS")
            if candidate not in candidate_names:
                self._transition("cleaned", progress=100)
                return state.to_dict()
            self._action("cleanup_failed_candidate", "delete_collection", lambda: self.index.delete_collection(state.candidate_collection))
            fresh = topology_inventory(self.index, alias=self.alias, source_collection=self.source_collection, runtime_root=self.runtime_root, state_override=self._state.to_dict())
            if candidate in {item["name"] for item in fresh.get("candidate_collections", ())} or candidate in {item["target"] for item in fresh.get("aliases", ())}:
                raise RebuildError("CLEANUP_RESULT_UNKNOWN")
            self._transition("cleaned", progress=100)
            return state.to_dict()
        except Exception as error:
            self._transition("cleanup_pending", error=getattr(error, "code", "CLEANUP_FAILED"))
            raise RebuildError(getattr(error, "code", "CLEANUP_FAILED")) from error
        finally:
            self._lock.release()
