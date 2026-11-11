# 追加范围三 Task15：紧凑可展开指标卡（前端）

> 状态：**已完成**（含选项区样本数补丁 `?v=77`；复审与回归 514 passed） ｜ 关联 [spec-047 追加范围三](../../specs/047-evaluation-p2-and-observability-fixes.md)（§2.3/§5/§6/§8/§9/**§13**） ｜ 索引 [README](./README.md)
> 分派：`frontend-dev`（独立一次，与 task-14 并行开发、不派通吃 agent）｜ 依赖：需求评审 [§15](../../reviews/047-requirement-review.md) + 技术评审 [「追加范围三」](../../reviews/047-tech-review.md)
> 复核依据：技术评审 P1-2（前端 900000 对齐）、§13.2 升版静态契约、追加范围二修复的「marker 污染 live-script」P1。

## 1. 一句话目标

把 22 张指标卡缩小到常见桌面宽度下一屏可见大部分，长参数默认收进原生 `<details>`、点击可展开，
**关键信息始终可见**；版本号 `?v=76` / `?v=73` 生效且前端超时与服务端 900s 对齐。

## 2. 文件边界（严格遵守）

**只允许改**：`frontend/app.js`、`frontend/index.html`、`frontend/styles.css`，
以及 `tests/frontend/` 下的静态契约测试（属前端域，按能力命名、**文件名禁含 spec/task 编号**；
已知需改 `tests/frontend/test_evaluation_asset_versions.py` 的精确断言，可新增新文件）。

**禁止改**：`backend/**`（后端 pytest 一律不跑）、`docs/sdd/specs/**` / `reviews/**` / 状态台账、任何配置 / `.env` / 业务代码。

## 3. 卡片字段分层契约（前后端共用，spec §2.3）

| 层级 | 字段 | 行为 |
|---|---|---|
| **关键信息（始终可见，不隐藏、不随折叠收起）** | `label`、`value`（`null → —`）、`status`、`sample_count`、`detail.reason`（非空时）、`detail.judge_sample_count`（与 `sample_count` 不一致时）、对比页 `delta`、5 个分组标题 | `degraded` / `needs_ground_truth` / `unavailable` 卡片照常显示 status + reason，**不隐藏成关闭态**；不把 `null` 渲染成 `0` |
| **可折叠参数（默认收起，点击展开）** | `detail` 其余字段：`judge_model`、`under_test_model`、`answer_source`、`score_mapping`、`reference_fixture`、`rubric`、`context_source`、`per_class`、`predictions`、`expected`、`generation_failure_types`、`trace_count`、`generated_count`、`judge_mode`、`batch_count`、`total_items` 等（**按后端实际返回的 key 遍历，不白名单丢弃新增字段**） | 用原生 `<details>/<summary>`，摘要文案固定「参数与明细」；`details` 元素**不设 `open` 属性**（默认收起）；展开后每个参数一行 `key: value`（`String(...)` + `textContent`） |

- 无 `detail` 或 `detail` 为空的卡片**不渲染空的 `<details>`**；只有 `reason` 且无其它参数时同理。
- `reason` 在 `<details>` **外**单独渲染；`judge_sample_count` 若与 `sample_count` 不同，也在 `<details>` 外显示。

## 4. 实施步骤

1. **`frontend/app.js`**（评测段约 `7487–7790`）：
   - 改造 `renderEvaluationMetricCard(metric)`：把当前「`metric.detail` 全量平铺」改为上述分层；
     关键信息用现有节点与 `formatEvaluationMetricValue(metric)`（`status !== 'computed' || value == null → '—'` 规则逐字不动）。
     新增 `<details class="evaluation-metric-params">` / `<summary>参数与明细</summary>`，
     内部逐项 `createElement('div')` + `textContent = String(key) + ': ' + String(value)`；
     值含 `<script>` 时也必须是纯文本。
   - **P1-2 必改**：`submitEvaluationScore` 的 `evaluationRequest('/api/evaluation/score', ..., 300000)` → **`900000`**，
     与服务端 `SCORE_TIMEOUT_SECONDS=900.0` 对齐；等待文案补「100 条样本真实打分（批量生成 + 批量判官，可能耗时数分钟）」，
     **必须保留「评分中…」/「正在」字面**（否则打断 `tests/frontend/test_evaluation_metric_status_rendering.py:116-122`）。
   - `formatEvaluationStrategy(value)`、`EVALUATION_GROUP_ORDER`、分组渲染、compare 按组 delta、历史 run 详情渲染**逻辑不动**；
     历史 run 无 `judge_sample_count` 等新字段时必须正常显示、不丢卡、不报错。
2. **`frontend/index.html`**：live `app.js?v=75 → ?v=76`、`styles.css?v=72 → ?v=73`。
   **保留全部 legacy / compatibility marker 注释**，并新增一条含 `app.js?v=75` 的兼容 marker，
   且必须写成**纯属性片段**（照 `index.html:866` 写法：HTML 注释内只含 `src="/assets/app.js?v=75" href="/assets/styles.css?v=72"`，
   **不含 `<script` / `<link` 标签字面串**），避免重演上一轮「marker 污染 live-script 静态契约」P1。
3. **`frontend/styles.css`**（`#evaluation-view` 作用域内，约 `4218–4253`）：
   - `.evaluation-metrics` 网格 `minmax(230px,1fr) → minmax(160px,1fr)`、`gap:12px → 8px`；分组卡网格同步（`minmax(min(230px,100%),1fr)` → `minmax(min(160px,100%),1fr)`）。
   - `.evaluation-metric-card` `padding:14px → 8px`、`gap:8px → 5px`。
   - `.evaluation-metric-value` `22px → 18px`；`.evaluation-metric-label` `13px → 12px`；分数条 `height:8px → 6px`。
   - 新增 `.evaluation-metric-params` / `summary` 样式：字号 ≤12px、默认收起态不占额外高度、展开后 `overflow-wrap:anywhere` 防横向溢出；窄屏不产生横向滚动。
   - 所有新增 class 必须限定 `#evaluation-view` 作用域，且与 `app.js` 双向一致。
4. **静态契约测试**：
   - 改 `tests/frontend/test_evaluation_asset_versions.py:99-100` 的精确断言为 `_live_versions("app.js") == [76]`、`("styles.css") == [73]`；
     保留 `LEGACY_MARKERS` 与「新 marker 为纯属性片段」断言（该正则不匹配注释内纯属性片段，机制已由技术评审 2.7 核实）。
   - 新增/扩展用例断言：CSS 尺寸数值（8px / 18px / 160px / 6px / 5px）、`<details>` 存在且源码中无 `open` 默认展开、
     摘要文案「参数与明细」、`reason` 与 `sample_count` 在 `<details>` 外、900000 超时对齐、无 `innerHTML`、
     `null → —`、degraded 不隐藏、class 双向一致、含 `<script>` 的 label/reason 纯文本渲染。

## 5. 三项自查（回传必须逐条给结论）

1. **DOM class 与 CSS 双向一致**：新增的每个 class 在 `app.js` 与 `styles.css` 都能互相找到。
2. **`?v=N` 已升级且旧标记保留**：`app.js?v=76`、`styles.css?v=73`，旧 marker 一个没删，新 marker 是纯属性片段。
3. **无 `innerHTML`**：评测段所有新增渲染走 `createElement` / `textContent` / `replaceChildren()`；
   `label` / `reason` / `detail.*` 一律 `String(...)` + `textContent`。

验收命令（回传真实输出）：`node --check frontend/app.js`（退出码 0）+ `.venv/bin/python -m pytest -q tests/frontend/test_evaluation_asset_versions.py tests/frontend/test_evaluation_metric_status_rendering.py tests/frontend/test_evaluation_metric_grouping.py tests/frontend/test_evaluation_strategy_label_rendering.py`。

## 6. 明确不做

- 不改后端、不跑后端 pytest、不发明新端点 / 字段 / 错误码；不在前端补算后端没给的分数。
- 不引入图表库 / 第三方依赖、不用 `innerHTML`、不删旧版兼容标记。
- 不把 `value=null` 渲染成 `0`、不把 `degraded` 卡片隐藏成「关闭态」——照常显示 status + reason。
- 不因卡片缩小删掉 `reason`、`status`、`sample_count`、分组标题、对比 delta；不把关键信息塞进折叠区。
- 不改原六块与追加范围二的历史结论；不 push、不合 main。

## 7. 产出物 / 变更日志

- 代码：三份前端文件 + 静态契约测试。
- 落盘交接：`docs/sdd/plans/047/runs/task-15/implementation.md`（三项自查结论、改动文件、命令/退出码、风险）。
- 进展日志：`.codebuddy/agent-logs/spec-047/task-15/frontend-dev/<YYYYmmdd-HHMMSS>.md`，每步「观察 / 判断 / 下一步 / 进度 X%」，回传必须给日志路径。
- 新建文件只能用 `Bash` heredoc（定界符加单引号），创建后 `Read` 读回校验。
- 回传请 concise：改动清单 + 三项自查 + 定向测试真实输出 + 日志路径；**不要粘贴大段代码**。
