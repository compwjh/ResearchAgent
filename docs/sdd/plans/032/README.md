# Spec 032 执行计划：数据源与安全会议扩展

> 关联：[Spec 032](../../specs/032-research-source-expansion.md)
> 当前状态：待确认。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-source-adapter-contract.md) | Adapter、字段 provenance 和增量缓存合同 | Spec027/015、确认、双评审 | 待执行 |
| [03](./task-03-openalex-crossref-adapters.md) | 聚合书目来源接入 | 02 | 待执行 |
| [04](./task-04-security-conference-adapters.md) | IEEE S&P、ACM CCS、NDSS 官方目录 | 02 | 待执行 |
| [05](./task-05-source-merge-progress-ui.md) | 来源合并、Research Task 进度和界面 | 03、04 | 待执行 |
| [06](./task-06-review-regression-deploy.md) | 最终验收、全量回归、部署和复盘 | 02–05 | 待执行 |

## 统一规则

- 官方来源字段优先，聚合来源只补缺；搜索阶段不下载 PDF。
- 新来源必须有固定样本后才允许启用。
- 开发 Task 定向测试，Task06 唯一一次全量回归。
- 产出写入 `docs/sdd/plans/032/artifacts/task-NN/`。

## 变更日志

- 2026-09-12：随 Spec032 创建。
