# BLOCKED — Spec-042 real API E2E artifact

## Run identity and scope

- `spec`: Spec-042 offline evaluation
- `run_id`: `20261023-0431-real-e2e`
- candidate: branch `codex/spec042-offline-evaluation`, commit `6f644bc`
- product path: canonical CLI bypass; Spec-042 explicitly does not add a natural-language Intake, UI, or new product API path
- network boundary: all requests used `127.0.0.1`; no cloud or external HTTP request was made
- models: local Ollama `qwen3.5:9b` primary, `qwen3.8:27b` fallback; `/api/tags` returned HTTP 200 and both model names were present

## Runtime and preflight evidence

| component | command/source | result |
|---|---|---|
| ClickHouse | existing `/Users/wjh/opt/clickhouse/clickhouse`, existing `config.xml`/data | PID `79822`, `127.0.0.1:8123`, `/ping` HTTP 200; existing `.env` account auth HTTP 200 |
| PostgreSQL | existing `pg_ctl`, existing `/Users/wjh/opt/pgdata` | PID `79169`, `127.0.0.1:5432` |
| Redis | existing `redis-server --bind 127.0.0.1 --port 6379` | PID `79184`, `127.0.0.1:6379` |
| MinIO | existing `minio --address 127.0.0.1:9002 --console-address 127.0.0.1:9003` | PID `79197`, loopback ports 9002/9003; live health HTTP 200 |
| Langfuse worker | installed Node 24 / existing dependencies, `HOSTNAME=127.0.0.1 PORT=3030 pnpm --filter worker run dev` | PID `79363`, `127.0.0.1:3030`, `/api/health` HTTP 200 |
| Langfuse web | installed Node 24 / existing dependencies, `next dev --hostname 127.0.0.1` | PID `80339`, `127.0.0.1:3000`; `/`, `/api/public/health`, `/api/public/ready` HTTP 200 |
| Ollama | pre-existing process | PID `2882`, `/api/tags` HTTP 200; not modified |

No package was installed, no data was migrated, no configuration file was changed, and no unrelated process was stopped. The first ClickHouse launch used the wrong working directory and was stopped only for this run; the relaunch from the existing config directory loaded the existing `langfuse` user and passed authentication.

## Real chat-quality request and state trace

Command (exit code `1`):

```text
PYTHONPATH=/Users/wjh/ResearchAgent .venv/bin/python -m backend.eval_042.cli --export --output-dir docs/sdd/plans/042/runs/20261023-0431-real-e2e --task chat_quality --primary qwen3.5:9b --fallback qwen3.8:27b --repeats 3 --max-items 1
```

The CLI subprocess loaded the existing project credentials from `vendor/langfuse/.env` in memory only. Credentials and authorization headers are not in this artifact. The trace request was a read-only export of the existing `ollama-chat` trace; its input/output and judge completion were not persisted.

| stage | observed evidence |
|---|---|
| authenticated export | Langfuse traces API HTTP 200; one real trace selected, `trace_id=9a93fe5d085320fdd3a39f3101327a1e`; `synthetic=false` |
| local judge | 3 repeats completed with primary `qwen3.5:9b`; majority label `good`, mapped value `1.0`; no model text persisted |
| score write | one local score POST accepted by the canonical client; `post_status=written`; `score_id=ba272a71-74bf-4ce6-8e74-181d649521c4`; `name=chat_quality`; `trace_id` matched; `value=1.0` |
| canonical exact verification | runner made its bounded list-based verification attempts and returned `ScoreVerificationError: score id not found on trace`; no second POST was attempted |
| independent read-only confirmation | `GET /api/public/scores/{score_id}` HTTP 200 with exact ID, `name=chat_quality`, exact trace ID, and `value=1`; `GET /api/public/scores?traceId=...` HTTP 200 included the same ID; trace GET HTTP 200 returned a scores list containing the score |
| final CLI/report state | exit code `1`, report status `failed`, `written=1`, `verified=0`, `failed=1`; this is not an accepted E2E success because the canonical verifier failed even though later exact-ID reads found the score |

The independent read-back was performed only against the already-written score. The evidence is consistent with a short post-write visibility delay or list-filter/read-path behavior inside the runner's bounded 0.05/0.1 second retry window; it does not prove the implementation defect's root cause. The canonical candidate remains failed until the implementation is repaired and independently rerun.

