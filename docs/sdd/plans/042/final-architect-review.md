# Spec042 最终架构门禁评审（含预审历史）

> 预审日期：2026-10-23
> 最终评审角色：架构师
> 当前结论：**GO（验收门禁通过；Spec 状态仍由 root 按 DoD 另行收口）**

> 历史预审结论：在 tester 最终报告、headless UI read-back 和同候选最新全量返回前，本文曾记录 `NO-GO / BLOCKED`。该历史判断和原始失败 artifact 保留，已由下方当前证据 supersede，不作为当前候选结论。

本文最终只核对收口证据和剩余门禁，不重审已经独立 GO 的 Task04 后端代码，也不扩大到新增 UI、主服务 API 或其他可选能力。未修改生产代码、测试、服务、`.env` 或 Spec 状态；未发起真实 HTTP 请求。

## 1. 候选与证据边界

当前候选为分支 `codex/spec042-offline-evaluation` 的提交 `145f9d6`。旧候选 `6f644bc` 的完整回归 PASS、真实 API 失败 artifact 及后续诊断均保留，不能迁移为当前候选的收口证据，也不能被新候选结果覆盖。

本预审实际回读的证据如下：

| 证据 | 已支持结论 | 仍不能支持的结论 |
|---|---|---|
| `docs/sdd/plans/042/runs/20261023-0442-real-e2e-145f9d6/api-e2e.md:26-47`、同目录 `report.json`/`report.md` | 当前候选真实 CLI/API 主路径成功；真实 trace、真实 score、一次 POST、exact-ID 回查和双报告均有记录 | API artifact 单独不替代 UI read-back；UI 证据见同 run 的 `ui-readback.md` |
| `docs/sdd/plans/042/runs/20261023-0442-real-e2e-145f9d6/ui-readback.md:1-23` | headless 登录后在同一真实 trace 页面看到 `chat_quality=1.0` 及既有 Scores 控件；UUID 可见性边界如实记录 | 不支持新增 UI/聊天入口存在 |
| `docs/sdd/plans/042/final-regression-report.md:54-97` | 当前候选的历史 exit 1 与最新正式隔离全量 exit 0 均有记录；历史失败 artifact 保留；最新为 `3335 passed / 0 failed / 2 skipped` | 不得删除或改写中间 `[390]` 失败 |
| `docs/sdd/plans/042/mobile-regression-diagnosis.md:1-58` | 390px 单测独立重跑 3 次均通过，未改代码、断言、skip 或使用 force；根因仍未被证实 | 不能据此把全量失败认定为 flaky 或清除历史失败 |
| `docs/sdd/reviews/042-acceptance-review.md:1-5,137-174` | tester 已签 `READY_FOR_USER`，readiness `9/10 + 1 N/A`，无未解决 P0/P1；历史限制如实保留 | Spec 状态/ledger/部署仍由 root 按 DoD 收口 |
| `docs/sdd/specs/042-openeval-agent-evaluation.md:5-7,168-245,261-272` | Spec 仍是实施中；产品入口是 CLI，明确不新增 UI/主服务 API；原先待验证的 UI 步骤现由独立 read-back/验收 artifact 补齐 | 可把“没有新 UI”误判为功能缺失，或据验收 GO 直接跳过 root 的 Spec 状态收口 |
| `docs/sdd/retro/2026-10-23-spec042-offline-evaluation.md:1-50` | 真实 API 最终一致性修复、旧失败保留、全量移动端失败保留和收口条件均有复盘记录 | 复盘本身不能替代最终回归、UI 读回或签字 |
| `docs/sdd/plans/042/langfuse-runtime-preflight.md:229-244` 与 tester readiness | root-owned loopback runtime 健康检查和真实 API 运行时证据已记录；服务边界仍为 loopback | 不扩大到 Spec043/032 或外网/在线评测 |

## 2. 已通过的当前候选主路径（仅限 API/CLI）

`20261023-0442-real-e2e-145f9d6` 的命令在 artifact `api-e2e.md:28-32` 记录为 exit 0。`api-e2e.md:40-47` 和 `report.json` 共同证明：

