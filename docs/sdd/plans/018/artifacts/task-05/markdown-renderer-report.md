# Spec018 Task05-C Markdown block renderer report

## Result

`frontend/kb-inspection.js` now provides the isolated `renderMarkdownBlock()`
entry point for one backend `SourceBlock` DTO. It does not fetch documents,
load PDF resources, register event handlers, or trigger indexing. Runtime
wiring and cross-pane interaction remain Task05-D responsibilities.

## Fixed pipeline

1. Validate the required DTO fields: `block_id`, `ordinal`, `text`, `locator`,
   `heading_path`, and `block_type`.
2. Create an `article.kb-source-block` with DOM APIs. `data-block-id`, ordinal,
   role, accessible label, focusability, and metadata are all set through DOM
   APIs; untrusted heading/type metadata is assigned with `textContent`.
3. Call Marked with `{gfm:true, breaks:true}`.
4. Pass the generated HTML to the existing DOMPurify-compatible interface with
   script/style/iframe/form/resource restrictions. The detached HTML is the
   only value assigned to the template HTML parser.
5. Before any node is mounted, replace every `img` with a newly-created
   `span.kb-image-placeholder`. The original `src`/`srcset` never reaches the
   mounted tree; the placeholder uses `textContent` and truncates the source
   address to 2048 characters.
6. If Marked or DOMPurify is unavailable, render the original Markdown as
   plain text and emit `RENDERER_UNAVAILABLE` through the caller's error
   callback and `data-error-code`.

## Contract tests

The Node contract test is `tests/test_frontend_kb_inspection_renderer.js` and
uses a small DOM fixture (the repository has no root jsdom dependency). It
covers:

- Marked → DOMPurify ordering and options;
- hostile script/event input;
- image `src`/`srcset` replacement and 2048-character truncation boundary;
- metadata text-only rendering;
- required DTO validation;
- missing-library plain-text fallback and stable error code;
- absence of network/PDF/interaction APIs.

## Verification

| Probe | Exit code | Result |
|---|---:|---|
| `node --check frontend/kb-inspection.js` | 0 | PASS |
| `node --check tests/test_frontend_kb_inspection_renderer.js` | 0 | PASS |
| `node tests/test_frontend_kb_inspection_renderer.js` | 0 | PASS |
| renderer scope/security assertions | 0 | PASS |
| `git diff --check` | 0 | PASS |

## Files

- `frontend/kb-inspection.js`
- `tests/test_frontend_kb_inspection_renderer.js`
- `docs/sdd/plans/018/artifacts/task-05/markdown-renderer-report.md`
