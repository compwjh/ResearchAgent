# BLOCKED — Langfuse score UI read-only follow-up

- Scope: read-only visibility check for existing score `ba272a71-74bf-4ce6-8e74-181d649521c4` on trace `9a93fe5d085320fdd3a39f3101327a1e`; no create/edit/delete and no score POST.
- Candidate observed: `145f9d6` on `codex/spec042-offline-evaluation`; this document does not change the preserved CLI failure artifact.
- Intended local page: `http://127.0.0.1:3000/`.

## Actual browser attempt

1. Existing Chrome extension tab navigation to `http://127.0.0.1:3000/` returned `ERR_CONNECTION_REFUSED`.
2. The local native Chrome window was navigated to the same URL; the visible page title was `127.0.0.1 — Network error` and the page displayed “This site can’t be reached” / “refused to connect”.
3. No login form was reached. No email/password was entered, no credentials were guessed or reset, and no screenshot or full-page response was saved.

At the time, terminal health checks had previously returned HTTP 200, but the browser surface could not connect to the child-owned service namespace. The temporary child-owned services were stopped after the root session requested a root-owned foreground runtime; no UI score visibility claim is made.

## Result

`BLOCKED` for UI/API consistency evidence: the API exact read-back was already independently HTTP 200 for the existing score, but browser visibility could not be verified. This does not alter the canonical CLI result (`report.json` remains `status=failed`, `exit_code=1`) and is not a reason to create another score.

## Environment note

Root-level untracked `access/` and `preprocessed_configs/` contain the earlier ClickHouse wrong-working-directory remnants. At inspection time no ClickHouse process/listener used them; they were neither deleted nor committed. The current root-owned runtime should use `/Users/wjh/opt/clickhouse` as its working directory and existing config/data paths.
