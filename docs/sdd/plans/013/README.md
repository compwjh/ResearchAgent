# spec-013 任务计划索引

> 关联 spec：[`docs/sdd/specs/013-llm-observability-platform.md`](../../specs/013-llm-observability-platform.md)
> 本目录存放 spec-013 各任务的**思维链文档**：每个任务执行前先生成，说明步骤拆解、子代理分派、子代理返回后的处理，以及可实时查看进度的命令。

## 编号规则

- 编号格式 `task-NN-kebab-case.md`，`NN` 与 spec 编号 013 的任务序号对应，**从 01 开始**。
- **任务 01 = spec 本身的编写**，由架构师在主会话完成，因此不单独建思维链文档（避免文档自我引用）。
- 从任务 02 起，一任务一文档；spec 的「任务计划」表格中以相对链接关联到本目录。

## 任务清单

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-013（含回滚点） | 不单独建文档（即 spec 本体） | — | 完成 |
| 02 | 非 Docker 部署基础设施与 Langfuse v4（Go/No-Go） | [task-02](./task-02-deploy-langfuse.md) | 01 | 完成（Go） |
| 03 | 升级项目 Python 到 3.11 并重装依赖 | [task-03](./task-03-upgrade-python.md) | 01 | 完成 |
| 04 | 实现直连 Ollama 采集器与埋点封装层 | [task-04](./task-04-ollama-direct.md) | 03 | 完成（events_only 上报已验证） |
| 05 | 接入聊天与知识库 RAG 链路埋点 | [task-05](./task-05-instrument-chat-kb.md) | 04, 02 | 完成 |
| 06 | 统计路径 A：原生 Dashboard + numeric score | [task-06](./task-06-stats-native.md) | 05 | 完成 |
| 07 | 导入 Langfuse 源码并实现 Ollama 专用视图 | [task-07](./task-07-stats-custom-view.md) | 05 | 实施中（查询层、页面、分布、阶段与散点视图完成） |
| 08 | 评审验收与复盘 | [task-08](./task-08-review-retro.md) | 06, 07 | 待执行 |

## 2026-09-03 进度核对结论

- Task 02、03 的任务文档已记录完整执行结果。
- Task 04 的采集器、埋点封装和真实 Langfuse events_only 上报已完成；旧 `traces/observations` 视图为空不再作为失败条件。
- Task 05 已完成聊天/KB 接入、`kb.rerank` 事件和故障隔离测试；全量回归为 `322 passed`，仍待一次真实聊天与一次真实 KB 事件证据。
- Task 05 已完成聊天/KB 接入、`kb.rerank` 事件和故障隔离测试；全量回归为 `322 passed`，并已取得真实聊天/KB 事件证据。
- Task 06 已补齐固定样本生成器、20 条真实 fixture 和六项 Dashboard 配置；未来事件过滤验证通过。
- Task 07 已导入 Langfuse v4.27.0 到 `vendor/langfuse/`，完成 Ollama Insights tRPC router、events 字段声明、过滤、页面、阶段时间线、冷/热分布摘要和输入规模散点组件，并已接通输入规模字段；趋势图与完整前端测试仍在开发。
- Task 08 的三份 013 评审、产品步骤、验收签字、复盘、部署与稳定 commit 均未完成。

## 回滚

基线 commit `294138c`，完整回滚与分阶段回退方式见 spec 的「回滚点（Rollback Baseline）」章节。
