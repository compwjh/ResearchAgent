# Spec 013 Task 06 独立验证：统计路径 A（原生 Dashboard + numeric score）

> 评审角色：测试（子代理 tester，模型 `qwen3.5:9b`）
> 关联：spec-013、`docs/sdd/plans/013/task-06-stats-native.md`
> 范围：只读核对 Langfuse v4.27.0 本地事件、numeric score、metadata 和指标派生逻辑

## 结论：不通过（部分完成，固定样本与 Dashboard 证据不足）

当前数据证明 events_only 写入及 numeric score 链路可用，但不能证明 Task 06 的六项原生 Dashboard 统计已完成。建议保留 Task 06 为“部分完成/阻塞”，补齐固定样本、原生 Dashboard 配置记录和时间异常处理后再验收。

## 运行环境与数据范围

| 项 | 实测 |
|---|---|
| Langfuse | v4.27.0（本地） |
| ClickHouse | 26.4.6.3，HTTP 8123 |
| `events_full` | 43 行 |
| `events_core` | 43 行 |
| generation | 20 行（`type='GENERATION'`、`is_deleted=0`） |
| numeric score | 140 行，即 20 条 generation × 7 个指标 |
| `observations` / `traces` | 0 / 0；当前 events_only 口径下不作为失败证据 |

## 代码与数据证据

1. `backend/app/observability/spans.py:37-46` 定义 7 个 score：`ttft_ms`、`load_ms`、`prompt_eval_ms`、`eval_ms`、`overhead_ms`、`tokens_per_sec`、`is_cold_start`。
2. `backend/app/observability/spans.py:68-94`：
   - 所有耗时取非负值；
   - 无原生 timings 时 `overhead_ms=0`；
   - `tokens_per_sec=completion_tokens/(eval_ms/1000)`，eval 为 0 时为 0；
   - `is_cold_start` 使用 `load_ms > cold_start_threshold_ms()`。
3. `backend/app/observability/spans.py:109-128` 将 `input_chars`、`output_chars`、`thinking_chars`、token 数、阶段指标写入 metadata。
4. `backend/app/observability/spans.py:181-184` 写入 `success`、`success_flag`、`error_type`，因此成功率和错误率可按 metadata 复算。
5. `events_full` 实际可见 `kb.embedding`、`kb.retrieval`、`kb.rerank` 和 `kb.generation`，metadata 中包含 `route`、`model`、字符数、成功状态及阶段指标。

## 实际 generation 统计

| name / model / route | 样本 | 成功 | 失败 | TTFT P50 | TTFT P95 | 平均输入字符 | 平均输出字符 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `kb.generation` / `qwen3.5:9b` / `langchain` | 5 | 5 | 0 | 1.244 ms | 70820.759 ms | 714.6 | 141.4 |
| `ollama-chat` / `qwen3.5:9b` / `langchain` | 8 | 8 | 0 | 0.701 ms | 17415.115 ms | 21.5 | 14.0 |
| `ollama-chat` / `m1` / `langchain` | 6 | 3 | 3 | 0.018 ms | 0.025 ms | 436.2 | 1.0 |

全体成功 16/20（80%），失败 4/20（20%）。失败 `error_type` 实际包含 `ResponseError` 与 `RuntimeError`。失败样本不能进入成功耗时分位，原生 Dashboard 需用 `success=true` 过滤。

## Numeric score 聚合证据

直接对 `scores` 执行 `data_type='NUMERIC' AND is_deleted=0` 的聚合结果：

| score | n | P50 | P95 | P99 | min | max |
|---|---:|---:|---:|---:|---:|---:|
| `ttft_ms` | 20 | 0.629 | 70820.759 | 70820.759 | 0 | 70820.759 |
| `load_ms` | 20 | 0 | 10.658 | 10.658 | 0 | 10.658 |
| `prompt_eval_ms` | 20 | 0 | 183.660 | 183.660 | 0 | 183.660 |
| `eval_ms` | 20 | 0 | 5588.254 | 5588.254 | 0 | 5588.254 |
| `overhead_ms` | 20 | 0 | 47.145 | 47.145 | 0 | 47.145 |
| `tokens_per_sec` | 20 | 0 | 41.516 | 41.516 | 0 | 41.516 |
| `is_cold_start` | 20 | 0 | 0 | 0 | 0 | 0 |

其中一条 direct/synthetic 数据的 score `event_ts` 落在 `2299-12-31`，这会污染“最近 7/30 天”类时间筛选，必须在后续样本生成或数据清理策略中明确排除；报告不据此伪造长期趋势结论。

## 可复现查询与筛选口径

基础查询（不含凭据）：

```bash
curl -sS -u 'langfuse:<password>' --data-binary \
  $'SELECT name,value,data_type,trace_id,observation_id,event_ts,is_deleted FROM scores WHERE data_type=\'NUMERIC\' AND is_deleted=0 FORMAT JSONEachRow' \
  http://127.0.0.1:8123/
```

