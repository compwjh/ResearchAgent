# Agent evaluation report

- Schema: <code>agent-evaluation-report-v1</code>
- Status: <code>completed</code>
- Started at: <code>2026-11-08T06:04:42.722204+00:00</code>
- Finished at: <code>2026-11-08T06:05:09.003157+00:00</code>
- Human agreement: <code>not evaluated</code>
- Constructed gold only: <code>True</code>

## Summary

| metric | count |
|---|---:|
| <code>scored</code> | <code>2</code> |
| <code>skipped</code> | <code>1</code> |
| <code>unavailable</code> | <code>0</code> |
| <code>written</code> | <code>2</code> |
| <code>verified</code> | <code>2</code> |
| <code>failed</code> | <code>0</code> |
| <code>no_prior_context</code> | <code>0</code> |

## Metadata

| key | value |
|---|---|
| <code>dataset_sha256</code> | <code>&quot;19f49906f5e105ff255f641eab3c0380354689e58150e453fdaf668664977bfb&quot;</code> |
| <code>fallback_judge</code> | <code>&quot;qwen3.8:27b&quot;</code> |
| <code>judge_model</code> | <code>&quot;qwen3.5:9b&quot;</code> |
| <code>judge_model_digest</code> | <code>&quot;888f03bdc66326065533f76c1b66ea0878331d271f3f8179ee2df54ccf791db8&quot;</code> |
| <code>max_items</code> | <code>3</code> |
| <code>prompt_sha256</code> | <code>&quot;c77ee587c9fb237d0c14bbd63a266036ce458dba7d8800926a21dda6d1d272d8&quot;</code> |
| <code>repeats</code> | <code>3</code> |
| <code>seed</code> | <code>42</code> |
| <code>source</code> | <code>&quot;export&quot;</code> |
| <code>task</code> | <code>&quot;chat_quality&quot;</code> |
| <code>tie_break_rule</code> | <code>&quot;majority_label: among labels tied at the top count, prefer the label with the highest mapped score (per task ENUM_MAPS); ties broken alphabetically&quot;</code> |

## Items

| trace_id | status | model | score | score_id | requested | expected_value | post_status | verified_value | verified |
|---|---|---|---:|---|---|---:|---|---:|---|
| <code>0639caa627e3d6d09d8db08214edc486</code> | <code>skipped</code> | <code>&lt;unknown&gt;</code> | <code></code> | <code></code> | <code></code> | <code></code> | <code></code> | <code></code> | <code></code> |
| <code>0b654de23faadce42fc3efdc07de0ccf</code> | <code>scored</code> | <code>qwen3.5:9b</code> | <code>1.0</code> | <code>eval042-24ab881c34306f2953a5fb8a71cae8b4</code> | <code>True</code> | <code>1.0</code> | <code>written</code> | <code>1.0</code> | <code>True</code> |
  - Judge rationale: <code>reason_code=judge_explanation_source_echo_redacted</code>
| <code>0f62b5e18f6fd83287e371a19b4aa373</code> | <code>scored</code> | <code>qwen3.5:9b</code> | <code>0.0</code> | <code>eval042-688cb81c7eb36537f91fe9c93a4ea161</code> | <code>True</code> | <code>0.0</code> | <code>written</code> | <code>0.0</code> | <code>True</code> |
  - Judge rationale: <code>The answer is irrelevant because it fails to address the empty input context provided in the question.</code>

_Trace payloads, prompts, completions, hidden reasoning, and credentials are omitted._
