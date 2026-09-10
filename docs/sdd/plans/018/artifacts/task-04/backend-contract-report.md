# Task04-C backend contract report

## Scope

The canonical document application now owns HTTP upload, source reads,
inspection reads, explicit reindex submission, and deletion.  Upload accepts
PDF or UTF-8 Markdown, stores a server-generated basename with exclusive
create, writes `knowledge-document-v1`, and never invokes embedding or
Qdrant.  A repeated source hash returns the existing immutable document.

`GET/HEAD /api/kb/documents/{id}/source` delegates to the Task04-A reader and
preserves ETag, one-range 206, 304, and body-free HEAD behavior. Inspection
first checks canonical document identity (unknown documents are 404), then
requires the generation marker before reading a real manifest. A missing
manifest after that gate is reported as `INSPECTION_BUILDING` (202) with a
stable task id, `status=building`, `progress=0`, `Location`, and
`Retry-After: 2`; the response is backed by a persisted per-document/chunker
claim so concurrent polls do not submit duplicate builds. Ready inspection responses page blocks/chunks/anchors
together, include totals, an opaque document/chunker-bound cursor, and support
ETag/304. Reindex is an explicit 202 command with a unified body-validation/
error envelope and `Retry-After: 2`; running/hash conflicts use the frozen 409
codes; non-object JSON and missing upload files return 400 `INVALID_REQUEST`
without FastAPI `detail`. Delete returns completed only after the application
delete boundary succeeds; partial failure is `DELETE_PENDING` (503) with `Retry-After: 10`,
document `Location`, and `details.retry_after_seconds`.
Reindex checks canonical document identity before the generation gate, verifies
the current source SHA-256 before submission, and returns stable 404/409 errors
for unknown documents or source-hash conflicts.

The old `/api/kb/upload`, `/api/kb/papers/{id}/reindex`, and delete routes are
controlled aliases to the canonical document application.  They no longer
write source or metadata through route-owned legacy helpers.

## Verification

- `.venv/bin/python -m pytest -q tests/test_kb_document_routes.py tests/test_kb_routes.py`
  — exit 0, `47 passed`; TestClient/tempfile-only route fixtures; embedding and
  Qdrant writes: 0.
- `.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_paper_import*.py`
  — exit 0, `394 passed, 5 warnings, 29 subtests passed`.
- Draft 2020-12 `check_schema` on `api-schema.json` — exit 0.
- `ruff check` on changed routes, manifest/migration/store modules and migrated
  route tests — exit 0.
- `upload-closure-matrix.json` remains `review_status=baseline_frozen` with
  entries/tests still `open`/`pending` until Task04-D independently runs the
  full inventory, paper-import, startup, rebuild, and tombstone gates.

## Known boundary / security debt

The production Qdrant alias/CandidateIndexPort boundary, paper-import single
entry point, startup recovery removal, finalize protocol, and full closure
inventory are not reimplemented by this HTTP layer. They remain explicit
Task04/Task06 debt; the matrix therefore remains
`review_status=baseline_frozen` with `open`/`pending` entries and has not been
marked `closed`/`verified`. Task04-D must supply the independent
startup/index/import/finalize evidence before production cutover.
