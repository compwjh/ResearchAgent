# spec-015 任务计划索引

> 关联 spec：[`docs/sdd/specs/015-security-paper-discovery.md`](../../specs/015-security-paper-discovery.md)
> 本目录保存 spec-015 的详细实施任务。spec 只维护任务标题、依赖、状态与跳转链接，具体实施约束以下列文件为准。

## 编号规则

- 任务 01 是 spec 本身，由架构师完成，不重复建文件。
- 从任务 02 起，一任务一文件，命名为 `task-NN-kebab-case.md`。
- 文件初始状态均为 `待执行`；只有需求/技术评审通过且用户明确确认 spec 后才可开始。
- 使用本地 Ollama junior-dev 时，代码分派每次最多 2 个代码文件、改动不超过 150 行；线上模型不受此数量上限约束，但仍须按风险拆分并验证。
- Spec013/014 与 Reranker 判断按用户授权 deferred；Task02 仅对内置会议召回与 OpenAlex 补全条件放行，Venue Search 保持阻塞。
- Task13–17 是 2026-09-05 新增流程范围；在新需求/技术复审、复用审计和用户再次确认前全部保持 `待执行`。弱调度 Agent不得根据旧 Task04/07 自行猜测补全。
- Task13–17 必须读取 Spec015 的“现有实现复用与替换边界”；优先复用已验证模块，禁止新建第二套下载、安全、导入、批任务、身份规范化或 embedding 实现。

## 任务清单

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-015 | [spec-015](../../specs/015-security-paper-discovery.md) | — | 完成 |
| 02 | 验证数据源与浏览器桥接（Go/No-Go） | [task-02](./task-02-validate-baseline-and-sources.md) | 01 | 条件放行（内置会议；Venue Search blocked） |
| 03 | 建立会议配置与论文召回 | [task-03](./task-03-conference-registry-and-retrieval.md) | 02（条件放行） | 已完成（内置会议与 OpenAlex 收窄范围） |
| 04 | 实现语义排序与 Reranker 集成 | [task-04](./task-04-semantic-ranking-and-rerank.md) | 03，且 spec-014 可用 | 待执行 |
| 05 | 实现安全下载、规范命名与知识库导入 | [task-05](./task-05-secure-download-and-kb-import.md) | 03 | 已完成（单篇下载与导入闭环） |
| 06 | 实现批量任务与登录续传 | [task-06](./task-06-batch-import-and-login-resume.md) | 05 | 实施中（离线安全复核通过；真实登录环境阻塞） |
| 07 | 新增论文检索 Tab 与完整交互 | [task-07](./task-07-paper-discovery-tab.md) | 03, 04, 05, 06 | 实施中（离线通过；A3/真实环境阻塞） |
| 08 | 执行测试、排序基准与安全回归 | [task-08](./task-08-tests-ranking-and-security.md) | 04, 05, 06, 07 | 实施中（离线安全/回归通过；排序质量与真实环境阻塞） |
| 09 | 评审、部署与复盘 | [task-09](./task-09-review-deploy-retro.md) | 08 | 实施中（离线回归与本地部署通过；外部验收阻塞） |
| 10 | 论文发现限界上下文目录重构 | [task-10](./task-10-paper-discovery-package-migration.md) | 03, 05, 06, 07, 08 | 待确认 |
| 11 | USENIX accepted papers 与 arXiv 兜底来源 | [task-11](./task-11-usenix-accepted-and-arxiv-fallback.md) | 03, 05, 08 | 已完成 |
| 12 | USENIX 双 Skill 与跨 IDE 使用协议 | [task-12](./task-12-usenix-paper-skill.md) | 11 | 已完成（下载版/目录版） |
| 13 | 固化全局目录协议与复用审计 | [task-13](./task-13-catalog-contract-and-reuse-audit.md) | 03, 05, 11, 12 | 待执行 |
| 14 | 实现 USENIX 增量目录同步 | [task-14](./task-14-usenix-incremental-catalog.md) | 13 | 待执行 |
| 15 | 实现 LangGraph、目录 RAG 与冻结结果 | [task-15](./task-15-langgraph-catalog-rag.md) | 14 | 待执行 |
| 16 | 实现来源进度与十条分页交互 | [task-16](./task-16-search-progress-and-pagination.md) | 15 | 待执行 |
| 17 | 执行复用审计、验收、部署与复盘 | [task-17](./task-17-review-acceptance-deploy-retro.md) | 13, 14, 15, 16 | 待执行 |

## 分支与回滚

- 仓库起点：`feature/spec-015-security-paper-discovery@c17c7f4`。
- 当前 Spec015 成果检查点 commit 尚未创建：用户要求先完整落盘文档并暂停。后续创建检查点时必须排除 `docs/sdd/specs/017-*`、`docs/sdd/plans/017/**` 和 `docs/sdd/reviews/017-*`，不得伪造 hash。
- 目标分支：`feature/spec-015-security-paper-discovery`。
- 不回滚、不 stash、不清理当前未提交修改；创建分支前保存工作树证据。
- 功能级回滚：`PAPER_DISCOVERY_ENABLED=false`；不删除已成功导入的知识库论文。
