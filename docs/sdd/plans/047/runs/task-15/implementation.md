# task-15 前端实现交接报告（spec-047 追加范围三 · 紧凑可展开指标卡）

> 角色：`frontend-dev` ｜ 日期：2026-11-11 ｜ 关联任务卡 `plans/047/task-15-evaluation-compact-cards.md`
> 范围纪律：只改 `frontend/**` 三份文件与 `tests/frontend/**` 静态契约测试；**未改** `backend/**`、spec / reviews / 状态台账 / `.env`；**未跑后端 pytest**；未 push、未合 main、未改原六块与追加范围二历史结论。

## 1. 改动文件与行数

| 文件 | 改动内容 | 行数（删/加） |
|---|---|---|
| `frontend/app.js` | ① `renderEvaluationMetricCard` 字段分层重构（关键信息留 `<details>` 外、其余参数按后端实际 key 遍历进原生 `<details>/<summary>` 默认收起、无参数不渲染空容器）② `setEvaluationBusy` 等待文案补「100 条样本真实打分（批量生成 + 批量判官，多维打分可能耗时数分钟）」并保留「评分中…」「正在」「多维打分可能耗时数分钟」③ `submitEvaluationScore` `300000 → 900000` | 函数体 16→31 行 + 2 处单行替换 |
| `frontend/styles.css` | 三处卡片网格 `230→160px` / `gap 12→8px`；card `padding 14→8px` / `gap 8→5px`；value `22→18px`；label `13→12px`；分数条 `8→6px`；新增 3 条 `#evaluation-view` 作用域规则（`params` / `summary` / `param-row`） | 7 删 / 10 加 |
| `frontend/index.html` | live `app.js?v=75→76`（L863）、`styles.css?v=72→73`（L8）；新增 1 条含 `app.js?v=75` 的纯属性片段兼容 marker（L864）；全部 legacy marker 保留 | 2 删 / 3 加 |
| `tests/frontend/test_evaluation_asset_versions.py` | 精确断言 `[75]/[72] → [76]/[73]`（原 L99-100）；新增 `test_new_compatibility_marker_is_pure_attribute_fragment` | 2 删 / 20 加 |
| `tests/frontend/test_evaluation_metric_status_rendering.py` | 新增 `import re` + `CSS`/`INDEX` 句柄 + 8 条紧凑卡片/折叠静态契约 | 0 删 / 121 加 |
| `tests/frontend/test_evaluation_metric_grouping.py` | 三处精确断言同步（网格 160px、版本 76/73、超时 900s），保留全部 legacy marker 断言 | 8 删 / 16 加 |
| `tests/frontend/test_evaluation_strategy_label_rendering.py` | live app.js 版本锁 `75 → 76`、补 `v=75` 纯属性 marker 断言 | 2 删 / 4 加 |

> 说明：`grouping` / `strategy_label` 两个验收文件也锁死当前 live 版本(75/72)与 `300000`，升版必然打断，故同步更新期望值（属静态契约测试域，非历史结论翻案）。测试文件名按能力命名、无 spec/task 编号；未新增测试文件，全部扩展在验收命令覆盖的 4 文件内。

## 2. 字段分层落地（spec §2.3 / §5）

- **始终可见（不随折叠收起）**：`label`、`value`（`formatEvaluationMetricValue` 规则逐字不动，`null → —`、非 computed 显示原因）、`status`、`sample_count`、`detail.reason`、`detail.judge_sample_count`（与 `sample_count` 不一致时在 `<details>` 外额外显示「判官样本数」）、5 个分组标题、对比页 `delta`。
- **默认收起**：其余 `detail.*` 用 `Object.entries(...).filter(([key]) => key !== 'reason')` **按后端实际返回 key 全量遍历**（不白名单、不丢弃新增字段），逐项 `createElement('div')` + `textContent = String(key) + ': ' + <String(...)/JSON.stringify(...)>`；`<details class="evaluation-metric-params">` **不设展开属性**，`<summary>参数与明细</summary>`；`paramEntries.length === 0` 时不渲染空容器（含「只有 reason」与「无 detail」）。
- `degraded` / `needs_ground_truth` / `unavailable` 照常显示 status + reason，不隐藏、不跳过、不把 `null` 渲染成 `0`；`formatEvaluationStrategy` / `EVALUATION_GROUP_ORDER` / 分组渲染 / compare 按组 delta / 历史 run 详情逻辑**逐字未动**，历史无新字段的 run 不丢卡、不报错（分组 runtime harness 的 22 卡 + legacy/unknown 兜底 + XSS reason 断言全通过）。

