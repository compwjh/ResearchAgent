# 复盘：Spec-047 追加范围五遗留项清理收口（2026-11-12）

> 纯文档复盘，由主会话代行落盘（三处留痕：本头部 / spec 追加范围五 §7 / 状态台账 2026-11-12 收口条）。
> 分支 `feature/spec-047-followup-cleanup`；基线 `origin/main 42bbc188`（PR #5 squash）；闭环后仅本地 commit，不 push / 不合 main / 不 force push。

## 1. 为什么会有这个追加范围

追加范围四收口时逐条登记了 5 类遗留（缓存版本、P2 文案、测试布局、灰卡 R1 对比度、覆盖率可观测）与 3 项门禁偏差（无真实 CI workflow、覆盖率未量化、branch protection 未配置）。用户「灰色弱化成果只在本地分支 要做。遗留你也改一下」+ 连续「请继续」构成执行授权。按「不新增 spec 编号」的既有约束，把修复设计并入 047 文末追加范围五，不新建 `plans/048/`，不翻案历史四份评审签字。

## 2. 实际做了什么

| 项 | 动作 | 结果 |
|---|---|---|
| A | `research-tasks.js?v=25 → 26` + `v=25` 纯属性 marker | 5 处 `in INDEX` 冻结断言继续通过，缓存风险消除 |
| B | 2 处失败文案「为 75 → 为 76」、函数名 / 注释同步 | 诊断信息不再误导 |
| C | 4 个 `test_taskNN_*.py` 按能力改名；`tests/conftest.py` fixture 等价迁到根 `conftest.py` | `check_test_layout.py` 从 EXIT=1 / 5 项违规 → `test layout: ok` / EXIT=0 |
| D | 灰卡 4 类文字色仅在 `[data-status="needs_ground_truth"]` 下改 `var(--muted-strong)`；`styles.css?v=76 → 77` + `v=76` marker + 6 处精确断言同步 + R1 静态契约 | 对比度 3.0365:1 → **6.0947:1**；computed 绿 / degraded 橙 / unavailable 红逐字未变 |
| E | 新增 `.coveragerc` + 本地覆盖率实测 | `TOTAL 83.02%` 如实登记；**未设 `fail_under`**、未虚报 |

分工真实发生：`frontend-dev`（A/B/D）、`backend-dev`（C）、主会话（E1 / 回归 / 验证 / 收口）；收口阶段 `architect`（需求 + 技术 + 合并裁决）、`tester`（§17 验收签字）、`frontend-reviewer`（APPROVE）三次独立分派，非自批。无 `junior-dev`。

## 3. 证据

- 全量回归：`4559 passed, 2 skipped, 69 subtests passed / EXIT=0 / 887.98s`，覆盖率 `83.02%`（`runs/task-20/full-regression-coverage.txt`、`.exit`）。较上一轮 `4557` 净 +2，对应 2 条新增 R1 契约用例，无测试丢失。
- 单端：`616 passed`（前端）、`39 passed`（改名测试）、`37 passed`（后端定向）、布局 EXIT=0、`node --check` EXIT=0。
- 运行时：Chromium 22 卡 / 10 灰 / 12 computed，灰卡 `rgb(90, 93, 102)`；部署 5×200 `PASS`；收口前 `/api/health` 200。
- 门禁：三份评审真实结论 + 双签并列；`git diff --check` 0、变更文件冲突标记 0、047 引用路径 0 断链、spec 无「结论：/」占位。
- 汇总见 `docs/sdd/plans/047/runs/task-20/final-verification.md`。

## 4. 踩坑与经验

1. **`--delete-branch` 会切走工作区**：PR #5 合并后本地被切回旧 `main 440d9e33`，一度基于旧树勘察。恢复顺序应为：先比对并备份未跟踪日志 → 从 `origin/main` 新建分支 → 再继续。9 个历史日志已备份到 `.codebuddy/backup-untracked-047/`，未丢失。
2. **`git mv -f` 会静默删掉目标文件里的既有 fixture**：根 `conftest.py` 已含 5 个 `autouse=True` fixture，不能整体覆盖。改用「等价迁移 + `diff -u` 校验 + `git rm`」，git 记录为 `M + D` 而非 rename，属预期。
3. **纯属性 marker 的位置是硬约束**：marker 必须放 `index.html` 末尾注释区且不含 `<script` / `<link` 字面串；插进 `<head>` 会污染 `active_version` 取首个 `styles.css?v=` 的语义。这一约束在新旧两轮 marker 上都验证了。
4. **前台长测试会触发工具超时**：`pytest -q tests/frontend/` 跑到 46% 被截断；改后台运行 + `.exit` 文件取回真实退出码，避免把「超时」误记成「失败」或「只跑子集宣称全绿」。
5. **覆盖率要如实登记、不要凑绿**：本轮 83.02% 达标，但仍刻意不把 `fail_under` 写进默认配置——把一次性实测值固化成主干门禁会让后一次偶发波动直接红灯。
6. **准备度评分差异不必抹平**：`tester` 出报告时点 9/10（第 10 项待收口），`architect` 按材料齐备评 10/10；两者都 ≥9/10。保留时点差异比事后回改评分更可信。

## 5. 范围外 / 未解决（明确不做，转入后续）

- 真实 GitHub Actions workflow、平台 branch protection、覆盖率阈值门禁：本环境无法验证平台侧运行，属独立基础设施 spec，需先做依赖评估。
- Langfuse `:3000` 启动、浏览器控制台其它视图 4×404、全仓 185 个历史 lint 债务：环境 / 历史债务，非本轮引入。
- 历史 spec `013` / `016` / `037` 的 7 处评审文档引用断链：机械化校验中发现，属历史既有，未越界修复。
- `frontend-reviewer` 的 2 项 P2 信息性观察（B1 文案口径滞后、D1「非灰卡保持 `var(--muted)`」未显式锁断言）：实现正确、不阻断，记入后续整理。

## 6. 结论

追加范围五 **通过验收并批准收口**，spec 状态 `实施中 → 已完成`。无 P0 / P1、无 API E2E 失败、无关键产物缺失；所有已知非阻塞项逐条登记，未虚报全绿。闭环后仅本地 commit，`origin/main` 保持 `42bbc188`。
