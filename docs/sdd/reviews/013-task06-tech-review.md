# Spec 013 Task 06 技术评审：统计路径 A 最小补救方案

> 评审角色：开发主管（Tech Lead）
> 关联：spec-013、[`task-06-stats-native.md`](../plans/013/task-06-stats-native.md)、[`013-stats-native-review.md`](./013-stats-native-review.md)
> 评审范围：固定样本定义、未来时间戳隔离、Langfuse v4.27.0 六组原生 Dashboard 的可复现口径
> 评审方式：只读检查，未修改业务代码、配置或运行数据

## 结论

**有条件通过（Task 06 仍为部分完成/阻塞，不得标记完成）。**

底层指标上报已经足够支撑一组可复现的原生统计：`spans.py` 固定上报
`ttft_ms`、`load_ms`、`prompt_eval_ms`、`eval_ms`、`overhead_ms`、
`tokens_per_sec` 和 `is_cold_start` 七个 numeric score，并将输入/输出/思考字符数、
chunk 数及平均间隔写入 metadata。当前阻塞仅剩证据闭环：没有带版本号和样本标签的
固定样本，没有保存六组视图的筛选/聚合配置，也没有把异常未来时间记录从相对时间视图中隔离。

最小补救不需要扩展数据模型或修改业务埋点代码；应补一个可重复运行的样本生成与验收记录，
并把 Dashboard 配置按下述契约落盘。若原生 UI 不能表达某项统计，应明确标为 Task 07
自研视图输入，不用手工计算冒充原生 Dashboard。

## 只读证据

1. `docs/sdd/reviews/013-stats-native-review.md` 已确认 Langfuse v4.27.0 的
   `events_full/events_core` 和 numeric scores 可查询，但没有 Dashboard ID、导出配置或截图。
2. 同一报告发现一条 `event_ts` 位于 `2299-12-31` 的 direct/synthetic 样本；该样本会污染
   “最近 7/30 天”筛选，必须在视图查询中排除，而不是删除原始数据。
3. `backend/app/observability/spans.py:38-45` 固定了七个 score 名；
   `:102-119` 写入 `input_chars`、`output_chars`、`thinking_chars`、token 数、
   `chunk_count`、`avg_chunk_interval_ms`；`:176-184` 写入 `success`、`success_flag`
   和 `error_type`。
4. `derive_metrics()` 对耗时做非负截断，`overhead_ms` 在无原生 timings 时为 0，
   `is_cold_start` 由 `load_ms > cold_start_threshold_ms()` 判定。因此验收必须按
   `timings_available`、`is_cold_start` 和 `success` 分组，不能把 LangChain 样本与 direct
   样本混为一个性能结论。
5. Task 06 当前前置门禁要求冷/热、短/长、chat/KB 和失败样本，但任务执行结果尚未保存
   这些样本的固定标识及原生视图配置。

## 最小补救方案

### 1. 固定样本契约

每次样本运行生成一个不可变 `fixture_id`，建议格式
`spec013-task06-<UTC日期>-<短提交SHA>`，并在每条请求的 `extra_metadata` 中写入：

```json
{
  "fixture_id": "spec013-task06-20260903-294138c",
  "fixture_version": "v1",
  "sample_id": "cold-short-chat-01",
  "sample_class": "cold|hot|short|long|chat|kb|failure",
  "sample_expected_success": true,
  "sample_generated_at": "2026-09-03T11:00:00Z"
}
```

`sample_id` 使用固定矩阵而不是随机 UUID。最低矩阵如下：

| 类别 | 固定样本 | 最低数量 | 约束 |
|---|---|---:|---|
| cold / hot | 同一模型、同一 prompt，分别 5 条 | 各 5 | cold 前显式卸载模型；hot 在同一进程连续调用 |
| short / long | 同一模型、同一路由，分别 5 条 | 各 5 | prompt fixture 固定，长度边界写入记录 |
| chat / KB | 各一组正常请求 | 各 5 | `route`、`name`、`tags` 固定为协议值 |
| failure | 可控的无效模型或服务端错误 | 2 | 只验证错误率/错误类型，不进入成功耗时分位 |

同一请求可以属于多个标签，但 `sample_id` 必须唯一。样本正文不得写入验收报告；只记录
fixture 版本、长度、请求类别和哈希。重新生成样本时递增 `fixture_version`，禁止覆盖旧结果。
最低样本量是验收门槛，不代表可据此作长期性能结论。

### 2. 未来时间戳隔离

保留原始 `events_full`/`scores` 记录，避免破坏审计链；所有 Task 06 视图统一增加：

```sql
event_ts >= toDateTime64(now() - INTERVAL 30 DAY, 6)
AND event_ts <= toDateTime64(now(), 6)
```

若 Langfuse UI 只提供相对时间范围，则同时增加等价的 `event_ts <= now()` 过滤，并在配置
说明中写明“未来时间异常记录保留但不计入趋势”。固定样本验收另加：

