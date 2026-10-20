"""Evidence-gated map analysis and the narrow conversation bridge.

This module deliberately delegates generation and retrieval to the existing
chat/RAG seams.  It owns only map-specific evidence freezing, durable jobs,
and conversation bindings.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Mapping
from concurrent.futures import Executor
from typing import Any

from backend.app.chat.application.chat_runner import run_chat
from backend.app.chat.application.conversation_service import compose_chat_messages
from backend.app.knowledge_base.application import list_documents_for_project
from backend.app.knowledge_base.infrastructure.manifest_store import (
    FinalizeBundleStore,
    InspectionManifestStore,
    ManifestStoreError,
)
from backend.app.knowledge_base.infrastructure.prompts import citation_payloads
from backend.app.knowledge_base.infrastructure.retrieve import hybrid_search
from backend.app.literature_maps.domain.analysis import EVIDENCE_LEVELS, MapAnalysis
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.memory.repository import MemoryRepository
from backend.app.memory.markdown_store import read_user_memory_or_empty
from backend.app.platform.config import KB_DIR, MODEL_NAME

logger = logging.getLogger(__name__)


class MapAnalysisError(RuntimeError):
    """Stable, user-safe map-analysis failure."""

    def __init__(self, code: str, message: str = "分析暂不可用", *, retryable: bool = False, status: int = 409):
        self.code = code
        self.message = message
        self.retryable = bool(retryable)
        self.status = int(status)
        super().__init__(code)


def _hash_source(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(value), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _params_hash(value: Mapping[str, Any]) -> str:
    return _hash_source(value)


class MapAnalysisService:
    def __init__(
        self,
        *,
        store: LiteratureMapStore,
        executor: Executor | None = None,
        memory_repository: MemoryRepository | None = None,
        model_runner: Callable[..., Any] | None = None,
        source_checker: Callable[..., dict[str, Any]] | None = None,
        searcher: Callable[..., list[Any]] | None = None,
    ) -> None:
        self.store = store
        self.executor = executor
        self.memory_repository = memory_repository
        self.model_runner = model_runner
        self.source_checker = source_checker
        self.searcher = searcher or hybrid_search

    def _memory(self) -> MemoryRepository:
        return self.memory_repository or MemoryRepository()

    def source_status(self, map_id: str, node_id: str, owner_id: str) -> dict[str, Any]:
        map_item = self.store.get_map(map_id, owner_id)
        node = self.store.get_node(map_id, node_id, owner_id)
        if map_item is None or node is None:
            raise LookupError("map or node not found")
        if node.removed:
            raise MapAnalysisError("MAP_NODE_REMOVED", "论文节点已移除")
        abstract_available = bool(str(node.abstract or "").strip())
        source_versions: dict[str, str] = {}
        if abstract_available:
            source_versions["abstract"] = _hash_source(
                {"title": node.title, "abstract": node.abstract or "", "external_ids": node.external_ids}
            )
        full = self._full_source(map_item, node, owner_id)
        if full is not None:
            source_versions["full"] = full["source_version"]
        available = [level for level in ("abstract", "full") if level in source_versions]
        reason = None
        if not available:
            reason = "MAP_ABSTRACT_UNAVAILABLE" if not abstract_available else "MAP_FULLTEXT_UNAVAILABLE"
        return {
            "abstract_available": abstract_available,
            "fulltext_ready": "full" in source_versions,
            "available_evidence_levels": available,
            "source_versions": {"abstract": source_versions.get("abstract"), "full": source_versions.get("full")},
            "unavailable_reason": reason,
        }

    def _full_source(self, map_item: Any, node: Any, owner_id: str) -> dict[str, Any] | None:
        if self.source_checker is not None:
            try:
                return self.source_checker(map_item, node, owner_id)
            except Exception:
                return None
        document_id = str(node.document_id or "").strip()
        if not document_id:
            return None
        return self._full_source_for_project(map_item.project_id, document_id, owner_id)

    def _full_source_for_project(self, project_id: str | None, document_id: str, owner_id: str) -> dict[str, Any] | None:
        """Resolve a full-text source from the canonical project/manifest gate.

        This helper intentionally does not accept a caller-provided source
        version.  Every call re-reads the owner-scoped document association,
        the committed generation marker, and the inspection manifest.
        """
        # ``project_id=None`` is the owner-scoped shared pool.  It is a
        # legitimate canonical-document scope and must not be confused with
        # an omitted document identity.
        if not document_id:
            return None
        try:
            records = list_documents_for_project(project_id, owner_id=owner_id)
        except Exception:
            return None
        record = next((item for item in records if str(item.get("document_id") or item.get("paper_id") or "") == document_id), None)
        source_hash = str((record or {}).get("source_sha256") or "").strip()
        if record is None or not source_hash:
            return None
        try:
            generation = FinalizeBundleStore(KB_DIR.parents[1]).require_generation()
            manifest = InspectionManifestStore(KB_DIR).read(document_id, "v1").to_dict()
        except (ManifestStoreError, OSError, RuntimeError, ValueError):
            return None
        if (
            manifest.get("status") != "ready"
            or manifest.get("progress") != 100
            or manifest.get("source_hash_state") != "verified"
            or manifest.get("document_id") != document_id
            or manifest.get("chunker") != "v1"
            or manifest.get("source_sha256") != source_hash
            or manifest.get("indexed_source_sha256") != source_hash
            or not str(manifest.get("index_fingerprint") or "").strip()
        ):
            return None
        source_version = _hash_source(
            {
                "document_id": document_id,
                "source_sha256": source_hash,
                "chunker": "v1",
                "generation": generation.get("run_id"),
                "manifest": manifest.get("index_fingerprint") or manifest.get("mapping_algorithm_version"),
            }
        )
        return {"document_id": document_id, "source_version": source_version, "chunker": "v1", "generation": generation.get("run_id")}

    def conversation_context(self, binding: Any, owner_id: str, conversation_project_id: str | None) -> dict[str, Any]:
        """Revalidate a bound conversation without consulting a live map node.

        Abstract bindings are deliberately snapshot-only: deleting a map/node
        cannot erase the context that was already frozen into the conversation.
        Full bindings remain live evidence and therefore repeat the complete
        owner/project/document/generation/manifest gate on every message.
        """
        if binding is None or binding.owner_id != owner_id or binding.status != "confirmed":
            raise MapAnalysisError("MAP_CONVERSATION_CONTEXT_UNAVAILABLE", "论文上下文暂不可用")
        if binding.project_id_snapshot != conversation_project_id:
            raise MapAnalysisError("MAP_CONVERSATION_PROJECT_MISMATCH", "会话项目已变化")
        if binding.evidence_level == "abstract":
            context = dict(binding.context or {})
            if not str(context.get("title") or "").strip() or not str(context.get("abstract") or "").strip():
                raise MapAnalysisError("MAP_CONVERSATION_CONTEXT_UNAVAILABLE", "论文摘要上下文暂不可用")
            expected = _hash_source(
                {
                    "title": context.get("title", ""),
                    "abstract": context.get("abstract", ""),
                    "external_ids": context.get("external_ids") or {},
                }
            )
            if expected != binding.source_version:
                raise MapAnalysisError("MAP_CONVERSATION_CONTEXT_UNAVAILABLE", "论文摘要上下文已损坏")
            return {"context": context, "visible_document_ids": [], "source_version": binding.source_version}
        if binding.evidence_level != "full":
            raise MapAnalysisError("MAP_CONVERSATION_CONTEXT_UNAVAILABLE", "论文上下文暂不可用")
        if binding.project_id_snapshot is not None and self._memory().get_project(binding.project_id_snapshot, owner_id) is None:
            raise MapAnalysisError("MAP_FULLTEXT_UNAVAILABLE", "论文项目已不可用")
        document_id = str((binding.context or {}).get("document_id") or "").strip()
        full = self._full_source_for_project(binding.project_id_snapshot, document_id, owner_id)
        if full is None or full["source_version"] != binding.source_version:
            raise MapAnalysisError("MAP_ANALYSIS_SOURCE_CHANGED", "论文全文依据已变化，请重新发起会话")
        return {
            "context": dict(binding.context or {}),
            "visible_document_ids": [document_id],
            "source_version": full["source_version"],
            "chunker": full["chunker"],
        }

    def request_analysis(
        self,
        map_id: str,
        node_id: str,
        owner_id: str,
        *,
        evidence_level: str,
        idempotency_key: str,
        model: str | None = None,
    ) -> Any:
        if evidence_level not in EVIDENCE_LEVELS:
            raise MapAnalysisError("INVALID_EVIDENCE_LEVEL", "依据级别无效", status=400)
        status = self.source_status(map_id, node_id, owner_id)
        source_version = status["source_versions"].get(evidence_level)
        if not source_version:
            code = "MAP_ABSTRACT_UNAVAILABLE" if evidence_level == "abstract" else "MAP_FULLTEXT_UNAVAILABLE"
            raise MapAnalysisError(code, "当前依据不可用")
        selected_model = str(model or MODEL_NAME).strip() or MODEL_NAME
        params_hash = _params_hash({"evidence_level": evidence_level, "model": selected_model, "source_version": source_version})
        analysis, job, created = self.store.create_analysis(
            map_id,
            node_id,
            owner_id,
            evidence_level=evidence_level,
            source_version=source_version,
            model_id=selected_model,
            idempotency_key=idempotency_key,
            params_hash=params_hash,
        )
        if created and self.executor is not None:
            self.executor.submit(self.run_analysis_job, job.job_id, owner_id)
        return analysis, job, created

    def run_analysis_job(self, job_id: str, owner_id: str | None = None) -> MapAnalysis | None:
        resolved = self.store.get_job_with_owner(job_id) if owner_id is None else None
        if resolved is not None:
            job, owner_id = resolved
        else:
            job = self._job_for_owner(job_id, owner_id)
        if job is None or owner_id is None or job.operation != "analysis":
            return None
        claimed = self.store.claim_analysis_job(job.job_id, job.map_id, owner_id)
        if claimed is None:
            return self._analysis_for_job(job.job_id, job.map_id, owner_id)
        analysis = self._analysis_for_job(job.job_id, job.map_id, owner_id)
        if analysis is None:
            return None
        try:
            map_item = self.store.get_map(analysis.map_id, owner_id)
            node = self.store.get_node(analysis.map_id, analysis.node_id, owner_id)
            if map_item is None or node is None or node.removed:
                raise MapAnalysisError("MAP_NODE_REMOVED", "论文节点已移除")
            current = self.source_status(analysis.map_id, analysis.node_id, owner_id)
            if current["source_versions"].get(analysis.evidence_level) != analysis.source_version:
                raise MapAnalysisError("MAP_ANALYSIS_SOURCE_CHANGED", "论文依据已变化，请重新分析")
            hits: list[Any] = []
            if analysis.evidence_level == "full":
                full = self._full_source(map_item, node, owner_id)
                if full is None:
                    raise MapAnalysisError("MAP_FULLTEXT_UNAVAILABLE", "全文索引尚未就绪")
                hits = list(self.searcher(
                    f"请概括论文《{node.title}》的研究问题、方法和结论",
                    top_k=5,
                    chunker=full["chunker"],
                    document_ids=[full["document_id"]],
                    include_citations=False,
                ) or [])
                hits = [hit for hit in hits if getattr(hit, "paper_id", None) == full["document_id"] and str(getattr(hit, "text", "")).strip()]
                if not hits:
                    raise MapAnalysisError("MAP_EVIDENCE_UNAVAILABLE", "全文没有召回有效索引片段")
            summary = self._generate(node=node, analysis=analysis, owner_id=owner_id, hits=hits, map_item=map_item)
            # The model may take long enough for a document/manifest or node
            # snapshot to change.  Re-check immediately before the durable
            # completion CAS; stale text must never be persisted as current.
            final_status = self.source_status(analysis.map_id, analysis.node_id, owner_id)
            if final_status["source_versions"].get(analysis.evidence_level) != analysis.source_version:
                raise MapAnalysisError("MAP_ANALYSIS_SOURCE_CHANGED", "论文依据已变化，请重新分析")
            result = {
                "summary": summary,
                "citations": citation_payloads(hits) if hits else [],
                "source_refs": (
                    [{"kind": "fulltext", "document_id": hits[0].paper_id, "chunker": hits[0].chunker}]
                    if hits
                    else [{"kind": "abstract", "node_id": node.node_id}]
                ),
            }
            self.store.finish_analysis(job.job_id, analysis.map_id, owner_id, status="completed", result=result)
        except MapAnalysisError as error:
            self.store.finish_analysis(job.job_id, analysis.map_id, owner_id, status="failed", error={"code": error.code, "message": error.message, "retryable": error.retryable})
        except Exception:
            logger.exception("map analysis failed")
            self.store.finish_analysis(job.job_id, analysis.map_id, owner_id, status="failed", error={"code": "MAP_MODEL_FAILED", "message": "模型分析失败，请稍后重试", "retryable": True})
        return self._analysis_for_job(job.job_id, analysis.map_id, owner_id)

    def _generate(self, *, node: Any, analysis: MapAnalysis, owner_id: str, hits: list[Any], map_item: Any) -> str:
        project_instructions = None
        if map_item.project_id:
            project = self._memory().get_project(map_item.project_id, owner_id)
            project_instructions = project.instructions if project else None
        question = (
            f"请基于已提供的论文证据，输出一段简洁、可核验的中文总结。论文标题：{node.title}\n"
            f"论文摘要：{node.abstract or '未提供'}"
        )
        if hits:
            question = f"请基于检索到的论文片段，输出一段简洁、可核验的中文总结，不要声称通读全文。\n论文标题：{node.title}"
        history: list[Any] = []
        messages = compose_chat_messages(
            question,
            history,
            [],
            project_instructions,
            rag_hits=hits,
            system_rule=read_user_memory_or_empty() or None,
            project_id=map_item.project_id,
        )
        if self.model_runner is not None:
            run = self.model_runner(messages=messages, model=analysis.model_id, analysis=analysis, node=node, hits=hits)
        else:
            run = run_chat(question, analysis.model_id, messages=messages, think=False, reasoning_effort="off")
        for _event in getattr(run, "events", ()) or ():
            # Drain the existing ChatRun stream so its real OllamaChatResult is
            # finalized; thinking events are intentionally never persisted.
            continue
        result = getattr(run, "result", None)
        content = str(getattr(result, "content", "") or "").strip()
        if not content:
            raise MapAnalysisError("MAP_MODEL_EMPTY", "模型未返回有效分析", retryable=True, status=503)
        if bool(getattr(result, "interrupted", False)) or getattr(result, "completed_normally", True) is False:
            raise MapAnalysisError("MAP_MODEL_INTERRUPTED", "模型输出未正常完成", retryable=True, status=503)
        return content[:12000]

    def create_conversation(self, map_id: str, node_id: str, owner_id: str, *, evidence_level: str, idempotency_key: str) -> dict[str, Any]:
        if evidence_level not in EVIDENCE_LEVELS:
            raise MapAnalysisError("INVALID_EVIDENCE_LEVEL", "依据级别无效", status=400)
        map_item = self.store.get_map(map_id, owner_id)
        node = self.store.get_node(map_id, node_id, owner_id)
        if map_item is None or node is None or node.removed:
            raise MapAnalysisError("MAP_NODE_REMOVED", "论文节点已移除")
        status = self.source_status(map_id, node_id, owner_id)
        source_version = status["source_versions"].get(evidence_level)
        if not source_version:
            code = "MAP_ABSTRACT_UNAVAILABLE" if evidence_level == "abstract" else "MAP_FULLTEXT_UNAVAILABLE"
            raise MapAnalysisError(code, "当前依据不可用")
        context = {
            "map_id": map_id,
            "node_id": node_id,
            "title": node.title,
            "abstract": node.abstract or "",
            "external_ids": dict(node.external_ids or {}),
        }
        if node.document_id:
            context["document_id"] = node.document_id
        context["paper_context_hash"] = _hash_source(
            {"title": context["title"], "abstract": context["abstract"], "external_ids": context["external_ids"]}
        )
        prior = self.store.get_conversation_binding_for_request(map_id, node_id, owner_id, idempotency_key)
        if prior is not None:
            existing_state = self._memory().get_conversation_including_deleted(prior.conversation_id, owner_id)
            if existing_state is not None and existing_state.status in {"archived", "deleted"}:
                self.store.retire_conversation_binding(prior.binding_id, owner_id)
        binding, _reserved = self.store.reserve_conversation_binding(
            map_id,
            node_id,
            owner_id,
            project_id_snapshot=map_item.project_id,
            evidence_level=evidence_level,
            source_version=source_version,
            context=context,
            idempotency_key=idempotency_key,
            params_hash=_params_hash({"evidence_level": evidence_level, "source_version": source_version}),
        )
        current_map = self.store.get_map(map_id, owner_id)
        current_source = self.source_status(map_id, node_id, owner_id)
        if current_map is None or current_map.project_id != binding.project_id_snapshot:
            raise MapAnalysisError("MAP_CONVERSATION_PROJECT_CHANGED", "地图项目已变化，请重新发起会话")
        if current_source["source_versions"].get(evidence_level) != binding.source_version:
            raise MapAnalysisError("MAP_ANALYSIS_SOURCE_CHANGED", "论文依据已变化，请重新发起会话")
        memory = self._memory()
        existing = memory.get_conversation(binding.conversation_id, owner_id)
        if existing is not None:
            if existing.status != "active":
                self.store.retire_conversation_binding(binding.binding_id, owner_id)
                return self.create_conversation(
                    map_id,
                    node_id,
                    owner_id,
                    evidence_level=evidence_level,
                    idempotency_key=idempotency_key,
                )
            if existing.project_id != binding.project_id_snapshot:
                raise MapAnalysisError("MAP_CONVERSATION_PROJECT_MISMATCH", "会话项目已变化")
            confirmed = self.store.confirm_conversation_binding(binding.binding_id, owner_id, conversation_id=binding.conversation_id, context=context)
            return {"conversation_id": binding.conversation_id, "created": False, "project_id": binding.project_id_snapshot, "evidence_level": evidence_level, "source_version": source_version, "context": context}
        created_conversation = False
        try:
            memory.create_conversation(
                owner_id,
                project_id=binding.project_id_snapshot,
                title=f"关于论文：{node.title}"[:200],
                conversation_id=binding.conversation_id,
            )
            # ``created`` describes this request's actual MemoryRepository
            # insert, not which SQLite caller won the binding reservation.
            # A racing caller may observe an active row after another caller
            # inserted it and must return false; exactly one successful insert
            # reports true.
            created_conversation = True
        except Exception:
            # A crash after the reservation may have committed the conversation
            # already.  Re-read it and only fail closed on an owner/project
            # mismatch; never create a second conversation with a new ID.
            existing = memory.get_conversation(binding.conversation_id, owner_id)
            if existing is None:
                raise MapAnalysisError("MAP_CONVERSATION_CREATE_FAILED", "会话创建失败", retryable=True, status=503)
            if existing.project_id != binding.project_id_snapshot:
                raise MapAnalysisError("MAP_CONVERSATION_PROJECT_MISMATCH", "会话项目已变化")
        self.store.confirm_conversation_binding(binding.binding_id, owner_id, conversation_id=binding.conversation_id, context=context)
        return {"conversation_id": binding.conversation_id, "created": created_conversation, "project_id": binding.project_id_snapshot, "evidence_level": evidence_level, "source_version": source_version, "context": context}

    def _analysis_for_job(self, job_id: str, map_id: str, owner_id: str) -> MapAnalysis | None:
        with self.store.connection() as db:
            row = db.execute("SELECT a.* FROM literature_map_analyses a JOIN literature_maps m ON m.map_id=a.map_id WHERE a.job_id=? AND a.map_id=? AND m.owner_id=? AND m.deleted_at IS NULL", (job_id, map_id, owner_id)).fetchone()
        if row is None:
            return None
        from backend.app.literature_maps.infrastructure.store import _analysis
        return _analysis(row)

    def _job_for_owner(self, job_id: str, owner_id: str | None):
        if owner_id is None:
            return None
        with self.store.connection() as db:
            row = db.execute("SELECT j.* FROM literature_map_jobs j JOIN literature_maps m ON m.map_id=j.map_id WHERE j.job_id=? AND j.operation='analysis' AND m.owner_id=? AND m.deleted_at IS NULL", (job_id, owner_id)).fetchone()
        if row is None:
            return None
        from backend.app.literature_maps.infrastructure.store import _job
        return _job(row)

    def recover(self, owner_id: str | None = None) -> int:
        jobs = [job for job in self.store.recover_jobs(owner_id) if job.operation == "analysis"]
        for job in jobs:
            if self.executor is not None:
                self.executor.submit(self.run_analysis_job, job.job_id, owner_id)
        return len(jobs)


def conversation_binding(store: LiteratureMapStore, conversation_id: str, owner_id: str):
    """Read a confirmed binding for the existing conversation RAG seam."""
    return store.get_conversation_binding(conversation_id, owner_id)


__all__ = ["MapAnalysisError", "MapAnalysisService", "conversation_binding"]
