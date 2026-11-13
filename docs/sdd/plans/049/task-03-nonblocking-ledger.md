# 任务 03：NB1–NB10 分类决策台账落盘

> 关联：[spec-049](../../specs/049-known-nonblocking-followup-cleanup.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`（`runs/decision-ledger.md` 已落盘）

## 1. 状态与一句话目标

把 spec「只读勘察结论」表中 NB1–NB10 每一项写成有结论、有事实依据的落盘台账，消除「已知非阻塞项」仅被口头登记、无处置结论的状态。

## 2. 背景与前置条件

- 用户已明确确认 spec-049；C 组定案 `保持现状、零改动`。
- 输入：`docs/sdd/reviews/048-acceptance-review.md` §6（9 项）、`docs/sdd/plans/048/runs/task-04/final-verification.md` §6、`merge-decision.md` §③⑤、`deploy-verification.json:44-50`；spec 表格中的勘察事实（`文件:行` / 命令）已核实。
- 只读，不修改 spec-048 的任何历史文档正文。

## 3. 数据、配置与接口

- 数据模型 / 端点：**不适用**。
- 台账文件：`docs/sdd/plans/049/runs/decision-ledger.md`（新建，纯文档）。
- C 组零改动：本任务只落盘结论，不实现任何平台 / 阈值 / 环境 / 工作区改动。

## 4. 实施步骤与文件边界

| 序 | 动作 | 可观察结果 |
|---|---|---|
| 1 | 新建 `runs/decision-ledger.md`，逐条抄录 NB1–NB10 编号与登记来源 | 10 行齐全，无遗漏 |
| 2 | 每行填「结论 / 事实依据 / 是否产生改动」 | A 类「已闭环（证据路径）」；B 类「本次实现（任务 02）」；C 类「保持现状、零改动」 |
| 3 | C 类逐条写明结论 `保持现状` | 不得写成「已修复 / 已配置」，不得虚报门禁全绿 |
| 4 | 附「确认前后状态对照」：`.github/` 仍不存在、`.coveragerc` 无 `fail_under`、`ruff` 错误数不变、`git status --short` 未跟踪清单不变（除本轮文档） | 只读命令输出落盘 |
| 5 | 结论回填 spec「只读勘察结论」表与变更日志 | spec 与台账口径一致 |

## 5. 子代理分派

- 纯文档任务，由主会话代行（改动不含任何代码文件）；三处留痕「台账头部 / spec 变更日志 / 状态台账收口条」。
- 独立复核分派 `Task(architect)`，产出 `docs/sdd/reviews/049-tech-review.md` 的技术评审部分。

## 6. 边界与明确不做

- **不改** `.github/**`、`.coveragerc`、远端 branch protection / required checks / PR approval、CSS、未跟踪文件、`LANGFUSE_*` 配置。
- **不批量 `ruff --fix`**、不臆测修复 404、不启动 Langfuse。
- 不改 Spec-048 的状态、不改历史 FAIL 记录、不重开 Gate。
- 不把「保持现状」写成「已解决」，不虚报 CI / 覆盖率 / 分支保护门禁达标。
- 不改松任何断言。

## 7. 验收、风险与回滚

| 验收点 | 判定 |
|---|---|
| NB1–NB10 每行有结论 + 依据 | 人工核对 + 静态 grep 断言 |
| C 类结论均为 `保持现状` | 台账逐条核对 |
| 零副作用：确认前后的只读状态对照一致 | 命令输出落盘 |

**风险**：把「保持现状」写成「修复」会造成虚报。
**回滚**：台账为纯文档，删除本轮新建文件即可，不影响业务代码。

## 8. 产出物、执行结果与变更日志

- 产出物：`docs/sdd/plans/049/runs/decision-ledger.md`。
- 执行结果：`runs/decision-ledger.md`（NB1–NB10 逐项结论 + 确认前后状态对照 + C 类零改动结论）；确认前后 `.github` ABSENT、无 `fail_under`、ruff 185、marker `47 34`、211 行、tabs 12 条、按钮基线 56、CSS 未改、未跟踪清单未清理。阻塞项 0。
- 变更日志：2026-11-13 主会话代行落盘；`tester` 收尾追加 B007 修复事实（ruff 保持 185）。
