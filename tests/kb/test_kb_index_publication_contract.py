"""Index publication guards for document/chunker point snapshots."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.knowledge_base.infrastructure import index as index_module
from backend.app.knowledge_base.infrastructure.parse import Chunk


class _Point:
    def __init__(self, point_id, payload):
        self.id = point_id
        self.payload = dict(payload)
        self.vector = {}


class _PointStoreClient:
    def __init__(self, points=()):
        self.points = {str(point.id): point for point in points}
        self.delete_error = None
        self.scroll_error = None
        self.inject_after_upsert = None
        self.upsert_calls = []

    def collection_exists(self, _name):
        return True

    def delete(self, *, points_selector, **_kwargs):
        if self.delete_error is not None:
            raise self.delete_error
        expected = {
            condition.key: condition.match.value
            for condition in points_selector.filter.must
        }
        for point_id, point in list(self.points.items()):
            if all(point.payload.get(key) == value for key, value in expected.items()):
                del self.points[point_id]

    def upsert(self, *, points, **_kwargs):
        self.upsert_calls.append(list(points))
        for point in points:
            self.points[str(point.id)] = point
        if self.inject_after_upsert is not None:
            point = self.inject_after_upsert
            self.points[str(point.id)] = point

    def scroll(self, *, scroll_filter, **_kwargs):
        if self.scroll_error is not None:
            raise self.scroll_error
        expected = {
            condition.key: condition.match.value
            for condition in scroll_filter.must
        }
        points = [
            point
            for point in self.points.values()
            if all(point.payload.get(key) == value for key, value in expected.items())
        ]
        return points, None


def _payload(document_id, chunker, chunk_index, *, text=None, paper_id=None):
    return {
        "paper_id": paper_id or document_id,
        "document_id": document_id,
        "source_sha256": "a" * 64,
        "chunker": chunker,
        "chunk_index": chunk_index,
        "text": text or f"chunk-{chunk_index}",
        "page": None,
        "page_end": None,
        "section": "",
        "is_citation": False,
    }


def _point(document_id, chunker, chunk_index, *, text=None, paper_id=None):
    return _Point(
        index_module.point_id(document_id, chunk_index, chunker),
        _payload(document_id, chunker, chunk_index, text=text, paper_id=paper_id),
    )


def _record_and_bundle(tmp_path: Path, *, chunker="v2", count=3, status="ready", unmapped=0):
    source = tmp_path / "source.md"
    source.write_bytes(b"indexed source")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    record = {
        "document_id": "doc-1",
        "file_name": "source.md",
        "source_sha256": digest,
        "uploaded_at": "2026-10-26T00:00:00+00:00",
        "status": "indexed",
        "chunkers": {"v1": {}, "v2": {}},
    }
    chunks = [
        Chunk(f"chunk-{index}", None, index, section="")
        for index in range(count)
    ]
    provenance = SimpleNamespace(media_type="text/markdown", normalized_text="indexed source")
    bundle = SimpleNamespace(
        source_sha256=digest,
        chunker=chunker,
        status=status,
        unmapped_count=unmapped,
    )
    return record, source, provenance, bundle, chunks


def _run_index(monkeypatch, record, source, provenance, bundle, chunks, client, *, publish, failed):
    monkeypatch.setattr(
        index_module,
        "_build_index_bundle",
        lambda *_args, **_kwargs: (provenance, bundle, chunks),
    )
    monkeypatch.setattr(index_module, "update_chunker_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(index_module, "_publish_manifest_and_state", publish)
    monkeypatch.setattr(index_module, "_mark_index_failed", failed)
    monkeypatch.setattr(index_module, "embed_texts", lambda texts: [[0.1, 0.2] for _ in texts])
    monkeypatch.setattr(index_module, "encode_sparse", lambda _text: {"indices": [1], "values": [1.0]})
    return index_module.index_paper_chunker(
        record,
        source,
        "v2",
        client=client,
        destination_collection="papers_rebuild_live",
    )


def test_shrinking_chunker_removes_stale_tail_and_keeps_other_versions(monkeypatch, tmp_path):
    old_points = [_point("doc-1", "v2", index) for index in range(5)]
    unrelated = _point("other-doc", "v2", 0)
    other_version = _point("doc-1", "v1", 0)
    client = _PointStoreClient([*old_points, unrelated, other_version])
    record, source, provenance, bundle, chunks = _record_and_bundle(tmp_path, count=3)
    published = []

    def publish(*_args, **kwargs):
        published.append(kwargs)
        return {"status": "partial" if bundle.status == "partial" else "ready"}

    def failed(*_args, **_kwargs):
        pytest.fail("unexpected failure")
    _run_index(monkeypatch, record, source, provenance, bundle, chunks, client, publish=publish, failed=failed)

    v2_target = {
        point.payload["chunk_index"]
        for point in client.points.values()
        if point.payload.get("paper_id") == "doc-1" and point.payload.get("chunker") == "v2"
    }
    assert v2_target == {0, 1, 2}
    assert str(unrelated.id) in client.points
    assert str(other_version.id) in client.points
    assert published and published[0]["indexed_payloads"]


def test_delete_failure_stops_before_upsert_or_publication(monkeypatch, tmp_path):
    client = _PointStoreClient([_point("doc-1", "v2", 0)])
    client.delete_error = RuntimeError("delete unavailable")
    record, source, provenance, bundle, chunks = _record_and_bundle(tmp_path)
    published = []
    failures = []

    def publish(*_args, **_kwargs):
        published.append(True)

    def failed(*_args, **kwargs):
        failures.append(kwargs["error"])

    _run_index(monkeypatch, record, source, provenance, bundle, chunks, client, publish=publish, failed=failed)

    assert client.upsert_calls == []
    assert published == []
    assert failures == ["QDRANT_UNAVAILABLE"]


def test_pointset_mismatch_fails_closed_before_ready_or_partial_publication(monkeypatch, tmp_path):
    client = _PointStoreClient()
    client.inject_after_upsert = _point("doc-1", "v2", 99)
    record, source, provenance, bundle, chunks = _record_and_bundle(tmp_path)
    published = []
    failures = []

    def publish(*_args, **_kwargs):
        published.append(True)

    def failed(*_args, **kwargs):
        failures.append(kwargs["error"])

    _run_index(monkeypatch, record, source, provenance, bundle, chunks, client, publish=publish, failed=failed)

    assert client.upsert_calls
    assert published == []
    assert failures == ["INDEX_FINALIZE_REQUIRED"]


def test_payload_mismatch_fails_closed_before_publication(monkeypatch, tmp_path):
    client = _PointStoreClient()
    client.inject_after_upsert = _point("doc-1", "v2", 0, text="unexpected text")
    record, source, provenance, bundle, chunks = _record_and_bundle(tmp_path)
    published = []
    failures = []

    def publish(*_args, **_kwargs):
        published.append(True)

    def failed(*_args, **kwargs):
        failures.append(kwargs["error"])

    _run_index(monkeypatch, record, source, provenance, bundle, chunks, client, publish=publish, failed=failed)

    assert published == []
    assert failures == ["INDEX_FINALIZE_REQUIRED"]


def test_unmapped_partial_bundle_still_reaches_publication(monkeypatch, tmp_path):
    client = _PointStoreClient()
    record, source, provenance, bundle, chunks = _record_and_bundle(
        tmp_path, status="partial", unmapped=1
    )
    published = []
    failures = []

    def publish(*_args, **kwargs):
        published.append(kwargs)
        return {"status": "partial"}

    def failed(*_args, **kwargs):
        failures.append(kwargs["error"])

    _run_index(monkeypatch, record, source, provenance, bundle, chunks, client, publish=publish, failed=failed)

    assert not failures
    assert published and published[0]["indexed_payloads"]
    assert bundle.status == "partial"
    assert bundle.unmapped_count == 1
