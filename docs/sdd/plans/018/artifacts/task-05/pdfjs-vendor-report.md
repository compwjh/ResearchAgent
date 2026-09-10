# Spec018 Task05-A PDF.js vendoring report

## Result

Task05-A vendored the exact `pdfjs-dist@4.10.38` browser build. The main
module, worker, and upstream Apache-2.0 `LICENSE` are copied byte-for-byte from
the npm tarball. `NOTICE` is a project-added provenance file because neither
the npm package nor the upstream v4.10.38 source tree contains a standalone
NOTICE file; it does not replace or amend `LICENSE`.

## Fixed artifacts

- `frontend/vendor/pdfjs/pdf.min.mjs`
- `frontend/vendor/pdfjs/pdf.worker.min.mjs`
- `frontend/vendor/pdfjs/LICENSE`
- `frontend/vendor/pdfjs/NOTICE`
- `docs/sdd/plans/018/artifacts/task-05/pdfjs-vendor-manifest.json`

The manifest is the hash and configuration authority. It fixes the local
same-origin worker URL, `?v=4.10.38` resource query, display-only API allowlist,
forbidden API categories, and `getDocument` safety options.

## Verification

- Exact upstream byte comparison for main, worker, and LICENSE: exit 0.
- SHA-256 recomputation against all four manifest fields: exit 0.
- `node --check` for main and worker `.mjs`: exit 0.
- Manifest version/path/worker-origin/options assertions: exit 0.
- No CDN, iframe, or business HTML/JS/CSS changes were made.

## Source provenance

- Package: `pdfjs-dist@4.10.38`
- Upstream: `https://github.com/mozilla/pdf.js`
- Package tarball: obtained with `npm pack pdfjs-dist@4.10.38`; the exact
  tarball was inspected before copying.
