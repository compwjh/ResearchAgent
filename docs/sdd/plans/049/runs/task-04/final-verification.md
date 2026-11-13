# Spec-049 最终候选验证汇总

> 2026-11-13 ｜ 文档只写命令、退出码、通过数量、结论、阻塞项与产物路径。

## 1. 结论

**PASS / READY ｜ 阻塞项 0**。Gate 5 双签：`tester` 签字 R「通过 / READY」、`architect` 签字 A「批准收口」。

## 2. 命令与退出码

| 序 | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `.venv/bin/python -m pytest -q tests/frontend/test_literature_map_tabs_and_refresh_icon.py` | 0 | `12 passed` |
| 2 | `.venv/bin/python -m pytest -q tests/frontend/` | 0 | `628 passed` |
| 3 | `.venv/bin/python -m pytest -q tests/frontend/test_frontend_button_affordance_contract.py::test_button_count_is_frozen` | 0 | `1 passed`（基线 56） |
| 4 | `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_mobile_contract.py` | 0 | `EXIT=0`（390px `visibleMap.height >= 150`） |
| 5 | `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_map_header_actions_readability.py` | 0 | `EXIT=0` |
| 6 | `node --check frontend/literature-maps.js` | 0 | 语法通过 |
| 7 | `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| 8 | `git diff HEAD --check` | 0 | 无空白错误 |
| 9 | `python3 -c "import re,pathlib;s=pathlib.Path('frontend/index.html').read_text();print(re.findall(r'literature-maps\.js\?v=(\d+)',s)[-1],re.findall(r'literature-maps\.css\?v=(\d+)',s)[-1])"` | 0 | `47 34` |
| 10 | `grep -rn "in INDEX" tests/frontend \| wc -l` | 0 | 211 |
| 11 | `.venv/bin/python -m pytest -q --cov=backend/app --cov-report=term-missing` | **0** | `4571 passed, 2 skipped, 5 warnings, 69 subtests passed / TOTAL 51890 8820 83.00%` |
| 12 | `.venv/bin/ruff check . --no-cache --output-format concise` | 1（既有债务） | `Found 185 errors / 97 fixable`（与历史基线一致；本轮新增 B007 已修复） |
| 13 | `.venv/bin/python docs/sdd/plans/049/runs/task-04/browser_e2e.py` | 0 | `31/31 PASS / conclusion=PASS / failed_checks=[]` |
| 14 | curl `/api/health`、`/`、`/assets/literature-maps.js?v=49`、`/assets/literature-maps.css?v=36` | 0 | 4×200 |

## 3. 版本与冻结语义

| 项 | 值 |
|---|---|
| live JS | `literature-maps.js?v=49`（`frontend/index.html:903`） |
| live CSS | `literature-maps.css?v=36`（`:11`，不变） |
| `?v=77` | `app.js` / `styles.css` 不变 |
| 末尾 marker | `:918-919` 纯属性注释 `js?v=47` / `css?v=34`，不新增 / 不移动 |
| `re.findall(...)[-1]` | `47 34` |
| `in INDEX` 断言 | 211 行 |
| tabs 用例数 | 12（`grep -c "^def test_"`） |
| 按钮基线 | 56 |
| `v=48` 残留 | 0 命中 |

## 4. 真实浏览器 E2E

- 桌面 1440×900 + 窄屏 375×812；hash 路由 `#literature-maps-view` + DOM click 回退。
- 刷新主路径：点击后 `is-spinning` 加上；真实 API 响应结束后移除（`spin_not_fixed_700ms=true`）；连点 3 次 3×200、`spin_residue=0`；`no_unhandled_rejection=true`。
- `multi_click_3_real_requests=true`、`multi_click_no_spin_residue=true`、`mobile_touch_target_ge_44=true`（44×44）。
- assets：`js?v=49` / `css?v=36` 均 200；`v=47` / `v=34` 仅注释 marker 不加载。
- 首跑：`browser-e2e-run1.json` `28/29 FAIL`（`spin_not_fixed_700ms`），证据保留不动。判定口径 `0<elapsed<600` 与实测 3918.78 / 3698.1ms 不符，修正为 `|elapsed−700|>100` 并新增 2 条更严断言（29→31）；未改业务代码、未放宽断言。

## 5. 部署验证

`http://127.0.0.1:8000`：`/api/health` 200、`/` 200、`/assets/literature-maps.js?v=49` 200、`/assets/literature-maps.css?v=36` 200。首页 HTML live `<script>` = `v=49`、`<link>` = `v=36`，末尾 marker 存在。`CONCLUSION PASS`。

## 6. 真实 API 成功案例

