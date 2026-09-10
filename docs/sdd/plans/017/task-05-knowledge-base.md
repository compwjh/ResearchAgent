# 任务 05：迁移知识库限界上下文

> 关联：[Spec017](../../specs/017-backend-bounded-context-modularization.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 03；当前状态：`已完成`

> 2026-09-08 收口：知识库实现集中于 `knowledge_base/`，提供受控 PaperImport 适配器并保留既有索引与补偿语义。

## 目标

将 `services/kb/` 整体迁移为 `knowledge_base/`，拆除过大的包级 facade，并公开受控的应用入口与生命周期接口。

## 约束

- 保留现有 KB 数据目录、Qdrant collection、索引任务行为、reranker 降级和 API 契约。
- 论文发现只能通过知识库导入 application 入口访问 KB，不得依赖其 store/index/tasks 内部文件。
- 所有调用改为直接、明确的新模块 import；不保留 `services.kb`。

## 验收

- 上传、列举、重建、删除、检索、问答、启动恢复和 reranker 回归通过。
- 不存在包级 wildcard/facade 作为跨层依赖通道。
