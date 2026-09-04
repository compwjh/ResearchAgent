# 任务 08 — 集成 spec-013 观测能力

> 关联：[spec-014](../../specs/014-kb-reranker.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 05，且 spec-013 已形成可集成 commit；当前状态：`待执行`

## 一句话目标

在不丢失 spec-013 已完成观测能力的前提下集成两条分支，并把真实 Rerank 阶段加入知识库 trace。

## 前置条件

- spec-013 已完成自身评审或至少形成用户指定的稳定 commit。
- spec-014 的客户端和检索接入已完成针对性测试。
- 两个工作树均无未知后台 Agent 继续写文件；集成前检查活动 Agent 和 git 状态。

## 实施步骤

1. 记录 spec-013 最终 commit、测试结果和受影响文件。
2. 在 spec-014 独立 worktree 获取该 commit，通过 rebase 或明确 commit 集成；不得复制未提交工作树快照。
3. 对 `config.py`、KB retrieve/routes、requirements 与 deploy 脚本逐项解决语义冲突。
4. 保留 spec-013 的 embedding/retrieval/generation span；增加 rerank span。
5. span 仅记录：模型、候选数、输出数、延迟、used/degraded 和 fallback reason；不记录完整片段正文。
6. `LANGFUSE_ENABLED=false` 或 Langfuse 不可达时保持零侵入，不影响 rerank 与回答。
7. 分别验证 Langfuse 开/关、Reranker 开/关的四种组合。
8. 全仓扫描冲突标记，读回所有冲突文件，再运行针对性测试。

## 子代理分派

- `tech-lead` 先评审冲突清单和合并策略。
- 涉及代码的冲突修复按每批最多两个文件分派 `junior-dev`。
- 架构师负责 git 操作、最终语义核对和冲突标记扫描；不得用 `git reset --hard` 清理他人改动。

## 边界与明确不做

- spec-013 未完成时本任务等待，不猜测其最终接口。
- 不重写 spec-013 架构，不把 observability 变成 Reranker 的硬依赖。
- 不记录 query 和文档全文；遵守 spec-013 截断与采样配置。
- 禁止残留 `<<<<<<<`、`=======`、`>>>>>>>`，检查范围包含 `.gitignore`。

## 验收标准

- 四种启停组合均能完成 KB 问答。
- 启用观测时 trace 中阶段顺序和父子关系正确。
- rerank span 的候选数、耗时和降级原因与日志一致。
- 关闭观测时不发 Langfuse 请求；Langfuse 故障不影响业务。
- 冲突标记全仓 0 命中，针对性测试通过。

## 风险、回滚与产出

- 风险：spec-013 持续变化；只集成明确 commit，不跟踪脏工作树。
- 回滚：撤销集成 commit，spec-014 的独立功能仍保持可测。
- 产出：集成提交候选、rerank span、冲突清单和测试记录。
- 执行结果：待执行后填写。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-02 | 架构师(自身) | 创建任务计划，状态为待执行 |
