# Spec042 技术评审：离线评测交付续作

- 评审对象：`docs/sdd/specs/042-openeval-agent-evaluation.md`、`docs/sdd/plans/042/task-04-offline-evaluation-delivery.md`（本评审同时冻结其技术前提）
- 评审者：architect 子代理（当前任务）
- 评审角色：架构师／独立技术评审
- 评审模型：Luna xhigh（本次临时指派，不写入长期配置）
- 分派方式：`Task(architect)`
- 评审时间：2026-10-23（Asia/Shanghai）
- 评审范围：`backend/eval_042` 现有模块、Task02 实验入口、Task03 记忆上下文契约；只读，不改代码、API、部署或 Git
- 续作审查依据：`docs/sdd/plans/042/continuation-audit.md`（backend-reviewer 只读缺口审查）

## 结论：有条件通过

技术路线正确且可以在现有 `backend/eval_042` 模块上收敛，不需要引入第二套评测 package。放行条件是 Task04 按本报告的 T1–T8 冻结契约实现并由后端代码与后端测试分别分派；在这些条件完成前，不能把现有 docs 脚本称为正式 CLI，也不能把已有一次性 score 回写实测当作可复用交付。

## 现有实现事实

| 接缝 | 当前事实 | 对 Task04 的含义 |
|---|---|---|
| 数据导出 | `langfuse_export.py:23-40` 已在每次 GET/POST 前调用 `assert_loopback`；`collect_eval_items` 在 `:168-214` 拉取 trace、抽取 input/output、区分 synthetic Intake。当前空真实 trace 仍可被 fixture 填满。 | 复用该模块；补 `prior_context` 字段/缺失跳过、真实 trace 计数和有限传输重试；空真实导出必须失败，不另建 exporter。 |
| 判官 | `judge_client.py:62-78` 直连 Ollama、温度 0；`:81-117` 已有可选 `ctx` 和 R4 解析，但异常直接变成 `unavailable`，没有有限重试策略。 | 保持 R4/枚举映射；在 loopback 守卫后加有界瞬态重试，失败仍是 `UNAVAILABLE`。 |
| 离线守卫 | `offline_guard.py:17-28` 只允许 `127.0.0.1`、`localhost`、`::1`，但当前 `urlopen` 仍可能读取 proxy 并跟随 redirect。 | 所有新 HTTP 路径必须复用安全 transport：禁 proxy、拒绝 redirect、拒绝非 HTTP scheme，不能由 CLI 绕过。 |
| 实验 runner | `task-02-run-eval.py:43-68` 只跑 primary、只传 q/a、直接回写；`:71-101` 只验证 trace/name 且传入 `limit=200`；`:136-150` 只在末尾产 JSON。 | 将编排迁移到 package；补 fallback/ctx、先写报告+checkpoint、Markdown、错误退出、score ID/name/trace/value 精确验证，并把 limit 固定在服务端上限内。 |
| 记忆探针 | Task03 报告确认 `{ctx}/{q}/{a}`、`no_prior_context` 前置是必要契约，构造 gold 不是人工标注。 | 真实 trace 缺上下文必须跳过，不猜测、不生成人工真值。 |

## 技术核对矩阵