建议在 Langfuse v4.27 原生视图中固定：

- 数据对象：Observations / Generations 与 Scores；不要依赖空的旧 `traces`/`observations` 表。
- score 名：每个视图只选一个指标；单位按 score 名后缀解释（ms、token/s、0/1）。
- 成功耗时：metadata `success=true`；错误率：`success_flag` 或 `success=false`；错误拆分：`error_type`。
- 分组维度：observation name（`ollama-chat` / `kb.generation`）、model、route，以及 tag `kb`；阶段 score 按 model/route 分组。
- 时间范围：使用事件实际时间；排除未来时间异常记录。
- 分位：P50/P95/P99；慢请求排行按 `ttft_ms` 或目标 score 降序。

这些是可复现的筛选口径；本次没有发现已保存的 Dashboard ID、导出配置或截图，因此不能声称原生看板已建立。

## 六项统计能力判定

| 统计项 | 状态 | 依据与缺口 |
|---|---|---|
| TTFT 分解、冷/热对比 | 风险 | score/metadata 存在；当前 `is_cold_start` 全为 0，缺少冷/热各 5 次样本 |
| P50/P95/P99、慢请求排行 | 部分通过 | ClickHouse 可复算；20 条样本且含未来时间异常，不能作为稳定趋势 |
| token/s、输出长度、chunk 间隔 | 风险 | token/s 与 output_chars 存在；原生 score 没有 output length/chunk interval，需 metadata 过滤/导出，Dashboard 能力未实证 |
| 输入规模与延迟趋势 | 风险 | input_chars 存在；未建立并保存散点/趋势 Dashboard，原生交叉表达能力未验证 |
| 阶段构成占比 | 部分通过 | load/prompt_eval/eval/overhead score 存在；真实非零 direct 样本过少，无法验证分组趋势 |
| thinking 占比、调用量、成功率、错误趋势 | 风险 | thinking_chars、success、error_type metadata 存在；未有 thinking 非空样本，也没有已保存原生 Dashboard |

## 路径 A 已知缺口（交给 Task 07）

- 原生 Dashboard 是否支持 `input_chars` 对 TTFT 的真正散点图及多维交叉筛选，当前没有实测配置证据。
- 单次调用的 `load → prefill → first_token → decode → overhead` 精确甘特图无法由 numeric score 直接表达；应由 Task 07 读取 metadata 渲染。
- thinking 占比需要 `thinking_chars / (thinking_chars + output_chars)` 的派生表达；当前只有原始 metadata，未验证原生 Dashboard 能否计算。
- chat/KB 统一 trace、route/model/tag 组合筛选需补充固定样本并保存配置。

## 风险、阻塞与主 Agent 后续动作

- 阻塞 1：未达到 Task 06 规定的冷/热、短/长、chat/KB、失败固定样本量。
- 阻塞 2：没有原生 Dashboard 配置、截图或可导出查询定义，无法复现六组视图。
- 风险 3：未来时间戳样本会污染相对时间筛选和趋势图。
- 风险 4：`events_only` 下 `traces/observations` 为空，后续文档必须固定以 `events_full/events_core/scores` 为证据。

主 Agent 应：

1. 记录本报告为 Task 06 独立验证结果，保持“不通过/部分完成”；
2. 生成满足门槛的固定样本并排除未来时间记录；
3. 在 Langfuse v4.27 保存六组原生视图的筛选、聚合、时间范围、分组和单位；
4. 将本报告中的路径 A 缺口传给 Task 07；
5. 不因 numeric score 已写入而直接将 Task 06 标记完成。

## 测试命令、退出码与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `curl ... SELECT version(), currentDatabase()` | 0 | ClickHouse `26.4.6.3`, `default` |
| `curl ... SHOW TABLES` | 0 | events、scores 等 v4 表存在 |
| `curl ... SELECT count() FROM <table>` | 0 | 获得上述行数 |
| `curl ... SELECT ... FROM events_full ... FORMAT JSONEachRow` | 0 | 核对 20 条 generation metadata |
| `curl ... SELECT ... FROM scores ... GROUP BY name` | 0 | 核对 7 项 score 的 n/P50/P95/P99 |

## 产物与执行记录

- 报告：`docs/sdd/reviews/013-stats-native-review.md`
- 进展日志：`.codebuddy/agent-logs/tester-013-task06.md`
- 开始时间：2026-09-03（本轮任务开始后）
- 结束时间：2026-09-03（报告写入后）
- 总耗时：约 10 分钟
- 模型：`qwen3.5:9b`
- token / 工具调用统计：运行环境未提供可靠的 token 计数；执行 5 组只读 shell 查询与 2 次文档写入操作

