> 关联：[spec-045](../../specs/045-evaluation-observability-hardening.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03、04、05、06、07；当前状态：`已完成`（2026-11-08 收口，见「执行结果」）

# Task 08 — 真实集成测试与验收

## 状态与一句话目标

`已完成`。用真实 SDK、真实 Ollama、真实 Langfuse 收口全部 11 项加固，
产出 Q10 四类证据集，并按 `AGENTS.md` 三道门禁完成评审、签字、部署验证与状态台账。

## 背景与前置条件

- 必读：[spec-045](../../specs/045-evaluation-observability-hardening.md) 的「验收」章节、
  Q8/Q9/Q10/Q12；[ADR 0002](../../../adr/0002-langfuse-precondition-and-offline-evaluation-scope.md)；
  两份调研 notes 的第 4/5 节（测试缺口）。
- **F6**：评测 85 个用例、观测约 54 个用例**全部 mock SDK / fake transport**；
  `docs/sdd/plans/042/task-04-offline-evaluation-delivery.md:92` 明示；
  `spec-041:93` 要求每次 langfuse 升版跑一次回归（含 33 项观测测试 + 一次真实对话触发）。
- 已知测试缺口：`plans/013/task-05-instrument-chat-kb.md:80` 要求覆盖「流中断和并发请求」至今缺失；
  `scripts/generate_observability_fixtures.py` 的 `--send` 无覆盖；
  `scripts/setup_langfuse_dashboards.py`、`gen_observability_samples.py` 无测试；
  无「prompt 内含 API key」的隐私回归；无测试能发现「thinking 正文未上报」。
- 前置：task 02 硬前置已完成，task 03–07 均已完成并各自补了红绿测试。
- 流程约束：`AGENTS.md:110-119` 三道评审门禁、`:129` 收口即 DoD、
  `:55-56` Task 定向测试通过不代表 Spec 可收口、收口前必须有当前部署版本的真实 API E2E 成功案例。

## 数据、配置与接口

- 真实依赖：自托管 Langfuse（web 3000 / worker 3030 + ClickHouse/PG/Redis/MinIO）、
  远程 Ollama `192.168.31.180:11434`、主服务 8000。
- `requirements.lock.txt` 锁 `langfuse==4.15.1`；升版冒烟须记录实际版本。
- 不新增业务端点、不改公开接口；本任务只补测试、跑验收、落文档。

## 实施步骤与文件边界

1. **真实 SDK 集成/升版冒烟**：用真 `Langfuse` client（非 mock）跑一次 chat 与 kb-ask，
   核对四段 phase span、`completion_start_time`、7 个 score、trace 归属；
   记录 SDK 版本与私有符号形状。
2. **并发/流中断测试**：SSE 中断、并发请求下 `ContextVar` 不串线，
   trace_id 与 reset token 正确复位（`trace.py:28-32,88-89,117-125`）。
3. **`--send` 与 dashboard 契约测试**：fixtures 导入后 trace 数量/score 可查；
   看板脚本幂等重建不产生重复 widget。
4. **隐私与 thinking 回归**：凭据不落地、思考正文可见（与 task 06 的红测互补，
   这里是真实链路复核，不重复实现）。
5. **Q10 四类证据集汇总**到 `docs/sdd/plans/045/runs/task-08/`：
   ① 红绿测试记录（03/04/09 项）；
   ② 真实 `eval_042` 的 `report.json` + `report.md`（含指纹）；
   ③ Langfuse 完整 trace（四段 phase span + 一次 score 回写 + trace ID）；
   ④ 瀑布图截图。
6. **最终全量回归 + 覆盖率**（`AGENTS.md:55`），三份评审文档落
   `docs/sdd/reviews/045-{requirement,tech,acceptance}-review.md`，
   `tester` 与 `architect` 双签；部署验证；复盘落 `docs/sdd/retro/`。
7. 全部满足后按 `AGENTS.md:129` 转 `已完成`，追加 `spec-status-changelog.md`，
   本地 `git commit`（`AGENTS.md:138`，**不 push、不合 main**）。

**文件边界**：`tests/**`、`docs/sdd/plans/045/runs/task-08/**`、
`docs/sdd/reviews/045-*`、`docs/sdd/retro/`、`docs/sdd/spec-status-changelog.md`、
spec-045 状态字段。若发现需改业务代码，回对应 task 修复，不在本任务扩大范围。

## 子代理分派

- 测试编写/执行：`Task(backend-tester)`、`Task(frontend-tester)`；
  跨端验收总控 `Task(tester)` 出 `045-acceptance-review.md`。
- 需求/技术评审：`Task(backend-dev)` 不适用评审角色，按 `AGENTS.md:110-119` 由
  开发主管/`architect` 承担；架构师签字 `Task(architect)`。
- 主会话只做编排、决策与最小增量落地校验（`AGENTS.md:125`），不代写测试代码。

## 边界与明确不做

- **不做** P2 三项（人工标注 gold 集、分数口径统一、在线实时评测）。
- **不接受** mock / 内部函数 / 仅表单调用冒充真实 E2E（`AGENTS.md:56`）。
- 不改 spec 的目标、数据模型、公开接口或用户行为；若需改动，
  按 `AGENTS.md:68,112` 暂停、修订 spec 并退回 `待确认` 重新确认。
- 不宣称「准备度 10/10」除非十项检查至少九项通过且无 P0/P1 或关键产物缺失
  （模板要求）。
- 不 push、不合 main、不 force push。

## 验收、风险与回滚

| 验收点 | 证据 |
|---|---|
| 真 SDK 冒烟 | 真 client 跑通的 trace ID + 四段 span 截图，SDK 版本记录 |
| 并发/流中断 | 并发用例通过，无 trace_id 串线 |
| 四类证据齐全 | `runs/task-08/` 下四类产物路径全部存在且可查 |
| 全量回归 | 最终 `pytest` 退出码 0 + 覆盖率报告 |
| 三道门禁 | 三份 `045-*-review.md` 结论通过、双签、部署验证记录 |
| 台账 | changelog 有 `实施中 → 已完成` 条目，本地 commit 完成 |

风险：自托管 Langfuse 栈不稳定会阻塞全部真实取证；
`human_agree_rate` 仍为 `null`、两套分数口径仍不统一，须在验收结论中
**如实声明为已声明边界**，不得写成遗漏或失败；
`spec-041:93` 的私有属性升版风险虽经封装缓解，仍需在结论中保留升版回归要求。
任一硬前置或证据缺失 → spec 保持 `实施中`，退回对应 task，不转 `已完成`。

## 产出物、执行结果与变更日志（2026-11-08）

**结论：已完成，验收通过。** 证据索引：[`runs/task-08/q10-evidence-index.md`](./runs/task-08/q10-evidence-index.md)。

| 项 | 真实结果 |
|---|---|
| 真 SDK 冒烟 | `langfuse==4.15.1` 真 client；chat / kb-ask 真实 HTTP 200；`sdk-smoke.json` 含私有符号形状与 trace ID。发现 kb-ask 双 trace 缺陷 → 已修，见 `trace-attribution-fix.json`（单条 trace `1979780d…`，9 observations、四段 phase span、7 scores、根已结束），chat 链路未回归 |
| 并发 / 流中断 / 隐私 | `tests/observability/` 三个新测试（不含编号）；精确 `49 passed, EXIT=0`；`--send` 真重跑 traces 385→405、scores +140；dashboard 默认重建幂等「新建 0 跳过 6」 |
| Q10 四类证据 | ① `q10-red-green-summary.md` + 4 份 RED/GREEN 日志（GREEN `21 passed`）；② `runs/task-02/eval-baseline/report.{json,md}` 五类指纹；③ `runs/task-02/trace-summary.json` + `sdk-smoke.json` + `trace-attribution-fix.json` + `deploy-verification.json`；④ `waterfall.png`（四段 phase span 可见、`hasSecret=false`） |
| 最终全量回归 | `.venv/bin/python -m pytest -q` → `4112 passed, 2 skipped, 5 warnings, 67 subtests passed in 779.30s`，`PYTEST_EXIT=0`；日志 `runs/task-08/full-regression.txt`。项目无覆盖率采集/阈值配置，未宣称覆盖率门禁通过 |
| 部署验证 | 重启后 `/api/health` 200、PID 65665；当前版本 `deploy-chat-sse.txt` `status=completed` 无 error、`deploy-kb-sse.txt` `done` 无 error；kb 单条 trace `220f5fb2…` 9 obs / `root_ended=true`；`deploy-verification.json` |
| 三份评审 | `045-requirement-review.md` 通过、`045-tech-review.md` 通过、`045-acceptance-review.md` 通过且架构师已签字；准备度 **9/10**、P0=0/P1=0 |
| 复盘 / 台账 | `docs/sdd/retro/2026-11-08-spec045-evaluation-observability-closure.md`；`spec-status-changelog.md` 末条 `实施中 → 已完成` |

**commit**：收口 commit 与本文档同一提交，hash 在提交后由 `git log -1` 查得
（同一提交内无法自引用），见最终交付说明。**不 push、不合 main**。

**如实保留的边界**：P2 三项、`human_agree_rate=null`、两套分数口径、值级脱敏不按 key 名、
`--force` 非幂等（默认重建幂等已验证）、`018` revision `8b0cde1`、并列 `started_at` 行序差异、
retention 启动期同步、Langfuse 读回怪癖与 scores `limit=100` 截断、`spec-041:93` 升版回归要求、
无覆盖率配置。见验收评审与复盘。
