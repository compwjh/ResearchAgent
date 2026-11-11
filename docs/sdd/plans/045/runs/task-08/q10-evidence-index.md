# Spec045 · Q10 四类证据索引（2026-11-08 收口）

> 关联：[spec-045 验收（Q9/Q10）](../../../../specs/045-evaluation-observability-hardening.md) ｜
> [task-08](../../task-08-integration-tests-and-acceptance.md) ｜
> [验收评审](../../../../reviews/045-acceptance-review.md)
>
> 全部为真实落盘产物；mock、内部函数调用、仅表单调用均不作为 E2E 证据。

## 四类证据（缺一不验收）

| 类别 | 产物路径（相对 `docs/sdd/plans/045/`） | 真实结果 |
|---|---|---|
| ① 红绿测试 | `runs/task-08/q10-red-green-summary.md`；`red-03-sampling.log`、`red-04-flush.log`、`red-09-redaction-thinking.log`、`green-current-code.log` | 03 项 RED `2 failed`（同一 trace 采样决策不一致）；04 项 RED `1 failed in 10.34s`（flush 阻塞 SSE 10s）；09 项 RED `8 failed, 7 passed`（明文 `sk-proj-…`、payload 超限、thinking 缺失）；当前代码 GREEN `21 passed, EXIT=0`。历史红测输出原本未落盘，已在隔离副本补可复现取证，未改仓库业务代码 |
| ② 评测产物 | `runs/task-02/eval-baseline/report.json`、`report.md` | 真实 `eval_042 --export`，`dataset_sha256` / `judge_model_digest` / `prompt_sha256` / `seed=42` / `tie_break_rule` 五类指纹齐全；`scored=2 / written=2 / verified=2 / skipped=1 / failed=0`。score 真实重跑 `979 → 979`，delta=0 |
| ③ 可查 trace | `runs/task-02/trace-summary.json`；`runs/task-08/sdk-smoke.json`、`trace-attribution-fix.json`、`deploy-verification.json` | SDK `langfuse==4.15.1`（真 client，非 mock）。基线 trace `98b91aa3…` 四段 phase span + 7 scores；真 SDK 冒烟 chat `2bc3846c…`、kb `b8e36974…` 暴露归属分裂；修复后 TestClient 真链路 `1979780d…` 一条 trace / 9 observations / 四段 phase span / 7 scores / 根 observation 已结束；当前部署版本 kb `220f5fb2…` 同构、chat `f7e44efc…` 5 observations 含四段 phase span |
| ④ 瀑布图截图 | `runs/task-08/waterfall.png` | Langfuse v4.27.0 UI 真实截图（trace `1979780d…`），时间轴可见 `phase:load` / `phase:prefill` / `phase:decode` / `phase:overhead` 四段与 `kb-ask` 根、`kb.embedding`/`kb.retrieval`/`kb.rerank`/`kb.generation`，39.40s。截图区域经文本核对 `hasSecret=false`，不含系统提示与召回历史明文 |

## 补充证据（能力落地与回归）

| 项 | 路径 | 结果 |
|---|---|---|
| 基准卡片 A 打通 | `runs/task-07/benchmark-real.json`、`benchmark-summary.json`、`benchmark-summary.event.json`、`benchmark-card.png`、`benchmark-card-browser.txt` | 真实基准四项指标；事件 seq 40；Chromium 四项指标可见 |
| 分页与 retention | `runs/task-07/paging-api-evidence.txt`、`backend-review.md` | 无参扁平 25 条、`limit=2` 带游标、三类越界 400、逐页 9 页集合一致；评审通过 P0=0/P1=0 |
| 真 SDK / 并发 / 隐私 / dashboard | `runs/task-08/sdk-smoke.json`、`dashboard-contract.json`、`tests/observability/` 三个新测试 | 精确 `49 passed`；`--send` 真重跑 traces 385→405、scores +140；dashboard 默认重建「新建 0 跳过 6」幂等 |
| 最终全量回归 | `runs/task-08/full-regression.txt` | `.venv/bin/python -m pytest -q` → `4112 passed, 2 skipped, 5 warnings, 67 subtests passed in 779.30s`，`PYTEST_EXIT=0` |
| 当前部署版本 E2E | `runs/task-08/deploy-verification.json`、`deploy-chat-sse.txt`、`deploy-kb-sse.txt` | 服务重启后 `/api/health` 200 / PID 65665；chat `status=completed` 无 error；kb-ask `done` 无 error；kb 单条 trace 9 observations、`root_ended=true` |
| 三份评审 | `docs/sdd/reviews/045-{requirement,tech,acceptance}-review.md` | 需求/技术均通过 P0=0/P1=0；验收通过、准备度 9/10、架构师已签字 |

## 已声明边界（不得写成遗漏或失败）

`human_agree_rate=null` 与两套分数口径（P2 明确不做）；在线实时评测不做；
`redaction.py` 值级脱敏、不按 key 名过滤（避免误伤学术文本的设计取舍）；
`setup_langfuse_dashboards.py --force` 非幂等（默认重建已验证幂等，`--force` 未真实重跑）；
`018` 矩阵 `inventory_git_revision` 仍 `8b0cde1`；并列 `started_at` 时无参与分页行序可能不同但集合一致；
retention 默认启动期同步执行；Langfuse `GET /api/public/traces/{id}` 读回怪癖、
`scores?traceId=` 受 `limit=100` 截断（按 7 类 score name 核对）；
`spec-041:93` 私有 SDK 符号升版回归要求保留；
项目无覆盖率采集/阈值配置，本次全量证据为 `pytest -q` 退出码 0 与 4112 passed；
Spec045 不 push、不合 main，`origin/main` 仍 `1b26c76c`。

## 取证过程中的两次纠错（如实留痕）

1. 首次用 `timeout 300 ...` 在 macOS 报 `EXIT=127`，改后台 `nohup` 跑通真实基准。
2. 部署验证脚本初次把 fixtures 合成 trace `aaaaaaaa…`（31 obs / 100 scores）误判为本次 kb-ask，
   已改为按 `220f5fb2…`（9 obs、单条 trace）核对并重写 `deploy-verification.json`；
   `launchctl submit` 未注册成功，按 `deploy/README.md` 允许的 `nohup` 后台方式恢复服务。
