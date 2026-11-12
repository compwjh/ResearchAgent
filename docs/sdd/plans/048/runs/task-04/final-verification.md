# Spec-048 最终候选验证记录（收口）

> **产出性质**：纯文档，由主会话代行落盘（三处留痕：本头部 / spec 变更日志 / 状态台账 2026-11-13 收口条）。
> **基线**：`origin/main 42bbc188`；**分支** `feature/spec-047-followup-cleanup`；**日期** 2026-11-13。
> **结论**：**PASS**，阻塞项 0。

## 1. 最终候选全量回归（Spec 收口阶段，修复与二次升版后重跑）

| 项 | 值 |
|---|---|
| 命令 | `.venv/bin/python -m pytest -q --cov=backend/app --cov-report=term-missing` |
| 退出码 | **0**（`docs/sdd/plans/048/runs/task-04/full-regression-final.exit`） |
| 通过数 | **`4571 passed, 2 skipped, 5 warnings, 69 subtests passed in 895.87s (0:14:55)`** |
| 失败数 | **0 failed / 0 error** |
| 覆盖率 | **`TOTAL 51890 8815 83.01%`**（未设 `fail_under`，如实登记、不虚报 / 不改阈值凑绿） |
| 输出落盘 | `docs/sdd/plans/048/runs/task-04/full-regression-final.txt`（296 行） |
| 与上一轮对比 | Spec-047 收口 `4559 passed` → 本轮 `4571 passed`，净 **+12**，恰对应新增的 12 条 tab / 图标静态契约用例；无测试丢失、无 skip / xfail 增加 |

**前一次回归如实记录**：`full-regression-coverage.txt` / `.exit` = **EXIT=1**（`2 failed, 4569 passed`），失败为 B1 冻结基线未同步与 B2 390px 窄屏几何；按「失败先定向修复，再重新运行全量回归」已在当前 Task 修复并重跑通过，原失败记录保留不翻案。

## 2. 单端与静态检查

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---|---|
| JS 语法 | `node --check frontend/literature-maps.js` | 0 | 通过 |
| 前端单端全量 | `.venv/bin/python -m pytest -q tests/frontend/` | 0 | **`628 passed in 128.09s`**（复审实测） |
| B1 定向 | `pytest -q tests/frontend/test_frontend_button_affordance_contract.py::test_button_count_is_frozen` | 0 | `1 passed`（基线 58→56 精确同步） |
| B2 定向 | `pytest -q '...test_real_graph_detail_stays_in_viewport_without_growing_canvas[390]'` | 0 | `1 passed`（`visibleMap.height` 144→152） |
| 新增静态契约 | `pytest -q tests/frontend/test_literature_map_tabs_and_refresh_icon.py` | 0 | `12 passed` |
| 测试布局门禁 | `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| diff 空白 | `git diff HEAD --check` | 0 | 无错误 |

**缺陷修复链路**：`docs/sdd/plans/048/runs/task-04/frontend-regression.md`（初判 FAIL，原记录保留）→ `defect-fix.md`（B1/B2 修复）→ `version-bump.md`（CSS 内容变化后二次升版 `v=35 → v=36`）→ 同文件末尾「复审结论 **PASS**」。`frontend-reviewer` 在 `048-frontend-review.md` 末尾追加「二次升版复核 **APPROVE 保持**」。

## 3. 真实浏览器 / API / 部署验证（当前部署版本）

- **Chromium E2E**：`docs/sdd/plans/048/runs/task-04/browser-e2e.json` — **18/18 PASS**（桌面 1440×900 + 375×812 窄屏）；tab 默认态 / 切换不重建表单 / 表单值往返保留 / 刷新按钮在画布工具区且无可见文字 / `aria-label="刷新状态"` / 点击 `is-spinning` / header 旧「新建地图」按钮移除 / 其余 5 个作业按钮保留 / live `css?v=36` 与 `js?v=48` / 窄屏 ≥44px 触摸目标。**88 个真实 API 响应**被捕获（含 `/api/literature-maps/tags` 200、`/api/papers/imports` 实体 `1a76e369-…`、`/api/research-notifications` 实体 `106358f6…`），非 mock、非内部函数。
- **截图**：`map-tabs-desktop.png`、`map-tabs-mobile.png`。
- **部署验证**：`deploy-verification.json` — `/api/health`、首页、`/assets/literature-maps.css?v=36`、`/assets/literature-maps.js?v=48` **4×200**；INDEX live 版本正确、2 条纯属性 marker 仍在末尾注释区；`CONCLUSION PASS`。
- **服务访问**：`http://127.0.0.1:8000/`（端口 8000；`./deploy/start.sh -d`，端口占用时 `PORT=8300 ./deploy/start.sh -d`）。

## 4. 版本与冻结语义

| 资源 | 最终生效 | 说明 |
|---|---|---|
| `literature-maps.js` | `v=48` | 首次升版后未再改动 |
| `literature-maps.css` | `v=36` | 缺陷修复改 CSS 内容后二次升版 |
| `app.js` / `styles.css` | `v=77` / `v=77` | 本 spec 未动 |
| 末尾 marker | `src="...js?v=47"` / `href="...css?v=34"` | 位置与内容未变，保证 `re.findall(...)[-1]` 仍为 47/34，13 处 `in INDEX` 冻结断言继续通过 |

## 5. 评审与签字

| 角色 | 产出 | 结论 |
|---|---|---|
| `architect`（Gate 2） | `docs/sdd/reviews/048-requirement-review.md`、`048-tech-review.md` | 需求 / 技术均**通过（附意见）**，P0=0/P1=0，强制约束 C1–C10 |
| `frontend-reviewer` | `docs/sdd/reviews/048-frontend-review.md`（含二次升版复核） | **APPROVE 保持**，三项必查 PASS、C1–C10 10/10、P2=1 |
| `frontend-tester` | `docs/sdd/plans/048/runs/task-04/frontend-regression.md`（含复审） | 复审 **PASS**，阻塞项 0 |
| `tester` | `docs/sdd/reviews/048-acceptance-review.md` | 验收签字（见该报告） |
| `architect`（Gate 5） | `docs/sdd/plans/048/runs/task-04/merge-decision.md` | 合并裁决签字（见该报告） |

## 6. 已知非阻塞项（如实登记，不虚报全绿）

1. `is-spinning` 旋转反馈使用 700ms 定时器而非请求结束回调（P2 观察项，功能与安全无缺陷）。
2. Langfuse `:3000` span 导出 transient 告警；浏览器控制台其它视图 404。
3. 全仓 `ruff check .` 185 个历史 lint 债务，非本轮引入。
4. 无真实 GitHub Actions workflow、平台 branch protection 未配置；覆盖率 `83.01%` 为本地实测，未设 `fail_under`。
5. 初判单端 FAIL 与首次全量回归 EXIT=1 已修复并重跑通过，原记录保留。
6. B2 窄屏余量 `152 ≥ 150`（2px），后续若再增高 tab / header 需复核。

## 7. 阻塞项

**0**。无 P0 / P1、无 API E2E 失败、无关键产物缺失、无引用路径断链、无冲突标记。

## 8. 交付边界

按用户 2026-11-13 当次指示：闭环后**省略 PR 流程**，以 fast-forward 直接推送远端 `main`；**不 force push、不新建 PR**；Spec-047 追加范围五成果（`c6abb7a6`）随同一交付一并推送。
