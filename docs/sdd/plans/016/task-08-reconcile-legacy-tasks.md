# 任务 08 — 对账并迁移 spec-013～015

> 关联：[spec-016](../../specs/016-portable-task-ledger.md) ｜ 索引：[README](./README.md)
> 依赖：任务 07 ｜ 被依赖：任务 09 ｜ 当前状态：`完成（云端迁移范围）`

## 一句话目标

基于代码、Git、Task 执行结果和评审证据逐项核对 spec-013～015 的真实进度，只把已验证事实迁入新协议，确保自动执行不会重复已完成工作或把半成品误标完成。

## 当前证据（2026-09-03）

- spec-013 仍为待确认，但 README 记载 Task 02/03 完成、Task 04 部分完成，工作树已有大量观测代码和测试。
- spec-014 已确认，但 README/Task 仍全部写待执行，且可能有另一 Agent 的实现尚未稳定提交。
- spec-015 为待确认，全部 Task 待执行，并依赖 spec-013/014 稳定完成。
- 当前所有 `docs/sdd/plans/` 均为未跟踪目录，不能根据 Git 历史推断其完成时间。
- 本 Task 只做事实对账与协议迁移，不实现 013–015 业务功能。

## 前置门禁

1. Task 07 的 CLI 与 Codex/CodeBuddy Skills 验收通过。
2. spec-013/014 的在途 Agent 已停止写文件或提供稳定交接；无法确认时对应项保持 `migration_unverified`。
3. 对账前记录每个相关 worktree 的 branch、HEAD、status、活跃进程和文档 hash。
4. 禁止 reset、stash、clean、覆盖、移动或删除任何 legacy 工作成果。

## 思维链

### A. 建立只读证据矩阵

1. 对每个 Task 记录文档状态、声明产物、实际文件、相关测试、评审、commit 和运行时证据。
2. 证据强度依次为：已提交文件+测试/验收；未提交文件+可重复测试；仅文档陈述；仅聊天摘要。
3. “代码存在”不等于 Task 完成；缺验收、真实外部 smoke 或文档回填时按部分完成处理。
4. 不为 legacy run 编造开始时间、模型、token、工具调用或耗时。

### B. 分类与迁移

5. 已完成：补 schema v1 元数据，状态 completed，生成 `provenance=legacy` 摘要并列明未知指标。
6. 部分完成：保留原文与证据，创建/修订一个明确剩余 Task；原任务不得假完成。
7. 待执行：补完整 Prompt、返回协议、allowed paths 和依赖，状态 pending。
8. 无法确认或与在途 Agent 冲突：标 `migration_unverified`，CLI 必须拒绝领取。

### C. 状态与依赖收口

9. 同步 Task 权威状态、README/spec 镜像和跨 Spec 依赖。
10. spec-015 的 Task 02 继续依赖 013/014 完成；不得因迁移绕过。
11. 每个 spec 单独运行 doctor；全部通过后 rebuild，再核对 status JSON。
12. 迁移提交只包含该 spec 的文档、legacy run 摘要和必要索引，不混入业务代码。

## 子代理分派计划

### 分派 1：`tester` — spec-013 只读对账

**完整 Prompt：**

```text
你是 spec-016 Task 08 的 tester，负责只读核对 spec-013 Task 02–08 的真实状态。不要实现或修复 spec-013。

只读取：spec-013、plans/013/README 与 Task 02–08、013 相关代码/测试/部署文件、现有评审/复盘、git status/log/diff。只运行不会改 tracked 文件的针对性测试与健康检查。

允许写入：.sdd/runtime/runs/{{RUN_ID}}/spec-013-audit.json 和 result.json。禁止修改 tracked 文件、安装依赖、reset/stash/clean/checkout 覆盖、push/merge。

对每个 Task 输出：document_status、evidence_files、tests、runtime_evidence、commit、classification(completed/partial/pending/migration_unverified)、remaining_work、unknown_metrics、conflicts。代码存在但缺真实 smoke/验收时不得 completed。

result.json 使用 sdd-run-result/v1，列出结论、证据、风险、阻塞和主 Agent 应如何迁移；未知时间/model/token/tool 数写 null。
```

### 分派 2：`tester` — spec-014/015 只读对账

**完整 Prompt：**

```text
你是 spec-016 Task 08 的 tester，负责只读核对 spec-014 Task 02–09 与 spec-015 Task 02–09。不要执行这些业务 Task。

只读取：spec-014/015、两个 plans README 与全部 Task、014 评审、相关 worktree/代码/测试/运行证据、git status/log/diff。不得把当前分支上的相似代码自动归属给某个 Task。

允许写入：.sdd/runtime/runs/{{RUN_ID}}/spec-014-015-audit.json 和 result.json。禁止修改 tracked 文件、外部下载、真实登录、安装依赖、reset/stash/clean/checkout 覆盖、push/merge。

逐 Task 输出 document_status、evidence_files、tests、runtime_evidence、commit、classification、remaining_work、unknown_metrics、conflicts。存在其他 Agent 写入或归属不清时必须 migration_unverified。spec-015 保持未确认且不可领取；其跨 spec 依赖不得放宽。

result.json 使用完整 sdd-run-result/v1；不伪造模型、耗时、token 或登录/下载证据。
```

