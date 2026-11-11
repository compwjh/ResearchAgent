# Spec047 追加范围二 · Task12 前端实施交接（评测指标 5 组 / 22 卡分组视图）

> 角色：`frontend-dev` ｜ 分派范围：**只改 frontend/** 与前端静态契约测试** ｜ 未触碰 `backend/**`，未跑后端 pytest。
> 依据：`docs/sdd/plans/047/task-12-evaluation-grouped-view.md`、`docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md` 追加范围二 §2.2–§2.5。
> 方法：TDD（先写静态契约红灯，再最小实现转绿）。

## 1. 改动文件与行数

| 文件 | 变更 | 说明 |
|---|---|---|
| `frontend/app.js` | +66 / -19 | 新增分组常量/兜底/统一渲染/对比行渲染；三处 renderer 复用；超时 120000→300000；等待文案 |
| `frontend/index.html` | +3 / -2 | `?v=74→?v=75`、`?v=71→?v=72`；新增 1 条兼容 marker |
| `frontend/styles.css` | +3 / -0 | 新增 3 条 `#evaluation-view` 作用域分组规则 |
| `tests/frontend/test_evaluation_metric_grouping.py` | 新增 352 行 / 15 用例 | 静态契约 + node 真实执行契约（文件名按能力命名，无 spec/task 编号） |

### app.js 新增/改造清单
- `EVALUATION_GROUP_ORDER`（`retrieval/intent/answer_quality/generation/safety/other` 固定顺序）
- `EVALUATION_GROUP_LABELS`（检索质量 / 意图识别 / 回答质量 / 生成可用性 / 安全 / 其它维度）
- `evaluationGroupOf(metric)`：无 `group`、未知 `group` 一律 `String(...)` 后兜底 `other`，不丢卡、不报错
- `appendEvaluationGroupedRows(container, rows, renderRow)`：按固定顺序分组，空组不渲染标题；标题 `createElement` + `textContent`；组内复用 `renderRow`
- `renderEvaluationDeltaRow(row)`：保留既有 `delta` / `label` / `null→—` 语义，按组输出
- `renderEvaluationMetrics` / `loadEvaluationRunDetail`（运行回看详情表）/ `renderEvaluationCompare` 三处统一调用分组函数，避免同页面两套逻辑
- `submitEvaluationScore`：`evaluationRequest('/api/evaluation/score', {...}, 300000)`（原 120000）
- `setEvaluationBusy` 等待文案补「多维打分可能耗时数分钟」

### 未改（既有契约保持）
`formatEvaluationMetricValue` / `renderEvaluationMetricCard` / `formatEvaluationStrategy` / `evaluationStatusLabel` / `EVALUATION_STATUS_LABELS` / `EVALUATION_ERROR_TEXT` / `evaluationRequest` 内部实现全部原样；`value=null` 仍显示 `—`，`degraded` / `needs_ground_truth` 卡片照常显示 `status` + `reason`。

## 2. 三项自查（逐条结论）

1. **DOM/CSS 双向一致：通过。** 新增 3 个 class `evaluation-metric-group` / `evaluation-metric-group-title` / `evaluation-metric-group-cards`，`app.js` 均以 `className = '...'` 动态渲染（L7611/7614/7618），`styles.css` 均有 `#evaluation-view .xxx` 作用域规则（L4251–4253）；反向 CSS 作用域 class 均能在 JS 找到。`cards` 用 `repeat(auto-fit, minmax(min(230px, 100%), 1fr))` + `min-width: 0`，窄屏换行不横向溢出；无行首裸 `.evaluation-*` 规则。
2. **`?v=N` 升级且旧 marker 保留：通过。** `app.js?v=75`（L863）、`styles.css?v=72`（L8）。`git diff` 显示 L7 / L862 / L864 / L865 / L867 / L868 全部 legacy / compatibility 注释**逐字未删**，仅新增一条兼容 marker。
   - 新增 marker：`<!-- Evaluation grouped-view compatibility markers retained for older static contracts: <script src="/assets/app.js?v=74"></script> href="/assets/styles.css?v=71" -->`
   - 原因：既有基线 `test_evaluation_strategy_label_rendering.py` 用正则锁定 `<script src="/assets/app.js?v=74"`、`test_evaluation_asset_versions.py` 锁定 `href="/assets/styles.css?v=71"` 恰好 1 次。故升版时必须把这两个旧 live 标签值逐字降级为兼容 marker，才能在**零改动既有 4 份基线**前提下继续全绿。
3. **无 `innerHTML`：通过。** 评测模块（L7352 起）`innerHTML` 计数 = 0。所有新增渲染走 `createElement` + `textContent` / `replaceChildren()`；`group` / `label` / `reason` / `detail.per_class` 等后端文本一律 `String(...)` 后 `textContent`；运行时契约用 `<script>alert(1)</script>` 样本断言其作为纯文本原样出现、未执行、无 `[object Object]`。

## 3. 超时对齐证据（R1(b)）

- `frontend/app.js` 中 `120000` 已 0 处、`300000` 1 处：`7694:    }, 300000);`（`submitEvaluationScore` 内 `evaluationRequest('/api/evaluation/score', ..., 300000)`）。
- 与服务端 `SCORE_TIMEOUT_SECONDS=300` 对齐，避免「前端报失败但 `save_run` 已落盘」跨端不一致。
- 等待文案：`7484: ...多维打分可能耗时数分钟...`。
- 未改 `evaluationRequest` 的 `AbortController` / `EVAL_SCORE_TIMEOUT` / `setTimeout` 机制。

## 4. 验证命令与真实输出

```
cd /Users/wjh/ResearchAgent && node --check frontend/app.js
  → NODE_CHECK_EXIT=0

.venv/bin/python -m pytest -q tests/frontend/test_evaluation_metric_grouping.py \
    tests/frontend/test_evaluation_view_contract.py \
    tests/frontend/test_evaluation_asset_versions.py \
    tests/frontend/test_evaluation_metric_status_rendering.py \
    tests/frontend/test_evaluation_strategy_label_rendering.py --tb=short
  → 39 passed in 0.65s, EXIT=0

.venv/bin/python -m pytest -q tests/frontend
  → 499 passed in 172.53s (0:02:52), PYTEST_EXIT=0
```

TDD 红灯记录（实现前仅新增测试文件）：
```
.venv/bin/python -m pytest -q tests/frontend/test_evaluation_metric_grouping.py --tb=no
  → 13 failed, 2 passed in 0.41s, EXIT=1
```
（2 个通过的是「模块无 innerHTML」「旧 marker 保留」这类保持型断言，实现后仍常绿。）

整目录首次前台运行曾触发工具层命令超时（56 个 py 文件含多个 node harness，累计约 172s），改用 `nohup` 后台运行 + 轮询日志取得真实输出与退出码，非测试失败。

## 5. 边界与未做

- 严格未触碰 `backend/**`；`git status` 中 `backend/**`、`docs/**`、`artifacts/**` 的改动为主会话 / `backend-dev`（Task11）等既有产出，与本分派无关。
- 未跑后端 pytest；未改 spec / 任务卡；未改 `.env`；未引入图表库或 vendor React；未发明新端点/字段/错误码。
- 未 push、未合 main、未 git commit、未改 git 配置。

## 6. 风险与遗留

- **兼容 marker 内含 `<script ...>` 字面串**：为喂给既有基线正则而写，位于 HTML 注释内、不会被浏览器执行；`test_evaluation_asset_versions.py::_live_versions` 用 `<script src="/assets/app.js?v=(\d+)"` 会把它也算作一个版本号（返回 `[75, 74]`），但该基线只断言 `[-1] >= 73`、`test_frontend_literature_map_contract.py` 只断言 `>= 59`，均通过。后续若有人把断言收紧为「`[-1]` 必须等于最大 live 版本」，需同步调整此 marker 写法——建议优先演进测试而非堆叠 marker。
- 分组标题文案与顺序为**前端冻结常量**，与 Task11 后端 `group` 枚举一致；若后端新增第 6 个枚举组，前端需同步 `EVALUATION_GROUP_ORDER` / `EVALUATION_GROUP_LABELS`（当前未知组一律兜底 `other` 已有测试保护）。
- 真实性依赖：22 卡来自后端 `metrics[]`（本分派用 22 条模拟数据 + node harness 验证渲染层，未做真实 API / 浏览器 E2E，属 Task13 范围）。

## 7. 进展日志

`.codebuddy/agent-logs/spec-047/task-12/frontend-dev/20261110-062722.md`

---

## 8. P1 修复记录（frontend-reviewer 判定 · 兼容 marker 污染 live-script 静态契约）

> 角色：`frontend-dev` ｜ 依据：`docs/sdd/reviews/047-frontend-metrics-review.md` §5.2/§5.4（结论「优先演进过时测试而非堆叠 marker」）+ 任务卡 §4.2「照 L865 写法」。
> 边界：**只改 `frontend/index.html`（1 行）与 `tests/frontend/**`（2 文件）**；未改 `app.js` / `styles.css` / `backend/**`，未跑后端 pytest，未 push / 合 main / git commit。

### 缺陷
`index.html:866` 兼容 marker 写成含**完整** `<script src="/assets/app.js?v=74"></script>` 字面串的注释，导致 `test_evaluation_asset_versions.py:60` 的 `re.findall(r'<script src="/assets/app\.js\?v=(\d+)"', INDEX)` 返回 `['75','74']`，把 v=74 误算成第二个 live script、`[-1]` 语义被污染。浏览器不执行注释内标签、XSS=0、旧断言宽松恰好仍过，但语义已污染，未来收紧即挂。

### 修复（最小增量，只加严不放宽）
1. **`frontend/index.html:866`**：marker 降级为纯属性片段（照 L865），去掉 `<script` 前缀 / `>` / `</script>`：
   `<!-- Evaluation grouped-view compatibility markers retained for older static contracts: src="/assets/app.js?v=74" href="/assets/styles.css?v=71" -->`
   其余所有 marker 注释（L7 / L862 / L864 / L865 / L867 / L868）**逐字保留**；live 标签仍为 `app.js?v=75`（L863）、`styles.css?v=72`（L8）。
2. **`tests/frontend/test_evaluation_strategy_label_rendering.py`**：演进 :99 过时写死正则 `re.search(r'<script src=...v=74"')` 为语义正确的「1 个纯属性 marker + 1 个 live」双断言并**加严**：`assert 'src="/assets/app.js?v=74"' in INDEX`、`count(...) == 1`、且 `re.findall(r'<script src="/assets/app\.js\?v=(\d+)"', INDEX) == ["75"]`（live 恰好 1 个且为 v=75）。
3. **`tests/frontend/test_evaluation_asset_versions.py`**：新增 `test_live_asset_versions_are_unique_and_current`，复用现成 `_live_versions` 断言 `== [75]` / `== [72]`。**未改 `_live_versions` 正则实现、未删任何既有断言**。

### TDD（先红灯后绿灯）
- 红灯（仅改测试、实现未动）：`2 failed, 23 passed in 0.47s, PYTEST_EXIT=1` —— 失败恰为 `[75, 74] == [75]` 与 `['75','74'] == ['75']`，23 个保持型断言未误伤。
- 绿灯（改 index.html:866 后）：`25 passed in 0.41s, PYTEST_EXIT=0`；实证 `app live=['75']`、`css live=['72']`、`注释内含 <script 的块数=0`。

### 验证命令与真实输出
```
cd /Users/wjh/ResearchAgent && node --check frontend/app.js        → NODE_CHECK_EXIT=0
.venv/bin/python -m pytest -q tests/frontend --tb=short（nohup 后台 + 轮询取真实退出码）
  → 1 failed, 499 passed in 140.22s (0:02:20), PYTEST_EXIT=1
```
- 唯一 FAILED：`test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions`，性能断言 `maxGestureWallMs < 1000`（实测 1013.70ms）。**与本改动无关**：该模块 docstring 明确「does not import or exercise the production frontend」，加载独立 fixture `tests/frontend/fixtures/literature_map_performance.html`（file://），不引用 `index.html`/`app.js?v`/`styles.css?v`/兼容性 marker；连续 5 次数值 1013.7 / 1010.4 / 1066.6 / PASS / 1048.1ms 在阈值上下波动、间歇通过，判定为**既有机器负载型 wall-clock flaky**。按纪律不隐瞒、不擅自放宽无关性能阈值，如实回报由主会话知悉。
- 本改动相关全部 PASS：3 份相关测试文件 `25 passed`；演进/新增两用例单独 `-v` 复跑 `2 passed`；全量 499 passed 含本改动全部断言。

### 三项自查
1. **DOM/CSS 双向一致**：本次**未动渲染**（`app.js` / `styles.css` 一行未改），既有分组 class 双向一致仍成立；git diff 中两文件的改动为 Task12 既有未提交产出，非本分派引入。
2. **`?v=N`**：`app.js?v=75`（L863）/ `styles.css?v=72`（L8）仍生效；L7 / L862 / L864 / L865 / L867 / L868 全部旧 marker 注释逐字保留；本次因未改 app.js/styles.css，按约定**无需**升版本号。
3. **无 `innerHTML`**：评测段 `grep -c innerHTML`（自「// ===== 评测视图」起）= 0；`index.html` 内 `innerHTML` = 0；`index.html` 注释内含 `<script` 字面串的注释块 = 0（修复前 1 → 修复后 0）。

### 风险与遗留
- 全量 pytest 的 1 个 failed 为与本改动隔离的既有 flaky 性能用例，非回归；本分派未修改该用例，交由主会话按需处置。
- 未改后端、未跑后端 pytest、未改 spec / 任务卡、未 git commit / push / 合 main。
