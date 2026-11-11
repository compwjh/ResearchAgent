# task-02 修复 C：`--force` 幂等（widget_id manifest 按 ID 删/复用）

> 关联：[spec-047](../../specs/047-evaluation-p2-and-observability-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`（9 passed 契约；真实 `--force` 按 D4 降级未重跑） ｜ 对应 spec 表编号 03 ｜ 决策 D4

## 状态与一句话目标

`待执行`。给 `scripts/setup_langfuse_dashboards.py` 加「脚本自建 widget_id manifest，按 ID 清单删 / 复用」能力，禁止按名称或全量删；真实 `--force` 重跑降级为隔离项目 / 只读契约验证。

## 背景与前置条件

- 只读调查 C 节 + [技术评审 §3 风险 2](../../reviews/047-tech-review.md)：`setup.py:271-283` 现 `--force` 只删 dashboard 不删 widget，随后新建 40 个 → 每次遗留 40 孤儿；`public-dashboard-widget-service.ts:318-333` 只按 `projectId` 分页无来源过滤；`dashboard-contract.json:81-90` 已有跨看板重名 widget；`schema.prisma:1542-1568` 无 `createdBy`/`dashboardId` 外键；DELETE 为硬删不可回滚。
- 前置：task-01 完成；D4 已拍板「按 ID 删/复用 + 单独授权窗口 + 只读备份」。

## 数据 / 配置 / 接口增量

- **新增 manifest（本地文件，非 DB）**：`docs/sdd/plans/047/runs/task-02/widget-manifest.json`，结构 `{"schema_version":1,"project_id":"...","created_at":"UTC","source":"setup_langfuse_dashboards.py","widgets":[{"id","name","dashboard_index"}]}`；原子写 + 文件锁，跨 `--force` 重跑保留、不被删。
- **复用既有端点**（不新增自研端点）：`GET /api/public/unstable/dashboard-widgets?page=&limit=`、`DELETE /api/public/unstable/dashboard-widgets/{widgetId}`、`POST ...`、`DELETE /dashboards/{id}`，Basic Auth = `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`。

## 实施步骤与文件边界

**唯一可改文件**：`scripts/setup_langfuse_dashboards.py`；新增 manifest 与契约测试（mock httpx）；`runs/task-02/` 证据。

1. `DashboardBuilder` 增 `list_widgets()`（GET + **按 `meta.totalPages` 循环翻页**，`limit` 保守取 100，不假设单页 50 取全）与 `delete_widget()`（DELETE + Basic auth）。
2. 每次 `create_widget` 成功后**立即**追加写 manifest（先于 create_dashboard / add_placement）。
3. 改 `:269-283` 的 `--force` 分支：读 manifest → 只按 manifest 内 ID 逐个删 / PATCH 复用；**先删 dashboard / 清 placement 再删 widget**（`dashboard-widgets.yml:145` 409 约束）。禁止按名称、禁止全量删。`DASHBOARDS` 定义(`:95-196`)不动。
4. **红→绿契约测试（mock httpx）**：断言「按 ID 删/复用」「名称重名不误删」「先清 placement」「重建后 widget 总数仍 40、无孤儿」「默认模式新建 0 / 跳过 6 / 40 widget ID 不变」。

## 子代理分派

- 脚本改动 → `Task(backend-dev)`（最小上下文：技术评审 §3 风险 2 + 本任务 + `setup.py` 行号）；回传片段 + 读回校验。
- 回归 → `Task(backend-tester)`（mock 契约测试）。

## 边界与明确不做

- **不删用户手工 widget**：只按 manifest 记录的脚本自建 ID 操作；`createdAt` 仅作弱辅助、不作可靠判据。
- **不可靠区分是既成事实，如实降级**：无 `createdBy` 字段，无法区分「manifest 建立前的历史 40 widget」与「用户手工 widget」，二者一律不动。
- **真实 `--force` 重跑降级**：仅在隔离 Langfuse 项目 / mock 契约层验证；**不触碰当前部署的 6 个真实 dashboard**；`dashboard-contract.json:92-104` 的 `DEFECT (reported, not fixed)` **不改写**；**不得声称线上 `--force` 已修好**。
- 未经 D4 单独书面授权不执行线上真实重跑；执行前先 `GET ...dashboard-widgets?limit=100` 只读落盘清单备份。
- 不改 vendor Langfuse 源码；不 push、不合 main；不写状态台账；不改 `.env`。

## 验收、风险与回滚

- 契约测试全绿；默认模式只读真跑复现「新建 0 / 跳过 6 / 40 widget ID 不变」。
- E2E 取证：`runs/task-02/` 落契约测试输出 + 只读清单备份（若授权窗口开启则附隔离项目真实 widget ID / 删除前后 totalItems）；真实请求 / 状态码 / widget ID / 产物路径。
- 风险：历史孤儿无法清理（如实记录，非本 task 能解）；DELETE 409（placement 未清）。回滚：manifest 文件 + 脚本改动回退；已删 widget 用备份清单经既有 `create_widget`/`create_dashboard`/`add_placement` 重建（placements 需重建）。

## 产出物、执行结果与变更日志

- 产出物：`docs/sdd/plans/047/runs/task-02/widget-manifest.json`、契约测试输出、只读清单备份。
- 执行结果：待执行后填写。
- 变更日志：待执行后填写。

