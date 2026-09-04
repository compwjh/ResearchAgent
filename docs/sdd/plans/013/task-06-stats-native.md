# 任务 06 — 统计路径 A：原生 Dashboard + numeric score

> 关联：[spec-013](../../specs/013-llm-observability-platform.md) ｜ 索引：[README](./README.md)
> 依赖：任务 05 ｜ 被依赖：任务 08 ｜ 当前状态：`待执行（底层指标函数已具备）`

## 一句话目标

仅使用 Langfuse 原生 observation、score、filter 和 Dashboard 能力，搭出可复现的性能统计看板，覆盖 spec 约定的六项统计，并验证真实数据能够实时写入和聚合。

## 当前证据（2026-09-03）

- `backend/app/observability/spans.py` 已定义 `SCORE_METRICS`，包含 TTFT、load、prefill、eval、overhead、吞吐与冷启动标记。
- 指标派生和 score 上报已有单元测试。
- 任务 05 尚未接入真实业务，因此目前没有来自聊天/KB 主链路的稳定观测数据。
- 尚无原生 Dashboard 配置、截图、查询口径或六项统计验收记录。
- 本任务只能视为“基础函数具备”，不能标记完成。

## 前置门禁

1. 任务 05 已能稳定产生聊天和 KB trace。
2. Langfuse Web/worker/基础设施处于健康状态。
3. 已固定一组冷调用、热调用、短输入、长输入和失败请求样本。
4. score 名称、单位和 route/model/tag 维度在技术评审后冻结，避免看板建成后反复迁移。

## 指标口径

| 指标 | 单位/类型 | 来源 | 用途 |
|---|---|---|---|
| `ttft_ms` | ms | 客户端首个内容片段 | 首 token 分位、慢请求 |
| `load_ms` | ms | Ollama `load_duration` | 冷/热与加载瓶颈 |
| `prompt_eval_ms` | ms | Ollama `prompt_eval_duration` | 输入预填充 |
| `eval_ms` | ms | Ollama `eval_duration` | 解码耗时 |
| `overhead_ms` | ms | `max(client_wall-total, 0)` | 网络与框架开销 |
| `tokens_per_sec` | token/s | completion tokens / eval | 生成吞吐 |
| `is_cold_start` | 0/1 | load 阈值判定 | 冷/热分组 |
| `input_chars` / `output_chars` / `thinking_chars` | 字符数 | 截断前长度 | 规模相关性和思考占比 |
| `success` / `error_type` | 布尔/枚举 | 调用结果 | 成功率和错误趋势 |

若当前底层尚未记录后三组字段，应在任务 05 范围内补齐最小 metadata/score，而不是在 Dashboard 中用不可复现的手工计算代替。

## 实施步骤

1. 用固定脚本产生至少以下样本：同模型冷/热各 5 次、短/长输入各 5 次、聊天/KB 各 5 次、失败请求至少 2 次。
2. 在 Langfuse 中确认 observation 与 numeric score 实时可见，SDK 写入延迟满足本地使用需求。
3. 建立六组原生视图：
   - TTFT 分解与冷/热对比
   - P50/P95/P99 与慢请求排行
   - token/s、输出长度与单段间隔
   - 输入规模与延迟趋势
   - load/prefill/eval/overhead 构成占比
   - thinking 占比、调用量、成功率和错误率趋势
4. 为每个视图记录筛选条件、聚合方式、时间范围、route/model 分组和单位。
5. 检查原生 Dashboard 无法表达的统计：真散点、单次阶段甘特图、复杂冷/热交叉对比等，明确列入任务 07，不在本任务伪造。
6. 导出或截图关键视图，记录到验收文档；不得把 API Key 或用户输入正文写入截图说明。

## 子代理分派

- `tester`：根据固定样本核对 score 数值、分位数和筛选口径，产出独立验证记录。
- `tech-lead`：审查指标口径是否能支撑六项统计，以及路径 A 的已知缺口是否如实记录。
- 如发现缺少必要字段，代码改动必须退回 `junior-dev` 窄任务；本任务执行者不直接扩张 Task 05 范围。

