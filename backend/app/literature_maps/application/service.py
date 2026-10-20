"""Literature-map orchestration over the isolated SQLite store."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from concurrent.futures import Executor
from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from backend.app.literature_maps.application.catalog_adapter import (
    SUPPORTED_CONFERENCE_IDS,
    SUPPORTED_SOURCE_IDS,
    CatalogRow,
    CatalogSourceAdapter,
    canonical_conference,
    canonical_source,
    compatible_scope_pairs,
)
from backend.app.literature_maps.application.similarity import build_similarity_edges, is_valid_vector
from backend.app.literature_maps.domain.identity import deterministic_identity_key
from backend.app.literature_maps.domain.models import (
    LiteratureMap,
    MapEdge,
    MapJob,
    MapPaper,
    MapPreview,
    content_hash,
    iso_now,
    safe_edge_basis,
    safe_edge_content_hash,
    safe_edge_model_version,
)
from backend.app.literature_maps.infrastructure.store import LiteratureMapStore
from backend.app.paper_discovery.infrastructure.semantic_scholar_metadata import (
    SEMANTIC_SCHOLAR_METADATA_FIELDS,
    SemanticScholarGraphClient,
    SemanticScholarGraphPage,
    SemanticScholarMetadata,
)

logger = logging.getLogger(__name__)
MAX_NODES = 200
ALLOWED_LIMITS = {20, 30, 50}
GRAPH_REQUEST_BUDGET = 60
REFERENCES_PER_NODE = 100
SIMILARITY_THRESHOLD = 0.75
REQUEST_CACHE_TTL_SECONDS = 86400
REQUEST_CACHE_VERSION = "literature-map-v1"
_UNSET = object()


@dataclass(frozen=True)
class CreateMapResult:
    map: LiteratureMap
    job: MapJob


class LiteratureMapService:
    def __init__(self, *, store: LiteratureMapStore, client: Any | None = None, embedder: Callable[[Sequence[str]], list[list[float]]] | None = None, executor: Executor | None = None, project_lookup: Callable[[str, str], Any] | None = None, import_bridge: Callable[[MapPaper, str], Mapping[str, Any]] | None = None, catalog_adapter: Any | None = None) -> None:
        self.store = store
        self.client = client or SemanticScholarGraphClient()
        self.embedder = embedder
        self.executor = executor
        self.project_lookup = project_lookup
        self.import_bridge = import_bridge
        self.catalog_adapter = catalog_adapter or CatalogSourceAdapter(semantic_client=self.client)
        self._catalog_scopes: dict[str, CatalogRow] = {}

    def create_map(self, *, owner_id: str, topic: str, name: str | None = None, project_id: str | None = None, year_start: int | None = None, year_end: int | None = None, source_ids: Iterable[str] = (), conference_ids: Iterable[str] = (), requested_count: int = 30, idempotency_key: str | None = None) -> CreateMapResult:
        topic = str(topic or "").strip()
        if not 1 <= len(topic) <= 500:
            raise ValueError("TOPIC_REQUIRED")
        requested_count = int(requested_count)
        if requested_count not in ALLOWED_LIMITS:
            raise ValueError("INVALID_LIMIT")
        if year_start is not None and not 1900 <= int(year_start) <= 2100:
            raise ValueError("INVALID_YEARS")
        if year_end is not None and not 1900 <= int(year_end) <= 2100:
            raise ValueError("INVALID_YEARS")
        if year_start is not None and year_end is not None and int(year_start) > int(year_end):
            raise ValueError("INVALID_YEARS")
        if project_id:
            self._validate_project(project_id, owner_id)
        normalized_sources = sorted({canonical_source(item) for item in source_ids if str(item).strip()})
        normalized_conferences = sorted({canonical_conference(item) for item in conference_ids if str(item).strip()})
        if any(item not in SUPPORTED_SOURCE_IDS for item in normalized_sources):
            raise ValueError("INVALID_MAP_SCOPE")
        if any(item not in SUPPORTED_CONFERENCE_IDS for item in normalized_conferences):
            raise ValueError("INVALID_MAP_SCOPE")
        if normalized_sources and normalized_conferences and not compatible_scope_pairs(normalized_sources, normalized_conferences):
            raise ValueError("INVALID_MAP_SCOPE")
        filters = {"year_start": year_start, "year_end": year_end, "source_ids": normalized_sources, "conference_ids": normalized_conferences}
        params_hash = _params_hash({"topic": topic, "name": name, "project_id": project_id, "filters": filters, "requested_count": requested_count})
        atomic_creator = getattr(self.store, "create_map_with_job", None)
        if callable(atomic_creator):
            item, job, created = atomic_creator(
                owner_id,
                topic=topic,
                name=name,
                project_id=project_id,
                filters=filters,
                requested_count=requested_count,
                operation="create",
                idempotency_key=idempotency_key,
                params_hash=params_hash,
            )
        else:
            # Compatibility for narrow test doubles predating the store CAS;
            # production LiteratureMapStore always takes the atomic path.
            item = self.store.create_map(owner_id, topic=topic, name=name, project_id=project_id, filters=filters, requested_count=requested_count)
            job = self.store.create_job(item.map_id, owner_id, operation="create", idempotency_key=idempotency_key, params_hash=params_hash)
            if idempotency_key:
                self.store.bind_map_idempotency(item.map_id, owner_id, idempotency_key, params_hash, job.job_id)
            created = True
        if self.executor is not None and created:
            self.executor.submit(self.run_job, job.job_id, owner_id)
        return CreateMapResult(item, job)

    def run_job(self, job_id: str, owner_id: str | None = None) -> MapJob | None:
        resolved = self.store.get_job_with_owner(job_id) if owner_id is None else None
        if resolved is not None:
            job, owner_id = resolved
        else:
            job = self._find_job(job_id, owner_id)
        if job is None:
            return None
        map_item = self.store.get_map(job.map_id, owner_id or self._owner_for_job(job))
        if map_item is None:
            return None
        owner = owner_id or self._owner_for_job(job)
        claim = getattr(self.store, "claim_job", None)
        if callable(claim):
            claimed = claim(job.job_id, job.map_id, owner)
            if claimed is False or claimed is None:
                current = self.store.get_job(job.job_id, job.map_id, owner)
                if current is None or current.status != "running":
                    return current
                job = current
        elif not self.store.job_can_write(job.job_id, job.map_id, owner):
            return self.store.get_job(job.job_id, job.map_id, owner)
        counts = dict(job.counts)
        failed: list[dict[str, Any]] = list(job.failed_units)
        layers: dict[str, Any] = dict(job.cursor.get("layers", {})) if isinstance(job.cursor.get("layers"), dict) else {}
        layers.setdefault("citation", {"status": "waiting", "error_code": None})
        layers.setdefault("similarity", {"status": "waiting", "error_code": None})
        resume_nodes = self.store.list_nodes(map_item.map_id, owner) if job.step in {"metadata", "references", "similarity"} else []
        step = job.step if resume_nodes else "discover"
        self.store.update_job(job.job_id, job.map_id, owner, status="running", step=step, event_type="started")
        try:
            # A restarted process resumes from durable nodes/checkpoints. A
            # job already past discovery must not spend another search request
            # or create a second identity set.
            nodes = resume_nodes
            selected = nodes
            if nodes:
                counts["node_count"] = len(nodes)
                counts.setdefault("accepted_count", len(nodes))
            else:
                rows, discover_error, provider_requests, provider_count = self._discover_rows(map_item)
                counts["provider_request_count"] = counts.get("provider_request_count", 0) + provider_requests
                if discover_error:
                    failed.append({"unit": "discover", "error_code": discover_error, "retryable": True})
                    layers["citation"] = {"status": "partial", "error_code": discover_error}
                    # A source outage is an explicit partial map state, even
                    # when it happened before the first node was accepted;
                    # callers must not mistake it for a successful empty map.
                    discovery_status = "failed" if discover_error in {"MAP_JOB_INVALID_INPUT", "CATALOG_INVALID_RESPONSE", "SEMANTIC_SCHOLAR_INVALID_RESPONSE"} else "partial"
                    return self._finish(job, owner, counts, failed, layers, status=discovery_status, step="finished")
                counts["provider_count"] = provider_count
                counts["provider_truncated"] = int(provider_count > map_item.requested_count)
                selected = self._select_rows(rows, map_item)
                counts["accepted_count"] = len(selected)
                nodes = [self._to_node(map_item.map_id, row) for row in selected[: map_item.requested_count]]
                self._add_nodes(map_item.map_id, owner, nodes, job.job_id)
                counts["node_count"] = len(self.store.list_nodes(map_item.map_id, owner))
                self._save_checkpoint(job.job_id, map_item.map_id, owner, "discover", "completed", {"accepted_count": len(selected)})
                self.store.update_job(job.job_id, map_item.map_id, owner, step="metadata", counts=counts, cursor={"selected_identities": [node.identity_key for node in nodes], "layers": layers})

            self.store.update_job(job.job_id, map_item.map_id, owner, step="references", counts=counts, cursor={"selected_identities": [node.identity_key for node in nodes], "layers": layers})
            retry_reference_ids = {
                str(item.get("unit")) for item in failed
                if item.get("unit") and item.get("unit") != "discover"
            }
            completed_reference_units = self._completed_units(job.job_id, map_item.map_id, owner)
            pending_reference_ids = {
                node.node_id for node in nodes
                if f"references:{node.node_id}" not in completed_reference_units
            }
            only_reference_ids = retry_reference_ids or pending_reference_ids
            remaining_provider_budget = max(
                0,
                GRAPH_REQUEST_BUDGET - counts.get("provider_request_count", 0),
            )
            citation_edges, graph_failures, graph_requests = self._collect_references(
                owner,
                map_item,
                nodes,
                job_id=job.job_id,
                only_node_ids=only_reference_ids,
                request_budget=remaining_provider_budget,
            )
            counts["provider_request_count"] = counts.get("provider_request_count", 0) + graph_requests
            failed = self._replace_failures(failed, retry_reference_ids, graph_failures)
            if graph_failures:
                layers["citation"] = {"status": "partial", "error_code": graph_failures[0].get("error_code")}
            else:
                layers["citation"] = {"status": "completed", "error_code": None}
            self._add_edges(map_item.map_id, owner, citation_edges, job.job_id)
            counts["citation_edge_count"] = len([edge for edge in self.store.list_edges(map_item.map_id, owner) if edge.kind == "citation"])

            self.store.update_job(job.job_id, map_item.map_id, owner, step="similarity", counts=counts, cursor={"selected_identities": [node.identity_key for node in nodes], "layers": layers})
            similarity_edges, similarity_error = self._collect_similarity(nodes)
            if similarity_error:
                layers["similarity"] = {"status": "unavailable", "error_code": similarity_error}
                failed.append({"unit": "similarity", "error_code": similarity_error, "retryable": True})
                self._save_checkpoint(job.job_id, map_item.map_id, owner, "similarity", "failed", {}, similarity_error)
            else:
                layers["similarity"] = {"status": "completed", "error_code": None}
                self._add_edges(map_item.map_id, owner, similarity_edges, job.job_id)
                counts["similarity_edge_count"] = len([edge for edge in self.store.list_edges(map_item.map_id, owner) if edge.kind == "similarity"])
                self._save_checkpoint(job.job_id, map_item.map_id, owner, "similarity", "completed", {"edge_count": counts["similarity_edge_count"]})
            status = "ready"
            if len(selected) < map_item.requested_count or failed:
                status = "partial" if counts.get("node_count", 0) else "failed"
            return self._finish(job, owner, counts, failed, layers, status=status, step="finished")
        except LookupError:
            # Deleting a map revokes the writer qualification. A worker that
            # was already between checkpoints exits quietly and cannot
            # recreate the tombstoned map.
            if self.store.get_map(job.map_id, owner) is None:
                return None
            failed.append({"unit": "job", "error_code": "MAP_JOB_NOT_FOUND", "retryable": True})
            layers["citation"] = {"status": "partial", "error_code": "MAP_JOB_NOT_FOUND"}
            status = "partial" if counts.get("node_count", 0) else "failed"
            return self._finish(job, owner, counts, failed, layers, status=status, step="finished")
        except ValueError:
            current = self.store.get_map(job.map_id, owner)
            if current is None or current.status == "stopped":
                return None
            failed.append({"unit": "job", "error_code": "MAP_JOB_INVALID_INPUT", "retryable": False})
            layers["citation"] = {"status": "partial", "error_code": "MAP_JOB_INVALID_INPUT"}
            status = "partial" if counts.get("node_count", 0) else "failed"
            return self._finish(job, owner, counts, failed, layers, status=status, step="finished")
        except Exception:
            logger.exception("literature map job failed")
            failed.append({"unit": "job", "error_code": "MAP_JOB_FAILED", "retryable": True})
            return self._finish(job, owner, counts, failed, layers, status="failed", step="finished")

    def recover(self, owner_id: str | None = None) -> int:
        jobs = self.store.recover_jobs(owner_id)
        for job in jobs:
            owner = owner_id or self._owner_for_job(job)
            if job.operation.startswith("preview:"):
                preview_id = str(job.cursor.get("preview_id") or "")
                request = self.store.get_preview_request(job.map_id, preview_id, owner) if preview_id else None
                if request is not None and self.executor is not None:
                    node_id, query = request
                    self.executor.submit(self._run_preview, job.map_id, owner, preview_id, job.operation.split(":", 1)[1], node_id, query)
                continue
            if job.operation == "analysis":
                # MapAnalysisService owns its own CAS/terminal transition;
                # the graph worker must never interpret an analysis row as a
                # discovery job or mutate map.status.
                continue
            if self.executor is not None:
                self.executor.submit(self.run_job, job.job_id, owner)
        return len(jobs)

    def graph(self, map_id: str, owner_id: str) -> dict[str, Any]:
        item = self.store.get_map(map_id, owner_id)
        if item is None:
            raise LookupError("map not found")
        job = self.store.latest_job(map_id, owner_id)
        layers = {"citation": {"status": "waiting", "error_code": None}, "similarity": {"status": "waiting", "error_code": None}}
        if job and isinstance(job.cursor.get("layers"), dict):
            layers.update(job.cursor["layers"])
        return {"schema_version": "literature-map-v1", "map": item.to_dict(), "nodes": [node.to_dict() for node in self.store.list_nodes(map_id, owner_id)], "edges": [edge.to_dict() for edge in self.store.list_edges(map_id, owner_id)], "layers": layers, "latest_job": job.to_dict() if job else None}

    def groups(self, map_id: str, owner_id: str) -> dict[str, Any]:
        item = self.store.get_map(map_id, owner_id)
        if item is None:
            raise LookupError("map not found")
        return _groups_envelope(item, self.store.list_groups(map_id, owner_id))

    def create_group(self, map_id: str, owner_id: str, *, expected_revision: int, name: str, color: str) -> dict[str, Any]:
        self.store.create_group(map_id, owner_id, expected_revision=expected_revision, name=name, color=color)
        return self.groups(map_id, owner_id)

    def update_group(
        self,
        map_id: str,
        group_id: str,
        owner_id: str,
        *,
        expected_revision: int,
        name: str | None = None,
        color: str | None = None,
    ) -> dict[str, Any]:
        self.store.update_group(map_id, group_id, owner_id, expected_revision=expected_revision, name=name, color=color)
        return self.groups(map_id, owner_id)

    def delete_group(self, map_id: str, group_id: str, owner_id: str, *, expected_revision: int) -> dict[str, Any]:
        self.store.delete_group(map_id, group_id, owner_id, expected_revision=expected_revision)
        return self.groups(map_id, owner_id)

    def assign_node_group(
        self,
        map_id: str,
        node_id: str,
        owner_id: str,
        *,
        expected_revision: int,
        group_id: str | None,
    ) -> dict[str, Any]:
        node = self.store.assign_node_group(
            map_id,
            owner_id,
            node_id=node_id,
            expected_revision=expected_revision,
            group_id=group_id,
        )
        item = self.store.get_map(map_id, owner_id)
        if item is None:
            raise LookupError("map not found")
        return {"schema_version": "literature-map-v1", "map_id": map_id, "revision": item.revision, "node": node.to_dict()}

    def export_map(self, map_id: str, owner_id: str) -> dict[str, Any]:
        """Return a portable, read-only export assembled from active map rows.

        Export deliberately does not reuse ``to_dict`` because that projection
        is an internal API and carries owner IDs and unrestricted provenance.
        """

        item = self.store.get_map(map_id, owner_id)
        if item is None:
            raise LookupError("map not found")
        groups = self.store.list_groups(map_id, owner_id)
        all_nodes = self.store.list_nodes(map_id, owner_id)
        active_nodes = [node for node in all_nodes if not node.removed]
        active_ids = {node.node_id for node in active_nodes}
        edges = [edge for edge in self.store.list_edges(map_id, owner_id) if edge.source_id in active_ids and edge.target_id in active_ids]
        return {
            "schema_version": "literature-map-export-v1",
            "exported_at": iso_now(),
            "map": {
                "map_id": item.map_id,
                "name": item.name,
                "topic": item.topic,
                "project_id": item.project_id,
                "filters": _export_filters(item.filters),
                "requested_count": item.requested_count,
                "revision": item.revision,
                "view_settings": _export_view_settings(item.view_settings),
            },
            "groups": [group.to_dict() for group in groups],
            "nodes": [_export_node(node) for node in active_nodes],
            "edges": [_export_edge(edge) for edge in edges],
        }

    def update_map(self, map_id: str, owner_id: str, *, expected_revision: int, name: str | None = None, project_id: str | None | object = _UNSET) -> LiteratureMap:
        if project_id is not _UNSET and project_id:
            self._validate_project(str(project_id), owner_id)
        return self.store.update_map_details(map_id, owner_id, expected_revision=expected_revision, name=name, project_id=project_id)

    def stop_job(self, map_id: str, job_id: str, owner_id: str) -> MapJob:
        job = self.store.get_job(job_id, map_id, owner_id)
        if job is None:
            raise LookupError("job not found")
        if job.status in {"completed", "partial", "failed", "stopped"}:
            # Stop is intentionally idempotent for terminal jobs.  In
            # particular, a completed map must never be rewritten as stopped.
            return job
        store_stop = getattr(self.store, "stop_job", None)
        if callable(store_stop):
            updated = store_stop(job_id, map_id, owner_id)
            if updated is None:
                raise LookupError("job not found")
            return updated
        updated = self.store.update_job(job_id, map_id, owner_id, status="stopped", step=job.step, counts=job.counts, failed_units=job.failed_units, event_type="stopped")
        self.store.set_map_status(map_id, owner_id, "stopped")
        if updated is None:
            raise LookupError("job not found")
        return updated

    def retry_job(self, map_id: str, job_id: str, owner_id: str) -> MapJob:
        job = self.store.get_job(job_id, map_id, owner_id)
        if job is None:
            raise LookupError("job not found")
        if job.status not in {"failed", "partial", "stopped"}:
            raise ValueError("job is not retryable")
        if job.operation == "analysis":
            retry = self.store.retry_job(job_id, map_id, owner_id)
            if retry is None:
                raise ValueError("job is not retryable")
            analysis = getattr(self, "analysis_service", None)
            if analysis is not None and analysis.executor is not None:
                analysis.executor.submit(analysis.run_analysis_job, job_id, owner_id)
            return retry
        nodes = self.store.list_nodes(map_id, owner_id)
        failed_units = [
            item for item in job.failed_units
            if isinstance(item, Mapping) and item.get("retryable") is True
        ]
        if job.failed_units and not failed_units:
            raise ValueError("MAP_NO_RETRYABLE_UNITS")
        retry_step = "discover"
        if any(item.get("unit") == "similarity" for item in failed_units):
            retry_step = "similarity"
        elif nodes and any(item.get("unit") not in {"discover", "similarity"} for item in failed_units):
            retry_step = "references"
        elif nodes and job.step in {"metadata", "references", "similarity"}:
            retry_step = job.step
        retry = getattr(self.store, "retry_job", None)
        if callable(retry):
            try:
                updated = retry(job_id, map_id, owner_id, step=retry_step)
            except TypeError:
                updated = retry(job_id, map_id, owner_id)
            if updated is not None:
                try:
                    updated = self.store.update_job(
                        job_id,
                        map_id,
                        owner_id,
                        step=retry_step,
                        cursor=job.cursor,
                        failed_units=failed_units,
                        event_type="retry_units",
                        expected_status="queued",
                    )
                except TypeError:
                    updated = self.store.update_job(
                        job_id,
                        map_id,
                        owner_id,
                        step=retry_step,
                        cursor=job.cursor,
                        failed_units=failed_units,
                        event_type="retry_units",
                    )
        else:
            self.store.set_map_status(map_id, owner_id, "generating")
            updated = self.store.update_job(job_id, map_id, owner_id, status="queued", step=retry_step, counts=job.counts, cursor=job.cursor, failed_units=failed_units, event_type="retry")
        if updated is None:
            raise LookupError("job not found")
        if self.executor is not None:
            self.executor.submit(self.run_job, job_id, owner_id)
        return updated

    def node(self, map_id: str, node_id: str, owner_id: str) -> MapPaper:
        item = self.store.get_node(map_id, node_id, owner_id)
        if item is None:
            raise LookupError("node not found")
        return item

    def create_preview(
        self,
        map_id: str,
        owner_id: str,
        *,
        kind: str,
        node_id: str | None = None,
        query: str | None = None,
        idempotency_key: str | None = None,
    ) -> MapPreview:
        """Calculate and persist a bounded candidate preview.

        The provider is consulted only from this explicit user action.  The
        durable candidate snapshot is then the sole input to apply, so a
        later provider response cannot silently change what the user confirms.
        """
        if kind not in {"topic", "references", "citations", "refresh"}:
            raise ValueError("INVALID_PREVIEW_KIND")
        map_item = self.store.get_map(map_id, owner_id)
        if map_item is None:
            raise LookupError("map not found")
        source_node = None
        if kind in {"references", "citations"}:
            if not node_id:
                raise ValueError("PREVIEW_NODE_REQUIRED")
            source_node = self.store.get_node(map_id, node_id, owner_id)
            if source_node is None or source_node.removed:
                raise LookupError("node not found")
        params_hash = _params_hash({"kind": kind, "node_id": node_id, "query": query or map_item.topic, "base_revision": map_item.revision})
        if self.executor is not None:
            preview, _, created = self.store.create_preview(
                map_id,
                owner_id,
                kind=kind,
                base_revision=map_item.revision,
                candidates=[],
                diff=[],
                warnings=[],
                node_id=node_id,
                query=query,
                status="queued",
                idempotency_key=idempotency_key,
                params_hash=params_hash,
            )
            if created:
                self.executor.submit(self._run_preview, map_id, owner_id, preview.preview_id, kind, node_id, query)
            return preview
        candidates, diff, warnings, provider_request_count = self._calculate_preview(map_item, owner_id, kind=kind, node_id=node_id, query=query)
        preview, _, _ = self.store.create_preview(
            map_id,
            owner_id,
            kind=kind,
            base_revision=map_item.revision,
            candidates=candidates,
            diff=diff,
            warnings=warnings,
            node_id=node_id,
            query=query,
            idempotency_key=idempotency_key,
            params_hash=params_hash,
            provider_request_count=provider_request_count,
        )
        return preview

    def _run_preview(self, map_id: str, owner_id: str, preview_id: str, kind: str, node_id: str | None, query: str | None) -> None:
        try:
            preview_state = self.store.get_preview(map_id, preview_id, owner_id)
            if preview_state is None:
                return
            _, job = preview_state
            claim = self.store.claim_job(job.job_id, map_id, owner_id)
            if claim is None:
                current = self.store.get_job(job.job_id, map_id, owner_id)
                if current is None or current.status not in {"queued", "running"}:
                    return
                job = current
            checkpoint = self.store.get_unit_checkpoint(job.job_id, map_id, owner_id, "preview:calculate")
            if checkpoint and checkpoint.get("status") == "completed":
                payload = checkpoint.get("payload") or {}
                self.store.complete_preview(map_id, preview_id, owner_id, status="completed", candidates=list(payload.get("candidates") or []), diff=list(payload.get("diff") or []), warnings=list(payload.get("warnings") or []), provider_request_count=int(payload.get("provider_request_count") or 0))
                return
            map_item = self.store.get_map(map_id, owner_id)
            if map_item is None:
                return
            candidates, diff, warnings, provider_request_count = self._calculate_preview(map_item, owner_id, kind=kind, node_id=node_id, query=query)
            self.store.save_unit_checkpoint(job.job_id, map_id, owner_id, unit_key="preview:calculate", status="completed", payload={"candidates": candidates, "diff": diff, "warnings": warnings, "provider_request_count": provider_request_count, "provider_request_budget": max(0, GRAPH_REQUEST_BUDGET - provider_request_count)})
            self.store.complete_preview(map_id, preview_id, owner_id, status="completed", candidates=candidates, diff=diff, warnings=warnings, provider_request_count=provider_request_count)
        except (LookupError, ValueError) as error:
            self.store.complete_preview(map_id, preview_id, owner_id, status="failed", candidates=[], diff=[], warnings=[str(error)], provider_request_count=0)
        except Exception:
            logger.exception("literature map preview failed")
            self.store.complete_preview(map_id, preview_id, owner_id, status="failed", candidates=[], diff=[], warnings=["MAP_PREVIEW_FAILED"], provider_request_count=0)

    def _calculate_preview(self, map_item: LiteratureMap, owner_id: str, *, kind: str, node_id: str | None, query: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], int]:
        map_id = map_item.map_id
        existing = self.store.list_nodes(map_id, owner_id)
        by_identity = {node.identity_key: node for node in existing if node.identity_key}
        candidates: list[dict[str, Any]] = []
        warnings: list[str] = []
        diff: list[dict[str, Any]] = []
        provider_request_count = 0
        if kind == "refresh":
            candidates, diff, warnings, provider_request_count = self._refresh_candidates(existing, by_identity, owner_id)
        elif kind == "topic":
            discovery_map = replace(map_item, topic=str(query).strip()) if str(query or "").strip() else map_item
            rows, error_code, provider_request_count, _ = self._discover_rows(discovery_map)
            if error_code:
                warnings.append(str(error_code))
            for row in rows[:MAX_NODES]:
                candidate_node = self._to_node(map_id, row)
                candidate = self._preview_candidate(candidate_node, by_identity)
                if not any(item.get("candidate_id") == candidate.get("candidate_id") for item in candidates):
                    candidates.append(candidate)
        else:
            source_node = self.store.get_node(map_id, str(node_id), owner_id) if node_id else None
            if source_node is None or source_node.removed:
                raise LookupError("node not found")
            relation = "references" if kind == "references" else "citations"
            graph_result = self._preview_graph(source_node, relation)
            provider_request_count = 1 if graph_result.get("provider_request") else 0
            if graph_result.get("code"):
                warnings.append(str(graph_result["code"]))
            for row in graph_result.get("items", ()):
                candidate_node = self._to_node(map_id, row)
                candidate = self._preview_candidate(candidate_node, by_identity)
                candidate["relation"] = "citation"
                candidate["relation_source_node_id"] = source_node.node_id
                if not any(item.get("candidate_id") == candidate.get("candidate_id") for item in candidates):
                    candidates.append(candidate)
        return candidates[:MAX_NODES], diff, warnings, provider_request_count

    def _refresh_candidates(self, existing: list[MapPaper], by_identity: Mapping[str | None, MapPaper], owner_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], int]:
        active = [node for node in existing if not node.removed]
        identifiers = [node.external_ids.get("semantic_scholar") for node in active if node.external_ids.get("semantic_scholar")]
        rows: list[SemanticScholarMetadata] = []
        warnings: list[str] = []
        provider_request_count = 0
        if identifiers:
            key = self._request_cache_key(provider="semantic_scholar", operation="metadata_batch", identifier="|".join(identifiers), filters={}, page=0)
            payload = self._get_request_cache(key)
            if payload is not None:
                rows = self._parse_search_payload(payload)
            else:
                batch = getattr(self.client, "batch", None)
                if not callable(batch):
                    warnings.append("SEMANTIC_SCHOLAR_METADATA_UNAVAILABLE")
                else:
                    try:
                        provider_request_count += 1
                        result = batch(identifiers, fields=SEMANTIC_SCHOLAR_METADATA_FIELDS)
                        code = getattr(result, "code", None)
                        if code:
                            warnings.append(str(code))
                        else:
                            payload = getattr(result, "payload", result)
                            rows = self._parse_search_payload(payload)
                            if rows:
                                self._put_request_cache(key, payload)
                    except (TypeError, ValueError, OSError):
                        warnings.append("SEMANTIC_SCHOLAR_INVALID_RESPONSE")
        by_provider = {row.paper_id: row for row in rows}
        candidates: list[dict[str, Any]] = []
        diff: list[dict[str, Any]] = []
        candidate_by_node: dict[str, dict[str, Any]] = {}
        for node in active:
            row = by_provider.get(node.external_ids.get("semantic_scholar"))
            refreshed = node
            if row is not None:
                # A partial provider response is not permission to erase a
                # value already curated or imported into the map.  Preserve
                # the local value when the provider omits it (empty author or
                # venue lists are treated as omitted as well).
                refreshed = replace(
                    node,
                    title=row.title or node.title,
                    authors=row.authors or node.authors,
                    year=row.year if row.year is not None else node.year,
                    venue=row.venue or node.venue,
                    abstract=row.abstract if row.abstract is not None else node.abstract,
                    citation_count=row.citation_count if row.citation_count is not None else node.citation_count,
                )
            candidate = self._preview_candidate(refreshed, by_identity)
            candidate["relation_targets"] = []
            candidates.append(candidate)
            candidate_by_node[node.node_id] = candidate
            changes: dict[str, Any] = {}
            for field in ("title", "authors", "year", "venue", "abstract", "citation_count"):
                before = getattr(node, field)
                after = getattr(refreshed, field)
                before_value = list(before) if isinstance(before, tuple) else before
                after_value = list(after) if isinstance(after, tuple) else after
                if before_value != after_value:
                    changes[field] = {"from": before_value, "to": after_value}
            if changes:
                diff.append({"node_id": node.node_id, "changes": changes})
        # Refresh relation checks are bounded by the same per-job budget as
        # initial graph construction.  A provider miss is a warning, never a
        # deletion, so an outage cannot erase user-visible relations.
        current_edges = {(edge.source_id, edge.target_id) for edge in self.store.list_edges(active[0].map_id, owner_id) if edge.kind == "citation"} if active else set()
        by_provider_node = {node.external_ids.get("semantic_scholar"): node for node in active if node.external_ids.get("semantic_scholar")}
        relation_diff: dict[str, dict[str, Any]] = {}
        for node in active:
            if provider_request_count >= GRAPH_REQUEST_BUDGET:
                warnings.append("MAP_GRAPH_BUDGET_EXCEEDED")
                break
            result = self._preview_graph(node, "references")
            if result.get("provider_request"):
                provider_request_count += 1
            if result.get("code"):
                if str(result["code"]) not in warnings:
                    warnings.append(str(result["code"]))
                continue
            target_ids: list[str] = []
            for row in result.get("items", ()):
                target = by_provider_node.get(row.paper_id)
                if target is None or target.node_id == node.node_id or not target.identity_key:
                    continue
                target_ids.append(target.identity_key)
                if (node.node_id, target.node_id) not in current_edges:
                    relation_diff.setdefault(node.node_id, {"added": [], "removed": []})["added"].append(target.identity_key)
            candidate = candidate_by_node.get(node.node_id)
            if candidate is not None:
                candidate["relation_targets"] = sorted(set(target_ids))
        for node_id, changes in relation_diff.items():
            diff.append({"node_id": node_id, "changes": {"relations": changes}})
        return candidates, diff, warnings, provider_request_count

    def get_preview(self, map_id: str, preview_id: str, owner_id: str) -> tuple[MapPreview, MapJob]:
        result = self.store.get_preview(map_id, preview_id, owner_id)
        if result is None:
            raise LookupError("preview not found")
        return result

    def apply_preview(
        self,
        map_id: str,
        preview_id: str,
        owner_id: str,
        *,
        expected_revision: int,
        selected_candidate_ids: list[str],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        preview, _ = self.get_preview(map_id, preview_id, owner_id)
        if len(selected_candidate_ids) != len(set(selected_candidate_ids)):
            raise ValueError("INVALID_PREVIEW_CANDIDATE")
        candidate_by_id = {str(item.get("candidate_id")): item for item in preview.candidates if isinstance(item, Mapping)}
        selected: list[Mapping[str, Any]] = []
        if preview.kind == "refresh" and not selected_candidate_ids:
            # The refresh contract uses an empty selection as confirmation of
            # every server-computed diff.  Derive the set from the persisted
            # preview, never from client-provided fields.  Relation additions
            # are represented in the same node diff and are therefore applied
            # together with metadata changes.
            diff_node_ids = {
                str(item.get("node_id"))
                for item in preview.diff
                if isinstance(item, Mapping) and item.get("node_id")
            }
            selected = [
                candidate
                for candidate in preview.candidates
                if isinstance(candidate, Mapping)
                and candidate.get("node_id")
                and str(candidate.get("node_id")) in diff_node_ids
                and not candidate.get("removed")
            ]
        else:
            for candidate_id in selected_candidate_ids:
                candidate = candidate_by_id.get(candidate_id)
                if candidate is None or (preview.kind != "refresh" and candidate.get("already_present")) or candidate.get("removed"):
                    raise ValueError("INVALID_PREVIEW_CANDIDATE")
                selected.append(candidate)
        if preview.kind != "refresh" and len(selected) > 20:
            raise ValueError("PREVIEW_BATCH_LIMIT")
        effective_candidate_ids = [str(candidate.get("candidate_id")) for candidate in selected]
        nodes: list[MapPaper] = []
        updates: list[MapPaper] = []
        relations: list[tuple[str, str, str]] = []
        for candidate in selected:
            node = self._candidate_node(map_id, candidate)
            if preview.kind == "refresh":
                current = self.store.get_node(map_id, str(candidate.get("node_id")), owner_id)
                if current is None or current.removed:
                    raise ValueError("INVALID_PREVIEW_CANDIDATE")
                if current.identity_key != node.identity_key:
                    raise ValueError("INVALID_PREVIEW_CANDIDATE")
                node = replace(node, node_id=current.node_id, identity_key=current.identity_key, position=current.position, group_id=current.group_id, document_id=current.document_id, download_status=current.download_status, catalog_paper_id=current.catalog_paper_id)
                updates.append(node)
            else:
                nodes.append(node)
            if preview.kind in {"references", "citations"}:
                relation_source = str(candidate.get("relation_source_node_id") or "")
                if relation_source:
                    if preview.kind == "references":
                        relations.append(("citation", relation_source, node.identity_key or ""))
                    else:
                        relations.append(("citation", node.identity_key or "", relation_source))
            if preview.kind == "refresh":
                for target_identity in candidate.get("relation_targets", ()):
                    relations.append(("citation", node.node_id, str(target_identity)))
        params_hash = _params_hash({"preview_id": preview_id, "expected_revision": expected_revision, "selected": selected_candidate_ids})
        result = self.store.apply_preview(
            map_id,
            owner_id,
            preview_id=preview_id,
            expected_revision=expected_revision,
            selected_candidate_ids=effective_candidate_ids,
            nodes=nodes,
            relations=relations,
            updates=updates,
            idempotency_key=idempotency_key,
            params_hash=params_hash,
        )
        if nodes and self.embedder is not None:
            active_nodes = [item for item in self.store.list_nodes(map_id, owner_id) if not item.removed]
            similarity_edges, _ = self._collect_similarity(active_nodes)
            if similarity_edges:
                self.store.add_edges(map_id, owner_id, similarity_edges)
        return result

    def remove_node(self, map_id: str, node_id: str, owner_id: str, *, expected_revision: int, idempotency_key: str | None = None) -> dict[str, Any]:
        return self.store.remove_node(map_id, node_id, owner_id, expected_revision=expected_revision, idempotency_key=idempotency_key, params_hash=_params_hash({"node_id": node_id, "expected_revision": expected_revision}))

    def restore_node(self, map_id: str, node_id: str, owner_id: str, *, expected_revision: int, idempotency_key: str | None = None) -> dict[str, Any]:
        return self.store.restore_node(map_id, node_id, owner_id, expected_revision=expected_revision, idempotency_key=idempotency_key, params_hash=_params_hash({"node_id": node_id, "expected_revision": expected_revision}))

    @staticmethod
    def _preview_candidate(node: MapPaper, existing: Mapping[str | None, MapPaper]) -> dict[str, Any]:
        identity = node.identity_key or deterministic_identity_key(node.external_ids)
        candidate_id = "candidate-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
        prior = existing.get(identity)
        return {
            "candidate_id": candidate_id,
            "identity_key": identity,
            "node_id": prior.node_id if prior else None,
            "title": node.title,
            "authors": list(node.authors),
            "year": node.year,
            "venue": node.venue,
            "abstract": node.abstract,
            "keywords": list(node.keywords),
            "citation_count": node.citation_count,
            "external_ids": dict(node.external_ids),
            "source_url": node.source_url,
            "provenance": dict(node.provenance),
            "catalog_paper_id": node.catalog_paper_id,
            "already_present": prior is not None and not prior.removed,
            "removed": bool(prior and prior.removed),
        }

    @staticmethod
    def _candidate_node(map_id: str, candidate: Mapping[str, Any]) -> MapPaper:
        return MapPaper.new(
            map_id,
            external_ids=dict(candidate.get("external_ids") or {}),
            title=str(candidate.get("title") or "").strip(),
            authors=tuple(str(item) for item in candidate.get("authors", ()) if str(item).strip()),
            year=candidate.get("year"),
            venue=candidate.get("venue"),
            abstract=candidate.get("abstract"),
            keywords=tuple(str(item) for item in candidate.get("keywords", ()) if str(item).strip()),
            citation_count=candidate.get("citation_count"),
            source_url=candidate.get("source_url"),
            provenance=dict(candidate.get("provenance") or {}),
            catalog_paper_id=candidate.get("catalog_paper_id"),
        )

    def _preview_graph(self, node: MapPaper, relation: str) -> dict[str, Any]:
        provider_id = node.external_ids.get("semantic_scholar")
        if not provider_id:
            return {"code": "SEMANTIC_SCHOLAR_NO_ID", "items": (), "cache_hit": False, "provider_request": False}
        try:
            result = self._cached_graph_request(provider_id, 0, relation=relation)
        except (TypeError, ValueError, OSError):
            return {"code": "SEMANTIC_SCHOLAR_UNAVAILABLE", "items": (), "cache_hit": False, "provider_request": True}
        if result.get("code"):
            return {"code": str(result["code"]), "items": (), "cache_hit": bool(result.get("cache_hit")), "provider_request": not bool(result.get("cache_hit"))}
        page = result.get("graph_page")
        if not isinstance(page, SemanticScholarGraphPage):
            return {"code": "SEMANTIC_SCHOLAR_INVALID_RESPONSE", "items": (), "cache_hit": bool(result.get("cache_hit")), "provider_request": not bool(result.get("cache_hit"))}
        return {"code": None, "items": page.items, "cache_hit": bool(result.get("cache_hit")), "provider_request": not bool(result.get("cache_hit"))}

    def detach_project(self, project_id: str, owner_id: str) -> int:
        # This method is deliberately owner scoped and transactional; callers
        # must invoke it before deleting the project and fail closed on error.
        return self.store.detach_project(project_id, owner_id)

    def import_node(self, map_id: str, node_id: str, owner_id: str, *, source_url: str | None = None) -> Mapping[str, Any]:
        node = self.node(map_id, node_id, owner_id)
        source_url = source_url or node.source_url
        if not source_url:
            raise ValueError("IMPORT_URL_UNSAFE")
        parsed = urlsplit(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("IMPORT_URL_UNSAFE")
        if self.import_bridge is None:
            raise RuntimeError("IMPORT_BRIDGE_UNAVAILABLE")
        return dict(self.import_bridge(node, source_url))

    def _discover_rows(self, map_item: LiteratureMap) -> tuple[list[SemanticScholarMetadata], str | None, int, int]:
        filters = map_item.filters
        source_ids = tuple(filters.get("source_ids", ()))
        conference_ids = tuple(filters.get("conference_ids", ()))
        if source_ids or conference_ids:
            adapter = self.catalog_adapter
            if adapter is None:
                return [], "CATALOG_SOURCE_UNAVAILABLE", 0, 0
            try:
                result = adapter.search(
                    query=map_item.topic,
                    source_ids=source_ids,
                    conference_ids=conference_ids,
                    year_start=filters.get("year_start"),
                    year_end=filters.get("year_end"),
                    limit=map_item.requested_count,
                )
            except (TypeError, ValueError):
                return [], "CATALOG_INVALID_RESPONSE", 0, 0
            rows: list[SemanticScholarMetadata] = []
            for item in result or ():
                catalog_row = item if isinstance(item, CatalogRow) else CatalogRow(item)
                metadata = catalog_row.metadata
                if isinstance(metadata, Mapping):
                    parsed = self._parse_search_payload([metadata])
                    metadata = parsed[0] if parsed else None
                if not isinstance(metadata, SemanticScholarMetadata):
                    continue
                scope_source = canonical_source(catalog_row.source_id) if catalog_row.source_id else None
                scope_conference = canonical_conference(catalog_row.conference_id) if catalog_row.conference_id else None
                if source_ids and scope_source not in source_ids:
                    continue
                if conference_ids and scope_conference not in conference_ids:
                    continue
                if catalog_row.source_id != scope_source or catalog_row.conference_id != scope_conference:
                    catalog_row = CatalogRow(
                        metadata=catalog_row.metadata,
                        source_id=scope_source,
                        conference_id=scope_conference,
                        source_kind=catalog_row.source_kind,
                        catalog_paper_id=catalog_row.catalog_paper_id,
                        official_page_url=catalog_row.official_page_url,
                        official_pdf_url=catalog_row.official_pdf_url,
                        prepublication_pdf_url=catalog_row.prepublication_pdf_url,
                        doi=catalog_row.doi,
                        arxiv_id=catalog_row.arxiv_id,
                        snapshot=catalog_row.snapshot,
                    )
                self._catalog_scopes[metadata.paper_id] = catalog_row
                rows.append(metadata)
            official_error = getattr(adapter, "last_error", None) if not rows else None
            if len(rows) >= map_item.requested_count:
                return rows[: map_item.requested_count], official_error, 0, len(rows)

            # The official catalog remains authoritative.  A bounded S2 query
            # is allowed only to inspect/enrich the gap; a venue string is not
            # scope proof, so unmatched S2 rows are never admitted to a scoped
            # map.  This also records the provider's actual response count
            # when it ignores the requested limit.
            gap = map_item.requested_count - len(rows)
            search_key = self._request_cache_key(
                provider="semantic_scholar",
                operation="search_scope_gap",
                query=map_item.topic,
                identifier="",
                filters={
                    "year_start": filters.get("year_start"),
                    "year_end": filters.get("year_end"),
                    "limit": gap,
                    "source_ids": list(source_ids),
                    "conference_ids": list(conference_ids),
                },
                page=0,
            )
            cached = self._get_request_cache(search_key)
            provider_requests = 0
            supplemental: list[SemanticScholarMetadata] = []
            if cached is not None:
                try:
                    supplemental = self._parse_search_payload(cached)
                except (TypeError, ValueError):
                    supplemental = []
            else:
                try:
                    try:
                        result = self.client.search_bulk(map_item.topic, limit=gap, fields=SEMANTIC_SCHOLAR_METADATA_FIELDS)
                    except TypeError as error:
                        if "fields" not in str(error):
                            raise
                        result = self.client.search_bulk(map_item.topic, limit=gap)
                    provider_requests = 1
                except (TypeError, ValueError):
                    result = None
                if result is not None:
                    code = getattr(result, "code", None)
                    if not code:
                        payload = getattr(result, "payload", result)
                        try:
                            supplemental = self._parse_search_payload(payload)
                        except (TypeError, ValueError):
                            supplemental = []
                        if supplemental:
                            self._put_request_cache(search_key, payload)
                    else:
                        supplement_error = str(code)
                        if rows:
                            # Official rows remain usable when the bounded
                            # supplement is rate-limited or unavailable; the
                            # resulting shortfall is represented as partial,
                            # not as an empty discovery failure.
                            return rows, None, provider_requests, len(rows)
                        return rows, supplement_error, provider_requests, len(rows)

            # Only an identity match to an already attested catalog row can
            # enrich a row.  Keep all official fields and never append generic
            # S2 hits merely because their venue happens to look familiar.
            for index, official in enumerate(rows):
                candidate = next((item for item in supplemental if self._same_paper_identity(item, official)), None)
                if candidate is None:
                    continue
                # Enrichment is fill-only: catalog title/authors/year/abstract
                # and official provenance remain authoritative, while a real
                # DOI/arXiv identity match can supply missing S2 metadata.
                enriched = replace(
                    official,
                    authors=official.authors or candidate.authors,
                    year=official.year or candidate.year,
                    doi=official.doi or candidate.doi,
                    arxiv_id=official.arxiv_id or candidate.arxiv_id,
                    abstract=official.abstract or candidate.abstract,
                    citation_count=official.citation_count if official.citation_count is not None else candidate.citation_count,
                    venue=official.venue or candidate.venue,
                )
                rows[index] = enriched
                scope = self._catalog_scopes.get(official.paper_id)
                if scope is not None and (scope.doi is None or scope.arxiv_id is None):
                    self._catalog_scopes[official.paper_id] = replace(
                        scope,
                        doi=scope.doi or candidate.doi,
                        arxiv_id=scope.arxiv_id or candidate.arxiv_id,
                    )
            if rows:
                # A sparse official result is still useful and is deliberately
                # persisted as a partial map. Unverified supplement rows are
                # dropped, while the selected-count shortfall drives the
                # terminal partial status after graph/similarity layers run.
                return rows, None, provider_requests, len(rows) + len(supplemental)
            return [], official_error or "CATALOG_SCOPE_UNVERIFIED", provider_requests, len(supplemental)

        cache_key = self._request_cache_key(
            provider="semantic_scholar",
            operation="search_relevance",
            query=map_item.topic,
            identifier="",
            filters={"year_start": filters.get("year_start"), "year_end": filters.get("year_end"), "limit": map_item.requested_count},
            page=0,
        )
        cached = self._get_request_cache(cache_key)
        if cached is not None:
            rows = self._parse_search_payload(cached)
            return rows, None, 0, len(rows)
        try:
            try:
                search_relevance = getattr(self.client, "search_relevance", None)
                if callable(search_relevance):
                    result = search_relevance(map_item.topic, limit=map_item.requested_count, fields=SEMANTIC_SCHOLAR_METADATA_FIELDS)
                else:
                    # Narrow compatibility for test doubles and older injected
                    # clients; production uses the relevance-ranked endpoint.
                    result = self.client.search_bulk(map_item.topic, limit=map_item.requested_count, fields=SEMANTIC_SCHOLAR_METADATA_FIELDS)
            except TypeError as error:
                if "fields" not in str(error):
                    raise
                search_relevance = getattr(self.client, "search_relevance", None)
                if callable(search_relevance):
                    result = search_relevance(map_item.topic, limit=map_item.requested_count)
                else:
                    result = self.client.search_bulk(map_item.topic, limit=map_item.requested_count)
        except (TypeError, ValueError):
            return [], "MAP_JOB_INVALID_INPUT", 1, 0
        code = getattr(result, "code", None)
        if code:
            return [], str(code), 1, 0
        payload = getattr(result, "payload", result)
        rows = self._parse_search_payload(payload)
        if rows:
            self._put_request_cache(cache_key, payload)
        return rows, None, 1, len(rows)

    def _request_cache_key(self, *, provider: str, operation: str, query: str = "", identifier: str = "", filters: Mapping[str, Any] | None = None, page: int = 0) -> Any:
        builder = getattr(self.store, "request_cache_key", None)
        if not callable(builder):
            return None
        return builder(
            provider=provider,
            operation=operation,
            query=query,
            identifier=identifier,
            filters=dict(filters or {}),
            page=page,
            fields=SEMANTIC_SCHOLAR_METADATA_FIELDS,
            version=REQUEST_CACHE_VERSION,
        )

    def _get_request_cache(self, key: Any) -> Any:
        getter = getattr(self.store, "get_request_cache", None)
        if key is None or not callable(getter):
            return None
        try:
            return getter(key)
        except (TypeError, ValueError):
            return None

    def _put_request_cache(self, key: Any, payload: Any) -> None:
        writer = getattr(self.store, "put_request_cache", None)
        if key is None or not callable(writer):
            return
        try:
            writer(key, payload, ttl_seconds=REQUEST_CACHE_TTL_SECONDS, status="success")
        except (TypeError, ValueError):
            return

    def _cached_graph_request(self, provider_id: str, offset: int, relation: str = "references") -> dict[str, Any]:
        key = self._request_cache_key(
            provider="semantic_scholar",
            operation=relation,
            identifier=provider_id,
            filters={"limit": REFERENCES_PER_NODE},
            page=offset,
        )
        cached = self._get_request_cache(key)
        if cached is not None:
            page = self._cached_graph_page(cached, provider_id, offset, relation=relation)
            if page is None:
                return {"code": "SEMANTIC_SCHOLAR_INVALID_RESPONSE", "retryable": False, "cache_hit": True}
            return {"code": None, "graph_page": page, "cache_hit": True}
        try:
            try:
                result = self.client.graph_edges(provider_id, relation, limit=REFERENCES_PER_NODE, offset=offset, fields=SEMANTIC_SCHOLAR_METADATA_FIELDS)
            except TypeError as error:
                if "fields" not in str(error):
                    raise
                result = self.client.graph_edges(provider_id, relation, limit=REFERENCES_PER_NODE, offset=offset)
        except (TypeError, ValueError):
            return {"code": "SEMANTIC_SCHOLAR_INVALID_RESPONSE", "retryable": False, "cache_hit": False}
        code = getattr(result, "code", None)
        if code:
            return {"code": str(code), "retryable": bool(getattr(result, "retryable", False)), "cache_hit": False}
        page = getattr(result, "graph_page", None)
        if page is None:
            page = self.client.parse_graph_page(getattr(result, "payload", None), relation, provider_id, offset=offset) if hasattr(self.client, "parse_graph_page") else None
        if not isinstance(page, SemanticScholarGraphPage):
            return {"code": "SEMANTIC_SCHOLAR_INVALID_RESPONSE", "retryable": False, "cache_hit": False}
        self._put_request_cache(key, self._graph_page_payload(page))
        return {"code": None, "graph_page": page, "cache_hit": False}

    @staticmethod
    def _graph_page_payload(page: SemanticScholarGraphPage) -> dict[str, Any]:
        return {
            "relation": page.relation,
            "source_paper_id": page.source_paper_id,
            "offset": page.offset,
            "next_offset": page.next_offset,
            "total": page.total,
            "items": [
                {"paperId": item.paper_id, "title": item.title, "abstract": item.abstract, "year": item.year,
                 "authors": [{"name": author} for author in item.authors], "venue": item.venue,
                 "citationCount": item.citation_count, "url": item.source_url,
                 "externalIds": {key: value for key, value in {"DOI": item.doi, "ArXiv": item.arxiv_id}.items() if value}}
                for item in page.items
            ],
        }

    @staticmethod
    def _cached_graph_page(payload: Any, provider_id: str, offset: int, *, relation: str = "references") -> SemanticScholarGraphPage | None:
        if not isinstance(payload, Mapping):
            return None
        if payload.get("relation") == relation and isinstance(payload.get("items"), list):
            items = tuple(item for item in LiteratureMapService._parse_search_payload(payload.get("items", ())))
            return SemanticScholarGraphPage(relation, str(payload.get("source_paper_id") or provider_id), items, int(payload.get("offset", offset)), payload.get("next_offset"), payload.get("total"))
        return None

    @staticmethod
    def _replace_failures(previous: list[dict[str, Any]], attempted: set[str], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not attempted:
            return previous + current
        retained = [item for item in previous if str(item.get("unit")) not in attempted]
        return retained + current

    def _completed_units(self, job_id: str, map_id: str, owner: str) -> set[str]:
        getter = getattr(self.store, "completed_units", None)
        if not callable(getter):
            return set()
        try:
            return set(getter(job_id, map_id, owner))
        except (LookupError, TypeError, ValueError):
            return set()

    def _save_checkpoint(self, job_id: str, map_id: str, owner: str, unit_key: str, status: str, payload: Mapping[str, Any], error_code: str | None = None) -> None:
        saver = getattr(self.store, "save_unit_checkpoint", None)
        if not callable(saver):
            return
        try:
            saver(job_id, map_id, owner, unit_key=unit_key, status=status, payload=payload, error_code=error_code)
        except (LookupError, TypeError, ValueError):
            # A concurrent stop/delete revokes the checkpoint write.  The
            # caller's map/job qualification remains the source of truth.
            return

    def _add_nodes(self, map_id: str, owner: str, nodes: list[MapPaper], job_id: str) -> None:
        try:
            self.store.add_nodes(map_id, owner, nodes, job_id=job_id)
        except TypeError as error:
            if "job_id" not in str(error):
                raise
            self.store.add_nodes(map_id, owner, nodes)

    def _add_edges(self, map_id: str, owner: str, edges: list[MapEdge], job_id: str) -> None:
        try:
            self.store.add_edges(map_id, owner, edges, job_id=job_id)
        except TypeError as error:
            if "job_id" not in str(error):
                raise
            self.store.add_edges(map_id, owner, edges)

    def _finish(self, job: MapJob, owner: str, counts: dict[str, int], failed: list[dict[str, Any]], layers: dict[str, Any], *, status: str, step: str) -> MapJob | None:
        map_status = "partial" if status == "partial" else ("failed" if status == "failed" else status)
        error_code = next((str(item.get("error_code")) for item in failed if item.get("error_code")), None)
        job_status = {"ready": "completed", "partial": "partial", "failed": "failed"}.get(status, status)
        cursor = {"layers": layers, "resume_step": step}
        finalizer = getattr(self.store, "finish_job", None) or getattr(self.store, "atomic_finish", None)
        if callable(finalizer):
            # Store CAS owns the running->terminal transition, map status and
            # terminal event in one transaction. A losing stop/delete or a
            # duplicate worker therefore returns None without resurrection.
            return finalizer(
                job.job_id,
                job.map_id,
                owner,
                status=job_status,
                map_status=map_status,
                step=step,
                counts=counts,
                failed_units=failed,
                cursor=cursor,
                error_code=error_code,
                event_type="completed" if status in {"ready", "partial"} else "failed",
            )
        # Compatibility for old, narrow test doubles only. Production store
        # exposes finish_job/atomic_finish and never enters this branch.
        map_item = self.store.get_map(job.map_id, owner)
        if map_item is None:
            return None
        current = self.store.get_job(job.job_id, job.map_id, owner)
        if current is not None and current.status in {"completed", "failed", "stopped"} and current.status != "running":
            return current
        self.store.set_map_status(job.map_id, owner, map_status)
        return self.store.update_job(job.job_id, job.map_id, owner, status=job_status, step=step, counts=counts, failed_units=failed, cursor=cursor, error_code=error_code, event_type="completed" if status in {"ready", "partial"} else "failed")

    def _collect_references(self, owner: str, map_item: LiteratureMap, nodes: list[MapPaper], *, job_id: str | None = None, only_node_ids: set[str] | None = None, request_budget: int = GRAPH_REQUEST_BUDGET) -> tuple[list[MapEdge], list[dict[str, Any]], int]:
        by_external = {node.external_ids.get("semantic_scholar"): node for node in nodes if node.external_ids.get("semantic_scholar")}
        edges: list[MapEdge] = []
        failures: list[dict[str, Any]] = []
        request_count = 0
        for node in nodes:
            if only_node_ids is not None and node.node_id not in only_node_ids:
                continue
            provider_id = node.external_ids.get("semantic_scholar")
            if not provider_id:
                continue
            offset = 0
            seen_items = 0
            failure_start = len(failures)
            while True:
                if request_count >= max(0, int(request_budget)):
                    failures.append({"unit": node.node_id, "error_code": "MAP_GRAPH_BUDGET_EXCEEDED", "retryable": False})
                    break
                result = self._cached_graph_request(provider_id, offset)
                if not result.get("cache_hit"):
                    request_count += 1
                code = result.get("code")
                if code:
                    failures.append({"unit": node.node_id, "error_code": str(code), "retryable": bool(result.get("retryable", False))})
                    break
                page = result.get("graph_page")
                if not isinstance(page, SemanticScholarGraphPage):
                    failures.append({"unit": node.node_id, "error_code": "SEMANTIC_SCHOLAR_INVALID_RESPONSE", "retryable": False})
                    break
                for paper in page.items[: max(0, REFERENCES_PER_NODE - seen_items)]:
                    cited = by_external.get(paper.paper_id)
                    if cited is not None and cited.node_id != node.node_id:
                        edges.append(MapEdge.new(map_item.map_id, "citation", node.node_id, cited.node_id, provenance={"provider": "semantic_scholar", "relation": "references", "source_paper_id": provider_id}))
                seen_items += len(page.items)
                if page.next_offset is None or seen_items >= REFERENCES_PER_NODE:
                    if page.next_offset is not None and page.total is not None and page.next_offset < page.total:
                        failures.append({"unit": node.node_id, "error_code": "MAP_REFERENCES_TRUNCATED", "retryable": False})
                    break
                if page.next_offset <= offset:
                    failures.append({"unit": node.node_id, "error_code": "SEMANTIC_SCHOLAR_INVALID_RESPONSE", "retryable": False})
                    break
                offset = page.next_offset
            if job_id:
                node_failures = failures[failure_start:]
                if node_failures:
                    first_code = str(node_failures[0].get("error_code"))
                    checkpoint_status = "partial" if first_code == "MAP_REFERENCES_TRUNCATED" else "failed"
                    self._save_checkpoint(job_id, map_item.map_id, owner, f"references:{node.node_id}", checkpoint_status, {"request_count": request_count}, first_code)
                else:
                    self._save_checkpoint(job_id, map_item.map_id, owner, f"references:{node.node_id}", "completed", {"request_count": request_count})
        return edges, failures, request_count

    def _collect_similarity(self, nodes: list[MapPaper]) -> tuple[list[MapEdge], str | None]:
        if not nodes:
            return [], None
        embedder = self.embedder
        if embedder is None:
            from backend.app.knowledge_base.infrastructure.embed import embed_texts

            embedder = embed_texts
        basis = "title_abstract"
        model_version = str(getattr(embedder, "model_version", "bge-m3"))
        vectors_by_node: dict[str, list[float]] = {}
        missing_nodes: list[MapPaper] = []
        for node in nodes:
            cached = self.store.get_embedding(model_version=model_version, basis=basis, content_hash=content_hash(node.title, node.abstract))
            if cached is None:
                missing_nodes.append(node)
            elif is_valid_vector(cached):
                vectors_by_node[node.node_id] = [float(item) for item in cached]
            else:
                return [], "EMBEDDING_INVALID_RESPONSE"
        expected_dimension = len(next(iter(vectors_by_node.values()))) if vectors_by_node else None
        texts = [f"{node.title}\n{node.abstract or ''}".strip() for node in missing_nodes]
        try:
            vectors = embedder(texts) if texts else []
        except Exception:
            return [], "EMBEDDING_UNAVAILABLE"
        if not isinstance(vectors, list) or len(vectors) != len(missing_nodes):
            return [], "EMBEDDING_INVALID_RESPONSE"
        for node, vector in zip(missing_nodes, vectors, strict=True):
            if not is_valid_vector(vector, dimension=expected_dimension):
                return [], "EMBEDDING_INVALID_RESPONSE"
            vector_value = [float(item) for item in vector]
            expected_dimension = expected_dimension or len(vector_value)
            vectors_by_node[node.node_id] = vector_value
        if expected_dimension is None or any(not is_valid_vector(vector, dimension=expected_dimension) for vector in vectors_by_node.values()):
            return [], "EMBEDDING_INVALID_RESPONSE"
        for node in missing_nodes:
            vector_value = vectors_by_node[node.node_id]
            try:
                self.store.put_embedding(model_version=model_version, basis=basis, content_hash=content_hash(node.title, node.abstract), vector=vector_value)
            except (TypeError, ValueError, OverflowError):
                return [], "EMBEDDING_INVALID_RESPONSE"
        return build_similarity_edges(nodes, vectors_by_node, threshold=SIMILARITY_THRESHOLD, top_k=3, model_version=model_version, basis=basis), None

    @staticmethod
    def _parse_search_payload(payload: Any) -> list[SemanticScholarMetadata]:
        if isinstance(payload, list) and all(isinstance(item, SemanticScholarMetadata) for item in payload):
            return list(payload)
        return list(SemanticScholarGraphClient.parse_search_results(payload))

    @staticmethod
    def _same_paper_identity(left: SemanticScholarMetadata, right: SemanticScholarMetadata) -> bool:
        def normalized(value: object) -> str:
            return " ".join(str(value or "").casefold().strip().split())

        left_doi = normalized(left.doi).removeprefix("https://doi.org/")
        right_doi = normalized(right.doi).removeprefix("https://doi.org/")
        if left_doi and right_doi:
            return left_doi == right_doi
        left_arxiv = normalized(left.arxiv_id).removeprefix("arxiv:")
        right_arxiv = normalized(right.arxiv_id).removeprefix("arxiv:")
        if left_arxiv and right_arxiv:
            return left_arxiv == right_arxiv
        if normalized(left.title) != normalized(right.title):
            return False
        return left.year is None or right.year is None or left.year == right.year

    @staticmethod
    def _safe_url(value: object) -> str | None:
        if not value:
            return None
        candidate = str(value).strip()
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            return None
        return candidate

    @classmethod
    def _safe_catalog_snapshot(cls, snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
        if not isinstance(snapshot, Mapping):
            return {}
        blocked = {"authorization", "headers", "raw_html", "pdf_bytes", "secret", "token"}

        def sanitize(key: str, value: Any) -> Any:
            if key.casefold() in blocked:
                return None
            if key.casefold().endswith("url") or key.casefold() in {"url", "article_url", "page_url"}:
                return cls._safe_url(value)
            if isinstance(value, Mapping):
                return {
                    str(child_key): child_value
                    for child_key, child in value.items()
                    if (child_value := sanitize(str(child_key), child)) is not None
                }
            if isinstance(value, (list, tuple)):
                return [child_value for child in value if (child_value := sanitize(key, child)) is not None]
            if isinstance(value, (str, int, float, bool)) or value is None:
                return value
            return None

        return {
            str(key): value
            for key, item in snapshot.items()
            if (value := sanitize(str(key), item)) is not None
        }

    def _select_rows(self, rows: list[SemanticScholarMetadata], map_item: LiteratureMap) -> list[SemanticScholarMetadata]:
        filters = map_item.filters
        year_start, year_end = filters.get("year_start"), filters.get("year_end")
        source_ids = set(filters.get("source_ids", ()))
        conference_ids = set(filters.get("conference_ids", ()))
        dedup: dict[str, SemanticScholarMetadata] = {}
        for row in rows:
            if year_start is not None and (row.year is None or row.year < year_start):
                continue
            if year_end is not None and (row.year is None or row.year > year_end):
                continue
            scope = self._catalog_scopes.get(row.paper_id)
            # S2 venue is deliberately not used as conference proof.  Rows
            # entering a scoped map must carry an attestation from the catalog
            # adapter; an unscoped S2 result is rejected rather than mislabeled.
            if source_ids and (scope is None or scope.source_id not in source_ids):
                continue
            if conference_ids and (scope is None or scope.conference_id not in conference_ids):
                continue
            key = deterministic_identity_key({"semantic_scholar": row.paper_id, "doi": row.doi, "arxiv": row.arxiv_id})
            if key and key not in dedup:
                dedup[key] = row
        query_tokens = set(map_item.topic.casefold().split())
        def score(row: SemanticScholarMetadata) -> tuple[int, str]:
            haystack = f"{row.title} {row.abstract or ''}".casefold()
            return (sum(1 for token in query_tokens if token and token in haystack), row.paper_id)
        ranked = list(dedup.values())
        if source_ids or conference_ids:
            ranked.sort(key=lambda row: (-score(row)[0], score(row)[1]))
        # Do not pad a sparse result with unrelated provider rows merely to
        # reach the requested count. A semantic/dense adapter can be added at
        # this seam later; the MVP's deterministic lexical gate is fail-safe.
        if any(score(row)[0] > 0 for row in ranked):
            ranked = [row for row in ranked if score(row)[0] > 0]
        return ranked[: map_item.requested_count]

    def _to_node(self, map_id: str, row: SemanticScholarMetadata) -> MapPaper:
        scope = self._catalog_scopes.get(row.paper_id)
        provenance = {"provider": "semantic_scholar", "operation": "search"}
        catalog_paper_id = None
        official_page_url = None
        official_pdf_url = None
        prepublication_pdf_url = None
        doi = row.doi
        arxiv_id = row.arxiv_id
        if scope is not None:
            catalog_paper_id = scope.catalog_paper_id
            if scope.source_id:
                provenance["source"] = scope.source_id
            if scope.source_kind:
                provenance["source_kind"] = scope.source_kind
            if scope.conference_id:
                provenance["conference_id"] = scope.conference_id
            official_page_url = self._safe_url(scope.official_page_url)
            official_pdf_url = self._safe_url(scope.official_pdf_url)
            prepublication_pdf_url = self._safe_url(scope.prepublication_pdf_url)
            doi = scope.doi or doi
            arxiv_id = scope.arxiv_id or arxiv_id
            provenance.update({
                "catalog_paper_id": catalog_paper_id,
                "official_page_url": official_page_url,
                "official_pdf_url": official_pdf_url,
                "prepublication_pdf_url": prepublication_pdf_url,
                "doi": doi,
                "arxiv_id": arxiv_id,
            })
            snapshot = self._safe_catalog_snapshot(scope.snapshot)
            if snapshot:
                provenance["catalog_snapshot"] = snapshot
        return MapPaper.new(
            map_id,
            external_ids={"semantic_scholar": row.paper_id, "doi": doi, "arxiv": arxiv_id},
            title=row.title,
            authors=row.authors,
            year=row.year,
            venue=row.venue,
            abstract=row.abstract,
            citation_count=row.citation_count,
            source_url=official_page_url or row.source_url,
            provenance=provenance,
            catalog_paper_id=catalog_paper_id,
        )

    def _find_job(self, job_id: str, owner_id: str | None) -> MapJob | None:
        if owner_id:
            for item in self.store.recover_jobs(owner_id):
                if item.job_id == job_id:
                    return item
            # Finished jobs cannot be found through recover_jobs; locate map by
            # a bounded owner list for the worker's own explicit owner path.
            for map_item in self.store.list_maps(owner_id):
                item = self.store.get_job(job_id, map_item.map_id, owner_id)
                if item:
                    return item
            return None
        # Runtime recovery always supplies owner; no cross-owner lookup exists.
        return None

    def _owner_for_job(self, job: MapJob) -> str:
        resolved = self.store.get_job_with_owner(job.job_id)
        if resolved is None:
            raise LookupError("map job not found")
        return resolved[1]

    def _validate_project(self, project_id: str, owner_id: str) -> None:
        if self.project_lookup is not None:
            if self.project_lookup(project_id, owner_id) is None:
                raise ValueError("PROJECT_NOT_FOUND")
            return
        from backend.app.memory.repository import MemoryRepository

        if MemoryRepository().get_project(project_id, owner_id) is None:
            raise ValueError("PROJECT_NOT_FOUND")


def _params_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _groups_envelope(item: LiteratureMap, groups: Iterable[Any]) -> dict[str, Any]:
    return {
        "schema_version": "literature-map-v1",
        "map_id": item.map_id,
        "revision": item.revision,
        "groups": [group.to_dict() for group in groups],
    }


_EXPORT_EXTERNAL_ID_KEYS = {"semantic_scholar", "doi", "arxiv", "pmid", "pmc", "openalex"}
_EXPORT_NODE_PROVENANCE_KEYS = {
    "provider",
    "source",
    "source_kind",
    "conference_id",
    "catalog_paper_id",
    "official_page_url",
    "official_pdf_url",
    "prepublication_pdf_url",
    "doi",
    "arxiv_id",
    "basis",
    "collected_at",
    "catalog_snapshot",
}
_EXPORT_EDGE_PROVENANCE_KEYS = {
    "provider",
    "relation",
    "source_paper_id",
    "source_url",
    "source_page_url",
    "algorithm",
    "threshold",
    "top_k",
    "basis",
    "model_version",
    "content_hash",
    "collected_at",
}
_EXPORT_CATALOG_KEYS = {
    "catalog_paper_id",
    "title",
    "authors",
    "year",
    "venue",
    "abstract",
    "keywords",
    "doi",
    "arxiv_id",
    "source",
    "source_kind",
    "conference_id",
    "official_page_url",
    "official_pdf_url",
    "prepublication_pdf_url",
    "collected_at",
}
_EXPORT_FILTER_KEYS = {"year_start", "year_end", "source_ids", "conference_ids"}


def _export_filters(filters: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(filters, Mapping):
        return {}
    exported: dict[str, Any] = {}
    for key in _EXPORT_FILTER_KEYS:
        value = filters.get(key)
        if key in {"year_start", "year_end"}:
            if value is None:
                continue
            try:
                exported[key] = int(value)
            except (TypeError, ValueError):
                continue
        elif isinstance(value, (list, tuple)):
            exported[key] = [str(item)[:100] for item in value if isinstance(item, (str, int))]
    return exported


def _export_view_settings(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(settings, Mapping):
        return {}
    exported: dict[str, Any] = {"filters": _export_filters(settings.get("filters"))}
    viewport = settings.get("viewport")
    if isinstance(viewport, Mapping):
        candidate: dict[str, float] = {}
        for key in ("x", "y", "scale"):
            try:
                value = float(viewport[key])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(value) and (key != "scale" or value > 0):
                candidate[key] = value
        if candidate:
            exported["viewport"] = candidate
    layers = settings.get("layers")
    if isinstance(layers, Mapping):
        exported["layers"] = {key: bool(layers[key]) for key in ("citation", "similarity") if key in layers}
    return exported


def _export_external_ids(external_ids: Mapping[str, Any] | None) -> dict[str, str]:
    if not isinstance(external_ids, Mapping):
        return {}
    return {
        key: str(value)[:500]
        for key, value in external_ids.items()
        if key in _EXPORT_EXTERNAL_ID_KEYS and isinstance(value, (str, int)) and str(value).strip()
    }


def _safe_export_url(value: Any) -> str | None:
    candidate = str(value or "").strip()
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        return None
    if any(token in parsed.query.casefold() for token in ("token", "secret", "api_key", "apikey", "password", "authorization", "credential")):
        return None
    return candidate[:2000]


def _export_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return value[:2000]
    if value is None or isinstance(value, (int, bool)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    return None


def _export_text_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item)[:500] for item in value if isinstance(item, (str, int))]


def _export_position(value: Mapping[str, Any] | None) -> dict[str, float] | None:
    if not isinstance(value, Mapping):
        return None
    result: dict[str, float] = {}
    for key in ("x", "y"):
        try:
            number = float(value[key])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(number):
            result[key] = number
    return result if len(result) == 2 else None


def _export_catalog_snapshot(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    exported: dict[str, Any] = {}
    for key in _EXPORT_CATALOG_KEYS:
        if key not in value:
            continue
        item = value[key]
        if key.endswith("url") or key in {"url", "official_page_url", "official_pdf_url", "prepublication_pdf_url"}:
            item = _safe_export_url(item)
        elif key in {"authors", "keywords"} and isinstance(item, (list, tuple)):
            item = [str(child)[:500] for child in item if isinstance(child, (str, int))]
        else:
            item = _export_scalar(item)
        if item is not None:
            exported[key] = item
    return exported


def _export_provenance(value: Mapping[str, Any] | None, *, edge: bool = False) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    allowed = _EXPORT_EDGE_PROVENANCE_KEYS if edge else _EXPORT_NODE_PROVENANCE_KEYS
    exported: dict[str, Any] = {}
    for key in allowed:
        if key not in value:
            continue
        item = value[key]
        if key == "catalog_snapshot":
            item = _export_catalog_snapshot(item)
        elif edge and key == "basis":
            item = safe_edge_basis(item)
        elif edge and key == "model_version":
            item = safe_edge_model_version(item)
        elif edge and key == "content_hash":
            item = safe_edge_content_hash(item)
        elif key.endswith("url") or key in {"url", "source_url", "source_page_url", "official_page_url", "official_pdf_url", "prepublication_pdf_url"}:
            item = _safe_export_url(item)
        else:
            item = _export_scalar(item)
        if item is not None:
            exported[key] = item
    return exported


def _export_node(node: MapPaper) -> dict[str, Any]:
    return {
        "node_id": node.node_id,
        "identity_key": node.identity_key,
        "external_ids": _export_external_ids(node.external_ids),
        "title": node.title,
        "authors": _export_text_list(node.authors),
        "year": node.year,
        "venue": node.venue,
        "abstract": node.abstract,
        "keywords": _export_text_list(node.keywords),
        "citation_count": node.citation_count,
        "source_url": _safe_export_url(node.source_url),
        "provenance": _export_provenance(node.provenance),
        "catalog_paper_id": node.catalog_paper_id,
        "document_id": node.document_id,
        "download_status": node.download_status,
        "position": _export_position(node.position),
        "group_id": node.group_id,
    }


def _export_edge(edge: MapEdge) -> dict[str, Any]:
    score: float | None = None
    if edge.score is not None:
        try:
            candidate_score = float(edge.score)
        except (TypeError, ValueError):
            candidate_score = float("nan")
        if math.isfinite(candidate_score):
            score = candidate_score
    return {
        "edge_id": edge.edge_id,
        "kind": edge.kind,
        "source_id": edge.source_id,
        "target_id": edge.target_id,
        "provenance": _export_provenance(edge.provenance, edge=True),
        "score": score,
        "basis": safe_edge_basis(edge.basis),
        "model_version": safe_edge_model_version(edge.model_version),
        "content_hash": safe_edge_content_hash(edge.content_hash),
    }




__all__ = ["CreateMapResult", "LiteratureMapService", "MAX_NODES"]
