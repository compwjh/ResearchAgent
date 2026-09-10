"""Atomic InspectionManifest, claim and finalize persistence.

All paths are supplied explicitly by the caller (tests use ``tmp_path``).  The
store only writes manifest/runtime files; it never calls an embedder or a
Qdrant write method.  Finalize commit is deliberately a file protocol: the
caller must have already verified the candidate alias/topology.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker

from backend.app.knowledge_base.infrastructure.inspection import InspectionManifest

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_CHUNKERS = {"v1", "v2"}
_lock = threading.RLock()


def _with_manifest_lock(function):
    """Serialize generation publication with other manifest-store mutations."""

    @wraps(function)
    def locked(*args, **kwargs):
        with _lock:
            return function(*args, **kwargs)

    return locked

# JSON Schema carries these as ``x-*`` annotations; the runtime must enforce
# them on both publish and read because Draft 2020-12 has no byte-length rule.
MAX_MANIFEST_BYTES = 256 * 1024 * 1024
MAX_BLOCKS = 200_000
MAX_CHUNKS = 100_000
MAX_ANCHORS = 400_000
MAX_BLOCK_BYTES = 2 * 1024 * 1024
MAX_CHUNK_BYTES = 512 * 1024
MAX_ANCHOR_BYTES = 4 * 1024


class ManifestStoreError(RuntimeError):
    """Stable, path-free manifest/finalize failure."""

    def __init__(self, code: str, *, status: int = 409) -> None:
        self.code = code
        self.status = int(status)
        super().__init__(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, OverflowError) as error:
        raise ManifestStoreError("MANIFEST_SERIALIZATION_FAILED", status=500) from error


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical(value))


def _safe_id(value: Any, code: str = "INVALID_DOCUMENT_ID") -> str:
    result = str(value or "")
    if not _ID_RE.fullmatch(result):
        raise ManifestStoreError(code, status=400)
    return result


def _chunker(value: Any) -> str:
    result = str(value or "")
    if result not in _CHUNKERS:
        raise ManifestStoreError("CHUNKER_UNSUPPORTED", status=400)
    return result


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(str(directory), flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    except OSError as error:
        with suppress(OSError):
            temp_path.unlink(missing_ok=True)
        raise ManifestStoreError("ATOMIC_WRITE_FAILED", status=503) from error


def _read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestStoreError(code, status=503) from error
    if not isinstance(value, dict):
        raise ManifestStoreError(code, status=503)
    return value


def _schema(name: str) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[4] / "docs/sdd/plans/018/artifacts/task-03"
    try:
        return json.loads((root / name).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestStoreError("SCHEMA_UNAVAILABLE", status=503) from error


def _validate(schema_name: str, value: Mapping[str, Any], code: str) -> None:
    try:
        errors = list(Draft202012Validator(_schema(schema_name), format_checker=FormatChecker()).iter_errors(value))
    except ManifestStoreError:
        raise
    except Exception as error:
        raise ManifestStoreError("SCHEMA_UNAVAILABLE", status=503) from error
    if errors:
        raise ManifestStoreError(code)
    if schema_name != "inspection-manifest.schema.json":
        return
    try:
        serialized = _canonical(value)
        blocks = value.get("blocks", [])
        chunks = value.get("chunks", [])
        anchors = value.get("anchors", [])
        if len(serialized) > MAX_MANIFEST_BYTES:
            raise ManifestStoreError("PAYLOAD_TOO_LARGE", status=413)
        if len(blocks) > MAX_BLOCKS or len(chunks) > MAX_CHUNKS or len(anchors) > MAX_ANCHORS:
            raise ManifestStoreError("PAYLOAD_TOO_LARGE", status=413)
        if any(len(_canonical(item)) > MAX_BLOCK_BYTES for item in blocks):
            raise ManifestStoreError("PAYLOAD_TOO_LARGE", status=413)
        if any(len(_canonical(item)) > MAX_CHUNK_BYTES for item in chunks):
            raise ManifestStoreError("PAYLOAD_TOO_LARGE", status=413)
        if any(len(_canonical(item)) > MAX_ANCHOR_BYTES for item in anchors):
            raise ManifestStoreError("PAYLOAD_TOO_LARGE", status=413)
    except ManifestStoreError:
        raise
    except (TypeError, ValueError, UnicodeError, OverflowError) as error:
        raise ManifestStoreError("MANIFEST_SERIALIZATION_FAILED", status=500) from error


@dataclass(frozen=True)
class ManifestClaim:
    document_id: str
    chunker: str
    owner: str
    token: str
    expires_at: str
    path: Path


class InspectionManifestStore:
    """Publish and claim per-document manifests under an explicit root."""

    def __init__(self, live_root: Path, *, claim_root: Path | None = None) -> None:
        self.live_root = Path(live_root).resolve()
        self.manifest_root = self.live_root / "manifests"
        self.claim_root = Path(claim_root).resolve() if claim_root is not None else self.manifest_root

    def path(self, document_id: str, chunker: str) -> Path:
        return self.manifest_root / _safe_id(document_id) / f"{_chunker(chunker)}.json"

    def _claim_path(self, document_id: str, chunker: str) -> Path:
        return self.claim_root / _safe_id(document_id) / f"{_chunker(chunker)}.claim"

    def read(self, document_id: str, chunker: str) -> InspectionManifest:
        path = self.path(document_id, chunker)
        if self.tombstone_path(document_id, chunker).exists():
            raise ManifestStoreError("MANIFEST_TOMBSTONED", status=404)
        if not path.exists():
            raise ManifestStoreError("MANIFEST_NOT_FOUND", status=404)
        value = _read_json(path, "MANIFEST_INVALID")
        _validate("inspection-manifest.schema.json", value, "MANIFEST_INVALID")
        if value.get("document_id") != _safe_id(document_id) or value.get("chunker") != _chunker(chunker):
            raise ManifestStoreError("MANIFEST_ID_MISMATCH")
        return InspectionManifest(value)

    def write(self, manifest: InspectionManifest | Mapping[str, Any]) -> InspectionManifest:
        value = manifest.to_dict() if isinstance(manifest, InspectionManifest) else dict(manifest)
        _validate("inspection-manifest.schema.json", value, "MANIFEST_INVALID")
        document_id = _safe_id(value.get("document_id"))
        chunker = _chunker(value.get("chunker"))
        if self.tombstone_path(document_id, chunker).exists():
            raise ManifestStoreError("MANIFEST_TOMBSTONED", status=409)
        _atomic_bytes(self.path(document_id, chunker), json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
        return InspectionManifest(value)

    def claim(self, document_id: str, chunker: str, owner: str, *, lease_seconds: int = 300) -> ManifestClaim:
        document_id = _safe_id(document_id)
        chunker = _chunker(chunker)
        owner = str(owner or "").strip()
        if not owner or len(owner) > 128:
            raise ManifestStoreError("INVALID_CLAIM_OWNER", status=400)
        now = datetime.now(timezone.utc)
        expires = now.timestamp() + max(1, int(lease_seconds))
        path = self._claim_path(document_id, chunker)
        with _lock:
            if path.exists():
                current = _read_json(path, "MANIFEST_CLAIM_INVALID")
                if current.get("document_id") != document_id or current.get("chunker") != chunker:
                    raise ManifestStoreError("MANIFEST_CLAIM_INVALID")
                try:
                    active_until = datetime.fromisoformat(str(current.get("expires_at")).replace("Z", "+00:00")).timestamp()
                except (TypeError, ValueError):
                    raise ManifestStoreError("MANIFEST_CLAIM_INVALID") from None
                if active_until > now.timestamp():
                    raise ManifestStoreError("MANIFEST_CLAIMED", status=409)
                try:
                    path.unlink()
                    _fsync_directory(path.parent)
                except OSError as error:
                    raise ManifestStoreError("MANIFEST_CLAIM_INVALID", status=503) from error
            token = uuid.uuid4().hex
            expires_at = datetime.fromtimestamp(expires, timezone.utc).isoformat()
            value = {
                "schema_version": "inspection-claim-v1",
                "document_id": document_id,
                "chunker": chunker,
                "owner": owner,
                "token": token,
                "pid": os.getpid(),
                "started_at": now.isoformat(),
                "attempt": 1,
                "heartbeat": now.isoformat(),
                "expires_at": expires_at,
            }
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))
                    stream.flush()
                    os.fsync(stream.fileno())
                _fsync_directory(path.parent)
            except FileExistsError as error:
                raise ManifestStoreError("MANIFEST_CLAIMED", status=409) from error
            except OSError as error:
                raise ManifestStoreError("MANIFEST_CLAIM_FAILED", status=503) from error
            return ManifestClaim(document_id, chunker, owner, token, expires_at, path)

    def release(self, claim: ManifestClaim) -> None:
        with _lock:
            if claim.path != self._claim_path(claim.document_id, claim.chunker):
                raise ManifestStoreError("MANIFEST_CLAIM_INVALID")
            current = _read_json(claim.path, "MANIFEST_CLAIM_INVALID")
            if (
                current.get("document_id") != claim.document_id
                or current.get("chunker") != claim.chunker
                or current.get("token") != claim.token
                or current.get("owner") != claim.owner
            ):
                raise ManifestStoreError("MANIFEST_CLAIM_OWNER_MISMATCH", status=409)
            try:
                claim.path.unlink()
                _fsync_directory(claim.path.parent)
            except OSError as error:
                raise ManifestStoreError("MANIFEST_CLAIM_RELEASE_FAILED", status=503) from error

    def tombstone_path(self, document_id: str, chunker: str) -> Path:
        del chunker
        return self.live_root / "tombstones" / f"{_safe_id(document_id)}.json"

    def tombstone(self, document_id: str, chunker: str, *, reason: str, owner: str) -> Path:
        document_id = _safe_id(document_id)
        chunker = _chunker(chunker)
        value = {
            "schema_version": "inspection-tombstone-v1",
            "document_id": document_id,
            "chunker": chunker,
            "reason": str(reason or "deleted")[:128],
            "owner": str(owner or "")[:128],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path = self.tombstone_path(document_id, chunker)
        if path.exists():
            current = _read_json(path, "TOMBSTONE_INVALID")
            if current.get("document_id") != document_id or current.get("chunker") not in _CHUNKERS:
                raise ManifestStoreError("TOMBSTONE_INVALID")
            if current.get("owner") != value["owner"]:
                raise ManifestStoreError("TOMBSTONE_OWNER_MISMATCH", status=409)
            if isinstance(current.get("created_at"), str):
                value["created_at"] = current["created_at"]
            # Same owner retries are idempotent and preserve the original
            # timestamp; only finish removing a manifest if one remains.  The
            # tombstone file is shared by v1/v2, so a same-owner call for the
            # other chunker may still need to remove that manifest.
            manifest = self.path(document_id, chunker)
            if current.get("chunker") == chunker and not manifest.exists():
                FinalizeBundleStore(self.live_root.parents[1]).refresh_live_digests()
                return path
        _atomic_bytes(path, json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        manifest = self.path(document_id, chunker)
        try:
            manifest.unlink(missing_ok=True)
            if manifest.parent.exists():
                _fsync_directory(manifest.parent)
        except OSError as error:
            raise ManifestStoreError("TOMBSTONE_PENDING", status=503) from error
        # A committed generation covers the live manifest digest.  Keep the
        # marker usable after a successful delete instead of leaving a
        # transient tombstone-induced hash mismatch for the next request.
        FinalizeBundleStore(self.live_root.parents[1]).refresh_live_digests()
        return path


class FinalizeBundleStore:
    """Stage and idempotently publish FinalizeBundleV1 plus marker-last."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime_root = self.root / ".sdd/runtime/spec-018/rebuild"
        self.live_root = self.root / "data/kb"

    def run_root(self, run_id: str) -> Path:
        return self.runtime_root / _safe_id(run_id, "INVALID_RUN_ID") / "finalize"

    def _bundle_path(self, run_id: str) -> Path:
        return self.run_root(run_id) / "bundle.json"

    def stage(
        self,
        run_id: str,
        *,
        candidate_collection: str,
        metadata: Sequence[Mapping[str, Any]],
        manifests: Mapping[tuple[str, str], InspectionManifest | Mapping[str, Any]],
        collection_fingerprint: str,
        alias_name: str = "papers",
        obsolete_manifests: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        run_id = _safe_id(run_id, "INVALID_RUN_ID")
        if not re.fullmatch(r"papers_rebuild_[A-Za-z0-9][A-Za-z0-9._-]{0,127}", candidate_collection):
            raise ManifestStoreError("INVALID_CANDIDATE_COLLECTION", status=400)
        if alias_name != "papers" or not re.fullmatch(r"[0-9a-f]{64}", collection_fingerprint):
            raise ManifestStoreError("FINALIZE_INPUT_INVALID", status=400)
        root = self.run_root(run_id)
        metadata_path = root / "metadata.json"
        metadata_bytes = json.dumps(list(metadata), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        _atomic_bytes(metadata_path, metadata_bytes)
        entries: list[dict[str, Any]] = []
        for key, item in sorted(manifests.items(), key=lambda pair: (pair[0][0], pair[0][1])):
            document_id = _safe_id(key[0])
            chunker = _chunker(key[1])
            value = item.to_dict() if isinstance(item, InspectionManifest) else dict(item)
            _validate("inspection-manifest.schema.json", value, "MANIFEST_INVALID")
            if value.get("document_id") != document_id or value.get("chunker") != chunker:
                raise ManifestStoreError("MANIFEST_ID_MISMATCH")
            staged_path = root / "manifests" / document_id / f"{chunker}.json"
            manifest_bytes = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
            _atomic_bytes(staged_path, manifest_bytes)
            entries.append({
                "document_id": document_id,
                "chunker": chunker,
                "staged_path": f".sdd/runtime/spec-018/rebuild/{run_id}/finalize/manifests/{document_id}/{chunker}.json",
                "live_path": f"data/kb/manifests/{document_id}/{chunker}.json",
                "sha256": _sha256_bytes(manifest_bytes),
            })
        bundle = {
            "schema_version": "finalize-bundle-v1",
            "run_id": run_id,
            "candidate_collection": candidate_collection,
            "alias_name": alias_name,
            "collection_fingerprint": collection_fingerprint,
            "metadata_staged_path": f".sdd/runtime/spec-018/rebuild/{run_id}/finalize/metadata.json",
            "metadata_staged_sha256": _sha256_bytes(metadata_bytes),
            "manifests": entries,
            "obsolete_manifests": [dict(item) for item in obsolete_manifests],
        }
        _validate("finalize-bundle.schema.json", {**bundle, "bundle_sha256": _sha256_json(bundle)}, "FINALIZE_BUNDLE_INVALID")
        bundle["bundle_sha256"] = _sha256_json(bundle)
        _atomic_bytes(self._bundle_path(run_id), json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
        return bundle

    def _read_bundle(self, run_id: str) -> dict[str, Any]:
        bundle = _read_json(self._bundle_path(run_id), "FINALIZE_BUNDLE_UNAVAILABLE")
        _validate("finalize-bundle.schema.json", bundle, "FINALIZE_BUNDLE_INVALID")
        expected = bundle.get("bundle_sha256")
        actual = _sha256_json({key: value for key, value in bundle.items() if key != "bundle_sha256"})
        if expected != actual:
            raise ManifestStoreError("FINALIZE_BUNDLE_HASH_MISMATCH")
        return bundle

    def read_bundle(self, run_id: str) -> dict[str, Any]:
        """Read and verify a staged bundle without touching live files."""
        return self._read_bundle(run_id)

    def _live_manifests_digest(self) -> str:
        entries: list[dict[str, str]] = []
        manifest_root = self.live_root / "manifests"
        if manifest_root.exists():
            for path in sorted(manifest_root.glob("*/*.json")):
                if not path.is_file():
                    continue
                relative = path.relative_to(self.root).as_posix()
                try:
                    digest = _sha256_bytes(path.read_bytes())
                except OSError as error:
                    raise ManifestStoreError("INDEX_FINALIZE_REQUIRED", status=503) from error
                entries.append({"live_path": relative, "sha256": digest})
        return _sha256_json(entries)

    def refresh_live_digests(
        self,
        *,
        expected_destination_collection: str | None = None,
    ) -> dict[str, Any] | None:
        """Atomically refresh marker digests after an authorized metadata change.

        Reindex progress and document deletion are ordinary, generation-bound
        state transitions.  They update ``papers.json`` or tombstones after a
        finalize commit, so retaining the old marker hash would make a valid
        generation fail closed forever.  This method only operates when an
        existing marker is present and never creates one or changes topology.
        """
        with _lock:
            marker_path = self.live_root / "index-generation.json"
            if not marker_path.exists():
                if expected_destination_collection is not None:
                    raise ManifestStoreError("INDEX_GENERATION_DRIFT")
                return None
            marker = _read_json(marker_path, "INDEX_FINALIZE_REQUIRED")
            _validate("index-generation.schema.json", marker, "INDEX_FINALIZE_REQUIRED")
            if (
                expected_destination_collection is not None
                and marker.get("alias_target") != expected_destination_collection
            ):
                raise ManifestStoreError("INDEX_GENERATION_DRIFT")
            try:
                metadata_hash = _sha256_bytes((self.live_root / "papers.json").read_bytes())
            except OSError as error:
                raise ManifestStoreError("INDEX_FINALIZE_REQUIRED", status=503) from error
            marker["metadata_sha256"] = metadata_hash
            marker["manifests_digest"] = self._live_manifests_digest()
            _validate("index-generation.schema.json", marker, "GENERATION_MARKER_INVALID")
            _atomic_bytes(
                marker_path,
                json.dumps(marker, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
            )
            return self.require_generation()

    @_with_manifest_lock
    def commit(self, run_id: str, *, allow_replace: bool = False) -> dict[str, Any]:
        """Publish a staged bundle after the caller proves index topology.

        ``allow_replace`` is deliberately explicit.  A direct file-store
        caller may retry the same run, but may not replace a live generation
        merely because it has a different bundle.  CandidateRebuildService
        sets it only after its Qdrant alias/candidate/topology proof.
        """
        bundle = self._read_bundle(run_id)
        root = self.run_root(run_id)
        marker_path = self.live_root / "index-generation.json"
        if marker_path.exists():
            # A valid marker plus matching live files is already committed.  Do
            # not rewrite metadata, manifests, or the marker during resume.
            marker = _read_json(marker_path, "INDEX_FINALIZE_REQUIRED")
            _validate("index-generation.schema.json", marker, "INDEX_FINALIZE_REQUIRED")
            if (
                marker.get("run_id") == bundle["run_id"]
                and marker.get("alias_name") == bundle["alias_name"]
                and marker.get("alias_target") == bundle["candidate_collection"]
                and marker.get("bundle_sha256") == bundle["bundle_sha256"]
                and marker.get("collection_fingerprint") == bundle["collection_fingerprint"]
            ):
                # Same-run retries must not rewrite live files.  The
                # generation check below also keeps this path fail-closed if
                # a live artifact was changed after the original commit.
                return self.require_generation(finalize_pending=True)
            if not allow_replace:
                # A mismatch is not evidence that this bundle owns the live
                # index.  Keep direct/resume-finalize store calls fail-closed;
                # only the orchestrator can authorize a next-generation
                # replacement after checking the actual index topology.
                raise ManifestStoreError("INDEX_FINALIZE_REQUIRED", status=503)
            # A marker for an older generation is expected during a later
            # rebuild once CandidateRebuildService has proved the Qdrant
            # alias, candidate and topology immediately before calling this
            # file-only commit.
        metadata_path = root / "metadata.json"
        try:
            metadata_bytes = metadata_path.read_bytes()
        except OSError as error:
            raise ManifestStoreError("FINALIZE_STAGED_MISSING", status=503) from error
        if _sha256_bytes(metadata_bytes) != bundle["metadata_staged_sha256"]:
            raise ManifestStoreError("FINALIZE_STAGED_HASH_MISMATCH")

        # Verify all staged files before touching any live file.  A late
        # manifest mismatch must not leave a mixture of old and new live
        # artifacts behind the marker.
        staged_entries: list[tuple[dict[str, Any], bytes]] = []
        for entry in bundle["manifests"]:
            staged = self.root / entry["staged_path"]
            try:
                data = staged.read_bytes()
            except OSError as error:
                raise ManifestStoreError("FINALIZE_STAGED_MISSING", status=503) from error
            if _sha256_bytes(data) != entry["sha256"]:
                raise ManifestStoreError("FINALIZE_STAGED_HASH_MISMATCH")
            staged_entries.append((entry, data))

        # Validate the cleanup set before publishing too.  A missing obsolete
        # file is already clean; an existing one must still have the digest
        # recorded by this bundle, otherwise topology changed underneath the
        # finalize operation and we stop fail-closed.
        staged_live_paths = {str(entry["live_path"]) for entry, _data in staged_entries}
        obsolete_entries: list[tuple[dict[str, Any], Path]] = []
        for obsolete in bundle.get("obsolete_manifests", ()):
            path_value = str(obsolete.get("live_path") or "")
            if not path_value.startswith("data/kb/manifests/") or path_value in staged_live_paths:
                continue
            path = self.root / path_value
            try:
                if path.exists():
                    if _sha256_bytes(path.read_bytes()) != obsolete.get("sha256"):
                        raise ManifestStoreError("FINALIZE_CLEANUP_HASH_MISMATCH")
                    obsolete_entries.append((obsolete, path))
            except ManifestStoreError:
                raise
            except OSError as error:
                raise ManifestStoreError("FINALIZE_CLEANUP_PENDING", status=503) from error

        _atomic_bytes(self.live_root / "papers.json", metadata_bytes)
        try:
            if _sha256_bytes((self.live_root / "papers.json").read_bytes()) != bundle["metadata_staged_sha256"]:
                raise ManifestStoreError("FINALIZE_LIVE_HASH_MISMATCH")
        except ManifestStoreError:
            raise
        except OSError as error:
            raise ManifestStoreError("FINALIZE_LIVE_HASH_MISMATCH", status=503) from error
        live_entries: list[dict[str, str]] = []
        for entry, data in staged_entries:
            live = self.root / entry["live_path"]
            _atomic_bytes(live, data)
            if _sha256_bytes(live.read_bytes()) != entry["sha256"]:
                raise ManifestStoreError("FINALIZE_LIVE_HASH_MISMATCH")
            live_entries.append({"live_path": entry["live_path"], "sha256": entry["sha256"]})
        for _obsolete, path in obsolete_entries:
            try:
                path.unlink(missing_ok=True)
                if path.parent.exists():
                    _fsync_directory(path.parent)
            except ManifestStoreError:
                raise
            except OSError as error:
                raise ManifestStoreError("FINALIZE_CLEANUP_PENDING", status=503) from error
        # Include every remaining live manifest, not only newly staged entries;
        # this keeps the marker's digest identical to require_generation().
        manifests_digest = self._live_manifests_digest()
        marker = {
            "schema_version": "index-generation-v1",
            "run_id": bundle["run_id"],
            "alias_name": bundle["alias_name"],
            "alias_target": bundle["candidate_collection"],
            "bundle_sha256": bundle["bundle_sha256"],
            "collection_fingerprint": bundle["collection_fingerprint"],
            "metadata_sha256": _sha256_bytes((self.live_root / "papers.json").read_bytes()),
            "manifests_digest": manifests_digest,
            "committed_at": datetime.now(timezone.utc).isoformat(),
        }
        _validate("index-generation.schema.json", marker, "GENERATION_MARKER_INVALID")
        _atomic_bytes(self.live_root / "index-generation.json", json.dumps(marker, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
        return marker

    def resume_finalize(self, run_id: str) -> dict[str, Any]:
        return self.commit(run_id)

    def require_generation(self, *, finalize_pending: bool = False) -> dict[str, Any]:
        marker_path = self.live_root / "index-generation.json"
        if not marker_path.exists():
            code = "INDEX_FINALIZE_REQUIRED" if finalize_pending else "INDEX_REBUILD_REQUIRED"
            raise ManifestStoreError(code, status=503 if finalize_pending else 409)
        marker = _read_json(marker_path, "INDEX_FINALIZE_REQUIRED")
        _validate("index-generation.schema.json", marker, "INDEX_FINALIZE_REQUIRED")
        try:
            metadata_hash = _sha256_bytes((self.live_root / "papers.json").read_bytes())
        except OSError as error:
            raise ManifestStoreError("INDEX_FINALIZE_REQUIRED", status=503) from error
        if metadata_hash != marker.get("metadata_sha256"):
            raise ManifestStoreError("INDEX_FINALIZE_REQUIRED", status=503)
        if self._live_manifests_digest() != marker.get("manifests_digest"):
            raise ManifestStoreError("INDEX_FINALIZE_REQUIRED", status=503)
        return marker


__all__ = ["FinalizeBundleStore", "InspectionManifestStore", "ManifestClaim", "ManifestStoreError"]
