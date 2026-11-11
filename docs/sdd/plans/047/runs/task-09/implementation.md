# task-09 评测台前端 · 实现交接

> 角色：frontend-dev（TDD）。范围：仅 `frontend/**`、`tests/frontend/` 新增静态契约测试、本交接文档。
> 依据：`docs/sdd/plans/047/task-09-evaluation-frontend.md`、spec-047 D8–D12 / 主案例 E0。
> 状态：实现完成，静态契约全绿；后端由 backend-dev（task-08）并行实现，未依赖其先行完成。

## 1. 改动文件与行数

| 文件 | 类型 | 变化 |
|---|---|---|
| `frontend/index.html` | 修改 | 新增第 9 导航项 + 评测视图容器；`styles.css?v=70→71`、`app.js?v=72→73`；新增 1 条兼容注释保留旧精确标签串；**未删除任何 legacy marker** |
| `frontend/app.js` | 修改 | `MAIN_AREA_VIEW_IDS` / `showView` / `HASH_VIEW_MAP` 各一处接线；末尾追加评测模块（下拉填充、评分、逐维度卡片、历史回看、两次对比） |
| `frontend/styles.css` | 修改 | 末尾追加 `#evaluation-view` 作用域样式（纯 CSS/SVG，无图表库） |
| `tests/frontend/test_evaluation_view_contract.py` | 新增 | 第 9 视图 DOM/hash、class 双向一致、无 `innerHTML`、SVG 自绘 |
| `tests/frontend/test_evaluation_metric_status_rendering.py` | 新增 | 四 status 分支、`value=null` 不渲染 0、错误码、不可比、busy/超时 |
| `tests/frontend/test_evaluation_asset_versions.py` | 新增 | `?v=N` 已升 + 全部 legacy marker 保留 |
| `docs/sdd/plans/047/runs/task-09/implementation.md` | 新增 | 本交接文档 |

最终行数见文末附录。

## 2. 第 9 视图 DOM 契约（供 E2E 定位）

- 导航 hash：`#evaluation-view`；导航项 `[data-view="evaluation"]`；容器 `#evaluation-view`（默认 `hidden`）。
- 三个下拉：`#evaluation-strategy-select`、`#evaluation-model-select`、`#evaluation-dataset-select`。
- 表单 `#evaluation-score-form`；按钮 `#evaluation-score-button`（「开始评分」→「评分中…」）。
- 状态条 `#evaluation-status`；spinner `#evaluation-spinner`；运行头 `#evaluation-run-head`。
- 分维度卡片容器 `#evaluation-metrics`（每张 `.evaluation-metric-card`，`data-status` ∈ computed / degraded / needs_ground_truth / unavailable）；空态 `#evaluation-metrics-empty`。
- 运行历史 `#evaluation-runs-list` / `#evaluation-runs-refresh` / `#evaluation-runs-empty` / 回看 `#evaluation-run-detail`。
- 两次对比 `#evaluation-compare-a` / `#evaluation-compare-b` / `#evaluation-compare-button` / `#evaluation-compare-result`。

主案例 E0 界面路径：点导航「评测」→ 三选一 → 「开始评分」→ 看每维度独立分数卡（数值 / status / 样本数 / 明细）→ 切策略再评分一次 → 选 A/B 点「对比」看 delta → 运行历史点任一条回看。**入口是界面控件，不是内部 API 调用。**

## 3. 数据流（按 D11 契约）

| 动作 | 前端调用 |
|---|---|
| 填充三下拉 | `GET /api/evaluation/options` → `{strategies, models, datasets}` |
| 开始评分 | `POST /api/evaluation/score`，body `{strategy_id, model, dataset_id}` → `{run_id, metrics[], strategy, model, dataset, created_at}` |
| 运行历史 | `GET /api/evaluation/runs`；回看 `GET /api/evaluation/runs/{run_id}`（`encodeURIComponent`） |
| 两次对比 | `GET /api/evaluation/compare?a=&b=`（`URLSearchParams`） |

