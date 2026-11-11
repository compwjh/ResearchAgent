# spec-047 merge-remote 前端落地自测结果（frontend-dev）

- 分支：`feature/spec-047-merge-remote`
- 角色：frontend-dev（ECC tdd-guide，最小改动 / 单次一事）
- 范围：仅两处改动；未触碰其它 310 个已 staged 的合并文件

## 一、改动清单（2 个文件）
1. `frontend/research-tasks.js`：由 `docs/sdd/plans/047/runs/merge-remote/tmp/resolved.js` 用 `cp` **原样**落地，4182 行；`cmp -s` 校验与产物逐字节一致（exit=0）；`git add` 已 staged（`M  `）。未重写/重构，未改动 resolved.js 本身。
2. `tests/frontend/test_research_detail_actions_placement_contract.py`：仅第 224 行 `assert live_app == ["74"]` → `["77"]`（连同该行 f-string 文案同步为 77），并在其上一行加 1 行说明注释；`git add` 已 staged。第 219/220 行 marker 断言、其它断言、`UNDECORATED` 正则、其它测试文件一律未动。

- staged 文件数：310 → 312（仅新增上述 2 个），其余未动。
- 命令退出码：`cp=0`、`git add=0`、`node --check=0`、`cmp=0`。

## 二、验证命令（真实执行，逐条退出码）
| # | 命令 | 退出码 | 输出摘要 |
|---|------|--------|----------|
| 1 | `node --check frontend/research-tasks.js` | 0 | 无输出（语法通过） |
| 2 | `node tests/frontend/test_research_task_search.js` | 0 | `research task search contract: PASS (B1/B2/B3/B4/B6/B7/B9/B10 pure functions)` |
| 3 | `node tests/frontend/test_research_view_stability.js` | 0 | `ok - research view stability behavior contract` |
| 4 | `node tests/frontend/test_report_action_race.js` | 0 | `Report action race contract: PASS (task isolation, rollback, delayed response ordering)` |
| 5 | `.venv/bin/python -m pytest -q <5 文件>` | 0 | `59 passed in 0.45s`（59/59 通过） |

- pytest 的 5 个文件：`test_research_task_search.py`、`test_research_detail_actions_placement_contract.py`、`test_research_view_stability_contract.py`、`test_frontend_button_affordance_contract.py`、`test_memory_return_global_contract.py`。
- 合计：5/5 命令退出码均为 0；Python 静态契约 59/59 通过；3 个 node 契约均 PASS。**无失败，未改测试凑绿**。
- 第 4 条命令 stderr 含 1 行 `[research-tasks] insertBefore degraded, falling back to appendChild Error: DOM detached`：该用例（testKeyedListRenderCannotEraseTaskListOrReport）刻意模拟 DOM detached 以触发降级分支，属预期日志，测试本身 PASS，非回归。

## 三、三项自查结论
1. **DOM 契约 / class**：`grep -n "research-open-session" frontend/styles.css` → 命中 3 处（3573、3583、3584，exit=0）。落地 JS 中该 class 用于「打开对应会话」按钮（1161 行）与「复制任务 ID」按钮（1172 行）。`research-task-card-id`（1167）、`research-copy-task-id`（1172）为 JS 内辅助定位类，按约定不需新增 CSS 规则；`grep -nE` 在 styles.css 中 0 命中（纯定位类，符合预期）。boot 第 4145 行同时绑定 `bindResearchTabs()` 与 `bindTaskSearch()`（937 / 1338 行定义）—— 主干 keyed-diff UX 重构与旧分支搜索层均在。
2. **资源版本号**：本次**未改** `app.js` / `styles.css` / `index.html` —— `git diff -- frontend/index.html frontend/app.js frontend/styles.css` 为空（工作区零改动）。故按约定**不需要**升 `?v=N`。`index.html` 现状：第 905 行生效 `<script src="/assets/app.js?v=77">`；第 911 行 `app.js?v=74` 为注释兼容 marker。这些（含合并把 `?v=74`→`?v=77`）是主会话合并分支**已 staged 的 310 个文件产物**，`git status` 显示三者为 `M  `（仅 staged、工作区干净），我原样保留、未触碰。
3. **XSS**：`grep -nE "innerHTML|outerHTML|insertAdjacentHTML|document\.write" frontend/research-tasks.js` → 0 命中（exit=1）；`grep -c "textContent"` → 129、`grep -c "input\.value"` → 3。用户输入只经 `textContent` / `input.value`（搜索输入 1339–1359 行 `applyTaskQuery(input.value, ...)`），无 `innerHTML` 拼接。

> 工具备注：Grep 工具 `outputMode: "count"` 在本环境对 `textContent` / `input.value` / `innerHTML` 一律返回 0，与 Read 直接读到的 `textContent`、`input.value` 矛盾，判定为计数模式异常；以上结论均以 Bash `grep` 复核为准，未据异常计数下结论。

## 四、风险与阻塞
- 无失败命令、无阻塞；原先 5 个前端回归失败已消除。
- 唯一提示：第 4 条命令 stderr 的降级日志为用例预期行为，非回归。
- 未做（按禁令）：git commit / push / 合 main / force push；未改 spec、台账、`backend/**`、`styles.css`、`app.js`、`index.html`、其它测试与其它 staged 文件。
- 待主会话：合并收尾与提交决策。

## 五、进展日志
`.codebuddy/agent-logs/spec-047/merge-remote/frontend-dev/20261112-034839.md`
