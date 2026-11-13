# Spec-049 Gate 5 合并裁决（签字 A）

> 只读评审。唯一产出：本文档。文档只写结论、事实依据（文件:行 / 命令）与验证方式。
> 签字 A（`architect`，开发主管 · 合并裁决）与签字 R（`tester`，跨端验收总控）**并列、非自批**；签字 R 见 `docs/sdd/reviews/049-acceptance-review.md:138`，本分派不代签、不改动。
> 依据：`docs/sdd/SDD-GATE-CHECKLIST.md` Gate 5 段（:106-113）、§3 收口清单（:128-138）、§4 机械化校验（:140-163）。
> 本分派执行边界：只读核对 + 生成本文档；不改 spec、业务代码、测试、台账、其它评审文档、E2E 证据；不执行任何 git 写操作（无 add / commit / push）。

## 1. 结论

**批准收口。**

| 项 | 值 | 事实依据（文件:行 / 命令） |
|---|---|---|
| 结论 | `批准收口` | 本文件 §1 |
| P0 | 0 | `docs/sdd/reviews/049-frontend-review.md:11-15`；`docs/sdd/reviews/049-acceptance-review.md:22`（阻塞项 0） |
| P1 | 0 | `docs/sdd/reviews/049-frontend-review.md:11-15`；`docs/sdd/reviews/049-acceptance-review.md:22` |
| P2 | 0（本轮实现/验收新增问题计数） | `docs/sdd/reviews/049-frontend-review.md:9-16`（APPROVE，P0=0 / P1=0 / P2=0）、`:106-115`（Review Summary 四档 0） |

- 批准条件核对：`P0=0`、`P1=0`（`docs/sdd/SDD-GATE-CHECKLIST.md:110-112`、`docs/sdd/specs/049-known-nonblocking-followup-cleanup.md:173-174`）→ 满足。
- Gate 2 附意见条目：`docs/sdd/reviews/049-requirement-review.md:15`（P0=0 / P1=0 / P2=4）、`docs/sdd/reviews/049-tech-review.md:15`（P0=0 / P1=0 / P2=5）。该 P2=4 / P2=5 已沉淀为强制约束 C1–C10（`docs/sdd/reviews/049-tech-review.md:100-113`），逐项 10/10 满足（`docs/sdd/reviews/049-frontend-review.md:16,52-63`、`docs/sdd/reviews/049-acceptance-review.md:13,45-60`），非本轮新增问题、非阻塞；如实登记，不隐藏、不计入本轮 P2。
- 验收签字 R 已填：`docs/sdd/reviews/049-acceptance-review.md:8`（通过 / READY）、`:138`；留空则不得转 `已完成` 的条件（`docs/sdd/SDD-GATE-CHECKLIST.md:111`）已解除。

## 2. 签字栏

| 签字 | 角色 | 结论 | 依据 |
|---|---|---|---|
| 签字 R | `tester`（跨端验收总控） | 通过 / READY（已填） | `docs/sdd/reviews/049-acceptance-review.md:8,138` |
| **签字 A** | `architect`（开发主管 · 合并裁决） | **批准收口（本分派填写）** | 本文件 §1；`docs/sdd/specs/049-known-nonblocking-followup-cleanup.md:151`（架构师行含「Gate 5 合并裁决」）；`docs/sdd/SDD-GATE-CHECKLIST.md:106,111` |

- 签字 A 与签字 R 并列、非自批：签字 R 代表跨端验收判定（`docs/sdd/reviews/049-acceptance-review.md:138`），签字 A 代表合并裁决，二者独立落盘。
- 签字 A 落点为本文件；`docs/sdd/reviews/049-acceptance-review.md:139` 的「开发主管签字」字段由收口动作回填，本分派不改动该评审文档。

## 3. DoD 逐项判定（`docs/sdd/SDD-GATE-CHECKLIST.md` §3 七项，:132-138）

