# Task04-B manifest/finalize foundation report

## 结果

`Task04-B` backend foundation is implemented with explicit temporary roots.
The store is suitable for tempfile-backed tests and does not connect to
Qdrant or execute a rebuild.

## Implemented contract

- `InspectionManifestStore` persists one validated manifest per
  `document_id/chunker` under `manifests/<document_id>/<chunker>.json`.
  Writes use a temporary file, file fsync, atomic replace and directory fsync;
  malformed or schema-invalid JSON fails closed.
- Claims use create-exclusive `<chunker>.claim` files beside the manifest and
  owner/token checks. An active claim blocks a second owner; an expired claim
  can be reclaimed. Tombstones are written before the derived manifest is
  removed at `tombstones/<document_id>.json`, and tombstoned manifests cannot
  be read or rewritten.
- `FinalizeBundleStore` stages metadata and manifest files beneath the
  run-scoped `.sdd/runtime/spec-018/rebuild/<run-id>/finalize/` directory,
  stores canonical SHA-256 values, validates the frozen schemas, and publishes
  live artifacts idempotently.
- The generation marker is written last and includes the bundle hash,
  candidate alias target, metadata hash and live-manifest digest. Missing,
  corrupt or mismatched marker/live files return
  `INDEX_REBUILD_REQUIRED` or `INDEX_FINALIZE_REQUIRED` as appropriate.
- Obsolete cleanup is limited to bundle-listed `data/kb/manifests/` entries;
  the store never deletes source files or arbitrary paths.

## Evidence

- Implementation:
  `backend/app/knowledge_base/infrastructure/manifest_store.py`.
- Application boundary: `backend/app/knowledge_base/application.py`.
- Tests: `tests/test_kb_document_foundation.py`.
- Runtime schemas:
  `docs/sdd/plans/018/artifacts/task-03/inspection-manifest.schema.json`,
  `finalize-bundle.schema.json` and `index-generation.schema.json`.

## Verification

Focused tests pass for single-owner claims, concurrent claim contention,
tombstone reads, marker-last publication, live hash verification,
missing-generation health gates and repeated finalize commit. Fixtures use
only temporary roots.

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

Qdrant alias switching, rebuild FSM/lock recovery, API health wiring and the
full delete protocol (including vector deletion) remain Task02A-D, Task04-C/D
or Task06 scope. This store intentionally has no Qdrant or embedding call.
