# Spec 024 需求评审最终复审：可见推理过程与会话级推理档位

## 固定字段

- **评审性质**：前两轮 NO-GO 后的 P1 最终需求复审
- **评审角色**：架构师/开发主管（临时 Luna high）
- **评审时间**：2026-09-12 00:08–00:12 +0800
- **评审范围**：Spec024、plans/024 README、Task02–05、Spec025 占位；只读复核，不修改业务代码
- **结论**：**GO（P0=0，P1=0，P2=0）**
- **报告路径**：`docs/sdd/reviews/024-requirement-review.md`

## 结果状态和摘要

本轮复核确认上轮两个 P1 和一个 P2 均已闭合：

1. **首条消息与既有会话入口已形成同一份可实现合同。** Spec024 明确了 `POST /api/conversations/messages` 的请求 JSON、别名解析、`text/event-stream` 成功返回、首个完整 `meta` 字段、能力/项目校验时机、统一错误体和“不创建空会话/不调用模型”规则；既有会话路径明确复用同一请求与 SSE 合同。Task02 对两条路径再次冻结。
2. **SSE 字段、耗时定义、取消/断线/模型失败序列已唯一冻结。** `meta`、`progress`、`memory`、`sources`、`reasoning_*`、`token`、`done`、`error` 均有 envelope 和业务字段；`duration_ms` 明确是 `answer_duration_ms` 的兼容别名，二者均为 SSE stream start 到 done；推理耗时独立定义为 started 到 completed；off、无 delta、失败、首 token 前失败、可写/不可写断线和终态丢弃规则均已写明。
3. **PATCH `updated_at` 已统一。** 值未变化时保持原值，值变化时与 preference 更新事务使用同一时间戳；成功响应在 Spec024 的两个相关章节一致包含 `conversation_id`、`reasoning_effort`、`last_reasoning_effort` 和 `updated_at`。
4. **Spec025 仍为待确认占位。** 没有 `docs/sdd/plans/025/`，且占位明确不创建 Task、不冻结接口、不修改业务代码、不影响 Spec024。

因此，**需求层面允许 Task02 启动**；但项目总门禁仍须遵守 README 的依赖：用户先明确确认 Spec024，且技术评审通过后才可实际启动 Task02。Task02 仍只能在临时数据库中执行探针/合同测试，不得提前执行真实库清理或业务实现。

## 复审依据（实际章节/行号）

- Spec024 端点、首条/既有会话合同：`docs/sdd/specs/024-visible-reasoning-controls.md:81-90`
- Spec024 SSE 事件字段、envelope、event_seq 与状态机：`docs/sdd/specs/024-visible-reasoning-controls.md:92-113`
- Spec024 耗时、off、无 delta、失败、取消/断线和终态：`docs/sdd/specs/024-visible-reasoning-controls.md:115-125`
- Spec024 能力校验、错误体与首条消息不建空会话：`docs/sdd/specs/024-visible-reasoning-controls.md:146-165`
- Spec024 PATCH `updated_at` 与并发优先级：`docs/sdd/specs/024-visible-reasoning-controls.md:160-165,220-223`
- Task02 SSE/入口/耗时/失败序列冻结合同：`docs/sdd/plans/024/task-02-reasoning-protocol-and-migration.md:53-67`
- Task03 后端复用、隔离与观测验收：`docs/sdd/plans/024/task-03-backend-reasoning-stream.md:16-33,95-112`
- Task04 前端事件顺序、终态与历史恢复：`docs/sdd/plans/024/task-04-frontend-reasoning-panel.md:16-24,59-65,79-93`
- Task05 前置门禁、故障 fixture、Spec025 机械检查：`docs/sdd/plans/024/task-05-review-regression-deploy.md:10-23,44-81`
- README 的 Spec 确认与 Task02→03→04→05 依赖：`docs/sdd/plans/024/README.md:4-13`
- Spec025 待确认占位、明确不做与未进入评审：`docs/sdd/specs/025-conversation-context-compaction.md:1-7,39-43,59-69`

## 三项重点复核

### 1. 首条消息 POST 与既有会话路径

**结论：已关闭，P1=0。**

| 检查项 | 结论 | 证据 |
|---|---|---|
| 首条请求 JSON | 完整 | Spec024:87 给出 `content`、`project_id`、`model`、`mode`、可选 `reasoning_effort`，并保留 `question`/`message` 别名；Spec024:88 明确三种正文字段至少一个非空。 |
| 既有会话请求 JSON | 与首条相同 | Spec024:88-90；Task02:56 明确两条路径复用同一字段集合和解析规则。 |
| 首个成功事件 | 完整 `meta` | Spec024:87-90；固定包含 `project_id`、`conversation_id`、`user_message_id`、`assistant_message_id`、`model`、`mode`、最终 `reasoning_effort`、`capabilities_source`，并共享 `message_id`、`event_seq`、`timestamp` envelope。 |
| 失败合同 | 稳定且前置 | Spec024:157、162-165；Task02:56。400/404/409/503 使用统一 `error` body；能力、模型、项目校验发生在会话持久化前。 |
| 空会话与模型调用 | 明确禁止 | Spec024:87、157、165；Task02:56。校验失败不创建空会话、不调用模型；既有会话失败不产生回答 token。 |

本项已足够支持独立实现者完成原子创建、前端首事件初始化和失败回滚，不再需要从 Spec022 猜测新会话合同。

### 2. SSE 字段、耗时、取消/断线/模型失败

**结论：已关闭，P1=0。**

