# task-09 评测台前端：第 9 个「评测」视图与静态契约

> 关联：[spec-047 追加范围](../../specs/047-evaluation-p2-and-observability-fixes.md)（2026-11-10 用户授权，D7–D12，尤其 D11）
> 索引：[README.md](./README.md) ｜ 依据：[技术评审「追加范围技术评审」](../../reviews/047-tech-review.md)
> 依赖：task-08 端点契约（`GET /api/evaluation/options`、`POST /api/evaluation/score`、`GET /api/evaluation/runs*`、`GET /api/evaluation/compare`）；并行于/后于 task-08，前置于 task-10

## 状态
**已完成**（2026-11-10 收口：第 9 视图 / ?v=74 / 24 passed 评测契约 / 326 passed 静态回归；[object Object] P1 已修复）

## 一句话目标
在 `frontend/` 新增第 9 个「评测」视图：三个下拉（策略/模型/评测集）+「开始评分」按钮 + 每维度独立分数卡（数值/状态/样本数/明细）+ 运行历史 + 两次对比 delta；纯 SVG/CSS 自绘，让用户在界面上真实看到「每一部分的分数」与策略切换的效果提升。

## 前置条件
- task-08 的五个端点契约已定稿并可实现（前端按契约对齐，不依赖后端先行完成，用契约测试替身做静态开发）。
- 现有 `frontend/index.html:97-107` 为 8 个视图（chat/research/models/kb/memory/papers/literature-maps/skill-tool）；无图表库。
- 静态契约硬约束：`index.html:8,815-818` 的 `?v=N` 与旧版 HTML 注释兼容标记被 `tests/frontend/test_research_task_search.py:37-41` 等锁定（`?v=22`/`?v=70`/`?v=72` 与 legacy marker **必须保留**）；`regression-guard` 前端清单：`app.js`/`styles.css` 改动须同步升 `index.html` 的 `?v=N`、新增 class 须在 `styles.css` 存在、禁 `innerHTML`（用 `createElement`/`textContent`）、CSS 作用域限定本视图。
- Spec013 vendor React 图表组件验收不通过，**不可复用**；本视图纯 SVG/CSS 自绘。

## 文件边界（唯一可改）
- `frontend/index.html`：新增第 9 个导航项与视图容器；改了 `app.js`/`styles.css` 后升 `?v=N`；**不得删除**任何旧版兼容标记注释。
- `frontend/app.js`（或按现有评测相关模块约定）：下拉填充、开始评分请求、每维度卡片渲染、运行历史、两次对比 delta；只用 `createElement`/`textContent`。
- `frontend/styles.css`：本视图作用域内新 class，全部在 `app.js`/`index.html` 有对应。
- 新增前端静态契约测试（`tests/frontend/`）：第 9 视图存在、`?v=N` 已升、legacy marker 保留、无 `innerHTML`、DOM class 双向一致。
- **不改**：`backend/`（归 task-08）、原 8 视图行为、任何旧兼容标记、业务代码之外的配置。

## 分派角色
`frontend-dev`（实现 + 静态契约）；`frontend-tester` 静态核对（DOM 契约 / `?v=N` / XSS / `node --check`）。

## 验收
- 三个下拉数据来自 `GET /api/evaluation/options`；点「开始评分」调用 `POST /api/evaluation/score`，按 `metrics[]` 逐维度渲染独立卡片（数值 / `status` / `sample_count` / `detail`），能看到「每一部分的分数」。
- 两次运行可按维度看 `delta`（策略导致的效果提升）；`EVAL_NOT_COMPARABLE` 时无 delta 且给出原因（不同 dataset / 不同判官不得算可比差值）。
- 运行历史（`GET /api/evaluation/runs`、`runs/{run_id}`）可见；失败态按稳定错误码映射文案，不出现「降级/关闭态」隐藏分数，`degraded`/`needs_ground_truth` 卡片如实展示 `status` 与 `reason`。
- `node --check` 通过；新增 class 在 `styles.css` 存在；`?v=N` 已升且 legacy marker 全部保留；静态契约测试通过；无 `innerHTML` 拼接用户输入（XSS）。

## 回滚
- 前端为纯静态追加：移除第 9 导航项/视图容器与相关 `app.js`/`styles.css` 增量、`?v=N` 回退到追加前值（保留所有 legacy marker）即恢复原 8 视图；不影响后端与原功能。

## 产出物
- `frontend/index.html`（第 9 视图 + 版本号）、`frontend/app.js`、`frontend/styles.css` 增量、`tests/frontend/` 新增静态契约、`docs/sdd/plans/047/runs/task-09/`（实现交接 + `node --check` 与契约测试输出）。
