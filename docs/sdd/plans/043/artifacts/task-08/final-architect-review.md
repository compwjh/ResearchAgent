# Spec043 Task08 架构师最终门禁复审与签字

> **状态：FINAL REVIEW / GO（READY_FOR_USER）**
> 日期：2026-10-22（Asia/Shanghai）
> 候选：`a328932`，`http://127.0.0.1:8000/`

## 1. 审查范围与证据边界

本次只审查文档与已落盘证据，不修改业务代码、测试、服务、数据库或 Git，不部署、不提交、不读取 `.env`。已核对：

- Spec043、需求/技术/验收评审草稿、`SDD-GATE-CHECKLIST.md` 的 Gate 5 与 DoD；
- Task08 `coverage-audit.md`、`final-candidate-runtime.md`、`deployment-verification.md`、`live-api-e2e.md`、`regression-report.md`、`final-browser-export.md`；
- Spec018 同范围 PDF 安全/发布修复目录的 `acceptance-review.md`、`backend-review.md`、`regression-repair-review.md`、`inventory-refresh.md`、`runtime-e2e.md`。

本复审基于 tester 已签字的最终验收报告，不把历史候选或未执行项推断为通过；Spec 状态同步、DoD 台账和提交仍由主会话完成。

## 2. 当前证据判断

### 2.1 a328932 runtime：真实 PASS，但仅限 runtime smoke

`runs/20261022-092419-a328932-final-runtime/evidence.json` 明确绑定 `candidate_commit=a328932`、端口 8000、时间窗口和 HTTP 请求结果。其内容与 `final-candidate-runtime.md` 一致：

- `/api/ready`、`/api/health`、首页及 `styles.css?v=59`、地图 CSS/JS 资源均为真实 HTTP 成功；四项 warmup 均 ready。
- 两张地图身份被明确分开：导出地图为 21 nodes/17 edges；全文地图为 21 nodes/18 edges；没有把 GAT 节点错归到导出地图。
- GAT 文档 source hash 为 `verified` 且 source/indexed hash 相等，v1/v2 均 `indexed`/100%；全文 analysis v2 completed，摘要 v1 仍保留。
- application binding 通过真实 POST 返回 13 个严格递增 SSE 事件，`done=completed`，sources 只含目标 document；消息 GET postcheck 也为 completed。

因此可以确认“当前候选 runtime/API 冒烟 PASS”。报告同时如实标记了新建地图、失败恢复、处理中 UI、页面/API 一致性和全量回归未在本轮执行；该报告的 `overall=BLOCKED` 是正确的，不应改写为最终 GO。

### 2.2 历史失败不回溯误判当前，但仍须保留

`1a3ff26` 的首轮全量 `3191 passed / 18 failed / 14 skipped / 67 subtests / 5 warnings`、14 项普通沙箱浏览器启动失败，以及早期 provider 限流/空图记录均是不可覆盖的历史证据。它们不能自动判定 `a328932` 失败；同样，提权诊断的 16 项通过也不能替代当前候选的最终全量。

最新 `a328932` 全量报告已给出实际命令、退出码、完整计数和隔离说明：`exit 0`，`3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`；2 个 skip 均是未设置 `RUN_E2E=1` 的仓库约定生命周期 guard。历史 BLOCK 保留为历史，不再构成当前候选阻塞。

### 2.3 浏览器：同候选最终收口证据已通过

`final-candidate-browser.md` 已明确绑定候选 `a328932`，并记录真实 Chromium/Playwright、普通 locator、无 force click/evaluate click、232 次 GET、页面错误 0、1440/375 视口、两张地图计数、详情/全文历史、375 详情关闭、无横向溢出。列表关闭初次 180ms 快照命中 `.18s` 动画；后续 180–600ms 复核确认 `hidden`、移出视口、`pointer-events=none`、`elementFromPoint` 不拦截且 `wait_for(hidden)` 通过。因此该观察已被正确分类为时序现象，不是当前缺陷。历史 `1a3ff26` 浏览器证据继续按历史来源保留。

历史浏览器证据仍只用于补充未变更能力；最终当前候选判断以 `final-candidate-browser.md` 为准，未把旧候选文件名改写为当前候选。

## 3. Spec018 同范围 PDF 安全/发布修复判断

本次授权范围仅为 PDF 安全分类、manifest/hash/generation 发布门禁及其全文 evidence gate 接缝，不扩大为重新验收整个 Spec018。