| # | §3 条目 | 当前事实（文件:行 / 命令） | 判定 |
|---|---|---|---|
| 1 | 任务计划 / `plans/049/README.md` / task 头部状态一致、所有 task `已完成` | spec 任务计划 `docs/sdd/specs/049-known-nonblocking-followup-cleanup.md:167-169`（02 `进行中`、03 `进行中`、04 `待执行`）；`docs/sdd/plans/049/README.md:11-13`（02 `进行中`、03 `进行中`、04 `待执行`）；`docs/sdd/plans/049/task-02-refresh-spin-promise.md:4`、`task-03-nonblocking-ledger.md:4`「进行中」、`task-04-verification-and-closure.md:4`「待执行」 | **待回填**：当前不一致（02/03 `进行中`、04 `待执行`），须由主会话收口时统一改 `已完成`，不得虚报已一致 |
| 2 | spec 状态 → `已完成` | `docs/sdd/specs/049-known-nonblocking-followup-cleanup.md:8`「实施中」 | **待回填**：收口时转 `已完成`（验收签字 R 已填、签字 A 本文件已签） |
| 3 | `spec-status-changelog.md` 已追加本次状态流转条目 | `docs/sdd/spec-status-changelog.md:811`（新建→待确认）、`:813`（待确认→已确认）、`:815`（已确认→实施中）三条已在 | **部分满足 / 待回填**：三条已追加；须再追加收口条 `实施中 → 已完成` |
| 4 | 评审记录三行结论均为真实结论、无「/」、无占位 | `docs/sdd/specs/049-known-nonblocking-followup-cleanup.md:173`（需求评审「通过（附意见）」）、`:174`（技术评审「通过（附意见）」）、`:175`（验收评审「待评审（未执行）」） | **待回填**：验收行仍「待评审（未执行）」，须如实登记待回填真实结论；§4 校验① `grep -n "结论：/"` = 0 命中 |
| 5 | 变更日志补齐每行（时间 / 角色 / 动作） | `docs/sdd/specs/049-known-nonblocking-followup-cleanup.md:177-183`（当前 3 行，止于「已确认 → 实施中」） | **待回填**：补齐本轮 Gate 4 / Gate 5 / 收口动作行 |
| 6 | spec 引用的每个文档路径真实存在 | §4 校验② `grep -o "reviews/...md"` → `049-acceptance-review.md` / `049-requirement-review.md` / `049-tech-review.md` 全部 `[ -f ]` OK；校验④ `plans/049/task-02/03/04-*.md` 全部 OK；校验① 0 命中 | **满足** |
| 7 | 复盘已落盘 | `ls -1 docs/sdd/retro/ \| grep -i 049` → 0 命中；`find docs/sdd -iname "*049*retro*"` → 0 命中；`docs/sdd/retro/` 现存最新为 `2026-11-12-spec048-literature-map-tabs-closure.md` | **待回填**：Spec-049 复盘尚未落盘 |

- **DoD 满足数 / 待回填数：1 / 6**（当场满足 #6；#1 #2 #3 #4 #5 #7 待主会话收口回填；#3 为「三条已在、收口条待追加」）。
- 全部 6 项待回填均登记于 §7 收口动作清单，不在本分派内执行。

## 4. 边界 1–12 / C1–C10 总判定

> 逐项判定见 tester 报告 `docs/sdd/reviews/049-acceptance-review.md` §2（:28-43）、§3（:45-60），本裁决引用其逐项结论，不重复长表。

| 项 | 总数 | 关键依据 |
|---|---|---|
| 边界 1–12 | **12 / 12 通过** | `docs/sdd/reviews/049-acceptance-review.md:12`、§2 `:28-43`；Gate 4 复核 `docs/sdd/reviews/049-frontend-review.md:37-63` |
| C1–C10 | **10 / 10 满足** | `docs/sdd/reviews/049-acceptance-review.md:13`、§3 `:45-60`；约束唯一落点 `docs/sdd/reviews/049-tech-review.md:100-113`；Gate 4 `docs/sdd/reviews/049-frontend-review.md:16,52-63` |
| 产品使用步骤 | 桌面 4/4、窄屏 3/3、决策项核对齐备、失败恢复 4 行 | `docs/sdd/reviews/049-acceptance-review.md:14`、§4 `:62-86` |
| 十项人工验收准备度 | 10 / 10（阈值 ≥9/10） | `docs/sdd/reviews/049-acceptance-review.md:15,88-103` |
| 单端回归 | 628 passed / EXIT=0 | `docs/sdd/plans/049/runs/task-04/frontend-regression.md:3,16-19` |
| 全量回归 | 4571 passed、2 skipped、EXIT=0、TOTAL 83.00% | `docs/sdd/plans/049/runs/task-04/full-regression.txt:296-297`、`full-regression.exit:1` = `0` |
| 真实浏览器 E2E | 31/31 PASS、`failed_checks=[]`、`conclusion=PASS` | `docs/sdd/plans/049/runs/task-04/browser-e2e.json` |
| 真实 API 案例 | curl `200 OK` 原样响应含实体 ID | `artifacts/spec-049-api-sample.md:16,36,56,76,98-99` |
| 部署验证 | 4×200、live `v=49`/`v=36`、marker `47`/`34`、PASS | `docs/sdd/plans/049/runs/task-04/deploy-verification.json:7-10,13-32` |
| 阻塞项 | 0 | `docs/sdd/reviews/049-acceptance-review.md:22` |