- `meta`、`progress`、`memory`、`sources`、`reasoning_started`、`reasoning_delta`、`reasoning_completed`、`token`、`done`、`error` 的业务字段逐项冻结于 Spec024:111；所有事件统一带 `type`、`message_id`、`event_seq`、UTC `timestamp`。
- `done` 同时包含 `duration_ms`、`reasoning_duration_ms`、`answer_duration_ms`；Spec024:100、115 明确 `duration_ms == answer_duration_ms`，均从 SSE stream start 计至 done。`reasoning_completed.duration_ms` 与 `done.reasoning_duration_ms` 均从 reasoning_started 计至 reasoning_completed；推理未启动时推理耗时为 null。
- `off` 不发送 reasoning 三事件，推理字段和 `reasoning_duration_ms` 为 null，但保留整条 SSE 流的 `duration_ms`/`answer_duration_ms`；Spec024:106、116。
- started 后无有效 delta 的正常完成、started 后模型失败、reasoning_completed 后首 token 前失败均有唯一顺序；Spec024:117-119。
- 可写连接的取消/断线唯一序列为 `error(STREAM_INTERRUPTED,retryable=true)` → `done(interrupted)`；不可写连接只持久化 interrupted；正文前后断线均不得回到 running；Spec024:120、Task02:62。
- 模型失败唯一序列为 `error(CHAT_FAILED)` → `done(failed)`，且 done 为最后逻辑事件；Spec024:118、121、Task02:62。
- event_seq 是全事件流序号，缺口触发 `EVENT_SEQUENCE_GAP`，重复/旧序号和终态后事件丢弃；Spec024:103-113。

本项已满足前端计时、动画终止、持久化状态和后端实现无需自行解释的要求。

### 3. PATCH `updated_at`

**结论：已关闭，P2=0。**

Spec024:163 明确 PATCH 成功响应包含 `updated_at`；值未变化时保持原值，值变化时与 preference 更新事务使用同一时间戳。Spec024:223 重申同一响应字段和更新规则。Spec024:65 的数据模型约束也一致要求选择变更时更新，未发现前后章节冲突。

## P0 / P1 / P2

### P0

无。未发现改变产品目标、引入第二聊天链路、绕过唯一会话流或必然误删长期数据的致命问题。

### P1

无。上轮 P1-1（首条消息完整请求/响应合同）和 P1-2（SSE 字段、耗时、失败/中止序列）均已被 Spec024 与 Task02 的一致文本关闭。

### P2

无。上轮 PATCH `updated_at` 响应字段不一致问题已统一。

## 风险与阻塞

- **需求评审阻塞：无。**
- **实现前置风险：**本次是文档复审，尚未验证真实 Ollama 五档能力、临时数据库迁移回滚、LangChain/direct 双路径、过滤器和 event_seq 运行时行为；这些仍是 Task02 的必做证据，不得把本报告的 GO 当作运行时通过。
- **门禁约束：**README:4、10 要求用户明确确认 Spec024 且需求/技术复审通过后才启动 Task02；在此之前 Spec024 仍保持 `待确认`，不得改状态或执行业务实现。
- **非阻塞风险：**Task03/04/05 当前均为待执行，Task05 仍需 P0/P1 清零、全量回归、部署 smoke 和 Spec025 机械检查。

## 主 Agent 后续动作

1. 保持 Spec024 状态为 `待确认`，等待用户明确“确认 spec/按这个执行”；本报告 GO 不替代用户确认。
2. 完成并通过技术评审；技术评审与用户确认都满足后，允许按 Task02 依赖启动协议冻结/能力探针，且只使用临时数据库。
3. 启动 Task02 时逐项落盘真实五档证据、迁移前后计数、故障回滚、逐事件 JSON 样本和双路径隔离报告；若任何档位或保留边界失败，按 Task02 规则回到 NO-GO。
4. 后续 Task03/04 严格复用本次冻结的入口、SSE、耗时和终态合同；Task05 再执行全量回归和部署验收。

## 改动文件

- 覆盖写入：`docs/sdd/reviews/024-requirement-review.md`
- 未修改：`backend/**`、`frontend/**`、数据库、迁移、部署配置、Spec024、Task02–05、Spec025

## 检查命令、退出码和结果

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `test -f` 核对 Spec024、README、Task02–05、Spec025 | 0 | 所有复审输入存在 |
| `test ! -e docs/sdd/plans/025` | 0 | Spec025 计划目录不存在 |
| `rg -n '^<<<<<<<|^=======|^>>>>>>>'` 覆盖本次复审输入 | 1 | 无冲突标记；无匹配的退出码 1 属预期 |
| `git diff --check -- <复审输入>` | 0 | 无空白错误 |

未运行 pytest、node 检查、真实 Ollama、数据库迁移、服务启动、浏览器 smoke、部署或全量回归；本轮仅做需求文档复审，以上动作属于后续 Task02/Task05。

## 产物路径

- 需求评审最终复审报告：`docs/sdd/reviews/024-requirement-review.md`

## 决策依据

三项指定复核点都已达到“独立实现者无需猜测”的需求门槛：入口请求/响应与空会话规则完整，SSE 字段/耗时/终态唯一，PATCH `updated_at` 一致；Spec025 仍隔离为待确认占位。因此本次结论为 **GO**，允许在用户确认 Spec024 且技术评审通过后启动 Task02。

## 开始、结束和总耗时

- **开始**：2026-09-12 00:08 +0800
- **结束**：2026-09-12 00:12 +0800
- **总耗时**：约 4 分钟

## 模型、token 和工具统计

- **模型**：临时 Luna high（按主 Agent 分派要求）
- **Token**：当前运行环境未提供可靠计数，未编造数值
- **工具调用**：6 次只读文件/命令检查，1 次报告覆盖写入；未调用测试、迁移、部署、reset、stash、clean、push 或业务代码编辑
