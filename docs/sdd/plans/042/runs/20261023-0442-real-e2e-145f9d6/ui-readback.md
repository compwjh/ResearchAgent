# Langfuse UI read-back (headless, read-only)

## Result

The local Langfuse UI was opened with headless Playwright using the existing system Chrome executable. Existing seed credentials were loaded from `vendor/langfuse/.env` in memory only; credential values were not printed or written. No score, trace, or configuration mutation was performed.

- Login page selectors observed: `input[name=email]`, `input[name=password]`, and the `Sign in` button.
- Login succeeded; post-login title: `Organizations | Langfuse`.
- The observed project link was `/project/local-proj`.
- Actual trace URL: `http://127.0.0.1:3000/project/local-proj/traces/9a93fe5d085320fdd3a39f3101327a1e`
- Trace page title: `Tracing | Langfuse`.
- The rendered page contained the requested score label `chat_quality` and value `1.0`, and the requested trace ID was present in the trace-page context.
- Read-only controls observed: `Scores` and `+4` with aria label `Show 4 more scores`.
- The score UUID `cf95289f-8ef0-4d08-a0a6-81759a6f359e` was not rendered as visible DOM text. Its exact identity, name, trace ID, and value were verified separately by the canonical API exact-GET checks recorded in `api-e2e.md`; this UI check does not claim that the UUID itself is visible in the UI.
- No screenshot was saved, and no trace input/output or other user-originating text was copied into this artifact.

## Credential mapping note

The canonical CLI run used the existing local Langfuse credential configuration. The seed `.env` contains `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` and `LANGFUSE_INIT_PROJECT_SECRET_KEY`, which are the local values mapped to `LANGFUSE_PK` and `LANGFUSE_SK` for this deployment. Values are intentionally omitted. A different project must provide its own `LANGFUSE_PK`/`LANGFUSE_SK` explicitly.

## Historical UI attempt

The earlier desktop-browser attempt remains preserved at `../20261023-0431-real-e2e/ui-readback.md` and records the prior connection-refused result. It was not overwritten by this successful headless read-back.
