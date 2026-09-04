# 任务 09 — 评审、验收、提交与复盘

> 关联：[spec-016](../../specs/016-portable-task-ledger.md) ｜ 索引：[README](./README.md)
> 依赖：任务 08 ｜ 当前状态：`待执行`

## 一句话目标

由 tester 独立执行 A1–A14、由 tech-lead 审查并签字，完成文档、Git、运行时和复盘收口后，再把 spec-016 标记为已完成并正式启用新 Task 流程。

## 当前证据（2026-09-03）

- spec-016 尚为待确认，三份评审未执行。
- CLI、Skills、SQLite 与 legacy 迁移均尚未实现。
- 当前 ResearchAgent 业务工作树有其他 Spec 未提交修改，最终验收必须在 spec-016 独立 worktree 中进行。
- 本任务不得用“单测通过”替代 Codex/CodeBuddy 真实 smoke、数据库重建和中断恢复。

## 前置门禁

1. Task 02–08 均已完成并回填真实命令、结果、风险、产物和变更日志。
2. 需求评审、技术评审已在实施前真实通过；若缺失，不得补写成事前评审。
3. spec-013～015 的未验证项有明确阻塞，不要求为完成 016 而伪造 legacy 状态。
4. `git status` 可区分 spec-016 改动与其他 worktree；无冲突标记和敏感文件。

## 思维链

### A. 静态与自动化验收

1. 运行 Task schema、SQLite、并发 claim、worktree、生命周期、脱敏、Skill 和迁移全部测试。
2. 删除隔离 fixture DB 后 rebuild，比较前后持久 Task/run 输出。
3. 两进程竞争、三次失败、活跃/过期租约、有/无部分改动中断逐项复验。
4. 检查 commit 只含 allowed paths，不存在 push/merge 或敏感数据。

### B. 双 IDE 真实验收

5. 在隔离 fixture 创建两个可执行 Task，让 Codex 执行“执行目前未完成的 Task”，确认只领取第一个并调用正确逻辑角色。
6. 重置 fixture 运行状态后由 CodeBuddy 执行同一句话，确认选择、Prompt、result schema 一致。
7. 制造缺角色、缺 result、需用户输入和越界修改，验证弱调度器全部停止而不代行。
8. 换一个 IDE/新会话只读 Git 文档，要求其说明当前进度、最后结果和下一 Task。

### C. 项目回归、文档与部署

9. 运行 ResearchAgent 全量测试，确认流程工具未改变业务行为。
10. 按项目正式命令启动服务；验证首页与 `/api/health`，默认端口占用时选择可用端口。
11. tester 产出 `016-acceptance-review.md`；tech-lead 做代码/安全审查并签字。
12. 完成复盘、Task/spec/README 状态、状态台账、引用检查和本地原子提交；不 push/merge。

## 子代理分派计划

### 分派 1：`tester` — A1–A14 独立验收

**完整 Prompt：**

```text
你是 spec-016 Task 09 的 tester。独立执行 spec-016 A1–A14，不修业务代码，不降低验收条件。

重点读取：spec-016 全文、Task 02–09 的执行结果、docs/sdd/TASK-PROTOCOL.md、新 CLI/Skills/tests、spec-013～015 迁移摘要。按需读取真实实现，不全项目扫描。

必须执行：全部 sdd_tasks 单测；两进程 claim；SQLite 删除/rebuild；成功/失败/blocked/recover；越界与敏感信息拒绝；Git 精确提交；Codex 与 CodeBuddy 真实或可验证 smoke；ResearchAgent 全量回归；服务启动后的首页和 /api/health。

不得修改业务代码、spec、Task 状态或实现；发现缺陷记录不通过并退回对应 Task。禁止伪造另一个 IDE、用户交互、测试数量、运行地址、模型或 token 数据。

报告写入 docs/sdd/reviews/016-acceptance-review.md，逐 A1–A14 写环境、命令、证据、判定、风险和总结；开发主管签字栏留空。另写 .sdd/runtime/runs/{{RUN_ID}}/result.json，使用完整 sdd-run-result/v1。

最终回传：通过数/总数、结论、失败项、报告路径、result 路径、日志路径、服务实际地址。
```

