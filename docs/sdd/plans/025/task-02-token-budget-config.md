> 关联：[spec-025](../../specs/025-conversation-context-compaction.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01（Spec 确认）；当前状态：`已完成`

# Task 02 — 统一 token 计量与预算配置

## 1. 状态与一句话目标

`已完成`。交付全链路唯一的 `estimate_tokens()` 与一套命名预算配置常量，并收敛仓库现有的 `*4` 换算口径。

## 2. 背景与前置条件

- Spec025 已确认；当前装配全部按字符截断（`backend/app/chat/application/conversation_service.py:238-267`）。
- 现有换算散落且不一致：`backend/app/memory/repository.py:1607` 使用 `token_budget*4`（1 token≈4 字符）。
- 配置写法沿用 `backend/app/platform/config.py`（模块级常量 + `os.getenv`，辅助函数 `_env_bool` `:19-29`、`_env_positive_number` `:32-49`）。
- 真实 token 只从 `backend/app/platform/ollama_direct.py:164` 回读做观测，本 Task 不改动观测链路。

## 3. 数据、配置与接口

| 名称 | 默认 | 语义 |
|---|---|---|
| `estimate_tokens(text)` | — | `chars / 1.6` 向上取整；空串返回 0 |
| `CHAT_TOTAL_TOKEN_BUDGET` | 8000 | 单次调用硬上限 |
| `CHAT_COMPACT_TRIGGER_RATIO` | 0.8 | 达到即触发自动异步压缩 |
| `CHAT_RECENT_RAW_MESSAGES` | 10 | 最近原文保留条数 |
| `CHAT_RAG_BUDGET_CHARS` | 6000 | 沿用现状 |
| `CHAT_SUMMARY_BUDGET_CHARS` | 1500 | 沿用现状 |
| `CHAT_PROJECT_INSTR_CHARS` | 5000 | 沿用现状 |

- `repository.py:1607` 的 `*4` 改为复用 `estimate_tokens()`；全仓库不得并存两套换算。
- 非法配置（≤0）在读取时 fail-fast。

## 4. 实施步骤与文件边界

1. 在装配域新增唯一的 `estimate_tokens()`（单文件，不复制实现）。
2. 在 `backend/app/platform/config.py` 增加上表常量，按 spec 分节注释。
3. 改 `repository.py:1607` 复用同一函数，保持其外部行为可被单测断言。
4. 让 `compose_chat_prompt` 的四个字符参数改为读取新常量（默认值不变，保持向后兼容）。

可观察结果：`grep -rn "\*4\|token_budget" backend/app/memory/repository.py` 不再出现独立换算；新增单测通过。

## 5. 子代理分派

- `backend-dev`（hy3，64k）：单次只改上述文件；回传后由架构师读回校验 diff 与 `node --check` 等价的 Python 语法/静态检查。

## 6. 边界与明确不做

- 不引入 tiktoken 或任何 tokenizer 依赖。
- 不改变现有默认截断行为（数值等价），只统一来源。
- 不改动 Ollama 客户端与观测链路。
- 不触碰 `frontend/**`。

## 7. 验收、风险与回滚

- 验收：`estimate_tokens` 单测（空串、纯中文、中英混排、超长）；`CHAT_TOTAL_TOKEN_BUDGET=0` 时 fail-fast；装配默认输出与改动前逐字符一致。
- 风险：改 `*4` 会收紧记忆召回预算——属预期修正，需在报告记录影响面。
- 回滚：revert 本 Task 提交，不影响其它 Task。

## 8. 产出物、执行结果与变更日志

- 新增 `backend/app/chat/application/token_budget.py`（`estimate_tokens` / `chars_for_tokens`，CHARS_PER_TOKEN=1.6）。
- `backend/app/platform/config.py` 新增 6 个 `CHAT_*` 预算常量（`_env_positive_number` 保证正数）。
- `conversation_service.compose_chat_prompt` 默认参数改为读取配置常量，输出逐字符等价。
- `repository.list_recall_context` 的 `token_budget*4` 收敛为 `chars_for_tokens(token_budget)`（该分支当前无调用方，属死代码收敛）。
- 测试：`python -m pytest tests/test_spec025_token_budget.py -q` → 9 passed（退出码 0）。
