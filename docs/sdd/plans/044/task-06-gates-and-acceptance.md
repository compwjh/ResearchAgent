> 关联：[spec-044](../../specs/044-conversation-answer-display-and-provenance.md) ｜ 索引：[README](./README.md)
> 依赖：任务 05；当前状态：`已完成`（2026-11-08 收口）

# Task06 门禁、验收、台账、复盘、提交

## 1. 状态与一句话目标
- 状态：`已完成`。
- 一句话目标：按 Gate 2/4/5 顺序完成三份评审真实结论、验收签字、台账追加、复盘落盘与本地提交，并做运行时验证与人工验收可复现准备；交付可收口的 Spec044。

## 2. 背景与前置条件
- 依赖 task-05：测试与真实 E2E 已全绿。
- 设计依据：spec「评审记录」「变更日志」「编号说明」；`decision-baseline.md` §4 编号冲突说明、D13。
- 强制流程：Gate 2 双评审通过 → Gate 4 跨端真实分派 → Gate 5 `tester` 验收签字；spec 转 `已完成` 需引用检查与台账通过。

## 3. 数据、配置与接口
- 增量：评审文档（`docs/sdd/reviews/044-*-review.md`）、验收签字、台账追加（`docs/sdd/spec-status-changelog.md`）、复盘落盘、本地 commit。
- 接口：不适用（纯文档/提交动作）。

## 4. 实施步骤与文件边界
1. Gate 2：需求评审 + 技术评审真实落盘结论（不伪造），改变范围时回退修订 spec 与受影响 task。
2. Gate 4：跨端真实分派 `backend-dev`/`frontend-dev` 实施（若尚未执行）。
3. Gate 5：`tester` 总控跨端验收；架构师在验收签字栏签字；给出合并裁决（不自动合 main）。
4. 台账追加：向 `spec-status-changelog.md` 追加一条（四要素齐备），不覆盖历史。
5. 复盘落盘：将复盘写入 `docs/sdd/plans/044/` 或 retro 目录。
6. 引用路径存在性检查：spec/task/reviews 全部链接可解析。
7. 本地 commit（不 push、不合 main 除非用户指示）。
8. 部署与运行时验证：启动服务后 `首页/health` 返回 200，再报告访问地址与启动命令。
9. 人工验收可复现步骤与准备度十项检查。
- 可观察结果：三份评审真实结论、签字栏、台账条目、复盘、commit、运行时 200 与访问地址、十项检查表。

## 5. 子代理分派
- 角色：architect（评审裁决/签字/台账/复盘/提交）、tester（Gate 5 验收总控）、backend-reviewer/frontend-reviewer（评审）；模型：`Deepseek-V4.1-Flash`（评审角色），架构师自身。
- 最小上下文：本 task + spec「评审记录」+ `decision-baseline.md` 全部 + 三份评审文档。
- 单次文件范围：仅 `docs/sdd/reviews/`、`docs/sdd/spec-status-changelog.md`、`docs/sdd/plans/044/` 复盘、本地 commit。
- 回传后架构师读回校验：评审结论真实、签字栏完整、台账追加未覆盖、引用检查通过。

## 6. 边界与明确不做
- 不伪造评审结论；不自动合 main / push（除非用户明确指示）。
- 不改业务实现（task-02/03/04 已落地）；不新增 HTTP 端点（D1）。
- 不擅自改号：若 `architecture-boundary-guards` 分支先合入 main，须用户明确指示后整体顺延 045（§4，范围外）。

## 7. 验收、风险与回滚
- 验收：① Gate 2/4/5 顺序正确、三份评审真实结论；② 验收签字栏填写；③ 台账追加四要素齐备未覆盖；④ 复盘落盘；⑤ 引用路径存在性检查通过；⑥ 本地 commit 成功（未 push/未合 main）；⑦ 运行时首页/health 200 并报告地址与命令；⑧ 人工验收十项检查可复现。
- 风险：评审伪造、台账覆盖历史、误合 main。回滚到 task-05 与 spec，重走门禁。

## 8. 产出物、执行结果与变更日志

**2026-11-08 执行结果：已完成。**

| Gate / 项 | 真实结果 |
|---|---|
| Gate 2 | `044-requirement-review.md`（通过·附意见）、`044-tech-review.md`（首轮打回 2 项 P1 → 复审通过·附意见，原打回保留） |
| Gate 3 | 用户「确认了，你开展工作吧」→ `已确认`，台账已记录 |
| Gate 4 | 真实分派 `backend-dev` ×2、`frontend-dev` ×2（跨端拆两次），主会话读回校验；限流 6004 时按编排规则临时换档，任务结束后还原 |
| Gate 5 | `tester` 产出 `044-acceptance-review.md`：30/30 通过、准备度 10/10、无 P0/P1；`architect` 子代理复核 5 份证据后签字同意收口 |
| 台账 | `docs/sdd/spec-status-changelog.md` 追加 `实施中 → 已完成` 条目 |
| 复盘 | `docs/sdd/plans/044/retro-044.md` |
| 引用检查 | 机械化校验 ①–④ 通过（`结论：/` 无残留、reviews / task 引用路径均存在、架构师行不写死型号） |
| 运行时验证 | 重启 `com.researchagent.recovery8000`（PID 88588），`/` 与 `/api/health` 均 200；7 个静态资源全 200；真实 API + 真实 Chromium E2E 见 `artifacts/spec-044-api-sample.md` |
| 人工验收准备度 | 10/10（验收报告第七节），可复现步骤见 spec「九 / 十」节与 `artifacts/spec044-b-domain-e2e.py` |
| 本地提交 | 单个原子 commit，`Refs: spec-044`；未 push、未合 main |

已知限制（非 P0/P1）：Reranker 模型缺失 → RRF 降级；SSE `progress` 帧不携带 `detail_json`（设计取舍）；A/C 域未做人工手动全流程点击；4 条 404 来自历史会话列表已删除会话的 GET。
