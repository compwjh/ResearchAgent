# Spec043 验收评审（tester 最终验收）

> **状态：READY_FOR_USER（tester 与 architect 已签；Spec 状态已由主会话同步为已完成）**
>
> 候选 `a328932` 的真实 API、runtime、最终全量回归与浏览器复核均已通过；列表关闭在等待 180–600ms 后 hidden、移出视口、`pointer-events=none` 且 `wait_for(hidden)` 通过。本文为 tester 与 architect 最终验收结论；Spec 状态已由主会话同步为已完成。用户尚未实际执行人工验收。

日期：2026-10-22（Asia/Shanghai）
角色：tester（独立最终验收）
范围：Spec043 原始确认范围、Task03–Task08 已落盘验收材料；不修改业务代码，不调用 API，不重复已确认的人工/API路径。

## 一、验收判定边界

Spec043 的收口必须同时具备：真实 API E2E、关键产物可查看、可照做的人工步骤、最终全量回归通过、当前候选部署验证、无 P0/P1、人工验收准备度至少 9/10，以及 tester 与 architect 的最终签字。历史候选证据可以证明能力已曾经运行，但不能替代 `a328932` 的最终绑定。

最新全量证据见 [`regression-report.md`](../plans/043/artifacts/task-08/regression-report.md)：a328932 于 09:19:28Z–09:31:55Z 完成，exit 0，`3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`，745.06s；2 个 skip 均为 `RUN_E2E` 未设置的合法生命周期 guard。最终浏览器证据见 [`final-candidate-browser.md`](../plans/043/artifacts/task-08/final-candidate-browser.md)：桌面两图、详情、全文历史、375px 详情关闭、列表关闭动画后的 hidden 状态和无横向溢出均通过。

首轮全量失败保留为历史事实：候选 `1a3ff26` 的隔离 `map_regression_preflight` 为 `3191 passed / 18 failed / 14 skipped / 67 subtests / 5 warnings`；另有 16 项提权浏览器诊断通过，不能替代该历史全量门禁。当前 a328932 runtime smoke 已真实核验首页、`/api/ready`、`/api/health`、两张既有地图、全文 v1/v2、document hash 与 application binding 13-event SSE；最终全量重跑已 exit 0，`3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`。列表关闭初次 180ms 快照只是动画时序，随后 180–600ms 检查和 `wait_for(hidden)` 均通过。

## 二、按 Spec 能力映射证据

