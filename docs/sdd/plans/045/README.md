# 实施计划索引：spec-045 评测与可观测性加固闭环

> 关联：[spec-045 评测与可观测性加固闭环](../../specs/045-evaluation-observability-hardening.md)
> Spec 当前状态：**`已确认`（实施中）** — 2026-11-08 两道评审通过后用户明确确认，见 `spec-status-changelog.md`
> 索引状态（2026-11-08 Spec045 收口）：**全部 8 个任务已完成，spec 状态 `已完成`**。
> Task 07 证据 `runs/task-07/`；Task 08 / Q10 四类证据索引 `runs/task-08/q10-evidence-index.md`；
> 三份评审 `docs/sdd/reviews/045-{requirement,tech,acceptance}-review.md`（架构师已签字）。
> 下方任务索引表保留设计阶段原文作历史记录；**真实进度以 `HANDOVER.md` 第 8 节、各 task 文档「执行结果」与台账最新条目为准**。

## 目标（一句话）

把现有「离线评测 + 可观测性」加固为一套能长期开着、结果可跨版本比较、
能演示能验收的质量基线：发布前后各跑一次评测即可判定回答质量涨跌，
出问题时用一个 ID 还原全链路，而观测上报拖不慢聊天、数据不会越跑越胀。

## 前置与范围

- 范围：P0 + P1 共 11 项（含 Q7 并入的私有 SDK 兼容层）；**P2 三项明确不做**。
- 硬前置（task 02）：启用 Langfuse + 造可复现样本 + 跑通一次真实 E2E。
  缺任一项不得判 spec `已完成`；由验收执行者完成，不由开发任务代劳（Q9）。
- 设计阶段（2026-11-08 之前）不改业务代码、不启用 Langfuse、不跑评测（Q8）；
  **用户确认后已进入实施**，Q8 的「仅交付文档」边界随之解除，
  Task 03–06 的代码与 Task 02 的真实取证均已落地（见台账最新条目）。
- 代行留痕：本目录 7 份 task 文档与设计阶段产出均为纯文档，由主会话代行
  （`AGENTS.md:127` 唯一允许的代行条件），三处留痕见两份 notes 头部、
  spec-045「代行记录」与 `spec-status-changelog.md` 045 条目；
  本轮接手的运行态取证（Task 02）亦属不含代码文件的动作，详见 `runs/task-02/evidence.md`。

## 任务索引

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-045（含 grill with docs 分析、两份调研记录、ADR 0002） | [spec-045 本体](../../specs/045-evaluation-observability-hardening.md) | — | 完成（spec 已 `已确认`） |
| 02 | 验收前置：启用 Langfuse + 造可复现样本 + 跑通一次真实 E2E | [task-02](./task-02-acceptance-preconditions.md) | 01 | **已完成**（接手机器真实取证，见 `runs/task-02/evidence.md`） |
| 03 | 评测可信度：fallback 生效 + 合并判官编排 + 可复现基线 | [task-03](./task-03-evaluation-reproducibility.md) | 02 | 代码与契约测试完成；Q10 ② 真实产物已补 |
| 04 | 评测结果可靠性：score 幂等 + 报告目录文件锁 | [task-04](./task-04-score-idempotency.md) | 02 | **已完成**（`runner.py:563` 已接线；真实重跑 score delta=0） |
| 05 | 观测采样与上报解耦：trace 级采样 + flush 出 SSE + 私有 SDK 兼容层 | [task-05](./task-05-observability-decoupling.md) | 02 | 代码与契约测试完成；Q10 ③ 四段 span 已补 |
| 06 | 链路标识与脱敏：统一 trace_id + 脱敏归一 + payload 上限 + thinking 上报 | [task-06](./task-06-trace-identity-and-redaction.md) | 02 | **已完成**（`spans.py` 已接线，观测侧测试通过） |
| 07 | 数据生命周期与面板：retention + 分页 + 基准卡片收口 | [task-07](./task-07-retention-and-benchmark-card.md) | 02 | **已完成**（A 打通；真机四项指标 + 分页 API + 评审通过） |
| 08 | 真实集成测试与验收：真 SDK 冒烟、并发/流中断、四类证据集、签字复盘 | [task-08](./task-08-integration-tests-and-acceptance.md) | 03–07 | **已完成**（Q10 4/4、全量回归 EXIT=0、三评审双签） |

> task 03–07 相互独立，可在 task 02 就绪后并行；task 08 汇总验收。

## 验收证据集（Q10，缺一不验收）

| 类别 | 证据 | 适用项 |
|---|---|---|
| ① 红绿测试 | 缺陷类先红后绿的测试记录 | 03 / 04 / 09 |
| ② 评测产物 | 一次真实 `eval_042` CLI 的 `report.json` + `report.md`，含数据集/模型/prompt 指纹 | 01 / 02 / 08 |
| ③ 可查 trace | Langfuse 一条完整 trace：四段 phase span + 一次 score 回写，附 trace ID | 03 / 04 / 05 / 07 / 09 / 11 |
| ④ 瀑布图截图 | 时间轴四段可见、顺序正确 | 05 / 11 |

## 关联

- 调研：[045-evaluation-module-survey.md](../../notes/045-evaluation-module-survey.md) ｜
  [045-observability-module-survey.md](../../notes/045-observability-module-survey.md)
- ADR：[0002-langfuse-precondition-and-offline-evaluation-scope.md](../../../adr/0002-langfuse-precondition-and-offline-evaluation-scope.md)
- 上游：[spec-042](../../specs/042-openeval-agent-evaluation.md) ｜
  [spec-041](../../specs/041-langfuse-trace-detail-and-waterfall.md) ｜
  [spec-013](../../specs/013-llm-observability-platform.md)
