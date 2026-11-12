# task-22 追加范围五：独立评审、验收签字与收口

> **产出性质**：纯文档任务书，由主会话代行创建（三处留痕：本头部 / spec 追加范围五 §7 / 状态台账 2026-11-12 收口条）。
> **状态**：`已完成`；依赖 task-20 → task-21（单向）；**分派**：`architect` · `tester` · `frontend-reviewer` · 主会话（编排与收口）。

## 一、目标与前置条件

前置：task-20 / 21 实现落地并读回校验；后台最终候选全量回归已完成；真实浏览器复核与部署验证已 PASS。

目标：Gate 5 独立评审（需求 / 技术 / 验收合并裁决）+ 验收签字 + 代码评审；补齐 spec 状态、台账、复盘、人工验收步骤与本地 commit。

## 二、实施与文件边界

- 独立分派三次，均只读评审、不改业务代码 / spec / 历史评审：`Task(architect)`、`Task(tester)`、`Task(frontend-reviewer)`。
- `tester` 只在 `docs/sdd/reviews/047-acceptance-review.md` **末尾追加 §17**，既有 §1–§16 逐字保留（`shasum` 前后一致）。
- 主会话只做纯文档 / 配置收口与编排；含代码文件的实现一律由 task-20 / 21 的专职子代理承担。
- 机械化校验、状态回填、台账、复盘、人工验收文档、`git commit`。

## 三、验收

- 三份评审结论：`architect` 通过 / 通过 / **批准收口**（P0=0 / P1=0 / P2=0，签字 A）；`tester` §17 **通过**（契约 9/9、§5 8/8、集成 5/5，签字 R，准备度 9/10 ≥ 门槛）；`frontend-reviewer` **APPROVE**（三项必查 PASS，P2=2 信息性）。
- 全量回归 EXIT=0 / `4559 passed` / `83.02%`；`git diff --check` 0；变更文件冲突标记 0；047 引用路径 0 断链；部署 5×200 PASS；收口前 `GET /api/health` 200。
- 十项人工验收准备度 ≥9/10，无 P0 / P1、无 API E2E 失败、无关键产物缺失。

## 四、风险与回滚

风险：签字栏留空即转 `已完成` 属门禁违规；本任务以 `merge-review.md` 架构师签字 + §17 tester 签字双签并列为前提。风险：把历史 spec `013` / `016` / `037` 的 7 处引用断链误记为本轮问题；已在 `final-verification.md` §3 如实区分。回滚：`git revert` 收口 commit 并把 spec 状态退回 `实施中`。

## 五、产出与执行结果

- 裁决：`docs/sdd/plans/047/runs/task-20/merge-review.md`（217 行）。
- 验收：`docs/sdd/reviews/047-acceptance-review.md` §17（1027 行起，文件 1160 行）。
- 代码评审：`docs/sdd/reviews/047-followup-frontend-review.md`（214 行）。
- 最终验证记录：`docs/sdd/plans/047/runs/task-20/final-verification.md`。
- 人工验收步骤：`artifacts/spec-047-followup-cleanup-manual-e2e.md`；复盘：`docs/sdd/retro/2026-11-12-spec047-followup-cleanup-closure.md`。
- 进展日志：`.codebuddy/agent-logs/spec-047/task-22/{architect,tester,frontend-reviewer}/20261112-*.md`。
- **执行结果：`已完成`**；spec 状态 `实施中 → 已完成`，台账已追加；闭环后仅本地 commit，**不 push、不合 main、不 force push**。