## 3. 三项自查结论（逐条）

1. **新增 class 与 CSS 双向一致、作用域正确** ✅
   `evaluation-metric-params`(app.js:7577)、`evaluation-metric-param-row`(app.js:7583) 与 `styles.css:4233-4235` 双向命中；既有 `evaluation-metric-detail` / `evaluation-metric-detail-row` 亦双向存在；全部新增规则以 `#evaluation-view` 前缀限定，无裸 `^\.` 全局选择器（`test_new_param_classes_are_bidirectional_and_scoped`、`test_group_css_classes_are_bidirectional_and_scoped` 均通过）。
2. **`?v=N` 已升级且旧标记保留、新 marker 为纯属性片段** ✅
   `index.html:8` `styles.css?v=73`、`index.html:863` `app.js?v=76`；L862 / L865-870 全部 legacy marker 逐字保留；L864 新增 `<!-- Evaluation compact-cards compatibility marker: src="/assets/app.js?v=75" href="/assets/styles.css?v=72" -->` —— 注释内**只含属性片段**、无 `<script` / `<link` 标签字面串，故不会被 `_live_versions` 正则误算为第二个 live 标签（未重演追加范围二 P1）。`test_live_asset_versions_are_unique_and_current`(`[76]/[73]`)、`test_new_compatibility_marker_is_pure_attribute_fragment`、strategy_label `live == ["76"]` 全通过。
3. **无 `innerHTML`** ✅
   评测模块（`app.js:7352 // ===== 评测视图` 起）零 `innerHTML`（全文件 17 处均在 L7352 之前的其它模块）；新增渲染全部走 `createElement` / `createElementNS` / `textContent` / `replaceChildren()`；`label` / `reason` / `detail.*` 一律 `String(...)`（对象值 `JSON.stringify`）后 `textContent`，含 `<script>` 的样本纯文本展示。`test_evaluation_module_never_uses_innerhtml`、分组 runtime harness 的 `XSS_REASON` / `<script>` 断言均通过。

## 4. 验证命令 / 退出码 / 通过数（真实输出）

| 命令 | 退出码 | 输出 |
|---|---|---|
| `node --check frontend/app.js` | `0` | 无输出（语法通过） |
| `.venv/bin/python -m pytest -q tests/frontend/test_evaluation_asset_versions.py tests/frontend/test_evaluation_metric_status_rendering.py tests/frontend/test_evaluation_metric_grouping.py tests/frontend/test_evaluation_strategy_label_rendering.py` | `0` | `.......................................... [100%]` / `42 passed in 0.40s` |
| `.venv/bin/python -m pytest --collect-only -q tests/frontend/`（额外） | `0` | `509 tests collected in 0.16s` |
| `.venv/bin/python -m pytest -q tests/frontend/`（额外全量稳健性回归，后台执行） | `0` | `509 passed in 153.66s (0:02:33)`；`0` failed / `0` error |

- **TDD 轨迹**：先改测试跑 RED `EXIT_CODE=1 / 13 failed, 29 passed`，再改实现跑 GREEN `EXIT_CODE=0 / 42 passed`；最终全量 `509 passed`。

## 5. 风险与阻塞

