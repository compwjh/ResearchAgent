"""Evidence-gated map analysis and the narrow conversation bridge.

This module deliberately delegates generation and retrieval to the existing
chat/RAG seams.  It owns only map-specific evidence freezing, durable jobs,
and conversation bindings.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import Executor
from datetime import datetime, timezone
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
        queue_executor: Executor | None = None,
        memory_repository: MemoryRepository | None = None,
        model_runner: Callable[..., Any] | None = None,
        source_checker: Callable[..., dict[str, Any]] | None = None,
        searcher: Callable[..., list[Any]] | None = None,
        auxiliary_recovery: Callable[[str, str], int] | None = None,
    ) -> None:
        self.store = store
        self.executor = executor
        self.queue_executor = queue_executor or executor
        self.memory_repository = memory_repository
        self.model_runner = model_runner
        self.source_checker = source_checker
        self.searcher = searcher or hybrid_search
        self.auxiliary_recovery = auxiliary_recovery
        self._queue_dispatch_lock = threading.Lock()
        self._queue_dispatching: set[tuple[str, str]] = set()
        self._queue_retry_wakeups: dict[tuple[str, str], threading.Timer] = {}
        self._analysis_lease_wakeups: dict[tuple[str, str], threading.Timer] = {}
        self._shutdown = False

    def shutdown(self) -> None:
        """Stop this service's daemon wakeups before its runtime is reset.

        Timers are deliberately owned by the service instance.  Cancelling
        and clearing them before executors close prevents an old runtime from
        mutating the durable queue after a new runtime has taken over.
        """

        with self._queue_dispatch_lock:
            self._shutdown = True
            timers = [*self._queue_retry_wakeups.values(), *self._analysis_lease_wakeups.values()]
            self._queue_retry_wakeups.clear()
            self._analysis_lease_wakeups.clear()
        for timer in timers:
            timer.cancel()

    def _finish_analysis_if_active(
        self,
        job_id: str,
        map_id: str,
        owner_id: str,
        *,
        status: str,
        result: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
        worker_token: str | None = None,
        queue_pause_reason: str | None = None,
    ) -> MapAnalysis | None:
        """CAS-finish only while the runtime lifecycle remains open.

        The lock covers only this short durable transaction, never model
        generation.  It makes the shutdown flag and final finish one atomic
        choice: an in-flight finish completes before shutdown returns, or a
        worker that observes shutdown performs no persistent write.
        """

        with self._queue_dispatch_lock:
            if self._shutdown:
                return None
            return self.store.finish_analysis(
                job_id,
                map_id,
                owner_id,
                status=status,
                result=result,
                error=error,
                worker_token=worker_token,
                queue_pause_reason=queue_pause_reason,
            )

    def _memory(self) -> MemoryRepository:
        return self.memory_repository or MemoryRepository()

    def analysis_config_fingerprint(self) -> str:
        """Return the normalized server-side configuration identity.

        Automatic queue synchronization includes this value in its durable
        idempotency key. A model/configuration change therefore reconciles to
        a new analysis version instead of colliding with an older candidate.
        """

        selected_model = str(MODEL_NAME or "").strip() or MODEL_NAME
        return _hash_source({"model": selected_model})

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
        # ``project_id=None`` is the owner-scoped shared pool of canonical
        # records with no sidecar association.  Associated records remain
        # excluded even when their relation belongs to another owner/project.
        # It must not be confused with an omitted document identity.
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
        # The generation marker is shared by every document.  A later valid
        # refresh must not make an older ready manifest usable after this
        # document was durably marked mismatched or otherwise unpublished.
        # Read the canonical v1 state as part of this narrow 043 gate.
        chunkers = (record or {}).get("chunkers")
        v1_state = chunkers.get("v1") if isinstance(chunkers, dict) else None
        try:
            v1_progress = int((v1_state or {}).get("progress", -1))
        except (TypeError, ValueError):
            v1_progress = -1
        if (
            (record or {}).get("source_hash_state") != "verified"
            or (record or {}).get("indexed_source_sha256") != source_hash
            or not isinstance(v1_state, dict)
            or v1_state.get("status") != "indexed"
            or v1_progress != 100
            or v1_state.get("error") not in (None, "")
        ):
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
        if self._shutdown:
            return None
        resolved = self.store.get_job_with_owner(job_id) if owner_id is None else None
        if resolved is not None:
            job, owner_id = resolved
        else:
            job = self._job_for_owner(job_id, owner_id)
        if job is None or owner_id is None or job.operation != "analysis":
            return None
        with self._queue_dispatch_lock:
            if self._shutdown:
                return None
            claimed = self.store.claim_analysis_job(job.job_id, job.map_id, owner_id)
        if claimed is None:
            return self._analysis_for_job(job.job_id, job.map_id, owner_id)
        self._schedule_analysis_lease_wakeup(job.map_id, owner_id, claimed.lease_expires_at)
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
            self._finish_analysis_if_active(
                job.job_id,
                analysis.map_id,
                owner_id,
                status="completed",
                worker_token=claimed.worker_token,
                result=result,
            )
        except MapAnalysisError as error:
            self._finish_analysis_if_active(
                job.job_id,
                analysis.map_id,
                owner_id,
                status="failed",
                worker_token=claimed.worker_token,
                error={"code": error.code, "message": error.message, "retryable": error.retryable},
                queue_pause_reason=error.code if _queue_pause_required(error.code) else None,
            )
        except Exception as error:
            classified = _classify_provider_error(error)
            logger.exception("map analysis failed")
            self._finish_analysis_if_active(
                job.job_id,
                analysis.map_id,
                owner_id,
                status="failed",
                worker_token=claimed.worker_token,
                error={"code": classified.code, "message": classified.message, "retryable": classified.retryable},
                queue_pause_reason=classified.code if _queue_pause_required(classified.code) else None,
            )
        result_analysis = self._analysis_for_job(job.job_id, analysis.map_id, owner_id)
        # An explicit analysis may have occupied the map-wide serial slot
        # while an automatic queue was waiting.  Wake that queue after the
        # explicit child finishes; queue children themselves are drained by
        # their current scheduler loop to avoid recursive submissions.
        if not job.cursor.get("queue_job_id"):
            try:
                self._schedule_analysis_queue(analysis.map_id, owner_id, self.store.get_analysis_queue(analysis.map_id, owner_id))
            except LookupError:
                pass
        self._schedule_waiting_analysis(analysis.map_id, owner_id)
        return result_analysis

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

    def ensure_analysis_queue(self, map_id: str, owner_id: str, *, idempotency_key: str) -> dict[str, Any]:
        """Explicitly reconcile all active nodes into the durable abstract queue."""

        nodes = [node for node in self.store.list_nodes(map_id, owner_id) if not node.removed]
        selected_model = str(MODEL_NAME or "").strip() or MODEL_NAME
        candidates: list[dict[str, Any]] = []
        for node in nodes:
            abstract = str(node.abstract or "").strip()
            source_version = _hash_source(
                {"title": node.title, "abstract": node.abstract or "", "external_ids": node.external_ids}
            ) if abstract else ""
            stable_key = f"auto:{node.node_id}:{source_version}:{selected_model}" if source_version else None
            candidates.append(
                {
                    "node_id": node.node_id,
                    "abstract_available": bool(abstract),
                    "source_version": source_version,
                    "model_id": selected_model,
                    "idempotency_key": stable_key,
                    "params_hash": _params_hash({"evidence_level": "abstract", "model": selected_model, "source_version": source_version}),
                }
            )
        params_hash = _params_hash({"model": selected_model, "nodes": candidates})
        queue = self.store.ensure_analysis_queue(
            map_id,
            owner_id,
            idempotency_key=idempotency_key,
            candidates=candidates,
            params_hash=params_hash,
        )
        self._schedule_analysis_queue(map_id, owner_id, queue)
        return queue

    def get_analysis_queue(self, map_id: str, owner_id: str) -> dict[str, Any]:
        return self.store.get_analysis_queue(map_id, owner_id)

    def pause_analysis_queue(self, map_id: str, owner_id: str, *, idempotency_key: str) -> dict[str, Any]:
        return self.store.pause_analysis_queue(map_id, owner_id, idempotency_key=idempotency_key)

    def resume_analysis_queue(self, map_id: str, owner_id: str, *, idempotency_key: str) -> dict[str, Any]:
        queue = self.store.resume_analysis_queue(map_id, owner_id, idempotency_key=idempotency_key)
        self._schedule_analysis_queue(map_id, owner_id, queue)
        if self.auxiliary_recovery is not None:
            self.auxiliary_recovery(map_id, owner_id)
        return queue

    def retry_analysis_queue(self, map_id: str, owner_id: str, *, idempotency_key: str, analysis_ids: list[str] | None = None) -> dict[str, Any]:
        queue = self.store.retry_analysis_queue(map_id, owner_id, idempotency_key=idempotency_key, analysis_ids=analysis_ids)
        self._schedule_analysis_queue(map_id, owner_id, queue)
        return queue

    def run_analysis_queue(self, map_id: str, owner_id: str, queue_job_id: str | None = None) -> MapAnalysis | None:
        """Run one queue child per executor turn, preserving map seriality.

        A synchronous caller (the test/CLI seam) may drain the queue fully;
        an executor caller yields after one child so another map or graph job
        can acquire a slot. The durable store remains the sole scheduler
        state machine.
        """

        last: MapAnalysis | None = None
        while True:
            with self._queue_dispatch_lock:
                if self._shutdown:
                    break
                self.store.requeue_due_analysis_jobs(map_id, owner_id)
                queue = self.store.get_analysis_queue(map_id, owner_id)
            if queue_job_id and queue.get("queue_job_id") != queue_job_id:
                break
            if queue.get("state") != "active":
                break
            child_id = self.store.next_queued_analysis_job(map_id, owner_id)
            if child_id is None:
                with self._queue_dispatch_lock:
                    if not self._shutdown:
                        self.store.refresh_analysis_queue(map_id, owner_id)
                break
            last = self.run_analysis_job(child_id, owner_id)
            if last is None:
                break
            if self.queue_executor is not None:
                break
        return last

    def _schedule_analysis_queue(self, map_id: str, owner_id: str, queue: Mapping[str, Any]) -> None:
        if self.queue_executor is None or queue.get("state") != "active" or not queue.get("queue_job_id"):
            return
        key = (str(map_id), str(owner_id))
        with self._queue_dispatch_lock:
            if self._shutdown:
                return
            if key in self._queue_dispatching:
                return
            self._queue_dispatching.add(key)
        try:
            self.queue_executor.submit(self._run_scheduled_queue, map_id, owner_id, queue.get("queue_job_id"))
        except Exception:
            with self._queue_dispatch_lock:
                self._queue_dispatching.discard(key)
            raise

    def _run_scheduled_queue(self, map_id: str, owner_id: str, queue_job_id: str | None = None) -> MapAnalysis | None:
        key = (str(map_id), str(owner_id))
        try:
            return self.run_analysis_queue(map_id, owner_id, queue_job_id)
        finally:
            with self._queue_dispatch_lock:
                self._queue_dispatching.discard(key)
            try:
                queue = self.store.get_analysis_queue(map_id, owner_id)
            except LookupError:
                queue = None
            if (
                queue is not None
                and queue.get("state") == "active"
                and int(queue.get("counts", {}).get("queued", 0)) > 0
                and not self.store.has_running_analysis_job(map_id, owner_id)
            ):
                try:
                    self._schedule_analysis_queue(map_id, owner_id, queue)
                except RuntimeError:
                    pass
            elif queue is not None and queue.get("state") == "partial":
                self._schedule_analysis_retry_wakeup(map_id, owner_id, queue)

    def _schedule_analysis_retry_wakeup(self, map_id: str, owner_id: str, queue: Mapping[str, Any]) -> None:
        """Schedule one non-blocking wakeup for the durable retry deadline.

        The timer only wakes the existing queue executor; all eligibility and
        state changes remain in ``requeue_due_analysis_jobs``. A process
        restart reconstructs the same wakeup from the persisted deadline.
        """

        if self.queue_executor is None or queue.get("state") == "paused":
            return
        deadlines = []
        for item in queue.get("failed_items", ()) or ():
            if not isinstance(item, Mapping):
                continue
            raw = item.get("next_retry_at")
            if not raw:
                continue
            try:
                deadlines.append(datetime.fromisoformat(str(raw)))
            except (TypeError, ValueError):
                continue
        if not deadlines:
            return
        now = datetime.now(timezone.utc)
        deadline = min(deadlines)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        delay = max(0.05, (deadline - now).total_seconds())
        key = (str(map_id), str(owner_id))
        with self._queue_dispatch_lock:
            if self._shutdown:
                return
            existing = self._queue_retry_wakeups.get(key)
            if existing is not None and existing.is_alive():
                return
            timer = threading.Timer(delay, self._wake_due_analysis_queue, args=(map_id, owner_id))
            timer.daemon = True
            self._queue_retry_wakeups[key] = timer
        timer.start()

    def _wake_due_analysis_queue(self, map_id: str, owner_id: str) -> None:
        key = (str(map_id), str(owner_id))
        with self._queue_dispatch_lock:
            self._queue_retry_wakeups.pop(key, None)
            if self._shutdown:
                return
            # Keep the short durable transition inside the same lock used by
            # shutdown.  A reset therefore cannot return while this callback
            # is still writing through the old service instance.
            try:
                self.store.requeue_due_analysis_jobs(map_id, owner_id)
                queue = self.store.get_analysis_queue(map_id, owner_id)
            except LookupError:
                return
            if self._shutdown:
                return
        if (
            queue.get("state") == "active"
            and int(queue.get("counts", {}).get("queued", 0)) > 0
            and not self.store.has_running_analysis_job(map_id, owner_id)
        ):
            try:
                self._schedule_analysis_queue(map_id, owner_id, queue)
            except RuntimeError:
                # Runtime reset may close the executor while a daemon wakeup
                # is firing; the durable child remains queued for recovery.
                return
        elif queue.get("state") == "partial":
            self._schedule_analysis_retry_wakeup(map_id, owner_id, queue)

    def _schedule_analysis_lease_wakeup(
        self,
        map_id: str,
        owner_id: str,
        lease_expires_at: str | None,
    ) -> None:
        """Wake the existing scheduler when a durable worker lease expires."""

        if not lease_expires_at or (self.queue_executor is None and self.executor is None):
            return
        try:
            deadline = datetime.fromisoformat(str(lease_expires_at))
        except (TypeError, ValueError):
            return
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        delay = max(0.05, (deadline - datetime.now(timezone.utc)).total_seconds())
        key = (str(map_id), str(owner_id))
        with self._queue_dispatch_lock:
            if self._shutdown:
                return
            existing = self._analysis_lease_wakeups.get(key)
            if existing is not None and existing.is_alive():
                return
            timer = threading.Timer(delay, self._wake_expired_analysis_jobs, args=(map_id, owner_id))
            timer.daemon = True
            self._analysis_lease_wakeups[key] = timer
        timer.start()

    def _wake_expired_analysis_jobs(self, map_id: str, owner_id: str) -> None:
        """Atomically recover expired children and resubmit them once."""

        key = (str(map_id), str(owner_id))
        with self._queue_dispatch_lock:
            self._analysis_lease_wakeups.pop(key, None)
            if self._shutdown:
                return
            # ``recover_analysis_jobs`` is an expiry-guarded transaction.  Do
            # not call it after shutdown has acquired this lock.
            recovered = self.store.recover_analysis_jobs(owner_id)
            if self._shutdown:
                return
        self._dispatch_recovered_analysis_jobs(recovered, owner_id)
        self._schedule_existing_analysis_lease_wakeups(owner_id)

    def _schedule_existing_analysis_lease_wakeups(self, owner_id: str | None = None) -> None:
        if self._shutdown:
            return
        for map_id, resolved_owner, lease_expires_at in self.store.running_analysis_jobs(owner_id):
            self._schedule_analysis_lease_wakeup(map_id, resolved_owner, lease_expires_at)

    def _dispatch_recovered_analysis_jobs(self, jobs: list[Any], owner_id: str | None = None) -> set[tuple[str, str]]:
        queue_maps: set[tuple[str, str]] = set()
        for job in jobs:
            resolved_owner = owner_id or self._owner_for_job(job)
            queue_job_id = str(job.cursor.get("queue_job_id") or "")
            if queue_job_id:
                queue_maps.add((job.map_id, resolved_owner))
            elif self.executor is not None:
                with self._queue_dispatch_lock:
                    allowed = not self._shutdown
                if allowed:
                    self.executor.submit(self.run_analysis_job, job.job_id, resolved_owner)
        for map_id, resolved_owner in sorted(queue_maps):
            if self.queue_executor is None:
                continue
            with self._queue_dispatch_lock:
                if self._shutdown:
                    continue
                try:
                    queue = self.store.get_analysis_queue(map_id, resolved_owner)
                    self.store.requeue_due_analysis_jobs(map_id, resolved_owner)
                    queue = self.store.get_analysis_queue(map_id, resolved_owner)
                except LookupError:
                    continue
                if self._shutdown:
                    continue
            try:
                self._schedule_analysis_queue(map_id, resolved_owner, queue)
            except RuntimeError:
                # Runtime reset may close the executor between the durable
                # recovery and this submission; the queued child remains
                # recoverable by the next service instance.
                continue
            if queue.get("state") == "partial":
                self._schedule_analysis_retry_wakeup(map_id, resolved_owner, queue)
        return queue_maps

    def _schedule_waiting_analysis(self, map_id: str, owner_id: str) -> None:
        """Wake one explicit analysis that was queued behind a map child."""

        if self.executor is None:
            return
        with self._queue_dispatch_lock:
            if self._shutdown:
                return
        for job in self.store.queued_analysis_jobs(owner_id):
            if job.map_id != map_id or job.cursor.get("queue_job_id"):
                continue
            with self._queue_dispatch_lock:
                if self._shutdown:
                    return
            try:
                self.executor.submit(self.run_analysis_job, job.job_id, owner_id)
            except RuntimeError:
                # A runtime reset may close the general pool between the
                # lifecycle check and submission; the durable queued job is
                # recovered by the next service instance.
                return
            break

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

    def _owner_for_job(self, job: Any) -> str:
        """Resolve the persisted owner for restart recovery without widening scope."""

        resolved = self.store.get_job_with_owner(job.job_id)
        if resolved is None:
            raise LookupError("analysis job not found")
        _stored_job, owner_id = resolved
        return owner_id

    def recover(self, owner_id: str | None = None) -> int:
        jobs = self.store.recover_analysis_jobs(owner_id)
        queued = self.store.queued_analysis_jobs(owner_id)
        queue_maps: set[tuple[str, str]] = set()
        queue_maps.update(self.store.active_analysis_queues(owner_id))
        queue_maps.update(self.store.retryable_analysis_queues(owner_id))
        explicit_queued = 0
        recovered_ids = {job.job_id for job in jobs}
        for job in queued:
            if job.job_id in recovered_ids:
                continue
            if job.cursor.get("queue_job_id"):
                continue
            explicit_queued += 1
            resolved_owner = owner_id or self._owner_for_job(job)
            if self.executor is not None and not self._shutdown:
                self.executor.submit(self.run_analysis_job, job.job_id, resolved_owner)
        queue_maps.update(self._dispatch_recovered_analysis_jobs(jobs, owner_id))
        for map_id, resolved_owner in sorted(queue_maps):
            if self.queue_executor is not None and not self._shutdown:
                try:
                    queue = self.store.get_analysis_queue(map_id, resolved_owner)
                except LookupError:
                    continue
                self.store.requeue_due_analysis_jobs(map_id, resolved_owner)
                queue = self.store.get_analysis_queue(map_id, resolved_owner)
                self._schedule_analysis_queue(map_id, resolved_owner, queue)
                if queue.get("state") == "partial":
                    self._schedule_analysis_retry_wakeup(map_id, resolved_owner, queue)
        self._schedule_existing_analysis_lease_wakeups(owner_id)
        return len(jobs) + explicit_queued


def conversation_binding(store: LiteratureMapStore, conversation_id: str, owner_id: str):
    """Read a confirmed binding for the existing conversation RAG seam."""
    return store.get_conversation_binding(conversation_id, owner_id)


def _queue_pause_required(code: str) -> bool:
    value = str(code or "").upper()
    return value in {"MAP_MODEL_UNAVAILABLE", "MAP_MODEL_AUTH_REQUIRED", "MAP_ANALYSIS_CONFIG_REQUIRED"} or "AUTH" in value or "CONFIG" in value


def _classify_provider_error(error: Exception) -> MapAnalysisError:
    """Map provider transport failures to stable, safe queue outcomes."""

    status_code = getattr(error, "status_code", None)
    if status_code is None:
        status_code = getattr(error, "http_status", None)
    if status_code is None:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
    text = str(error or "").lower()
    if status_code is None:
        match = re.search(r"\b(?:http(?:\s+status)?\s*)?([1-5]\d{2})\b", text)
        status_code = match.group(1) if match else None
    try:
        status = int(status_code) if status_code is not None else None
    except (TypeError, ValueError):
        status = None
    if status in {401, 403} or any(token in text for token in ("unauthorized", "forbidden", "authentication", "api key", "permission denied")):
        return MapAnalysisError("MAP_MODEL_AUTH_REQUIRED", "模型鉴权待配置", retryable=False, status=503)
    if status == 404 or any(token in text for token in ("model not found", "model does not exist", "no such model", "missing model", "model configuration", "model is required", "model required", "model_name", "no model configured", "model not configured", "model unavailable")):
        return MapAnalysisError("MAP_ANALYSIS_CONFIG_REQUIRED", "模型配置不可用", retryable=False, status=503)
    if status == 429 or any(token in text for token in ("rate limit", "too many requests", "temporarily throttled")):
        return MapAnalysisError("MAP_MODEL_RATE_LIMITED", "模型服务繁忙，请稍后重试", retryable=True, status=503)
    if isinstance(error, (TimeoutError, ConnectionError, OSError)) or any(token in text for token in ("timeout", "timed out", "connection refused", "connection reset", "connection attempts failed", "connecterror", "network", "unreachable", "temporarily unavailable")):
        return MapAnalysisError("MAP_MODEL_TRANSIENT", "模型服务暂时不可用，请稍后重试", retryable=True, status=503)
    return MapAnalysisError("MAP_MODEL_FAILED", "模型分析失败，请稍后重试", retryable=True, status=503)


__all__ = ["MapAnalysisError", "MapAnalysisService", "conversation_binding"]
