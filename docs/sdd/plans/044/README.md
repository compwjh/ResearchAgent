# Spec044 计划目录（plans/044）

> 关联：[spec-044](../../specs/044-conversation-answer-display-and-provenance.md)
> 本目录仅承载 Spec044 的任务拆分与依赖编排；具体设计决策与代码事实约束见 [`decision-baseline.md`](./decision-baseline.md)，做什么/为什么见 spec 本身。

## 目录说明

- Spec044 合并三个能力域：**A** 处理过程步骤证据浮层（可解释）、**B** 参考来源卡片片段定位（可溯源）、**C** 回答 LaTeX 公式渲染与源码浮层（可读）；B/C 零后端改动、不改 SSE 帧体、不新增数据契约。
- `decision-baseline.md`：D1–D13 冻结决策与 C1–C13 代码事实约束（已冻结，frontier 为空）。
- `task-02-backend-evidence-projection.md`：后端 `detail_json` 证据投影。
- `task-03-frontend-step-popover.md`：前端步骤浮层与记录列表。
- `task-04-source-link-routing.md`：来源跳转与片段定位（A 域浮层与 B 域参考来源卡片共用 `jumpToKnowledgeBase` 扩展 + `focusChunk`，禁止第二套高亮）。
- `task-05-contract-tests-and-e2e.md`：契约测试与真实 E2E。
- `task-06-gates-and-acceptance.md`：门禁、验收、台账、复盘、提交。
- `task-07-answer-math-rendering.md`：回答 LaTeX 公式渲染与源码浮层（C 域，两段式安全渲染 + 源码浮层）。
- 任务 01 即 spec 编写本身，以 `spec-044` 为文档，不重复建 task 文件（模板 §任务计划）。

## 任务索引表

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-044 | [`spec-044`](../../specs/044-conversation-answer-display-and-provenance.md) | — | 已完成 |
| 02 | 后端 detail_json 证据投影 | [`task-02-backend-evidence-projection.md`](./task-02-backend-evidence-projection.md) | 01 | 已完成 |
| 03 | 前端步骤浮层与记录列表 | [`task-03-frontend-step-popover.md`](./task-03-frontend-step-popover.md) | 02 | 已完成 |
| 04 | 来源跳转与片段定位 | [`task-04-source-link-routing.md`](./task-04-source-link-routing.md) | 03 | 已完成 |
| 05 | 契约测试与真实 E2E | [`task-05-contract-tests-and-e2e.md`](./task-05-contract-tests-and-e2e.md) | 04、07 | 已完成 |
| 06 | 门禁、验收、台账、复盘、提交 | [`task-06-gates-and-acceptance.md`](./task-06-gates-and-acceptance.md) | 05 | 已完成 |
| 07 | 回答 LaTeX 公式渲染与源码浮层 | [`task-07-answer-math-rendering.md`](./task-07-answer-math-rendering.md) | 01 | 已完成 |

> **07 为后补任务**：逻辑位置在 04 与 05 之间（依赖 01，独立实施），编号后补是为不破坏已落盘双向链接；07 可在 02–04 期间并行实施，但须在 05 前完成（05 的 C 域契约 / E2E 依赖 07，对应 P1-2 / Gate2-F1）。

## 状态总览

**全部 7 个任务已完成，Spec044 已收口**（2026-11-08）。全量回归 `4030 passed / 2 skipped / 67 subtests / EXIT=0`；Gate 5 验收 30/30 通过并经架构师签字；真实 API E2E 与真实 Chromium B 域 E2E 均跑通。详见 [`044-acceptance-review.md`](../../reviews/044-acceptance-review.md) 与 `artifacts/spec-044-api-sample.md`。

## 依赖链

```
01（编写 spec）→ 02 → 03 → 04 → 05 → 06
                   └→ 07（LaTeX 公式渲染，依赖 01；逻辑位置在 04 与 05 之间，独立实施）→ 05（07 → 05 汇聚边，05 须等 07 完成后执行）
```

## 边界声明（按阶段如实记录）

**设计阶段（2026-11-07，历史保留）**
- 建档为纯文档：仅 `architect` + `doc-updater` 参与，产出 spec、计划目录骨架、状态台账条目；不改业务代码、不跑测试、不部署、不 push、不合 main；所有 task 保持 `待执行`、spec 保持 `待确认`，停等用户明确确认。
- 唯一新增第三方依赖为本地 `frontend/vendor/katex/`（用户已明确授权放宽「不引入第三方依赖」，**仅限此项**，不含 CDN/npm/新框架/新组件库）。

**实施与收口阶段（2026-11-08）**
- 用户明确确认后，跨端改动拆为 `backend-dev` / `frontend-dev` 两次分派；`tester` 验收、`architect` 签字。
- 全量回归 `4030 passed / 2 skipped / 67 subtests / EXIT=0`；真实 API E2E 与真实 Chromium B 域 E2E 落盘 `artifacts/`；部署验证通过（首页与 `/api/health` 均 200）。
- 本地 commit 已完成；**未 push、未合 main**（除非用户明确指示）。