## 5. 已知非阻塞项（9 项）

> 逐项见 `docs/sdd/reviews/049-acceptance-review.md` §6（:120-134）。本裁决只登记总数与统一结论。

- 总数：**9 项**（首跑 FAIL 记录 / Langfuse `:3000` transient / 其它视图 404 / 185 个历史 lint / 无真实 CI workflow 与 branch protection / 覆盖率未设 `fail_under` / 窄屏 2px 余量 / marker 既有脆弱性 / 10 个未跟踪文件）。
- 统一结论：**保持现状、零改动**。
- 不写成「已修复」；不虚报「CI 全绿 / branch protection 通过 / 覆盖率门禁达标」：`docs/sdd/reviews/049-acceptance-review.md:26,134`、`docs/sdd/specs/049-known-nonblocking-followup-cleanup.md:70`。
- ruff 历史记录如实登记、不隐藏：Gate 5 全仓复核 `Found 186 errors`（`docs/sdd/reviews/049-acceptance-review.md:24,41,127,162,178`；历史基线 185 未改、未 `ruff --fix`）；收尾修复后 `186 → 185`（`docs/sdd/reviews/049-acceptance-review.md:172`、`docs/sdd/plans/049/runs/decision-ledger.md:30,39`）。

## 6. 门禁偏差披露（如实登记）

| # | 偏差项 | 事实（文件:行 / 命令） |
|---|---|---|
| 1 | C 类 7 项保持现状、零改动 | `docs/sdd/specs/049-known-nonblocking-followup-cleanup.md:48,50-54`（NB3–NB8、NB10）、`docs/sdd/plans/049/runs/decision-ledger.md:22,41-43`；未创建 `.github/workflows/**`、未改 `.coveragerc`、未改远端设置、未启动 Langfuse、未改 CSS / 窄屏余量 / marker、未清理未跟踪文件 |
| 2 | 无真实 CI workflow / 无 branch protection | `test -d .github` → `ABSENT`（本分派实测）；`docs/sdd/reviews/049-acceptance-review.md:26,128`；`docs/sdd/plans/049/runs/decision-ledger.md:16`；`docs/github.md:16,28`（规则说明，非真实 workflow） |
| 3 | 覆盖率未设 `fail_under` | `grep -n "^fail_under" .coveragerc` → 0 命中（本分派实测）；`docs/sdd/reviews/049-acceptance-review.md:26,129`；`docs/sdd/plans/049/runs/decision-ledger.md:17`；实测 `TOTAL 83.00%`（`full-regression.txt:296`） |
| 4 | 省略 PR、直接快进推送远端 `main`（交付方式）；不 force push、不新建 PR | `docs/sdd/specs/049-known-nonblocking-followup-cleanup.md:11,56,96`、`docs/sdd/plans/049/runs/decision-ledger.md:45`、`docs/sdd/plans/049/README.md:20`、`docs/sdd/plans/049/task-04-verification-and-closure.md:50`；`grep -rnE -- "--force\|gh pr create" docs/sdd/plans/049/` 命中行均为否定式声明（`docs/sdd/reviews/049-acceptance-review.md:146-147`） |
| 5 | 首跑 E2E FAIL 保留 | `docs/sdd/plans/049/runs/task-04/browser-e2e-run1.json` `28/29`、`conclusion=FAIL`、`failed_checks=["spin_not_fixed_700ms"]`；`docs/sdd/reviews/049-acceptance-review.md:105-118,124,174`（2341 行 + 两张截图保留、sha 前后一致）；正式结果 `browser-e2e.json` 31/31 PASS |
| 6 | B007 修复记录 | `docs/sdd/plans/049/runs/task-04/browser_e2e.py:224` `for i` → `for _`（仅 1 行）；`docs/sdd/reviews/049-acceptance-review.md:167-178` §10；全仓 ruff `186 → 185`、单文件 `All checks passed!`、E2E 重跑 31/31 EXIT=0 |
| 7 | 本分派 git 事实 | `git branch --show-current` = `feature/spec-047-followup-cleanup`；`git rev-parse HEAD` = `b160c58dd16ccccb52f9ad234db2596c9d8de5cb`；`git status --short` = 7 个 tracked 改动 + 若干未跟踪文档；HEAD 未变、无 add / commit / push |

