# Spec018 Task05-D1 runtime integration report

## Scope

This slice wires the Task05-B DOM and Task05-C renderer into a read-only
runtime. It modifies only `frontend/kb-inspection.js` and the script tags in
`frontend/index.html`; no styles, backend, vendor, upload, reindex, embedding,
or PDF source reads were added.

## Runtime behavior

- Loads the local runtime as `/assets/kb-inspection.js?v=16` and keeps the
  existing app script on the synchronized `?v=16` resource version.
- Implements roving `tabindex`, `aria-selected`, focus, Enter/Space activation,
  and Arrow/Home/End navigation for both the knowledge-base tabs and the narrow
  source/chunk pane tabs.
- On entering the inspection tab, performs only paginated
  `GET /api/kb/documents?limit=100` requests, follows opaque document-list
  cursors under a 1000-page safety cap, and fills the document `<select>` with
  DOM-created options and `textContent`. It does not auto-select the first
  document.
- On an explicit document/version selection, reads only
  `GET /api/kb/documents/{document_id}/inspection?chunker=v1|v2`, follows opaque
  `next_cursor` pages, and aggregates `blocks`, `chunks`, and `anchors`.
- Treats `INDEX_REBUILD_REQUIRED` and `INDEX_FINALIZE_REQUIRED` as distinct
  maintenance states; `INSPECTION_BUILDING` is polled using bounded
  `Retry-After` values. Ordinary failures use the alert state. Leaving the
  inspection tab, changing document, or changing version aborts the current
  request and clears the pending poll timer.
- Markdown blocks are rendered only through the Task05-C
  `renderMarkdownBlock` entry point. Chunk entries use DOM APIs and
  `textContent`, expose `data-chunk-id`, and expose space-separated associated
  block IDs from the anchor list.
- PDF documents show the stable placeholder “PDF 原文渲染将在下一段接入
  PDF.js。” No source endpoint or PDF.js API is loaded in D1.
- The chunk empty-state node is retained as a direct child of the chunk
  container across clear/render cycles; it is hidden only when chunk items are
  present.

## Verification

| Probe | Exit code | Result |
|---|---:|---|
| `node --check frontend/kb-inspection.js` | 0 | PASS |
| `node --check tests/test_frontend_kb_inspection_runtime.js` | 0 | PASS |
| `node tests/test_frontend_kb_inspection_renderer.js` | 0 | PASS |
| `node tests/test_frontend_kb_inspection_runtime.js` | 0 | PASS |
| `node --check frontend/app.js` | 0 | PASS |
| runtime safety/diff checks | 0 | PASS |

The runtime test covers tab roving keyboard behavior, two-page document-list
loading, two-page inspection opaque-cursor pagination, Markdown/chunk
association, empty-state lifecycle, maintenance errors, controlled
cancellation, and the absence of POST/reindex calls.

## Deferred to later Task05 slices

PDF.js display rendering, source endpoint reads, block/chunk click mapping,
highlighting, scroll suppression, and virtualized large-document rendering are
intentionally not included in D1.