```sql
metadata['fixture_id'] = 'spec013-task06-<fixture>'
AND metadata['fixture_version'] = 'v1'
```

对 ClickHouse 原生 `scores` 查询使用 `event_ts`；对 metadata 过滤时以 Langfuse UI
实际字段路径为准，若 UI 不支持 JSON 精确过滤，则用 `name/model/route` + 固定时间窗口，
并把 fixture ID 作为验收报告中的人工核对字段。禁止删除、回写或伪造时间戳。

### 3. 六组原生 Dashboard 配置契约

每组视图必须保存：Langfuse 版本、数据对象、固定筛选、时间范围、聚合/分位、分组维度、
单位、样本数量和独立 ClickHouse 对照查询。推荐配置如下：

| 视图 | 数据对象/筛选 | 聚合与分组 | 原生边界 |
|---|---|---|---|
| TTFT 分解、冷/热 | Scores；`name IN (ttft_ms,load_ms,prompt_eval_ms,eval_ms,overhead_ms)`、`success=true`、有效时间 | P50/P95/P99；按 `is_cold_start`、model、route | 只展示阶段分位，不伪造单次甘特图 |
| 延迟分位与慢请求 | Scores；目标 score、`success=true`、有效时间 | P50/P95/P99；按 observation name/model/route，另存 Top N 降序表 | P99 在小样本中只作链路校验 |
| 吞吐、输出长度、chunk 间隔 | Scores `tokens_per_sec` + Generations metadata `output_chars/avg_chunk_interval_ms`；成功且有效时间 | 平均/P50；按 model、route、sample_class | 若 UI 不能聚合 metadata，输出长度/间隔移交 Task 07 |
| 输入规模与延迟趋势 | Scores `ttft_ms` + metadata `input_chars`；成功且有效时间 | 按时间桶、model、route；记录桶宽 | 真散点/多维相关性不能由不支持散点的 UI 冒充 |
| 阶段构成占比 | Scores `load_ms/prompt_eval_ms/eval_ms/overhead_ms`；成功、`timings_available=true` | 平均或 P50；按 model、route、cold/hot | 占比计算若不能在 UI 中声明公式，移交 Task 07 |
| thinking、调用量、成功率、错误趋势 | Generations metadata `thinking_chars/success_flag/error_type`；有效时间 | 调用量 count、成功率 avg(success_flag)、错误按 error_type；按 name/model/route | `thinking_chars/(thinking_chars+output_chars)` 若不支持派生字段，移交 Task 07 |

“原生完成”的判定是：UI 中能保存上述对象、过滤、聚合和分组，并能由验收人员按配置
复现数值；不能只凭 ClickHouse SQL 有结果就宣称 Dashboard 已完成。每组至少保存一张
脱敏截图或可导出配置，截图不得包含 API Key、Cookie、token 或完整用户输入。

## 验收与停止条件

主 Agent 后续应按以下顺序执行：

1. 用固定 fixture 生成最低矩阵，确认每条事件带 `fixture_id/version/sample_id`。
2. 用有效时间条件重跑六组查询，并以 `events_full/events_core/scores` 为 v4 `events_only`
   的权威证据；旧 `traces/observations` 为空不作为失败理由。
3. 在 Langfuse v4.27.0 建立六组原生视图，保存配置/截图和独立查询结果到 Task 06 验收记录。
4. 对 UI 无法表达的 metadata 派生、真散点、阶段甘特图和复杂交叉筛选，记录为 Task 07
   输入，不扩张 Task 06 或擅自改业务埋点。
5. 任一固定样本缺失、未来时间仍进入趋势、视图无法按配置复现，Task 06 保持“部分完成”，
   不得进入 Task 08 收口。

## 结论与主 Agent 后续动作

- 结论：指标底座可用；Task 06 的剩余问题是可重复验收资料和时间过滤，不是 `spans.py`
  的必要代码缺陷。
- 主 Agent 必须先落盘固定样本生成/验收记录，再决定哪些能力移交 Task 07。
- 不删除异常事件、不修改已有 score，不在本评审中直接改业务代码。
- 完成上述证据后，由 tester 重新执行独立验证；tech-lead 再复核并签署 Task 06。

## 执行记录

- 开始时间：2026-09-03T19:53:07+0800
- 结束时间：2026-09-03T19:55:41+0800
- 总耗时：约 2 分 34 秒
- 读取文件：`docs/sdd/reviews/013-stats-native-review.md`、`docs/sdd/plans/013/task-06-stats-native.md`、`backend/app/observability/spans.py`
- 测试命令：只读 `sed`/`rg` 核对；退出码 0；未执行会改变状态的命令
- 模型：`qwen3.8:27b-mlx`
- token / 工具调用统计：运行环境未提供可靠 token 计数；1 组只读检查、1 次文档写入

