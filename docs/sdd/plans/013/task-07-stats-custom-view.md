# 任务 07 — 统计路径 B：前端自研 Ollama 专用视图

> 关联：[spec-013](../../specs/013-llm-observability-platform.md) ｜ 索引：[README](./README.md)
> 依赖：任务 05，并以任务 06 的能力缺口为输入 ｜ 被依赖：任务 08 ｜ 当前状态：`实施中`

## 一句话目标

将 Langfuse v4.27 源码以固定版本导入项目内可追踪目录，再新增 Ollama 专用分析页，读取同一份 observation/score 数据，补齐原生 Dashboard 不擅长的单次阶段甘特图、散点关系和冷/热对比。

## 当前证据（2026-09-03）

- 项目仓库中尚未发现 `ollama-insights` 页面、查询路由或相关测试。
- 原始源码位于 `/Users/wjh/opt/langfuse-src/langfuse`，当前不是项目 Git 工作树；不得直接在该目录开发。
- 导入前清单：[`langfuse-v4.27-import-manifest.md`](./langfuse-v4.27-import-manifest.md)。
- 当前已具备任务 05 的真实 metadata/numeric score 数据，并已由任务 06 固定样本验证。
- 已导入 Langfuse v4.27.0 到 `vendor/langfuse/`；所有二次开发只在该项目内副本进行。

## 前置门禁

1. 任务 05 已产出稳定数据，任务 06 已明确原生 Dashboard 的真实缺口。
2. 固定 Langfuse 源码版本 `v4.27.0`、来源校验和项目内 vendor 基线 commit。
3. 将源码导入项目内约定目录（建议 `vendor/langfuse/`），导入前记录源目录校验、文件规模和回滚点；不覆盖现有用户修改。
4. 先确认 `events_core` / `events_full` 或 v4 对应查询接口的真实 schema，不从旧版文档猜字段。

## 页面范围

1. 调用列表：时间、模型、route、chat/KB、成功状态、TTFT、总耗时。
2. 单次详情：prompt 组成、thinking、正式输出和阶段耗时。
3. 阶段甘特图：load、prefill、first token、decode、overhead 使用同一时间轴展示，并明确服务端与客户端时间轴的差异。
4. 冷/热对比：按模型和 route 分组展示 TTFT/load 分布。
5. 输入规模散点：输入字符/token 与 TTFT/总耗时的关系。
6. 吞吐、耗时构成、思考占比和错误趋势。

不新增用户体系、告警、历史数据迁移，也不修改 Langfuse 通用 trace 页面。

## 实施步骤

### A. 查询层

1. 读取 v4.27.0 现有 tRPC/router 与 ClickHouse 查询实现，复用权限、项目隔离、时间过滤和分页。
2. 定义 Ollama 专用查询输入：项目、时间范围、模型、route、链路类型、冷/热、成功状态。
3. 从 observation metadata 与 score 读取指标；所有数值做空值、非有限值和单位校验。
4. 大结果集使用聚合查询和分页，不把完整 input/output 拉进统计列表。

### B. 页面层

5. 按 Langfuse 现有组件规范新增 `ollama-insights` 页面和导航入口。
6. 单次甘特图以明确比例尺绘制，0 值阶段保留标签，不出现负宽度。
7. 散点图和分位图支持 model/route 过滤；无数据、加载、错误状态均有明确提示。
8. 正文详情默认折叠，显示截断标记；不得暴露凭据或环境变量。

### C. 验证与比较

9. 用任务 06 的固定样本验证图表数值，抽样与原 observation 逐项对照。
10. 记录路径 A 与路径 B 在六项统计、维护成本、查询性能和可解释性上的差异。
11. 交付后由用户择优；在用户决定前两条路径均保留，不能提前删除其中一条。

## 子任务拆分与分派

Langfuse 源码改动预计超过三个文件，必须拆分：

1. 查询 schema/router：最多两个文件。
2. ClickHouse 查询与类型：最多两个文件。
3. 页面骨架与导航：最多两个文件。
4. 甘特图组件：单文件或组件+测试两个文件。
5. 散点/分位/趋势组件：每批最多两个文件。

每批代码先分派 `junior-dev`，架构师只做集成和读回；`tester` 使用固定数据独立核对。每次分派明确 Langfuse 源码绝对路径、基线 commit、目标文件和测试命令。

## 测试与验收标准

