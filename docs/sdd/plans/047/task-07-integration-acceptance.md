# task-07 集成验收收口（三份评审、部署取证、复盘）

> 关联：[spec-047](../../specs/047-evaluation-p2-and-observability-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 06（并汇总 01–06）；当前状态：`已完成`（全量回归 `4180 passed / EXIT=0`、三份评审通过并双签、台账/复盘/本地 commit 闭环） ｜ 对应 spec 表编号 08 ｜ 决策 D6 收口

## 状态与一句话目标

`待执行`。汇总 task-01–06 的红绿测试与当前部署版本真实 E2E 证据，产出验收评审、开发主管签字、复盘与收口核对；**本轮评审阶段不执行收口、不改 spec 状态**。

## 背景与前置条件

- `docs/sdd/SDD-GATE-CHECKLIST.md` §3 收口清单 + `spec-047:215,229-230`；`retro045:42`「重启后重新取证才作数」。
- 前置：task-01–06 全部完成且验证通过；三份评审中需求/技术已落盘（本轮），**验收评审由 tester 在本 task 产出**；`origin/main` 仍 `1b26c76c`。

## 数据 / 配置 / 接口增量

不适用（本 task 为验收/文档收口，不改业务代码 / 数据模型 / 接口 / 配置）。

## 实施步骤与文件边界

**唯一可写文件**：`docs/sdd/reviews/047-acceptance-review.md`（tester 产出）；`docs/sdd/plans/047/runs/task-07/*`（汇总证据）；复盘文档；spec「评审记录 / 变更日志 / 任务计划状态」回填（**由主会话按模板执行，本轮不写状态台账**）。

1. 汇总 `runs/task-01..06/` 的红绿记录 + 真实 E2E 证据（真实请求 / 响应状态码 / 实体 ID / 最终状态 / 产物路径）。
2. `Task(tester)` 产出 `047-acceptance-review.md`：按 spec「产品使用步骤（案例 0–3）/ 边界」逐项判定，附 `文件:行` 依据，结论「通过/不通过」；**不 mock 冒充真实 E2E、不宣称准备度分数**。
3. 全量回归（先 `source .venv/bin/activate`）：`cd backend && python -m pytest -q`（对齐 `4112 passed, 2 skipped` 基线）、`ruff check .`、`python -c "import app"`、前端 `node --check`。
4. 收口核对：三份评审结论为真实结论（无「/」占位）、引用路径真实存在、`origin/main` 仍 `1b26c76c`、**未 push / 未合 main**、状态台账由主会话追加、复盘已落盘。
5. 由架构师评审子代理 `architect` 签字；签字后主会话才转 spec 状态（本轮不改 `实施中` / `已完成`）。

## 子代理分派

- 跨端验收总控 → `Task(tester)`（产出验收评审）；签字 → `Task(architect)`。
- 单端回归汇总 → `Task(backend-tester)` / `Task(frontend-tester)`（若涉前端展示）。

## 边界与明确不做

- **不 push、不合 main、不 git commit**；`origin/main` 仍 `1b26c76c`。
- 不代填三份评审结论、不伪造签字、不 mock 冒充真实 E2E、不宣称准备度分数。
- 不改写 `dashboard-contract.json:92-104` 等 045 已完成证据；不翻 045/013/046 已签字验收结论。
- 不写状态台账（主会话负责）、不改 spec 状态为 `实施中`。

## 验收、风险与回滚

- 验收：Gate 5 清单全勾（报告按产品步骤/边界逐项判定、运行时真实主链路、签字栏填写）；收口清单全勾。
- 风险：某块 E2E 证据缺失 → 退回对应 task 补取证，不进入收口；引用路径失效 → 按 checklist §4 机械化校验命令修正。
- 回滚：验收不通过 → 退回 Gate 4（对应 task），不进入部署 / 状态流转。

## 产出物、执行结果与变更日志

- 产出物：`docs/sdd/reviews/047-acceptance-review.md`、`docs/sdd/plans/047/runs/task-07/*`、复盘文档。
- 执行结果：待执行后填写。
- 变更日志：待执行后填写。

