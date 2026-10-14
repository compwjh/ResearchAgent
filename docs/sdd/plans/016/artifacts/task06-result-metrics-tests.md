# Task 06 Result and Metrics QA

## Scope

Added read-only QA for `result_for_run`, metrics export/filtering, and the ownerless CLI result/metrics
commands. The tests use isolated temporary Git repositories and real SQLite ledgers; no production
files were changed by this QA work.

| Batch | Test artifact | Added / deleted lines | Focus |
|---|---|---:|---|
| 1 | `tests/sdd_tasks/test_result_query.py` | 95 / 0 | Terminal canonical result; invalid, missing, and active run refusal; ledger mismatch and absent summary; DB/file read-only snapshots. |
| 2 | `tests/sdd_tasks/test_metrics.py` | 118 / 0 | Fixed JSON/CSV schema, exact filters and time boundaries, stable ordering, null/provenance semantics, private owner/event exclusion, and no writes. |
| 3 | `tests/sdd_tasks/test_metrics.py` | 41 / 0 | Unknown change counts stay null; observed empty changes yield zero; malformed or missing summary refuses the whole export. |
| 4 | `tests/sdd_tasks/test_cli_results.py` | 59 / 0 | `main()` result/metrics envelopes, parsed JSON vs CSV content, no owner arguments, and missing-runtime refusal without creation. |
| 5 | `tests/sdd_tasks/test_result_query.py` | 68 / 1 | Completed Task status keeps the stable definition hash; malformed, duplicate, private, and symlink-parent summaries refuse read-only. |
| 6 | `tests/sdd_tasks/test_result_query.py` | 12 / 5 | Duplicate-key and sensitive-value tests now start from a full valid result; each introduces only its target fault. |

## Validation

```text
/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_result_query
Ran 5 tests — OK (exit 0)
/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_result_query.py
All checks passed (exit 0)

/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_metrics
Ran 4 tests — OK (exit 0)
/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_metrics.py
All checks passed (exit 0)

/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_cli_results
Ran 2 tests — OK (exit 0)
/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_cli_results.py
All checks passed (exit 0)
```

Result, metrics, and CLI focused coverage totals 11 tests. An initial pytest invocation exited 1 during the repository-wide
`conftest.py` autouse setup because `python-dotenv` is absent (`ModuleNotFoundError: dotenv`); no test
body ran. The requested Python 3.9 stdlib unittest commands passed. The repo's `.sdd/runtime` was
not used or changed; runtime and result fixtures stayed inside temporary repositories.

## J7 helper QA (limited fixture)

Two focused batches added six tests in `tests/sdd_tasks/test_ledger_finalize.py` (100 additions, then
99 additions). They use a real claimed run and SQLite ledger in a temporary Git fixture, while the
journal is assembled as a structurally valid `index_reconciled`/`ledger_finalizing` envelope. The
tests cover derived terminal model/result path/artifact values, artifact membership mismatch,
expired-lease phase rules, owner/hash/worktree bindings, first-public-event start time, and failure
streak calculation. The expired-owner classifications are deliberately mocked (`ALIVE`, `UNKNOWN`,
`DEAD`); this verifies the helper's decision rules, not OS process-death observation. The constructed
journal's expected index and commit entries are shape-valid fixture data and do not prove a real Git
index transition or candidate commit. These six helper tests alone do not cover public finalization,
transaction rollback, crash replay, or retry; the final suite recheck below adds separate public-path
fixtures.

```text
/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_ledger_finalize
Ran 6 tests — OK (exit 0)
/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_ledger_finalize.py
All checks passed (exit 0)
```

## Workspace observation QA (private helpers only)

Three test batches added `tests/sdd_tasks/test_workspace_observation.py`. Batch 1 created the
141-line fixture and its four initial tests. Batch 2 added the positive record-to-terminal-failure
decoder case and hardened the malformed/secret payload cases (46 additions, 6 deletions; net 40).
Batch 3 added baseline-copy and refusal coverage (122 additions, 1 deletion). The source-file batch
totals are exact additions/deletions, not net sizes.

| Batch | Added / deleted lines | Coverage |
|---|---:|---|
| 1 | 141 / 0 | Active owner records one private event and syncs one log; idempotent replay; owner/time/snapshot mismatch and post-capture workspace change refuse without DB writes. |
| 2 | 46 / 6 | Real record→failed-run→decode preserves canonical roots and original snapshot hashes after files change; malformed time/path/symlink, duplicate event/key, NaN, status path, and extra owner payload refusals. |
| 3 | 122 / 1 | Private failed-baseline helper returns the original copied snapshot read-only; malformed/missing/duplicate/gapped/out-of-time events, run-hash/owner mismatch, and self-cycle refuse read-only. |