## 验收标准

- 六项统计均有真实样本、明确口径和可重复筛选步骤。
- route、model、chat/KB、cold/hot 可以分组或过滤。
- P50/P95/P99 与独立计算结果在合理精度内一致。
- `LANGFUSE_ENABLED=false` 的请求不出现在看板。
- 失败请求不会污染成功耗时分位，错误率仍可单独统计。
- 明确列出路径 A 无法满足的功能，并作为任务 07 的输入。

## 风险与回滚

- 原生 Dashboard 能力随 Langfuse 版本变化；必须记录版本 `v4.27.0` 和具体配置步骤。
- 少量样本的 P99 没有统计意义；验收只验证计算链路，长期结论需积累更多数据。
- 删除 Dashboard 不影响原始 observation 数据；路径 A 可独立回滚。

## 产出物

- 原生 Dashboard 配置与六项统计验证记录。
- 固定样本生成命令和独立计算结果。
- 路径 A 能力/缺口清单，供任务 07 和最终择优使用。
- 本文档“执行结果”回填。

## 执行结果（2026-09-03：完成）

- Tester 复核报告：[`docs/sdd/reviews/013-stats-native-review.md`](../../reviews/013-stats-native-review.md)。真实数据包含 20 条 generation、140 条 numeric score，七项指标均可核对；成功 16/20、失败 4/20。
- Tech Lead 口径报告：[`docs/sdd/reviews/013-task06-tech-review.md`](../../reviews/013-task06-tech-review.md)。建议固定样本使用 `fixture_id`/`sample_id`/`fixture_version` 元数据，所有趋势筛选统一增加 `event_ts <= now()`，以隔离测试产生的未来时间戳。
- 固定样本脚本：`scripts/generate_observability_fixtures.py --send --fixture-id spec013-task06-fixed-20260903`；20 条样本覆盖冷/热、短/长、chat/KB、成功/失败，摘要保存在 `/tmp/spec013-task06-send.json`。
- 实测：`events_full` 中 fixture 样本 20 条，`event_ts > now()` 为 0；七项 score 均可查询。所有 Dashboard 查询统一过滤 `event_ts <= now()` 与 `metadata_names/metadata_values` 中的 `fixture_version=v1`。
- 原生 Dashboard 配置（Langfuse v4.27.0）：
  1. **TTFT 冷/热**：observation type=`GENERATION`；过滤 `event_ts <= now()`；按 `provided_model_name`、`metadata route`、`metadata temperature` 分组；聚合 `ttft_ms` 的 P50/P95/P99。
  2. **慢请求排行**：同上；按 `ttft_ms` 或 `total_ms` 降序，Top 20；排除 `success_flag=0` 后单独建失败视图。
  3. **吞吐与长度**：按 model/route 分组，展示 `tokens_per_sec`、`output_chars`、`avg_chunk_interval_ms` 的均值/分位。
  4. **输入规模趋势**：时间范围 + `input_chars`、`prompt_tokens` 与 `ttft_ms`/`total_ms` 的聚合趋势；列表仅取 metadata，不拉取正文。
  5. **耗时构成**：同一筛选下分别聚合 `load_ms`、`prompt_eval_ms`、`eval_ms`、`overhead_ms`，单位 ms；缺失值按 0。
  6. **思考/成功率趋势**：`thinking_chars / output_chars` 作为思考占比；`success_flag` 均值作为成功率，失败按 `error_type` 分组。
- 路径 A 缺口：真散点、单次阶段甘特图和复杂交叉过滤需 Task 07；不在原生 Dashboard 中伪造。
- 结论：固定样本、指标核对和可复现配置完成，Task 06 验收通过；Task 07 继续承担可视化缺口。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师（自身） | 确认仅有底层 score 函数，尚无真实 Dashboard，补齐任务计划 |
