# spec-047 追加范围四 / task-17 不相关指标灰色弱化 — 实现自测结果

- 角色：`frontend-dev`（纯前端单端改动，未碰 `backend/**` / spec / 台账 / 评审 / task 文档）
- 基线：`feature/spec-047-unrelated-metric-greyout`，live `styles.css?v=75` / `app.js?v=77`
- 唯一实现输入：`plans/047/task-17-evaluation-irrelevant-metric-gray-style.md` + spec §13 Gate 2 裁决 + tech-review「追加范围四技术评审」

## 一、裁决口径（下游只认落盘文档）

- **V3 最终色值**：徽章 `background:#e9eaee` + **`color:#5f626c`**（WCAG 5.0630:1 ≥4.5）。spec §3 的 `#6b6e78`（4.2330:1）**作废、未使用**。
- V4/V6：`var(--muted-strong)` = `#5a5d66` / 底 `#f6f6f8`（6.0947:1 ≥4.5）。
- V1 `#c9cbd3`、V2 `#f6f6f8`、V5 `var(--muted)`；V7 samples/detail-row/params 保持 `--muted` 不重复声明。
- 精确 live 断言 **6 处**（非 §4 边界 6 的「4 处」）；9 处 `in INDEX` 冻结断言靠新增 marker 继续满足。

## 二、改动文件与行数（共 8 个）

| 文件 | 改动 |
|---|---|
| `frontend/styles.css` | +5 行（4406–4410）：5 条 `#evaluation-view .evaluation-metric-card[data-status="needs_ground_truth"]` 限定的灰化规则，写在基础规则 4391–4394 / 4395–4405 之后，层叠覆盖生效；无 `opacity`/`filter`/`display:none`/`visibility:hidden`，不改 `:root`，四条基础规则逐字保留 |
| `frontend/index.html` | `:8` live `styles.css?v=75 → ?v=76`（1 行）；末尾注释区 911 之后 `:912` +1 行 `<!-- Merge compatibility marker: href="/assets/styles.css?v=75" -->`（纯属性片段、不含 `<link`/`<script`、不在 `<head>`）；`app.js?v=77` 与全部 legacy marker 不动 |
| `tests/frontend/test_evaluation_asset_versions.py` | `:100`、`:118` 两处 `[75] → [76]` |
| `tests/frontend/test_evaluation_dataset_count_rendering.py` | `:87` `styles.css?v=75 → v=76` |
| `tests/frontend/test_evaluation_metric_grouping.py` | `:189` `styles.css?v=75 → v=76` |
| `tests/frontend/test_research_detail_actions_placement_contract.py` | `:223` `["75"] → ["76"]` |
| `tests/frontend/test_memory_return_global_contract.py` | `:210` `["75"] → ["76"]` |
| `tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py` | **新建 139 行**（能力命名、不含编号、位于 `tests/frontend/`）：§1.4 全部要点静态契约 |

6 处精确断言均为「仅改期望值」，未删断言 / 未改正则 / 未放宽；其余 9 处冻结断言、2 处范围断言、app.js 相关断言全部未动。`frontend/app.js` 零改动。

## 三、TDD 过程

1. 测试先行：新建契约文件 + 同步 6 处断言。
2. RED：聚焦跑新契约文件 → `6 failed, 3 passed`（EXIT=1），失败项恰为依赖 CSS 灰化规则 / `v=76` / marker 的用例；独立 Python 复算 WCAG 得 5.063 / 6.0947，验证公式与裁决值一致、非恒真。
3. 实现：追加 5 条 CSS 规则 + `index.html` 升版 + 末尾 marker。
4. GREEN：见下节验证命令。

## 四、验证命令（真实执行，逐条退出码与输出）

| # | 命令 | 退出码 | 输出 |
|---|---|---|---|
| 1 | `node --check frontend/app.js` | **0** | 无输出（语法通过） |
| 2 | `.venv/bin/python -m pytest -q tests/frontend/` | 工具超时未完整返回 | 原命令一次执行在约 46% 处触发工具固定超时，已跑部分全为 `.`（无 F）。改以**按文件分 3 批等价串行执行**覆盖全部 69 个文件：批1 `228 passed in 37.61s` EXIT=0；批2 `218 passed in 82.67s` EXIT=0；批3 `168 passed in 2.33s` EXIT=0 → **合计 614 passed / 0 failed** |
| 3 | `git diff --check` | **0** | 无输出（无空白错误） |
| 4 | `.venv/bin/python scripts/check_test_layout.py` | **1** | 报错 5 项**均为仓库既有、本任务未改动**的 tracked 文件：`tests/conftest.py`（位于 tests 根目录）、`tests/evaluation/test_task03_reproducibility.py`、`test_task04_idempotency.py`、`tests/observability/test_task05_decoupling.py`、`tests/platform/test_task06_identity_redaction.py`（文件名含交付编号）。佐证：这 5 个文件 `git diff --name-only` 为空；新建的 `test_evaluation_irrelevant_metric_gray_contract.py` 不含 delivery id、位于 `tests/frontend/` 子目录，**未出现在报错列表**。属既有基线问题，按「不改测试凑绿 / 不越界」未改动它们 |

> 说明：命令 2 的原样全量执行因工具超时窗口（约 60–90s，实测单批 82.67s 可完成、全量约 100s+）未能一次返回；分批执行与全量命令覆盖完全相同的 `tests/frontend/test_*.py` 集合，未使用 `-k` 过滤、未 skip/xfail、未改任何测试。命令 4 的失败与本任务改动无关，如实回报。

## 五、三项自查结论

1. **新 CSS 选择器与 DOM 契约对应（无新 class）**：5 条规则仅复用既有 `evaluation-metric-card` / `-status` / `-label` / `-value` / `-params > summary`；这些 class 在 `styles.css:4395/4396/4400/4404/4405` 定义、在 `app.js:7753/7758/7788/7824` 由 `createElement` 渲染（含 `card.dataset.status`），未新增任何 class。
2. **`styles.css` 已改 → 版本与断言同步**：`index.html:8` live 升 `?v=76`；6 处精确断言读回均为 76；新增 `v=75` marker 位于末尾注释区 `:912`（911 之后）、含 `href="/assets/styles.css?v=75"` 纯属性片段、不含 `<link`/`<script`、未插入 `<head>`（不污染 `map_header:298` 的 `active_version`），9 处冻结断言由其继续满足；`app.js?v=77` 保持。
3. **无 `innerHTML`、用户输入仍走 `textContent` / `input.value`**：本任务 `frontend/app.js` 零改动，未引入任何 `innerHTML`；灰化为纯 CSS，无动态文本渲染。

## 六、风险与阻塞

- 无功能阻塞、无后端依赖，未 push / 合 main / commit。
- 已知基线（非本任务引入、如实记录）：V5/V7 沿用 `--muted` 在灰底约 3.0365:1，属既有基线轻微退化，按 §13 R1 不用 `opacity`/`filter` 补救，移交 task-19 `getComputedStyle` 复核。
- 命令 2 全量一次执行受工具超时限制；命令 4 为既有基线 EXIT=1，均按边界如实回报、未改测试凑绿。
- 交接：task-18（frontend-reviewer + frontend-tester）单端回归、task-19 真实浏览器 E2E 与部署验证。

## 七、进展日志

`.codebuddy/agent-logs/spec-047/task-17/frontend-dev/20261112-060503.md`
