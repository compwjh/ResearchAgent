# Spec 013 Task 07 架构评审：统计路径 B

> 评审角色：Tech Lead（子代理）
> 关联任务：`docs/sdd/plans/013/task-07-stats-custom-view.md`
> 关联评审：`docs/sdd/reviews/013-stats-native-review.md`
> 评审范围：只读检查 Langfuse v4.27.0 的 tRPC、Dashboard 查询、页面和导航结构；不修改 Langfuse 源码。

## 结论

结论：**外部目录直接修改为 No-Go；项目内 vendor 导入后可进入二次开发。**

Langfuse v4.27.0 的扩展点是可识别的：项目级 tRPC 总路由在
`/Users/wjh/opt/langfuse-src/langfuse/web/src/server/api/root.ts`，已有 Dashboard 查询和项目权限封装在
`/Users/wjh/opt/langfuse-src/langfuse/web/src/features/dashboard/server/dashboard-router.ts`，项目页面位于
`/Users/wjh/opt/langfuse-src/langfuse/web/src/pages/project/[projectId]/`，全局导航由
`/Users/wjh/opt/langfuse-src/langfuse/web/src/components/layouts/routes.tsx` 的 `ROUTES` 驱动。

但 `/Users/wjh/opt/langfuse-src/langfuse` 当前不是可用 Git 工作树（只读执行 `git log` 返回 `fatal: not a git repository`）。因此不能直接在外部目录开发。当前已按用户确认导入 `vendor/langfuse/`，版本固定为 `4.27.0`，排除了依赖、构建产物和运行时 `.env`；后续修改仅在 vendor 目录进行。

## 已核对的结构与复用点

### 查询层

- `web/src/server/api/root.ts` 已注册 `dashboard`、`observations`、`scores`、`events` 和 `scoreAnalytics` router。
- `web/src/features/dashboard/server/dashboard-router.ts` 的 `executeQuery` 使用 `protectedProjectProcedure`，并调用 `executeQuery(projectId, query, "v2")`；这提供项目隔离、权限和 v4 query view 复用点。
- `web/src/features/dashboard/server/dashboard-router.ts` 已有 `scores-numeric` / `scores-categorical` 的过滤、时间边界、聚合和空值处理，但其结果适合聚合看板，不适合单次阶段甘特图。
- `web/src/features/chart-view/lib/buildChartQuery.ts` 复用 `QueryType`、`executeQuery` 的 view/metric/dimension/filter 约定，可作为图表查询的输入形状参考。
- `web/src/server/api/routers/observations.ts` 的 `byId` 面向单次详情且允许 `compact`、`truncated`、`full`，不应在调用列表中批量拉取完整 input/output。

### 页面与导航层

- 已有页面：`web/src/pages/project/[projectId]/dashboards/index.tsx`、`dashboards/[dashboardId]/index.tsx` 和 `scores/analytics.tsx`。
- 现有图表组件集中在 `web/src/features/dashboard/components/`；页面公共壳为 `Page`。
- 导航只需在 `web/src/components/layouts/routes.tsx` 的 `ROUTES` 增加项目路径；`useFilteredNavigation.ts` 会依据项目上下文、RBAC、feature flag 和 product module 生成侧栏项目。
- 页面标签工具位于 `web/src/features/navigation/utils/`，例如 `dashboard-tabs.ts` 和 `scores-tabs.ts`。

## 推荐 Go/No-Go

### 直接修改 Langfuse 源码：No-Go

在外部源码目录建立 Git 基线、确认 v4.27.0 commit、记录独立分支和启动方式之前，不得分派编码任务，也不得直接修改以下文件：

- `/Users/wjh/opt/langfuse-src/langfuse/web/src/server/api/root.ts`
- `/Users/wjh/opt/langfuse-src/langfuse/web/src/features/dashboard/server/dashboard-router.ts`
- `/Users/wjh/opt/langfuse-src/langfuse/web/src/components/layouts/routes.tsx`
- `/Users/wjh/opt/langfuse-src/langfuse/web/src/pages/project/[projectId]/...`

若用户仍选择路径 B，必须先提供源码仓库的远程/归档来源或明确允许把该目录纳入版本控制；不能凭空创建基线 commit，也不能把外部目录的未追踪修改当作可回滚状态。

### 推荐替代方案：项目内只读 Insights 页面

先在 ResearchAgent 自有仓库实现一个只读 Ollama Insights 页面，通过受控查询访问 Langfuse v4 数据；不修改 Langfuse 通用页面、导航或数据库。推荐使用现有后端和纯静态前端：

- 后端查询适配器：`backend/app/observability/insights.py`
- API 路由与响应 schema：`backend/app/api/routes.py`、`backend/app/api/schemas.py`
- 前端页面入口与视图：`frontend/index.html`、`frontend/app.js`、`frontend/styles.css`
- 测试：`tests/test_observability_insights.py`（若目录不存在，先由实现任务创建）

该替代方案保留 Task 07 的核心价值（阶段甘特、冷/热对比、散点、分位和错误趋势），但不共享 Langfuse 内部 tRPC 权限上下文；因此必须使用服务端配置的只读凭据、明确项目 ID 白名单，并默认脱敏/截断 input/output。若需要 Langfuse 内部项目权限和侧栏入口，应将其作为后续独立 Spec，而非在当前不可回滚的外部目录中临时修改。

## 最小可行拆分（每批最多两个文件，目标改动不超过 150 行）

以下拆分适用于“项目内替代方案”。若外部 Langfuse 仓库恢复为可验证 Git 工作树，可将同样边界映射到 v4 源码，但每批仍须先分派 `junior-dev`。

### 批次 1：数据契约与查询适配器

