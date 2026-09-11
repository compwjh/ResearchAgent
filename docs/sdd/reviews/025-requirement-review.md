# Spec 025 需求评审

> 评审方式：**代行，非独立评审**（需求要点经由两轮 Grilling 与用户逐条确认，此处按实现结果回查覆盖情况）。

## 结论：通过

## 需求点与实现对照

| 需求（Grilling 确认） | 实现 | 状态 |
|---|---|---|
| 立项理由改为输入 token 预算 / 首 token 延迟 | 目标与背景已改写，指标为 P95 输入估算 token、P95 首 token 延迟 | 已覆盖 |
| 装配预算 8000 估算 token，达 80%（6400）触发 | `CHAT_TOTAL_TOKEN_BUDGET=8000`、`CHAT_COMPACT_TRIGGER_RATIO=0.8` | 已覆盖 |
| 后台异步压缩，本次不阻塞、下一条消息生效 | worker 入队后返回，装配在下一轮读段 | 已覆盖 |
| 输入框显示上下文占预算比例 | composer 占比条 + 百分比文案 + `role="progressbar"` | 已覆盖 |
| 用户可主动点击压缩（一档，无二次确认/无勾选） | `#context-compact-button`，disabled + try/finally | 已覆盖 |
| 占比只在加载会话后、每轮消息完成后刷新，无常驻轮询 | 两处刷新点；手动压缩后仅有上限跟随刷新 | 已覆盖 |
| `messages` append-only，压缩只在读时装配 | 迁移只读建新表；装配层消费段 | 已覆盖 |
| 规则化分段摘要（非 LLM） | `build_rule_summary` 三段式 + 消息 id 指针 | 已覆盖 |
| 统一 `chars/1.6` 计量，收敛旧 `*4` | `token_budget.py` 唯一实现；`repository.py` 改为 `chars_for_tokens` | 已覆盖 |
| 跨项目隔离、SystemRule/平台约束不压缩 | 段带 owner/conversation/project；SystemRule 与平台约束走既有 system-role 通道，不进历史段 | 已覆盖 |
| 不修订 Spec024、不与其耦合 | 未触碰 024 相关代码 | 已覆盖 |

## 明确不做复核

未实现 LLM 摘要、未引入 tokenizer、未删改 `messages`、未改 SSE 协议、未做跨会话摘要召回、未做"新建会话"引导、未改模型或 `num_ctx` —— 与 Spec「明确不做」逐条一致。

## 遗留

- 真实对话触发自动压缩的路径受本机 Ollama 环境限制未端到端验证（见验收评审）。
