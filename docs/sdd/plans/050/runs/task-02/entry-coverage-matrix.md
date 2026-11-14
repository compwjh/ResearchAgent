# Task02 入口覆盖矩阵

关联：[Spec050](../../../../specs/050-agent-safety-and-factuality.md) · [Task02 契约](../../task-02-contract-and-feasibility.md) · [Go/No-Go](go-no-go.md)

| 项 | 值 |
|---|---|
| 核对日期 | 2026-11-14 |
| 分支 / commit | `codex/spec050-piguard-integration` |
| 范围 | 只读代码勘察；未改动任何运行时代码 |
| 依据 | Spec050「端点与接入」段要求至少核对普通对话、直接聊天、知识库问答、文章助手、研究工具，逐项记录覆盖、跳过或禁止的动作 |

## 1. 状态边界

- Spec050 仍为 `待确认`；Gate 2 需求/技术评审未执行。本矩阵是**盘点证据**，不是通过评审的契约冻结。
- `guard-event-v1` 端点、投影与「单动作确认」端点在本分支全仓检索 **0 命中**（ABSENT），属 Task03/04 交付；现有只有 Spec044 的 `step-evidence-v1`（`backend/app/api/routes_conversations.py:1294,1324`）。
- 现有 `PlanApprovalService`（`backend/app/research/application/approval_service.py:62`）是**计划级**审批（`kind="plan"`、`APPROVAL_STALE`/`APPROVAL_CONFLICT`），不是 Spec050 要求的单动作授权；两者不可互相替代。
- 按三轮决策第 2 条：未接入路径如实标记覆盖范围，该路径的高风险动作仍不得直接放行。因此下表「待接入」不等于「可放行」。

## 2. 工具分发入口

| # | 入口 | 证据路径 | 现有硬约束 | Spec050 覆盖状态 |
|---|---|---|---|---|
| E01 | `POST /api/chat`（普通对话/Skill 命中） | `backend/app/api/routes_chat.py:55`；ToolLoop 构造 `:152-159` | `build_default_dispatch()`；仅 enabled 工具启用；全部禁用时明确提示不走工具链路 `:143-148` | **待接入**：工具执行前须加同一授权契约 |
| E02 | `POST /api/conversations/messages`、`POST /api/conversations/{id}/messages`（直接聊天） | `backend/app/api/routes_conversations.py:2423,2428`；ToolLoop `:1727-1732` | 同上；另有服务端派生的 `fallback_tool_call` `:1703-1722`（`download_and_import_paper` 与目录检索回退） | **待接入**：fallback 分支同样须过授权校验 |
| E03 | ToolLoop 原生 tool_calls 路径 A | `backend/app/skills/tool_executor.py:272` `run()`；`:338` 聚合执行 | `_check_tool` 校验工具名/enabled/参数 schema `:210-219`；先全部校验再执行 `:325-338` | **待接入**：校验内容不含任务授权与具体目标 |
| E04 | ToolLoop 降级计划 JSON 路径 B | `backend/app/skills/tool_executor.py:149` `parse_plan_json`；`:364-395` | 同样经 `_check_tool`；非法计划拒绝执行并给出可读错误 | **待接入**：JSON 降级不得绕过授权 |
| E05 | ToolLoop 服务端派生 fallback 调用 | `backend/app/skills/tool_executor.py:395-410`（`fallback_attempted` 单次） | 只执行一次、且仅在 `not tool_executed` 时；仍走 `_check_tool` | **待接入**：属模型未产出调用时的隐式动作，必须显式登记 |
| E06 | `build_default_dispatch()` / `_ADAPTERS` | `backend/app/skills/tool_dispatch.py:473-481`（7 项）、`:484-500` | 未知工具/异常安全降级为 `DispatchResult(ok=False)`；`_check_tool` 已过滤未注册工具 | **待接入**：分发表是共享收敛点，适合统一挂接，但研究运行时另有独立入口 |
| E07 | 研究 AgentRuntime `_dispatch` | `backend/app/research/application/agent_runtime.py:2050-2056` | 注入 `tool_executor` 优先；生产 fallback 直接调 `build_default_dispatch()` | **待接入**：必须在此独立入口校验，不能只改 E06 |
| E08 | 研究 WorkerTool `dispatch` | `backend/app/paper_discovery/application/worker_tool.py:641-649` | `operation` 仅 `discover`/`import`；`_KNOWN_SOURCES` 校验；失败带 `retryable` 标志 `:625-638` | **待接入**：异步工具执行前的授权确认点 |

## 3. 下载 / 导入入口

