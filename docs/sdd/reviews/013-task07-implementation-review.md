# Spec-013 Task 07 实现技术评审

评审角色：Tech Lead  
评审日期：2026-09-03  
评审范围：Ollama Insights router、API root 注册、v2 `eventsObservationsView` 相关声明、页面及阶段/分布/散点组件。

## 结论：打回

查询路由和页面骨架已经接通，但当前统计结果存在口径错误，且页面筛选与部分验收能力没有形成可验证闭环。以下问题修复并完成验证后再复审。

## 评审意见

| 维度 | 判定 | 证据 |
|---|---|---|
| v2 events 查询与访问入口 | 部分通过 | `vendor/langfuse/web/src/server/api/root.ts:78-101` 注册了 `ollamaInsights`；`vendor/langfuse/web/src/features/ollama-insights/server/router.ts:200-207` 调用 `executeQuery(..., "v2")`，查询 view 为 `observations`。v2 声明在 `vendor/langfuse/packages/shared/src/features/query/dataModel.ts:1193-1344,1551-1620` 将字段映射到 `events_observations` 并从 metadata 提取专用指标。 |
| 项目/时间/type/future/limit | 基本通过 | router 固定 `type=GENERATION`，按 `start_time` 时间窗口查询，并加 `timestamp <= now()`；`protectedProjectProcedure` 负责项目级入口约束（`vendor/langfuse/web/src/features/ollama-insights/server/router.ts:72-127,200-207`）。输入 limit 限定为 1–100（同文件 `10-24`），结果映射对空值和非有限值有 null 降级（同文件 `46-65,180-197`）。 |
| 页面筛选绑定 | 部分通过 | 页面将 model、route、chainType、success 绑定至同一 list query，并实现清除（`vendor/langfuse/web/src/pages/project/[projectId]/ollama-insights/index.tsx:68-97,123-136`）。但 chainType 只在 data model 中读取 metadata 的 `chain_type`/`chainType`（`vendor/langfuse/packages/shared/src/features/query/dataModel.ts:1328-1344`），目标实现未能证明该字段有稳定值来源，页面上的该筛选可能长期为空；需补数据契约和正反向验证。 |
| 敏感数据 | 当前通过 | router 只选择 id/name、维度和聚合指标，不返回 input/output；页面也未渲染正文，model/route 等 React 文本插值不会作为 HTML 执行（`vendor/langfuse/web/src/features/ollama-insights/server/router.ts:136-163`；`vendor/langfuse/web/src/pages/project/[projectId]/ollama-insights/index.tsx:268-290`）。 |

## 必须修复项

1. **阶段时间线重复计算 TTFT。** 页面把 `load`、`prompt_eval`、`ttft`、`eval`、`overhead` 当作五个并列 duration，并在 `getTotalStageDuration` 中求和（`vendor/langfuse/web/src/pages/project/[projectId]/ollama-insights/index.tsx:33-56`）。`StageTimeline` 再按这些值计算比例（`vendor/langfuse/web/src/features/ollama-insights/components/StageTimeline.tsx:81-130`）。TTFT 是累计到首 token 的时间，不能在已有阶段 duration 之上再次作为独立段；当前列表 Total 和图形总时长会失真。应改为真实的 `first_token` 增量或累计标记，并以固定样本校验。
2. **冷/热分布不是全量且缺少验收指标。** list query 按 `avg_ttft desc`、`row_limit=100` 返回 rows（`vendor/langfuse/web/src/features/ollama-insights/server/router.ts:146-164`），页面将同一批 rows 直接传给分布组件（`vendor/langfuse/web/src/pages/project/[projectId]/ollama-insights/index.tsx:220-240`）。`LatencyDistribution` 只算 cold/hot 的 TTFT P50/P95/P99 和平均吞吐，未使用 load，也未按 model/route 分组（`vendor/langfuse/web/src/features/ollama-insights/components/LatencyDistribution.tsx:126-148,250-278`）。应提供独立聚合/明确抽样查询，并补 load 及 model/route 分组，不能把 Top-100 当作总体分布。
3. **散点统计同样被 Top-100 截断，且 auto 选择会丢点。** `InputLatencyScatter` 的 `auto` 只要任一行存在 TTFT 就全局选择 TTFT，只有 `total_ms` 的行会被排除（`vendor/langfuse/web/src/features/ollama-insights/components/InputLatencyScatter.tsx:59-64,80-93`）；页面又只传入上述受限 rows（`vendor/langfuse/web/src/pages/project/[projectId]/ollama-insights/index.tsx:231-240`）。应定义全量/抽样口径，提供明确 metric 选择或逐点回退，并补 mixed-metric 边界测试。
4. **非法数值在 API/列表层仍可泄漏。** `toNumberOrNull` 只检查 finite，不拒绝负数；v2 metadata 数值表达式也只是 `toFloat64OrNull`（`vendor/langfuse/web/src/features/ollama-insights/server/router.ts:46-50`；`vendor/langfuse/packages/shared/src/features/query/dataModel.ts:1181-1185`）。组件内部虽然清洗负数/非有限值，页面表格 `formatMilliseconds` 仍会直接显示负值（`vendor/langfuse/web/src/pages/project/[projectId]/ollama-insights/index.tsx:21-23,283-290`）。应按指标单位在服务端统一归一化/拒绝，确保图表和列表同一口径。
5. **链路类型与正文详情的验收闭环未完成。** 页面存在 chain type 输入和列（`vendor/langfuse/web/src/pages/project/[projectId]/ollama-insights/index.tsx:169-183,245-250`），但 query 只取声明的 metadata 字段，缺少可验证的数据契约；同时页面没有 spec 所需的 prompt 组成、thinking、正式输出折叠详情及截断/脱敏展示。需补稳定字段来源、详情接口的最小字段与脱敏测试；若不在本任务实现，应明确拆分而不能宣称完成。

## 测试缺口与构建阻塞

- 现有组件测试覆盖比例、0 值、空值、负数/非有限值、分位计算和 input fallback，但没有 router 级别的 SQL/字段别名、项目隔离、GENERATION、future、limit、success/chainType 过滤测试，也没有页面 query 参数绑定和 Top-N 统计口径测试。相关组件测试文件：`vendor/langfuse/web/src/features/ollama-insights/components/StageTimeline.test.tsx`、`vendor/langfuse/web/src/features/ollama-insights/components/LatencyDistribution.test.tsx`、`vendor/langfuse/web/src/features/ollama-insights/components/InputLatencyScatter.test.tsx`。
- 本次按只读评审要求未运行测试、类型检查或构建；因此不能签署构建/运行验收。必须在 vendor 依赖可用的环境补跑目标 Vitest、TypeScript、Prettier 和页面构建，并用固定样本逐项对照 observation。

## 建议项

- 在一次 router 请求中计算并复用同一个 effective `to`，避免两个并行 query 各自取当前时间造成边界漂移（`vendor/langfuse/web/src/features/ollama-insights/server/router.ts:67-74,160-176`）。
- 列表显示当前 rows 的采样/上限和 total 的关系，避免用户把总数误认为图表样本数。
- 继续保留 React 文本渲染的默认转义，并为未来详情字段增加凭据、环境变量和截断标记的回归测试。

## 风险定级：高

阶段时间线和分布统计在正常有数据时即可产生错误性能结论；同时构建和 router/page 验证尚未完成，当前不具备通过条件。
