# GO — Spec-042 real API E2E artifact and UI read-back

## Run identity

- `spec`: Spec-042 offline evaluation
- `run_id`: `20261023-0442-real-e2e-145f9d6`
- candidate: branch `codex/spec042-offline-evaluation`, commit `145f9d6`
- product path: canonical CLI bypass; no new natural-language Intake, frontend, or product API path
- network: all evaluator/API/model requests used loopback addresses; no cloud or external HTTP request
- service ownership: root-owned foreground runtime, retained after this run; this task did not start, stop, or clean services

## Runtime evidence

| component | observed runtime |
|---|---|
| ClickHouse | session `20709`, PID `83740`, existing config/data, loopback listener |
| PostgreSQL | existing PID `79169`, `127.0.0.1:5432` |
| Redis | session `84985`, PID `83764`, `127.0.0.1:6379` |
| MinIO | session `61216`, PID `83782`, `127.0.0.1:9002/9003` |
| Langfuse worker | session `49556`, PID `83835`, `127.0.0.1:3030` |
| Langfuse web | session `71694`, PID `83862`, `127.0.0.1:3000` |
| Ollama | pre-existing local process, accessed only at `127.0.0.1:11434` |

Preflight immediately before the run: web `/`, `/api/public/health`, `/api/public/ready`, and worker `/api/health` each returned HTTP 200. No service was modified by this run.

## Canonical CLI request

Command (exit code `0`):

```text
PYTHONPATH=/Users/wjh/ResearchAgent .venv/bin/python -m backend.eval_042.cli --export --output-dir docs/sdd/plans/042/runs/20261023-0442-real-e2e-145f9d6 --task chat_quality --primary qwen3.5:9b --fallback qwen3.8:27b --repeats 3 --max-items 1
```

The subprocess loaded `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` / `LANGFUSE_INIT_PROJECT_SECRET_KEY` from the existing local `.env` in memory only, mapped to the CLI variables expected by the evaluator. No credential or authorization header was printed or persisted.

## State trace and exact verification

| stage | observed result |
|---|---|
| real export | one existing `ollama-chat` trace selected, `trace_id=9a93fe5d085320fdd3a39f3101327a1e`, `synthetic=false`; no trace body persisted |
| local judge | primary `qwen3.5:9b`, 3 repeats, majority `good`, numeric value `1.0`; model output text omitted |
| score POST | exactly one POST issued by the canonical runner; response accepted as `post_status=written`; `score_id=cf95289f-8ef0-4d08-a0a6-81759a6f359e`; `name=chat_quality`; `trace_id` matched; value `1.0` |
| canonical verification | runner returned `verified=true`, `verification_status=verified`, `verified_value=1.0` |
| exact GET production wait | six read-only `GET /api/public/scores/{score_id}` attempts with delays `0`, `0.25`, `0.50`, `1.00`, `2.00`, `4.00` seconds; all six HTTP 200 with exact ID/name/trace/value matches |
| final CLI result | `status=completed`, `scored=1`, `written=1`, `verified=1`, `failed=0`, `exit_code=0` |

No second POST, trace mutation, score deletion, synthetic trace, or business DB write was performed.

## Sanitized artifacts

- [report.json](./report.json): completed report, one real scored item
- [report.md](./report.md): completed Markdown projection
- reports contain only trace/score IDs, status, model/label, numeric value, and safe explanation reason code; trace input/output, prompts, completions, hidden reasoning, credentials, cookies, and authorization headers are omitted

## UI read-only follow-up

The existing Langfuse UI was successfully inspected with headless Playwright and the local system Chrome executable. Seed credentials were loaded from the existing `vendor/langfuse/.env` in memory only; no values were printed or persisted. The login page selectors were `input[name=email]`, `input[name=password]`, and the `Sign in` button. Login reached `Organizations | Langfuse`, and the observed project link was `/project/local-proj`.

The actual read-only trace URL was `http://127.0.0.1:3000/project/local-proj/traces/9a93fe5d085320fdd3a39f3101327a1e` with title `Tracing | Langfuse`. The rendered page contained `chat_quality` and `1.0`, with `Scores` and `+4` / `Show 4 more scores` controls. The score UUID `cf95289f-8ef0-4d08-a0a6-81759a6f359e` was not rendered as visible DOM text; its exact identity/name/trace/value match is established by the canonical exact-GET checks above. The detailed UI evidence is in [ui-readback.md](./ui-readback.md). No screenshot or trace-originating text was saved. The earlier desktop-browser connection-refused attempt remains preserved in [the historical UI artifact](../20261023-0431-real-e2e/ui-readback.md).

## Manual acceptance case

The Spec product path is the CLI bypass, not a natural-language or frontend path. The reproducible API case is the exact command above. A user should wait for the safe JSON line with `exit_code=0`, `status=completed`, `written=1`, and `verified=1`, then inspect the two report files. The current CLI case and the headless UI read-back both succeeded; any later desktop-browser review is optional and must remain read-only.

## Readiness matrix

| # | criterion | result | evidence |
|---:|---|---|---|
| 1 | service started and accessible | PASS | root-owned loopback runtime and HTTP 200 preflight |
| 2 | real score creation entry succeeds | PASS | one real score POST, score ID present, `post_status=written` |
| 3 | main-path parameters parsed correctly | PASS | task/model/repeats/max-items recorded in report metadata |
| 4 | task/entity state reaches final state | PASS | `completed`, `verified=true`, exact numeric value |
| 5 | frontend processing prompt shown | N/A | Spec-042 explicitly excludes a frontend path |
| 6 | user knows when to wait/continue | PASS | CLI emits safe terminal summary and report paths |
| 7 | core business artifact generated successfully | PASS | completed JSON/Markdown reports exist and are internally consistent |
| 8 | failure state has actionable recovery | PASS | canonical failure handling is represented in preserved prior run; this run had no failure |
| 9 | page state and API state agree | PASS | headless UI showed the requested trace page, `chat_quality`, and `1.0`; exact score UUID/name/trace/value match is recorded by API GET |
| 10 | steps reproducible without chat context | PASS | command, runtime, entity IDs, six GET results, and artifact paths recorded |

API/UI readiness is `PASS=9/10` plus `N/A=1`; no P0/P1 or critical artifact blocker remains for this run.

## Final decision

`GO` for the requested handoff on `145f9d6`: exactly one new real score was written, exactly verified six additional times, and the corresponding Langfuse trace page was inspected read-only with the expected score label/value. No additional score POST is required.
