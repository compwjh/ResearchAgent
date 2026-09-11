> 关联：[spec-025](../../specs/025-conversation-context-compaction.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03；当前状态：`已完成`

# Task 04 — 上下文用量端点与压缩端点

## 1. 状态与一句话目标

`已完成`。交付 `GET /api/conversations/{id}/context-usage` 与 `POST /api/conversations/{id}/compactions`，并在装配后按 80% 阈值自动入队压缩（内部路径，非公开端点）。

## 2. 背景与前置条件

- Spec025「端点 / 接口」与「边界」两节为唯一依据。
- 装配唯一函数 `compose_chat_prompt`（`conversation_service.py:238-267`）为纯函数，可 dry-run。
- 会话路由在 `backend/app/api/routes_conversations.py`；job 状态端点模式参考 `:489-504`（`memory_analysis_jobs`）。
- `context_pressure` 观测事件已存在于 `routes_conversations.py:270-275`，本次沿用，不改语义。
- Task03 已提供段与 job 的仓储能力。

## 3. 数据、配置与接口

```json
// GET /api/conversations/{id}/context-usage
{ "used_tokens": 5200, "budget_tokens": 8000, "ratio": 0.65,
  "segment_count": 2, "compaction_status": "idle" }
```

```json
// POST /api/conversations/{id}/compactions
{ "job_id": "...", "status": "queued", "trigger": "manual" }
```

- 失败码：404（会话不存在或不属于当前用户）、409（已有非终态 job）、500（入队失败）。
- `ratio = used_tokens / budget_tokens`；`budget_tokens ≤ 0` 时按 1.0 处理并记录观测，禁止除零崩溃。
- dry-run 只计算历史段与记忆/摘要段，**不触发 RAG 检索、不调用模型**。

## 4. 实施步骤与文件边界

1. 新增用量端点：dry-run 复用 `compose_chat_prompt` → `estimate_tokens` → 组装响应（含最新 job 终态）。
2. 新增手动压缩端点：校验归属 → 判重（非终态 job 返回 409）→ 入队 `trigger='manual'` → 返回 job。
3. 在装配后接入自动触发：`ratio ≥ CHAT_COMPACT_TRIGGER_RATIO` 时入队 `trigger='auto'`，**本次请求照常返回**。
4. 自动入队失败只记观测，不得影响本次回答。

可观察结果：手动触发返回 job；重复触发返回 409；自动触发不延长本次响应；`context-usage` 不触发任何模型调用。

## 5. 子代理分派

- `backend-dev`（hy3，64k）：只改路由与装配衔接层，不重写装配函数；回传后架构师读回校验 dry-run 与真实装配同源。
- `backend-tester`（hy3，32k）：只跑本 Task 相关 pytest。

## 6. 边界与明确不做

- 不把 dry-run 结果写库，不产生副作用。
- 不在端点内触发压缩计算（压缩一律走 worker）。
- 不做逐条勾选、程度选择、预览接口。
- 不改 SSE 事件协议，不为占比新增事件（占比由前端在两处主动拉取）。
- 不改 `frontend/**`。

## 7. 验收、风险与回滚

- 验收：0.79 不触发 / 0.80 触发；409 去重；404 越权；`budget=0` 不崩溃；dry-run 与真实装配在历史段与记忆/摘要段口径上一致；自动入队失败不影响回答（断言响应正常）。
- **注意（复审提示）**：`used_tokens` 不含 RAG advisory、SystemRule 与平台安全约束，非项目长会话可能长期达不到 6400；验证 0.79/0.80 时**必须构造能触及阈值的会话**（项目会话或足量长历史），否则自动触发路径实际未被覆盖。
- 风险：dry-run 与真实装配漂移——必须共用同一函数与同一配置，并以单测锁定。
- 回滚：摘除两个端点与自动触发钩子，不影响 Task03 产物。

## 8. 产出物、执行结果与变更日志

- `routes_conversations.py`：`compute_context_usage`（dry-run，不触发 RAG/模型）、`GET /api/conversations/{id}/context-usage`、`POST /api/conversations/{id}/compactions`（404/409/500）、装配后 80% 自动触发（try/except 不阻塞）。
- 测试：`python -m pytest tests/test_spec025_context_usage_api.py -q` → 10 passed（退出码 0）。
- 运行时：手动压缩 job `queued → done`，`segment_count` 0→1；不存在会话 404。
- 注意：阈值用例需构造可触及阈值的会话（调低预算或足量长历史），因 `used_tokens` 不含 RAG/SystemRule。
