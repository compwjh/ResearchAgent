"""Full-text evidence projection for Spec029.

This is deliberately a small application seam around the existing knowledge
base retrieval and inspection contracts.  It never embeds, chunks, writes
Qdrant, or reads a client supplied document path.  A hit becomes evidence only
after its deterministic chunk id is found in the current inspection manifest.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from backend.app.knowledge_base.application import create_manifest_store, hybrid_search
from backend.app.knowledge_base.infrastructure.index import point_id
from backend.app.platform.config import KB_DIR
from backend.app.research.domain.models import EvidenceUpgrade

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EvidenceUpgradeError(ValueError):
    """Stable errors at the Research↔knowledge-base evidence boundary."""

    _STATUS = {
        "TASK_NOT_FOUND": 404,
        "DOCUMENT_NOT_APPROVED": 409,
        "INVALID_REQUEST": 400,
        "EVIDENCE_INSUFFICIENT": 409,
        "EVIDENCE_UNAVAILABLE": 409,
        "INDEX_REVALIDATION_REQUIRED": 409,
    }

    def __init__(self, code: str, message: str, *, status: int | None = None) -> None:
        self.code = code
        self.http_status = int(status or self._STATUS.get(code, 409))
        self.message = message
        super().__init__(message)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "to_dict"):
        converted = value.to_dict()
        if isinstance(converted, Mapping):
            return converted
    return {}


def _hit_value(hit: Any, name: str, default: Any = None) -> Any:
    if isinstance(hit, Mapping):
        return hit.get(name, default)
    return getattr(hit, name, default)


class EvidenceUpgradeService:
    """Upgrade claims using only approved, currently indexed KB documents."""

    def __init__(
        self,
        store: Any,
        *,
        search: Callable[..., Sequence[Any]] | None = None,
        manifest_reader: Callable[[str, str], Mapping[str, Any]] | None = None,
        generation_reader: Callable[[], Any] | None = None,
    ) -> None:
        self.store = store
        self.search = search or hybrid_search
        manifest_store = create_manifest_store(live_root=KB_DIR)
        self._manifest_reader = manifest_reader or (
            lambda document_id, chunker: manifest_store.read(document_id, chunker).to_dict()
        )
        self._generation_reader = generation_reader or manifest_store.require_generation

    @staticmethod
    def _document_ids(values: Sequence[str] | None) -> tuple[str, ...]:
        result: list[str] = []
        for value in values or ():
            document_id = str(value or "").strip()
            if document_id and document_id not in result:
                result.append(document_id)
        return tuple(result)

    def _allowlist(self, task_id: str, document_ids: Sequence[str] | None) -> tuple[str, ...]:
        links = self.store.list_document_links(task_id)
        approved: set[str] = set()
        for link in links:
            value = _as_mapping(link)
            document_id = value.get("document_id", getattr(link, "document_id", None))
            status = value.get("status", getattr(link, "status", ""))
            if document_id and str(status) in {"completed", "indexed", "available"}:
                approved.add(str(document_id))
        requested = self._document_ids(document_ids)
        if not requested:
            raise EvidenceUpgradeError("INVALID_REQUEST", "document_ids 不能为空")
        if not set(requested).issubset(approved):
            raise EvidenceUpgradeError("DOCUMENT_NOT_APPROVED", "全文检索文档不在已确认导入清单中")
        return requested

    def _generation(self) -> str:
        try:
            value = self._generation_reader()
        except Exception as error:
            raise EvidenceUpgradeError("INDEX_REVALIDATION_REQUIRED", "知识库索引代次不可用") from error
        payload = _as_mapping(value)
        generation = payload.get("run_id") or payload.get("generation") or payload.get("index_generation")
        if generation is None and isinstance(value, str):
            generation = value
        generation = str(generation or "").strip()
        if not generation:
            raise EvidenceUpgradeError("INDEX_REVALIDATION_REQUIRED", "知识库索引代次不可用")
        return generation

    def _manifest(self, document_id: str, chunker: str) -> Mapping[str, Any]:
        manifest = _as_mapping(self._manifest_reader(document_id, chunker))
        if not manifest or manifest.get("document_id") != document_id:
            raise EvidenceUpgradeError("EVIDENCE_UNAVAILABLE", "全文检查清单不可用")
        source_hash = str(manifest.get("source_sha256") or "").lower()
        indexed_hash = str(manifest.get("indexed_source_sha256") or "").lower()
        if not _SHA256.fullmatch(source_hash) or indexed_hash != source_hash:
            raise EvidenceUpgradeError("EVIDENCE_UNAVAILABLE", "全文来源哈希未验证")
        if manifest.get("source_hash_state") != "verified":
            raise EvidenceUpgradeError("EVIDENCE_UNAVAILABLE", "全文来源哈希未验证")
        if manifest.get("status") in {"failed", "building", "indexing"}:
            raise EvidenceUpgradeError("EVIDENCE_UNAVAILABLE", "全文索引尚未完成")
        return manifest

    @staticmethod
    def _validated_hits(hits: Sequence[Any], allowlist: tuple[str, ...], chunker: str, manifests: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for hit in hits:
            document_id = str(_hit_value(hit, "document_id", _hit_value(hit, "paper_id", "")) or "")
            if document_id not in allowlist:
                continue
            hit_chunker = str(_hit_value(hit, "chunker", chunker) or chunker)
            if hit_chunker != chunker:
                continue
            raw_index = _hit_value(hit, "chunk_index")
            if isinstance(raw_index, bool):
                continue
            try:
                chunk_index = int(raw_index)
            except (TypeError, ValueError):
                continue
            if chunk_index < 0:
                continue
            manifest = manifests.get(document_id)
            if manifest is None:
                continue
            chunks = manifest.get("chunks")
            if not isinstance(chunks, list):
                continue
            chunk = next((item for item in chunks if isinstance(item, Mapping) and item.get("chunk_index") == chunk_index), None)
            if chunk is None or not isinstance(chunk.get("text"), str):
                continue
            # Retrieval payload is untrusted.  Require it to be the exact
            # indexed chunk before recording a locator; never persist its text.
            hit_text = _hit_value(hit, "text", "")
            if not isinstance(hit_text, str) or hit_text != chunk["text"]:
                continue
            page = chunk.get("page", _hit_value(hit, "page"))
            page_end = chunk.get("page_end", _hit_value(hit, "page_end"))
            if not isinstance(page, int) or isinstance(page, bool) or page < 1:
                continue
            if not isinstance(page_end, int) or isinstance(page_end, bool) or page_end < page:
                page_end = page
            result.append({
                "document_id": document_id,
                "chunk_id": point_id(document_id, chunk_index, chunker),
                "chunk_index": chunk_index,
                "page": page,
                "page_end": page_end,
                "manifest": manifest,
            })
        return result

    def upgrade(
        self,
        task_id: str,
        *,
        claim_id: str,
        question: str,
        document_ids: Sequence[str],
        from_level: str = "abstract",
        chunker: str = "v1",
        top_k: int = 5,
    ) -> EvidenceUpgrade:
        if not str(task_id).strip() or not str(claim_id).strip() or not str(question).strip():
            raise EvidenceUpgradeError("INVALID_REQUEST", "task_id、claim_id、question 不能为空")
        if from_level not in {"catalog", "abstract"}:
            raise EvidenceUpgradeError("INVALID_REQUEST", "from_level 必须为 catalog 或 abstract")
        if chunker not in {"v1", "v2"} or int(top_k) < 1 or int(top_k) > 50:
            raise EvidenceUpgradeError("INVALID_REQUEST", "chunker 或 top_k 无效")
        allowlist = self._allowlist(task_id, document_ids)
        generation = self._generation()
        try:
            hits = self.search(
                question,
                top_k=int(top_k),
                chunker=chunker,
                document_ids=allowlist,
                include_citations=False,
            )
        except Exception as error:
            raise EvidenceUpgradeError("EVIDENCE_UNAVAILABLE", "全文检索暂时不可用", status=503) from error
        manifests: dict[str, Mapping[str, Any]] = {}
        manifest_error = False
        for document_id in allowlist:
            try:
                manifests[document_id] = self._manifest(document_id, chunker)
            except Exception:
                manifest_error = True
        valid = self._validated_hits(list(hits or ()), allowlist, chunker, manifests)
        if not valid:
            status = "unavailable" if manifest_error else "insufficient"
            upgrade = EvidenceUpgrade(
                claim_id=claim_id, task_id=task_id, from_level=from_level,
                to_level=from_level, chunk_ids=[], status=status,
            )
            return self.store.save_evidence_upgrade(upgrade)
        first = valid[0]
        manifest = first["manifest"]
        evidence = EvidenceUpgrade(
            claim_id=claim_id,
            task_id=task_id,
            document_id=first["document_id"],
            from_level=from_level,
            to_level="fulltext",
            chunk_ids=[item["chunk_id"] for item in valid if item["document_id"] == first["document_id"]],
            page=min(item["page"] for item in valid if item["document_id"] == first["document_id"]),
            page_end=max(item["page_end"] for item in valid if item["document_id"] == first["document_id"]),
            status="upgraded",
            source_sha256=str(manifest["source_sha256"]),
            manifest_generation=generation,
            manifest_fingerprint=str(manifest.get("index_fingerprint") or ""),
            chunker=chunker,
        )
        return self.store.save_evidence_upgrade(evidence)

    def revalidate(self, task_id: str) -> list[EvidenceUpgrade]:
        """Downgrade stale references without changing report history."""
        generation = None
        try:
            generation = self._generation()
        except EvidenceUpgradeError:
            pass
        refreshed: list[EvidenceUpgrade] = []
        for existing in self.store.list_evidence_upgrades(task_id):
            if existing.status not in {"upgraded", "revalidation_required"} or not existing.document_id:
                refreshed.append(existing)
                continue
            status = "upgraded"
            try:
                manifest = self._manifest(existing.document_id, existing.chunker or "v1")
                chunk_ids = {
                    point_id(existing.document_id, int(item.get("chunk_index")), existing.chunker or "v1")
                    for item in manifest.get("chunks", ())
                    if isinstance(item, Mapping) and isinstance(item.get("chunk_index"), int)
                }
                if existing.source_sha256 != manifest.get("source_sha256"):
                    status = "revalidation_required"
                elif existing.manifest_fingerprint and existing.manifest_fingerprint != manifest.get("index_fingerprint"):
                    status = "revalidation_required"
                elif generation is None or existing.manifest_generation != generation:
                    status = "revalidation_required"
                elif not set(existing.chunk_ids).issubset(chunk_ids):
                    status = "revalidation_required"
            except Exception:
                status = "unavailable"
            if status != existing.status:
                existing = self.store.save_evidence_upgrade(
                    EvidenceUpgrade(**{**existing.__dict__, "status": status})
                )
            refreshed.append(existing)
        return refreshed


__all__ = ["EvidenceUpgradeError", "EvidenceUpgradeService"]