- 导出的是一个 `synthetic=false` 的真实 trace `9a93fe5d085320fdd3a39f3101327a1e`；本次没有持久化 trace body。
- 本地 judge 使用 `qwen3.5:9b` 重复 3 次，得到 `good`、value `1.0`。
- canonical runner 只发出一次 score POST，创建真实 score `cf95289f-8ef0-4d08-a0a6-81759a6f359e`，`name=chat_quality`，trace 和 value 匹配。
- 生产等待策略执行了 6 次只读 `GET /api/public/scores/{score_id}`，最终每次均是精确 `id/name/traceId/value` 匹配；CLI 的 `status=completed`、`written=1`、`verified=1`、`failed=0`、exit 0 与 `report.json` summary 一致。
- `report.json` 的 `human_agree_rate` 为 `null`，`constructed_gold_only=true`；这是真实 score 创建和自动 judge 证据，不是人工一致率。
- 无第二次 POST、trace mutation、score deletion 或业务 DB write。score 创建本身是 Spec 明确的 Langfuse score 落点，不能把它误报为业务数据变更。

因此，**当前候选的代码/API 主路径门禁可记为 GO**；结合 tester 与本文件的签字，验收门禁已 GO，但这不是 Spec 状态已完成。

旧失败 `docs/sdd/plans/042/runs/20261023-0431-real-e2e/` 仍必须保留：它记录旧短可见性窗口下的 `not_found`，后续只读 exact lookup 才观察到四字段一致。新候选的成功 artifact 没有重放或覆盖该历史 score，符合“不用同名旧 score/first-100 列表项冒充本次结果”的收口要求。

## 3. 收口状态与剩余 DoD

### 3.1 当前候选完整回归已形成 PASS；历史失败仍保留

现有正式报告 `final-regression-report.md:80-97` 已追加同候选最新正式结果：

```text
exit 0
3335 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings
pytest 679.33s (0:11:19)
```

最新回归未筛选、未分片、未设置 `RUN_E2E`，两个 skip 仍是既有研究生命周期 E2E 的合法前置条件；日志和 metadata 位于 `runs/20261023-000644-145f9d6/`。因此当前候选完整回归门禁可记为 **PASS**。

此前失败仍不可抹除：Playwright 在 `tests/frontend/test_frontend_map_mobile_contract.py:100` 点击地图 fixture 时持续 `element is not stable`，并非被 skip 或断言修改掩盖；`mobile-regression-diagnosis.md:16-32` 的三次精确重跑也没有足够证据将其事后定义为 flaky。正式报告 `final-regression-report.md:54-78` 及 `/private/tmp/spec042-final-regression-bm7F8l` 继续作为历史失败证据保留。旧候选 `6f644bc` 的 `3325 passed / 0 failed / 2 skipped` 仍不能替代当前候选，但当前候选已有自己的全量 exit 0。

两个 `RUN_E2E=1` 既有 skip 的合法性已在正式报告说明；它们不是新增失败，也未掩盖最新的 exit 0。

### 3.2 UI/API 一致性已通过；UUID 可见性边界保留

前次桌面 UI 读回因 macOS 锁屏而 `BLOCKED` 的事实仍保留在原 API artifact；它已由同 run 的 `ui-readback.md:1-23` 后续 headless 只读证据补齐。该证据记录登录成功、实际 trace URL/title、页面显示 `chat_quality` 与 `1.0`、既有 `Scores` 与 `Show 4 more scores` 控件，并明确没有保存截图或 trace 原文。

score UUID 未在 UI 可见 DOM 中显示；这是已记录的 UI 边界，不是缺陷。其精确 `id/name/traceId/value` 由同一真实 run 的 API exact GET 核对，未使用同名旧 score、列表前 100 项或二次 POST 冒充本次实体。

这不是要求新增前端功能：Spec 明确产品入口是 CLI，`specs/042-openeval-agent-evaluation.md:157-170` 排除新 UI/主服务 API；这里检查的是既有 Langfuse 展示与真实 score 状态的一致性，以及验收步骤是否可复核，不能把 CLI 无新 UI 误判为缺少新功能。

### 3.3 Gate 5 的独立验收与架构签字已完成

`docs/sdd/SDD-GATE-CHECKLIST.md:106-112` 要求：

1. `tester` 产出按 Spec 产品步骤/边界逐项判定的 `reviews/042-acceptance-review.md`，含通过/不通过结论和文件:行依据；
2. 真实服务主链路运行时验证不能只靠单测；
3. 架构师在验收报告签字；签字为空不得将 Spec 转为已完成。

当前 `reviews/042-acceptance-review.md:1-5,137-174` 已由 tester 给出 `READY_FOR_USER`，readiness 为 `PASS=9/10 + N/A=1`、无未解决 P0/P1；本文件下方补充独立架构师最终签字。tester 签字与本架构师签字均不直接修改 Spec 状态。