- 分支名 `feature/spec-047-followup-cleanup` 承载 Spec-049 交付、交付方式为直接快进推送远端 `main`，均为定案事实（`docs/sdd/specs/049-known-nonblocking-followup-cleanup.md:11,56`），如实登记。

## 7. 收口动作清单（给主会话执行；本分派不执行）

| # | 动作 | 对应 DoD 项 |
|---|---|---|
| 1 | spec 状态 `实施中 → 已完成`（`docs/sdd/specs/049-known-nonblocking-followup-cleanup.md:8`） | #2 |
| 2 | 任务 02 / 03 / 04 状态统一改 `已完成` | #1 |
| 3 | `docs/sdd/plans/049/README.md:11-13` 与 `task-02/03/04-*.md:4` 头部同步 `已完成` | #1 |
| 4 | spec「评审记录」验收行 `:175` 回填真实结论 | #4 |
| 5 | spec「变更日志」`:177-183` 补齐本轮各行（时间 / 角色 / 动作） | #5 |
| 6 | `docs/sdd/spec-status-changelog.md` 追加 `实施中 → 已完成` 收口条 | #3 |
| 7 | 复盘落盘至 `docs/sdd/retro/` | #7 |
| 8 | 本地 `git commit`（文档随实现一并提交，`docs/sdd/SDD-GATE-CHECKLIST.md:176`） | 交付 |
| 9 | 省略 PR、直接快进推送远端 `main`；不 force push、不新建 PR | 交付 |

- 收口动作 1–9 由主会话执行；本分派不修改任何既有文件、不执行任何 git 写操作。
- `docs/sdd/reviews/049-acceptance-review.md:139` 开发主管签字段的回填归入收口动作 4 同批；本分派不改动该评审文档。

## 8. 验证方式（本裁决只读命令清单）

| 编号 | 命令 | 输出 |
|---|---|---|
| V1 | `git branch --show-current` / `git rev-parse HEAD` / `git status --short` | `feature/spec-047-followup-cleanup` / `b160c58d…` / 7 tracked `M` + 未跟踪文档 |
| V2 | `grep -n "结论：/" docs/sdd/specs/049-known-nonblocking-followup-cleanup.md` | 0 命中（§4 校验①） |
| V3 | §4 校验② `grep -o "reviews/…md"` + `[ -f ]` | `049-acceptance-review.md` / `049-requirement-review.md` / `049-tech-review.md` 全部 OK |
| V4 | §4 校验④ `grep -o "plans/049/task-…md"` + `[ -f ]` | `task-02` / `task-03` / `task-04` 全部 OK |
| V5 | `test -d .github` / `grep -n "^fail_under" .coveragerc` | `ABSENT` / 0 命中 |
| V6 | `cat docs/sdd/plans/049/runs/task-04/full-regression.exit` / `tail -6 …/full-regression.txt` | `0` / `TOTAL …83.00%`、`4571 passed, 2 skipped…` |
| V7 | `grep -oE '"(conclusion|passed|total)"…' …/browser-e2e.json` / `…/browser-e2e-run1.json` | `31/31 PASS, failed_checks=[]` / `28/29 FAIL` |
| V8 | `cat …/deploy-verification.json` | 4×200、`conclusion: PASS` |
| V9 | `ls -1 docs/sdd/retro/ \| grep -i 049` / `find docs/sdd -iname "*049*retro*"` | 0 命中 / 0 命中（复盘待回填） |
| V10 | `grep -n "Spec049" docs/sdd/spec-status-changelog.md` | `:811`（新建→待确认）/ `:813`（待确认→已确认）/ `:815`（已确认→实施中）三条 Spec049 状态条（收口条待追加）；`grep -n "049" …` 另含 `:307` 一处 `app.js:1049` 行号误命中，共 4 行 |