- `metrics[]` 每项 `{key,label,value,status,sample_count,detail}`：卡片**同时**显示数值、`status` 中文标签 + 原值、样本数、`detail` 全部键值（`reason` 优先）。
- 仅 `status=computed` 显示数值与 SVG 分数条；`degraded` / `needs_ground_truth` / `unavailable` 一律显示「—」+ `detail.reason`，**不隐藏卡片、不跳过维度、不显示假 0**（`formatEvaluationMetricValue` 对 `value === null` 返回 `'—'`，函数体无任何 `|| 0` / `?? 0` 兜底）。
- 稳定错误码映射中文提示且可重试（按钮在 `finally` 恢复）：`EVAL_OPTION_NOT_FOUND` / `EVAL_DATASET_INVALID` / `EVAL_BACKEND_UNAVAILABLE` / `EVAL_SCORE_TIMEOUT` / `EVAL_NOT_COMPARABLE`；未知码走通用文案。
- busy 态：按钮禁用 +「评分中…」+ spinner +「正在真实打分，请稍候；期间仍可查看已有运行历史…」；历史刷新按钮不禁用；`AbortController` 120s 超时按 `EVAL_SCORE_TIMEOUT` 提示，不无限等待。
- `EVAL_NOT_COMPARABLE`（非 2xx 稳定错误体，或 200 body 标记）：显示「不可比」原因后 `return`，**不渲染 delta**；可比时按维度渲染 `delta`（正数带 `+`，`null` 显示「—」）。
- `created_at` 按 UTC 解析后 `toLocaleString()` 本地化展示。

## 4. 版本号与 legacy marker

- 升级前：活跃 `href="/assets/styles.css?v=70"`（L8）、`src="/assets/app.js?v=72"`（原 L818）。
- 升级后：活跃 `href="/assets/styles.css?v=71"`（L8）、`src="/assets/app.js?v=73"`（L863）。
- 新增兼容注释（L864）：`<!-- Evaluation view compatibility markers retained for older static contracts: href="/assets/styles.css?v=70" src="/assets/app.js?v=72" -->`，逐字保留旧两个精确标签串。
- 全部旧版注释标记（Task09/Task10、Task05、Session UI、`research-tasks.js?v=21`、Legacy asset-version markers、Spec037 等）**一条未删**；既有 `test_research_task_search.py` / `test_frontend_management_contract.py` / `test_answer_math_rendering_contract.py` / `test_frontend_map_header_actions_readability.py` 的逐字断言与 `INDEX.index()` 位置断言继续通过（回归 321 passed）。该注释位于 KaTeX 标签之后，`katex_js < app_js` 仍成立。

## 5. TDD 过程与验证结果

| 阶段 | 命令 | 退出码 | 结果 |
|---|---|---|---|
| RED（实现前） | `pytest` 三份新测试 `-q --confcutdir=tests/frontend` | 1 | 17 failed / 2 passed（失败点均为待实现能力，门禁真实有效） |
| GREEN（实现后） | 同上 | 0 | **19 passed** |
| 最终门禁 | 同上 + `node --check frontend/app.js` | 0 | 19 passed；`NODE_CHECK_EXIT=0` |
| 既有回归 | `pytest tests/frontend -q --confcutdir=tests/frontend` 并 `--ignore` 19 个 playwright 用例 | 0 | **321 passed** |

精确命令：

```bash
cd /Users/wjh/ResearchAgent
node --check frontend/app.js
python -m pytest tests/frontend/test_evaluation_view_contract.py \
  tests/frontend/test_evaluation_metric_status_rendering.py \
  tests/frontend/test_evaluation_asset_versions.py -q --confcutdir=tests/frontend
IGNORES=$(grep -l playwright tests/frontend/*.py | sed 's|^|--ignore=|' | tr '\n' ' ')
python -m pytest tests/frontend -q --confcutdir=tests/frontend $IGNORES
```

> 环境说明：仓库根 `conftest.py` 的 autouse fixture 依赖 `langchain_ollama` 等后端包，19 个既有测试依赖 `playwright`，本环境均未安装 → 纯静态契约测试须以 `--confcutdir=tests/frontend` 隔离根 conftest、并 `--ignore` 浏览器用例。改动前基线 `pytest tests/frontend -q` 即因同样原因退出码 2、13 个 collection error；与本次改动无关。

## 6. 三项自查（regression-guard 前端 1–4 条）

1. **DOM class 双向一致**：脚本核对 `html=20 / js=20 / css=38`，`html-not-in-css=[]`、`js-not-in-css=[]`、`css-not-rendered=[]`；CSS 全部为 `#evaluation-view .evaluation-*` 作用域，无行首裸 `.evaluation-*` 规则；`#evaluation-view[hidden]` 保证互斥显隐。
2. **资源版本号**：`app.js?v=72→73`、`styles.css?v=70→71`，活跃标签各唯一；旧精确标签串与全部 legacy 注释保留（回归佐证）。
3. **XSS**：评测模块 `innerHTML` 出现次数 = 0；后端不可信文本（`detail` / `reason` / 模型名 / 策略名 / label / run_id）一律 `createElement` + `textContent` / `replaceChildren()`，输入读取只用 `select.value`。
4. **不改原 8 视图**：8 个 `data-view` 全部保留；`showView` 仅新增 1 行 `#evaluation-view` 显隐；评测数据加载由模块自身 nav click / hashchange 监听触发，不侵入既有控制流（也规避模块末尾 `const` 的 TDZ）。

