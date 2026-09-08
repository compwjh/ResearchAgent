# 任务 04：迁移论文发现限界上下文

> 关联：[Spec017](../../specs/017-backend-bounded-context-modularization.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 05（KB application contract 就绪）；当前状态：`已完成`

> 2026-09-08 收口：论文导入编排改为注入 `PaperImportPort`，不再直连知识库内部存储/索引实现。
> 本任务**不得早于** Task05 提供 KB application facade；必须改为调用 Task03 定义的 port，禁止继续 import KB 的 store/index/tasks。

## 目标

将 Spec015 的领域模型、SQLite 仓储、数据源、下载、安全、浏览器、解析器、批量导入和 application 用例一次性迁移到 `paper_discovery/`。

## 约束

- 不改变数据库 schema、状态机、错误码、下载安全策略、浏览器隔离或 API 行为。
- 项目内 import、测试和 API 适配层同步改为新路径；不保留旧 `services/` 或 `domain/` 转发文件。
- 与知识库的唯一协作通过明确导入 application 入口，而非读取 KB 内部仓储。

## 验收

- `paper_discovery/` 是该能力唯一实现根目录。
- 论文发现、导入批次、浏览器、下载和安全测试通过。
- 旧路径零 import、零实现文件。
