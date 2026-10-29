# Spec 030 执行计划：证据矩阵与深度研究报告

> 关联：[Spec 030](../../specs/030-research-evidence-reporting.md)
> 当前状态：实施中。2026-10-29用户确认、独立需求/技术GO，Task07合同门通过，Task08分步实施；历史Task02–06保持已完成。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-evidence-report-contract.md) | 冻结 Claim/Evidence、引用与导出合同 | Spec027；全文场景依赖029 | 已完成 |
| [03](./task-03-evidence-matrix.md) | 结构化跨论文证据矩阵 | 02 | 已完成 |
| [04](./task-04-report-generation-export.md) | 只读版本化报告与 Markdown/JSON 导出 | 03 | 已完成 |
| [05](./task-05-report-workspace-ui.md) | 报告工作台和引用展开 | 04 | 已完成 |
| [06](./task-06-review-regression-deploy.md) | 最终验收、回归、部署和复盘 | 02–05 | 已完成 |

| 07 | 内容质量合同与运行路径审计 | [Task07](./task-07-quality-contract.md) | 本修订确认/独立评审 | 已完成（独立GO） |
| 08 | 后端实质报告生成与质量门禁 | [Task08](./task-08-substantive-report-generation.md) | 07 | 实施中 |
| 09 | 前端报告质量与恢复反馈 | [Task09](./task-09-report-quality-feedback.md) | 08接口冻结 | 待执行 |
| 10 | 内容质量最终验收与交付 | [Task10](./task-10-quality-acceptance.md) | 08、09 | 待执行 |

## 统一规则

- 无证据不补写论文事实；每条主要 Claim 必须可回查。
- 开发 Task 定向测试，历史Task06的全量结果不覆盖当前增量；本轮Task10最终候选运行全量回归。
- 产出写入 `docs/sdd/plans/030/artifacts/task-NN/`。

## 变更日志

- 2026-09-12：随 Spec030 创建。
- 2026-09-17：用户确认 Spec030，进入 Task02 实施；后续 Task 依赖前序交接报告。
- 2026-09-17：Task03 完成 Claim/Evidence/ComparisonDimension/Cell 持久化与矩阵接口，定向测试 3 passed；开始 Task04。
- 2026-09-17：Task04 完成不可覆盖报告版本与 JSON/Markdown/HTML 导出，定向测试 4 passed；开始 Task05。
- 2026-09-17：Task05 完成矩阵/报告/引用工作台与下载交互，前端定向测试 35 passed；开始 Task06。
- 2026-09-17：Task02 以 `evidence-report-v1` 合同完成并判定 `GO_FOR_TASK03`；开始 Task03。
- 2026-09-17：Task06 完成固定矩阵/manifest/三格式/XSS/键盘/窄屏审计、唯一全量回归和临时部署 smoke；全量 `2495 passed, 5 failed, 67 subtests passed`，未知报告路由真实返回 500（应 404），因此保留 Task06/Spec030 为实施中并记录 P1 阻塞，详见 [`Task06 审计`](./artifacts/task-06/acceptance-audit.md)。
- 2026-09-17：修复报告错误出口、矩阵未就绪 409 映射并补齐旧样式版本兼容标记；全量回归 `2504 passed, 1 skipped, 67 subtests passed`，部署 smoke 通过，Task06 与 Spec030 已完成。

2026-10-29：新增Task07–10及[质量合同](2026-10-29-report-quality-contract.md)，用户确认，进入独立需求/技术门禁；尚未修改代码。
