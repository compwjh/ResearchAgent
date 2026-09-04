# spec-014 任务计划索引

> 关联 spec：[`docs/sdd/specs/014-kb-reranker.md`](../../specs/014-kb-reranker.md)
> 本目录保存 spec-014 的详细实施任务。spec 只维护任务标题、依赖、状态与跳转链接，具体实施约束以下列文件为准。

## 编号规则

- 任务 01 是 spec 本身，由架构师完成，不重复建文件。
- 从任务 02 起，一任务一文件，命名为 `task-NN-kebab-case.md`。
- 文件初始状态均为 `待执行`；只有 spec 经用户明确确认后才可开始。
- 涉及代码的分派必须遵守每次最多 2 个文件、改动不超过 150 行。

## 任务清单

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-014 | [spec-014](../../specs/014-kb-reranker.md) | — | 完成 |
| 02 | 验证 Reranker 运行时（Go/No-Go） | [task-02](./task-02-validate-reranker-runtime.md) | 01 | 完成（Go） |
| 03 | 管理 Reranker 服务生命周期 | [task-03](./task-03-reranker-service-lifecycle.md) | 02 | 完成 |
| 04 | 实现 Reranker 客户端 | [task-04](./task-04-reranker-client.md) | 02 | 完成 |
| 05 | 接入知识库检索链路 | [task-05](./task-05-integrate-retrieval-pipeline.md) | 04 | 完成 |
| 06 | 接入健康状态与前端展示 | [task-06](./task-06-reranker-health-status.md) | 03, 04 | 完成 |
| 07 | 执行测试与质量基准 | [task-07](./task-07-reranker-tests-benchmark.md) | 05, 06 | 完成 |
| 08 | 集成 spec-013 观测能力 | [task-08](./task-08-integrate-spec013-observability.md) | 05，且 spec-013 完成 | 部分完成（四组合逐请求关联仍待补齐） |
| 09 | 评审、部署与复盘 | [task-09](./task-09-review-deploy-retro.md) | 07, 08 | 阻塞（验收未通过，待恢复后问答与签字） |

## 分支与回滚

- 基线：`294138c`。
- 目标分支：`feature/spec-014-kb-reranker`。
- 使用独立 worktree，不修改 spec-013 Agent 的未提交工作。
- 功能级回滚：`RERANKER_ENABLED=false`；服务失败时运行时自动回退 RRF。