- 文件：`backend/app/observability/insights.py`、`backend/app/api/schemas.py`
- 内容：定义时间范围、model、route、链路类型、成功状态和分页输入；只读取 `events_full/events_core` 与 `scores`；过滤未来时间、NaN、负耗时和超大正文；输出列表聚合、单次阶段数据和分位数据。
- 约束：不复用论文下载业务的 `TaskStore`；不把凭据或完整 prompt/output 写入响应。
- 验证：`.venv/bin/python -m pytest tests/test_observability_insights.py -q`；另加一条带空值、未来时间和失败样本的固定 fixture。

### 批次 2：API 接线

- 文件：`backend/app/api/routes.py`、`backend/app/main.py`
- 内容：新增只读 `/api/observability/insights` 与 `/api/observability/insights/{observation_id}`；复用现有配置读取和错误响应风格；设置超时、分页上限和项目白名单。
- 验证：`.venv/bin/python -m pytest tests/test_routes.py tests/test_observability_insights.py -q`；用测试客户端确认 200、400、404、502 四种状态。

### 批次 3：页面骨架与筛选

- 文件：`frontend/index.html`、`frontend/app.js`
- 内容：添加独立 Insights 区域、时间/model/route/type/success 筛选、分页、loading/empty/error 状态和详情抽屉入口；不改变现有聊天/知识库流程。
- 验证：现有前端静态检查命令（若无专项命令则执行项目既有测试）并用浏览器完成无数据、成功和错误三种状态验收。

### 批次 4：甘特与分布图

- 文件：`frontend/app.js`、`frontend/styles.css`
- 内容：复用现有前端脚本风格，绘制五阶段甘特、冷/热箱线或分位摘要、输入规模散点；阶段值必须非负、统一单位，0 值保留标签；图表渲染前限制样本数。
- 验证：固定样本逐项比对 `load_ms/prompt_eval_ms/ttft_ms/eval_ms/overhead_ms`，验证 0 值、不完整数据和大样本降级。

### 批次 5：回归与脱敏测试

- 文件：`tests/test_observability_insights.py`、`frontend/app.js`
- 内容：覆盖权限/项目隔离、未来时间、失败样本、NaN/负值、脱敏、截断和分页；页面不得显示 password、cookie、token 或环境变量。
- 验证：`.venv/bin/python -m pytest -q`，并保存固定样本校验摘要。

> 上述批次中前端 `app.js` 被两个批次触及，实际执行时必须串行合并并由主 Agent 读回确认，总改动仍不得超过每批约 150 行；若超过则再拆成独立图表模块。

## 若恢复外部 Langfuse Git 工作树后的映射

仅在版本控制门禁通过后，建议按以下文件边界实施：

1. 查询 schema/router：`web/src/features/ollama-insights/server/router.ts` + `web/src/server/api/root.ts`。
2. 查询工具/类型：`web/src/features/ollama-insights/server/query.ts` + `web/src/features/ollama-insights/types.ts`。
3. 页面骨架/入口：`web/src/pages/project/[projectId]/ollama-insights/index.tsx` + `web/src/components/layouts/routes.tsx`。
4. 甘特组件：`web/src/features/ollama-insights/components/StageTimeline.tsx` + `StageTimeline.clienttest.tsx`。
5. 分布/趋势组件：`web/src/features/ollama-insights/components/LatencyDistribution.tsx` + `InputLatencyScatter.tsx`。

这些是建议的新文件路径，不是当前已存在文件；不得在执行记录中写成已创建。新 router 应复用 `protectedProjectProcedure`，但不得把未经确认的 `events_full/events_core` 列名硬编码为旧版 observations schema，必须先以运行时 `DESCRIBE` 和固定 fixture 验证。

## 测试与验收标准

- 查询只返回指定 project，时间/model/route/type/success 过滤可复现。
- 阶段甘特五项数值与固定事件 metadata 一致，缺字段和 0 值安全。
- P50/P95/P99、冷/热、散点和错误趋势与独立计算一致。
- 列表分页，不拉取完整正文；详情默认折叠且有截断标记。
- Langfuse 外部源码未被修改；项目既有聊天、KB 和测试不回归。
- 能证明凭据、Cookie、Token、环境变量和完整 prompt/output 未进入页面或 Git 摘要。

## 回滚点

### 项目内替代方案

在 ResearchAgent 分支上只回滚本 Spec 的独立 commit，目标限定为上述新增/明确修改文件；不执行 `reset`、`stash`、`clean`，不覆盖用户其他修改，不删除 Langfuse 数据。

### 外部 Langfuse 方案

必须先获得可验证基线 commit；之后每批单独 commit，可按批次反向撤销页面、router、查询和测试，不回滚采集数据、不修改主工作树。

## 评审后的主 Agent 动作

1. 将 Task 07 标记为“源码导入完成，页面实施中”。
2. 在 vendor 目录建立 Git 基线提交（当前环境 `.git/index.lock` 写权限不足，尚未提交，需在可写 Git 环境完成）。
3. 按上述拆分逐批分派 `junior-dev`，再由 `tester` 验收；禁止修改外部源码目录。

## 执行记录

- 开始时间：2026-09-03 19:55:48 +0800
- 结束时间：2026-09-03 19:56:59 +0800（本评审文档写入时）
- 总耗时：约 1 分 11 秒
- 模型：`qwen3.8:27b-mlx`
- token / 工具调用统计：运行环境未提供可靠 token 计数；执行 5 组只读文件/搜索命令，未修改外部 Langfuse 源码。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | Tech Lead（子代理） | 完成 Task 07 只读架构评审；发现外部 Langfuse 目录不是 Git 工作树，拒绝进入不可回滚的源码实施，并提出项目内只读替代方案。 |