| Spec 能力 | 已落盘证据 | 当前覆盖判断 | 明确限制/不重复要求 |
|---|---|---|---|
| 主题创建、稳定身份、图谱读取与部分成功 | [`Task08 live API`](../plans/043/artifacts/task-08/live-api-e2e.md)、fresh map `35a56c6f2da84fca85fc3c21dfa0055c` | **历史 LIVE PASS_WITH_LIMITATIONS**：真实 retry 生成 20 节点，preview/apply 后 21 节点、17 边、revision 3 | `partial`/provider warning 必须保留；等待 a328932 最终产物绑定，不要求重新抓同一主题 |
| citation 与 similarity 关系 | [`Task08 live API`](../plans/043/artifacts/task-08/live-api-e2e.md) | **历史 LIVE PASS_WITH_LIMITATIONS**：11 citation、5 similarity，方向与缺失范围可见 | 不要求把外部 provider 的 partial 伪装为 complete；不要求用户重复已确认调用 |
| 详情字段、来源、缺失回退与边界 | Task03 API/Chrome、Task04/Task07 报告 | **历史主要路径通过** | 全部缺字段与跨 owner 拒绝不是当前新增阻塞，但最终报告应引用已有 TEST/LIVE 分类，不能扩大为全来源成功 |
| 200 节点上限与每批最多 20 | Task03/04 精准集成与真实 preview `21/200` | **TEST/集成 + 历史 LIVE 局部通过** | 不把外部抓取当边界测试；199→200、超 200、超 20 的既有精准测试沿用，除非最终全量明确失败 |
| references 预览、确认、幂等、CAS、墓碑恢复 | Task08 preview 45→apply 1、CAS `409 MAP_CONFLICT`；Task04 refresh/remove→restore | **历史 LIVE PASS_WITH_LIMITATIONS** | 不重复确认同一 diff；只在收口绑定最终候选的证据路径 |
| stop、retry、进程重启与持久恢复 | Task08 stop job `3e5ba79d825349448bfe5852b7e1a747`、restart evidence | **历史 LIVE PASS_WITH_LIMITATIONS**：停止保留 node，重启 events 1–8 单调且无重复 ID | 不要求用户替 Agent 重跑；当前只等待最终 runtime 报告是否绑定 a328932 |
| position/viewport、筛选/图层、刷新保护与移动端 | Task03/04 保存恢复；Task07 `1a3ff26` 375/390/1440 浏览器；a328932 [`final-candidate-browser.md`](../plans/043/artifacts/task-08/final-candidate-browser.md) 桌面/375 详情/列表 | **历史 LIVE + 当前 LIVE PASS**：两图计数、详情、全文历史、375 详情关闭、列表关闭和无横向溢出通过 | 首次 180ms 快照已由后续动画完成复核解释；不外推为物理真机 iOS/Android |
| 项目解绑、地图删除、共享 KB 与旧会话隔离 | Task08 project/map delete postcheck | **历史 LIVE PASS_WITH_LIMITATIONS**：map 删除不删共享 KB/旧 conversation，项目删除仅解绑 | 跨 owner/晚回调故障注入仍应保持 TEST 分类，不伪称已有 LIVE |
| 主动入库、全文 evidence gate、摘要/全文分析与会话 | Task03 `GAT` import；Task05 run `20261021-172344-82c816f-full`；Spec018 repair runtime；a328932 [`final-candidate-runtime.md`](../plans/043/artifacts/task-08/final-candidate-runtime.md)；全文 analysis `3bb20a...`、conversation `cc9f02...` | **历史 LIVE API + 当前 runtime/browser PASS_WITH_LIMITATIONS**：v1/v2 indexed、source hash verified、analysis v2 completed；当前候选真实 application binding 为 13 events、done completed、source doc 精确匹配，GAT UI 历史入口和全文按钮已通过 | v2 `INDEX_FINALIZE_REQUIRED` 等历史失败必须保留；不要求重复全文 POST；不外推所有来源均 ready |
| 分组、删除组只解绑、JSON/PNG 脱敏导出 | Task06 API/browser、Task08 `final-browser-export.md`、a328932 runtime 资产 `exports/task08-live-map-export.{json,png}` | **历史 LIVE PASS + 当前产物可读**：fresh map 为 21 节点/17 边，GAT map 为 21 节点/18 边；JSON/PNG 资产可复核 | 两张地图必须分开查看；Task06 候选较早，最终 UI/人工报告只需正确绑定，不要求重新创建组 |

### 地图/全文样例边界

- fresh 建图样例是 map `35a56c6f2da84fca85fc3c21dfa0055c`，a328932 runtime 读回 revision `5`，导出结果为 21 nodes / 17 edges。
- GAT 全文 ready 样例是 map `0baabeae7268429c9f7e4de8098ae1d0`，a328932 runtime 读回 revision `124`；GAT node 为 `21041260a5394f42891b020128fa60fa`，document 为 `55afc3b8f01445429462fe78ed0d4c98`，该节点不能在 fresh map 中查找。
- 人工验收文档已经把“已保存示例快速查看”和“新建地图完整验收”分开；用户可以直接查看已有 JSON/PNG、21 节点地图和 GAT 全文 ready 产物，不承担 Agent 的重复调用或历史候选对齐工作。

## 三、十项验收准备度（当前候选）

下表是最终双签验收时点状态。`历史通过` 表示历史证据仍保留，`通过` 表示当前候选已有可复核证据；用户人工验收仍待实际执行。