- `backend-review.md` 的最终窄复审已将原三项 P1（解析前 source mismatch 留旧 ready、literal 伪造安全目标、page generation 错配）逐项闭合，110 项受影响测试通过，结论为 backend implementation review **GO**。
- `regression-repair-review.md` 的矩阵维护复审已确认 entry/test 双向引用、evidence 路径、八文件 hash/digest、当前 revision 与闭集均修复；末尾增量结论 **GO**。文档保留了前一节的历史 BLOCK，不应把该历史段误读为当前内容复审仍 BLOCK。
- `inventory-refresh.md` 的架构签字只表示冻结清单门禁已完成并置为 verified，不代表 Spec018 或 Spec043 的最终全量、部署和验收均已完成。
- `runtime-e2e.md` 早期 `dd616d5` scoped run 的 shared-pool/fulltext gate BLOCK 必须保留；后续 `82c816f` 真实全文链路（canonical verified、v1 indexed、全文 analysis/conversation 完成且引用锁定目标 document）以及 a328932 的只读 corroboration 证明同范围运行链路已恢复。该后续 PASS 不应倒写覆盖早期限制，也不构成 Spec018 整体再次收口签字。
- `acceptance-review.md` 当前为 tester 与 architect 已签的 `READY_FOR_USER` 修复范围追加结论；仍声明不替代 Spec018 整体状态同步，范围边界保持诚实。

结论：Spec018 同范围修复的窄范围 review/runtime 证据足以作为 Spec043 当前候选的全文安全接缝支撑；它不是 Spec018 全量最终验收的替代物，也没有发现需要把已通过的后续 runtime 重新判为历史 BLOCK 的实质依据。

## 4. Gate 5 / DoD 最终判定

| 门禁项 | 当前判定 | 依据/缺口 |
|---|---|---|
| tester 验收报告含逐项结论 | 已通过 | `043-acceptance-review.md` 已由 tester 签字为 `READY_FOR_USER`。 |
| 真实 runtime 主链路 | 已通过（限定） | a328932 runtime smoke 与脱敏 `evidence.json` 可复核；不含新建地图/失败恢复/处理中 UI。 |
| 最终全量回归 | 已通过 | a328932：exit 0，3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings；2 skip 为合法 `RUN_E2E` guard。 |
| 当前候选浏览器/人工闭环 | 已通过 | a328932 browser smoke、`manual-acceptance.md` 与列表动画后复核均已落盘。 |
| 无 P0/P1 | 已通过 | tester/coverage audit 明确无已确认 P0/P1；provider partial、历史失败、非物理真机和未执行故障注入均按限制披露。 |
| tester 签字 | 已通过 | a328932 最终全量、runtime、browser 和人工步骤均已签字，结论 `READY_FOR_USER`。 |
| architect 签字 | 已通过 | 本文签署独立 architect 最终复审；仅签当前候选与 Spec018 本次修复范围。 |
| Spec/Task/台账/复盘 DoD | 待主会话行政收口 | 不属于业务验收缺口；主会话仍需同步状态台账、复盘并按项目规则提交。 |

## 5. 最终结论与限制

**最终架构结论：`GO`（`READY_FOR_USER`）。** tester 的十项准备度在签字前报告为 `9/10+`（第 10 项等待 architect）；本次 architect 签字后 Gate 5 准备度闭环为 **10/10**。P0=0，P1=0；没有未解释的当前候选失败。

放行范围与限制如下：

1. 仅签 `a328932` 当前候选、Spec043 Task08 Gate 5 和 Spec018 `2026-10-21-pdf-safety-repair` 同范围安全/发布修复；不恢复 Spec032，不把 Spec018 历史正式范围扩张为本次签字。
2. Semantic Scholar partial/限流、旧候选失败、旧 `INDEX_FINALIZE_REQUIRED`、非物理真机浏览器边界和未执行跨 owner/晚回调故障注入均已保留并按证据类别披露，不被本 GO 改写为 complete/live。
3. `READY_FOR_USER` 表示可交付用户人工验收；Spec 状态、Task/README、`spec-status-changelog.md`、复盘、部署收口和本地 commit 仍由主会话按 DoD 完成，本签字不代替这些行政动作。

## 审查签名

- 角色：architect（独立最终门禁复审）
- 候选：`a328932`；Spec018 修复范围：`2026-10-21-pdf-safety-repair`
- 本文结论：**GO / READY_FOR_USER（10/10；P0=0，P1=0）**
- 业务代码/部署/提交：未执行
- 限制：provider partial、历史候选与失败记录、非物理真机、未执行故障注入和 Spec018 非本次修复范围均保持原分类。
- 最终 architect 签字：**通过（2026-10-22；独立角色；同意进入用户人工验收）**
