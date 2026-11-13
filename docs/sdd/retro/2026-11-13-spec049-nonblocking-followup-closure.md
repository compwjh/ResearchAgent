# Spec-049 复盘：已知非阻塞项定案与刷新旋转反馈修正

> 2026-11-13 ｜ 文档只写结论、事实依据（文件:行 / 命令）与验证方式。

## 1. 交付结果

| 项 | 结果 |
|---|---|
| Spec | `docs/sdd/specs/049-known-nonblocking-followup-cleanup.md`，`待确认 → 已确认 → 实施中 → 已完成` |
| 实现 | `frontend/literature-maps.js:1579-1588` 删 700ms 定时器、两分支链 `.finally` + `.catch` 兜底；`v=48 → v=49` 五处同步；tabs 既有函数内新增静态契约断言 |
| 定案 | A 已闭环 2 项（NB1、NB9）、B 本次实现 1 项（NB2）、C 保持现状 7 项（NB3–NB8、NB10，零改动） |
| Gate 2 | `049-requirement-review.md` / `049-tech-review.md` 均「通过（附意见）」，C1–C10 共 10 条 |
| Gate 4 | `049-frontend-review.md` `APPROVE`（C1–C10 10/10，P0/P1/P2 全 0）；单端 `628 passed / EXIT=0` |
| Gate 5 | `049-acceptance-review.md` 签字 R「通过 / READY」；`merge-decision.md` 签字 A「批准收口」，双签并列非自批 |
| 全量 | `4571 passed / 2 skipped / 83.00% / EXIT=0` |
| E2E / 部署 | Chromium `31/31 PASS`、真实 API 响应捕获、部署 4×200、`artifacts/spec-049-api-sample.md` |
| 交付 | 省略 PR、直接快进推送远端 `main`；不 force push、不新建 PR |

## 2. 证据链

- 计划模式只读勘察：`.github/` ABSENT、`docs/github.md:11-29`、`.coveragerc:21`、`ruff.toml:35,45`、`backend/app/platform/config.py:145-152`、`browser-e2e.json:571`、`literature-maps.js:1579-1587,3224,3470`、`git status --short`。
- 角色分工：`Task(architect)` Gate 2 → `Task(frontend-dev)` 实现 → `Task(frontend-reviewer)` / `Task(frontend-tester)` 单端 → `Task(tester)` E2E + 签字 R → `Task(architect)` 签字 A。纯文档（spec / plans / 台账 / 复盘）由主会话代行并三处留痕。
- 子代理「说改了」不算改了：6 个实现文件、2 份 Gate 2 评审、验收报告、裁决文档均在主会话读回校验后进入下一门禁。

## 3. 经验

1. **定向绿灯不等于全量绿灯**：本轮单端 `628 passed` 后仍跑完整全量 `4571 passed`，Spec 收口阶段全量回归是硬门禁。
2. **CSS 改动必须升 `?v=N`，JS 改动同理**：本次 JS 内容变化触发 `v=48 → v=49`，牵动 index / fixture / 3 处精确断言共 5 处；漏一处即冻结断言失败。
3. **`re.findall(...)[-1]` marker 语义很脆**：`index.html:918-919` 两条纯属性注释必须保持在全文最后一次出现；211 处 `in INDEX` 断言依赖其字面串。升版时**不得新增任何 `?v=` 引用**，只改 live 链接。
4. **新增断言挂在既有测试函数内可保住用例计数基线**：C8 要求 tabs `grep -c "^def test_"` = 12、按钮基线 56；把新静态契约断言加进既有刷新图标测试函数内，既不新增函数也不放宽任何断言。
5. **E2E 判定口径须与真实耗时对齐**：首跑 `28/29 FAIL` 的 `spin_not_fixed_700ms` 是脚本判定 `0<elapsed<600` 与实测 3.7–3.9s 不符；修正为 `|elapsed−700|>100`（旧 700ms 实现下必 FAIL）并新增 2 条更严断言（checks 29→31）。首跑证据逐字保留、不翻案，未改业务代码、未放宽断言。
6. **新增脚本也会抬升全仓 lint 计数**：边界 10 要求 ruff 错误数不变，本轮新增 `browser_e2e.py:224` 的 B007 使 `185 → 186`；把循环变量改 `_` 后回到 185。新引入项应在当前 Task 内闭环，不混入「历史 lint 债务」的非阻塞项。
7. **几何余量 / 冻结断言不要靠改断言凑绿**：Spec-048 的 B2 修复改实现不改阈值；本轮延续该纪律，窄屏 2px 余量、marker 脆弱性保持现状并如实登记。
8. **双阶段评审保留历史**：Gate 2 附意见沉淀为 C1–C10，Gate 5 双签并列；首跑 FAIL、ruff 186 中间态、9 项非阻塞项全部如实登记，不虚报门禁达标。
9. **单端改动只派单端角色**：纯前端改动未跑后端专项 pytest，只在 Spec 收口启动全量回归；避免「改一行 CSS 触发全套后端用例」。
10. **C 类零改动要机械化核对**：`.github/`、`.coveragerc`、`ruff`、CSS、未跟踪清单在确认前后逐项对照落盘，避免「保持现状」被写成「已修复」。

## 4. 已知非阻塞项（9 项，保持现状、零改动）

首跑 E2E FAIL 记录、Langfuse `:3000` transient 告警、其它视图 404、185 个历史 lint、无真实 CI workflow / branch protection、覆盖率未设 `fail_under`、窄屏 2px 余量、marker 既有脆弱性、10 个工作区未跟踪文件。详见 `docs/sdd/reviews/049-acceptance-review.md` §6 与 `docs/sdd/plans/049/runs/decision-ledger.md`。

## 5. 引用路径

- `docs/sdd/plans/049/runs/decision-ledger.md`
- `docs/sdd/plans/049/runs/task-02/implementation.md`
- `docs/sdd/plans/049/runs/task-04/{frontend-regression.md,full-regression.txt,full-regression.exit,browser_e2e.py,browser-e2e.json,browser-e2e-run1.json,refresh-desktop.png,refresh-mobile.png,deploy-verification.json,merge-decision.md,final-verification.md}`
- `docs/sdd/reviews/049-{requirement,tech,frontend,acceptance}-review.md`
- `artifacts/spec-049-api-sample.md`
- `docs/sdd/spec-status-changelog.md`
