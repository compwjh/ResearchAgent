# Spec 029 执行计划：全文获取与知识库联动

> 关联：[Spec 029](../../specs/029-research-fulltext-acquisition.md)
> 当前状态：待确认。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-reuse-and-evidence-gate.md) | 证明既有下载、导入、KB 接缝可直接复用 | Spec027/028、确认、双评审 | 待执行 |
| [03](./task-03-acquisition-approval-import.md) | 候选确认和批量导入接线 | 02 | 待执行 |
| [04](./task-04-fulltext-evidence-upgrade.md) | 全文 RAG 与证据等级升级 | 03 | 待执行 |
| [05](./task-05-acquisition-progress-ui.md) | 进度、登录等待与重试交互 | 03、04 | 待执行 |
| [06](./task-06-review-regression-deploy.md) | 最终验收、全量回归、部署和复盘 | 02–05 | 待执行 |

## 统一规则

- 禁止复制下载、安全、导入、文档解析、索引或 RAG 实现。
- 每个开发 Task 只跑定向测试；Task06 才运行全量回归。
- 产出写入 `docs/sdd/plans/029/artifacts/task-NN/`。

## 变更日志

- 2026-09-12：随 Spec029 创建。
