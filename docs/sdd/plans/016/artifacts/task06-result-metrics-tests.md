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

## 2026-10-14 服务入口恢复后定向复测

- 未 push 的旧服务源码已在新环境重建，当前 complete_run/fail_run 尚未接入 CLI。主 agent 读回后修复观察事件时间晚于终态 ended_at 的问题：合法结果先记录真实观察，再获取最终服务端时间；无效结果和 complete 的失败命令不写观察。
- `/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_completion_service`：2 个测试方法通过，4.800 秒。成功方法包含 NULL/非 NULL 数据库 model 两种真实完成流程；拒绝方法包含损坏 JSON、敏感内容、重复键与 NaN 四种输入。
- 实际声明命令覆盖自报命令，时间来自服务端，观察事件恰好一条且不晚于 ended_at；首次无 run 目录可完成。无效输入不执行命令、不记录观察且账本不变。Ruff 0.17.0 对服务和测试通过。
- fail 的真实非零命令、部分代码保留、blocked、重放及失败历史恢复尚待本环境验收，不以旧环境记录冒充通过。
  其中非零 fail/部分源码的后续复测见下文；blocked、重放及失败历史仍待验收。

## J7 final suite recheck

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

## Task06 completion-service QA reconstructed after reset

This QA slice reconstructs completion-service tests whose unpushed workspace changes were lost in an
environment reset. The historical run output and any prior push were not recovered; the evidence
below is from the current focused rerun only. Four test methods cover two success model cases, four
invalid JSON/content cases, a nonzero validation followed by failed publication for the same run,
and a failed outcome with an actual passing validation and an unstaged source edit.

The success path reruns the task's declared command, publishes the server-owned timestamps and
actual command receipt, preserves a draft model only when the database model is null, and records
one private workspace observation before the returned result end time. Malformed, sensitive,
duplicate-key, and NaN inputs fail before validation, observation, database changes, or run-directory
creation. A successful completion with a deleted validation input is refused after the actual
nonzero command receipt is written; the lease and ledger stay active. `fail_run` then publishes the
accurate deletion in the public result, closes the lease, and commits only the run summary. A
separate failed-outcome case confirms a passing command does not stage or commit its modified source.

```text
/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_completion_service
Ran 4 tests in 9.505s — OK
/workspace/researchagent-cli-venv39/bin/ruff check scripts/sdd_tasks/completion_service.py tests/sdd_tasks/test_completion_service.py
All checks passed
```

## 2026-10-14 Completion-service elapsed time and principal replay QA

The updated Python 3.9 service suite passes 9 tests in 17.410s; Ruff passes. The returned
`duration_ms` is checked against the floored elapsed milliseconds between the server's returned
`started_at` and `ended_at`. For both terminal complete and fail journals, a wrong principal with
malformed raw input is rejected before validation or observation; the journal, ledger, and public
result remain unchanged. This service-level replay check does not cover the separate CLI result-file
read behavior or failed-history/new-retry flow.

```text
/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_completion_service
Ran 9 tests in 17.410s — OK
/workspace/researchagent-cli-venv39/bin/ruff check scripts/sdd_tasks/completion_service.py tests/sdd_tasks/test_completion_service.py
All checks passed
```

## 2026-10-14 服务重放与 principal 校验增量

Luna xhigh 新增真实 journal 重放和错误 executor 测试；主 agent 读回后，Python 3.9 服务套件
6 项通过（9.949 秒），Ruff 通过。合法重放忽略损坏的草稿，不再次验证或写观察事件，
账本、journal 和结果保持一致。错误 executor 在读取草稿前被拒绝且不创建运行时目录。
本增量不覆盖显式 blocked、观察已保存但 journal 缺失和 CLI 路由。

The temporary repository fixtures emitted `stale_task_copies_ignored` warnings during catalog
rebuild; all four tests passed. This slice does not cover blocked outcomes, the three-failure retry
threshold, existing-journal replay with raw-input bypass, failed-history/public-caller proof, or CLI
wiring. Those remain separate QA gates.

## 2026-10-14 五个真实进程中断点

Luna xhigh 独立 QA 扩展 `test_completion_crash_recovery.py`，主 agent 读回后执行：
Python 3.9 定向套件 2 项测试、5 个中断点通过，耗时 10.822 秒；两个指定测试文件 Ruff 通过。
中断点为文档写入后、CAS 后、SQLite COMMIT 后、owned index image 部分写入后及 index rename 后。
恢复使用 fresh-spawn 进程，核验单一 run、无残留 lease/index.lock、候选 HEAD、索引树和重建结果。
partial-index 阶段另外核验 owned inode 与原始 image 严格前缀；rename 阶段核验已安装索引 hash。
这是进程退出实验，不构成断电实验。fixture 的 stale_task_copies_ignored warning 为预期。

`completion_recovery.py` 与失败历史核心目前仅完成主 agent 源码读审、Python 3.9 编译及 Ruff；
恢复拒绝矩阵、失败历史文档证明及 CLI 接线尚待独立验收，不视为已完成。


## 2026-10-14 Completion-recovery QA