## 7. 契约不一致 / 风险（需 backend-dev 或 task-10 确认）

- `GET /api/evaluation/compare` 的**成功返回体形状 spec 未完全定稿**（仅写「按维度 delta」）。前端做了兼容归一化：`payload.deltas[]` / `payload.metrics[]` / 顶层数组；每行取 `label ?? key` 与 `delta`；`comparable === false` / `not_comparable === true` / `error.code` / `code` 均视为不可比。若后端改用别的字段（如 `diff` / `per_metric`），需前端补映射或后端对齐。
- `EVAL_NOT_COMPARABLE` 同时兼容「非 2xx + 稳定错误体（`detail.code` / `error.code` / `code`）」与「200 + body 标记」；不可比原因优先读 `payload.reason` / `payload.detail.reason`，否则用中文兜底文案。请后端确认 reason 字段名。
- `GET /api/evaluation/runs` 兼容「数组」与 `{runs: []}`；`options` 三个列表兼容「字符串数组」与 `{id/key/name, label}` 对象数组。若后端返回 `{items: []}` 或更深嵌套，需补映射。
- `POST /api/evaluation/score` 未传可选 `max_items`（由服务端默认/上限约束）；前端超时阈值 120s 只是防无限等待的兜底，以服务端 `EVAL_SCORE_TIMEOUT` 为准。
- 本任务只做静态契约，未做真实浏览器 E2E（依赖后端五端点可用 + playwright 环境）；真实出分 / 策略 delta / 人工验收由 task-10 完成。

## 8. 回滚

移除第 9 导航项/视图容器、`app.js` 3 处接线与末尾模块、`styles.css` 末尾增量，`?v=N` 回退到 `70` / `72`（保留所有 legacy marker，含本轮新增的兼容注释亦可），并删本轮 3 个静态契约测试。原 8 视图与后端不受影响。

## 9. 日志路径

`.codebuddy/agent-logs/spec-047/task-09/frontend-dev/20261110-013622.md`

## 附：最终文件行数

```
     869 frontend/index.html
    7809 frontend/app.js
    4251 frontend/styles.css
     124 tests/frontend/test_evaluation_view_contract.py
     129 tests/frontend/test_evaluation_metric_status_rendering.py
      92 tests/frontend/test_evaluation_asset_versions.py
   13274 total
```

---

## 10. 增量修复记录：策略名显示 `[object Object]`（本 Task 内可见 UI 缺陷）

> 范围：`frontend/app.js`、`frontend/index.html`（仅版本号）、新增 1 份静态契约测试、本交接文档。
> 未动 `backend/**`、spec、台账、其它视图、原 8 视图行为；未 commit。

### 10.1 缺陷事实与根因

主会话真实浏览器 E2E 快照 `eval-initial.yaml` / `eval-scored.yaml` 复现：后端 run 的 `strategy` 是**对象**
`{"id":"topk-10","label":"扩大召回（v1 / top_k=10 / reranker=off）","chunker":"v1","top_k":10,"reranker":"off"}`，
而 `dataset` / `model` 是字符串。原实现把 `strategy` 直接 `String()` 或塞进数组插值：

| 位置（修复前行号） | 原写法 | 症状 |
|---|---|---|
| L7588 运行详情表 | `['策略', run.strategy]` | `策略：[object Object]` |
| L7655 运行历史 meta | `[run?.strategy, ...].map(part => String(part ?? '—'))` | `eval-xxx · [object Object] · rag-retrieval` |
| L7687 运行回看 head | 同上 | 同上 |
| L7718 对比下拉 option | `${String(run?.strategy ?? '—')}` | `eval-xxx · [object Object] · main-case` |

### 10.2 最小修复

- 新增局部 helper `formatEvaluationStrategy(value)`（L7396-7405，紧邻同类 `formatEvaluationCreatedAt`）：
  对象优先 `value.label` → 无则 `value.id` → 都没有返回 `'—'`；字符串原样返回；`null/undefined` 返回 `'—'`；
  其余类型返回 `'—'`。**一律返回字符串，函数体无任何 `String(value)` / 数组插值对象**。
- 4 处统一改走 helper（修复后行号 L7601 / L7668 / L7700 / L7731），不再把对象直接转成字符串。
- `app.js` 改动 → `index.html` 活跃 `app.js?v=73→74`（L863）；新增兼容注释 L865 逐字保留
  `src="/assets/app.js?v=73"` 恰好 1 份；**所有 legacy marker 一条未删**（兼容注释块 `<!--` 由 13→14）。
- `styles.css` 未改（`?v=71` 保持不变）；未新增/修改任何 class；未使用 `innerHTML`。

