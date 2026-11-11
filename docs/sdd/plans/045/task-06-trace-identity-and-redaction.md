> 关联：[spec-045](../../specs/045-evaluation-observability-hardening.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`已完成`（2026-11-08 接手机器只读核实）

# Task 06 — 链路标识与脱敏统一

## 状态与一句话目标

`已完成`。一次请求用一个 ID 串起三套观测记录；凭据不再明文进监控；
模型思考过程在瀑布图里可见。

对应 spec 11 项中的 **07（能力补齐）**、**09（缺陷修复）**。

## 背景与前置条件

- 必读：[spec-045](../../specs/045-evaluation-observability-hardening.md) F8/F12/F13；
  [045-observability-module-survey.md](../../notes/045-observability-module-survey.md) 第 1/6 节。
- **F8**：观测三套并存（Langfuse SDK / 自建 SQLite 事件 / 路由观测），
  无全局 HTTP middleware 埋点，各记各的 ID。
- **F12 三套脱敏口径冲突**：
  Langfuse 明文全量 prompt（`spans.py:338-341,401-411`，
  `spec-041:7,39,97-101` 用户裁决「无需隐私设计」）；
  `raw_events` 明文完整用户消息且 payload 无上限
  （`routes_conversations.py:1248`、`repository.py:1158`）；
  `research_events` 严格白名单 + 值级脱敏（`research_store.py:130-161`，
  URL/Bearer/token 替换为 `[REDACTED]`、字符串截 1000），
  `processing_projector.py:36-50` 二次白名单，
  `routing_observation.py:27-38,484-505` 有 key 级 + 值级凭据正则。
- **F13**：`spec-013:101` 要求 `thinking` 与 content 分开上报，
  但 `spans.py:137-138` 只记 `reasoning_present/reasoning_chars`，
  generation output 只有 `result.content`（`:374`），思考正文未上报。
- 现有护栏：`tests/platform/test_retry_observability.py`、
  `tests/frontend/test_retry_observability_frontend.py` 锁定白名单形状、脱敏、前端文案；
  `tests/system/test_observability.py:371,430` 锁定 `thinking_chars`。
- 前置：task 02 已完成。

## 数据、配置与接口

- 统一 `request_id` / `trace_id`：在请求入口生成并写入 `ContextVar`，
  Langfuse trace metadata、自建 `raw_events`/`research_events` payload、
  路由决策记录共用同一值。不新增全局 middleware 也可实现（沿用手工埋点），
  但必须覆盖 chat / article / kb / research 四条链路。
- 脱敏：抽出一处值级过滤（key/token/URL userinfo），三套写入路径共用；
  `raw_events.payload` 增加大小上限（超过则截断并标记）。
- thinking：generation 增加独立字段承载思考正文（与 `content` 分离），
  保留 `reasoning_present/reasoning_chars` 既有字段以免破坏测试。
- **不修改** `research_events` 既有白名单契约（`safe_payload` 形状被契约测试锁定）；
  只在其上层补统一 ID 与共用脱敏函数。

## 实施步骤与文件边界

1. 红测：① prompt 内含 `sk-*` / Bearer / URL userinfo 时三处落盘均不含明文；
   ② 超长 `raw_events.payload` 被截断并标记；
   ③ 同一次请求在三套记录里 ID 一致；④ 思考正文可在 Langfuse 读到。
2. 新增统一脱敏模块与请求 ID 上下文；在各写入点接入。
3. `spans.py` 增加 thinking 字段；`routes_conversations.py` 的 `append_raw_event`
   加 payload 上限。
4. 回归三套观测相关测试；真实 trace 中核对 ID 串联（Q10 证据③）。

**文件边界**：`backend/app/platform/observability/{spans,trace}.py` + 新增脱敏/ID 模块、
`backend/app/api/routes_{chat,article,kb,conversations}.py`、
`backend/app/memory/repository.py`、
`backend/app/research/infrastructure/research_store.py` 的写入辅助、
`tests/platform/**`、`tests/observability/**`、`tests/frontend/test_retry_observability_frontend.py`。

## 子代理分派

- 含 `.py` / `.js` 改动 → 分别 `Task(backend-dev)` 与 `Task(frontend-dev)`
  （若前端需展示 ID），主会话只编排（`AGENTS.md:127,128`）。
- 隐私红测由 `Task(backend-tester)` 独立执行，避免开发自证。
- 最小上下文：本 task 文档 + F12 三处路径行号 + 「不改 research_events 白名单契约」边界。

## 边界与明确不做

- **不推翻 spec-041 的「input/output 全量可见」用户裁决**：本任务只做**值级凭据过滤**，
  不做整段 prompt 脱敏或清空（现有 `test_prompt_input.py:57-147` 锁定 input 原文不清空）。
- **不改** `research_events` 的 `safe_payload` 白名单形状与 SSE 事件协议。
- 不新增全局 middleware（沿用手工埋点），不改 `LANGFUSE_ENABLED` 默认值。
- 不做在线实时评测、不做人工标注、不做分数口径统一（P2）。
- 不修改根 `CONTEXT.md`（Q4）。

## 验收、风险与回滚

| 验收点 | 证据 |
|---|---|
| ID 串联 | 一次真实请求在 Langfuse / raw_events / research_events 中同一 ID（Q10 证据③） |
| 凭据不落地 | 隐私红绿测试 + 三处落盘内容抽查 |
| payload 上限 | 超长输入被截断且带标记，不丢事件 |
| thinking 可见 | 真实 trace 中思考正文与 content 分离可读 |

风险：值级过滤可能误伤正常的学术文本（如含 `token` 一词的论文标题），
需采用精确凭据模式而非宽泛关键字；`spans.py` 增字段可能与 `spec-041` 的
dual 模式属性映射冲突，须在真 SDK 冒烟中验证。
失败时回滚到任务 02 状态。

## 产出物、执行结果与变更日志

初始写「待执行后填写」。执行后回填：红绿测试输出、三处落盘抽查样例（脱敏后）、
真实 trace ID 与 thinking 字段截图、改动文件清单、`spec-status-changelog.md` 条目。

## 接手机器执行结果（2026-11-08，只读核实）

**状态：已完成。** 交接文档称「骨架在、未接入调用链」已过时：
`backend/app/platform/observability/spans.py` 实际接线位置：

- `:45-46` 导入 `redaction` 与 `ensure_request_id`；
- `:356,470,535` 统一 `request_id` 写入三套观测记录；
- `:378-389` thinking 正文与 content 分离上报（spec-013:101 承诺落地）；
- `:425-431,469-482,511-514` 值级脱敏覆盖 prompt / payload / 路由观测；
- `routes_conversations.py:80` 引入 `bind_request_id`，`:1259-1261` 在 SSE 入口绑定并跨 yield 复位。

`tests/platform/test_task06_identity_redaction.py` 存在并通过；
接手机器定向基线 `pytest tests/evaluation/ tests/observability/ tests/platform/ -q` → `214 passed, EXIT=0`。
真实 trace `98b91aa3…` 的四段 phase span 已由 Langfuse public API 查证（`runs/task-02/evidence.md`）。
