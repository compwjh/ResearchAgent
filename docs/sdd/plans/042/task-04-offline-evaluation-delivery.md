> 关联：[spec-042](../../specs/042-openeval-agent-evaluation.md) ｜ [计划索引](./README.md) ｜ [需求评审](../../reviews/042-requirement-review.md) ｜ [技术评审](../../reviews/042-tech-review.md)
> 依赖：Task 02（Go，`chat_quality` 闭环）与 Task 03（记忆探针，`adopt:qwen3.5:9b`）
> 当前状态：**进行中（待实现）**（2026-10-23 用户明确继续；本文件只冻结交付范围与实现契约）

# Task 04 — 可复用本地离线评测交付

## 一句话目标

把 `docs/sdd/plans/042/task-02-run-eval.py` 已验证的最小流程迁移为 `backend/eval_042` 内可复用 CLI：导出 Langfuse trace → 本地判官评分 → 回写 score → 精确验证，并始终落盘 JSON + Markdown 报告；全链路只允许 loopback，失败返回非零。

## 已确认范围

- 只覆盖 Spec042 第一期的 `chat_quality` 与 `memory_correctness`。
- 复用 `backend/eval_042/config.py`、`langfuse_export.py`、`judge_client.py`、`offline_guard.py`、现有枚举和 R4 输出格式。
- 正式入口放在现有 `backend/eval_042` package 内（建议 `python -m eval_042.cli`），不重命名 package、不另建第二套业务评测实现。
- 结果同时写本地 JSON 与 Markdown；真实 trace 的 score 仍回写 Langfuse，回写失败时本地报告不得丢失。
- `memory_correctness` 只接受带 `prior_context` 的 item；缺失时 `status=SKIPPED`、`skip_reason=no_prior_context`，不调用 judge、不写 score。
- 只允许 `http://127.0.0.1`、`http://localhost`、`http://[::1]`。显式禁用环境 proxy，首期拒绝任何 HTTP redirect；429、可重试 5xx、超时/连接瞬态错误只做有限次数与有限退避，所有尝试都先过 `offline_guard`，不引入新的限流体系。
- 评分结果保存非空 `score_id`，精确核验 `id`、`traceId`、`name`、预期 `value`；score 列表请求的 `limit` 不超过服务端上限 100，并把 requested/post/verified 状态写入报告。
- 真实 trace 数为 0 或输入数据集仅含 synthetic fixture 时失败；synthetic 只用于分类测试，不得掩盖空导出成功。
- Task04 只做后端旁路工具与测试；最终全量回归留 Spec042 收口。

## 明确不做

- 不新增主服务业务 API、UI、前端代码或 CI 门禁。
- 不修改业务对话链路、Langfuse 观测上报、采样率、路由/token 缺陷或部署配置。
- 不引入云端 judge、外网依赖、第二套 `openeval` package 或评分模型训练。
- 不建立真实人工标注平台，不把 Task03 的构造 gold 或自动判官结果写成 `human_agree_rate` 达标；报告固定保留人工真值未评估状态，真实人工标注列为后续工作。
- 不把 `SKIPPED`/`UNAVAILABLE` 静默转换为 0 分；不以 dry-run 代替真实 score 回写验收。
- 不允许默认 proxy、重定向、`file:`/`ftp:` 等非 HTTP scheme 或非 loopback host 参与任何请求；不新增全局限流/调度体系。

## 现有入口与缺口

| 现有资产 | 复用方式 | Task04 补齐项 |
|---|---|---|
| `docs/sdd/plans/042/task-02-run-eval.py` | 作为迁移基线与历史实测证据 | 主流程迁入 package；旧脚本不得保留独立实现。 |
| `backend/eval_042/langfuse_export.py` | trace 拉取、`EvalItem`、空/Intake 分类、Langfuse score API | `prior_context` 承载、`no_prior_context` 分类、有限传输重试、score ID/limit 精确契约、真实 trace 计数。 |
| `backend/eval_042/judge_client.py` | loopback Ollama、温度 0、R4 解析、枚举映射、可选 `ctx` | 有界瞬态重试与 runner 对 ctx/fallback 的统一调用。 |
| `backend/eval_042/offline_guard.py` | 所有请求前的 loopback 白名单 | 增加 HTTP scheme 校验，提供禁 proxy/拒绝 redirect 的统一 transport；新入口和 retry 路径不得绕过。 |
| Task03 结果 | 三段式 `{ctx}/{q}/{a}`、构造 gold 只作下界 | 真实缺 ctx 直接 skip，不伪造人工真值。 |