A fresh focused run covers missing and malformed journals, mocked ALIVE/UNKNOWN/DEAD owners with an
unexpired lease, and real dead-owner recovery. Missing journal returns `None` without database
changes; malformed and unsafe-to-recover cases preserve both database rows and journal bytes. The
real recovery fixture exits its owner process at the documents crash point, expires the lease, then
recovers the durable journal. Replaying its completed terminal journal returns the same public
result. Owner-status refusal cases use a patched classifier; the dead-owner acceptance uses a real
child-process exit.

```text
/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_completion_recovery
Ran 3 tests in 2.935s — OK
/workspace/researchagent-cli-venv39/bin/ruff check scripts/sdd_tasks/completion_recovery.py tests/sdd_tasks/test_completion_recovery.py
All checks passed (Ruff 0.16.10)
```

A failed terminal run followed by a real new retry, failed-history verification, and CLI wiring are
not covered by this slice. No retry was synthesized with direct SQL.

## 2026-10-14 Prepared-journal crash boundary

Three methods cover seven real process exits, including exits before and halfway through the first prepared-journal write; the latter leaves only a fsynced mode-0600 strict-prefix temp. Both initial-write crashes leave `completion.json` absent; `resume_dead_completion()` returns `None` with the active run, pending Task, and lease unchanged. This verifies only the no-journal Task05 boundary; public recovery routing remains pending.
```text
/workspace/researchagent-cli-venv39/bin/python -m unittest tests.sdd_tasks.test_completion_crash_recovery
Ran 3 tests in 11.633s — OK
/workspace/researchagent-cli-venv39/bin/ruff check tests/sdd_tasks/test_completion_crash_recovery.py tests/sdd_tasks/test_completion_prepare.py
All checks passed
```

## 2026-10-14 Completion-service blocked and journal-gap QA

The focused Python 3.9 suite passes 8 tests in 13.242s and Ruff passes. A real blocked `fail_run`
executes the declared command successfully, then commits exactly three blocked status mirrors plus
the run summary; the source path is excluded and remains byte-for-byte unchanged.

A private observation without a completion journal makes both `complete_run` and `fail_run` return
`COMPLETION_RECOVERY_REQUIRED` before validation, preserving ledger rows without journal/receipt
creation or validation/observation reruns. A real failed-history/new-retry flow and CLI routing remain
untested by this service slice.

独立补充验收：`python -m unittest tests.sdd_tasks.test_cli_completion tests.sdd_tasks.test_cli_recover`
共 6 项通过（8.697 秒），新 CLI 测试 Ruff 通过；覆盖 complete/result/metrics、缺草稿的重放、
fail、结果文件 symlink/超限拒绝以及真实崩溃后的 CLI recover。fail 的完整提交路径证明待扩展。
`python -m unittest -v tests.sdd_tasks.test_failure_history` 2 项通过（3.94 秒），Ruff 通过；
真实失败提交仅含 summary，源代码保留；校验读取不改 DB、HEAD/refs、索引和对象文件列表。
篡改工作树 summary 会被拒绝。此轮未覆盖多次失败后的真实新 retry。

后续独立增量：CLI 与旧恢复 6 项通过（7.777 秒），失败草稿采用 Task worktree 内的相对路径，
真实 journal 仅提交 summary；SOURCE 保持修改、未暂存，HEAD 内容仍为 baseline。Ruff 通过。
真实中断套件 3 项、7 个退出点通过（12.782 秒）；首次 journal 写入前/中断的两个场景进一步
走通 CLI recover → abandoned/partial → 私有观察解码 → 同 Task child 领取，snapshot 严格保持原基线。
失败历史套件扩至 5 项通过（9.669 秒），Ruff 通过；覆盖额外 SOURCE commit、篡改私有 Git anchor
的拒绝，以及已暂存 SOURCE 的只读证明。上述 fixture 均有预期 stale_task_copies_ignored warning。

## 2026-10-14 工具域阶段回归

独立 Luna xhigh 执行 `python -m unittest discover -s tests/sdd_tasks -t .`：
348 项通过，129.610 秒；`ruff check scripts/sdd_tasks tests/sdd_tasks` 通过。
测试前 HEAD 为 `a4d704d`，存在尚未跟踪的 failed_workspace.py；测试后 HEAD 为 `8a2020a`，
service 测试有并行增量。故此为阶段性工具域回归，不冒充冻结源码的最终 Spec 验收，
也不覆盖尚无测试的 failed_workspace 模块。业务全量回归尚未执行。

随后服务定向套件 9 项通过（17.410 秒），Ruff 通过；新增精确服务端 duration_ms 检查，
及 complete/fail 两条已有 journal 的错误 principal 重放拒绝和无副作用检查。

```text
/workspace/researchagent-cli-venv39/bin/python -m unittest -v tests.sdd_tasks.test_completion_service
Ran 8 tests in 13.242s — OK
/workspace/researchagent-cli-venv39/bin/ruff check scripts/sdd_tasks/completion_service.py tests/sdd_tasks/test_completion_service.py
All checks passed
```