`artifacts/spec-049-api-sample.md`：curl 原样请求 / 响应（含实体 ID）、最终状态（刷新后状态栏文案、`is-spinning` 已移除）、产物路径、调用约束与已知限制。

## 7. 评审

| 门禁 | 文档 | 结论 |
|---|---|---|
| Gate 2 需求 | `docs/sdd/reviews/049-requirement-review.md` | 通过（附意见），P0=0 / P1=0 / P2=4 |
| Gate 2 技术 | `docs/sdd/reviews/049-tech-review.md` | 通过（附意见），P0=0 / P1=0 / P2=5，C1–C10 共 10 条 |
| Gate 4 代码 | `docs/sdd/reviews/049-frontend-review.md` | `APPROVE`，C1–C10 10/10，P0/P1/P2 全 0 |
| Gate 5 验收 | `docs/sdd/reviews/049-acceptance-review.md` | 通过 / READY，边界 12/12、准备度 10/10（签字 R） |
| Gate 5 裁决 | `docs/sdd/plans/049/runs/task-04/merge-decision.md` | 批准收口，P0=0 / P1=0 / P2=0（签字 A） |

## 8. 已知非阻塞项（9 项，保持现状、零改动）

首跑 E2E FAIL 记录、Langfuse `:3000` transient 告警、其它视图 404、185 个历史 lint、无真实 CI workflow / branch protection、覆盖率未设 `fail_under`、窄屏 2px 余量、marker 既有脆弱性、10 个工作区未跟踪文件。未虚报「CI 全绿 / branch protection 通过 / 覆盖率门禁达标」。

## 9. 交付边界

省略 PR、直接快进推送远端 `main`；不 force push、不新建 PR。C 类 7 项零改动：`.github/` ABSENT、`.coveragerc` 无 `fail_under`、ruff 185、CSS 未改、未跟踪清单未清理、Langfuse 未启动、平台设置未改。

## 10. 收口机械化校验（`docs/sdd/SDD-GATE-CHECKLIST.md` §4）

| 项 | 结果 |
|---|---|
| ① `grep -rn "结论：/" docs/sdd/specs/` | 049 命中 0；另 2 行来自历史 spec 047 / 010 的说明文字（既有，非本轮引入） |
| ② reviews 引用存在性 | 049 引用 0 断链；另 7 行 `MISSING` 来自历史 spec 013 / 016 / 037（既有债务，本轮明确不动） |
| ③ 执行配置架构师行 | `自身（当前执行任务的 Agent，不写死模型代号）`，五行齐全 |
| ④ task 引用存在性 | 0 断链 |
| 049 全部 `.md` 引用 | 0 断链 |
| git 冲突标记 | `<<<<<<<` / `>>>>>>>` 命中 0；`=======` 命中 2 行均为 `full-regression.txt` 的 pytest 分隔线（误报） |
| 状态一致性 | spec / README / task-02/03/04 全部 `已完成` |

## 11. 引用路径

`docs/sdd/specs/049-known-nonblocking-followup-cleanup.md`（`已完成`）、`docs/sdd/plans/049/README.md`、task-02/03/04（`已完成`）、`runs/decision-ledger.md`、`docs/sdd/retro/2026-11-13-spec049-nonblocking-followup-closure.md`、`docs/sdd/spec-status-changelog.md`（`实施中 → 已完成`）、`artifacts/spec-049-nonblocking-manual-e2e.md`。

## 12. 收口执行结果

| 项 | 结果 |
|---|---|
| 本地提交链 | `feat(spec-049): 定案已知非阻塞项并修正刷新旋转反馈`（32 文件）→ `docs(spec-049): 回填验收报告签字 A 结论`（1 文件）→ 收口一致性修正（签字栏表述 + 本文件 §12）；以 `git log` 为准 |
| 本地 `HEAD` / `origin/main` / 远端 `main` | 三者一致 |
| 远端引用更新 | `PATCH git/refs/heads/main`，`force=false`，两次均 `sha_match=true` / `tree_match=true` |
| 签字栏 | 签字 R（`tester`）与签字 A（`architect`）在 `049-acceptance-review.md` §7 与 `merge-decision.md` §2 并列、非自批 |
| 部署复验 | `/api/health`、`/`、`js?v=49`、`css?v=36` 均 200；ruff `Found 185 errors` 保持基线 |

`merge-decision.md` §3 的「待回填」与 `049-requirement-review.md:84` 的「保持待评审至 Gate 5」为评审当时快照，按不翻案原则逐字保留；实际收口动作见 spec「任务计划」「评审记录」「变更日志」与本文件 §12。
