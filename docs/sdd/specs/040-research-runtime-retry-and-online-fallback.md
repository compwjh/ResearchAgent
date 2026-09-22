# Spec 040 — Research Runtime 指数退避与线上模型兜底

## 状态

**当前状态：`已完成`**

## 一句话目标

当研究 Worker 遇到临时资源竞争、Ollama 不可用或模型调用失败时，任务能够持久化等待并按指数退避重试；重试仍失败时，在明确授权的前提下切换到线上模型继续执行，而不是立即变成无法诊断的 `AGENT_RUN_FAILED`。

## 背景与问题

- 资源探针没有可用 Worker 时，Runner 在模型调用前立即退出，当前编排器将底层错误泛化成 `AGENT_RUN_FAILED`。
- 研究任务之间共享单机 Worker 配额，同一时刻启动多个任务会产生短暂资源竞争；立即失败既浪费已有 Intake/计划结果，也不符合“可恢复失败”的约定。
- 当前模型升级只发生在模型已经进入循环且输出格式反复无效的场景，不能覆盖模型创建失败、连接超时、429/5xx 或资源争用。
- 用户需要看到“排队、下一次重试时间、正在切换模型”等可操作状态，不能把等待误报为终态失败。

## 范围与成功定义

本 Spec 只改 ResearchAgent Runtime 的失败分类、持久化退避调度、受控模型回退和进度投影。成功条件：

1. 临时资源忙不会立即终止任务；WorkItem 进入可恢复等待状态并在退避后自动重试。
2. Ollama/本地模型的瞬态失败可按策略重试；达到阈值后才尝试线上模型。
3. 线上模型切换必须经过配置和能力白名单，失败仍保留原始错误、尝试链和可重试状态。
4. 已完成的 Worker、候选证据和报告版本不可被重试覆盖；同一 WorkItem 不能并发重复执行。

## 数据模型

| 记录 | 字段与约束 |
|---|---|
| `RetryPolicy` | `max_attempts`、`base_delay_seconds`、`max_delay_seconds`、`jitter_ratio`、可重试错误码集合；服务端固定上限，禁止任务自行放大 |
| `WorkItemAttempt` | `attempt_id`、`work_item_id`、`attempt`、`provider`、`model`、`error_code`、`started_at`、`ended_at`、`next_retry_at`、`status`；每次尝试只追加不覆盖 |
| `ProviderFallback` | `research_task_id`、`work_item_id`、`from_provider`、`to_provider`、`reason_code`、`approved`、`created_at`；不得保存 API Key、Cookie 或完整 Prompt |
| `ResearchWorkItem` 增量字段 | `retry_count`、`next_retry_at`、`last_error_code`、`provider_preference`、`status=waiting_retry`（或等价现有状态） |

## 失败分类与处理顺序

| 类别 | 示例 | 处理 |
|---|---|---|
| 临时资源 | Worker 配额为 0、探针暂时不可用 | 持久化 `waiting_retry`，指数退避；不换模型、不丢任务 |
| 本地模型瞬态 | Ollama 连接断开、超时、429/5xx、模型加载失败 | 有界重试；仍失败且允许线上回退时切换 Provider |
| 模型输出瞬态 | JSON 不合法、字段缺失、重复工具调用 | 复用现有有限重试和 Search Worker 恢复；达到阈值后按角色策略回退 |
| 确定性输入/安全错误 | 能力未授权、证据越界、工具参数非法、用户取消 | 不自动换模型；立即失败并保留明确错误码 |
| 上游失败 | 依赖 WorkItem 失败 | 等待依赖恢复后重试；不得伪造候选或报告 |

### 指数退避

第 `n` 次重试等待 `min(max_delay, base_delay × 2^(n-1)) × (1 ± jitter_ratio)`；默认建议 `base=2s`、`max=120s`、`jitter=20%`、单 WorkItem 最多 5 次。实际常量进入配置/注册表并可由测试注入。服务重启后按 `next_retry_at` 恢复，不能重新从零计数。

### 线上模型回退

- 默认先用当前本地路由结果；只对 `MODEL_UNAVAILABLE`、超时、429/5xx 和连续输出无效等临时错误启用。
- 线上 Provider 必须在模型注册表中已启用、通过能力/成本/数据边界校验，并由部署配置显式打开；未打开时保持可重试失败，不偷偷外传数据。
- 回退顺序为“本地重试 → 线上候选一次或有限次数 → 失败后 `partial/failed`”；不在安全错误、用户取消或证据越界时回退。
- 事件中只记录 Provider/模型别名、原因码和尝试编号，不记录密钥、完整请求、隐藏思维链或论文正文。

## 端点 / 接口与事件

| 动作 | 输入 | 成功返回 | 失败情况 |
|---|---|---|---|
| 查询任务 | `GET /api/research-tasks/{id}` | 含 `waiting_retry`、`retry_count`、`next_retry_at`、当前 Provider | 不存在 404 |
| 事件流 | 现有 research events SSE | `retry_scheduled`、`retry_started`、`provider_fallback`、`retry_exhausted` | 断线可按 event_seq 续接 |
| 手动恢复 | 现有恢复/重试入口（若已存在则扩展） | 幂等触发待重试 WorkItem | 非可恢复状态 409，权限/配置错误 403/422 |
| 配置探针 | 部署配置/模型注册表 | 返回允许的 Provider 列表与脱敏原因 | 未配置线上 Provider 时明确 `ONLINE_FALLBACK_DISABLED` |

## 边界与失败场景