### 分派 3：`tech-lead` — 迁移裁决

**完整 Prompt：**

```text
你是 spec-016 Task 08 的 tech-lead。依据 tester 的两份 audit 与真实文件，对每个 legacy Task 给出迁移裁决，不写业务代码。

只读取：spec-016/Task 08、docs/sdd/TASK-PROTOCOL.md、spec-013～015 及 plans、两个 audit JSON、相关 git/测试证据。

允许写入：.sdd/runtime/runs/{{RUN_ID}}/migration-decisions.md 和 result.json。禁止直接修改 legacy 文档、业务代码或 Git 历史。

逐 Task 输出唯一裁决：completed/partial/pending/migration_unverified；说明证据和缺口。completed 可生成 legacy 摘要但未知指标必须 null；partial 必须给出决策完整的剩余 Task 目标/边界/验收；unverified 必须给出解除条件。复核跨 spec 依赖和不能自动领取的门禁。

结果必须明确哪些文件可由主 Agent 机械更新、哪些必须等待在途 Agent。使用完整 sdd-run-result/v1。
```

## 子代理返回后主 Agent 必须执行

1. 读回 audit 与 migration decisions，抽查每项证据真实存在。
2. 按 spec 分批迁移文档；纯文档允许架构师落盘，但一次只处理一个 spec，完成后立即 doctor。
3. completed Task 生成独立 legacy run 摘要，所有不可得指标写 null；不得倒推耗时或 token。
4. partial Task 的剩余工作必须有完整 Prompt 和验收；不可确认项保持 migration_unverified。
5. 运行 rebuild/status，确认 015 不可领取、跨 spec 依赖未绕过。
6. 逐 spec 本地提交迁移文档，不包含任何现有业务代码，不 push/merge。

## 实时监控命令

```bash
git status --short --branch
git worktree list --porcelain
python3 -m scripts.sdd_tasks doctor
python3 -m scripts.sdd_tasks status --json
tail -f .sdd/runtime/runs/<run-id>/events.jsonl
```

## 测试与验收标准

- spec-013～015 每个 Task 都有证据矩阵和唯一迁移裁决。
- 完成项不伪造指标，部分完成项不误标完成。
- 在途或归属不明项不可自动领取。
- spec/README/Task 镜像一致，依赖无环且跨 spec 门禁保留。
- 迁移前后现有业务代码字节不变。
- 每个 spec 的迁移提交只含文档和 legacy 摘要。

## 风险、停止条件与回滚

- 其他 Agent 仍写入同一文件：停止该 spec 迁移，保持 unverified。
- 文档与代码无法建立归属：不猜测，记录解除条件。
- 运行测试会改变外部状态或需要登录：不运行，保留阻塞。
- 回滚为恢复迁移前文档版本；不得删除 legacy 证据或业务实现。

## 产出物

- spec-013～015 逐 Task 审计矩阵和迁移裁决。
- schema v1 Task 元数据、完整剩余 Prompt 与 legacy run 摘要。
- doctor/rebuild/status 证据及逐 spec 文档提交。
- 本文件执行结果。

## 执行结果

- Luna xhigh 完成只读审计、迁移与独立检查；root 逐批读回并提交文档。31 项 legacy 为 22 completed、7 partial、1 pending、1 migration_unverified；另建 7 项明确的剩余工作 Task，保留阻塞。
- 迁移后共 38 个协议 Task：22 completed、15 blocked、1 pending；31 份旧正文从首个二级标题起逐字节保留。历史指标保持 null，未生成虚构 Run。
- 013/014/015 parser、三处状态镜像及逐 Spec doctor 通过；rebuild 得到 38 tasks / 0 runs。status 无 eligible，唯一 pending 的 015 Task04 因缺少授权 gate 留在 waiting，Task10 保持 unverified、不可领取。未执行 013–015 业务。
- 真实 015 canonical worktree 仅用于门禁检查。迁移提交：013 `ba0a429`、014 `83fadbe`、015 `4b14130`。账本未初始化提示和未迁移旧文档提示按真实诊断保留。
- 迁移任务兼容旧正文历史状态标记的修复 `37bb056` 通过 10 项定向与 382 项全工具域测试，Ruff、compileall 通过；普通 Task 校验未放宽。
- 证据：[审计](./artifacts/legacy-task-audit.md)、[legacy summaries](./artifacts/legacy-summaries.md)、[迁移验证](./artifacts/legacy-migration-validation.md)、[工具域 QA](./artifacts/task06-final-tool-tests.md)。真实 CodeBuddy A6 仍待本地；Spec016 整体保持实施中。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师（自身） | 创建 Task 08，状态置待执行；明确先对账后迁移 |