## 编码子任务（每项最多 2 个文件）

> 以下编码任务按顺序执行，避免多个 agent 同时改同一文件。所有生产代码任务派 `backend-dev`；测试任务单独派 `backend-tester`，不得由同一分派同时改代码和测试。模型采用本次用户临时指定的 Luna xhigh，不写入长期 agent 配置。

| 子任务 | 文件（最多 2 个） | 依赖 | 分派 | 状态 |
|---|---|---|---|---|
| 04-A 传输与数据契约 | `backend/eval_042/offline_guard.py`；`backend/eval_042/langfuse_export.py` | 无 | `Task(backend-dev)` | 已完成（独立GO；48项专项通过，POST不自动重试） |
| 04-B 判官与 runner 编排 | `backend/eval_042/judge_client.py`；`backend/eval_042/runner.py` | 04-A | `Task(backend-dev)` | 实现完成，独立复审及失败路径测试中 |
| 04-C CLI 迁移包装 | `backend/eval_042/cli.py`；`docs/sdd/plans/042/task-02-run-eval.py` | 04-B | `Task(backend-dev)` | 实现完成，独立复审中 |
| 04-D 报告投影 | `backend/eval_042/report.py`；`backend/eval_042/config.py` | 04-B | `Task(backend-dev)` | report模块已实现（无需修改config）；独立定向测试中 |
| 04-E 契约与失败回归测试 | `tests/evaluation/test_offline_transport.py`；`tests/evaluation/test_evaluation_runner.py` | 04-A–D | `Task(backend-tester)` | 进行中（传输48、报告14、原有28共90项通过；runner测试在编写） |

### 04-A 传输与数据契约

- 为 `EvalItem` 保留/补齐 `prior_context`（真实 trace 缺失时为 `None`）；memory 任务由统一分类函数产出 `SKIPPED/no_prior_context`。
- 在现有 `offline_guard` 接缝上提供统一 HTTP transport：只接受 HTTP loopback，显式禁用环境 proxy，首期拒绝任何 redirect；每次尝试前先调用 `assert_loopback`。
- 仅对 429、可重试 5xx、超时/连接瞬态错误做已有范围内的有限次数与有限退避；不得因重试绕过守卫，不得引入新的限流体系，不得对认证/参数/解析错误重试。
- `_get`/`_post` 固定使用服务端允许的 `limit<=100`；score POST 的非空 `id` 必须进入后续校验。
- `collect_eval_items`/dataset loader 分开记录 `real_trace_count` 与 `synthetic_count`；真实计数为 0 或仅 synthetic 时抛出可报告错误，测试 fixture 不得伪装真实导出。
- 保持 Langfuse public API、Basic auth、现有分页和 `post_score` 数据形状不变。

### 04-B 判官与 runner 编排

- 复用 `judge_one`/`judge_repeats` 的 R4 解析和枚举映射；对 `memory_correctness` 传入 `prior_context`，不从 q/a 猜上下文。
- 保留 primary `qwen3.5:9b`、fallback `qwen3.8:27b` 的既有配置与回退语义；每条结果记录 `judge_model`、原始错误、标签、理由和 `status`。
- 流程顺序固定为：加载/导出 → 分类（空/Intake/no_prior_context 先 skip）→ judge → 枚举转数值 → score 回写 → 查询验证。
- `SKIPPED` 不发 judge、不写 score；任一重复调用异常/解析失败即整条 `UNAVAILABLE`，不记 0、不用剩余标签偷偷写分；单条 write/verify 失败保留错误且使整体运行进入非零失败状态。
- score 验证必须按 `id==score_id`，并同时匹配 `traceId`、`name` 和预期 `value`（0.0–1.0 直接数值相等）；记录 requested/post/verified 三态和 mismatch 原因。

### 04-C CLI 迁移包装

- 提供稳定的 `python -m eval_042.cli` 入口，参数至少覆盖 dataset/导出模式、输出目录、task、primary/fallback、repeats 与必要的 item 上限。
- 将 docs 脚本中的流程迁入 package；旧脚本仅保留历史兼容薄包装或明确委托 CLI，禁止两处维护主流程。
- 在解析输入前初始化 JSON+Markdown 报告并写入 skeleton；每条 item 后 checkpoint，`finally` 更新最终状态。坏 JSON、顶层/条目 shape 错误、导出异常、loopback 违规、配置错误、judge `UNAVAILABLE`、score 写回失败或精确验证失败均返回非零；`SKIPPED` 不单独导致失败。
- 真实 trace 为 0 或 dataset 仅含 synthetic fixture 时报告错误并非零；不得用空数据集或“请求成功”冒充完成。

