# Task04-A source/chunk foundation report

## 结果

`Task04-A` backend foundation is implemented for the controlled application
boundary. This report covers source reads and DTO/manifest construction only;
HTTP route wiring and the upload-closure migration remain Task04-C/D scope.

## Implemented contract

- `DocumentSourceReader` resolves only a validated `document_id` and a
  server-owned `stored_name` basename. It never accepts a caller path and
  verifies the current source SHA-256 against canonical metadata before a
  read.
- PDF and UTF-8 Markdown validation is exposed as a small, side-effect-free
  helper. Unsupported media, invalid PDF magic and invalid UTF-8 return stable
  errors without writing a file.
- Full GET (200), one bounded byte range (206), matching ETag (304), and
  body-free HEAD semantics are represented by `SourceRead`; headers include
  ETag, Content-Length, Content-Type, Accept-Ranges and inline disposition.
- `SourceBlock`, `ChunkSnapshot`, `SourceAnchor` and `InspectionManifest` are
  immutable DTO wrappers. `build_inspection_manifest` consumes a real
  `SourceProvenanceBundle` and current index payloads, validates identity,
  source hash, chunker, contiguous indexes, payload text and the frozen
  Draft 2020-12 manifest schema.
- The inspection builder only reads payloads and provenance. Embedding,
  chunking, Qdrant upsert/delete and source/metadata writes are not called.

## Evidence

- Implementation: `backend/app/knowledge_base/infrastructure/document_read.py`
  and `backend/app/knowledge_base/infrastructure/inspection.py`.
- Application boundary: `backend/app/knowledge_base/application.py`.
- Tests: `tests/test_kb_document_foundation.py`.
- Frozen schema consumed at runtime:
  `docs/sdd/plans/018/artifacts/task-03/inspection-manifest.schema.json`.

## Verification

The focused foundation suite passes. It covers safe IDs, source basename
resolution, full/range/HEAD/ETag reads, PDF/Markdown validation, real
provenance payloads, legacy-payload fail-closed behavior, and schema-backed
manifest construction. All fixtures use `tmp_path`; no user `data/kb`, real
Qdrant, frontend or rebuild command is used.

Recorded checks:

- `.venv/bin/python -m pytest -q tests/test_kb_document_foundation.py` — exit 0
  (7 passed).
- `.venv/bin/python -m pytest -q` — exit 0 (785 passed, 38 subtests).
- `.venv/bin/ruff check` on the changed backend/application/test files — exit 0.
- `.venv/bin/python -m py_compile` on the changed Python files — exit 0.
- Draft 2020-12 `check_schema` on the three Task03 runtime schemas — exit 0.

The fixed `upload-closure-matrix.json` inventory hashes/digest were refreshed
for the current Task03 baseline plus this application-boundary change. Its
entry statuses intentionally remain `open`/`pending` with
`review_status=baseline_frozen`; Task04-C/D must close and verify them.

## Deferred boundary

Route handlers, pagination, upload deduplication/concurrency, unified delete
workflow, and the full upload-closure matrix are Task04-C/D gates and are not
claimed by this report.
