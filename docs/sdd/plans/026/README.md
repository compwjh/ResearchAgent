# Spec 026 执行计划：推理档位反馈与首屏响应修复

> 关联：[spec-026](../../specs/026-reasoning-effort-feedback-fixes.md)

## 一句话目标

修掉「提问后没有对话卡片」「不支持的档位也能选、选了才报 409」「所有错误都叫连接失败」三个缺陷。

## 两条根因

1. **无乐观渲染** —— assistant 卡片绑在 SSE `meta` 事件上（`frontend/app.js:1825`），发送后聊天区长时间空白。
2. **能力探测脆弱 + 前端不消费能力** —— 串行 5 探针全败即 503（`backend/app/platform/ollama.py:69-95`）；`default_effort` 取到最低档（`:97`）；前端探测失败时编造 `['off']`（`frontend/app.js:386-389`）且从不校正选中值（`:359-366`）。

## 任务索引

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec 026 | [spec 本体](../../specs/026-reasoning-effort-feedback-fixes.md) | — | 完成 |
| 02 | 后端：能力失败语义与 default_effort 修正 | [task-02](./task-02-backend-capability-semantics.md) | 01、Spec 确认 | 待执行 |
| 03 | 后端：能力接口 source/refresh 与 stale 缓存 | [task-03](./task-03-backend-options-endpoint.md) | 02 | 待执行 |
| 04 | 前端：乐观建卡、失败终态与错误文案分流 | [task-04](./task-04-frontend-optimistic-card.md) | 03 | 待执行 |
| 05 | 前端：档位选择器三态与选中值校正 | [task-05](./task-05-frontend-selector-states.md) | 03 | 待执行 |
| 06 | 评审、全量回归、部署与复盘 | [task-06](./task-06-review-regression-deploy.md) | 04、05 | 待执行 |

## 边界提醒

- 本 spec **不改**能力探测性能（并发/预热/超时/持久化），另开 spec 027。
- 不做 DDL、不改 SSE 协议、不做 UI redesign。
- 024 的「不静默降低用户显式选择的档位」红线保留；仅在切换模型 / 载入历史会话时允许**带提示的校准**。
- Ollama 不可用时 Task 06 置 `阻塞`，不得以 mock 结果声称 smoke 通过。

## 只读最小上下文

- `backend/app/platform/ollama.py`（能力探测与缓存）
- `backend/app/api/routes_conversations.py`（能力接口与错误映射，约 167-223 行）
- `frontend/app.js`（299-410 档位选择器；1798-1947 发送与 SSE 消费）
- `docs/sdd/specs/024-visible-reasoning-controls.md`（被修订的既有合同，只读 §能力探测与模型映射）