- **跨端依赖**：本任务仅前端静态契约；`900000` 与服务端 `SCORE_TIMEOUT_SECONDS=900.0` 的收敛、≥100 条样本真实出分、批量化 Go/No-Go 基准由 `backend-dev`(task-14) 负责。本任务未跑后端 pytest、未验证真实 API 响应；`detail` 新增字段（`judge_sample_count` / `batch_count` / `total_items` 等）由前端按 key 全量遍历自动承接，无需后端为本任务改接口。
- **未做真实浏览器 E2E**：「22 张卡一屏可见大部分、无横向溢出」仅由 CSS 尺寸 + `overflow-wrap:anywhere` 静态契约保障；真实浏览器截图 / snapshot 属 task-16。
- **全量前端回归**：509 测试后台执行完成 `509 passed in 153.66s`、0 failed / 0 error；前台单次被工具超时截断仅因大量 node harness 子进程拖长耗时，属执行环境限制、非断言失败。Grep 全 `tests/frontend/` 确认**没有其它文件仍锁旧版本/旧超时/旧尺寸**（12 处旧值命中全在本任务改的 4 文件，且均为「旧值不得残留」否定断言或 `v=75` 纯属性 marker 保留断言），故升版不会打断其它静态契约。
- **文案兼容**：等待文案保留「评分中…」「正在」「多维打分可能耗时数分钟」三个字面，未打断 `test_evaluation_metric_status_rendering.py:116-122` 与 grouping 的 busy 态断言。
- **阻塞**：无；未发现需后端接口改动，无需转派 `backend-dev`。

## 6. 验收缺口补丁：选项区显示真实样本数（追加范围三 · task-15 补丁）

> 背景：主会话 Chromium 实测 `runs/task-16/eval-initial.yaml:623-628` 显示评测集下拉只有 3 个 label、未显示样本数；spec §8 ① 要求「选项区显示该评测集真实样本数 ≥100」。`GET /api/evaluation/options` 已返回 `datasets[].item_count`（实测 128 / 120 / 120），但 `fillEvaluationSelect` 对象分支只用 `label/name/id`。本补丁为**已确认范围内的最小增量**：不新增 spec、不改需求 / 数据模型 / 公开接口 / 用户行为；策略 / 模型下拉逐字不变；`option.value` 仍是 `item.id`，`POST /api/evaluation/score` 请求体不受影响。

### 6.1 改动点（`文件:行号`）

| 文件 | 行号 | 改动 | 行数（删/加） |
|---|---|---|---|
| `frontend/app.js` | `fillEvaluationSelect` 对象分支 `app.js:7450-7452` | `item.item_count` 为**非负整数**（`Number.isInteger(...) && >= 0`）时，把 `（N 条样本）` 追加到 `option.textContent`；原 `option.value`(7448)、`option.textContent`(7449) 两行**逐字不动**，字符串分支(7444-7446)不动 | 0 删 / 3 加 |
| `frontend/index.html` | L863 / L864 | live `app.js?v=76 → ?v=77`；新增 L864 含 `app.js?v=76` 的兼容 marker，纯属性片段 `src="/assets/app.js?v=76" href="/assets/styles.css?v=73"`（照既有 compact-cards 纯属性片段 marker 写法，注释内**无** `<script` / `<link` 字面串）；`styles.css?v=73`(L8) 与全部 legacy marker 保留 | 1 删 / 2 加 |
| `tests/frontend/test_evaluation_asset_versions.py` | L99 / L117 | 精确断言 `[76] → [77]`（2 处） | 2 删 / 2 加 |
| `tests/frontend/test_evaluation_metric_grouping.py` | L187-188 | 函数名 `...bumped_to_76_and_73 → ...77_and_73`、live 标签 `v=76 → v=77` | 2 删 / 2 加 |
| `tests/frontend/test_evaluation_strategy_label_rendering.py` | L105 / L108 | 注释 + `live == ["76"] → ["77"]`（含消息 `v=76 → v=77`） | 2 删 / 2 加 |
| `tests/frontend/test_evaluation_dataset_count_rendering.py` | 新建 219 行 | 按能力命名、无编号。2 条静态（对象分支读 `item_count` + 文案带「条样本」+ `Number.isInteger` 校验 + `option.value` 仍是 id + 零 `innerHTML`；live `v=77` 与 `v=76` 纯属性 marker）+ 3 条 runtime（Node harness 走 `loadEvaluationOptions()` 真实路径：评测集「（128 条样本）」且 ≥100、`option.value` 仍是 id、策略/模型文本不变、缺/非整数/负数/`null` 不追加、整数 `0` 合法追加、字符串项逐字不变） | 0 删 / 219 加 |

