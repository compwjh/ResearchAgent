# Task02 授权与事件契约（盘点草案）

关联：[Spec050](../../../../specs/050-agent-safety-and-factuality.md) · [入口覆盖矩阵](entry-coverage-matrix.md) · [Task02 契约](../../task-02-contract-and-feasibility.md)

| 项 | 值 |
|---|---|
| 核对日期 | 2026-11-14 |
| 分支 | `codex/spec050-piguard-integration` |
| 性质 | **盘点草案**，不是已冻结契约；未新增任何端点或运行时代码 |

## 1. 定稿边界（先写明，避免误用）

- Spec050「端点与接入」段明确：**新增确认端点的具体路径、状态码及读写契约，核验选项的请求字段，以及事件水合载体在 Gate 2 冻结**。本文件不冻结这些值，只登记现状与候选字段。
- 按当次用户指派，**执行授权边界、检测失败时敏感动作处置、上线阈值、最终评测口径由负责人定稿**。本文件不给出这些项的裁决值。
- Spec050 仍 `待确认`，Gate 2 需求/技术评审未执行。本草案是 Task03 的输入盘点，不能当作已评审契约使用。

## 2. 现有可复用资产（实测）

| 资产 | 位置 | 可复用部分 | 不足 |
|---|---|---|---|
| 计划审批状态机 | `backend/app/research/application/approval_service.py:62`；错误码 `:44-45` | 版本绑定、幂等键、过期/冲突/取消、`supersede_approvals` | 粒度是「计划」，不是「单动作」 |
| 审批持久化 | `backend/app/research/infrastructure/research_store.py:3762` `create_approval` | 所有者校验、状态转换 | 无 `action_ref`、无参数规范化摘要、无消费态 |
| 证据投影 | `backend/app/api/routes_conversations.py:1294,1324` `step-evidence-v1` | 有界列表、脱敏投影、消息归属 | 是 Spec044 投影，不是 `guard-event-v1` |
| URL / SSRF 校验 | `backend/app/core/url_security.py:141,185,205,236` | 白名单、重定向链、peer IP | 与目标级动作授权正交 |
| 幂等 | `backend/app/research/application/acquisition.py:183-250,594` | `idempotency_key`、一次确认 | 防重复导入，不防越权动作 |
| worker 租约 | `backend/app/research/application/scheduler.py:31-58` | lease / reservation / ownership token | 资源租约，不是用户授权 |

**实测结论**：本分支不存在 `guard-event-v1`、`guard_event`、单动作确认端点或 action-level 授权表（全仓检索 0 命中）。Task03 需要新建，不能靠改 `PlanApprovalService` 替代。

## 3. 任务授权范围（候选字段，待 Gate 2 冻结）

Spec050 数据模型要求由**服务端**保存，网页、PDF、工具结果、历史记忆、模型生成文字均不能授予或扩大权限。候选字段：

| 字段 | 说明 |
|---|---|
| `task_scope_id` / `owner_id` / `task_id` | 服务端绑定，不接受请求体注入 |
| `goal` | 用户目标原文摘要（仅展示） |
| `allowed_capabilities` | 允许能力集合，服务端白名单 |
| `resource_constraints` | 资源约束（主机白名单、目标域名、数量上限等） |
| `scope_version` / `policy_version` | 策略版本；执行前仍校验当前权限是否撤销 |

## 4. 拟执行动作与单次授权（候选状态机）

状态集合按 Spec050：`待确认 → 允许 / 拒绝 / 失效 / 已消费`。

| 转换 | 触发 | 必须成立的校验 |
|---|---|---|
| 创建 → 待确认 | 硬规则允许、在任务范围内、但缺授权 | 已注册动作；参数与目标已规范化并生成摘要 |
| 待确认 → 允许 | 用户确认具体动作/目标/范围 | 服务端在**真正执行前**再次校验；确认只使用一次 |
| 待确认 → 失效 | 参数变化、任务取消、超时、并发重复确认 | 旧确认不得触发新执行 |
| 允许 → 已消费 | 动作执行返回明确结果 | 幂等键；不得重放 |
| 允许 → 待复核 | 结果未知 / 故障 | 重试不得扩大原范围、不得重复已成功的副作用 |
| 任意 → 拒绝 | 违反硬规则或超出任务范围 | 直接阻止，不发起确认 |

