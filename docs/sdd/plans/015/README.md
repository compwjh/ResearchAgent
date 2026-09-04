# spec-015 任务计划索引

> 关联 spec：[`docs/sdd/specs/015-security-paper-discovery.md`](../../specs/015-security-paper-discovery.md)  
> 本目录保存 spec-015 的详细实施任务。spec 只维护任务标题、依赖、状态与跳转链接，具体实施约束以下列文件为准。

## 编号规则

- 任务 01 是 spec 本身，由架构师完成，不重复建文件。
- 从任务 02 起，一任务一文件，命名为 `task-NN-kebab-case.md`。
- 文件初始状态均为 `待执行`；只有需求/技术评审通过且用户明确确认 spec 后才可开始。
- 涉及代码的分派必须遵守每次最多 2 个文件、改动不超过 150 行。
- spec-013、spec-014 未形成稳定基线前，任务 02 不得判定 Go，任务 03–09 不得开始。

## 任务清单

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-015 | [spec-015](../../specs/015-security-paper-discovery.md) | — | 完成 |
| 02 | 验证稳定基线、数据源与浏览器桥接（Go/No-Go） | [task-02](./task-02-validate-baseline-and-sources.md) | 01，且 spec-013/014 完成 | 待执行 |
| 03 | 建立会议配置与论文召回 | [task-03](./task-03-conference-registry-and-retrieval.md) | 02 | 待执行 |
| 04 | 实现语义排序与 Reranker 集成 | [task-04](./task-04-semantic-ranking-and-rerank.md) | 03，且 spec-014 可用 | 待执行 |
| 05 | 实现安全下载、规范命名与知识库导入 | [task-05](./task-05-secure-download-and-kb-import.md) | 03 | 待执行 |
| 06 | 实现批量任务与登录续传 | [task-06](./task-06-batch-import-and-login-resume.md) | 05 | 待执行 |
| 07 | 新增论文检索 Tab 与完整交互 | [task-07](./task-07-paper-discovery-tab.md) | 03, 04, 05, 06 | 待执行 |
| 08 | 执行测试、排序基准与安全回归 | [task-08](./task-08-tests-ranking-and-security.md) | 04, 05, 06, 07 | 待执行 |
| 09 | 评审、部署与复盘 | [task-09](./task-09-review-deploy-retro.md) | 08 | 待执行 |

## 分支与回滚

- 基线：待 spec-013、spec-014 完成并形成稳定提交后在任务 02 回填。
- 目标分支：`feature/spec-015-security-paper-discovery`。
- 不回滚、不 stash、不清理当前未提交修改；创建分支前保存工作树证据。
- 功能级回滚：`PAPER_DISCOVERY_ENABLED=false`；不删除已成功导入的知识库论文。