| # | 入口 | 证据路径 | 现有硬约束 | Spec050 覆盖状态 |
|---|---|---|---|---|
| E09 | 工具 `download_and_import_paper` | `backend/app/skills/tool_dispatch.py:348-378` | 复用 `_paper_candidate_hosts` 白名单（`backend/app/api/common.py:206`）；禁止传入任意 URL；`safe_import_error_message` 脱敏 | **已覆盖（URL 层）** / **待接入（授权层）** |
| E10 | `import_candidate()` 主实现 | `backend/app/paper_discovery/application/paper_import.py:474`；内部 fallback `:640` | `allowed_hosts` 贯穿 DOI 解析与语义学者回退 `:553-579,637-643` | **已覆盖（URL 层）** / **待接入（授权层）** |
| E11 | 论文检索路由导入 | `backend/app/api/routes_paper.py:692` | `common.article_settings` + `_paper_candidate_hosts`；会议须服务端已配置 `:687-689` | **待接入** |
| E12 | 文章助手下载 | `backend/app/api/routes_article.py:237` `/agent/articles/download`；`/agent/run` `:105`；人工登录动作 `:348` | 任务/候选 ID 校验；`waiting_login` 状态；`download_article` 或 `download_under_skill` | **待接入**：已有人工确认语义，但不是单动作授权状态机 |
| E13 | 文献地图导入桥接 | `backend/app/literature_maps/application/runtime.py:54` | 要求先解析官方/OA PDF，否则 `IMPORT_SOURCE_UNRESOLVED`；不落地页自动补全 `:40-46` | **待接入** |
| E14 | URL / 重定向 / SSRF 校验 | `backend/app/core/url_security.py:141` `validate_url`、`:185` `validate_redirect_target`、`:205` `validate_redirect_chain`、`:236` `validate_peer_ip` | 混淆主机识别、私网 IP 拒绝、DNS 解析校验、重定向链逐跳校验 | **已覆盖**：现有硬约束始终生效，Spec050 不替换 |

## 4. 研究异步与重试入口

| # | 入口 | 证据路径 | 现有硬约束 | Spec050 覆盖状态 |
|---|---|---|---|---|
| E15 | `POST /research-tasks`（202 异步） | `backend/app/api/routes_research.py:1464-1485` | 仅进统一 Session/Intake；旧 payload 兼容分支不启动 Orchestrator；project-mismatch fail-closed | **待接入** |
| E16 | `POST /{id}/acquisitions`（202 导入批次） | `backend/app/api/routes_research.py:1640-1658` | 一次确认 + `idempotency_key`；`backend/app/research/application/acquisition.py:183-250,594` | **已覆盖（幂等）** / **待接入（授权）** |
| E17 | 调度器与 worker 授权粒度 | `backend/app/research/application/scheduler.py:31` `WorkerGrant`、`:62` `ResearchScheduler` | lease CAS、`reservation_ids`、`ownership_token`；grant 明确不含 prompt/owner token | **待接入**：这是**资源租约**授权，不是用户动作授权 |
| E18 | `RetryPolicy` / 退避 | `backend/app/research/application/agent_runtime.py:66-87`、`:89-104` | `max_attempts=5`、`max_delay=120s`、jitter ≤0.5；白名单错误码 | **待接入**：重试须重新校验授权且不得重放已成功副作用 |
| E19 | 重试执行点 | `backend/app/research/application/agent_runtime.py:1951` `_start_retry_attempt`、`:3120` | checkpoint + handoff hash；独立 Run link | **待接入**：需区分「模型输出无效重试」与「动作结果未知重试」 |
| E20 | 计划审批 | `backend/app/research/application/approval_service.py:62`；`research_store.py:3762` | 计划版本 + 幂等键 + 状态机 | **不替代**：需另建单动作授权，二者并存 |

## 5. 五个 Scope 内场景逐项判定

| 场景 | 入口 | 覆盖 | 跳过 | 禁止 |
|---|---|---|---|---|
| 普通对话 | E01、E03–E06 | 工具执行前校验（Task03） | 无工具的纯文本问答不产生动作 | 未接入授权前，联网/下载/写入/导入/外发类工具不得直接放行 |
| 直接聊天 | E02、E04、E05 | 原生、JSON 降级、fallback 三条路径同一契约 | 全部工具禁用时的降级提示链路（不产生动作） | 模型文本或历史记忆不得授予/扩大权限 |
| 知识库问答 | `backend/app/api/routes_kb.py:996-997` `/kb/ask` | 主动启用核验时单独设置正文发布边界（Task07） | 当前直接 SSE 转发、无工具调用，无需执行前授权 | 检索结果/引用内容不得作为授权来源 |
| 文章助手 | E12、E13、E11 | 下载/导入动作纳入单动作确认 | `waiting_login` 人工登录沿用现有流程 | 任意 URL 下载、越权目标导入 |
| 研究工具 | E07、E08、E15–E19 | 独立分发入口 + 异步 + 重试全部挂接 | 纯检索类只读动作按现有白名单继续 | 重试扩大原范围、重放已成功副作用、lease 冒充用户授权 |

## 6. 可追溯性核对

- 每个入口均给出文件与行号，来自本分支 `6082742d` 之前的运行时代码；本任务未修改这些文件。
- 现有「已覆盖」项仅指 URL/SSRF/参数/幂等等**既有硬约束**，不代表 Spec050 的执行授权契约已实现。
- 结论：`guard-event-v1` 与单动作授权均 ABSENT，覆盖矩阵中 20 个入口里 **3 项已覆盖硬约束、17 项待接入**，无「已完整接入」项；Task03 需以 E06/E07/E08 三个收敛点为主挂接位置。