## Real memory skip request

Command (exit code `0`):

```text
PYTHONPATH=/Users/wjh/ResearchAgent .venv/bin/python -m backend.eval_042.cli --export --output-dir docs/sdd/plans/042/runs/20261023-0435-memory-skip --task memory_correctness --primary qwen3.5:9b --fallback qwen3.8:27b --repeats 3 --max-items 1
```

This selected the same real trace with no `prior_context`. Observed result: `status=completed`, `skipped=1`, `no_prior_context=1`, `written=0`, `verified=0`, and no score POST. No synthetic item was used and no original trace was changed.

## Sanitized terminal artifacts

- chat-quality terminal report: [report.json](./report.json), [report.md](./report.md)
- memory skip report: [report.json](../20261023-0435-memory-skip/report.json), [report.md](../20261023-0435-memory-skip/report.md)
- reports contain IDs, status, numeric score metadata, and safe reason codes only; they omit trace input/output, prompts, completions, hidden reasoning, credentials, cookies, and authorization headers
- the failed chat-quality report is preserved and was not overwritten by a retry

## Manual acceptance case (not releasable yet)

Because the Spec defines a CLI bypass and excludes UI/natural-language Intake, the reproducible case is a terminal invocation rather than a click path:

1. **Input/entry:** from the repository root, run the exact chat-quality command above with existing local loopback services and local Ollama available.
2. **Immediate indication:** the command must print one safe JSON summary containing `status`, `exit_code`, report paths, and counts; it must not print trace or judge text.
3. **Wait condition:** wait for the command to return after export, three local judge calls, one score POST, and bounded exact verification. No extra POST may be retried manually.
4. **Waiting display:** there is no UI progress surface in the Spec; the terminal remains the only observable surface. The current candidate returned a failed summary, which is a blocking result.
5. **Next step:** only after a repaired candidate returns `exit_code=0`, inspect the generated JSON/Markdown reports and use the exact score ID/trace ID for local Langfuse review.
6. **Failure recovery:** preserve the failed run directory, do not delete the score, and hand the exact verifier failure plus paths to backend implementation/review. A new fix attempt must use a new run ID and may not overwrite this artifact.

Success criterion: one real trace, local judge result, one score write, exact ID/name/trace/value verification, and completed JSON/Markdown reports. Current criterion is not met because canonical exact verification failed.

## Readiness matrix

| # | criterion | result | evidence |
|---:|---|---|---|
| 1 | service started and accessible | PASS | loopback listener/health table above |
| 2 | real API creation entry succeeds | N/A | Spec-042 exports an existing trace and writes a score; it does not create a new trace/entity |
| 3 | main-path parameters parsed correctly | PASS | CLI accepted `chat_quality`, local model names, repeats, and max-items; report metadata records them |
| 4 | task/entity state reaches final state | FAIL | score was written but canonical exact verification ended in `failed` |
| 5 | frontend processing prompt shown | N/A | Spec-042 explicitly has no UI/frontend path |
| 6 | user knows when to wait/continue | PASS | CLI returns a safe terminal summary and report paths; current failure is explicit |
| 7 | core business artifact generated successfully | FAIL | failed chat-quality report is present, but verified success artifact is not |
| 8 | failure has actionable recovery | PASS | failed report preserves error, IDs, paths, and no-repeat-POST instruction |
| 9 | page state matches API state | N/A | Spec-042 explicitly has no page/UI state |
| 10 | steps reproducible without chat context | PASS | command, preconditions, observed IDs, statuses, and recovery are recorded above |

Count: `PASS=5/10`, `N/A=3`, `FAIL=2`; unresolved P1: canonical score exact verification. The API E2E failure independently forces `BLOCKED` regardless of the count.

## Final decision

`BLOCKED` — runtime, authentication, real export, local judge, and one authorized score POST completed; memory `no_prior_context` skip completed without POST. The canonical chat-quality run exited `1` because its exact score verification failed, so this candidate must not be handed to user manual acceptance. The failure artifacts and the independent same-ID read-back are preserved for backend repair and a new-run re-verification.