候选字段：`action_ref`、`owner_id`、`task_id`、`tool_name`、`normalized_args_hash`、`target_summary`、`status`、`scope_version`、`idempotency_key`、`consumed_at`、`result_unknown`。

**待负责人定稿**：检测失败时敏感动作如何处置（Spec050 要求「停止必须核验的动作并提示重试」「敏感动作需要的检查无法完成时暂停该动作」，具体降级与重试策略未定）。

## 5. `guard-event-v1` 公共投影（候选字段，待 Gate 2 冻结）

Spec050 要求的字段：稳定事件 ID、请求及可用的消息／步骤／任务关联、模块、阶段、状态、原因码、实际模型及策略版本、耗时、白名单计数、授权可见证据定位；明确区分执行完毕 / 拦截 / 失败 / 跳过。

| 字段组 | 候选字段 | 隐私约束 |
|---|---|---|
| 标识 | `event_id`、`request_id`、`message_id` / `step_id` / `task_id` | 按消息/任务所有者读取 |
| 分类 | `module`、`phase`、`status`、`reason_code` | `status ∈ {executed, blocked, failed, skipped}`；故障不得记为成功防御 |
| 版本 | `model_actual`、`policy_version`、`strategy_version` | 记录实际使用的模型，不记录隐藏推理 |
| 度量 | `duration_ms`、`allowlist_count` | 不携带攻击原文 |
| 证据 | `authorization_evidence_ref` | 指向服务端授权记录，不内联敏感资料/凭据 |

生命周期：刷新可查脱敏事件；删除所属消息或任务时清理；无持久会话仅展示当次；SSE 重连不重复、不从终态倒退；前端与 Langfuse 只收白名单投影。与 `step-evidence-v1` **并存**，不替换。

## 6. 清单（版本化，供 Task06/08）

- `guard-model-manifest-v1`：角色、基础模型与 tokenizer 版本、数据及分割指纹、训练参数与日志、产物哈希、评测引用。
- `security-benchmark-v1`：环境、样本、评分器、配置、结果及失败统计。

本机已具备的固定值（见 [PIGuard 证据核对](../../piguard-training-evidence.md) 与本目录 [加载冒烟](m3max-load-smoke.md)）：revision `8ccc9b6f…`、上游 commit `1b5751e8…`、训练/验证指纹 `d2d3a74c…` / `fdf0f1f8…`、权重 SHA-256 `3f284d8e…`、标签映射 `{benign:0, injection:1}`、`max_length=256`、3 epoch / 7,194 步。

**尚未固定**：safetensors 转换产物哈希、转换前后同输入一致性证据、策略版本号、评测引用、上线阈值（由负责人定稿）。

## 7. 交接给 Task03 的最小挂接点

按 [覆盖矩阵](entry-coverage-matrix.md) §6，以三个收敛点为主：

1. `backend/app/skills/tool_dispatch.py:484` `build_default_dispatch()` — 聊天原生/JSON 降级/fallback 共用。
2. `backend/app/research/application/agent_runtime.py:2050` `_dispatch()` — 研究运行时独立入口，必须单独校验。
3. `backend/app/paper_discovery/application/worker_tool.py:641` `dispatch()` — 异步 discover/import。

加上 E11/E12/E13 三个直接导入路由，以及 E15–E19 的异步与重试路径。异步、重定向、重试、批次与可直接调用的分发入口都要覆盖。

## 8. 明确不做（本任务）

- 不新增端点、不改状态码、不冻结事件水合载体（Gate 2）。
- 不写授权边界/失败处置/上线阈值/评测口径的裁决值（负责人）。
- 不实现 `guard-event-v1` 或单动作确认（Task03/04）。
- 不加载模型进运行时、不做权重转换、不跑公开基准（Task08）。
