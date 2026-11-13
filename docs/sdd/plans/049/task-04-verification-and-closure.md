# 任务 04：定向 / 全量回归、真实 API E2E、评审、部署与复盘

> 关联：[spec-049](../../specs/049-known-nonblocking-followup-cleanup.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02、任务 03；当前状态：`已完成`（全量 4571 passed / E2E 31/31 / 部署 4×200 / 双签批准收口）

## 1. 状态与一句话目标

在真实部署版本上验证「刷新旋转与请求同步」与「C 类零副作用」，完成三份评审、双签、状态台账、复盘与本地 commit，再直接快进推送远端 `main`。

## 2. 背景与前置条件

- 任务 02 / 03 已完成；`frontend-dev` 改动读回校验通过。
- 服务可启动：`./deploy/start.sh -d`（端口占用 `PORT=8300 ./deploy/start.sh -d`）；`http://127.0.0.1:8000/api/health` 200。
- 基线：Spec-048 收口 `4571 passed / 2 skipped / 83.01%`、E2E `18/18 PASS`、部署 `4×200`；本轮只做增量验证与全量收口。

## 3. 数据、配置与接口

- 数据模型 / 端点：**不适用**。
- live 版本：`literature-maps.js?v=49`、`literature-maps.css?v=36`；marker `v=47` / `v=34` 仍在末尾注释区。

## 4. 实施步骤与文件边界

| 序 | 动作 | 命令 / 产物 | 通过标准 |
|---|---|---|---|
| 1 | 定向静态契约 | `pytest -q tests/frontend/test_literature_map_tabs_and_refresh_icon.py` | EXIT=0，新增 `finally` / 无 700ms 断言通过 |
| 2 | 单端全量 | `pytest -q tests/frontend/` | EXIT=0、`628+ passed`、无 skip/xfail 增加 |
| 3 | 静态检查 | `node --check frontend/literature-maps.js`、`.venv/bin/python scripts/check_test_layout.py`、`git diff HEAD --check` | 三项 EXIT=0 |
| 4 | 最终候选全量回归（Spec 收口阶段） | `.venv/bin/python -m pytest -q --cov=backend/app --cov-report=term-missing` | EXIT=0、通过数 ≥ 4571；覆盖率如实登记 |
| 5 | 真实浏览器 / API E2E | Chromium 桌面 1440×900 + 375×812；捕获真实 API 响应（含实体 ID） | 点击刷新后 `is-spinning` 在响应结束后移除、连点 3 次无残留；桌面 + 窄屏 checks 全 PASS；截图 + JSON 落盘 |
| 6 | 部署验证 | curl `/api/health`、`/`、`/assets/literature-maps.js?v=49`、`/assets/literature-maps.css?v=36` | 4×200；live `<script>`=v49、marker 仍在 |
| 7 | Gate 2 / Gate 5 评审 | `Task(architect)` 需求 + 技术评审、`Task(frontend-reviewer)` 代码评审、`Task(tester)` 验收、`Task(architect)` 合并裁决 | 三份评审真实结论、P0=0/P1=0；双签并列非自批 |
| 8 | 收口与交付 | spec → `已完成`、台账追加、复盘落盘、本地 `git commit`、直接快进推送远端 `main` | DoD 全满足；引用路径 0 断链、冲突标记 0 |

## 5. 子代理分派

| 角色 | 分派 | 最小上下文 | 产出 |
|---|---|---|---|
| `frontend-tester` | `Task(frontend-tester)` | task-02 改动清单 + 定向用例 | `runs/task-04/frontend-regression.md`（命令 / 退出码 / 通过数 / 阻塞项） |
| `frontend-reviewer` | `Task(frontend-reviewer)` | diff + spec 边界 1–9 | `docs/sdd/reviews/049-frontend-review.md` |
| `tester` | `Task(tester)` | 全部回归 / E2E / 部署产物路径 | `docs/sdd/reviews/049-acceptance-review.md`（签字 R） |
| `architect` | `Task(architect)` | spec + 三份评审 + 验收材料 | `049-requirement-review.md`、`049-tech-review.md`、合并裁决（签字 A） |

> 单端回归只跑受影响的前端领域；全量回归只在 Spec 收口阶段启动且最终候选必须通过。失败先定向修复再重跑全量，原失败记录保留。

## 6. 边界与明确不做

- 不以 mock / 内部函数调用替代真实 API E2E；不以「应该没问题」代替落盘证据。
- 不改松 / 删 / skip / xfail 断言凑绿；不虚报 CI 全绿 / branch protection 通过 / 覆盖率门禁达标。
- 不改 Spec-048 历史报告正文、不翻案、不重开已完成门禁。
- **不 force push、不新建 PR**；闭环后以 fast-forward 直接快进推送远端 `main`。
- C 类零改动，不启用任何平台配置。

## 7. 验收、风险与回滚

| 验收点 | 判定 |
|---|---|
| 十项人工验收准备度 ≥9/10、无 P0/P1、无 API E2E 失败 | `tester` 报告 |
| 双签 + 台账 + 复盘 + 引用路径 + 状态流转齐全 | Gate 5 DoD |
| 部署 4×200 且服务可访问 | 真实 curl 输出 |

**风险**：升版后浏览器命中旧缓存 → 硬刷新 + 核对源代码 live 版本；窄屏 E2E 侧栏元素在视口外 → 用 hash 路由 `#literature-maps-view` + DOM click 回退（Spec-048 既有方案，不改产品行为）。
**回滚**：保留上一可用 commit；失败则 spec 保持 `实施中` 并记录阻塞，不标记 `已完成`。

## 8. 产出物、执行结果与变更日志

- 产出物：`docs/sdd/plans/049/runs/task-04/`（回归输出、E2E JSON / 截图、部署验证、最终候选验证）、`docs/sdd/reviews/049-*.md`、`docs/sdd/retro/`、`docs/sdd/spec-status-changelog.md` 收口条。
- 执行结果：`frontend-regression.md` 单端 `628 passed / EXIT=0`；`full-regression.txt` + `.exit` 全量 `4571 passed / 2 skipped / 83.00% / EXIT=0`；`browser-e2e.json` `31/31 PASS`（首跑 `browser-e2e-run1.json` `28/29 FAIL` 保留）；`deploy-verification.json` 4×200；`artifacts/spec-049-api-sample.md` 真实 API 成功案例；`049-acceptance-review.md` 签字 R「通过 / READY」+ `merge-decision.md` 签字 A「批准收口」。阻塞项 0。
- 变更日志：2026-11-13 `frontend-tester` / `tester` / `architect` 按 Gate 5 流程落盘；主会话收口：spec `已完成`、台账追加、复盘落盘、本地 commit、省略 PR 直接快进推送远端 `main`。
