# Spec 030 report-generation faithfulness prompt review

Date: 2026-10-30  
Reviewer: backend reviewer, narrow independent review  
Scope: `agent_runtime.py` report-quality prompt boundary and `test_report_content_runtime.py`; no production edits.

## Verdict

**PASS.** The prompt provides reusable evidence-faithfulness guidance for the opt-in report-quality path. I found no paper-specific MIGP rule, no claim that runtime can assess semantic truth, and no regression to the legacy synthesizer contract.

## Review findings

- **Generic scope classification:** Each paper analysis must use an existing supported text field to describe its relationship to the research question as `direct`, `adjacent`, or `cross-domain`, identify the object and system layer being authenticated/protected, and classify from the supplied study scope rather than keyword overlap. It explicitly says that the word “authentication” alone does not make a study about user login. The instruction is a general rubric; paper names and domain-specific corrections do not appear in the system prompt. The mixed-example test passes browser risk authentication, password-credential checking, kernel CFI/Pointer Authentication, SMTP DANE/TLSA, and facial liveness excerpts as request context while asserting that those names are absent from the prompt. [Prompt boundary](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/agent_runtime.py:457) [mixed-scope prompt test](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_report_content_runtime.py:254)
- **Simulation versus deployment:** The prompt directs the model to state simulated outcomes as simulation results and separately retain any practical deployment as a deployment fact. If a supplied excerpt reports a deployment, it forbids saying deployment was absent or unverified and limits unknowns to details the excerpt does not provide. The test fixture explicitly contains both a simulated attack result and a practical deployment and checks for the corresponding generic prompt rule.
- **Research-gap provenance:** The prompt distinguishes author-stated future work from gaps inferred from the current evidence scope and requires reviewer-derived gaps to be labeled as inferences. It also prohibits inventing unreported methods, populations, deployment results, limitations, or findings beyond the excerpts/full-text scope.
- **No semantic-validation claim:** These are model instructions, not a new semantic checker. The prompt says runtime validates structure/references and computes an output digest; it does not say runtime can verify relevance, deployment interpretation, or research-gap truth. The capturing-model test checks prompt/context forwarding only. The handoff correctly states that the test cannot prove generated text follows the rubric and leaves final semantic assessment to the acceptance reviewer.
- **Schema and legacy compatibility:** The change adds no report fields or endpoint. It writes the relation explanation into an existing supported text field. `_role_contract_prompt` adds this boundary only when the synthesizer has a `report_quality_context` mapping; the normal legacy synthesizer path continues to use its existing synthesis boundary. The [legacy test](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_report_content_runtime.py:313) still accepts output without `report_content`.

## Verification

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_content_runtime.py` — exit 0, **20 passed in 0.59s**.
- No full suite, real model call, deployment, or Git operation was run.

## Limits

The prompt may improve model behavior but does not mechanically ensure that a future report classifies each source correctly or labels inferred gaps accurately. A subsequent report still needs an independent content review against its evidence, including checks that it does not overstate relevance or summarize unreported deployment outcomes.

## 2026-10-30 follow-up: narrow inferred gaps to excerpt evidence

**Verdict: PASS for the prompt change.** The common opt-in report-quality boundary now asks the model to check every cited excerpt before stating a reviewer-derived gap. When an excerpt already reports the method, measurement, deployment, or high-level result, the gap must identify only a specific detail that remains unclear; missing detail must not be described as absence of the underlying activity or result. The examples (observation window, sample representativeness, temporal granularity) are generic and do not hard-code DANE, MIGP, or any selected paper.

The change only extends prompt text. `_role_contract_prompt` continues to select this boundary only for a synthesizer request carrying a `report_quality_context` mapping; the ordinary legacy synthesis boundary and legacy output contract remain unchanged. No schema fields, persistence behavior, or artifact writes were added, so existing report artifacts are not rewritten by this change. The new fixture verifies that the generic rule reaches the prompt; it does not establish that a model will follow it in a generated report.

Verification for this follow-up:

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_content_runtime.py` — exit 0, **21 passed in 0.60s**.
- `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/application/agent_runtime.py tests/research/test_report_content_runtime.py` — exit 0, **All checks passed**.

This PASS is limited to the prompt implementation and compatibility boundary. It does not clear the existing Task10 acceptance BLOCKED state or validate the previously published report. Generate the requested v6 within the original remaining task budget, then independently review its content against its cited evidence and complete the live browser verification before revisiting acceptance readiness.