- 页面只查询当前项目数据，时间和模型过滤正确。
- 甘特图五个阶段的数值与 observation metadata 一致。
- 冷/热分组、P50/P95/P99、散点和吞吐结果与独立计算一致。
- 1,000 条及以上样本下页面无明显卡顿，列表使用分页/聚合。
- 无数据、缺字段、旧数据和查询失败不会导致白屏。
- Langfuse 原有页面和测试不回归。
- 给出路径 A/B 对比结论，但最终删除哪条路径由用户决定。

## 风险与回滚

- Langfuse 内部 schema/API 不是稳定扩展面，升级可能冲突；必须保留小型独立 commit 和补丁说明。
- 自研页面维护成本高，若任务 06 已满足需求，可在用户选择后放弃本路径。
- 回滚只撤销 Langfuse 源码分支中的页面/router/query commit，不删除已采集数据，也不影响项目后端埋点。

## 产出物

- Langfuse 源码侧 Ollama Insights 页面、查询接口和测试。
- 页面截图或运行记录。
- 路径 A/B 对比报告及用户择优入口。
- 本文档“执行结果”回填。

## 执行结果（2026-09-03：源码导入完成，页面开发中）

- Tech Lead 架构评审：[`docs/sdd/reviews/013-task07-architecture-review.md`](../../reviews/013-task07-architecture-review.md)。
- 结论：直接修改 `/Users/wjh/opt/langfuse-src/langfuse` 为 No-Go；改为先导入项目内 vendor 工作树，再按小批次二次开发。
- 已完成：源码导入到 `vendor/langfuse/`，版本 `4.27.0`，排除依赖/构建产物/运行时 `.env`；导入清单见 [`langfuse-v4.27-import-manifest.md`](./langfuse-v4.27-import-manifest.md)。
- 当前状态：页面/查询开发中；由于当前环境无法写入 `.git/index.lock`，vendor 基线 commit 尚未建立，需在可写 Git 环境补齐。

### 第一批：Insights tRPC Router（2026-09-03，junior-dev）

- 已新增 `vendor/langfuse/web/src/features/ollama-insights/server/router.ts`，并在 `web/src/server/api/root.ts` 注册 `ollamaInsights`。
- 当前 `list` 查询复用 v4 `observations` query abstraction，支持 project、时间范围、model、limit 与基础 latency/TTFT/吞吐字段；尚未猜测 events 表列名。
- `route`、`chainType`、`success` 及阶段 score 过滤在 shared query declaration 尚未正式暴露，当前显式返回 `BAD_REQUEST`，后续需先扩展 shared declaration。
- 验证：vendor 依赖未完整安装，`pnpm exec prettier --check` 因网络无法解析 npm registry 阻塞；未修改 lockfile。
- 代码改动仅限上述两个 vendor 文件，外部源码目录未修改。

### 第二批：events 查询字段与过滤（2026-09-03，junior-dev）

- 修改 `vendor/langfuse/packages/shared/src/features/query/dataModel.ts`：为 v2 `eventsObservationsView` 增加 `timestamp`、`startTime`、`route`、`chainType`、`success` 维度及 `ttft`、`load`、`prompt_eval`、`eval`、`overhead`、`tokens_per_sec`、`is_cold_start` 指标；metadata 从 `metadata_names/metadata_values` 提取，数值使用 `toFloat64OrNull`，布尔值保留三态。
- 修改 `vendor/langfuse/web/src/features/ollama-insights/server/router.ts`：启用上述过滤，固定 `type=GENERATION`，加入 `timestamp <= now()`，保持 project/time/limit 隔离。
- 验证：ClickHouse 表达式冒烟与字段/冲突标记静态检查通过；Prettier、TypeScript、Vitest 因 vendor 依赖未完整安装且 npm registry DNS 失败而阻塞，未修改 lockfile。
- 日志：`.codebuddy/agent-logs/junior-dev-013-task07-shared-fields.md`。

### 第三批：页面骨架与导航（2026-09-03，junior-dev）

- 新增 `vendor/langfuse/web/src/pages/project/[projectId]/ollama-insights/index.tsx`：复用 Langfuse `Page`、`Skeleton` 与 tRPC API，查询最近 24 小时数据，提供加载、错误、空态和时间/模型/route/链路类型/成功状态/TTFT/吞吐/冷启动表格。
- 修改 `vendor/langfuse/web/src/components/layouts/routes.tsx`：增加 Ollama Insights 入口，仅在 `v4WriteMode` 为 `events_only` 或 `dual` 时显示。
- 验证：冲突标记检查无冲突；新增文件无 whitespace 错误；`git diff --check` 仅命中既有无关的 `backend/app/services/ollama.py:138` EOF 空行。Prettier/TypeScript 因 vendor 依赖缺失及 npm registry DNS `ENOTFOUND` 阻塞。
- 日志：`.codebuddy/agent-logs/junior-dev-013-task07-page.md`。

