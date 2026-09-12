# Task 03：后端能力接口 source/refresh 与 stale 缓存

> 关联：[spec-026](../../specs/026-reasoning-effort-feedback-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`已完成`

## 一句话目标

把 `GET /api/chat/reasoning-options` 改造为：探测失败返回 200 + `source=stale|unknown`（不再 503），并支持 `refresh=1` 强制重探。

## 背景与前置条件

- 已确认 spec 026，重点 §端点/接口、§对 Spec 024 的修订声明、边界 B1、B2、B4。
- 现状代码：`backend/app/api/routes_conversations.py`
  - `get_reasoning_options`（约 188-199 行）：探测失败 → 503 `MODEL_CAPABILITIES_UNAVAILABLE`。
  - `resolve_reasoning_effort` 的异常映射（约 176-186 行）：`RuntimeError` → 503。
- 前置：Task 02 已完成，`get_reasoning_capabilities` 已不再抛异常。
- 参考：`docs/sdd/specs/024-visible-reasoning-controls.md` §能力接口请求与错误体（被本 spec 修订的那一条）。

## 数据、配置与接口

请求：`GET /api/chat/reasoning-options?model=<urlencoded>&refresh=0|1`

| source | HTTP | supported_efforts | default_effort | cached_at |
|---|---|---|---|---|
| `ollama_probe` | 200 | 实测集合 | 支持的最高档 | 本次探测时间 |
| `cache` | 200 | 缓存集合 | 支持的最高档 | 缓存写入时间 |
| `stale` | 200 | **旧**缓存集合 | **旧**集合的最高档 | **旧**缓存时间 |
| `unknown` | 200 | `[]` | `null` | 本次尝试时间 |

- 未知/空白模型仍按 024 返回 404 `MODEL_NOT_FOUND`。
- 本接口**不再返回 503**。503 `MODEL_CAPABILITIES_UNAVAILABLE` 的错误码定义保留（兼容发消息路径），但本端点不使用。

## 实施步骤与文件边界

目标文件：**`backend/app/api/routes_conversations.py`** + 对应测试。

1. 路由增加 `refresh: int = 0` 查询参数，透传给 `get_reasoning_capabilities(model, refresh=bool(refresh))`。
2. 移除/改造现有的「能力不可用即 503」分支：改为按 `caps.source` 直接序列化返回。
3. 序列化时 `unknown` → `supported_efforts: []`、`default_effort: null`；`stale` → 原样输出旧集合与旧 `cached_at`。
4. 确认 `resolve_reasoning_effort` 在收到 `unknown` 能力对象时的行为：**必须**对任何非 `off` 请求返回 409 `REASONING_EFFORT_UNSUPPORTED`（不得放行也不得 503）；如现有实现会因 `default_effort=None` 崩溃，需在此 Task 内修正并记录。
5. 完成后可观察结果：`curl -s 'http://127.0.0.1:8000/api/chat/reasoning-options?model=<m>'` 在 Ollama 停止时返回 200 且 `source` 为 `stale` 或 `unknown`。

## 子代理分派

| 角色 | 模型 | 最小上下文 | 文件范围 | 回读校验 |
|---|---|---|---|---|
| backend-dev | `Deepseek-V4.1-Flash` | spec 026 §端点/接口 + `routes_conversations.py:167-223` | `backend/app/api/routes_conversations.py` + 测试 | 主会话读回 diff 与 curl 实测输出 |

## 边界与明确不做

- 不做：不改 `POST /conversations/messages` 与 `PATCH /conversations/{id}/reasoning` 的现有语义。
- 不做：不给 `PATCH /reasoning` 补 `_validate_model`（登记为后续项，不在本 spec）。
- 不做：不改统一错误体结构 `{"error":{"code","message","retryable"}}`。
- 不得在 `unknown` 时把 `supported_efforts` 写成 `["off"]`。

## 验收、风险与回滚

- 验收：Ollama 停止时 curl 该接口 → HTTP 200、`source ∈ {stale, unknown}`；无 503。
- 验收：`refresh=1` 连续两次调用，第二次 `source` 为 `ollama_probe`（非 `cache`）。
- 验收：以 `unknown` 能力发送非 off 档位 → 409 `REASONING_EFFORT_UNSUPPORTED`，不调用模型、不建空会话。
- 风险：前端旧代码假定 `default_effort` 一定是字符串 → 由 Task 05 处理，本 Task 只需保证后端不 500。
- 回滚：`git checkout -- backend/app/api/routes_conversations.py`。

## 产出物、执行结果与变更日志

待执行后填写：curl 真实输出、`pytest` 结果、边界用例清单。