### 10.3 TDD 与验证（命令 / 退出码 / 通过数）

新增 `tests/frontend/test_evaluation_strategy_label_rendering.py`（按能力命名、不含编号，237 行，5 个用例）：
静态契约（helper 存在且不 String 对象、4 处均改用 helper、`?v=74` 且旧标签保留 1 份）
+ node 真实执行（用对象形态 `strategy` 在最小 DOM stub 中执行真实渲染函数，断言历史 / 详情 / 对比文本
不含 `[object Object]` 且含可读 label / id；helper 对 6 种输入形态一律返回字符串）。

| 阶段 | 命令 | 退出码 | 结果 |
|---|---|---|---|
| RED（实现前） | `python -m pytest` 4 份评测契约 `-q --confcutdir=tests/frontend` | 1 | `5 failed, 19 passed`；node 真实复现 `[object Object] · rag-retrieval · main-case · ...` |
| GREEN（实现后） | 同上 | 0 | **`24 passed`** |
| 语法 | `node --check frontend/app.js` | 0 | **`NODE_CHECK_EXIT=0`** |
| 全量前端静态回归 | `python -m pytest tests/frontend -q --confcutdir=tests/frontend $IGNORES` | 0 | **`326 passed`**（原 321 + 新增 5） |

精确命令：

```bash
cd /Users/wjh/ResearchAgent
node --check frontend/app.js
python -m pytest tests/frontend/test_evaluation_view_contract.py \
  tests/frontend/test_evaluation_metric_status_rendering.py \
  tests/frontend/test_evaluation_asset_versions.py \
  tests/frontend/test_evaluation_strategy_label_rendering.py -q --confcutdir=tests/frontend
IGNORES=$(grep -l playwright tests/frontend/*.py | sed 's|^|--ignore=|' | tr '\n' ' ')
python -m pytest tests/frontend -q --confcutdir=tests/frontend $IGNORES
```

### 10.4 人工验收「看得到」的效果（node 真实执行渲染，非静态猜测）

| 渲染位置 | 修复前 | 修复后 |
|---|---|---|
| 运行历史 meta | `[object Object] · rag-retrieval · main-case · ...` | `扩大召回（v1 / top_k=10 / reranker=off） · rag-retrieval · main-case · ...` |
| 对比下拉 option | `eval-xxx · [object Object] · main-case` | `eval-object-001 · 扩大召回（v1 / top_k=10 / reranker=off） · main-case` |
| 运行详情表「策略」 | `[object Object]` | `扩大召回（v1 / top_k=10 / reranker=off）` |
| 运行回看 head | `[object Object] · rag-retrieval · ...` | `扩大召回（v1 / top_k=10 / reranker=off） · rag-retrieval · ...` |

helper 边界：`{id:'topk-10'}` → `topk-10`；`{}` / `null` / `undefined` → `—`；`'legacy-string'` → `legacy-string`；全部 `typeof === 'string'`。

### 10.5 三项自查（regression-guard 前端 1–4 条）

1. **DOM 契约**：本次未新增/修改任何 class；脚本核对评测模块 17 个动态 class 在 CSS 中缺失 `[]`，行首裸 `.evaluation-*` 规则 0。
2. **资源版本号**：活跃 `app.js?v=74`（`styles.css?v=71` 未动）；`src="app.js?v=73"` 精确串恰好 1 份、`src="app.js?v=72"` 1 份，兼容注释块 14 个，全部 legacy marker 保留；全量回归 326 passed 佐证既有逐字断言不回归。
3. **XSS**：评测模块 `innerHTML` 0 次；新增代码仅纯函数 helper 与 4 处 `textContent` 赋值；残留裸插值 `String(run?.strategy` / `[run?.strategy, ` / `['策略', run.strategy]` 均为 `False`。
4. **CSS 作用域**：`styles.css` 本轮未写入，`#evaluation-view[hidden]` 保持存在，无全局污染。

### 10.6 风险与阻塞

- 无阻塞，后端未改动、无需 backend-dev 介入；真实浏览器 E2E 仍由主会话人工验收 / task-10 完成（本轮为静态契约 + node 真实渲染验证）。
- helper 对非字符串 `id`（如数字）返回 `—`；当前后端 `id` 恒为字符串，若后续改为数值型需放宽（超出本 Task 范围，未扩大改动）。

### 10.7 日志路径

`.codebuddy/agent-logs/spec-047/task-09/frontend-dev/20261110-030334.md`

### 10.8 最终文件行数（本轮修复后）

```
     870 frontend/index.html
    7822 frontend/app.js
    4251 frontend/styles.css（未改）
     237 tests/frontend/test_evaluation_strategy_label_rendering.py
```