### 第四批：阶段时间线与页面接线（2026-09-03，junior-dev）

- 新增 `vendor/langfuse/web/src/features/ollama-insights/components/StageTimeline.tsx` 及 `StageTimeline.test.tsx`：统一非负比例尺，0 值保留图例，null/负数/NaN/Infinity 安全处理，并提供可访问标签。
- 修改 `vendor/langfuse/web/src/pages/project/[projectId]/ollama-insights/index.tsx`：每条 generation 展开一行阶段时间线，复用 router 返回的 load、prompt_eval、ttft、eval、overhead 指标，不新增查询。
- 验证：组件与页面已读回；Vitest/TypeScript 因 vendor 依赖未完整安装而阻塞。
- 日志：`.codebuddy/agent-logs/junior-dev-013-task07-timeline.md`、`.codebuddy/agent-logs/junior-dev-013-task07-page-timeline.md`。

### 第五批：冷/热分布摘要与页面接线（2026-09-03，junior-dev）

- 新增 `vendor/langfuse/web/src/features/ollama-insights/components/LatencyDistribution.tsx` 与测试：按严格 cold/hot 分组，计算 TTFT P50/P95/P99 和平均吞吐；清洗 null、负数、NaN/Infinity，并显示缺失/空数据状态。
- 修改 `vendor/langfuse/web/src/pages/project/[projectId]/ollama-insights/index.tsx`：在列表上方接入分布摘要，复用既有 rows，不新增查询。
- 验证：目标文件冲突标记和 `git diff --check` 通过；Vitest/TypeScript/Prettier 因 vendor 依赖未安装而待补。
- 日志：`.codebuddy/agent-logs/junior-dev-013-task07-distribution.md`、`.codebuddy/agent-logs/junior-dev-013-task07-distribution-page.md`。

### 第六批：输入规模散点组件（2026-09-03，junior-dev）

- 新增 `vendor/langfuse/web/src/features/ollama-insights/components/InputLatencyScatter.tsx` 与测试：优先使用 `input_chars`，缺失时回退 `prompt_tokens`；显示 TTFT/总耗时的有限非负点，保留 0 值并清洗非法值，提供可访问点列表和空态。
- 当前组件等待查询层补充 `input_chars`、`prompt_tokens`、`total_ms` 字段后接入页面。
- 验证：冲突标记检查无匹配，`git diff --check` 通过；Vitest/TypeScript/Prettier 因 vendor 依赖缺失而待补。
- 日志：`.codebuddy/agent-logs/junior-dev-013-task07-scatter.md`。

### 第七批：输入规模字段查询（2026-09-03，junior-dev）

- 修改 `vendor/langfuse/packages/shared/src/features/query/dataModel.ts`：在 v2 events observation measures 增加 `input_chars`、`prompt_tokens`、`total_ms`，均通过 metadata 数值解析。
- 修改 `vendor/langfuse/web/src/features/ollama-insights/server/router.ts`：同步行类型、聚合指标和结果映射，保持 generation/project/time/future 过滤不变。
- 验证：目标文件冲突标记扫描与 `git diff --no-index --check` 通过；未执行网络或依赖命令。
- 日志：`.codebuddy/agent-logs/junior-dev-013-task07-scatter-fields.md`。

### 第八批：输入规模散点页面接线（2026-09-03，junior-dev）

- 修改 `vendor/langfuse/web/src/pages/project/[projectId]/ollama-insights/index.tsx`：在有数据状态中接入 `InputLatencyScatter`，传入 `input_chars`、`prompt_tokens`、`ttft`、`total_ms`、model、route；不新增查询或展示完整正文。
- 验证：目标文件冲突标记、`git diff --check` 和未跟踪文件 `git diff --no-index --check` 通过；Prettier/TypeScript 因 vendor 依赖缺失待补。
- 日志：`.codebuddy/agent-logs/junior-dev-013-task07-scatter-page.md`。

### 第九批：分布摘要 EOF 空白返修（2026-09-03，junior-dev）

- 返修 `LatencyDistribution.tsx` 与 `LatencyDistribution.test.tsx` 文件末尾多余空行。
- 验证：两文件 `git diff --no-index --check` 输出为空（仅因未跟踪文件与 `/dev/null` 存在正常内容差异而返回 1），无 whitespace 错误。
- 日志：`.codebuddy/agent-logs/junior-dev-013-task07-distribution.md`。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师（自身） | 确认自研视图尚无代码产物，补齐任务计划，状态为待执行 |
