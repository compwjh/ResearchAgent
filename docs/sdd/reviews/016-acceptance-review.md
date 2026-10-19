# Spec 016 云端验收矩阵与架构复核签字

- 日期：2026-10-19
- 评审者：final_architect；角色：architect；模型：gpt-6-luna xhigh
- 候选：Python `37bb056ed5f61c357cbdfba78eced21076154013`；legacy 文档迁移提交 `4b14130`
- 总结：**云端范围 PASS；完整 Spec 未通过，保持实施中。** A1–A5、A7–A14 的云端证据已复核；A6 真实 CodeBuddy 场景仍待本地执行，Task09 云端主管签字已另行完成；完整跨 IDE 签字待本地证据。此结论只签云端证据，不代表跨 IDE/完整 Spec 验收通过。

## A1–A14

| 验收点 | 状态 | 当前证据与未满足项 |
|---|---|---|
| A1 文档自足 | PASS（云端文档自足范围） | fresh-context 终审确认可恢复 Task01–09 云端进度、下一项本地 CodeBuddy/A6、tester 角色与九项本地验收场景；不声称已执行 A6 或另一 IDE。[fresh-context validation](../plans/016/artifacts/fresh-context-validation.md)。 |
| A2 Prompt 完整 | PASS（云端 CLI/Skill 范围） | 四份通用 Skill 与 CodeBuddy adapter 经官方 validator 校验，root 独立读回；真实 Codex/Luna fixture 展示 CLI prompt 与 complete 流程。[Task07 记录](../plans/016/task-07-cross-ide-skills.md#L154)、[live demo](../plans/016/artifacts/live-luna-demo.md)。 |
| A3 单任务选择 | PASS（CLI 范围） | live fixture 中多个 Task 并存时，真实 `next --claim` 只领取 Task09；候选 37bb056 的 382 项工具域 suite 通过。[live demo](../plans/016/artifacts/live-luna-demo.md)、[Task06 final QA](../plans/016/artifacts/task06-final-tool-tests.md)。 |
| A4 防重复领取 | PASS（隔离 fixture） | 两个独立 subprocess 同时 claim 同一 Task，结果为一个 `claimed`、一个 `rejected`；该证据是隔离 preflight，完整 Task02/双 IDE gate 仍未完成。[runtime preflight](../plans/016/artifacts/runtime-preflight.md#L37)。 |
| A5 门禁有效 | PASS（迁移验证范围） | 三个 Spec 的 doctor/rebuild/status 和 38 个 canonical Task 镜像校验通过；Spec015 Task04 因未满足的 `spec-015.legacy-resume-authorized` gate 留在 waiting 且不 eligible，Task10 保持 blocked/unverified，未尝试领取。[legacy migration validation](../plans/016/artifacts/legacy-migration-validation.md)。 |
| A6 跨 IDE | DEFERRED — CodeBuddy 本地 smoke | Codex → Luna → CLI 的真实协议示例已完成；CodeBuddy Task 调用及双端行为矩阵明确为 `not_run`，不能据 Skill 校验替代实际 CodeBuddy 行为。[Task07 记录](../plans/016/task-07-cross-ide-skills.md#L160)。 |
| A7 结果闭环 | PASS（云端 fixture） | 真实 CLI complete 写入规范 run summary；result/metrics 返回一致的 run、hash、outcome、变更文件和未知指标，Task 状态与 rebuild 后查询一致。[live demo](../plans/016/artifacts/live-luna-demo.md)。 |
| A8 越界保护 | PASS（工具域 fixture） | journal/index QA 验证 staged outsider 保留、lock/image 冲突拒绝、index replay 及候选路径校验；382 项工具域 suite 全绿。[index reconciliation](../plans/016/artifacts/task06-index-reconciliation-tests.md)、[journal validation](../plans/016/artifacts/task06-journal-validation.md#L26)、[final QA](../plans/016/artifacts/task06-final-tool-tests.md)。 |
| A9 中断恢复 | PASS（工具域 fixture） | 真实 child 进程 `os._exit(86)` 后执行 CLI recover、领取 immediate-source child、complete 和 rebuild；另有 journal/index 故障窗口恢复验证。[result/metrics QA](../plans/016/artifacts/task06-result-metrics-tests.md)、[journal validation](../plans/016/artifacts/task06-journal-validation.md)。 |
| A10 可重建 | PASS（隔离 live fixture） | 删除隔离 SQLite DB 后由 CLI rebuild 恢复 Task 与 run；status/result/metrics 与删除前一致，后续 `next --claim` 返回 `NO_TASK`。[live demo](../plans/016/artifacts/live-luna-demo.md#L21)。 |
| A11 指标导出 | PASS（CLI/工具域范围） | 真实 metrics 查询返回已知文件变更数，并将未知 token/tool 计数保留为 null；metrics QA 覆盖固定 schema、过滤、排序和无写入行为。[live demo](../plans/016/artifacts/live-luna-demo.md#L18)、[result/metrics QA](../plans/016/artifacts/task06-result-metrics-tests.md)。 |
| A12 Git 边界 | PASS（本地 fixture/工具域范围） | journal QA 覆盖 expected-old ref CAS、staged outsider 保留、index 原子安装和恢复；live fixture 通过本地 CLI complete/rebuild 验证结果。无证据表明该流程 push 或合并；此项不扩大为真实项目仓库发布验收。[journal validation](../plans/016/artifacts/task06-journal-validation.md#L80)、[live demo](../plans/016/artifacts/live-luna-demo.md)。 |
| A13 Legacy 对账 | PASS（迁移验证范围） | 31 项保留 Task 正文 31/31 byte-identical；38 个 canonical Task 的 parse/mirror 验证通过；未知指标仍为 null，rebuild `runs=0`、doctor `summary_count=0`，无历史 Run 被伪造。[legacy audit](../plans/016/artifacts/legacy-task-audit.md)、[legacy migration validation](../plans/016/artifacts/legacy-migration-validation.md)。 |
| A14 ResearchAgent 回归 | PASS（云端回归范围） | 全仓 pytest：3275 passed、3 skipped、546 subtests passed，exit 0；本地服务 HTTP smoke 1 passed，首页、health、models 与 12 个静态资源均 HTTP 200，memory schema v8。3 项 skip 是两个需 `RUN_E2E=1`/后端的浏览器 E2E，以及一个 Ollama 实时推理用例；本结论不声称浏览器 E2E 或真实模型推理通过。[final business/runtime](../plans/016/artifacts/final-business-runtime.md)。 |

## QA 证据边界

候选 `37bb056` 的 Task06 final QA 记录：`unittest discover -s tests/sdd_tasks -t .` 共 382 项通过（153.440 秒，exit 0）；Ruff 与 compileall 均通过。完整测试从 HEAD `37bb056` 开始、在 `83fadbe` 结束，期间 `scripts/sdd_tasks` 与 `tests/sdd_tasks` 无变动；QA artifact 保留早期失败及修复重试链，并记录最终命令、日志路径、HEAD/status 与 metadata。[Task06 final tool tests](../plans/016/artifacts/task06-final-tool-tests.md)。

A14 的全仓业务测试和本地服务 smoke 记录于 [final business/runtime](../plans/016/artifacts/final-business-runtime.md)。服务的 `/api/models` 返回空列表，因此没有执行或模拟模型推理；浏览器 E2E 因环境门槛跳过。

## 架构复核与签字边界

**架构师云端范围签字：PASS。** 评审者：`final_architect`；角色：architect；模型：gpt-6-luna xhigh；候选：Python `37bb056`，文档迁移 `4b14130`。本签字覆盖本矩阵所列云端证据。Task06 status/claim 原 P1 已由 `4388c9b` / `f620887` 修复；Task06 QA 为 382 项通过，Ruff/compileall 通过；对 `37bb056` mirrors 迁移豁免实现作了只读复核，未发现残留 P1。评审范围内无未关闭 P0/P1；证据见 [Task06 review](./016-task06-review.md)、[Task06 final QA](../plans/016/artifacts/task06-final-tool-tests.md) 与 [fresh-context validation](../plans/016/artifacts/fresh-context-validation.md)。

### Gate 状态

- **云端证据齐备：** A1–A5、A7–A14；包含 Task06 QA、Task08 legacy gate/mirror/rebuild、ResearchAgent 全仓回归与本地 HTTP smoke。
- **本地剩余：** A6 九项真实 CodeBuddy 场景目前均为 `not_run`。待本地执行和证据复核后，再由 tech-lead 独立签署 Task09；本签字不冒充 tech-lead 签字。

**最终状态：** 本文签署的是云端范围 PASS。A5/A13、A14 与 A1 的范围边界以各自矩阵行说明为准；A6 与完整 Spec 验收未通过，Spec 016 整体保持 `实施中`。

云端独立主管复核另见 [cloud closure signoff](./016-cloud-closure-signoff.md)，结论 PASS；该签字限已授权云端范围，不解除 A6 或完整 Spec 的本地门禁。
