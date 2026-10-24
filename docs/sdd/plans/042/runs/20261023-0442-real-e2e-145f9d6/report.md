# Agent evaluation report

- Schema: <code>agent-evaluation-report-v1</code>
- Status: <code>completed</code>
- Started at: <code>2026-10-22T22:19:50.903592+00:00</code>
- Finished at: <code>2026-10-22T22:20:14.847053+00:00</code>
- Human agreement: <code>not evaluated</code>
- Constructed gold only: <code>True</code>

## Summary

| metric | count |
|---|---:|
| <code>scored</code> | <code>1</code> |
| <code>skipped</code> | <code>0</code> |
| <code>unavailable</code> | <code>0</code> |
| <code>written</code> | <code>1</code> |
| <code>verified</code> | <code>1</code> |
| <code>failed</code> | <code>0</code> |
| <code>no_prior_context</code> | <code>0</code> |

## Metadata

| key | value |
|---|---|
| <code>fallback_judge</code> | <code>&quot;qwen3.8:27b&quot;</code> |
| <code>judge_model</code> | <code>&quot;qwen3.5:9b&quot;</code> |
| <code>max_items</code> | <code>1</code> |
| <code>repeats</code> | <code>3</code> |
| <code>source</code> | <code>&quot;export&quot;</code> |
| <code>task</code> | <code>&quot;chat_quality&quot;</code> |

## Items

| trace_id | status | model | score | score_id | requested | expected_value | post_status | verified_value | verified |
|---|---|---|---:|---|---|---:|---|---:|---|
| <code>9a93fe5d085320fdd3a39f3101327a1e</code> | <code>scored</code> | <code>qwen3.5:9b</code> | <code>1.0</code> | <code>cf95289f-8ef0-4d08-a0a6-81759a6f359e</code> | <code>True</code> | <code>1.0</code> | <code>written</code> | <code>1.0</code> | <code>True</code> |
  - Judge rationale: <code>reason_code=judge_explanation_source_echo_redacted</code>

_Trace payloads, prompts, completions, hidden reasoning, and credentials are omitted._
