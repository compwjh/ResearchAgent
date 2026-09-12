# Spec 025 执行计划：会话上下文压缩与 Token 预算管理

> 关联：[Spec 025](../../specs/025-conversation-context-compaction.md)
> 当前状态：已完成。需求/技术/后端/前端/验收五份评审均已落盘并通过。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-token-budget-config.md) | 统一 token 计量与预算配置，收敛现有 `*4` 口径 | Spec 确认 | 已完成 |
| [03](./task-03-segments-and-worker.md) | 分段摘要、装配消费改造与异步压缩 worker | 02 | 已完成 |
| [04](./task-04-context-usage-api.md) | 上下文用量端点与压缩端点 | 03 | 已完成 |
| [05](./task-05-frontend-context-meter.md) | 前端占比指示与手动压缩按钮 | 04 | 已完成 |
| [06](./task-06-review-regression-deploy.md) | 双端评审、全量回归、运行时验收、部署与复盘 | 05 | 已完成 |

## 统一执行规则

- Task 开发阶段只运行与本 Task 相关的定向测试；只有 Task06 执行一次全量回归。
- 下游角色只读取 Spec025、当前 Task、其中列出的代码路径及上一角色固定报告，不扫描整个项目。
- 线上子 Agent 正常运行时等待其主动返回，不频繁读取日志；仅在超时、报错或明确阻塞时诊断。
- `messages` 表 append-only 是硬约束：任何 Task 都不得 UPDATE/DELETE 既有行，压缩只发生在读时装配层。
- 任何范围变化，尤其是引入 tokenizer 依赖、LLM 摘要、跨会话摘要召回或改动 Spec024，必须停止并回到 Spec。
- 实现、定向测试和评审证据统一写入 `docs/sdd/plans/025/artifacts/task-NN/`。

## 里程碑

- M1 / Task02：`estimate_tokens` 全链路唯一，预算常量可配置，两套口径已消除。✔
- M2 / Task03：分段摘要可生成、迁移可重复执行、异步 worker 不阻塞对话、装配层消费段。✔
- M3 / Task04：占比端点与手动压缩端点可用，job 去重与失败降级成立。✔
- M4 / Task05：输入框可见占比、可一键压缩、版本号与契约测试同步（`?v=33→34`）。✔
- M5 / Task06：全量回归、运行时 smoke、部署与复盘完成。✔

## 执行结果摘要

- 全量回归：`python -m pytest tests/ -q` → 1345 passed、1 skipped、47 subtests；唯一失败 `test_import_compensation.py::test_import_without_temp_dir_uses_attempt_private_root_and_cleans_only_it` 已用 `git stash` 在干净树复现，属存量问题。
- 新增测试 52 项：后端 40（9+7+14+10）+ 前端契约 12。
- 部署：http://127.0.0.1:8000（`deploy/start.sh -d`）。
- 遗留：本机 Ollama 无可用模型，"长会话达 80% 自动压缩"的真实端到端路径待 Ollama 可用后补验。

## 变更日志

- 2026-09-11：根据两轮 Grilling 共同理解创建 Task02–06；前端占比指示与手动压缩纳入本计划。
- 2026-09-12：用户确认 Spec 后实施；Task02–Task06 全部完成，Spec 转 `已完成`；技术评审复审通过，后端/前端评审 GO，验收通过；复盘见 `docs/sdd/retro/2026-09-12-spec-025-context-compaction.md`。