| # | 准备度检查 | 状态 | 证据/限制 |
|---:|---|---|---|
| 1 | Spec 目标、边界与明确不做已能映射 | 历史通过 | [`Spec043`](../specs/043-literature-map-topic-exploration.md)、Task03–08 报告 |
| 2 | 真实 API E2E 请求、响应、实体 ID、终态和产物路径齐全 | 通过 | Task08/Task05 历史链路齐全；a328932 runtime 已记录两图、analysis、document 与 13-event binding；最终全量 exit 0 |
| 3 | 主路径 UI 与自然语言/分析入口可按真实按钮操作 | 通过 | a328932 浏览器覆盖桌面两图、详情、全文历史、375 详情关闭与列表关闭动画后状态 |
| 4 | 关键产物可查看（21 节点地图、GAT 全文、JSON、PNG） | 通过 | a328932 runtime 明确两张地图身份、revision、GAT document v1/v2 与 export JSON/PNG 路径；browser 确认 21/17、21/18 图谱 |
| 5 | 人工步骤含点击后提示、等待、等待中显示、下一步、失败恢复 | 历史通过 | [`manual-acceptance.md`](../plans/043/artifacts/task-08/manual-acceptance.md) 已结构化；不要求用户替 Agent 排查 |
| 6 | 关键失败/降级场景诚实呈现且无 P0/P1 | 通过 | provider partial 属降级合同；a328932 全量 0 failed，浏览器列表关闭动画复核通过 |
| 7 | 最终全量回归通过且退出码/计数可复核 | 通过 | `regression-report.md`：exit 0，3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings；2 skip 为 `RUN_E2E` 未启用的合法 guard |
| 8 | 当前候选部署首页、ready/health 与关键链路验证 | 通过 | [`final-candidate-runtime.md`](../plans/043/artifacts/task-08/final-candidate-runtime.md) 已记录 HTTP 200/ready/health、两图、全文与 binding；服务入口为 `http://127.0.0.1:8000/` |
| 9 | API/浏览器/人工步骤/导出产物统一绑定当前候选 | 通过 | a328932 runtime、全量、browser/产物与 manual 步骤已统一索引；不要求用户重复已验路径 |
| 10 | tester 结论、architect 签字与状态台账闭环 | 通过 | tester 与 architect 均已签字，Spec 状态台账已由主会话同步；用户人工验收仍待实际执行 |

tester 在架构师签字前报告准备度为 **9/10+**；本次 architect 签字后十项均闭环，最终 Gate 5 准备度为 **10/10**。Spec 状态台账已同步完成，不构成用户人工验收阻塞；用户尚未实际执行本文步骤。结论为 `READY_FOR_USER`。

## 四、当前确实未满足的事项

这些是收口硬条件，不是要求用户重复已验路径：

1. a328932 runtime、全量回归、浏览器/人工步骤、JSON/PNG、21 节点 fresh map 与 GAT 全文 ready 样例均已完成证据索引；不把历史失败或 provider partial 改写为成功，也不要求用户重复已验路径。
2. Spec 状态台账已由主会话同步为已完成；这不改变 `READY_FOR_USER` 仅表示可交付用户执行、而非用户已经通过的含义。

已确认的 stop/restart、preview/apply/CAS、保存 viewport、移动触控、分组/导出、map/project 删除保护和全文 API 链路不列为“未验收”；它们只需在最终报告中引用正确 refs。provider partial、Task03 v2 `INDEX_FINALIZE_REQUIRED` 和首轮失败也不应被抹除或转嫁给用户。

## 五、当前结论与签字

**当前结论：`READY_FOR_USER`（tester 与 architect 最终验收通过；Spec 状态已同步为已完成）。** 用户尚未实际执行人工验收，本文不宣称用户已通过。

- Tester：a328932 全量、runtime 与 browser smoke 已通过；10 项准备度达到 **10/10**，签字结论为 `READY_FOR_USER`。
- Architect：通过（2026-10-22；独立最终架构复审；候选 `a328932`；依据本报告、Task08 runtime/full-regression/browser 证据及 `final-architect-review.md`，同意 `READY_FOR_USER`）。限制：provider partial、历史候选/失败、非物理真机与未执行故障注入保持原证据分类；不恢复 Spec032，不改变 Spec 状态。
- Spec 状态：**已完成**（主会话已按双签验收、部署验证与状态台账同步）；历史 Task PASS/失败仍按各自证据分类保留。

依据索引：[`coverage-audit.md`](../plans/043/artifacts/task-08/coverage-audit.md)、[`regression-report.md`](../plans/043/artifacts/task-08/regression-report.md)、[`live-api-e2e.md`](../plans/043/artifacts/task-08/live-api-e2e.md)、[`final-candidate-runtime.md`](../plans/043/artifacts/task-08/final-candidate-runtime.md)、[`final-candidate-browser.md`](../plans/043/artifacts/task-08/final-candidate-browser.md)、[`final-browser-export.md`](../plans/043/artifacts/task-08/final-browser-export.md)、Task03–Task07 `acceptance-report.md`/`api-e2e.md`/`browser-e2e.md`、[`Spec018 repair runtime`](../plans/018/artifacts/2026-10-21-pdf-safety-repair/runtime-e2e.md)。
