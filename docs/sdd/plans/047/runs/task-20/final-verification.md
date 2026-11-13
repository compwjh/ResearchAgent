# task-20 最终候选验证记录（Spec-047 追加范围五收口）

> **产出性质**：纯文档，由主会话代行落盘（三处留痕：本头部 / spec 追加范围五 §7 评审记录 / 状态台账 2026-11-12 收口条）。
> **基线**：`origin/main 42bbc188`（PR #5 squash）；**分支** `feature/spec-047-followup-cleanup`；**日期** 2026-11-12。
> **结论**：**PASS**，阻塞项 0，spec 状态 `实施中 → 已完成`。

## 1. 最终候选全量回归（仅在 Spec 收口阶段启动）

| 项 | 值 |
|---|---|
| 命令 | `.venv/bin/python -m pytest -q --cov=backend/app --cov-report=term-missing` |
| 退出码 | **0**（`docs/sdd/plans/047/runs/task-20/full-regression-coverage.exit`） |
| 通过数 | **`4559 passed, 2 skipped, 5 warnings, 69 subtests passed in 887.98s (0:14:47)`** |
| 失败数 | **0 failed / 0 error** |
| 覆盖率 | **`TOTAL 51890 8811 83.02%`**（`--cov=backend/app`，采集配置 `.coveragerc`） |
| 输出落盘 | `docs/sdd/plans/047/runs/task-20/full-regression-coverage.txt`（297 行，后台完整运行、非截断） |
| 阈值 | **未设 `fail_under`**；83.02% 为如实实测登记，未改阈值凑绿、未虚报 ≥80% |
| 与上一轮对比 | 追加范围四收口 `4557 passed` → 本轮 `4559 passed`，净 **+2**，恰对应新增 2 条 R1 静态契约用例；无测试丢失、无 skip / xfail 增加 |

**已知非阻塞输出**：`Failed to export span batch due to timeout, max retries or shutdown.`（Langfuse `:3000` 未启动，3 行 transient）、`DeprecationWarning: builtin type swigvarlink has no __module__ attribute`；均未影响 `EXIT=0`。全仓 `.venv/bin/python -m ruff check .` 为 `Found 185 errors` 的既有 lint 债务，非本轮引入，未越界修复；单文件 `ruff check conftest.py` EXIT=0。

## 2. 单端定向与静态检查

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---|---|
| JS 语法 | `node --check frontend/app.js` | 0 | 通过（本范围未改 app.js） |
| 前端单端回归 | `.venv/bin/python -m pytest -q tests/frontend/` | 0 | `616 passed in 129.77s` |
| 测试布局门禁 | `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| 4 个改名测试 | `.venv/bin/python -m pytest -q <4 files>` | 0 | `39 passed in 2.18s` |
| conftest 迁移后端定向 | `.venv/bin/python -m pytest -q tests/system/test_startup_warmup.py tests/kb/test_kb_routes.py` | 0 | `37 passed in 4.88s` |
| diff 空白检查 | `git diff --check` / `git diff HEAD --check` | 0 | 无错误 |
| 冲突标记 | `git diff HEAD --name-only` 逐文件扫描 `^<<<<<<< ` / `^=======$` / `^>>>>>>> ` | 0 | 变更文件内 **0** 命中；全仓通配扫描的 `=======` 命中均为 `vendor/`、`*.log`、历史报告中的分隔线，非冲突标记 |

## 3. 机械化校验（收口前后各跑一次）

| 校验 | 结果 |
|---|---|
| `grep -rn "结论：/" docs/sdd/specs/047-*.md` | **NONE**（无占位结论） |
| spec 引用的 `reviews/*.md` 存在性（047） | **0 断链**；全仓扫描另见 7 处 MISSING，全部来自历史 spec `013` / `016` / `037`，非本轮引入、不翻案 |
| spec 引用的 `plans/047/task-*.md` 存在性 | **0 断链** |
| `git diff HEAD --check` | EXIT=0 |

## 4. 运行时 / 浏览器 / 部署验证

- **真实浏览器**（Chromium，当前部署版本）：`docs/sdd/plans/047/runs/task-20/r1-computed-style.txt` — 22 张评测卡，`needs_ground_truth` 10 / `computed` 12；灰卡 `-value` / `-samples` / `-detail-row` 计算色 `rgb(90, 93, 102)`（对应 `#5a5d66`，对 `#f6f6f8` 独立复算 **6.0947:1 ≥ 4.5**）；computed 左边框仍绿 `rgb(40, 124, 67)`；live CSS 仅 `["/assets/styles.css?v=77"]`。截图 `task-20-gray.png`（159621 bytes）。
- **Playwright 观察偏差如实登记**：所选灰卡未取到 `.evaluation-metric-params` 节点，返回 `params:null`，不虚报为实测色值；静态 CSS 契约与部署侧 `gray_muted_strong_rules: 6` 已验证该规则存在。
- **部署验证**：`docs/sdd/plans/047/runs/task-20/deploy-verification.json` — `GET /api/health`、首页、`styles.css?v=77`、`research-tasks.js?v=26`、`/api/evaluation/options` **5×200**；`gray_muted_strong_rules: 6`、`search_layer_present: 3`；`CONCLUSION PASS`。收口前再次复核 `GET /api/health` → **200**。
- **服务访问**：`http://127.0.0.1:8000/`（端口 8000，启动命令见 `deploy/README.md`）。

## 5. 独立评审与双签（Gate 5）

| 角色 | 产出 | 结论 |
|---|---|---|
| `architect`（独立只读） | `docs/sdd/plans/047/runs/task-20/merge-review.md`（217 行） | 需求评审 **通过** / 技术评审 **通过** / 验收合并裁决 **批准收口**；P0=0 / P1=0 / P2=0；架构师签字 A（非自批） |
| `tester`（跨端验收总控） | `docs/sdd/reviews/047-acceptance-review.md` §17（1027 行起） | **通过**；契约 9/9、§5 8/8、集成 5/5；验收签字 R；既有 §1–§16 `shasum` 前后一致、逐字未变 |
| `frontend-reviewer` | `docs/sdd/reviews/047-followup-frontend-review.md`（214 行） | **APPROVE**；DOM 契约 / `?v=N` / XSS 三项 PASS；WCAG 复算 6.0947:1；P0=0 / P1=0 / P2=2（信息性，不阻断） |

**准备度差异如实登记**：`tester` 报告出具时点评为 **9/10**（第 10 项「状态台账 / 复盘 / 本地 commit」为时点快照，尚待闭环，非实现缺陷，且明确不回改 10/10）；`architect` 裁决按材料齐备评 **10/10 就绪**。两者均 **≥ 9/10 门槛**；本轮收口动作（双签、台账、复盘、commit）完成后第 10 项前置条件齐备，不修改 tester 既有评分。

**已知非阻塞项（7 项，均如实登记、不构成打回）**：全仓 185 个历史 lint 债务；Langfuse `:3000` span 导出超时；Playwright `params:null`；无真实 GitHub Actions workflow；平台 branch protection 未配置；覆盖率未设 `fail_under`；浏览器控制台其它视图 4×404。另有 pytest `5 warnings`。

## 6. 阻塞项

**0**。无 P0 / P1、无 API E2E 失败、无关键产物缺失、无引用路径断链、无冲突标记。

## 7. 收口边界

本范围闭环后仅**本地 `git commit`**；**不 push、不合 `main`、不 force push**；`origin/main` 保持 `42bbc188`。不新增 spec 编号 / `plans/048/`、不新增真实 CI workflow、不翻案历史评审与门禁。
