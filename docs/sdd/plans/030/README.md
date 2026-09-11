# Spec 030 执行计划：证据矩阵与深度研究报告

> 关联：[Spec 030](../../specs/030-research-evidence-reporting.md)
> 当前状态：待确认。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-evidence-report-contract.md) | 冻结 Claim/Evidence、引用与导出合同 | Spec027；全文场景依赖029 | 待执行 |
| [03](./task-03-evidence-matrix.md) | 结构化跨论文证据矩阵 | 02 | 待执行 |
| [04](./task-04-report-generation-export.md) | 只读版本化报告与 Markdown/JSON 导出 | 03 | 待执行 |
| [05](./task-05-report-workspace-ui.md) | 报告工作台和引用展开 | 04 | 待执行 |
| [06](./task-06-review-regression-deploy.md) | 最终验收、回归、部署和复盘 | 02–05 | 待执行 |

## 统一规则

- 无证据不补写论文事实；每条主要 Claim 必须可回查。
- 开发 Task 定向测试，Task06 唯一一次全量回归。
- 产出写入 `docs/sdd/plans/030/artifacts/task-NN/`。

## 变更日志

- 2026-09-12：随 Spec030 创建。