- 多任务同时争用单一 Worker；退避期间服务重启或进程崩溃。
- Ollama 进程不可达、模型不存在、加载超时、429/5xx；线上 Provider 不可达或额度耗尽。
- 同一 WorkItem 重复恢复、租约过期、已有完成结果后收到迟到的重试。
- `max_attempts=0`、负数、过大延迟、时钟回拨、随机抖动不可复现。
- 线上 Provider 未配置、授权失效、数据边界不允许外发。
- 依赖搜索失败时，评估/报告不能提前运行；不能用空候选生成报告。

## 明确不做

- 不做跨机器分布式调度、消息队列或自动扩缩容。
- 不自动下载/卸载模型，不改变既有来源、下载安全和证据范围。
- 不在安全/权限/用户取消错误上盲目重试或换线上模型。
- 不保存完整内部思维链、API Key、Cookie、Token 或完整 Prompt。
- 不保证线上 Provider 一定可用；回退失败必须可诊断、可手动恢复。

## 验收方式

1. 启动两个研究任务竞争单 Worker，第二个任务显示 `waiting_retry`，退避后自动获得槽位并完成搜索。
2. 注入 Ollama 超时/429，验证尝试记录、指数延迟、最大次数和服务重启恢复。
3. 在开启线上回退的配置下模拟本地模型不可用，验证事件顺序、Provider 切换和最终报告；关闭配置时不得外发。
4. 注入能力未授权、证据越界和用户取消，确认不重试、不换模型且错误码稳定。
5. 验证两个进程不会重复领取同一 WorkItem，已完成证据不被覆盖，SSE 断线可续接。
6. 运行当前 Spec 的定向测试；Spec 收口时再执行全量回归、真实 API E2E、部署和人工验收案例。

## 产品使用步骤（初稿）

1. 用户用自然语言创建并批准研究计划。
2. 若资源暂时繁忙，页面显示“资源排队中，将在约 X 秒后重试”，用户无需重复提交。
3. 若本地模型不可用且部署允许线上回退，页面显示“本地模型不可用，正在切换备用模型”，随后继续显示 Worker 进度。
4. 若所有尝试失败，页面显示稳定错误码、最后一次尝试时间、可重试按钮和是否发生过 Provider 切换；已完成部分保持可查看。

## 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---:|---|---|
| 架构师 | 自身（当前执行任务的 Agent） | 200k | 主会话 | 失败分类、回退顺序和最终裁决 |
| 产品经理 | `qwen3.5:9b`（已由 `ollama list` 核实） | 32k | Task(doc-updater) | 用户等待/回退提示和验收步骤 |
| 开发主管 | `qwen3.8:27b`（已由 `ollama list` 核实） | 64k | Task(architect) | 运行时、路由和持久化技术评审 |
| 后端开发 | `qwen3.8:27b`（已由 `ollama list` 核实） | 64k | Task(backend-dev) | 退避、重试、Provider 回退实现 |
| 测试 | `qwen3.5:9b`（已由 `ollama list` 核实） | 32k | Task(tester) | 定向测试、并发和真实 API 验证 |

线上模型不在本地模型名中硬编码；必须通过模型注册表和部署配置提供，并在运行证据中记录脱敏别名。

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写本 Spec | 本文件 | — | 完成 |
| 02 | 固化失败分类与 Go/No-Go 门禁 | [task-02-failure-contract.md](../plans/040/task-02-failure-contract.md) | 01 | 待执行 |
| 03 | 持久化指数退避与资源排队 | [task-03-exponential-backoff.md](../plans/040/task-03-exponential-backoff.md) | 02 | 待执行 |
| 04 | 受控线上模型回退 | [task-04-online-provider-fallback.md](../plans/040/task-04-online-provider-fallback.md) | 02、03 | 已完成 |
| 05 | 事件、前端状态与观测指标 | [task-05-retry-observability.md](../plans/040/task-05-retry-observability.md) | 03、04 | 已完成 |
| 06 | 定向验收、全量回归、部署与复盘 | [task-06-review-deploy-retro.md](../plans/040/task-06-review-deploy-retro.md) | 05 | 已完成 |

## 评审记录

- 需求评审：`docs/sdd/reviews/040-requirement-review.md`（通过；Task06 证据补充完成）
- 技术评审：`docs/sdd/reviews/040-tech-review.md`（通过；Task06 证据补充完成）
- 验收评审：`docs/sdd/reviews/040-acceptance-review.md`（READY_FOR_USER，10/10）

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-20 | 架构师（自身） | 根据会话 `14355ba3973e46d6a59fd2819df6f9b8` 的并发资源失败证据，新增指数退避、持久化重试和受控线上模型回退 Spec；当前仅落盘文档，等待确认。 |
| 2026-09-20 | 后端/前端实现 | Task02–05 已完成：资源忙进入持久化 `waiting_retry`，模型瞬态错误按有界指数退避恢复；授权后可通过 Spec035 注册表只回退一次线上 Provider；任务 API、SSE 投影和 Research 页面展示脱敏等待/切换状态。Task06 收口门禁仍待执行。 |
| 2026-09-20 | 架构师（自身） | Task06 完成：全量回归 `2684 passed, 3 skipped, 67 subtests`；8500 回环部署的 health/ready/models/research-task/scheduler API 全部通过；DeepSeek 线上探针在修正模型别名为 `deepseek-flash` 后 HTTP 200；人工验收案例、准备度矩阵、验收评审和复盘已落盘，Spec040 标记为已完成。 |