### 分派 2：`tech-lead` — 代码、安全与验收签字

**完整 Prompt：**

```text
你是 spec-016 Task 09 的 tech-lead。基于真实代码、Git diff、测试和 tester 报告完成最终审查；只有全部满足才签字。

只读取：spec-016、Task 02–09 执行结果、016 三份评审、TASK-PROTOCOL、新 CLI/Skills/tests、legacy 摘要、Git diff/log 与 tester 原始证据。

必须复核：文档是持久事实源且 DB 可重建；事务防双领取；worktree 不清理用户改动；Task/Prompt hash；allowed paths 和精确 stage；失败恢复；敏感信息脱敏；弱调度器不代行；两个 IDE 使用相同协议；无 push/merge；业务回归和服务 smoke 真实。

发现任一缺陷时结论不通过，列出应退回 Task 03–08 的具体项，不签字、不改代码。全部通过时在 016-acceptance-review.md 开发主管签字栏填写角色、模型、时间、证据与“通过”。

把审查结果另写 .sdd/runtime/runs/{{RUN_ID}}/result.json，使用完整 sdd-run-result/v1；不可得指标写 null，不伪造。
```

## 子代理返回后主 Agent 必须执行

1. 读回 acceptance report、签字、result JSON、测试输出和服务日志；不只看子 Agent 摘要。
2. 若任何 A1–A14 不通过或签字为空，保持 spec 实施中并退回归属 Task。
3. 运行全仓冲突标记、敏感文件、死链接、Task 状态镜像、Git diff/check-ignore 检查。
4. 写 `docs/sdd/retro/2026-*-spec-016-*.md`，记录跨 IDE、锁、Prompt 完整度、弱调度器和 legacy 迁移经验。
5. 实际启动 ResearchAgent 并报告可点击地址、实际端口和启动命令。
6. 全部通过后同步 Task/README/spec 为完成，追加状态台账，创建本地提交；不 push、不合并 main。

## 实时监控命令

```bash
python3 -m scripts.sdd_tasks status --json
tail -f .sdd/runtime/runs/<run-id>/events.jsonl
git status --short --branch
git diff --check
curl -sS http://127.0.0.1:<port>/api/health
```

## 完成清单

- [ ] A1–A14 全部通过，证据可复现。
- [ ] Codex 与 CodeBuddy 均完成真实或明确标阻塞的 smoke；阻塞时不得完成。
- [ ] 016-requirement-review 与 016-tech-review 是实施前真实评审。
- [ ] 016-acceptance-review 有 tester 结论和 tech-lead 签字。
- [ ] Task 02–09 执行结果、状态和变更日志完整。
- [ ] spec/README/Task 状态镜像一致。
- [ ] legacy 未验证项没有被自动执行或伪造完成。
- [ ] SQLite/runtime/worktree 被 Git 忽略，run 摘要已脱敏。
- [ ] 复盘和状态 changelog 已落盘。
- [ ] ResearchAgent 全量测试、首页与 health 运行时验证通过。
- [ ] 本地提交范围正确，无 push/merge。

## 风险、停止条件与回滚

- 另一 IDE 无法真实验收：保持阻塞，不用模拟结果替代。
- tester 不通过或 tech-lead 未签字：spec 不得转完成。
- 服务因环境或依赖失败：记录具体阻塞和解决命令，不声称已部署。
- 回滚为停止启用新 Skill/CLI，继续旧 Markdown 手工流程；保留全部验收与失败记录。

## 产出物

- `docs/sdd/reviews/016-acceptance-review.md` 与开发主管签字。
- spec-016 复盘、部署证据、状态台账和本地 commit。
- A1–A14、双 IDE、rebuild、恢复和业务回归的真实证据。
- 本文件最终执行结果。

## 执行结果

> 待 Task 08 完成后填写。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师（自身） | 创建 Task 09，状态置待执行 |

