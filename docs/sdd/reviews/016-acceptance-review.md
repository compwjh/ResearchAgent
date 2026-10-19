# Spec 016 验收矩阵（草稿）

- 日期：2026-10-19
- 评审者：final_architect；角色：architect；模型：gpt-6-luna xhigh
- 候选：`281e93373aa328b47d289662919f991646d12773`
- 总结：**BLOCKED — 实施中。** Task06 已完成本范围静态复审和工具域 QA；Task07 云端证据已记录，但 CodeBuddy 本地验收未做；Task08 迁移与 Task09 独立整体验收仍待完成。此矩阵不代表 ResearchAgent 业务全量回归通过。

## A1–A14

| 验收点 | 状态 | 当前证据与未满足项 |
|---|---|---|
| A1 文档自足 | PENDING | 尚无独立 IDE 只读 spec、README、Task 与 run summary 后复述进度、下一 Task、角色和完成条件的验收记录。 |
| A2 Prompt 完整 | PASS（云端 CLI/Skill 范围） | 四份通用 Skill 与 CodeBuddy adapter 经官方 validator 校验，root 独立读回；真实 Codex/Luna fixture 展示 CLI prompt 与 complete 流程。[Task07 记录](../plans/016/task-07-cross-ide-skills.md#L154)、[live demo](../plans/016/artifacts/live-luna-demo.md)。 |
| A3 单任务选择 | PASS（CLI 范围） | live fixture 中多个 Task 并存时，真实 `next --claim` 只领取 Task09；候选 281e933 的 379 项工具域 suite 通过。[live demo](../plans/016/artifacts/live-luna-demo.md)、[Task06 closure QA](../plans/016/artifacts/task06-final-tool-tests.md#L59)。 |
| A4 防重复领取 | PASS（隔离 fixture） | 两个独立 subprocess 同时 claim 同一 Task，结果为一个 `claimed`、一个 `rejected`；该证据是隔离 preflight，完整 Task02/双 IDE gate 仍未完成。[runtime preflight](../plans/016/artifacts/runtime-preflight.md#L37)。 |
| A5 门禁有效 | PENDING | Task08 的 31 项 legacy audit 已完成分类，但 summaries、Task metadata/mirrors、rebuild/status 与不可领取门禁尚未完成验收；迁移决策记录在 [Task06 review](./016-task06-review.md#L45)。 |
| A6 跨 IDE | DEFERRED — CodeBuddy 本地 smoke | Codex → Luna → CLI 的真实协议示例已完成；CodeBuddy Task 调用及双端行为矩阵明确为 `not_run`，不能据 Skill 校验替代实际 CodeBuddy 行为。[Task07 记录](../plans/016/task-07-cross-ide-skills.md#L160)。 |
| A7 结果闭环 | PASS（云端 fixture） | 真实 CLI complete 写入规范 run summary；result/metrics 返回一致的 run、hash、outcome、变更文件和未知指标，Task 状态与 rebuild 后查询一致。[live demo](../plans/016/artifacts/live-luna-demo.md)。 |
| A8 越界保护 | PASS（工具域 fixture） | journal/index QA 验证 staged outsider 保留、lock/image 冲突拒绝、index replay 及候选路径校验；379 项工具域 suite 全绿。[index reconciliation](../plans/016/artifacts/task06-index-reconciliation-tests.md)、[journal validation](../plans/016/artifacts/task06-journal-validation.md#L26)、[closure QA](../plans/016/artifacts/task06-final-tool-tests.md#L59)。 |
| A9 中断恢复 | PASS（工具域 fixture） | 真实 child 进程 `os._exit(86)` 后执行 CLI recover、领取 immediate-source child、complete 和 rebuild；另有 journal/index 故障窗口恢复验证。[result/metrics QA](../plans/016/artifacts/task06-result-metrics-tests.md)、[journal validation](../plans/016/artifacts/task06-journal-validation.md)。 |
| A10 可重建 | PASS（隔离 live fixture） | 删除隔离 SQLite DB 后由 CLI rebuild 恢复 Task 与 run；status/result/metrics 与删除前一致，后续 `next --claim` 返回 `NO_TASK`。[live demo](../plans/016/artifacts/live-luna-demo.md#L21)。 |
| A11 指标导出 | PASS（CLI/工具域范围） | 真实 metrics 查询返回已知文件变更数，并将未知 token/tool 计数保留为 null；metrics QA 覆盖固定 schema、过滤、排序和无写入行为。[live demo](../plans/016/artifacts/live-luna-demo.md#L18)、[result/metrics QA](../plans/016/artifacts/task06-result-metrics-tests.md)。 |
| A12 Git 边界 | PASS（本地 fixture/工具域范围） | journal QA 覆盖 expected-old ref CAS、staged outsider 保留、index 原子安装和恢复；live fixture 通过本地 CLI complete/rebuild 验证结果。无证据表明该流程 push 或合并；此项不扩大为真实项目仓库发布验收。[journal validation](../plans/016/artifacts/task06-journal-validation.md#L80)、[live demo](../plans/016/artifacts/live-luna-demo.md)。 |
| A13 Legacy 对账 | PENDING | 31 项 audit 为 22 completed、7 partial、1 pending、1 migration_unverified；独立 legacy summaries 与规范 Task 状态镜像迁移还未落盘并通过逐 Spec doctor/rebuild/status。[legacy audit](../plans/016/artifacts/legacy-task-audit.md)。 |
| A14 ResearchAgent 回归 | PENDING | 本矩阵只引用 `scripts/sdd_tasks` 工具域 suite，不包含 ResearchAgent 业务测试或运行时行为的全量回归证据。 |

## QA 证据边界

候选 `281e933` 的 Task06 closure QA 记录：30 个目标测试通过；`unittest discover -s tests/sdd_tasks -t .` 共 379 项通过（142.850 秒，exit 0）；Ruff 与 compileall 均通过。QA artifact 保留了更早的失败和修复重试链，最终 closure run 的命令、日志路径、HEAD/status 与 metadata 均已记录。[Task06 final tool tests](../plans/016/artifacts/task06-final-tool-tests.md#L59)。

## 签字边界

Task06 的独立架构复审为 PASS，详见 [Task06 review](./016-task06-review.md)。A1、A5、A6、A13、A14 仍未完成；A6 明确留待用户授权的本地 CodeBuddy 验收。Task09 的独立验收、Task08 legacy migration 及 ResearchAgent 业务回归未签收，Spec 016 整体状态保持 `实施中`。不得将上述局部 PASS 汇总成 Spec 整体 PASS。
