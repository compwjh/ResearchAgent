# Spec 014 本地 Rerank 重排 — 复盘（2026-09-04）

> 关联：[spec-014](../specs/014-kb-reranker.md) ｜ [验收报告](../reviews/014-acceptance-review.md) ｜ [Task 09](../plans/014/task-09-review-deploy-retro.md)

## 交付摘要

本地 Reranker（llama.cpp `/v1/rerank` + Qwen3-Reranker-0.6B Q8_0）完成接入：候选池重排、稳定映射、异常降级、健康状态、接入 spec-013 观测。冻结 10 题 MRR@5 由 RRF `0.225` 提升至 `0.495`；20 候选热请求中位数 `0.367s`。全量回归 `351 passed`。

收口过程中发现并修复了两个回答模型协议缺陷（`8c1c3ae`、`6daa498`），使四种 Langfuse/Reranker 启停组合的真实 KB ask 全部完整收口到 `done`。

## 关键经验

### 1. 模型能力开关的默认值应当是「不下发」，而不是「开启」

`think` / `reasoning` 是 Ollama 的模型能力开关。把它设为默认 `True` 会同时伤害两类模型：

- 不支持 thinking 的模型（`deepseek-coder-v2:16b`）→ HTTP 400 `does not support thinking`
- 思考模型（`qwen3.5:9b`）→ 被强制开启思维链，响应被拖长到无法收口

教训：**「开启某个能力」的开关，默认值应当是 `None`（不下发，交由模型自身默认行为），而不是 `True`。** 只有明确知道要关闭时（受控耗时采样、KB 问答避免思维链淹没正文）才显式下发 `False`。

### 2. 给函数加参数时，默认值必须选「保持原行为」的那个值

`8c1c3ae` 的本意是「KB 问答关思维链、普通聊天行为不变」，但把 `create_chat_model` 的默认值从「不下发（None）」改成了 `True`。diff 只有几行，却改变了 4 个调用方的行为：`article_agent` 意图分类、`download_paper_skill`、`kb/retrieve.py`、langchain 聊天链路。

教训：加参数前后必须**枚举所有调用方**；默认值优先选"改动前等价"的值，而不是语义上"看起来合理"的值。本次正是因为默认值语义缺乏断言，回归才一直没被发现。

### 3. 复现要下沉到协议层，而不是停留在现象层

前两轮分别把 `qwen3.5:9b` 无 `done` 归因为「模型慢/超时」、把 `deepseek` 400 归因为「模型不兼容」——两个独立现象、两个独立猜测。直接对 `/api/chat` 用 4 组 `think` 取值（`true`/`false`/`null`/不传）压测后，两个现象被**同一个根因**解释清楚。

| 请求体 `think` | HTTP | 说明 |
|---|---|---|
| `true` | 400 | `deepseek-coder-v2:16b does not support thinking` |
| `false` | 200 | 正常 |
| `null` | 200 | 正常（改动前默认） |
| 不传 | 200 | 正常 |

教训：遇到「模型行为异常」，先用最小 curl 把变量隔离到请求体字段级，再动代码。

### 4. 回归测试要锁「默认值语义」

`8c1c3ae` 已经补了「传 `reasoning=False` 时显式下发」的测试，但仍然漏掉了默认值回归——因为没有任何测试断言默认值本身。本次补上：

- `test_factory_does_not_force_thinking_by_default`：断言 `create_chat_model("m").reasoning is None`
- `test_factory_forwards_explicit_reasoning`：断言显式传值时原样转发

教训：**新增可选参数时，至少补两条测试——一条锁默认值，一条锁显式传值。**

## 流程偏差（如实记录）

- **验收评审与 tech-lead 签字为主会话代行**：本项目已有 `junior-dev`、`tester` 子代理在长流程任务中中途失效的复盘记录（2026-09-01），本次为保证收口进度未再分派子代理。签字栏已如实标注代行及理由。
- **`6daa498` 回归修复由主会话（架构师）直接完成**，未按 Task 09「发现代码缺陷时退回 `junior-dev` 窄任务修复」执行。原因是该修复仅为 1 行默认值调整 + 2 条契约测试，且当时卡在验收签字环节；已在 Task 09 变更日志中标注实际角色。

## 遗留问题（不在 spec-014 范围，建议单开缺陷单）

`run_chat` 的默认参数仍是 `think: bool = True`（spec-013 引入的既有行为）。因此：

- 默认 `OLLAMA_ROUTE=langchain`：本次已修复（langchain 路径默认不再下发 `think`）。
- 若显式设置 `OLLAMA_ROUTE=direct`：`chat_direct_stream` 会把 `think=True` 原样发给 Ollama，对不支持 thinking 的模型仍会返回 HTTP 400。

建议后续单独处理该默认值（改为 `None` 语义），不在 spec-014 收口时扩大改动范围。

## 其他

- Reranker 长片段需 `--ubatch-size 1024`，否则超长输入会失败。
- 停服降级（RRF 回退）与恢复闭环均有真实 trace 证据（`kb.rerank status=degraded/degraded_reason=connection`）。
- 本次提交严格不含 `.env`、模型文件、日志、PID，也未包含他人正在编辑的 Spec 015 文档。