### 3.4 DoD 其余项尚未闭合

按 `docs/sdd/SDD-GATE-CHECKLIST.md:128-138`，还须在最终事实齐备后由主流程核对：

- Spec 任务计划、`plans/042/README.md` 和 Task04 状态全部一致且必需任务完成；
- Spec 状态保持“实施中”直到验收签字，之后才能转“已完成”；
- `spec-status-changelog.md` 追加真实状态流转；
- 三份评审结论均是真实结论、变更日志完整、引用路径存在、复盘已落盘；
- 当前候选 loopback runtime、真实 API/UI read-back、人工验收步骤与最终 full 回归证据齐备；root 仍需按 DoD 完成状态台账和部署收口。

本评审不修改这些台账，不替 root 预先更新状态。

## 4. 预审 readiness

| 门禁 | 当前判断 | 依据 |
|---|---|---|
| Task04 后端/API 代码与当前真实 CLI 主路径 | **GO（局部）** | `145f9d6` 一次 POST、六次 exact GET、exit 0；此前后端窄评审/修复记录另行保留 |
| 真实 score 是本次创建的实体 | **PASS** | 本次 `score_id=cf95289f-8ef0-4d08-a0a6-81759a6f359e`，report 与 exact GET 一致；不依赖同名旧 score/first-100 |
| JSON/Markdown/隐私/human agreement 边界 | **PASS（本 run）** | 双报告 completed、summary 一致、敏感正文未落盘、`human_agree_rate=null` |
| 旧失败与真实修复历史 | **PASS（证据保留）** | `20261023-0431-real-e2e` 与后续复盘未被覆盖 |
| 当前候选正式全量回归 | **PASS** | `20261023-000644-145f9d6`：exit 0，`3335 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`；此前 `[390]` 失败和三次精确重跑均保留 |
| 既有 Langfuse UI/API 精确一致性 | **PASS** | `ui-readback.md` 同一真实 trace 显示 `chat_quality=1.0`；UUID 精确身份由 API exact GET 核对 |
| tester 最终验收报告与签字 | **PASS** | `reviews/042-acceptance-review.md:168-174`：`READY_FOR_USER`，9/10 + 1 N/A，无未解决 P0/P1 |
| 架构师最终签字 | **GO（本文件）** | 下方最终签字；范围仅为验收门禁，不修改 Spec 状态 |
| root 的部署/DoD/Spec 状态收口 | **PENDING（非 P0/P1）** | tester 明确把状态台账、部署和最终收口留给 root；Spec 仍保持实施中 |

## 5. 最终架构结论

**当前最终架构验收结论：`GO`。** tester 已完成 Gate 5 验收并签 `READY_FOR_USER`；当前候选的真实 API、headless UI/API 一致性、报告边界、loopback runtime 和最新完整回归均有可复核证据，无未解决 P0/P1。

此 `GO` 是候选实现/验收门禁 GO，不等于 Spec 状态已完成。root 仍须在本地完成 DoD 台账、部署/运行时收口及状态同步；在此之前 Spec 保持“实施中”。

历史 `NO-GO / BLOCKED` 预审记录保持不变：它对应当时尚未到达的 tester、UI 和 full-regression 证据，不应被删除或倒写为从未发生。

## 6. 架构师最终签字

- 角色：`architect` / final acceptance sign-off
- 结论：`GO`（验收门禁通过；允许进入 root 的 DoD/状态收口，不代表 Spec 已完成）
- 依据：tester `READY_FOR_USER`（`reviews/042-acceptance-review.md:168-174`）；真实 CLI/API exit 0、恰好一次 POST、六次 exact GET 四字段一致（`runs/20261023-0442-real-e2e-145f9d6/report.json`、`api-e2e.md:36-47`）；headless 同 trace 页面显示 `chat_quality=1.0` 且既有 Scores 控件可见（`ui-readback.md:7-15`）；当前候选最终 full `3335 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`（`final-regression-report.md:80-97`）；root-owned loopback runtime health 证据与人工步骤已落盘。
- 范围与限制：只 loopback；不新增 UI、在线评测、主服务 API 或人工标注；`human_agree_rate` 保持 `null`；constructed gold 不冒充人工真值；Spec043 未修改，Spec032 仍暂停；旧 API/full/390px 失败 artifact 均保留。
- 签字时间：2026-10-23
