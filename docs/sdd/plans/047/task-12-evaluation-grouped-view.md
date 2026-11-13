# 追加范围二 Task12：评测指标分组视图（前端）

> 状态：**已完成** ｜ 关联 [spec-047 追加范围二](../../specs/047-evaluation-p2-and-observability-fixes.md) ｜ 索引 [README](./README.md)
> 分派：`frontend-dev` ｜ 依赖：Task11 的 `group` 字段契约（规格已冻结，可并行开发）
> 复核依据：`047-tech-review.md`「追加范围二技术评审」R1(b) 与前端契约三项

## 1. 一句话目标

把评测视图的指标卡从平铺 6 张改成**按 5 个组渲染 22 张**，对比视图按组展示 delta，
历史 run 不丢卡、不报错；所有新文本走 `textContent`。

## 2. 文件边界（严格遵守）

**只允许改**：`frontend/app.js`、`frontend/index.html`、`frontend/styles.css`，
以及新增 `tests/frontend/` 下的静态契约测试（属前端域，按能力命名、**文件名禁含 spec/task 编号**）。

**禁止改**：`backend/**`（后端 pytest 一律不跑）、`docs/sdd/specs/**`、任何配置 / `.env` / 业务代码。

## 3. 契约（与 Task11 对齐，不要自己发明字段）

`metrics[]` 每项新增 `group`，取值 `retrieval` / `intent` / `answer_quality` / `generation` / `safety`；
历史 run 的 6 项**没有 `group`** → 前端兜底为 `other`。
`compare` 的 `deltas[]` 每项同样带 `group`（旧 run 可能没有 → 兜底 `other`）。

分组标题文案（固定，便于静态契约断言）：

| group | 标题 |
|---|---|
| `retrieval` | 检索质量 |
| `intent` | 意图识别 |
| `answer_quality` | 回答质量 |
| `generation` | 生成可用性 |
| `safety` | 安全 |
| `other` / 未知 | 其它维度 |

## 4. 实施步骤

1. **`frontend/app.js`**（评测段约 `7487–7790`）：
   - 新增 `EVALUATION_GROUP_ORDER` 与 `EVALUATION_GROUP_LABELS` 常量、`evaluationGroupOf(metric)` 兜底函数。
   - 改造 `renderEvaluationMetrics(metrics)`：按 `EVALUATION_GROUP_ORDER` 顺序分组，每组插入一个标题节点
     （`createElement` + `textContent`，建议 `h3.eval` / `div.evaluation-metric-group-title`），组内按原顺序
     `appendChild(renderEvaluationMetricCard(...))`；空组不渲染标题；`metrics` 为空仍走既有
     `#evaluation-metrics-empty` 逻辑。
   - 改造 `renderEvaluationCompare`：把 `deltas[]` 同样按组输出标题与逐维度行，保留既有 `delta` / `status_a` /
     `status_b` 语义；跨 dataset 的 `EVAL_NOT_COMPARABLE` 分支不变。
   - `renderEvaluationRunHead` / 运行历史 / 详情表（`renderEvaluationDetail...` 约 7704 行）中的卡片渲染
     一并复用分组函数，避免同一页面两套逻辑。
   - **R1(b) 必改**：`submitEvaluationScore` 里 `evaluationRequest(..., 120000)` 改成 `300000`，
     与服务端 `SCORE_TIMEOUT_SECONDS=300` 对齐，避免「前端报失败但 `save_run` 已落盘」的跨端不一致；
     等待文案可补「多维打分可能耗时数分钟」。
   - `formatEvaluationStrategy(value)` 等既有 helper 不动；`value=null` 继续显示 `—`，**不得显示 0**。
2. **`frontend/index.html`**：`app.js?v=74` → **`app.js?v=75`**，`styles.css?v=71` → **`styles.css?v=72`**；
   **保留全部 legacy / compatibility marker 注释**（L7、L862、L864、L865、L867、L868 逐字不动），
   并新增一条含 `app.js?v=74` 的兼容 marker 注释（照 L865 写法）。
3. **`frontend/styles.css`**：新增 `.evaluation-metric-group` / `.evaluation-metric-group-title` 等样式，
   选择器必须限定在 `#evaluation-view` 作用域内；风格与既有 `.evaluation-metric-card` 一致
   （深色底、可窄屏换行、不产生横向溢出）。
4. **静态契约测试**：新增 `tests/frontend/` 用例，断言分组常量/标题文案存在、`group` 兜底分支存在、
   `?v=75` / `?v=72` 生效且旧 marker 保留、无 `innerHTML` 拼接、`300000` 超时对齐、CSS class 双向一致。

## 5. 三项自查（回传必须逐条给结论）

1. **DOM class 与 CSS 双向一致**：新增的每个 class 在 `app.js` 与 `styles.css` 都能互相找到。
2. **`?v=N` 已升级且旧标记保留**：`app.js?v=75`、`styles.css?v=72`，旧 marker 一个没删。
3. **无 `innerHTML`**：评测段所有新增渲染走 `createElement` / `textContent` / `replaceChildren()`；
   `group` / `label` / `reason` / `detail.per_class` 等后端文本一律 `String(...)` + `textContent`。

验收命令：`node --check frontend/app.js`（退出码 0）+ 新增静态契约 pytest 真实输出。

## 6. 明确不做

- 不改后端、不跑后端 pytest、不发明新端点 / 字段 / 错误码。
- 不引入图表库、不复用 Spec013 vendor React 组件、不用 `innerHTML`、不删旧版兼容标记。
- 不把 `value=null` 渲染成 `0`、不把 `degraded` 卡片隐藏成「关闭态」——**照常显示 status + reason**。
- 不伪造维度、不在前端补算后端没给的分数；不 push、不合 main。

## 7. 产出物 / 变更日志

- 代码：三份前端文件 + 静态契约测试。
- 落盘交接：`docs/sdd/plans/047/runs/task-12/implementation.md`（三项自查结论、改动文件、命令/退出码、风险）。
- 进展日志：`.codebuddy/agent-logs/spec-047/task-12/frontend-dev/<YYYYmmdd-HHMMSS>.md`，每步「观察/判断/下一步/进度 X%」，回传必须给日志路径。
- 新建文件只能用 `Bash` heredoc（定界符加单引号），创建后 `Read` 读回校验。
