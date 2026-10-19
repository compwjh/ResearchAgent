# spec-015 任务计划索引

> 关联 spec：[`docs/sdd/specs/015-security-paper-discovery.md`](../../specs/015-security-paper-discovery.md)
> 本目录保存 spec-015 的详细实施任务。spec 只维护任务标题、依赖、状态与跳转链接，具体实施约束以下列文件为准。

## 编号规则

- 任务 01 是 spec 本身，由架构师完成，不重复建文件。
- 从任务 02 起，一任务一文件，命名为 `task-NN-kebab-case.md`。
- 文件初始状态均为 `待执行`；只有需求/技术评审通过且用户明确确认 spec 后才可开始。
- 使用本地 Ollama junior-dev 时，代码分派每次最多 2 个代码文件、改动不超过 150 行；线上模型不受此数量上限约束，但仍须按风险拆分并验证。
- Spec013/014 与 Reranker 判断按用户授权 deferred；Task02 仅对内置会议召回与 OpenAlex 补全条件放行，Venue Search 保持阻塞。
- Task13–17 是 2026-09-05 新增流程范围；Task13/14 已按实际落盘实现回填，Task15–17 在用户明确要求“接下来开发”后进入实施。弱调度 Agent不得根据旧 Task04/07 自行猜测补全。
- Task13–17 必须读取 Spec015 的“现有实现复用与替换边界”；优先复用已验证模块，禁止新建第二套下载、安全、导入、批任务、身份规范化或 embedding 实现。

## 任务清单

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-015 | [spec-015](../../specs/015-security-paper-discovery.md) | — | 完成 |
| 02 | 验证数据源与浏览器桥接（Go/No-Go） | [task-02](./task-02-validate-baseline-and-sources.md) | 01 | 阻塞 |
| 03 | 建立会议配置与论文召回 | [task-03](./task-03-conference-registry-and-retrieval.md) | 02（条件放行） | 完成 |
| 04 | 实现语义排序与 Reranker 集成 | [task-04](./task-04-semantic-ranking-and-rerank.md) | 03, Spec014 Task09 | 待执行 |
| 05 | 实现安全下载、规范命名与知识库导入 | [task-05](./task-05-secure-download-and-kb-import.md) | 03 | 完成 |
| 06 | 实现批量任务与登录续传 | [task-06](./task-06-batch-import-and-login-resume.md) | 05 | 阻塞 |
| 07 | 新增论文检索 Tab 与完整交互 | [task-07](./task-07-paper-discovery-tab.md) | 03, 04, 05, 06 | 阻塞 |
| 08 | 执行测试、排序基准与安全回归 | [task-08](./task-08-tests-ranking-and-security.md) | 04, 05, 06, 07 | 阻塞 |
| 09 | 评审、部署与复盘 | [task-09](./task-09-review-deploy-retro.md) | 08 | 阻塞 |
| 10 | 论文发现限界上下文目录重构 | [task-10](./task-10-paper-discovery-package-migration.md) | 03, 05, 06, 07, 08 | 阻塞 |
| 11 | USENIX accepted papers 与 arXiv 兜底来源 | [task-11](./task-11-usenix-accepted-and-arxiv-fallback.md) | 03, 05, 08 | 完成 |
| 12 | USENIX 双 Skill 与跨 IDE 使用协议 | [task-12](./task-12-usenix-paper-skill.md) | 11 | 完成 |
| 13 | 固化全局目录协议与复用审计 | [task-13](./task-13-catalog-contract-and-reuse-audit.md) | 03, 05, 11, 12 | 完成 |
| 14 | 实现 USENIX 增量目录同步 | [task-14](./task-14-usenix-incremental-catalog.md) | 13 | 完成 |
| 15 | 实现 LangGraph、目录 RAG 与冻结结果 | [task-15](./task-15-langgraph-catalog-rag.md) | 14 | 完成 |
| 16 | 实现来源进度与十条分页交互 | [task-16](./task-16-search-progress-and-pagination.md) | 15 | 完成 |
| 17 | 执行复用审计、验收、部署与复盘 | [task-17](./task-17-review-acceptance-deploy-retro.md) | 13, 14, 15, 16 | 阻塞 |
| 18 | 补齐数据源与浏览器桥接真实证据 | [18](./task-18-legacy-remainder.md) | — | 阻塞 |
| 19 | 完成隔离浏览器登录与续传闭环 | [19](./task-19-legacy-remainder.md) | 05 | 阻塞 |
| 20 | 补齐论文检索 Tab 完整交互与真实 GUI 验收 | [20](./task-20-legacy-remainder.md) | 03, 04, 05, 19 | 阻塞 |
| 21 | 完成排序质量集与全范围安全回归验收 | [21](./task-21-legacy-remainder.md) | 04, 05, 19, 20 | 阻塞 |
| 22 | 完成 Spec015 全范围验收、部署与复盘 | [22](./task-22-legacy-remainder.md) | 04, 18, 19, 20, 21 | 阻塞 |
| 23 | 补齐 USENIX-only 收口签字与复盘 | [23](./task-23-legacy-remainder.md) | 13, 14, 15, 16 | 阻塞 |

## 分支与回滚

- 仓库起点：`feature/spec-015-security-paper-discovery@c17c7f4`。
- 当前 Spec015 成果检查点 commit 尚未创建：用户要求先完整落盘文档并暂停。后续创建检查点时必须排除 `docs/sdd/specs/017-*`、`docs/sdd/plans/017/**` 和 `docs/sdd/reviews/017-*`，不得伪造 hash。
- 目标分支：`feature/spec-015-security-paper-discovery`。
- 不回滚、不 stash、不清理当前未提交修改；创建分支前保存工作树证据。
- 功能级回滚：`PAPER_DISCOVERY_ENABLED=false`；不删除已成功导入的知识库论文。
