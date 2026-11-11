# task-18 不相关指标灰色弱化：前端评审 + 单端回归

> **产出性质**：纯文档任务书，由主会话代行创建（三处留痕：本头部 / spec 追加范围四 §13 / 状态台账 2026-11-12 条）。
> **状态**：`已完成`；依赖 task-17 完成。
> **分派**：`frontend-reviewer`（代码评审）与 `frontend-tester`（单端回归）两次独立 `Task`，互不代行。

## 一、评审输入

- 实现：[task-17 任务书](./task-17-evaluation-irrelevant-metric-gray-style.md)、`frontend/styles.css`、`frontend/index.html`、`tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py`。
- 裁决：[spec 追加范围四 §13](../../specs/047-evaluation-p2-and-observability-fixes.md)、[技术评审「追加范围四技术评审」](../../reviews/047-tech-review.md)、[需求评审 §16](../../reviews/047-requirement-review.md)。

## 二、`frontend-reviewer` 必查

1. **DOM 契约**：灰化选择器只作用于 `[data-status="needs_ground_truth"]`；`frontend/app.js` 逐字未改；`card.dataset.status` 渲染仍在；无新 class、无 `innerHTML`。
2. **版本号**：live `styles.css?v=76` / `app.js?v=77`；`v=75` 兼容 marker 为纯属性片段且位于 `index.html` 末尾注释区；6 处精确 live 断言逐处同步；9 处 `in INDEX` 冻结断言与 2 处范围断言未被改动。
3. **XSS / 反伪造**：无 `innerHTML`、无注入面；非 `computed` 仍 `value=null → —`、`detail.reason` 可见、`sample_count` 真实；灰卡不隐藏、`<details>` 可展开；`degraded` / `unavailable` 未被灰化。
4. **WCAG**：V3 用 `#5f626c`（5.0630:1）、V4 `var(--muted-strong)`（6.0947:1），不得出现作废的 `#6b6e78`；复算数值写进报告。
5. **凑绿排查**：无删断言 / 改松正则 / skip / xfail / 重算失败快照迁就实现。

产出 `docs/sdd/reviews/047-frontend-gray-style-review.md`，结论通过/打回 + P0/P1，落盘日志。

## 三、`frontend-tester` 单端回归

- `.venv/bin/python -m pytest -q tests/frontend/`（后端零改动，**不跑后端 pytest**）
- `node --check frontend/app.js`；`git diff --check`；`.venv/bin/python scripts/check_test_layout.py`
- 逐项复核技术评审 P1-2 的 6 处精确断言与 P1-1 的达标色值；复核 `app.js?v=77` 相关断言未受影响。
- 产出 `docs/sdd/plans/047/runs/task-18/frontend-regression.md`（命令 / 退出码 / 通过数 / 阻塞项），落盘日志。

## 四、失败处置

发现实现缺陷留在当前 Task 修复并复审，不退回 `待确认`；只有用户目标 / 数据模型 / 公开接口 / 用户行为变化才修订 spec 并重新确认。连续失败 ≥3 次记「阻塞」并停下告知用户。