The payload scanner still checks status paths and all extra/private payload fields. Only the three
already-validated canonical root fields (`repo_root`, `common_dir`, and `worktree_path`) are omitted
from the scanner's validation copy; the stored payload remains complete. The positive decoder test
also intentionally corrupts the initial `workspace_snapshot` event and still decodes the observation.
This records the boundary: `_decode_observation_event` validates an observation envelope against
its supplied expected tip; it does not establish complete journal history or independently prove
that expected tip. `_load_failed_run_baseline` checks the original copied snapshot and its local
event bindings only. These private-helper fixtures do not demonstrate multi-hop failed/abandoned
lineage, public recovery eligibility, or the Task 05 expired-owner-before-observation transition
(which must classify as abandoned).

```text
/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_workspace_observation
Ran 7 tests — OK (exit 0)
/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_workspace_observation.py scripts/sdd_tasks/workspace_observation.py
All checks passed (exit 0)
git diff --check
Passed (exit 0)
```

## Task05 abandoned ancestry follow-up

Two approved test-file batches add a real expired-owner recovery transition and abandoned-ancestor
guards. Batch 4 changed `tests/sdd_tasks/test_workspace_observation.py` by 66 additions and 1
deletion. Batch 5 added 43 lines. The Task05 fixtures record an observation while the actual owner
process is alive, terminate it, expire the lease, and call `recover_expired`; one path returns
`abandoned/requeued` with `unchanged`, and the other changes one allowed file and returns
`abandoned/preserved_for_recovery` with `partial`. The latter uses actual `claim_next` to create a
linked recovery child and checks that the private baseline helper returns the original copied
snapshot across that observed abandoned parent. An initially failing regression exposed the
abandoned-observation rejection; after the source fix, the full focused suite passes.

The unchanged path directly validates the legal optional recovery-decision event and decodes the
abandoned observation. Added read-only refusals cover a malformed observation envelope and an event
after the recovery decision. The recovery parent, owner death, lease recovery, and child claim use
real APIs; the child is marked terminal failed by a direct SQLite update. These fixtures do not run
Task06 finalization or prove public failed-history recovery eligibility. The selected failed run's
observation tip still requires the separate history verifier.

```text
/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_workspace_observation
Before the abandoned-envelope guards: Ran 9 tests in 33.188s — OK
After the guards: Ran 10 tests in 89.762s — OK
/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_workspace_observation.py scripts/sdd_tasks/workspace_observation.py
All checks passed (exit 0)
git diff --check
git diff --cached --check
Both passed (exit 0)
```

## J7 final suite recheck

## 2026-10-14 服务入口恢复后定向复测

- 未 push 的旧服务源码已在新环境重建，当前 complete_run/fail_run 尚未接入 CLI。主 agent 读回后修复观察事件时间晚于终态 ended_at 的问题：合法结果先记录真实观察，再获取最终服务端时间；无效结果和 complete 的失败命令不写观察。
- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_completion_service`：2 个测试方法通过，4.800 秒。成功方法包含 NULL/非 NULL 数据库 model 两种真实完成流程；拒绝方法包含损坏 JSON、敏感内容、重复键与 NaN 四种输入。
- 实际声明命令覆盖自报命令，时间来自服务端，观察事件恰好一条且不晚于 ended_at；首次无 run 目录可完成。无效输入不执行命令、不记录观察且账本不变。Ruff 0.17.0 对服务和测试通过。
- fail 的真实非零命令、部分代码保留、blocked、重放及失败历史恢复尚待本环境验收，不以旧环境记录冒充通过。

The expanded suite includes 16 tests: six helper tests plus ten public-path finalizer tests. It
covers committed terminal rows and lease closure, failed-run results and retries, database rollback,
pre-transaction journal-write failure, and replay after terminating the fixture child once. The
expired-owner acceptance test still mocks `DEAD`; process-death classification is not integration
tested. Synthetic journal index/commit entries remain shape-valid only, with no full Git candidate
lifecycle proof.

```text
/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_ledger_finalize
Ran 16 tests — OK (exit 0)
/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_ledger_finalize.py
All checks passed (exit 0)
```