> `300000`（三处 `not in` 反向断言）、`900000` 超时、等待文案「评分中…」/「正在」/「100 条样本真实打分」、卡片字段分层、`<details>` 折叠、CSS 尺寸、5 组渲染、compare 按组 delta、历史 run 兼容**全部逐字未动**。本补丁所有写操作目标仅 `app.js` / `index.html` / 上述 4 个 `tests/frontend/*.py` / 本文件 / 进展日志，**未改 `frontend/styles.css`**（`git status` 中该文件的 `M` 为 task-15 前序未提交累积改动，本补丁未触碰）。

### 6.2 三项自查结论

1. **DOM 契约 / class 双向一致** ✅ 本次未新增 / 修改任何 class 名（改动仅 `option.textContent` 文本赋值），`frontend/styles.css` 零改动；既有 class 双向契约由 `test_group_css_classes_are_bidirectional_and_scoped` / `test_new_param_classes_are_bidirectional_and_scoped` 继续通过保障。
2. **资源版本号** ✅ `index.html:8` `styles.css?v=73`（不动）、`index.html:863` `app.js?v=77`；`grep -n 'app.js?v=76' frontend/index.html` 仅命中 L864 注释行，且该行不含 `<script` / `<link`，故 `_live_versions("app.js") == [77]`、strategy_label `live == ["77"]` 通过，未重演 live-script 污染 P1；全部 legacy marker 逐字保留，`<!--` 数量只增不减。
3. **XSS** ✅ `fillEvaluationSelect` 全部文本走 `String(...)` + `textContent`（新增后缀仅插入经 `Number.isInteger` 校验的整数），零 `innerHTML`（评测模块自 `app.js:7352 // ===== 评测视图` 起 `innerHTML` 计数 = 0）；`test_evaluation_module_never_uses_innerhtml` 与新增 `test_object_branch_appends_item_count_text_and_keeps_id_value` 通过。

### 6.3 命令 / 退出码 / 通过数（真实输出）

| 命令 | 退出码 | 输出 |
|---|---|---|
| `node --check frontend/app.js` | `0` | 无输出（语法通过） |
| `.venv/bin/python -m pytest -q tests/frontend/test_evaluation_asset_versions.py tests/frontend/test_evaluation_metric_status_rendering.py tests/frontend/test_evaluation_metric_grouping.py tests/frontend/test_evaluation_strategy_label_rendering.py` | `0` | `.......................................... [100%]` / `42 passed in 0.89s` |
| 上述 4 文件 + `tests/frontend/test_evaluation_dataset_count_rendering.py`（额外，覆盖新增契约） | `0` | `............................................... [100%]` / `47 passed in 1.23s` |

- **TDD 轨迹**：先写 / 同步测试跑 RED `8 failed, 39 passed in 0.65s`（`EXIT_CODE=1`），再改实现跑 GREEN `42 passed` / `47 passed`（`EXIT_CODE=0`）。
- **未跑**：后端 pytest、真实 HTTP API 打分、服务重启 / 杀进程（主会话后台真实 API E2E PID 51629 未受影响）；未 push、未合 main、未改 spec / reviews / 状态台账 / gold 集 / `benchmark_100.py` / `go-no-go*` / `runs/task-16/` 证据文件。
- **阻塞**：无；`/api/evaluation/options` 已返回 `item_count`，无需后端接口改动，无需转派 `backend-dev`。
