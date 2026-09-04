# 任务 08 — 集成 spec-013 观测能力

> 关联：[spec-014](../../specs/014-kb-reranker.md) ｜ 索引：[README](./README.md)
> 依赖：任务 05，且 spec-013 已形成可集成 commit；当前状态：`部分完成（待补四组合关联证据）`

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

- `tech-lead` 先评审冲突清单和合并策略，使用 `gpt-5.6-luna` 高推理。
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
- 执行结果：代码已随 `main@e980cea` 集成；全量测试 `346 passed`、专项测试 `100 passed`。Langfuse `events_full` 已出现 `kb.rerank`/`kb.retrieval` 真实事件，成功事件含 `enabled=true,status=ok,input_count=20,output_count=1`，停服事件含 `degraded_reason=connection,status=degraded`，父子 trace 可关联。四种启停组合已有健康/降级证据，但仍缺每种组合的逐请求关联记录，保持部分完成。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-02 | 架构师(自身) | 创建任务计划，状态为待执行 |
| 2026-09-02 | 用户 | 指定剩余任务统一使用 Luna 高推理；本任务等待 spec-013 明确 commit |

## 补充执行结果（2026-09-04）

代码已随 `main@e980cea` 集成，且后续真实部署修复了 Reranker 启动参数的 `--ubatch-size 1024`。当前四组合证据对账如下：

| 组合 | 已落盘证据 | 状态 |
|---|---|---|
| Langfuse off × Reranker off | FastAPI 首页/health/KB health HTTP 200；KB health 明确 `reason=disabled` | 健康分支通过；未形成 KB ask 与 span 关联（按设计不应有 span） |
| Langfuse off × Reranker on | Reranker probe、11435 health、KB health HTTP 200；真实 KB ask HTTP 200，SSE 含 `meta/stage/citations/token/debug/done` | 通过 |
| Langfuse on × Reranker off | 停服后真实 KB ask 已开始返回 `meta/stage/citations`；Langfuse 记录 `kb.rerank status=degraded, degraded_reason=connection` 与同 trace `kb.retrieval status=ok` | 降级通过；完整 SSE done/恢复后再问关联未全部记录 |
| Langfuse on × Reranker on | 真实 KB ask HTTP 200、SSE 含 `meta/stage/citations`；Langfuse `kb.rerank status=ok, enabled=true, input_count=20, output_count=1`，同 trace 有 `kb.retrieval` 父阶段 | 成功路径通过；逐请求恢复证据仍待补齐 |

补充回归：全量测试 `346 passed`，Spec 014 专项测试 `100 passed`；Langfuse Web、FastAPI、KB health 与 Reranker health 均已取得 HTTP 200。当前状态仍为“部分完成（待补四组合关联证据）”：四组合中只有 off/on 有完整 SSE done 记录，on/off 为停服流已开始，on/on 为成功流的阶段事件，尚无四组合每一项都具备独立完整 `KB ask -> trace/span -> done` 对账。

后续补测修正组合 1 记录：在 Langfuse off × Reranker off 下，`qwen3.5:9b` 真实 ask 在 120/330 秒内持续 thinking、无 `done`；`deepseek-coder-v2:16b` 在 `citations` 后进入 error，Ollama `/api/chat` 返回 HTTP 400。故组合 1 仅 health/禁用分支通过，真实 KB ask 被回答模型耗时/协议错误阻塞；不伪造 Langfuse span 或完整问答结果。
