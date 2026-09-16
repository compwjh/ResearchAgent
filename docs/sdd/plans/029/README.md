# Spec 029 执行计划：全文获取与知识库联动

> 关联：[Spec 029](../../specs/029-research-fulltext-acquisition.md)
> 当前状态：已完成；运行时 generation reader、search_id 持久化桥接和公开 PDF 全文导入链均已验证。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-reuse-and-evidence-gate.md) | 证明既有下载、导入、KB 接缝可直接复用 | Spec027/028、确认、双评审 | 已完成（NO-GO，桥接缺口已冻结） |
| [03](./task-03-acquisition-approval-import.md) | 候选确认和批量导入接线 | 02 | 已完成 |
| [04](./task-04-fulltext-evidence-upgrade.md) | 全文 RAG 与证据等级升级 | 03 | 已完成 |
| [05](./task-05-acquisition-progress-ui.md) | 进度、登录等待与重试交互 | 03、04 | 已完成 |
| [06](./task-06-review-regression-deploy.md) | 最终验收、全量回归、部署和复盘 | 02–05 | 已完成 |

## 统一规则

- 禁止复制下载、安全、导入、文档解析、索引或 RAG 实现。
- 每个开发 Task 只跑定向测试；Task06 才运行全量回归。
- 产出写入 `docs/sdd/plans/029/artifacts/task-NN/`。

## 变更日志

- 2026-09-12：随 Spec029 创建。
- 2026-09-16：Task06 修复并验证默认 generation reader；新增服务端 catalog `search_id` 的持久化、任务详情投影和事件桥接。真实 selection→approval→batch→link→KB 链仍保持未完成。
- 2026-09-17：完成真实链路验证：任务 `3eee288b8e5a512dad3dad524d787c63` 绑定服务端快照 `fd6d1c7892fd49f29ea4682393530594`，公开 USENIX 论文导入批次 `67eec23f-d5e3-49ef-b380-acf8313fe8db` 完成，文档 `bfaf307d22a145b88fbf9e200df869b5` 的 v1 清单为 138 chunks，证据升级为 `fulltext`；全量回归 `2486 passed / 1 skipped / 5 warnings / 67 subtests`。