### 04-D 报告投影

- JSON 为机器可读权威产物，包含 schema/version、输入参数、运行时间、item 级状态、错误、score id、expected/verified value、汇总计数和退出原因。
- Markdown 从同一结果模型生成，至少展示 scored/skipped/unavailable/written/verified/failed 计数、`no_prior_context` 数量、失败明细和人工真值未评估声明。
- 报告写入失败本身返回非零并打印明确路径；报告不写入任何主服务或业务数据库。
- `human_agree_rate` 保持 `null`/未评估；构造 gold 只能标记 `constructed_gold`，不得出现“人工已达标”等表述。

### 04-E 契约与失败回归测试（与代码分开分派）

- `test_offline_transport.py`：验证非 HTTP/non-loopback 立即拒绝；环境 proxy 不生效；loopback 3xx redirect 直接拒绝；429/5xx/超时最多按上限重试；不可重试错误不重试；所有尝试先过 guard。
- `test_evaluation_runner.py`：验证空/Intake/no_prior_context 的 skip 语义、ctx 传递、任一重复失败即 UNAVAILABLE、不记 0、空真实导出失败、报告初始化/逐条 checkpoint/异常 finally、JSON+Markdown 落盘、失败非零、score ID/name/trace/value 精确匹配与不匹配分别通过和失败。
- 测试只使用 mock/fake transport，不依赖真实 Langfuse/Ollama；真实 API E2E 留验收评审，不能由 mock 冒充。

## 验收标准

| 编号 | 判据 | 证据 |
|---|---|---|
| A1 | `python -m eval_042.cli --help` 与最小离线命令可运行，入口不依赖 docs 路径注入 | 命令、退出码、入口路径 |
| A2 | Langfuse 不可达/空真实 trace/仅 synthetic/守卫拒绝时明确报错、非零、不生成成功空数据集 | 定向测试 + CLI 输出 |
| A3 | 空/Intake 与 memory 缺 ctx 均为 `SKIPPED`，分别保留原因；不调用 judge、不写 score | JSON item 记录、mock 断言 |
| A4 | 任一重复 judge 失败为 `UNAVAILABLE`，不记 0；受限重试不超过上限 | JSON、retry 测试 |
| A5 | 只有 HTTP loopback 请求；proxy 禁用、redirect 拒绝；429/5xx/超时有限重试，400/401/403/404/OfflineGuardError 不重试 | guard/transport 测试 |
| A6 | 成功与失败路径都落盘 JSON+Markdown，且初始化后/逐条 checkpoint；Markdown 与 JSON 汇总一致 | 文件路径、内容比对 |
| A7 | Langfuse score 回写后按 score ID 精确匹配 trace/name/value；任一 mismatch 或回写异常使退出码非零 | mock + 真实 smoke 证据 |
| A8 | 报告明确 `human_agree_rate` 未评估，构造 gold 不冒充人工真值 | JSON/Markdown 文本检查 |
| A9 | Task04 定向后端测试通过；真实 API E2E 跑通至少一条主链路后再交验收 | 测试命令/退出码、请求/响应/实体 ID/产物路径落盘 |

## 风险、回滚与收口

- 风险：Langfuse score 最终一致、Ollama 慢或限流、memory trace 缺 ctx、报告失败。统一以有限重试、明确状态和非零退出暴露，不扩大到业务链路。
- 回滚：删除/恢复 Task04 新增的 package CLI、runner、report、统一离线 transport 与测试；不触碰业务代码、Langfuse 数据或部署配置。真实 score 回写的清理仅按已授权的验收步骤执行，不在本 Task 自动删除业务数据。
- Task04 完成后回填本文件、plans README 和 Spec042 任务计划的状态与证据；Spec042 的最终全量回归、真实 API E2E、验收签字、部署和 `已完成` 状态留 Spec 收口阶段处理。

## 产出物与执行结果

- 计划产出：`backend/eval_042` canonical CLI/runner/report/统一离线 transport、迁移后的历史脚本包装、后端定向测试、JSON+Markdown 报告和真实 smoke 证据。
- 当前执行结果：尚未实现；本文件仅完成范围冻结与子任务拆分。不得将 Task02/03 的历史产物直接标记为 Task04 完成。
