# Spec 031 — 动态模型路由与资源调度优化

## 状态

**当前状态：实施中**

## 一句话目标

利用 Research Task 的真实质量、延迟和资源数据优化 fast/strong 模型路由及 9B Worker 并发，在不牺牲硬性质量门槛的前提下降低等待时间，并用基准决定是否需要多 Ollama 实例。

## 背景与依赖

- Spec027 已提供规则优先的动态路由、失败升级和基础内存额度，但不从历史数据自动调整策略。
- Spec013/Langfuse 已记录本地 Ollama 阶段耗时和调用结果，可作为离线评估输入；观测故障不能影响业务。
- 本 Spec 依赖 Spec027 和 Spec028 的稳定 WorkItem/调度数据；多实例不是预设结论。

## 数据模型

| 实体 | 关键字段 | 约束 |
|---|---|---|
| RoutingDecision | task_type、features、candidate_models、chosen_model、reason、policy_version | 不含 Prompt/思维链 |
| ModelOutcome | decision_id、schema_valid、quality_score、ttft、duration、tokens、error_code | 指标缺失可空 |
| ResourceSnapshot | available_memory、loaded_models、estimated_kv、active_workers、captured_at | 探针失败显式标记 |
| RoutingPolicy | version、profile、rules、thresholds、status | draft / shadow / active / retired |
| BenchmarkRun | topology、worker_count、model、throughput、ttft、peak_memory、failures | 固定负载可复现 |

## 路由与基准合同

- 首先对单 Ollama 服务的 1、2、3、4 个 9B Worker 做固定输入基准，比较吞吐、首 token、峰值内存和失败率。
- 只有多实例相对单实例在预设指标上有明确收益且不破坏局域网访问时，才允许增加受控多端口实例池。
- 历史指标先以 shadow policy 回放；达到最小样本量和质量门后才可激活，任何时候可回退 Spec027 静态策略。
- 路由器不得为了延迟选择无法满足 JSON Schema、上下文或证据任务的模型。
- 观测数据不可用时使用 Spec027 规则和实时资源探针，不阻塞任务。

## 接口

| 动作 | 输入 | 成功返回 | 失败 |
|---|---|---|---|
| GET /api/research-routing/status | 无 | active policy、模型健康与资源摘要 | 503 探针不可用但含降级状态 |
| GET /api/research-routing/decisions | task/filter/cursor | 脱敏决策与结果 | 400 |
| POST /api/research-routing/benchmarks | 受控模型/worker 范围 | 202 BenchmarkRun | 409 任务繁忙；422 非允许模型 |
| POST /api/research-routing/policies/{version}/activate | 明确确认 | active policy | 409 样本/质量门不够 |

## 边界与失败场景

- 模型卸载、资源数据过期、多个任务并发、基准中断、Langfuse 缺失、质量评分偏差和策略回滚。
- 至少保留 20% 系统内存；额度不足时排队，不使用交换内存作为正常扩容手段。
- 用户 speed/balanced/quality 是上层约束，优化器不能越过其硬预算和质量门。
- 多 Ollama 实例若启用，必须保持既有局域网入口不变，由内部路由隐藏端口细节。

## 明确不做

- 不训练或微调模型，不自动下载新模型，不修改用户 Ollama 安装。
- 不根据单次失败立即永久改变策略。
- 不把完整 Prompt、回答或隐藏思维链写入路由数据。
- 不实现跨机器集群调度。

## 验收方式

- 固定任务集比较静态策略、shadow policy 和 active policy，质量门不退化。
- 资源探针、9B 扩缩、27B 单并发、跨任务公平性和故障降级可重复验证。
- 多实例只有 Go/No-Go 报告为 GO 才实施；NO-GO 时 Spec 仍可凭单实例优化完成。
- 最终 Task 一次全量回归、运行时基准、部署和复盘。

## 产品使用步骤（由产品经理在 Spec 确认后填写）

- 待确认后补充质量档位、路由说明与基准管理的用户旅程。

## 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身 | 200k | 主会话 | 路由目标和 Go/No-Go |
| 产品经理 | `qwen3.5:9b` | 32k | `Task(doc-updater)` | 可解释路由交互 |
| 开发主管 | `qwen3.8:27b-mlx` | 32k | `Task(architect)` | 性能与质量评审 |
| 初级开发 | `qwen3.8:27b-mlx` | 32k | `Task(backend-dev)` / `Task(frontend-dev)` | 路由、调度和界面实现 |
| 测试 | `qwen3.5:9b` | 32k | 分端 tester + `Task(tester)` | 基准和回归验收 |

## 任务计划

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec031 | 本文件 | — | 完成 |
| 02 | 单实例/多实例与 Worker 基准门 | [`task-02-ollama-topology-benchmark.md`](../plans/031/task-02-ollama-topology-benchmark.md) | Spec027/028、确认、双评审 | 已完成（单实例条件放行） |
| 03 | 实现决策/结果数据与 shadow policy | [`task-03-routing-observation-shadow.md`](../plans/031/task-03-routing-observation-shadow.md) | 02 | 已完成（单实例条件放行） |
| 04 | 实现内存感知 Worker 扩缩与策略激活 | [`task-04-adaptive-worker-routing.md`](../plans/031/task-04-adaptive-worker-routing.md) | 03 | 已完成（后端 GO） |
| 05 | 实现路由解释与基准界面 | [`task-05-routing-insights-ui.md`](../plans/031/task-05-routing-insights-ui.md) | 04 | 已完成（前端 GO） |
| 06 | 最终评审、回归、基准、部署与复盘 | [`task-06-review-regression-deploy.md`](../plans/031/task-06-review-regression-deploy.md) | 02–05 | 待执行 |

## 评审记录

- 需求评审：`docs/sdd/reviews/031-requirement-review.md`（待评审（未执行））
- 技术评审：`docs/sdd/reviews/031-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/031-acceptance-review.md`（待评审（未执行））

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-12 | 架构师（自身） | 创建动态模型路由、资源优化和 Ollama 拓扑基准 Spec |
| 2026-09-17 | 架构师（自身） | 用户确认 Spec031，进入 Task02；子 Agent 临时使用 Luna high，Task 阶段只运行定向测试。 |