| 技术点 | 判定 | 必须固化的契约 |
|---|---|---|
| package 复用 | 通过（条件） | 保留 `config`、`langfuse_export`、`judge_client`、`offline_guard`；新增最小 `cli`/runner/report 模块即可，不重命名 `eval_042`，不复制业务 API 或新增限流体系。 |
| CLI 入口 | 必须修复 T1 | canonical 入口为 `python -m eval_042.cli`（从 `backend` 运行）；可接受显式 dataset/output 参数；docs 脚本保留为历史证据或薄包装，不再含第二套编排逻辑。 |
| 数据模型与跳过 | 必须修复 T2 | `EvalItem` 传递 `prior_context`；memory 任务在 judge 前检查非空，缺失输出 `SKIPPED/no_prior_context`，不调用 Ollama、不回写 score。 |
| retry 与离线 | 必须修复 T3 | 每次尝试前调用 `assert_loopback`；只对 429、可重试 5xx、超时/连接瞬态错误做已有范围内的有限重试；禁用环境 proxy、拒绝任何 redirect、拒绝非 HTTP scheme；400/401/403/404、解析错误和 `OfflineGuardError` 立即失败。 |
| 状态与退出码 | 必须修复 T4 | 报告初始化后立即写盘并逐条 checkpoint；fatal 导出/配置/守卫错误、坏 JSON/shape、任一重复 judge 失败、任何写回失败或精确校验失败均使 CLI 返回非零；`SKIPPED` 不是失败。 |
| 空导出语义 | 必须修复 T5 | `real_trace_count==0` 或仅 synthetic fixture 时失败；synthetic 只用于分类测试，不得让空真实导出返回成功。 |
| JSON/Markdown 报告 | 必须修复 T6 | JSON 保存 schema/version、参数、每条结果、错误、计数和 score verification；Markdown 从同一结果模型生成，坏输入/中途异常也必须存在；人工一致率保持 null/未评估。 |
| score 精确校验 | 必须修复 T7 | 保存非空 `score_id`，回查按 `id==score_id`，并同时匹配 `traceId`、`name` 和预期 `value`（0.0–1.0，直接数值相等，不用模糊阈值）；`list_scores` 的 limit 不超过 100；记录 requested/post/verified 三态。 |
| 测试与收口 | 必须修复 T8 | 后端代码子任务与测试子任务分开分派；每个编码子任务最多 2 个文件；测试放 `tests/evaluation/` 并按能力命名；Task04 只跑后端定向测试和真实 smoke，最终全量回归留到 Spec042 收口。 |

## 推荐实现切分（不超出 Task04）

1. **数据/传输层**：在现有 exporter 中加入 `prior_context` 数据承载和 `no_prior_context` 分类；新增一个小型 retry seam，统一复用 loopback 守卫，保持 Langfuse public API 与 Ollama API 不变。
2. **判官/编排层**：复用 `judge_repeats`、枚举映射和已有 primary/fallback 配置；runner 先分类再评分，按 `ctx` 调用 memory judge，按有限回退链处理结果，不修改业务观测链路。
3. **报告/CLI 层**：新增 package CLI 与报告投影；从同一结果模型写 JSON 与 Markdown。`task-02-run-eval.py` 不得继续保留一份独立的主流程。
4. **测试层**：纯函数测试 skip/ctx/score 映射；网络 mock 测试 retry 次数、非 loopback 拒绝、429/5xx 处理；runner/CLI 测试失败非零、报告仍落盘、精确 value 校验。测试任务不得修改生产代码。
5. **离线 transport 细节**：统一使用显式禁用 proxy 的 opener；首期直接拒绝 3xx redirect（不跟随，也不做跨跳放行）；`assert_loopback` 同时拒绝非 HTTP scheme 和非白名单 host。不得通过全局 monkey-patch 或新增限流体系绕过文件边界。

## 风险与处置

| 风险 | 等级 | 处置 |
|---|---|---|
| Langfuse 最终一致导致误判 | 中 | 写回后只按有限次数查询；仍未精确匹配则报告失败并非零，不把“写请求成功”冒充验收成功。 |
| 某条 judge 不可用 | 中 | 保存原始错误与 `UNAVAILABLE`；按约定返回非零，禁止回填 0。 |
| memory trace 缺上下文 | 高 | `no_prior_context` 早期跳过；不从普通 input/output 推断 prior context。 |
| 429/5xx 重试放大本机压力 | 中 | 仅在既有范围内做有限尝试/退避；不引入新的限流体系、不做无限轮询或跨 host fallback。 |
| 构造 gold 被误读为人工真值 | 高 | 报告固定显示 `human_agree_rate=null` 与“constructed gold only”；人工标注列为后续，不在 Task04 引入平台。 |
| proxy/redirect 出口 | 高 | 使用禁 proxy、拒绝 redirect、仅 HTTP loopback 的统一 transport，并用 mock 覆盖环境 proxy 与外部 Location。 |
| synthetic 掩盖空导出 | 高 | 单独记录 `real_trace_count`/`synthetic_count`；真实计数为 0 时报告失败、退出非零。 |

## 评审边界

本技术评审不授权改业务 API、UI、CI、Langfuse 部署配置或人工标注系统；不把旧脚本一次性实测提升为已完成的 Spec 验收。Task04 完成后仍需真实 API E2E、验收评审签字、状态台账和 Spec 收口全量回归。

## 签字

- 评审人：architect 子代理（当前任务）
- 日期：2026-10-23
- 结论：有条件通过（T1–T8 完成并通过定向验证后，方可进入验收门禁）
